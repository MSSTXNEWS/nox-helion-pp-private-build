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
// TURBO10: canonical events.v3 is enforced without a second event writer.
var nowV3 = DateTimeOffset.UtcNow;
var liveGpu = new SensorPoint("gpu.percent", 52.65, "%", "NVIDIA.NVML", nowV3, "LIVE");
var evt = E05CanonicalEventFactory.GpuUtilization("RUN-E05-TEST", liveGpu, nowV3);
Check(evt is not null && evt.EventType == "gpu.sample" && evt.Numerator == 5265 &&
    evt.Denominator == 10000 && !evt.EvidenceVerified &&
    E05CanonicalEventFactory.IsCanonical(evt), "T10-01: legacy events.v3 GPU payload only");
Check(E05CanonicalEventFactory.GpuUtilization("RUN-E05-TEST", liveGpu with {
    ObservedAtUtc = nowV3.AddMinutes(-2) }, nowV3) is null,
    "T10-01: old telemetry never emitted");
Check(!E05CanonicalEventFactory.IsCanonical(evt! with { EventType = "telemetry.snapshot" }),
    "T10-01: unsupported event type blocked");
Check(!E05CanonicalEventFactory.IsCanonical(evt! with { Message = null! }),
    "T10-01: null event message fails closed");
Check(!E05CanonicalEventFactory.IsCanonical(evt! with { Message = "unsafe\nlog" }),
    "T10-01: multiline event message fails closed");
var hw = E05HardwareEvidence.Snapshot("RUN-E05-TEST", new ISensorProvider[] {
    new FakeSensorProvider(liveGpu, new SensorPoint("gpu.vram.used_bytes", 20,
        "bytes", "NVML", nowV3, "LIVE"), new SensorPoint("gpu.vram.total_bytes", 10,
        "bytes", "NVML", nowV3, "LIVE")) }, nowV3, CancellationToken.None);
Check(hw.Sensors.Count == 5 && hw.Sensors.Single(x => x.Key == "gpu.vram.used_bytes").Value is null,
    "T10-02: inconsistent VRAM quarantined without fake values");
var approvedCores = Enumerable.Range(0, 8).Select(i => "ORIGINAL-" + i).ToArray();
var approvedPersonas = Enumerable.Range(0, 5).Select(i => "PERSONA-" + i).ToArray();
var cproof = approvedCores.Select((name, i) => new CoreProof(name, i * 10,
    "VERIFIED", "receipt-" + i, nowV3)).ToArray();
var pproof = approvedPersonas.Select(name => new PersonaProof(name, "AVAILABLE", nowV3)).ToArray();
var orb = E05CorePersonaProjection.Project(approvedCores, approvedPersonas,
    cproof, pproof, nowV3);
Check(orb.CenterPercent == 35 && orb.Status == "VERIFIED", "T10-03: 8 core and 5 persona proofs");
Check(E05CorePersonaProjection.Project(approvedCores, approvedPersonas,
    cproof, pproof, nowV3.AddHours(1)).CenterPercent is null,
    "T10-03: stale core ring becomes N/D");
var manifest = new string('a', 64);
var sealedLane = new E05SealedLane(1, manifest,
    new[] { new E05SealedCriterion("P01-T1", 1, "ACCEPTED", "receipt", new string('b', 64)) });
Check(E05SealedProgress.Evaluate(sealedLane, null) is null,
    "T10-04: no verifier means no readiness percentage");
Check(E05SealedProgress.Evaluate(sealedLane, new FakeReceiptVerifier()) == 100m,
    "T10-04: owner-bound acceptance evidence can produce measured percentage");
Check(E05SealedProgress.Evaluate(sealedLane with { ManifestSha256 = "not-sha" },
    new FakeReceiptVerifier()) is null, "T10-04: invalid manifest rejected");
Check(E05SealedProgress.Evaluate(sealedLane with { Criteria = null! },
    new FakeReceiptVerifier()) is null, "T10-04: null criterion manifest is N/D");
Check(E05SealedProgress.Evaluate(sealedLane with {
    Criteria = new E05SealedCriterion[] { null! } },
    new FakeReceiptVerifier()) is null, "T10-04: corrupted criterion row is N/D");
var activity = new E05ActivityTimeline("RUN-E05-TEST");
Check(activity.Accept(evt!, nowV3) && activity.Read(nowV3).Count == 1,
    "T10-05: actual live event enters timeline");
