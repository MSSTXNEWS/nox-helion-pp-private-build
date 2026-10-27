#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.P03.WorkerQueue;

namespace NoxHelion.P03.WorkerTransport;

/// <summary>
/// Isolated Ollama HTTP adapter for the existing P03 durable queue.
/// No WPF, host bridge, background daemon, or second queue is introduced.
/// Target: .NET 8. Integration and Windows runtime verification belong to #6/#7.
/// </summary>
public sealed class OllamaTransferAdapter : IDisposable
{
    public sealed record TransferEvent(string JobId, string Phase, long? Completed, long? Total);
    public sealed record GgufImportReceipt(string Model, string FileSha256, long FileBytes, bool BlobPresent, bool ModelListed);
    private sealed class Active
    {
        public readonly CancellationTokenSource Token;
        public int DesiredState; // 0 ordinary/pause, 1 permanent cancellation
        public Active(CancellationTokenSource token) => Token = token;
    }

    private readonly HttpClient _client;
    private readonly ModelDownloadQueueStore _queue;
    private readonly ConcurrentDictionary<string, Active> _active = new(StringComparer.Ordinal);
    private static readonly Regex Sha = new("^[a-fA-F0-9]{64}$", RegexOptions.Compiled);
    private static readonly Regex Model = new(@"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?:[a-zA-Z0-9][a-zA-Z0-9._-]*$", RegexOptions.Compiled);

