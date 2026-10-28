// NOX P05 source-only NET8 regression harness; no network, Windows EXE or duplicate bus.
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.Space.E05;

static class Program
{
    sealed class FixtureHandler : HttpMessageHandler
    {
        internal readonly List<string> Requested = new();
        internal readonly HashSet<string> Failed = new(StringComparer.Ordinal);
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            string endpoint = request.RequestUri!.AbsoluteUri;
            Requested.Add(endpoint);
            if (Failed.Contains(endpoint))
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
            string payload = JsonSerializer.Serialize(new {
                source = endpoint, observed = DateTimeOffset.UtcNow.ToString("O")
            });
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            });
        }
    }

    static DateTimeOffset? SourceClock(JsonElement element)
        => element.TryGetProperty("observed", out var timestamp)
            && DateTimeOffset.TryParse(timestamp.GetString(), out var value)
            ? value : null;

    static void Require(bool condition, string code)
    {
        if (!condition) throw new InvalidOperationException("P05_CACHE_SCOPE_" + code);
    }

    static async Task Main()
    {
        var handler = new FixtureHandler();
        using var http = new HttpClient(handler);
        var client = new SpaceFeedClient(http, TimeSpan.FromMinutes(10), TimeSpan.FromSeconds(5));
        var sourceA = new Uri("https://a.example.test/weather");
        var sourceB = new Uri("https://b.example.test/weather");
        var sourceB2 = new Uri("https://b.example.test/weather/other");
        var unavailable = new Uri("https://c.example.test/temporarily-offline");

        // 1. Same source can reuse its own snapshot.
        var a = await client.FetchAsync("weather", sourceA, "PROVIDER_A", SourceClock);
        var cachedA = await client.FetchAsync("weather", sourceA, "PROVIDER_A", SourceClock);
        Require(a.Status == "LIVE" && cachedA.Status == "CACHE"
            && cachedA.Source == "PROVIDER_A" && handler.Requested.Count == 1,
            "SAME_PROVENANCE_CACHE");
        Console.WriteLine("PASS same-source cached");

        // 2. Same FeedId but different provider MUST NOT inherit A.
        var b = await client.FetchAsync("weather", sourceB, "PROVIDER_B", SourceClock);
        Require(b.Status == "LIVE" && b.Source == "PROVIDER_B"
            && b.Data!.Value.GetProperty("source").GetString() == sourceB.AbsoluteUri
            && handler.Requested.Count == 2,
            "PROVIDER_SEPARATION");
        Console.WriteLine("PASS provider separation");

        // 3. Same FeedId+provider but changed endpoint MUST NOT inherit old bytes.
        var b2 = await client.FetchAsync("weather", sourceB2, "PROVIDER_B", SourceClock);
        Require(b2.Status == "LIVE" && b2.Data!.Value.GetProperty("source").GetString() == sourceB2.AbsoluteUri
            && handler.Requested.Count == 3, "ENDPOINT_SEPARATION");
        Console.WriteLine("PASS endpoint separation");

        // 4. New provider offline: never fall back to cached A/B data.
        handler.Failed.Add(unavailable.AbsoluteUri);
        var offline = await client.FetchAsync("weather", unavailable, "PROVIDER_C", SourceClock);
        Require(offline.Status == "OFFLINE" && offline.Source == "PROVIDER_C"
            && offline.Data is null && offline.IsStale
            && handler.Requested.Count == 4, "NO_CROSS_PROVIDER_OFFLINE_FALLBACK");
        Console.WriteLine("PASS offline no provenance mix");

        // 5. Previously fetched B source remains cached under its own identity.
        var cachedB = await client.FetchAsync("weather", sourceB, "PROVIDER_B", SourceClock);
        Require(cachedB.Status == "CACHE" && cachedB.Source == "PROVIDER_B"
            && handler.Requested.Count == 4, "CACHE_PERSISTENCE");
        Console.WriteLine("PASS per-source persistence");

        // 6. Relative URI should fail with ArgumentException; no unhandled Uri access.
        try {
            await client.FetchAsync("weather", new Uri("/relative", UriKind.Relative),
                "PROVIDER_A", SourceClock);
            throw new InvalidOperationException("P05_CACHE_SCOPE_RELATIVE_URI_ACCEPTED");
        }
        catch (ArgumentException) {
            Require(handler.Requested.Count == 4, "RELATIVE_URI_DID_NETWORK");
        }
        Console.WriteLine("PASS relative endpoint rejected");
        Console.WriteLine("P05_SPACE_CACHE_SCOPE_6_OF_6_PASS_SOURCE_ONLY");
    }
}
