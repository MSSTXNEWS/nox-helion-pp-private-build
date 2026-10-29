using System;
using System.IO;
using System.Collections.Generic;
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
        if (!ValidInput(documentId, runId, entry))
            throw new ArgumentException("Invalid receipt inputs");
        stop.ThrowIfCancellationRequested();

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
            if (!TryBody(beforeJson.RootElement, null, out var tabId, out var beforeBody))
                return new(runId, documentId, revision, null, "INVALID_DOCUMENT_TAB", entry.Length);
            var priorText = new StringBuilder();
            GatherText(beforeBody, priorText);
            string current = priorText.ToString();
            if (current.Contains(entry, StringComparison.Ordinal))
                return new(runId, documentId, revision, revision, "ALREADY_PRESENT", entry.Length);
            if (current.Contains(runId, StringComparison.Ordinal))
                return new(runId, documentId, revision, revision, "RUNID_COLLISION", entry.Length);

            var location = new Dictionary<string, string>();
            if (tabId is not null) location["tabId"] = tabId;
            string payload = JsonSerializer.Serialize(new {
                requests = new object[] { new { insertText = new {
                    endOfSegmentLocation = location, text = entry } } },
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
            string? revAfter = ReadRevision(afterJson.RootElement);
            if (string.IsNullOrWhiteSpace(revAfter))
                return new(runId, documentId, revision, null, "NO_READBACK_REVISION", entry.Length);
            // A successful insert must produce a newer revision for readback.
            if (string.Equals(revision, revAfter, StringComparison.Ordinal))
                return new(runId, documentId, revision, revAfter, "STALE_READBACK_REVISION", entry.Length);
            // Legacy first-body responses carry no stable tab identity. Do not
            // infer that a newly tabbed response refers to that same body.
            if (tabId is null && afterJson.RootElement.ValueKind == JsonValueKind.Object &&
                afterJson.RootElement.TryGetProperty("tabs", out _))
                return new(runId, documentId, revision, revAfter, "READBACK_TAB_MISSING", entry.Length);
            if (!TryBody(afterJson.RootElement, tabId, out _, out var afterBody))
                return new(runId, documentId, revision, revAfter, "READBACK_TAB_MISSING", entry.Length);
            var buffer = new StringBuilder();
            GatherText(afterBody, buffer);
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
    internal static bool ValidInput(string documentId, string runId, string entry)
    {
        if (string.IsNullOrWhiteSpace(documentId) || documentId.Length > 256 ||
            string.IsNullOrWhiteSpace(runId) ||
            runId.Length > 160 || !IsSafeRunId(runId) || string.IsNullOrWhiteSpace(entry) ||
            entry.Length > 100000 || !entry.Contains(runId, StringComparison.Ordinal)) return false;
        foreach (char c in documentId)
            if (!(char.IsAsciiLetterOrDigit(c) || c is '_' or '-')) return false;
        return true;
    }

    // Google Docs includeTabsContent=true returns bodies under document.tabs.
    // Append and readback must share one tab identity; never join unrelated tabs,
    // headers or footnotes to manufacture a successful entry match.
    private static bool TryBody(JsonElement root, string? selectedTab,
        out string? tabId, out JsonElement body)
    {
        tabId = selectedTab;
        body = default;
        if (root.ValueKind != JsonValueKind.Object) return false;
        if (!root.TryGetProperty("tabs", out var tabs))
            return selectedTab is null && root.TryGetProperty("body", out body) &&
                body.ValueKind == JsonValueKind.Object; // Legacy single-body DTO.
        if (tabs.ValueKind != JsonValueKind.Array || tabs.GetArrayLength() == 0) return false;
        if (selectedTab is null)
        {
            var first = tabs[0];
            if (first.ValueKind != JsonValueKind.Object ||
                !first.TryGetProperty("tabProperties", out var properties) ||
                properties.ValueKind != JsonValueKind.Object ||
                !properties.TryGetProperty("tabId", out var id) ||
                id.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(id.GetString()))
                return false;
            selectedTab = tabId = id.GetString();
        }
        int matches = 0;
        FindTabBodies(tabs, selectedTab!, ref body, ref matches);
        return matches == 1 && body.ValueKind == JsonValueKind.Object;
    }
    private static void FindTabBodies(JsonElement tabs, string tabId,
        ref JsonElement body, ref int matches)
    {
        foreach (var tab in tabs.EnumerateArray())
        {
            if (tab.ValueKind != JsonValueKind.Object) continue;
            if (tab.TryGetProperty("tabProperties", out var properties) &&
                properties.ValueKind == JsonValueKind.Object &&
                properties.TryGetProperty("tabId", out var id) &&
                id.ValueKind == JsonValueKind.String && id.GetString() == tabId)
            {
                matches++;
                if (tab.TryGetProperty("documentTab", out var documentTab) &&
                    documentTab.ValueKind == JsonValueKind.Object &&
                    documentTab.TryGetProperty("body", out var candidate)) body = candidate;
            }
            if (tab.TryGetProperty("childTabs", out var children) && children.ValueKind == JsonValueKind.Array)
                FindTabBodies(children, tabId, ref body, ref matches);
        }
    }
    private static bool IsSafeRunId(string id)
    {
        foreach (char c in id)
            if (!(char.IsAsciiLetterOrDigit(c) || c is '-' or '_' or '.')) return false;
        return true;
    }
    private static string? ReadRevision(JsonElement root) =>
        root.ValueKind == JsonValueKind.Object &&
        root.TryGetProperty("revisionId", out var r) &&
        r.ValueKind == JsonValueKind.String ? r.GetString() : null;

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
            if (e.TryGetProperty("textRun", out var t) && t.ValueKind == JsonValueKind.Object &&
                t.TryGetProperty("content", out var c) && c.ValueKind == JsonValueKind.String)
                buffer.Append(c.GetString());
            foreach (var p in e.EnumerateObject())
                if (p.Name != "textRun") GatherText(p.Value, buffer);
        }
        else if (e.ValueKind == JsonValueKind.Array)
            foreach (var value in e.EnumerateArray()) GatherText(value, buffer);
    }
}
