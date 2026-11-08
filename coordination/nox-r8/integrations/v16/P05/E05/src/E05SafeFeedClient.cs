using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Xml;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// All endpoints originate from an independently approved owner configuration.
// No user-provided URLs, no unlicensed sources, no tokens in URLs or logs.
public sealed record ApprovedFeed(string Id, string Provider, Uri Endpoint,
    string AllowedHost, string LicenseReceipt, TimeSpan Ttl,
    TimeSpan Timeout, TimeSpan MaxSourceAge, int MaxBytes = 262144);
public sealed record FeedResult(string Id, string Provider, string? Body,
    DateTimeOffset? SourceTimestamp, DateTimeOffset? FetchedAt,
    string Status, string? ErrorCode, bool Stale);

public sealed class E05SafeFeedClient : IDisposable
{
    private readonly HttpClient client;
    private readonly ConcurrentDictionary<string, FeedResult> cache = new();
    private readonly ConcurrentDictionary<string, SemaphoreSlim> gates = new();

    // Production factory fixes redirect and cookie policies at handler level.
    public static E05SafeFeedClient Production() => new(new HttpClientHandler {
        AllowAutoRedirect = false, UseCookies = false, UseDefaultCredentials = false
    });

    // Handler injection exists solely for deterministic local tests.
    public E05SafeFeedClient(HttpMessageHandler handler)
    {
        client = new HttpClient(handler, disposeHandler: true) {
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    public static bool Valid(ApprovedFeed? source)
    {
        if (source is null || string.IsNullOrWhiteSpace(source.Id) ||
            string.IsNullOrWhiteSpace(source.Provider) ||
            string.IsNullOrWhiteSpace(source.LicenseReceipt) ||
            string.IsNullOrWhiteSpace(source.AllowedHost) ||
            source.Endpoint is null || !source.Endpoint.IsAbsoluteUri ||
            source.Endpoint.Scheme != Uri.UriSchemeHttps ||
            !string.Equals(source.Endpoint.Host, source.AllowedHost, StringComparison.OrdinalIgnoreCase) ||
            source.Endpoint.IsLoopback ||
            source.Endpoint.HostNameType != UriHostNameType.Dns ||
            source.Endpoint.Host.EndsWith(".local", StringComparison.OrdinalIgnoreCase) ||
            !string.IsNullOrEmpty(source.Endpoint.UserInfo) ||
            !string.IsNullOrEmpty(source.Endpoint.Fragment) ||
            source.Ttl <= TimeSpan.Zero || source.Timeout <= TimeSpan.Zero ||
            source.MaxSourceAge <= TimeSpan.Zero ||
            source.MaxBytes < 512 || source.MaxBytes > 1024 * 1024)
            return false;
        return true;
    }

    // Parser must take timestamp from actual provider bytes, never from local clock.
    public async Task<FeedResult> FetchAsync(ApprovedFeed source,
        Func<string, DateTimeOffset?> sourceTime, CancellationToken cancel = default)
    {
        if (!Valid(source))
            return new(source?.Id ?? "UNKNOWN", source?.Provider ?? "UNKNOWN", null,
                null, null, "DISABLED", "SOURCE_NOT_APPROVED", true);
        if (sourceTime is null) throw new ArgumentNullException(nameof(sourceTime));
        // Cache identity also binds the approved license and the complete freshness policy.
        // A changed authorization may never inherit another provider's prior response.
        var key = string.Join("\u001f", source.Id, source.Provider,
            source.Endpoint.AbsoluteUri, source.AllowedHost, source.LicenseReceipt,
            source.Ttl.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture),
            source.MaxSourceAge.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture),
            source.Timeout.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture),
            source.MaxBytes.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var gate = gates.GetOrAdd(key, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(cancel).ConfigureAwait(false);
        try
        {
            var now = DateTimeOffset.UtcNow;
            if (cache.TryGetValue(key, out var old) && old.FetchedAt is { } at &&
                now - at >= TimeSpan.Zero && now - at < source.Ttl)
            {
                // TTL is only a transport cache limit; source freshness must be re-evaluated.
                bool sourceOld = old.SourceTimestamp is null ||
                    now - old.SourceTimestamp.Value > source.MaxSourceAge ||
                    old.SourceTimestamp.Value > now.AddMinutes(5);
                return old with {
                    Status = sourceOld ? "STALE_CACHE" :
                        old.Status == "LIVE" ? "CACHE" : old.Status,
                    Stale = sourceOld || old.Stale,
                    ErrorCode = sourceOld ? "SOURCE_STALE" : old.ErrorCode
                };
            }
            using var timed = CancellationTokenSource.CreateLinkedTokenSource(cancel);
            timed.CancelAfter(source.Timeout);  // Covers headers AND body with ResponseHeadersRead.
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, source.Endpoint);
                request.Headers.TryAddWithoutValidation("Accept", "application/json, application/rss+xml, text/xml");
                using var response = await client.SendAsync(request,
                    HttpCompletionOption.ResponseHeadersRead, timed.Token).ConfigureAwait(false);
                if ((int)response.StatusCode is >= 300 and < 400)
                    throw new HttpRequestException("REDIRECT_DENIED");
                response.EnsureSuccessStatusCode();
                if (response.Content.Headers.ContentLength > source.MaxBytes)
                    throw new InvalidDataException("RESPONSE_TOO_LARGE");
                await using var stream = await response.Content.ReadAsStreamAsync(timed.Token)
                    .ConfigureAwait(false);
                using var ms = new MemoryStream();
                var buffer = new byte[8192];
                while (true)
                {
                    int n = await stream.ReadAsync(buffer.AsMemory(), timed.Token).ConfigureAwait(false);
                    if (n == 0) break;
                    if (ms.Length + n > source.MaxBytes)
                        throw new InvalidDataException("RESPONSE_TOO_LARGE");
                    ms.Write(buffer, 0, n);
                }
                string body = new UTF8Encoding(false, true).GetString(ms.ToArray());
                DateTimeOffset? stamp = sourceTime(body);
                now = DateTimeOffset.UtcNow;
                var status = stamp is null ? "TIME_UNVERIFIED" :
                    stamp.Value > now.AddMinutes(5) ? "INVALID_SOURCE_TIME" :
                    now - stamp.Value > source.MaxSourceAge ? "STALE_SOURCE" : "LIVE";
                var result = new FeedResult(source.Id, source.Provider, body,
                    stamp, now, status, status == "LIVE" ? null : status, status != "LIVE");
                cache[key] = result;
                return result;
            }
            catch (OperationCanceledException) when (cancel.IsCancellationRequested) { throw; }
            catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException
                or InvalidDataException or DecoderFallbackException or FormatException
                or JsonException or XmlException)
            {
                var reason = ex is OperationCanceledException ? "TIMEOUT" :
                    ex is InvalidDataException ? "SIZE_LIMIT" :
                    ex is DecoderFallbackException ? "INVALID_ENCODING" :
                    ex is JsonException or XmlException ? "INVALID_SOURCE" :
                    ex.Message == "REDIRECT_DENIED" ? "REDIRECT_DENIED" : "FETCH_ERROR";
                if (old is not null)
                    return old with { Status = "OFFLINE_CACHE", ErrorCode = reason, Stale = true };
                return new(source.Id, source.Provider, null, null, null,
                    "OFFLINE", reason, true);
            }
        }
        finally { gate.Release(); }
    }
    public void Dispose()
    {
        client.Dispose();
        // Intended lifecycle: singleton host service, disposed only on host shutdown.
        foreach (var item in gates.Values) item.Dispose();
    }
}
