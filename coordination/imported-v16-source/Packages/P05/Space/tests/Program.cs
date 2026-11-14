// E05 R16: local-only, deterministic .NET 8 smoke tests; ZERO real network calls.
// Run: dotnet run --project Packages/P05/Space/tests/SpaceFeedClientR16Smoke.csproj
using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.Space.E05;

const int Cap = 8 * 1024 * 1024;
// Keep the offline LIVE fixture fresh across execution dates.
var Json = JsonSerializer.Serialize(new { source_time = DateTimeOffset.UtcNow.AddMinutes(-10) });
static DateTimeOffset? SourceAt(JsonElement e) => e.GetProperty("source_time").GetDateTimeOffset();
static HttpResponseMessage Reply(HttpContent content) => new(HttpStatusCode.OK) { Content = content };
static void Pass(bool ok, string description)
{
    if (!ok) throw new InvalidOperationException("FAIL " + description);
    Console.WriteLine("PASS " + description);
}
static SpaceFeedClient Client(Func<HttpResponseMessage> reply, TimeSpan? ttl = null) =>
    new(new HttpClient(new LocalOnlyHandler(reply)),
        ttl ?? TimeSpan.FromMilliseconds(10), TimeSpan.FromSeconds(12));
static Task<FeedSnapshot> Fetch(SpaceFeedClient c, CancellationToken ct = default) =>
    c.FetchAsync("brent", new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE", SourceAt, ct);

var valid = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))));
var small = await Fetch(valid);
Pass(small.Status == "LIVE" && small.Data is not null && small.SourceTimestamp is not null,
    "small valid JSON: LIVE with source timestamp");

// A provider that omits source time must never be accepted as live evidence.
var missingSourceTime = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))),
    TimeSpan.FromMinutes(1));
var noTime = await missingSourceTime.FetchAsync("brent",
    new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE",
    _ => (DateTimeOffset?)null);
Pass(noTime.Status == "UNVERIFIED_TIMESTAMP" &&
     noTime.ErrorCode == "SOURCE_TIME_MISSING" && noTime.IsStale,
    "unverified provider timestamp must stay stale");
var noTimeCached = await missingSourceTime.FetchAsync("brent",
    new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE",
    _ => (DateTimeOffset?)null);
Pass(noTimeCached.Status == "UNVERIFIED_TIMESTAMP" && noTimeCached.IsStale,
    "missing timestamp must not be promoted to LIVE/CACHE");

var futureBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {
    source_time = DateTimeOffset.UtcNow.AddDays(2)
}));
var future = Client(() => Reply(new ByteArrayContent(futureBytes)), TimeSpan.FromMinutes(1));
var impossibleTime = await Fetch(future);
Pass(impossibleTime.Status == "INVALID_SOURCE_TIME" &&
     impossibleTime.ErrorCode == "FUTURE_SOURCE_TIME" && impossibleTime.IsStale,
     "future source timestamp cannot be LIVE");
var impossibleCached = await Fetch(future);
Pass(impossibleCached.Status == "INVALID_SOURCE_TIME" && impossibleCached.IsStale,
     "unverified future source cannot be promoted to CACHE");

var redirected = Client(() => new HttpResponseMessage(HttpStatusCode.OK) {
    Content = new ByteArrayContent(Encoding.UTF8.GetBytes(Json)),
    RequestMessage = new HttpRequestMessage(HttpMethod.Get, "https://other.invalid/brent")
});
var wrongOrigin = await Fetch(redirected);
Pass(wrongOrigin.Status == "OFFLINE" && wrongOrigin.Data is null &&
     wrongOrigin.ErrorCode == "PROVIDER_ENDPOINT_CHANGED",
     "unapproved redirect endpoint rejected");

using var revoke = new CancellationTokenSource();
var cancelledAfterProvider = Client(() =>
    Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))));
try {
    await cancelledAfterProvider.FetchAsync("brent", new Uri("https://example.invalid/brent"),
        "APPROVED_TEST_SOURCE", value => { revoke.Cancel(); return SourceAt(value); }, revoke.Token);
    throw new InvalidOperationException("FAIL STOP after callback ignored");
} catch (OperationCanceledException) {
    Console.WriteLine("PASS STOP during provider callback");
}

