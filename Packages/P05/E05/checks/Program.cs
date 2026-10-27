using NoxHelion.E05;
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Text;
using System.Linq;
using System.Xml;

static void Check(bool ok, string test)
{
    if (!ok) throw new Exception("E05 regression failure: " + test);
    Console.WriteLine("PASS " + test);
}

var fifty = new LaneProof(1, "fixed-manifest-sha", new[] {
    new TaskCriterion("T1", 1, "ACCEPTED", "receipt-1"),
    new TaskCriterion("T2", 1, "OPEN", null)
});
Check(ProgressMath.LanePercent(fifty) == 50m, "weighted criterion 50%");
Check(ProgressMath.LanePercent(new LaneProof(1, "fixed", new[] {
    new TaskCriterion("T1", 1, "ACCEPTED", null) })) is null,
    "missing receipt cannot count accepted task");
var lanes = new List<LaneProof>();
for (int i = 1; i <= 5; i++)
    lanes.Add(new LaneProof(i, "source-lock", new[] {
        new TaskCriterion("done" + i, 1, "ACCEPTED", "proof-" + i) }));
Check(ProgressMath.Overall(lanes) == 100m, "all verified criteria 100%");
lanes[0] = fifty;
Check(ProgressMath.Overall(lanes) == 90m, "20/25/20/25/10 weighted overall 90%");
var cores = new List<CoreProof>();
for (int i = 0; i < 8; i++)
    cores.Add(new CoreProof("core-" + i, i * 10, "VERIFIED", "receipt-" + i, DateTimeOffset.UtcNow));
Check(ProgressMath.CoreAverage(cores) == 35, "8 verified cores equal average");
cores[7] = cores[0];
Check(ProgressMath.CoreAverage(cores) is null, "duplicate CoreID rejected");
Check(SpaceParsers.ParseQuote("{\"rate\":1.08,\"observed\":\"2026-10-27T12:00:00Z\"}",
    "eur-usd", "rate", "observed", "USD", "fixture").Status == "SOURCE_DATED",
    "timestamped quote accepted as source-dated");
Check(SpaceParsers.ParseQuote("{\"rate\":1.08}", "eur-usd", "rate", "observed",
    "USD", "fixture").Status == "UNVERIFIED", "quote without source timestamp unverified");
try
{
    SpaceParsers.ParseRss("<!DOCTYPE rss [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><rss><channel/></rss>",
        "untrusted");
    throw new Exception("DTD incorrectly accepted");
}
catch (XmlException) { Console.WriteLine("PASS RSS DTD blocked"); }

var id = "NOX-E05-CONTRACT-TEST";
var entry = id + " verified local fixture\n";
var handler = new DocsFixtureHandler(entry);
using var http = new HttpClient(handler);
var docs = new GoogleDocsAppendReadback(http, _ => Task.FromResult("test-fixture-token"));
var receipt = await docs.AppendAsync("1FixtureDocumentId", id, entry, CancellationToken.None);
Check(receipt.Status == "READBACK_PASS" && handler.PostCount == 1,
    "mock app-side append/readback exact RunID");
var second = await docs.AppendAsync("1FixtureDocumentId", id, entry, CancellationToken.None);
Check(second.Status == "ALREADY_PRESENT" && handler.PostCount == 1,
    "idempotent repeated RunID appends once");
var collisionHandler = new DocsFixtureHandler(entry) { InitialText = id + " different payload" };
using var otherHttp = new HttpClient(collisionHandler);
var otherDocs = new GoogleDocsAppendReadback(otherHttp, _ => Task.FromResult("fixture-token"));
var collision = await otherDocs.AppendAsync("1FixtureDocumentId", id, entry, CancellationToken.None);
Check(collision.Status == "RUNID_COLLISION" && collisionHandler.PostCount == 0,
    "RunID collision does not overwrite/duplicate existing data");

var def = new ApprovedFeed("weather", "fixture", new Uri("https://example.org/forecast"),
    "example.org", "APPROVED-LIC-001", TimeSpan.FromSeconds(20),
    TimeSpan.FromSeconds(2), TimeSpan.FromHours(2), 1024);
Check(E05SafeFeedClient.Valid(def), "licensed HTTPS host configuration valid");
Check(!E05SafeFeedClient.Valid(def with { Endpoint = new Uri("https://127.0.0.1/private"),
    AllowedHost = "127.0.0.1" }), "local IP endpoints rejected");
Check(!E05SafeFeedClient.Valid(def with { LicenseReceipt = "" }), "unlicensed feeds blocked");
Check(!E05SafeFeedClient.Valid(def with { Endpoint = new Uri("https://example.local/internal"),
    AllowedHost = "example.local" }), "local DNS name denied");
