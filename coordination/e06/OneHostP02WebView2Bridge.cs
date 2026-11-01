// NOX V16 E06 · manual T06 · adapter for the ONE existing WPF CoreWebView2.
// Inject this only from the authenticated original MainWindow after native
// SID, ACL and private PythonPipe process ownership are established.
// No second WebView, web server, database, Python host, or model is created.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Principal;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;
using Nox.P02;

namespace NoxP01;

internal sealed class OneHostP02WebView2Bridge : IDisposable
{
    private static readonly Regex RequestId = new(
        @"\A[0-9a-f]{32}\z", RegexOptions.CultureInvariant);
    private static readonly HashSet<string> Routes = new(StringComparer.Ordinal)
    {
        "helion.chat", "core.chat", "persona.chat", "chat.model",
        "chat.history", "chat.rag", "chat.voice", "chat.stop", "calls.history",
        "chat.commands", "models.catalog", "models.installed", "models.queue",
        "models.pull", "models.cancel", "models.retry", "models.digest", "models.gguf.import",
        "models.preflight", "models.licenses", "gpu.preflight", "training.start",
        "training.pause", "training.resume", "training.checkpoints", "training.evaluate",
        "system.autostart"
    };
    private static readonly HashSet<string> AuthorityFields = new(StringComparer.Ordinal)
    {
        "tenant", "principal", "windows_sid", "session_id", "scopes",
        "private_approved", "native_approve", "nativeConsent", "admin"
    };
    private readonly CoreWebView2 _web;
    private readonly Uri _virtualOrigin;
    private readonly NativePythonPipe _existingPipe;
    private readonly string _ownerWindowsSid;
    private readonly Func<string, string, bool> _nativeAcl;
    private readonly Func<string, JsonElement, CancellationToken, Task<bool>> _nativeConsent;
    private readonly SynchronizationContext _uiContext;
    private readonly Func<string, JsonElement, CancellationToken, Task<NativePipeResult>>? _nativeOwnerAction;
    private readonly HashSet<string> _usedIds = new(StringComparer.Ordinal);
    private readonly CancellationTokenSource _lifetime = new();
    private CancellationTokenSource _document = new();
    private long _epoch;
    private int _activeChat;
    private int _stopPending;
    private int _disposed;
    private long _streamEpoch;

    // All values here come from the native host, NEVER from a WebMessage.
    internal OneHostP02WebView2Bridge(
        CoreWebView2 existingCore,
        Uri trustedMappedOrigin,
        NativePythonPipe existingHostOwnedPipe,
        string authenticatedWindowsSid,
        Func<string, string, bool> nativeAcl,
        Func<string, JsonElement, CancellationToken, Task<bool>> nativeConsent,
        Func<string, JsonElement, CancellationToken, Task<NativePipeResult>>? nativeOwnerAction = null)
    {
        _web = existingCore ?? throw new ArgumentNullException(nameof(existingCore));
        _virtualOrigin = trustedMappedOrigin ?? throw new ArgumentNullException(nameof(trustedMappedOrigin));
        _existingPipe = existingHostOwnedPipe ?? throw new ArgumentNullException(nameof(existingHostOwnedPipe));
        _nativeAcl = nativeAcl ?? throw new ArgumentNullException(nameof(nativeAcl));
        _nativeConsent = nativeConsent ?? throw new ArgumentNullException(nameof(nativeConsent));
        _nativeOwnerAction = nativeOwnerAction;
        _uiContext = SynchronizationContext.Current ??
            throw new InvalidOperationException("E06_NATIVE_UI_CONTEXT_REQUIRED");
        if (_virtualOrigin.Scheme != Uri.UriSchemeHttps ||
            !_virtualOrigin.IsDefaultPort || _virtualOrigin.UserInfo.Length != 0 ||
            !string.Equals(_virtualOrigin.Host, "nox.local", StringComparison.OrdinalIgnoreCase) ||
            _virtualOrigin.AbsolutePath != "/" || _virtualOrigin.Query.Length != 0 ||
            _virtualOrigin.Fragment.Length != 0)
            throw new ArgumentException("E06_ORIGINAL_MAPPED_ORIGIN_REQUIRED");
        _ownerWindowsSid = authenticatedWindowsSid;
        if (!NativeSidMatches())
            throw new UnauthorizedAccessException("E06_AUTHENTICATED_WINDOWS_SID_REQUIRED");
        _web.WebMessageReceived += OnWebMessageReceived;
        _web.NavigationStarting += OnNavigationStarting;
        _web.SourceChanged += OnSourceChanged;
        _web.ContentLoading += OnContentLoading;
        _web.ProcessFailed += OnProcessFailed;
    }

