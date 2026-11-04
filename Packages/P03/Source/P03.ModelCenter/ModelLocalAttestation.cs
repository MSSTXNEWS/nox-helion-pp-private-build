using System.Net.Http;
using System.Text.Json;
using System.Text;
using System.Text.RegularExpressions;

namespace Nox.P03;

/// <summary>
/// Standalone safety checks used BY the canonical OllamaModelAdapter; no new
/// downloader, queue, host, UI, model registry, or provider is introduced.
/// Does not infer license rights or a verified install from an HTTP status.
/// </summary>
public static class ModelLocalAttestation
{
    public const int MaxEventCharacters = 1024 * 1024;
    public const int MaxStreamingEvents = 250_000;
    public const long MaxTagsResponseBytes = 8 * 1024 * 1024;
    public const long MaxReceiptBytes = 128 * 1024;
    private static readonly Regex HexSha = new("^[0-9a-fA-F]{64}$", RegexOptions.Compiled);

    public static void RequireNoExistingReparsePoint(string path)
    {
        // Check the ORIGINAL path and every existing ancestor before opening.
        // Path.GetFullPath alone does not reveal a symlink/junction source.
        var cursor = new FileInfo(Path.GetFullPath(path));
        for (var parent = cursor.Directory; parent is not null; parent = parent.Parent)
        {
            if (parent.Exists && (parent.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("REPARSE_POINT_DIRECTORY_NOT_AUTHORIZED");
        }
        if (File.Exists(path) || Directory.Exists(path))
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("REPARSE_POINT_FILE_NOT_AUTHORIZED");
        }
        else if (new FileInfo(path).LinkTarget is not null)
            throw new InvalidDataException("BROKEN_SYMLINK_NOT_AUTHORIZED");
    }

    public static void RequireRegularUnlinkedFile(string path)
    {
        RequireNoExistingReparsePoint(path);
        if (!File.Exists(path)) throw new FileNotFoundException("Model GGUF file not found.", path);
        if ((File.GetAttributes(path) & FileAttributes.Directory) != 0)
            throw new InvalidDataException("MODEL_PATH_IS_NOT_A_FILE");
    }

    public static void RequirePrivateUnlinkedDirectory(string path)
    {
        // Host retains exclusive responsibility for the user-data ACL.
        RequireNoExistingReparsePoint(path);
        Directory.CreateDirectory(path);
        RequireNoExistingReparsePoint(path);
    }

    public static string? ParseUnambiguousModelDigest(JsonElement root, string model)
    {
        if (string.IsNullOrWhiteSpace(model) || root.ValueKind != JsonValueKind.Object ||
            !root.TryGetProperty("models", out var items) || items.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("OLLAMA_TAGS_INVALID_SCHEMA");
        string? digest = null;
        foreach (var item in items.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object ||
                !item.TryGetProperty("name", out var name) || name.ValueKind != JsonValueKind.String)
                throw new InvalidDataException("OLLAMA_TAGS_MALFORMED_MODEL");
            if (!string.Equals(name.GetString(), model, StringComparison.Ordinal)) continue;
            if (digest is not null) throw new InvalidDataException("OLLAMA_TAGS_AMBIGUOUS_MODEL");
            if (!item.TryGetProperty("digest", out var d) || d.ValueKind != JsonValueKind.String)
                throw new InvalidDataException("OLLAMA_TAGS_MISSING_DIGEST");
            var value = d.GetString();
            if (value is null || !value.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ||
                value.Length != 71 || !HexSha.IsMatch(value[7..]))
                throw new InvalidDataException("OLLAMA_TAGS_INVALID_DIGEST");
            digest = value.ToLowerInvariant();
        }
        return digest;
    }

    /// <summary>Reads NDJSON a fixed-size chunk at a time. Never calls ReadLineAsync,
    /// whose allocation could grow without bound on hostile Ollama output.</summary>
    public static async IAsyncEnumerable<string> ReadBoundedEventLinesAsync(TextReader reader,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var buffer = new char[4096];
        var line = new StringBuilder(4096);
        while (true)
        {
            var read = await reader.ReadAsync(buffer.AsMemory(), ct);
            if (read == 0) break;
            for (var i = 0; i < read; i++)
            {
                var c = buffer[i];
                if (c == '\n')
                {
                    if (line.Length > 0 && line[^1] == '\r') line.Length--;
                    if (line.Length > 0) yield return line.ToString();
                    line.Clear();
                }
                else
                {
                    if (line.Length >= MaxEventCharacters)
                        throw new InvalidDataException("OLLAMA_STREAM_LINE_EXCEEDS_LIMIT");
                    line.Append(c);
                }
            }
        }
        if (line.Length > 0) yield return line.ToString();
    }

    private static string? ReadString(JsonElement root, string name, int maximum)
    {
        if (!root.TryGetProperty(name, out var item) || item.ValueKind == JsonValueKind.Null) return null;
        if (item.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("OLLAMA_STREAM_INVALID_" + name.ToUpperInvariant());
        var value = item.GetString();
        if (value is null || value.Length > maximum || value.Any(char.IsControl))
            throw new InvalidDataException("OLLAMA_STREAM_UNSAFE_" + name.ToUpperInvariant());
        return value;
    }

    private static long? ReadCounter(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var item) || item.ValueKind == JsonValueKind.Null) return null;
        if (item.ValueKind != JsonValueKind.Number || !item.TryGetInt64(out var counter) || counter < 0)
            throw new InvalidDataException("OLLAMA_STREAM_INVALID_" + name.ToUpperInvariant());
        return counter;
    }

