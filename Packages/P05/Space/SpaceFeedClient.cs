// NOX V16 / E05 candidate: isolated contract, NOT wired into MainWindow or host.
// BCL-only. Providers/endpoints are injected by host after license/security review.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
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
    private readonly HttpClient _http;
    private readonly ConcurrentDictionary<string, FeedSnapshot> _cache = new();
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
            endpoint is null || endpoint.Scheme != Uri.UriSchemeHttps ||
            !string.IsNullOrWhiteSpace(endpoint.UserInfo))
            throw new ArgumentException("Provider must use an authenticated, approved HTTPS endpoint.");
        var now = DateTimeOffset.UtcNow;
        if (_cache.TryGetValue(id, out var old) && now - old.FetchedAt < _ttl)
            return old with { Status = "CACHE" };
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stop);
        timeout.CancelAfter(_timeout);
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, endpoint);
            using var response = await _http.SendAsync(request,
                HttpCompletionOption.ResponseHeadersRead, timeout.Token).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            await using var stream = await response.Content.ReadAsStreamAsync(timeout.Token).ConfigureAwait(false);
            using var json = await JsonDocument.ParseAsync(stream,
                cancellationToken: timeout.Token).ConfigureAwait(false);
            var cloned = json.RootElement.Clone();
            var observed = extractSourceTime(cloned);
            var snapshot = new FeedSnapshot(id, provider, observed,
                DateTimeOffset.UtcNow, cloned, observed is null ? "UNVERIFIED_TIMESTAMP" : "LIVE",
                observed is null ? "SOURCE_TIME_MISSING" : null, false);
            _cache[id] = snapshot;
            return snapshot;
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { throw; }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            string error = ex is OperationCanceledException ? "TIMEOUT" :
                ex is JsonException ? "INVALID_JSON" : "NETWORK_ERROR";
            if (old is not null)
                return old with { Status = "OFFLINE_CACHE", ErrorCode = error, IsStale = true };
            return new FeedSnapshot(id, provider, null, DateTimeOffset.UtcNow,
                null, "OFFLINE", error, true);
        }
    }
}
