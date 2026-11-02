// NOX V16 P02 owner-only. Duplex client for the EXISTING authenticated Python host.
// The E06 Windows host owns Python process lifetime, original DB and native identity.
// This file starts no processes or HTTP listeners, creates no storage and grants no permissions.
using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Nox.P02;

public sealed class NativePipeHold : Exception
{
    public string Code { get; }
    public NativePipeHold(string code) : base(code) => Code = code;
}

public sealed record NativePipeResult(string RequestId, bool Accepted, JsonElement? Result, string? ErrorCode);

public sealed class NativePythonPipe : IAsyncDisposable
{
    private const int MaxInput = 64 * 1024;
    private const int MaxOutput = 1024 * 1024;
    private const int MaxRequests = 8192;
    private static readonly HashSet<string> Routes = new(StringComparer.Ordinal) {
        "helion.chat", "core.chat", "persona.chat", "chat.model", "chat.history",
        "chat.rag", "chat.voice", "chat.stop", "calls.history"
    };
    private static readonly Regex Nonce = new("^[a-f0-9]{32}$", RegexOptions.CultureInvariant);
    private static readonly Regex ErrorCode = new("^[A-Z][A-Z0-9_]{0,99}$", RegexOptions.CultureInvariant);
    private readonly Stream _input;
    private readonly Stream _output;
    private readonly string _runId;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly CancellationTokenSource _lifetime = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource<NativePipeResult>> _pending = new(StringComparer.Ordinal);
    private readonly Task _reader;
    private int _count;
    private int _busy;
    private int _closed;

    public NativePythonPipe(Stream pythonStdout, Stream pythonStdin, string hostRunId)
    {
        if (!pythonStdout.CanRead || !pythonStdin.CanWrite) throw new ArgumentException("Private duplex streams required");
        if (string.IsNullOrEmpty(hostRunId) || hostRunId.Length > 128 || hostRunId.Any(c => c < 32 || c > 126))
            throw new ArgumentException("Authenticated host RunID required", nameof(hostRunId));
        _input = pythonStdout;
        _output = pythonStdin;
        _runId = hostRunId;
        _reader = Task.Run(ReadPumpAsync);
    }

