// NOX FIN ZAGR V16 - Executor 2, TaskID N2-01/N2-02
// Candidate adapter only. Integrator #6 owns host binding; not Windows-accepted.
using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.P02;

public sealed record OllamaModel(string Name, string? ModifiedAt, long? Size);
public sealed record OllamaChunk(string Text, bool Done, string? DoneReason);
public sealed record OllamaMessage(string Role, string Content);

/// <summary>Single Ollama transport adapter, without UI, WebView, database, or second chat engine.</summary>
public sealed class OllamaChatClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly bool _ownsClient;
    private readonly Uri _baseUri;
    private readonly SemaphoreSlim _singleChat = new(1, 1);
    private readonly TimeSpan _firstResponseLimit;
    private readonly TimeSpan _streamIdleLimit;
    private bool _disposed;

    public OllamaChatClient(Uri endpoint, HttpClient? httpClient = null, TimeSpan? firstResponseLimit = null,
        TimeSpan? streamIdleLimit = null)
    {
        if (endpoint is null || endpoint.Scheme != Uri.UriSchemeHttp ||
            !(endpoint.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
              endpoint.Host == "127.0.0.1" || endpoint.Host == "[::1]" || endpoint.Host == "::1") ||
            !string.IsNullOrEmpty(endpoint.UserInfo) || !string.IsNullOrEmpty(endpoint.Query) ||
            !string.IsNullOrEmpty(endpoint.Fragment) || endpoint.AbsolutePath != "/")
            throw new ArgumentException("Only local Ollama HTTP endpoints are allowed.", nameof(endpoint));

        _baseUri = endpoint.AbsoluteUri.EndsWith("/", StringComparison.Ordinal)
            ? endpoint : new Uri(endpoint.AbsoluteUri + "/");
        _http = httpClient ?? new HttpClient();
        _ownsClient = httpClient is null;
        _http.Timeout = Timeout.InfiniteTimeSpan; // cancellation is per request, never shared
        _firstResponseLimit = firstResponseLimit ?? TimeSpan.FromSeconds(45);
        if (_firstResponseLimit <= TimeSpan.Zero)
            throw new ArgumentOutOfRangeException(nameof(firstResponseLimit));
        _streamIdleLimit = streamIdleLimit ?? TimeSpan.FromSeconds(60);
        if (_streamIdleLimit <= TimeSpan.Zero)
            throw new ArgumentOutOfRangeException(nameof(streamIdleLimit));
    }

    public async Task<IReadOnlyList<OllamaModel>> GetModelsAsync(CancellationToken stop)
    {
        ThrowIfDisposed();
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(_baseUri, "api/tags"));
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, stop)
            .ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(stop).ConfigureAwait(false);
        using var json = await JsonDocument.ParseAsync(stream, cancellationToken: stop).ConfigureAwait(false);
        var result = new List<OllamaModel>();
        if (!json.RootElement.TryGetProperty("models", out var models) ||
            models.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("Ollama /api/tags omitted models array.");
        foreach (var item in models.EnumerateArray())
        {
            var name = item.TryGetProperty("name", out var n) ? n.GetString() : null;
            if (string.IsNullOrWhiteSpace(name)) continue;
            var modified = item.TryGetProperty("modified_at", out var m) && m.ValueKind == JsonValueKind.String
                ? m.GetString() : null;
            long? size = item.TryGetProperty("size", out var s) && s.TryGetInt64(out var bytes)
                ? bytes : null;
            result.Add(new OllamaModel(name, modified, size));
        }
        return result;
    }

    /// <summary>
    /// One live request at a time. Caller's CancellationToken is STOP; cancel also disposes
    /// the response stream. Independent first-response and per-line stream-idle deadlines;
    /// no simulated chunks and no synthetic successful completion.
    /// </summary>
    public async IAsyncEnumerable<OllamaChunk> StreamChatAsync(
        string model, IReadOnlyList<OllamaMessage> messages, 
        [EnumeratorCancellation] CancellationToken stop)
    {
        ThrowIfDisposed();
        if (string.IsNullOrWhiteSpace(model)) throw new ArgumentException("Model is required.", nameof(model));
        if (messages is null || messages.Count == 0)
            throw new ArgumentException("At least one message is required.", nameof(messages));
        await _singleChat.WaitAsync(stop).ConfigureAwait(false);
        try
        {
            using var firstResponseCts = CancellationTokenSource.CreateLinkedTokenSource(stop);
            firstResponseCts.CancelAfter(_firstResponseLimit);
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(_baseUri, "api/chat"))
            {
                Content = JsonContent.Create(new { model, stream = true, messages })
            };
            HttpResponseMessage response;
            try
            {
                response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead,
                    firstResponseCts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException e) when (!stop.IsCancellationRequested)
            {
                throw new TimeoutException("Ollama /api/chat first-response timeout.", e);
            }
            using (response)
            {
                response.EnsureSuccessStatusCode();
                await using var raw = await response.Content.ReadAsStreamAsync(stop).ConfigureAwait(false);
                using var reader = new StreamReader(raw, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
                var sawDone = false;
                while (true)
                {
                    stop.ThrowIfCancellationRequested();
                    string? line;
                    using (var idleCts = CancellationTokenSource.CreateLinkedTokenSource(stop))
                    {
                        idleCts.CancelAfter(_streamIdleLimit);
                        try
                        {
                            line = await reader.ReadLineAsync(idleCts.Token).ConfigureAwait(false);
                        }
                        catch (OperationCanceledException e) when (!stop.IsCancellationRequested)
                        {
                            throw new TimeoutException("Ollama stream inactivity timeout.", e);
                        }
                    }
                    if (line is null) break;
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    using var json = JsonDocument.Parse(line);
                    if (json.RootElement.TryGetProperty("error", out var error))
                        throw new InvalidDataException("Ollama stream error: " + error.ToString());
                    var text = json.RootElement.TryGetProperty("message", out var msg) &&
                        msg.TryGetProperty("content", out var part) && part.ValueKind == JsonValueKind.String
                        ? part.GetString() ?? "" : "";
                    var done = json.RootElement.TryGetProperty("done", out var flag) &&
                        flag.ValueKind == JsonValueKind.True;
                    var reason = json.RootElement.TryGetProperty("done_reason", out var r) &&
                        r.ValueKind == JsonValueKind.String ? r.GetString() : null;
                    yield return new OllamaChunk(text, done, reason);
                    if (done) { sawDone = true; break; }
                }
                if (!sawDone)
                    throw new EndOfStreamException("Ollama stream ended without done=true.");
            }
        }
        finally { _singleChat.Release(); }
    }

    private void ThrowIfDisposed()
    {
        if (_disposed) throw new ObjectDisposedException(nameof(OllamaChatClient));
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        if (_ownsClient) _http.Dispose();
        // Do not dispose semaphore: an active streaming iterator may still release it.
    }
}
