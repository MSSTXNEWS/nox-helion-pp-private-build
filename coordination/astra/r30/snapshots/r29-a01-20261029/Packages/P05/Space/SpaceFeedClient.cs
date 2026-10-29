// NOX V16 / E05 candidate: isolated contract, NOT wired into MainWindow or host.
// BCL-only. Providers/endpoints are injected by host after license/security review.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.Space.E05;

public sealed record FeedSnapshot(
    string FeedId, string Source, DateTimeOffset? SourceTimestamp,
    DateTimeOffset FetchedAt, JsonElement? Data, string Status,
    string? ErrorCode, bool IsStale);
// No simulated metrics. Unsupported sensors and progress MUST be null.
public sealed record SensorReading(string Id, double? Value, string Unit,
    string Provider, DateTimeOffset? ObservedAt, string Status);
public sealed record ProgressEvidence(string TaskId, decimal Weight,
    decimal? ConfirmedPercent, string? ReceiptId, string State);
public static class EvidenceProgress
{
    public static decimal? WeightedProduct(IReadOnlyList<ProgressEvidence> lanes)
    {
        // Exactly five product blocks; E06/E07 are gates, not weights.
        decimal[] weights = { .20m, .25m, .20m, .25m, .10m };
        if (lanes.Count != 5) return null;
        decimal result = 0;
        for (int i = 0; i < 5; i++)
        {
            var lane = lanes[i];
            if (lane.Weight != weights[i] || lane.ConfirmedPercent is null ||
                lane.ConfirmedPercent < 0 || lane.ConfirmedPercent > 100 ||
                string.IsNullOrWhiteSpace(lane.ReceiptId) ||
                lane.State != "ACCEPTED") return null;
            result += lane.ConfirmedPercent.Value * weights[i];
        }
        return result;
    }
}
public sealed class SpaceFeedClient
{
    // Limit BOTH announced and streamed provider bytes before JSON materialization.
    // ResponseHeadersRead and request timeout alone do not bound response size.
    private const int MaximumFeedResponseBytes = 8 * 1024 * 1024;
    private sealed class FeedResponseTooLargeException : Exception { }
    private readonly HttpClient _http;
    // A cache entry is bound to the exact provider AND approved HTTPS endpoint.
    // FeedId alone is not an authorization or provenance identity.
    private readonly record struct CacheIdentity(string FeedId, string Provider, string Endpoint);
    private readonly ConcurrentDictionary<CacheIdentity, FeedSnapshot> _cache = new();
    private readonly TimeSpan _ttl;
    private readonly TimeSpan _timeout;
    public SpaceFeedClient(HttpClient http, TimeSpan ttl, TimeSpan timeout)
    {
        _http = http ?? throw new ArgumentNullException(nameof(http));
        if (ttl <= TimeSpan.Zero || timeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException();
        _ttl = ttl; _timeout = timeout;
    }

    // ID examples: weather, nox-news, eur-usd, eur-rub, bitcoin, brent, finance-news.
    // Exact source and timestamp must be provided by the trusted adapter; never guessed.
    public async Task<FeedSnapshot> FetchAsync(
        string id, Uri endpoint, string provider, Func<JsonElement, DateTimeOffset?> extractSourceTime,
        CancellationToken stop = default)
    {
        if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(provider) ||
            endpoint is null || !endpoint.IsAbsoluteUri ||
            endpoint.Scheme != Uri.UriSchemeHttps ||
            !string.IsNullOrWhiteSpace(endpoint.UserInfo))
            throw new ArgumentException("Provider must use an authenticated, approved HTTPS endpoint.");
        // STOP and source provenance rules also apply when a TTL cache entry exists.
        stop.ThrowIfCancellationRequested();
        ArgumentNullException.ThrowIfNull(extractSourceTime);
        var key = new CacheIdentity(id, provider, endpoint.AbsoluteUri);
        var now = DateTimeOffset.UtcNow;
        // Never reuse an earlier provider's bytes, even during its TTL or
        // during an offline fallback from a different approved endpoint.
        if (_cache.TryGetValue(key, out var old) &&
            now >= old.FetchedAt && now - old.FetchedAt < _ttl)
            return old with { Status = "CACHE" };
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stop);
        timeout.CancelAfter(_timeout);
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, endpoint);
            using var response = await _http.SendAsync(request,
                HttpCompletionOption.ResponseHeadersRead, timeout.Token).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            // Content-Length is only an early rejection: chunked streams may omit
            // it, and an untrusted server may understate it. Always count bytes.
            if (response.Content.Headers.ContentLength is long announced &&
                announced > MaximumFeedResponseBytes)
                throw new FeedResponseTooLargeException();
            await using var stream = await response.Content.ReadAsStreamAsync(timeout.Token).ConfigureAwait(false);
            using var bounded = new MemoryStream();
            var chunk = new byte[16 * 1024];
            int bytesRead;
            while ((bytesRead = await stream.ReadAsync(chunk.AsMemory(), timeout.Token)
                .ConfigureAwait(false)) != 0)
            {
                // Check BEFORE allocation/copy, even for a missing or forged length.
                if (bytesRead > MaximumFeedResponseBytes - bounded.Length)
                    throw new FeedResponseTooLargeException();
                await bounded.WriteAsync(chunk.AsMemory(0, bytesRead), timeout.Token)
                    .ConfigureAwait(false);
            }
            bounded.Position = 0;
            using var json = await JsonDocument.ParseAsync(bounded,
                cancellationToken: timeout.Token).ConfigureAwait(false);
            var cloned = json.RootElement.Clone();
            var observed = extractSourceTime(cloned);
            var snapshot = new FeedSnapshot(id, provider, observed,
                DateTimeOffset.UtcNow, cloned, observed is null ? "UNVERIFIED_TIMESTAMP" : "LIVE",
                observed is null ? "SOURCE_TIME_MISSING" : null, false);
            _cache[key] = snapshot;
            return snapshot;
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { throw; }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or
            JsonException or FeedResponseTooLargeException)
        {
            string error = ex is FeedResponseTooLargeException ? "RESPONSE_TOO_LARGE" :
                ex is OperationCanceledException ? "TIMEOUT" :
                ex is JsonException ? "INVALID_JSON" : "NETWORK_ERROR";
            if (old is not null)
                return old with { Status = "OFFLINE_CACHE", ErrorCode = error, IsStale = true };
            return new FeedSnapshot(id, provider, null, DateTimeOffset.UtcNow,
                null, "OFFLINE", error, true);
        }
    }
}
