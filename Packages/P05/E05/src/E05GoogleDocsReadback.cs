using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

public sealed record DriveAppendReceipt(string RunId, string DocumentId,
    string? RevisionBefore, string? RevisionAfter, string Status, int ExpectedChars);

// Uses existing host OAuth flow. No service-account secrets, token persistence or
// whole-document rewrites. The host must explicitly approve each document.
public sealed class GoogleDocsAppendReadback
{
    private const int MaxDocBytes = 8 * 1024 * 1024;
    private readonly HttpClient client;
    private readonly Func<CancellationToken, Task<string>> accessToken;

    public GoogleDocsAppendReadback(HttpClient client,
        Func<CancellationToken, Task<string>> accessToken)
    { this.client = client; this.accessToken = accessToken; }

    public async Task<DriveAppendReceipt> AppendAsync(string documentId, string runId,
        string entry, CancellationToken stop)
    {
        if (string.IsNullOrWhiteSpace(runId) || runId.Length > 160 ||
            string.IsNullOrWhiteSpace(entry) || entry.Length > 100000 ||
            !entry.Contains(runId, StringComparison.Ordinal) ||
            string.IsNullOrWhiteSpace(documentId))
            throw new ArgumentException("Invalid receipt inputs");
        foreach (char c in documentId)
            if (!(char.IsAsciiLetterOrDigit(c) || c is '_' or '-'))
                throw new ArgumentException("Invalid document ID");
        if (!IsSafeRunId(runId)) throw new ArgumentException("Invalid RunID");

        string uri = "https://docs.googleapis.com/v1/documents/" + documentId;
        string token = await accessToken(stop).ConfigureAwait(false);
        if (string.IsNullOrWhiteSpace(token))
            return new(runId, documentId, null, null, "NO_AUTH", entry.Length);

        try
        {
            using var before = await SendAsync(HttpMethod.Get, uri + "?includeTabsContent=true",
                token, null, stop).ConfigureAwait(false);
            if (!before.IsSuccessStatusCode)
                return new(runId, documentId, null, null, "READ_FAILED", entry.Length);
            using var beforeJson = await ParseBoundedAsync(before, stop).ConfigureAwait(false);
            string? revision = ReadRevision(beforeJson.RootElement);
            if (string.IsNullOrWhiteSpace(revision))
                return new(runId, documentId, null, null, "NO_REVISION", entry.Length);
            var priorText = new StringBuilder();
            GatherText(beforeJson.RootElement, priorText);
            string current = priorText.ToString();
            if (current.Contains(entry, StringComparison.Ordinal))
                return new(runId, documentId, revision, revision, "ALREADY_PRESENT", entry.Length);
            if (current.Contains(runId, StringComparison.Ordinal))
                return new(runId, documentId, revision, revision, "RUNID_COLLISION", entry.Length);

            string payload = JsonSerializer.Serialize(new {
                requests = new object[] { new { insertText = new {
                    endOfSegmentLocation = new { }, text = entry } } },
                writeControl = new { requiredRevisionId = revision }
            });
            using var write = await SendAsync(HttpMethod.Post, uri + ":batchUpdate",
                token, payload, stop).ConfigureAwait(false);
            if (!write.IsSuccessStatusCode)
                return new(runId, documentId, revision, null,
                    write.StatusCode == System.Net.HttpStatusCode.BadRequest ?
                        "REVISION_CONFLICT_OR_REJECTED" : "APPEND_REJECTED", entry.Length);

            using var after = await SendAsync(HttpMethod.Get, uri + "?includeTabsContent=true",
                token, null, stop).ConfigureAwait(false);
            if (!after.IsSuccessStatusCode)
                return new(runId, documentId, revision, null, "READBACK_FAILED", entry.Length);
            using var afterJson = await ParseBoundedAsync(after, stop).ConfigureAwait(false);
            var buffer = new StringBuilder();
            GatherText(afterJson.RootElement, buffer);
            string? revAfter = ReadRevision(afterJson.RootElement);
            return new(runId, documentId, revision, revAfter,
                buffer.ToString().Contains(entry, StringComparison.Ordinal) ? "READBACK_PASS" :
                    "READBACK_MISMATCH", entry.Length);
        }
        catch (InvalidDataException)
        {
            return new(runId, documentId, null, null, "DOCUMENT_TOO_LARGE", entry.Length);
        }
        catch (JsonException)
        {
            return new(runId, documentId, null, null, "INVALID_GOOGLE_RESPONSE", entry.Length);
        }
        // Cancellation should propagate, not be interpreted as success.
    }
    private static bool IsSafeRunId(string id)
    {
        foreach (char c in id)
            if (!(char.IsAsciiLetterOrDigit(c) || c is '-' or '_' or '.')) return false;
        return true;
    }
    private static string? ReadRevision(JsonElement root) =>
        root.TryGetProperty("revisionId", out var r) ? r.GetString() : null;

    private static async Task<JsonDocument> ParseBoundedAsync(HttpResponseMessage response,
        CancellationToken stop)
    {
        if (response.Content.Headers.ContentLength > MaxDocBytes)
            throw new InvalidDataException("Google Doc exceeds bound");
        await using var source = await response.Content.ReadAsStreamAsync(stop).ConfigureAwait(false);
        using var ms = new MemoryStream();
        var buf = new byte[16384];
        while (true)
        {
            int n = await source.ReadAsync(buf.AsMemory(), stop).ConfigureAwait(false);
            if (n == 0) break;
            if (ms.Length + n > MaxDocBytes) throw new InvalidDataException("Google Doc exceeds bound");
            ms.Write(buf, 0, n);
        }
        ms.Position = 0;
        return await JsonDocument.ParseAsync(ms, cancellationToken: stop).ConfigureAwait(false);
    }
    private async Task<HttpResponseMessage> SendAsync(HttpMethod method, string uri,
        string token, string? json, CancellationToken stop)
    {
        using var req = new HttpRequestMessage(method, uri);
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        if (json is not null) req.Content = new StringContent(json,
            Encoding.UTF8, "application/json");
        return await client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead,
            stop).ConfigureAwait(false);
    }
    private static void GatherText(JsonElement e, StringBuilder buffer)
    {
        if (e.ValueKind == JsonValueKind.Object)
        {
            if (e.TryGetProperty("textRun", out var t) &&
                t.TryGetProperty("content", out var c) && c.ValueKind == JsonValueKind.String)
                buffer.Append(c.GetString());
            foreach (var p in e.EnumerateObject())
                if (p.Name != "textRun") GatherText(p.Value, buffer);
        }
        else if (e.ValueKind == JsonValueKind.Array)
            foreach (var value in e.EnumerateArray()) GatherText(value, buffer);
    }
}
