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
const string Json = "{\"source_time\":\"2026-10-28T20:00:00Z\"}";
static DateTimeOffset? SourceAt(JsonElement e) => e.GetProperty("source_time").GetDateTimeOffset();
static HttpResponseMessage Reply(HttpContent content) => new(HttpStatusCode.OK) { Content = content };
static void Pass(bool ok, string description)
{
    if (!ok) throw new InvalidOperationException("FAIL " + description);
    Console.WriteLine("PASS " + description);
}
static SpaceFeedClient Client(Func<HttpResponseMessage> reply) =>
    new(new HttpClient(new LocalOnlyHandler(reply)), TimeSpan.FromMilliseconds(10), TimeSpan.FromSeconds(12));
static Task<FeedSnapshot> Fetch(SpaceFeedClient c, CancellationToken ct = default) =>
    c.FetchAsync("brent", new Uri("https://example.invalid/brent"), "APPROVED_TEST_SOURCE", SourceAt, ct);

var valid = Client(() => Reply(new ByteArrayContent(Encoding.UTF8.GetBytes(Json))));
var small = await Fetch(valid);
Pass(small.Status == "LIVE" && small.Data is not null && small.SourceTimestamp is not null,
    "small valid JSON: LIVE with source timestamp");

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

Console.WriteLine("6/6 semantic assertions PASS (when this project actually runs on .NET 8)");

sealed class LocalOnlyHandler(Func<HttpResponseMessage> reply) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        return Task.FromResult(reply());
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