    // The native/Python boundary must not interpret the same field twice.
    // JsonElement permits duplicate JSON names while Python dict decoding
    // silently keeps the last value; deny ambiguity before any framed action
    // is written or any native reply/event is trusted.
    private static void RequireUnambiguousJson(JsonElement node)
    {
        if (node.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in node.EnumerateObject())
            {
                if (!keys.Add(property.Name))
                    throw new NativePipeHold("NATIVE_JSON_DUPLICATE_FIELD_DENIED");
                RequireUnambiguousJson(property.Value);
            }
        }
        else if (node.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in node.EnumerateArray())
                RequireUnambiguousJson(item);
        }
    }

    public async Task<NativePipeResult> RequestAsync(string route, object payload,
        TimeSpan? timeout = null, CancellationToken cancel = default)
    {
        if (Volatile.Read(ref _closed) != 0) throw new NativePipeHold("NATIVE_PIPE_CLOSED");
        if (route is null || !Routes.Contains(route)) throw new NativePipeHold("NATIVE_ROUTE_DENIED");
        if (payload is null) throw new NativePipeHold("NATIVE_PAYLOAD_INVALID");
        var wait = timeout ?? TimeSpan.FromSeconds(60);
        if (wait <= TimeSpan.Zero || wait > TimeSpan.FromMinutes(10))
            throw new NativePipeHold("NATIVE_TIMEOUT_INVALID");
        // The untrusted page may never supply native identity or permission fields.
        JsonElement data;
        try { data = JsonSerializer.SerializeToElement(payload); }
        catch (Exception e) when (e is JsonException or NotSupportedException) { throw new NativePipeHold("NATIVE_PAYLOAD_INVALID"); }
        if (data.ValueKind != JsonValueKind.Object) throw new NativePipeHold("NATIVE_PAYLOAD_INVALID");
        RequireUnambiguousJson(data);
        foreach (var prop in data.EnumerateObject())
            if (prop.Name is "tenant" or "principal" or "windows_sid" or "session_id" or "scopes"
                or "private_approved" or "native_approve" or "nativeConsent" or "admin")
                throw new NativePipeHold("PAGE_AUTHORITY_CLAIM_DENIED");

        bool regular = route != "chat.stop";
        if (regular && Interlocked.CompareExchange(ref _busy, 1, 0) != 0)
            throw new NativePipeHold("NATIVE_BUSY");
        var nonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(16)).ToLowerInvariant();
        var completion = new TaskCompletionSource<NativePipeResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        bool inserted = false;
        bool wrote = false;
        try
        {
            if (Interlocked.Increment(ref _count) > MaxRequests)
                throw new NativePipeHold("NATIVE_SESSION_FRAME_WINDOW_EXHAUSTED");
            var bytes = JsonSerializer.SerializeToUtf8Bytes(new {
                protocol = "NOX-P02-NATIVE-v1", requestId = nonce, route, payload = data, runId = _runId
            });
            if (bytes.Length == 0 || bytes.Length > MaxInput)
                throw new NativePipeHold("NATIVE_FRAME_TOO_LARGE_OR_EMPTY");
            inserted = _pending.TryAdd(nonce, completion);
            if (!inserted) throw new NativePipeHold("NATIVE_NONCE_COLLISION");
            // Only the short framed WRITE is serialized; STOP can overtake an active response.
            await _writeLock.WaitAsync(cancel).ConfigureAwait(false);
            try
            {
                var header = new byte[4];
                BinaryPrimitives.WriteUInt32BigEndian(header, checked((uint)bytes.Length));
                await _output.WriteAsync(header, cancel).ConfigureAwait(false);
                await _output.WriteAsync(bytes, cancel).ConfigureAwait(false);
                await _output.FlushAsync(cancel).ConfigureAwait(false);
            }
            catch
            {
                FaultAll("NATIVE_OUTPUT_TRANSPORT_FAILED");
                throw;
            }
            finally { _writeLock.Release(); }
            wrote = true;
            // A timeout does not recycle the requestId or retry an uncertain action.
            // Its pending entry remains until the peer replies or the session ends.
            return await completion.Task.WaitAsync(wait, cancel).ConfigureAwait(false);
        }
        finally
        {
            // Busy means one request may be active, not just one caller waiting.
            // It is released by the reader upon receiving that request's reply.
            if (!wrote && inserted) _pending.TryRemove(nonce, out _);
            if (!wrote && regular) Interlocked.Exchange(ref _busy, 0);
        }
    }

    private async Task ReadPumpAsync()
    {
        try
        {
            var header = new byte[4];
            while (!_lifetime.IsCancellationRequested)
            {
                await _input.ReadExactlyAsync(header, _lifetime.Token).ConfigureAwait(false);
                int count = checked((int)BinaryPrimitives.ReadUInt32BigEndian(header));
                if (count < 1 || count > MaxOutput) throw new NativePipeHold("NATIVE_REPLY_LENGTH_DENIED");
                var reply = new byte[count];
                await _input.ReadExactlyAsync(reply, _lifetime.Token).ConfigureAwait(false);
                using var doc = JsonDocument.Parse(reply);
                var root = doc.RootElement;
                RequireUnambiguousJson(root);
                if (root.ValueKind != JsonValueKind.Object ||
                    !root.TryGetProperty("protocol", out var p) || p.GetString() != "NOX-P02-NATIVE-v1" ||
                    !root.TryGetProperty("runId", out var r) || r.GetString() != _runId ||
                    !root.TryGetProperty("requestId", out var n) || n.ValueKind != JsonValueKind.String)
                    throw new NativePipeHold("NATIVE_RESPONSE_PROTOCOL_MISMATCH");
                string nonce = n.GetString()!;
                if (!Nonce.IsMatch(nonce) || !_pending.ContainsKey(nonce))
                    throw new NativePipeHold("NATIVE_RESPONSE_NONCE_MISMATCH");
                if (!root.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String)
                    throw new NativePipeHold("NATIVE_RESPONSE_STATUS_INVALID");
                var value = status.GetString();
                NativePipeResult outcome;
                if (value == "OK" && root.TryGetProperty("result", out var result))
                    outcome = new NativePipeResult(nonce, true, result.Clone(), null);
                else if (value == "HOLD" && root.TryGetProperty("errorCode", out var code) &&
                         code.ValueKind == JsonValueKind.String && ErrorCode.IsMatch(code.GetString() ?? ""))
                    outcome = new NativePipeResult(nonce, false, null, code.GetString());
                else throw new NativePipeHold("NATIVE_RESPONSE_STATUS_INVALID");
                if (!_pending.TryRemove(nonce, out var waiter))
                    throw new NativePipeHold("NATIVE_RESPONSE_NONCE_MISMATCH");
                waiter.TrySetResult(outcome);
                // Peer may return STOP before a chat; never release chat on STOP.
                if (_pending.IsEmpty) Interlocked.Exchange(ref _busy, 0);
            }
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception) { FaultAll("NATIVE_READ_TRANSPORT_HOLD"); }
    }

    private void FaultAll(string code)
    {
        Interlocked.Exchange(ref _closed, 1);
        foreach (var kv in _pending)
            if (_pending.TryRemove(kv.Key, out var task)) task.TrySetException(new NativePipeHold(code));
        Interlocked.Exchange(ref _busy, 0);
    }

    public async ValueTask DisposeAsync()
    {
        FaultAll("NATIVE_PIPE_CLOSED");
        _lifetime.Cancel();
        // Input/output/process are exclusively owned and disposed by E06 native host.
        try { await _reader.WaitAsync(TimeSpan.FromMilliseconds(200)).ConfigureAwait(false); }
        catch (Exception) { /* A non-cancellable stream remains caller-owned. */ }
        _lifetime.Dispose();
        _writeLock.Dispose();
    }
}