Check(!activity.Accept(evt!, nowV3), "T10-05: event ID deduplicated");
Check(activity.Read(nowV3.AddMinutes(4))[0].State == "OFFLINE",
    "T10-05: stream activity expiry is explicit");
var targets = new [] { new E05DriveTarget("report", "1FixtureDocumentId"),
    new E05DriveTarget("lessons", "1AnotherFixtureId"),
    new E05DriveTarget("master", "1ThirdFixtureId") };
using var docsGateHttp = new HttpClient(new DocsFixtureHandler("RUN-E05-TEST fixture"));
var docsGateWriter = new GoogleDocsAppendReadback(docsGateHttp,
    _ => Task.FromResult("fixture-token"));
var docsGate = await E05DriveRunGate.AppendRunAsync(docsGateWriter,
    "RUN-E05-TEST", "RUN-E05-TEST fixture", targets, false, CancellationToken.None);
Check(docsGate.State == "HOLD_MASTER_INTEGRITY" && docsGate.Receipts.Count == 2,
    "T10-06: unverified historical master prevents app-side journal write");
var malformedGate = await E05DriveRunGate.AppendRunAsync(docsGateWriter,
    "RUN-E05-TEST", "RUN-E05-TEST fixture", null!, false, CancellationToken.None);
Check(malformedGate.State == "HOLD_CONTRACT", "T10-06: null target list fails closed");
var cfg = def with { Id = "bitcoin" };
var known = E05FeedTrust.Classify(new FeedResult("bitcoin", "fixture", "{}",
    nowV3.AddHours(-1), nowV3, "LIVE", null, false), cfg, nowV3);
Check(known.Status == "SOURCE_DATED" && E05FeedTrust.SupportedIds.Count == 8,
    "T10-07: source-backed market feed, 8 known categories");
Check(E05FeedTrust.Classify(new FeedResult("bitcoin", "fixture", "{}",
    nowV3.AddHours(-4), nowV3, "LIVE", null, true), cfg, nowV3).Status == "STALE",
    "T10-07: stale price cannot look live");
var wow = E05WowCompatibility.Resolve(new[] { "live-aura", "stream-pulse" },
    false, false, false);
Check(wow.Count == 7 && wow.All(x => !x.Enabled),
    "T10-08: no verified event bridge means no decorative fake pulse");
Check(E05WowCompatibility.Resolve(new[] { "live-aura" }, true, true, false)
    .All(x => !x.Enabled), "T10-08: ECO disables optional visual motion");
var feedSnapshot = new FeedResult("weather", "fixture", "{}", nowV3,
    nowV3, "LIVE", null, false);
var mobile = E05SpaceReadOnlyProjection.Build("RUN-E05-TEST", nowV3,
    new [] { feedSnapshot }, hw, null);
Check(mobile.Access == "READ_ONLY" && mobile.Tiles.Count == 1 &&
    mobile.ProductProgress is null && mobile.Tiles[0].Preview is null,
    "T10-09: mobile/SPACE read-only, no invented progress");
try { await new E05SensorPublisher(Array.Empty<ISensorProvider>(),
    new FakeLegacyTransport()).PollOnceAsync("RUN-E05-TEST", CancellationToken.None);
    throw new Exception("T10-01 invalid bridge was allowed"); }
catch (NotSupportedException) { Console.WriteLine("PASS T10-10: old noncanonical telemetry publisher fails closed"); }

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

sealed class FakeSensorProvider : ISensorProvider
{
    private readonly SensorPoint[] sensors;
    public string Name => "TEST";
    public FakeSensorProvider(params SensorPoint[] sensors) { this.sensors = sensors; }
    public IReadOnlyList<SensorPoint> Read(CancellationToken cancel) => sensors;
}
sealed class FakeReceiptVerifier : IE05ReceiptVerifier
{
    public bool IsFrozenManifest(string sha, int id) => id == 1 && sha == new string('a', 64);
    public bool IsVerified(string task, string receipt, string sha) =>
        task == "P01-T1" && receipt == "receipt" && sha == new string('b', 64);
}
sealed class FakeLegacyTransport : IEventV3Transport
{
    public ValueTask SendAsync(TelemetryEventV3 m, CancellationToken stop) => ValueTask.CompletedTask;
}