    private bool NativeSidMatches()
    {
        try
        {
            var sid = WindowsIdentity.GetCurrent().User?.Value;
            return !string.IsNullOrWhiteSpace(sid) &&
                   string.Equals(sid, _ownerWindowsSid, StringComparison.Ordinal);
        }
        catch { return false; }
    }

    private bool Trusted(string? raw)
    {
        return Uri.TryCreate(raw, UriKind.Absolute, out var uri) &&
               uri.Scheme == Uri.UriSchemeHttps && uri.UserInfo.Length == 0 &&
               uri.IsDefaultPort &&
               string.Equals(uri.Host, _virtualOrigin.Host, StringComparison.OrdinalIgnoreCase);
    }

    private void RevokeDocument()
    {
        if (Volatile.Read(ref _disposed) != 0) return;
        Interlocked.Increment(ref _epoch);
        Interlocked.Increment(ref _streamEpoch);
        _document.Cancel();
        _document.Dispose();
        _document = new CancellationTokenSource();
        // Navigating away while a model is executing must request a real
        // owner STOP, not merely suppress its response in WebView2.
        if (Interlocked.CompareExchange(ref _stopPending, 1, 0) == 0)
            _ = StopRevokedChatAsync();
        // Never clear _usedIds: a page or transport must not replay native writes.
    }