    public OllamaTransferAdapter(ModelDownloadQueueStore queue, Uri ollamaEndpoint)
    {
        _queue = queue ?? throw new ArgumentNullException(nameof(queue));
        if (ollamaEndpoint is null || ollamaEndpoint.Scheme != Uri.UriSchemeHttp ||
            !string.IsNullOrEmpty(ollamaEndpoint.UserInfo) ||
            !string.IsNullOrEmpty(ollamaEndpoint.Query) ||
            !string.IsNullOrEmpty(ollamaEndpoint.Fragment) ||
            ollamaEndpoint.AbsolutePath != "/" ||
            !(ollamaEndpoint.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
              (IPAddress.TryParse(ollamaEndpoint.Host, out var ip) && IPAddress.IsLoopback(ip))))
            throw new ArgumentException("Only a local, unprivileged Ollama HTTP endpoint is allowed.", nameof(ollamaEndpoint));

        _client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
        {
            BaseAddress = ollamaEndpoint,
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    // On a fresh process, an orphaned Downloading item is not reset or discarded.
    // It becomes a visible retryable failure; real byte counters are preserved.
    public async Task<int> RecoverInterruptedAsync(CancellationToken cancellationToken = default)
    {
        int changed = 0;
        foreach (var item in await _queue.SnapshotAsync(cancellationToken).ConfigureAwait(false))
        {
            if (item.State == ModelDownloadState.Downloading && !_active.ContainsKey(item.QueueId))
            {
                await _queue.TransitionAsync(item.QueueId, ModelDownloadState.Failed,
                    "INTERRUPTED_RETRY_REQUIRED", cancellationToken).ConfigureAwait(false);
                changed++;
            }
        }
        return changed;
    }

    public bool Pause(string queueId) => Stop(queueId, false);
    public bool Cancel(string queueId) => Stop(queueId, true);

    // Stopping the HTTP stream is a client-side STOP. Ollama may share an existing
    // pull and may resume server-side downloads. Do not claim remote hard abort.
    private bool Stop(string queueId, bool permanent)
    {
        if (!_active.TryGetValue(queueId, out var operation)) return false;
        if (permanent) Interlocked.Exchange(ref operation.DesiredState, 1);
        operation.Token.Cancel();
        return true;
    }

    public async Task CancelQueuedAsync(string queueId, CancellationToken cancellationToken = default)
    {
        if (Cancel(queueId)) return;
        var item = (await _queue.SnapshotAsync(cancellationToken).ConfigureAwait(false))
            .Single(x => x.QueueId == queueId);
        if (item.State is ModelDownloadState.Pending or ModelDownloadState.Paused or ModelDownloadState.Failed)
            await _queue.TransitionAsync(queueId, ModelDownloadState.Cancelled,
                cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task PullAsync(string queueId, string expectedManifestDigestSha256,
        IProgress<TransferEvent>? events = null, CancellationToken cancellationToken = default)
    {
        if (!Sha.IsMatch(expectedManifestDigestSha256 ?? ""))
            throw new ArgumentException("An independently verified manifest SHA-256 is required.");
        var snapshot = (await _queue.SnapshotAsync(cancellationToken).ConfigureAwait(false))
            .Single(x => x.QueueId == queueId);
        if (snapshot.Evidence.GetProvenanceFailures().Count != 0)
            throw new InvalidDataException("Artifact provenance must be complete before transfer.");
        ValidateModel(snapshot.Evidence.ArtifactReference);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var active = new Active(linked);
        if (!_active.TryAdd(queueId, active))
            throw new InvalidOperationException("Job is already active in this process.");
        bool started = false;
        try
        {
            if (snapshot.State == ModelDownloadState.Failed)
                await _queue.TransitionAsync(queueId, ModelDownloadState.Pending).ConfigureAwait(false);
            else if (snapshot.State == ModelDownloadState.Downloading)
                throw new InvalidOperationException("Recover interrupted work before retry.");
            await _queue.TransitionAsync(queueId, ModelDownloadState.Downloading).ConfigureAwait(false);
            started = true;
            using var request = JsonPost("api/pull", new {
                model = snapshot.Evidence.ArtifactReference, stream = true, insecure = false
            });
            using var response = await _client.SendAsync(request,
                HttpCompletionOption.ResponseHeadersRead, linked.Token).ConfigureAwait(false);
            await RequireSuccessAsync(response, linked.Token).ConfigureAwait(false);
            await using var stream = await response.Content.ReadAsStreamAsync(linked.Token).ConfigureAwait(false);
            using var reader = new StreamReader(stream, Encoding.UTF8);
            var layers = new Dictionary<string, (long completed, long total)>(StringComparer.Ordinal);
            bool success = false;
            while (await reader.ReadLineAsync(linked.Token).ConfigureAwait(false) is { } line)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                if (ReadString(root, "error") is { Length: > 0 } error)
                    throw new InvalidDataException("OLLAMA_ERROR: " + error);
                var phase = ReadString(root, "status") ?? "unknown";
                if (phase == "success") success = true;
                var digest = ReadString(root, "digest");
                if (digest is not null && TryLong(root, "total", out var total) && total > 0)
                {
                    TryLong(root, "completed", out var completed);
                    if (completed < 0 || completed > total) throw new InvalidDataException("Bad Ollama progress counters.");
                    if (layers.TryGetValue(digest, out var previous))
                        layers[digest] = (Math.Max(completed, previous.completed), Math.Max(total, previous.total));
                    else layers.Add(digest, (completed, total));
                    long sumCompleted = checked(layers.Values.Sum(v => v.completed));
                    long sumTotal = checked(layers.Values.Sum(v => v.total));
                    var persisted = (await _queue.SnapshotAsync(linked.Token).ConfigureAwait(false))
                        .Single(x => x.QueueId == queueId);
                    if (sumCompleted >= persisted.CompletedBytes && sumTotal >= persisted.TotalBytes)
                        await _queue.UpdateProgressAsync(queueId, sumCompleted, sumTotal, linked.Token).ConfigureAwait(false);
                    events?.Report(new TransferEvent(queueId, phase, sumCompleted, sumTotal));
                }
                else events?.Report(new TransferEvent(queueId, phase, null, null));
            }
            if (!success) throw new InvalidDataException("Ollama stream ended without a success record.");
            if (!await HasModelDigestAsync(snapshot.Evidence.ArtifactReference,
                expectedManifestDigestSha256, linked.Token).ConfigureAwait(false))
                throw new InvalidDataException("LOCAL_MANIFEST_DIGEST_MISMATCH");
            var end = (await _queue.SnapshotAsync(linked.Token).ConfigureAwait(false))
                .Single(x => x.QueueId == queueId);
            // Cached downloads without a genuine byte receipt are kept unverified.
            if (end.TotalBytes <= 0 || end.CompletedBytes != end.TotalBytes)
                throw new InvalidDataException("TRANSFER_BYTE_RECEIPT_MISSING");
            await _queue.TransitionAsync(queueId, ModelDownloadState.Completed).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (started)
        {
            var next = Volatile.Read(ref active.DesiredState) == 1
                ? ModelDownloadState.Cancelled : ModelDownloadState.Paused;
            await _queue.TransitionAsync(queueId, next).ConfigureAwait(false);
            throw;
        }
        catch (Exception ex) when (started)
        {
            var code = ex is HttpRequestException ? "OLLAMA_NETWORK_OR_HTTP" :
                ex is JsonException ? "OLLAMA_BAD_JSON" :
                ex is InvalidDataException ? "OLLAMA_VERIFICATION_FAILED" : "OLLAMA_TRANSFER_FAILED";
            await _queue.TransitionAsync(queueId, ModelDownloadState.Failed, code).ConfigureAwait(false);
            throw;
        }
        finally
        {
            _active.TryRemove(queueId, out _);
        }
    }

    /// <summary>
    /// Imports ONE user-authorized local GGUF file. Rights/size/hash evidence is
    /// supplied by the caller, never guessed. No remote file download is done.
    /// Split GGUF requires a separate multi-blob adapter.
    /// </summary>
    public async Task<GgufImportReceipt> ImportGgufAsync(
        string modelName, string localFile, long expectedBytes, string expectedSha256,
        string rightsReceipt, IProgress<TransferEvent>? events = null,
        CancellationToken cancellationToken = default)
    {
        ValidateModel(modelName);
        if (string.IsNullOrWhiteSpace(rightsReceipt) || !Sha.IsMatch(expectedSha256 ?? "") ||
            expectedBytes <= 0 || !Path.GetExtension(localFile).Equals(".gguf", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("GGUF rights, exact bytes, SHA-256, and file type are required.");
        await using var file = new FileStream(Path.GetFullPath(localFile), FileMode.Open,
            FileAccess.Read, FileShare.Read, 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (file.Length != expectedBytes) throw new InvalidDataException("GGUF size mismatch.");
        var magic = new byte[4];
        if (await file.ReadAsync(magic, cancellationToken).ConfigureAwait(false) != 4 ||
            Encoding.ASCII.GetString(magic) != "GGUF") throw new InvalidDataException("Invalid GGUF header.");
        file.Position = 0;
        var digest = Convert.ToHexString(await SHA256.HashDataAsync(file, cancellationToken)
            .ConfigureAwait(false)).ToLowerInvariant();
        if (!digest.Equals(expectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("GGUF SHA-256 mismatch.");
        file.Position = 0;
        events?.Report(new TransferEvent(modelName, "sha256-verified", expectedBytes, expectedBytes));
        string uri = "api/blobs/sha256:" + digest;
        using (var head = await _client.SendAsync(new HttpRequestMessage(HttpMethod.Head, uri),
            cancellationToken).ConfigureAwait(false))
        {
            if (head.StatusCode == HttpStatusCode.NotFound)
            {
                using var upload = new HttpRequestMessage(HttpMethod.Post, uri) { Content = new StreamContent(file) };
                using var posted = await _client.SendAsync(upload, cancellationToken).ConfigureAwait(false);
                if (posted.StatusCode != HttpStatusCode.Created && posted.StatusCode != HttpStatusCode.OK)
                    await RequireSuccessAsync(posted, cancellationToken).ConfigureAwait(false);
            }
            else await RequireSuccessAsync(head, cancellationToken).ConfigureAwait(false);
        }
        events?.Report(new TransferEvent(modelName, "blob-present", null, null));
        using (var request = JsonPost("api/create", new {
            model = modelName, stream = true,
            files = new Dictionary<string, string> { [Path.GetFileName(localFile)] = "sha256:" + digest }
        }))
        using (var response = await _client.SendAsync(request,
            HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false))
        {
            await RequireSuccessAsync(response, cancellationToken).ConfigureAwait(false);
            await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
            using var reader = new StreamReader(stream, Encoding.UTF8);
            bool success = false;
            while (await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false) is { } line)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                if (ReadString(root, "error") is { Length: > 0 } error)
                    throw new InvalidDataException("OLLAMA_CREATE_ERROR: " + error);
                var phase = ReadString(root, "status") ?? "unknown";
                events?.Report(new TransferEvent(modelName, phase, null, null));
                if (phase == "success") success = true;
            }
            if (!success) throw new InvalidDataException("GGUF create ended without success.");
        }
        if (!await HasModelDigestAsync(modelName, null, cancellationToken).ConfigureAwait(false))
            throw new InvalidDataException("GGUF_MODEL_NOT_IN_LOCAL_TAGS");
        return new GgufImportReceipt(modelName, digest, expectedBytes, true, true);
    }

    private static void ValidateModel(string name)
    {
        if (!Model.IsMatch(name ?? "") || name.EndsWith(":latest", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Use an exact non-latest, locally authorized model tag.");
    }

    private async Task<bool> HasModelDigestAsync(string name, string? requiredDigest, CancellationToken token)
    {
        using var result = await _client.GetAsync("api/tags", token).ConfigureAwait(false);
        await RequireSuccessAsync(result, token).ConfigureAwait(false);
        using var doc = JsonDocument.Parse(await result.Content.ReadAsStringAsync(token).ConfigureAwait(false));
        if (!doc.RootElement.TryGetProperty("models", out var models) ||
            models.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Invalid Ollama tags response.");
        foreach (var item in models.EnumerateArray())
        {
            if (string.Equals(ReadString(item, "name"), name, StringComparison.OrdinalIgnoreCase) &&
                (requiredDigest is null ||
                 string.Equals(ReadString(item, "digest")?.Replace("sha256:", ""),
                    requiredDigest, StringComparison.OrdinalIgnoreCase))) return true;
        }
        return false;
    }

    private static HttpRequestMessage JsonPost(string path, object value) =>
        new(HttpMethod.Post, path) {
            Content = new StringContent(JsonSerializer.Serialize(value), Encoding.UTF8, "application/json")
        };
    private static string? ReadString(JsonElement root, string key) =>
        root.TryGetProperty(key, out var x) && x.ValueKind == JsonValueKind.String ? x.GetString() : null;
    private static bool TryLong(JsonElement root, string key, out long value)
    {
        value = 0;
        return root.TryGetProperty(key, out var x) &&
               x.ValueKind == JsonValueKind.Number && x.TryGetInt64(out value);
    }
    private static async Task RequireSuccessAsync(HttpResponseMessage response, CancellationToken token)
    {
        if (response.IsSuccessStatusCode) return;
        string reason = (await response.Content.ReadAsStringAsync(token).ConfigureAwait(false));
        if (reason.Length > 256) reason = reason[..256];
        throw new HttpRequestException("Ollama HTTP " + (int)response.StatusCode + ": " + reason);
    }

    public void Dispose() => _client.Dispose();
}