using var revokedOnHttpError = new CancellationTokenSource();
var failedAfterStop = Client(() =>
{
    revokedOnHttpError.Cancel();
    return new HttpResponseMessage(HttpStatusCode.BadGateway) {
        Content = new ByteArrayContent(Encoding.UTF8.GetBytes(Json))
    };
});
try {
    await Fetch(failedAfterStop, revokedOnHttpError.Token);
    throw new InvalidOperationException("FAIL HTTP-error cancellation returned cache");
} catch (OperationCanceledException) {
    Console.WriteLine("PASS STOP overrides concurrent HTTP error");
}

var announced = Client(() => {
    var r = Reply(new StreamContent(new GeneratedBody(Cap + 16)));
    r.Content.Headers.ContentLength = Cap + 16;
    return r;
});
var hugeHeader = await Fetch(announced);
Pass(hugeHeader.Status == "OFFLINE" && hugeHeader.ErrorCode == "RESPONSE_TOO_LARGE" && hugeHeader.Data is null,
    "declared oversize: no JSON parse, fail closed");

var chunked = Client(() => Reply(new StreamContent(new GeneratedBody(Cap + 16384))));
var hugeUnknown = await Fetch(chunked);
Pass(hugeUnknown.Status == "OFFLINE" && hugeUnknown.ErrorCode == "RESPONSE_TOO_LARGE",
    "unknown Content-Length: bound bytes while streaming");

var forged = Client(() => {
    var r = Reply(new StreamContent(new GeneratedBody(Cap + 1024)));
    r.Content.Headers.ContentLength = 100;
    return r;
});
var hugeUnderstated = await Fetch(forged);
Pass(hugeUnderstated.Status == "OFFLINE" && hugeUnderstated.ErrorCode == "RESPONSE_TOO_LARGE",
    "understated Content-Length: streaming cap is authoritative");

var badDate = Client(() => Reply(new ByteArrayContent(
    Encoding.UTF8.GetBytes("{\"source_time\":\"not-a-date\"}"))));
var badDateStatus = await Fetch(badDate);
Pass(badDateStatus.Status == "OFFLINE" &&
     badDateStatus.ErrorCode == "INVALID_SOURCE_TIME" && badDateStatus.Data is null,
     "malformed provider timestamp is a safe typed failure");

var wrongDateType = Client(() => Reply(new ByteArrayContent(
    Encoding.UTF8.GetBytes("{\"source_time\":123}"))));
var wrongDateStatus = await Fetch(wrongDateType);
Pass(wrongDateStatus.Status == "OFFLINE" &&
     wrongDateStatus.ErrorCode == "INVALID_SOURCE_TIME" && wrongDateStatus.Data is null,
     "non-string provider timestamp is a safe typed failure");

// Provider adapters can raise ordinary validation errors for untrusted source
// times; neither case may escape the SPACE error/status contract.
var invalidArgument = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))));
var invalidArgumentResult = await invalidArgument.FetchAsync("brent",
    new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE",
    _ => throw new ArgumentException("fixture-invalid-timestamp"));
Pass(invalidArgumentResult.Status == "OFFLINE" &&
     invalidArgumentResult.ErrorCode == "INVALID_SOURCE_TIME" &&
     invalidArgumentResult.IsStale, "provider ArgumentException maps to typed invalid timestamp");
var overflowDate = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))));
var overflowDateResult = await overflowDate.FetchAsync("brent",
    new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE",
    _ => throw new OverflowException("fixture-out-of-range-timestamp"));
Pass(overflowDateResult.Status == "OFFLINE" &&
     overflowDateResult.ErrorCode == "INVALID_SOURCE_TIME" &&
     overflowDateResult.IsStale, "provider OverflowException maps to typed invalid timestamp");

// Duplicate provider keys are ambiguous provenance, even in nested metadata.
var sourceTimeJson = JsonSerializer.Serialize(new { source_time = DateTimeOffset.UtcNow });
var duplicateRootJson = sourceTimeJson[..^1] + "," + sourceTimeJson[1..];
var duplicateRoot = Client(() => Reply(new ByteArrayContent(
    Encoding.UTF8.GetBytes(duplicateRootJson))));
var duplicateRootResult = await Fetch(duplicateRoot);
Pass(duplicateRootResult.Status == "OFFLINE" &&
     duplicateRootResult.ErrorCode == "INVALID_JSON" &&
     duplicateRootResult.Data is null && duplicateRootResult.IsStale,
    "duplicate provider source-time key rejected before LIVE cache");

