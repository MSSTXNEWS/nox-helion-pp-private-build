// NOX V16 §46 independent P05 cache-identity negative integration regression.
// Compiles the unchanged original Packages/P05/Space/SpaceFeedClient.cs.
// dotnet run --project qa/source_ready/P05CacheIdentityR02/P05CacheIdentityR02.csproj
// It must be RED on an id-only cache: a different provider/URL MUST refetch.
using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.Space.E05;

static void Require(bool condition, string message)
{
    if (!condition) throw new Exception("P05_CACHE_PROVENANCE_RED: " + message);
}

static DateTimeOffset? SourceTime(JsonElement json) =>
    DateTimeOffset.Parse(json.GetProperty("observed").GetString()!);

var handler = new RecordingHttp();
using var http = new HttpClient(handler);
var client = new SpaceFeedClient(http, TimeSpan.FromMinutes(30),
    TimeSpan.FromSeconds(10));
var urlA = new Uri("https://example.org/owner-A/weather");
var urlB = new Uri("https://example.org/owner-B/weather");

// Positive control: same exact source may reuse the same valid cache entry.
var first = await client.FetchAsync("weather", urlA, "ProviderA", SourceTime);
var same = await client.FetchAsync("weather", urlA, "ProviderA", SourceTime);
Require(first.Source == "ProviderA", "First authoritative response must be A.");
Require(same.Status == "CACHE", "Same approved source should be cached.");
Require(handler.Calls == 1, "Positive same-source cache should avoid a new fetch.");

// Negative: reuse of A under the SAME ID but DIFFERENT provider/URL is forbidden.
// Current owner source returns ProviderA/Status=CACHE here; expected RED until fixed.
var changed = await client.FetchAsync("weather", urlB, "ProviderB", SourceTime);
Require(handler.Calls == 2, "Changing source endpoint/provider must fetch B.");
Require(changed.Source == "ProviderB", "B request must never carry A provenance.");
Require(changed.Status != "CACHE", "A's cached value must not be labeled B's LIVE source.");
Require(changed.Data?.GetProperty("provider").GetString() == "ProviderB",
    "B request must contain B's payload rather than A's cached bytes.");
Console.WriteLine("P05_SOURCE_CACHE_IDENTITY_PASS, 2 HTTP owner requests");

sealed class RecordingHttp : HttpMessageHandler
{
    public int Calls { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken token)
    {
        Calls++;
        var isB = request.RequestUri!.AbsolutePath.Contains("owner-B", StringComparison.Ordinal);
        var label = isB ? "ProviderB" : "ProviderA";
        var json = "{\"observed\":\"2026-10-28T15:00:00Z\",\"provider\":\"" +
            label + "\"}";
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        });
    }
}