    private async Task StopRevokedChatAsync()
    {
        try
        {
            if (NativeSidMatches() && _nativeAcl(_ownerWindowsSid, "chat.stop"))
                await _existingPipe.RequestAsync("chat.stop", new { },
                    TimeSpan.FromSeconds(10), _lifetime.Token);
        }
        catch { /* Fail closed; the native host still owns process shutdown. */ }
        finally { Interlocked.Exchange(ref _stopPending, 0); }
    }
    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        RevokeDocument();
        if (!Trusted(e.Uri)) e.Cancel = true;
    }
    private void OnSourceChanged(object? sender, CoreWebView2SourceChangedEventArgs e)
        => RevokeDocument();
    private void OnContentLoading(object? sender, CoreWebView2ContentLoadingEventArgs e)
        => RevokeDocument();
    private void OnProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs e)
        => RevokeDocument();

    private bool IsCurrent(string source, long epoch) =>
        Volatile.Read(ref _disposed) == 0 && !_lifetime.IsCancellationRequested &&
        Interlocked.Read(ref _epoch) == epoch && Trusted(source) && Trusted(_web.Source) &&
        string.Equals(source, _web.Source, StringComparison.Ordinal);

    private void Reply(string source, long epoch, string id, string route,
                       string state, string? error, JsonElement? result = null)
    {
        if (!IsCurrent(source, epoch)) return;
        try
        {
            _web.PostWebMessageAsJson(JsonSerializer.Serialize(new
            {
                kind = "p02NativeResult", requestId = id, routeId = route,
                state, errorCode = error, result
            }));
        }
        catch { /* No stale delivery after WebView disposal. */ }
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (Volatile.Read(ref _disposed) != 0 || !Trusted(e.Source) || !Trusted(_web.Source))
            return;
        var source = e.Source;
        var epoch = Interlocked.Read(ref _epoch);
        var cancel = _document.Token;
        string id = "", route = "";
        try
        {
            var raw = e.WebMessageAsJson;
            if (raw.Length > 65536) return;
            using var json = JsonDocument.Parse(raw, new JsonDocumentOptions { MaxDepth = 16 });
            var root = json.RootElement;
            if (root.ValueKind != JsonValueKind.Object) return;
            // Ignore existing P01 messages. This is a separate, explicit
            // message kind using the SAME WebView and native user session.
            var kinds = root.EnumerateObject().Where(x => x.NameEquals("kind")).ToArray();
            if (kinds.Length != 1 || kinds[0].Value.ValueKind != JsonValueKind.String ||
                kinds[0].Value.GetString() != "p02.native") return;
            var props = root.EnumerateObject().ToArray();
            if (props.Length != 4 || props.Select(x => x.Name).Distinct(StringComparer.Ordinal).Count() != 4 ||
                !root.TryGetProperty("requestId", out var request) ||
                !root.TryGetProperty("routeId", out var name) ||
                !root.TryGetProperty("payload", out var payload) ||
                request.ValueKind != JsonValueKind.String ||
                name.ValueKind != JsonValueKind.String || payload.ValueKind != JsonValueKind.Object)
                return;
            id = request.GetString() ?? "";
            route = name.GetString() ?? "";
            if (!RequestId.IsMatch(id) || !Routes.Contains(route)) return;
            if (_usedIds.Count >= 8192 || !_usedIds.Add(id))
                return; // Never reuse even failed nonce IDs.
            if (payload.EnumerateObject().Any(p => AuthorityFields.Contains(p.Name)))
            {
                Reply(source, epoch, id, route, "HOLD", "PAGE_AUTHORITY_CLAIM_DENIED");
                return;
            }
            if (!NativeSidMatches() || !_nativeAcl(_ownerWindowsSid, route))
            {
                Reply(source, epoch, id, route, "HOLD", "NATIVE_PERMISSION_DENIED");
                return;
            }
            // A previously authorized queued-model STOP must overtake
            // transfers just like chat.stop. SID/ACL and bounded jobId remain
            // enforced by this bridge and by the native P03 owner.
            if (route is not ("chat.stop" or "models.cancel") &&
                !await _nativeConsent(route, payload.Clone(), cancel))
            {
                Reply(source, epoch, id, route, "HOLD", "NATIVE_CONSENT_DENIED");
                return;
            }
            if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                !_nativeAcl(_ownerWindowsSid, route)) return;
            if (route == "chat.stop") Interlocked.Increment(ref _streamEpoch);
            // P03's existing C# queue stays in this WPF host; it must not be
            // replaced by a Python downloader or sent through a second IPC.
            if (_nativeOwnerAction is not null &&
                (route.StartsWith("models.", StringComparison.Ordinal) ||
                 route=="chat.stop" ||
                 route=="system.autostart" ||
                 route=="chat.commands" && payload.TryGetProperty("action",out var command) &&
                 command.ValueKind==JsonValueKind.String && command.GetString()=="training.import"))
            {
                var ownerResult = await _nativeOwnerAction(route, payload.Clone(), cancel);
                if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                    !_nativeAcl(_ownerWindowsSid, route)) return;
                // Owner ACK means a durable job was accepted, NOT that the
                // entire model has been downloaded, imported or installed.
                // Never claim cancellation when the owner reports false.
                var ownerState = ownerResult.Accepted ? "COMPLETED" : "HOLD";
                if (route is "models.pull" or "models.retry" or "models.gguf.import")
                {
                    ownerState = "HOLD";
                    if (ownerResult.Accepted && ownerResult.Result is JsonElement job &&
                        job.ValueKind == JsonValueKind.Object &&
                        job.TryGetProperty("state", out var jobState) &&
                        jobState.ValueKind == JsonValueKind.String)
                    {
                        ownerState = jobState.GetString() switch
                        {
                            "Queued" => "QUEUED",
                            "Running" or "Cancelling" => "IN_PROGRESS",
                            "Completed" => "COMPLETED",
                            _ => "HOLD"
                        };
                    }
                }
                else if (route == "models.cancel")
                {
                    ownerState = ownerResult.Accepted &&
                        ownerResult.Result is JsonElement cancelled &&
                        cancelled.ValueKind == JsonValueKind.Object &&
                        cancelled.TryGetProperty("cancelled", out var flag) &&
                        flag.ValueKind == JsonValueKind.True ? "STOP_REQUESTED" : "HOLD";
                }
                else if (route == "chat.stop")
                    ownerState = ownerResult.Accepted ? "STOP_REQUESTED" : "HOLD";
                Reply(source, epoch, id, route, ownerState,
                      ownerResult.ErrorCode, ownerResult.Result);
                return;
            }
            // Track only actual model calls; native STOP may overtake the
            // blocking Python worker on navigation, reload or window teardown.
            var isChat = route is "helion.chat" or "core.chat" or "persona.chat";
            var streamEpoch = Interlocked.Read(ref _streamEpoch);
            if (isChat) Interlocked.Increment(ref _activeChat);
            try
            {
                var result = await _existingPipe.RequestAsync(
                    route, payload.Clone(), route == "chat.stop"
                        ? TimeSpan.FromSeconds(10) : TimeSpan.FromSeconds(60),
                    cancel, onEvent: item => _uiContext.Post(_ =>
                    {
                        // The reader runs off-thread. Recheck native grants on
                        // the UI thread and suppress every stale/revoked delta.
                        if (Interlocked.Read(ref _streamEpoch) != streamEpoch ||
                            !IsCurrent(source, epoch) || !NativeSidMatches() ||
                            !_nativeAcl(_ownerWindowsSid, route)) return;
                        try {
                            _web.PostWebMessageAsJson(JsonSerializer.Serialize(new {
                                kind = "p02NativeEvent", requestId = id,
                                routeId = route, state = "STREAMING", data = item
                            }));
                        } catch { /* Disposed native view: no stale delivery. */ }
                    }, null));
                // Host still re-authorizes after the potentially blocking IPC call.
                if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                    !_nativeAcl(_ownerWindowsSid, route)) return;
                // E-F2: STOP invalidates stale final chat replies, not only deltas.
                if (isChat && Interlocked.Read(ref _streamEpoch) != streamEpoch) return;
                // STOP acknowledged by the Python owner only means requested.
                // Never misreport a remote model as fully aborted before proof.
                var state = !result.Accepted ? "HOLD" :
                    route == "chat.stop" ? "STOP_REQUESTED" : "COMPLETED";
                Reply(source, epoch, id, route,
                      state, result.ErrorCode, result.Result);
            }
            finally { if (isChat) Interlocked.Decrement(ref _activeChat); }
        }
        catch (OperationCanceledException) { /* Native STOP/window close: no stale ACK. */ }
        catch (NativePipeHold hold)
        {
            if (RequestId.IsMatch(id)) Reply(source, epoch, id, route, "HOLD", hold.Code);
        }
        catch (TimeoutException)
        {
            if (RequestId.IsMatch(id)) Reply(source, epoch, id, route, "HOLD", "NATIVE_CHAT_TIMEOUT");
        }
        catch (Exception)
        {
            if (id.Length == 32 && RequestId.IsMatch(id))
                Reply(source, epoch, id, route, "HOLD", "NATIVE_TRANSPORT_HOLD");
        }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        _lifetime.Cancel();
        _document.Cancel();_document.Dispose();
        _web.WebMessageReceived -= OnWebMessageReceived;
        _web.NavigationStarting -= OnNavigationStarting;
        _web.SourceChanged -= OnSourceChanged;
        _web.ContentLoading -= OnContentLoading;
        _web.ProcessFailed -= OnProcessFailed;
        _lifetime.Dispose();
        // Original WPF host owns and disposes NativePythonPipe/process exactly once.
    }
}