// Construct the intentionally duplicate provider member names as raw JSON.
// JsonSerializer may reject a case-colliding anonymous type BEFORE FetchAsync,
// which would prevent testing the real parser's fail-closed behavior.
var duplicateNestedJson = Json[..^1] +
    ",\"metadata\":{\"license\":1,\"LICENSE\":2}}";
var duplicateNested = Client(() => Reply(new ByteArrayContent(
    Encoding.UTF8.GetBytes(duplicateNestedJson))));
var duplicateNestedResult = await Fetch(duplicateNested);
Pass(duplicateNestedResult.Status == "OFFLINE" &&
     duplicateNestedResult.ErrorCode == "INVALID_JSON" &&
     duplicateNestedResult.Data is null && duplicateNestedResult.IsStale,
    "case-insensitive nested duplicate provider key rejected");


var normalizedDuplicateJson = Json[..^1] +
    ",\"metadata\":{\"caf\u00e9\":1,\"cafe\u0301\":2}}";
var normalizedDuplicate = Client(() => Reply(new ByteArrayContent(
    Encoding.UTF8.GetBytes(normalizedDuplicateJson))));
var normalizedDuplicateResult = await Fetch(normalizedDuplicate);
Pass(normalizedDuplicateResult.Status == "OFFLINE" &&
     normalizedDuplicateResult.ErrorCode == "INVALID_JSON" &&
     normalizedDuplicateResult.Data is null && normalizedDuplicateResult.IsStale,
    "Unicode-equivalent nested provider keys cannot be treated as distinct provenance");

var badJson = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes("{"))));
var invalid = await Fetch(badJson);
Pass(invalid.Status == "OFFLINE" && invalid.ErrorCode == "INVALID_JSON",
    "bounded malformed JSON: explicit invalid format");

using var stopped = new CancellationTokenSource();
stopped.Cancel();
try {
    await Fetch(valid, stopped.Token);
    throw new InvalidOperationException("FAIL canceled STOP was ignored");
} catch (OperationCanceledException) {
    Console.WriteLine("PASS pre-canceled STOP: no cache success");
}

// Test fixtures only: these strings do NOT prove real accepted TaskIDs.
var lanes = new[] {
    new ProgressEvidence("P01", .20m, 100m, "test-r1", "ACCEPTED"),
    new ProgressEvidence("P02", .25m, 100m, "test-r2", "ACCEPTED"),
    new ProgressEvidence("P03", .20m, 100m, "test-r3", "ACCEPTED"),
    new ProgressEvidence("P04", .25m, 100m, "test-r4", "ACCEPTED"),
    new ProgressEvidence("P05", .10m, 100m, "test-r5", "ACCEPTED"),
};
Pass(EvidenceProgress.WeightedProduct(lanes) == 100m,
    "five distinct TaskID test fixtures use exact weighted arithmetic");
var duplicates = (ProgressEvidence[])lanes.Clone();
duplicates[4] = duplicates[4] with { TaskId = "p01" };
Pass(EvidenceProgress.WeightedProduct(duplicates) is null,
    "case-insensitive duplicate TaskID cannot be double-counted");
var blank = (ProgressEvidence[])lanes.Clone();
blank[1] = blank[1] with { TaskId = "  " };
Pass(EvidenceProgress.WeightedProduct(blank) is null,
    "blank TaskID cannot be accepted");
var unverified = (ProgressEvidence[])lanes.Clone();
unverified[2] = unverified[2] with { State = "SOURCE_PREPARED" };
Pass(EvidenceProgress.WeightedProduct(unverified) is null,
    "source-only TaskID cannot count toward accepted progress");
Console.WriteLine("P05 R16 smoke: 24 semantic assertions PASS (only after this .NET 8 program actually runs)");

sealed class LocalOnlyHandler(Func<HttpResponseMessage> reply) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var result = reply();
        result.RequestMessage ??= request;
        return Task.FromResult(result);
    }
}

// Non-seekable generator intentionally has no truthful Content-Length.
sealed class GeneratedBody(long length) : Stream
{
    private long _remaining = length;
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override int Read(byte[] buffer, int offset, int count)
    {
        var n = (int)Math.Min(count, _remaining);
        Array.Fill(buffer, (byte)' ', offset, n);
        _remaining -= n;
        return n;
    }
    public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        var n = (int)Math.Min(buffer.Length, _remaining);
        buffer.Span[..n].Fill((byte)' ');
        _remaining -= n;
        return ValueTask.FromResult(n);
    }
    public override void Flush() => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