    public static OllamaStreamUpdate ParseVerifiedEvent(string line)
    {
        if (string.IsNullOrWhiteSpace(line) || line.Length > MaxEventCharacters)
            throw new InvalidDataException("OLLAMA_STREAM_EMPTY_OR_OVERSIZED_EVENT");
        try
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("OLLAMA_STREAM_NONOBJECT_EVENT");
            var status = ReadString(root, "status", 512) ?? "unknown";
            var error = ReadString(root, "error", 2048);
            var digest = ReadString(root, "digest", 71);
            var completed = ReadCounter(root, "completed");
            var total = ReadCounter(root, "total");
            if ((completed is not null && total == 0) ||
                (completed is { } done && total is { } bound && done > bound))
                throw new InvalidDataException("OLLAMA_STREAM_BAD_PROGRESS");
            if (digest is not null && (digest.Length != 71 ||
                !digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ||
                !HexSha.IsMatch(digest[7..])))
                throw new InvalidDataException("OLLAMA_STREAM_BAD_LAYER_DIGEST");
            return new OllamaStreamUpdate(status, completed, total, digest, error);
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("OLLAMA_STREAM_MALFORMED_JSON", ex);
        }
    }

    /// <summary>Success must be the unique final event, not a fabricated mid-stream status.</summary>
    public static async IAsyncEnumerable<OllamaStreamUpdate> ReadValidatedStreamAsync(TextReader reader,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var count = 0;
        var successSeen = false;
        await foreach (var line in ReadBoundedEventLinesAsync(reader, ct))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (++count > MaxStreamingEvents)
                throw new InvalidDataException("OLLAMA_STREAM_EVENT_COUNT_EXCEEDED");
            if (successSeen)
                throw new InvalidDataException("OLLAMA_STREAM_DATA_AFTER_SUCCESS");
            var evt = ParseVerifiedEvent(line);
            if (evt.Status.Equals("success", StringComparison.OrdinalIgnoreCase)) successSeen = true;
            yield return evt;
        }
    }

    /// <summary>Atomically creates one immutable receipt. A duplicate job ID never overwrites evidence.</summary>
    public static async Task WriteNewReceiptAsync(string directory, ModelInstallReceipt receipt, CancellationToken ct)
    {
        if (receipt.JobId == Guid.Empty || receipt.Schema != "NOX_P03_INSTALL_RECEIPT_V1")
            throw new InvalidDataException("INSTALL_RECEIPT_IDENTITY_INVALID");
        RequirePrivateUnlinkedDirectory(directory);
        var path = Path.Combine(directory, $"{receipt.JobId:N}.json");
        RequireNoExistingReparsePoint(path);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var file = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                4096, FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await JsonSerializer.SerializeAsync(file, receipt, new JsonSerializerOptions(JsonSerializerDefaults.Web), ct);
                await file.FlushAsync(ct);
                file.Flush(flushToDisk: true);
            }
            // No overwrite even if another task completed the same job concurrently.
            File.Move(temp, path, overwrite: false);
            await VerifyReceiptAsync(path, receipt, ct);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    public static async Task<string?> ReadUnambiguousDigestAsync(HttpClient http, string model, CancellationToken ct)
    {
        using var response = await http.GetAsync("api/tags", HttpCompletionOption.ResponseHeadersRead, ct);
        if (!response.IsSuccessStatusCode) return null;
        // Redirects must be DISABLED in the #6-owned HttpClientHandler before requests.
        if (response.RequestMessage?.RequestUri is { } resolved &&
            (resolved.Scheme != Uri.UriSchemeHttp ||
             !((resolved.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase)) ||
               (System.Net.IPAddress.TryParse(resolved.Host, out var ip) && System.Net.IPAddress.IsLoopback(ip)))))
            throw new InvalidDataException("OLLAMA_REDIRECT_NOT_LOCAL");
        await response.Content.LoadIntoBufferAsync(MaxTagsResponseBytes);
        ct.ThrowIfCancellationRequested();
        await using var body = await response.Content.ReadAsStreamAsync(ct);
        using var doc = await JsonDocument.ParseAsync(body, cancellationToken: ct);
        return ParseUnambiguousModelDigest(doc.RootElement, model);
    }

    public static async Task VerifyReceiptAsync(string path, ModelInstallReceipt expected, CancellationToken ct)
    {
        RequireRegularUnlinkedFile(path);
        await using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            8192, FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (file.Length < 2 || file.Length > MaxReceiptBytes)
            throw new InvalidDataException("INSTALL_RECEIPT_SIZE_INVALID");
        var stored = await JsonSerializer.DeserializeAsync<ModelInstallReceipt>(file,
            new JsonSerializerOptions(JsonSerializerDefaults.Web), ct);
        if (stored is null || stored.Schema != "NOX_P03_INSTALL_RECEIPT_V1" ||
            stored.JobId != expected.JobId || stored.ModelTag != expected.ModelTag ||
            stored.Operation != expected.Operation ||
            !stored.CompletedAtUtc.EqualsExact(expected.CompletedAtUtc) ||
            stored.LocalSha256 != expected.LocalSha256 ||
            stored.LocalBytes != expected.LocalBytes ||
            stored.OllamaDigest != expected.OllamaDigest ||
            stored.LicenseSource != expected.LicenseSource ||
            stored.OllamaEndpoint != expected.OllamaEndpoint ||
            stored.MergedPayloadSha256 != expected.MergedPayloadSha256 ||
            stored.MergeReceiptSha256 != expected.MergeReceiptSha256 ||
            stored.TrainingReceiptSha256 != expected.TrainingReceiptSha256 ||
            stored.RightsAttestationId != expected.RightsAttestationId ||
            stored.RightsAttestationSha256 != expected.RightsAttestationSha256 ||
            stored.NativeApprovalId != expected.NativeApprovalId ||
            JsonSerializer.Serialize(stored.ImportedFiles) != JsonSerializer.Serialize(expected.ImportedFiles))
            throw new InvalidDataException("INSTALL_RECEIPT_READBACK_MISMATCH");
    }
}