using (var feed = new E05SafeFeedClient(new FeedFixtureHandler()))
{
    var measured = await feed.FetchAsync(def, _ => DateTimeOffset.UtcNow.AddMinutes(-2));
    Check(measured.Status == "LIVE" && measured.Body is not null,
        "bounded fixture feed has a source timestamp");
    var cached = await feed.FetchAsync(def, _ => null);
    Check(cached.Status == "CACHE", "repeat fetch returns cached provider response");
}
using (var feed = new E05SafeFeedClient(new FeedFixtureHandler()))
{
    var future = await feed.FetchAsync(def, _ => DateTimeOffset.UtcNow.AddHours(2));
    Check(future.Status == "INVALID_SOURCE_TIME", "future provider timestamp rejected");
}
using (var feed = new E05SafeFeedClient(new FeedFixtureHandler()))
{
    var undated = await feed.FetchAsync(def, _ => null);
    Check(undated.Status == "TIME_UNVERIFIED", "missing provider timestamp stays unverified");
}
using (var feed = new E05SafeFeedClient(new FeedFixtureHandler(System.Net.HttpStatusCode.Redirect)))
{
    var failure = await feed.FetchAsync(def, _ => null);
    Check(failure.Status == "OFFLINE" && failure.ErrorCode == "REDIRECT_DENIED",
        "provider redirect is denied");
}
using (var feed = new E05SafeFeedClient(new FeedFixtureHandler(payloadSize: 2048)))
{
    var failure = await feed.FetchAsync(def, _ => null);
    Check(failure.ErrorCode == "SIZE_LIMIT", "response byte budget enforced");
}
var ecb = E05EcbCsv.ParseEurUsd("TIME_PERIOD,OBS_VALUE,COMMENT\n2026-10-26,1.07,old\n2026-10-27,1.09,latest\n");
Check(ecb.Status == "SOURCE_DATED" && ecb.Value == 1.09m &&
    ecb.SourceTime?.UtcDateTime.Date == new DateTime(2026, 10, 27),
    "ECB CSV chooses latest valid dated EUR/USD observation");
Check(E05EcbCsv.ParseEurUsd("not,ecb\n1,2").Value is null,
    "invalid ECB CSV never invents price");
var weatherOffset = SpaceParsers.ParseWeather("{\"current\":{\"time\":\"2026-10-27T12:00\",\"temperature_2m\":18},\"utc_offset_seconds\":3600}");
Check(weatherOffset.Status == "SOURCE_DATED" && weatherOffset.SourceTime?.Hour == 11,
    "weather converts provider timezone offset to UTC");
var weatherNoOffset = SpaceParsers.ParseWeather("{\"current\":{\"time\":\"2026-10-27T12:00\",\"temperature_2m\":18}}");
Check(weatherNoOffset.Status == "UNVERIFIED",
    "weather without timezone stays unverified");
var licenseFixture = new FeedFixtureHandler();
using (var transport = new E05SafeFeedClient(licenseFixture))
{
    await transport.FetchAsync(def, _ => DateTimeOffset.UtcNow.AddMinutes(-1));
    await transport.FetchAsync(def with { LicenseReceipt = "APPROVED-LIC-NEW" },
        _ => DateTimeOffset.UtcNow.AddMinutes(-1));
    Check(licenseFixture.SendCount == 2,
        "provider license change invalidates cached source identity");
}
var projected = ReadinessProjection.Evaluate("run-verified-fixture",
    new LaneProof?[] {null, null, null, null, null}, "HOLD", "HOLD", DateTimeOffset.UtcNow);
Check(projected.Bars.Count == 7 && projected.Overall is null &&
    projected.Bars.All(x => x.Percent is null), "seven undefined bars are never fabricated");
Console.WriteLine("ALL E05 mocked/offline checks passed (no real hardware/network)");

sealed class DocsFixtureHandler : HttpMessageHandler
{
    private readonly string entry;
    public int PostCount { get; private set; }
    public string? InitialText { get; set; }
    public DocsFixtureHandler(string entry) { this.entry = entry; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        string json;
        if (request.Method == HttpMethod.Post)
        {
            PostCount++;
            json = "{}";
        }
        else
            json = System.Text.Json.JsonSerializer.Serialize(new {
                revisionId = PostCount > 0 ? "rev2" : "rev1", body = new { content = new object[] {
                    new { paragraph = new { elements = new object[] {
                        new { textRun = new { content = InitialText ?? (PostCount > 0 ? entry : "") } }
                    } } }
                } }
            });
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
            Content = new StringContent(json)
        });
    }
}

sealed class FeedFixtureHandler : HttpMessageHandler
{
    private readonly HttpStatusCode status;
    private readonly int payloadSize;
    public FeedFixtureHandler(HttpStatusCode status = HttpStatusCode.OK, int payloadSize = 12)
    { this.status = status; this.payloadSize = payloadSize; }
    public int SendCount { get; private set; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        SendCount++;
        return Task.FromResult(new HttpResponseMessage(status) {
            Content = new StringContent(new string('x', payloadSize))
        });
    }
}
