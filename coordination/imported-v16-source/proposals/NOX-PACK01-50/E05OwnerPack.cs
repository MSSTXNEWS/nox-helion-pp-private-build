// NOX PACK01: real E05 owner-API adapter; one existing safe feed client and sensors.
// Endpoints, approved licensing receipts and quote JSON paths originate from trusted
// E06 host configuration, NEVER from a web page or unverified default.
using NoxHelion.E05;

namespace Nox.Pack01;

public sealed record NativeFeedBinding(ApprovedFeed Source, string? DataPath = null,
    string? SourceTimePath = null, string? Unit = null);

public sealed record OwnerFeedResponse(FeedResult Transport, object? Data);

public sealed class E05OwnerPack
{
    private readonly E05SafeFeedClient _client;
    private readonly IReadOnlyDictionary<string, NativeFeedBinding> _sources;
    private readonly IReadOnlyList<ISensorProvider> _sensors;

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(StringComparer.Ordinal)
    {
        "space.news", "space.weather", "space.fx", "space.bitcoin",
        "space.brent", "system.telemetry"
    };

    public E05OwnerPack(E05SafeFeedClient client,
        IReadOnlyDictionary<string,NativeFeedBinding> nativeApprovedSources,
        IReadOnlyList<ISensorProvider> existingSensors)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _sources = nativeApprovedSources ?? throw new ArgumentNullException(nameof(nativeApprovedSources));
        _sensors = existingSensors ?? throw new ArgumentNullException(nameof(existingSensors));
    }

    public async Task<object> ExecuteAsync(string routeId, CancellationToken ct = default)
    {
        if (!Supported.Contains(routeId))throw new NotSupportedException("E05 owner route HOLD");
        if (routeId == "system.telemetry")
        {
            var points = new List<SensorPoint>();
            foreach (var sensor in _sensors)
                points.AddRange(sensor.Read(ct)); // Real OS sensors; null/N/D if unavailable.
            return points;
        }
        if (!_sources.TryGetValue(routeId, out var bound) ||
            !E05SafeFeedClient.Valid(bound.Source) ||
            !string.Equals(bound.Source.Id, routeId, StringComparison.Ordinal))
            throw new InvalidOperationException("Unapproved or missing source/license/freshness receipt");

        var result = await _client.FetchAsync(bound.Source, body => ReadObservedAt(routeId, body, bound), ct)
            .ConfigureAwait(false);
        if (result.Body is null || result.Stale)
            return new OwnerFeedResponse(result, null); // No artificial live value.

        object parsed = routeId switch
        {
            "space.news" => SpaceParsers.ParseRss(result.Body,bound.Source.Provider),
            "space.weather" => SpaceParsers.ParseWeather(result.Body),
            "space.fx" => E05EcbCsv.ParseEurUsd(result.Body),
            "space.bitcoin" or "space.brent" => ParseConfiguredQuote(routeId,result.Body,bound),
            _ => throw new NotSupportedException("Unknown E05 owner parser")
        };
        return new OwnerFeedResponse(result,parsed);
    }

    private static QuoteData ParseConfiguredQuote(string routeId,string body,NativeFeedBinding bound)
    {
        if (string.IsNullOrWhiteSpace(bound.DataPath) ||
            string.IsNullOrWhiteSpace(bound.SourceTimePath) ||
            string.IsNullOrWhiteSpace(bound.Unit))
            throw new InvalidOperationException("Trusted quote parsing fields required");
        return SpaceParsers.ParseQuote(body,routeId,bound.DataPath,
            bound.SourceTimePath,bound.Unit,bound.Source.Provider);
    }

    private static DateTimeOffset? ReadObservedAt(string routeId,string body,NativeFeedBinding bound)
    {
        try
        {
            return routeId switch
            {
                "space.weather" => SpaceParsers.ParseWeather(body).SourceTime,
                "space.fx" => E05EcbCsv.ParseEurUsd(body).SourceTime,
                "space.news" => SpaceParsers.ParseRss(body,bound.Source.Provider)
                    .Select(x=>x.PublishedAt).Where(x=>x.HasValue)
                    .OrderByDescending(x=>x.Value).FirstOrDefault(),
                "space.bitcoin" or "space.brent" =>
                    ParseConfiguredQuote(routeId,body,bound).SourceTime,
                _ => null
            };
        }
        catch (Exception) { return null; } // Invalid provider bytes fail freshness, not invented timestamp.
    }
}
