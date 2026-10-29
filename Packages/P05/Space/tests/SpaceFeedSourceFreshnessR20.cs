// NOX V16 P05 R20: local HTTP-handler fixture, no network or GPU.
using System;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.Space.E05;

static void Check(bool ok, string label)
{
    if (!ok) throw new InvalidOperationException("P05_FRESHNESS_FAILED: " + label);
    Console.WriteLine("PASS " + label);
}
static DateTimeOffset? Stamp(JsonElement e) => e.GetProperty("source_time").GetDateTimeOffset();
static SpaceFeedClient Feed(DateTimeOffset timestamp, TimeSpan maxAge) =>
    new(new HttpClient(new FakeHttp(JsonSerializer.SerializeToUtf8Bytes(
        new { source_time = timestamp }))), TimeSpan.FromHours(1),
        TimeSpan.FromSeconds(5), maxAge);
static Task<FeedSnapshot> Read(SpaceFeedClient feed, CancellationToken stop = default) =>
    feed.FetchAsync("weather", new Uri("https://approved.invalid/feed"),
        "APPROVED_LOCAL_TEST", Stamp, stop);

var now = DateTimeOffset.UtcNow;
var fresh = Feed(now.AddMinutes(-10), TimeSpan.FromHours(1));
var freshResult = await Read(fresh);
Check(freshResult.Status == "LIVE" && !freshResult.IsStale, "fresh source allowed");
var cachedResult = await Read(fresh);
Check(cachedResult.Status == "CACHE" && !cachedResult.IsStale, "fresh cache allowed");
var stale = Feed(now.AddDays(-3), TimeSpan.FromHours(1));
var staleResult = await Read(stale);
Check(staleResult.Status == "STALE_SOURCE" && staleResult.IsStale &&
      staleResult.ErrorCode == "SOURCE_STALE", "old timestamp rejected");
var staleCached = await Read(stale);
Check(staleCached.Status == "STALE_SOURCE" && staleCached.IsStale,
      "old timestamp never promoted to CACHE");
var future = Feed(now.AddDays(3), TimeSpan.FromHours(1));
Check((await Read(future)).Status == "INVALID_SOURCE_TIME",
      "future timestamp rejected");
try
{
    Feed(now, TimeSpan.Zero);
    throw new Exception("Invalid freshness policy accepted");
}
catch (ArgumentOutOfRangeException)
{
    Console.WriteLine("PASS zero maximum age rejected");
}
using var cancel = new CancellationTokenSource();
cancel.Cancel();
try
{
    await Read(fresh, cancel.Token);
    throw new Exception("STOP returned cached value");
}
catch (OperationCanceledException)
{
    Console.WriteLine("PASS STOP overrides cache");
}
Console.WriteLine("P05 SOURCE_FRESHNESS 7/7 semantic checks defined (runtime execution required)");

sealed class FakeHttp(byte[] payload) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            RequestMessage = request,
            Content = new ByteArrayContent(payload)
        });
    }
}
