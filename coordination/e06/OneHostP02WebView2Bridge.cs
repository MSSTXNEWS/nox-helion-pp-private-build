// NOX V16 E06 · manual T06 · adapter for the ONE existing WPF CoreWebView2.
// Inject this only from the authenticated original MainWindow after native
// SID, ACL and private PythonPipe process ownership are established.
// No second WebView, web server, database, Python host, or model is created.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
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
        "system.autostart", "browser.open", "browser.navidle", "menu.dispatch", "menu.binding", "selfwrite.ack", "selflearn.ack"
    };
    private static readonly HashSet<string> AuthorityFields = new(StringComparer.Ordinal)
    {
        "tenant", "principal", "windows_sid", "session_id", "scopes",
        "private_approved", "native_approve", "nativeConsent", "admin"
    };
    private readonly CoreWebView2 _web;
    private readonly Action<string> _writeDiagnostic;
    private readonly Uri _virtualOrigin;
    private readonly NativePythonPipe _existingPipe;
    private readonly string _ownerWindowsSid;
    private readonly Func<string, string, bool> _nativeAcl;
    private readonly Func<string, JsonElement, CancellationToken, Task<bool>> _nativeConsent;
    private readonly SynchronizationContext _uiContext;
    private readonly Func<string, JsonElement, CancellationToken, Task<NativePipeResult>>? _nativeOwnerAction;
    private readonly Action<CoreWebView2>? _onBrowserProcessExited;
    private readonly HashSet<string> _usedIds = new(StringComparer.Ordinal);
    private readonly CancellationTokenSource _lifetime = new();
    private CancellationTokenSource _document = new();
    private long _epoch;
    private int _activeChat;
    private int _stopPending;
    private int _disposed;
    private long _streamEpoch;
    private bool _rendererAwaitingTrustedContent;
    private bool _rendererReloadInitiated;
    private bool _browserProcessLost;
    private int _rendererReloadAttempts;
    private bool _externalMode;
    private bool _nativeReturnPending;
    private string? _externalHost;
    internal bool BrowserExternalActive => _externalMode;
    internal bool BrowserAllowsRequest(string? url) => _externalMode && ((_nativeReturnPending && ExactShellReturn(url)) || (!_nativeReturnPending && IsApprovedExternal(url)));

    // All values here come from the native host, NEVER from a WebMessage.
    internal OneHostP02WebView2Bridge(
        CoreWebView2 existingCore,
        Uri trustedMappedOrigin,
        NativePythonPipe existingHostOwnedPipe,
        string authenticatedWindowsSid,
        Func<string, string, bool> nativeAcl,
        Func<string, JsonElement, CancellationToken, Task<bool>> nativeConsent,
        Action<string> writeDiagnostic,
        Func<string, JsonElement, CancellationToken, Task<NativePipeResult>>? nativeOwnerAction = null,
        Action<CoreWebView2>? onBrowserProcessExited = null)
    {
        _web = existingCore ?? throw new ArgumentNullException(nameof(existingCore));
        _virtualOrigin = trustedMappedOrigin ?? throw new ArgumentNullException(nameof(trustedMappedOrigin));
        _existingPipe = existingHostOwnedPipe ?? throw new ArgumentNullException(nameof(existingHostOwnedPipe));
        _nativeAcl = nativeAcl ?? throw new ArgumentNullException(nameof(nativeAcl));
        _nativeConsent = nativeConsent ?? throw new ArgumentNullException(nameof(nativeConsent));
        _writeDiagnostic = writeDiagnostic ?? throw new ArgumentNullException(nameof(writeDiagnostic));
        _nativeOwnerAction = nativeOwnerAction;
        _onBrowserProcessExited = onBrowserProcessExited;
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
        _web.NavigationCompleted += OnNavigationCompleted;
        _web.NewWindowRequested += OnNewWindowRequested;
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

    // Native Back may restore IPC ONLY on the original, exact mapped HOME.
    // Non-HOME local paths remain quarantined during external navigation.
    private bool ExactShellReturn(string? raw) =>
        Trusted(raw) && Uri.TryCreate(raw, UriKind.Absolute, out var uri) &&
        string.Equals(uri.AbsoluteUri, _virtualOrigin.AbsoluteUri, StringComparison.Ordinal);

    private void RevokeDocument()
    {
        if (Volatile.Read(ref _disposed) != 0) return;
        // Read BEFORE cancelling: idle HOME/WebView2 navigation is not a user STOP.
        // An already-running native chat must still receive the existing real STOP.
        var chatWasActive = Volatile.Read(ref _activeChat) > 0;
        Interlocked.Increment(ref _epoch);
        Interlocked.Increment(ref _streamEpoch);
        // Exchange the lifetime before Cancel: reentrant callbacks must not
        // reuse a revoked token or prevent the existing owner STOP.
        var revoked = _document;
        _document = new CancellationTokenSource();
        try { revoked.Cancel(); }
        catch (AggregateException) { /* callbacks cannot restore authority */ }
        finally { revoked.Dispose(); }
        // Navigating away while a model is executing must request a real
        // owner STOP, not merely suppress its response in WebView2.
        if (chatWasActive && Interlocked.CompareExchange(ref _stopPending, 1, 0) == 0)
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
    // Native WPF owner only. Reuse THIS bridge and THIS WebView2.
    // Untrusted pages cannot create grants or modify native host permissions.
    internal bool TryOpenReviewedExternal(Uri target, IReadOnlyCollection<string> approvedHosts,
        bool nativeGestureVerified, bool ipcDetached, bool hostObjectsRemoved,
        bool networkIsolationAttested)
    {
        if (Volatile.Read(ref _disposed) != 0 || _externalMode ||
            !ExactShellReturn(_web.Source) || !NativeSidMatches() ||
            !nativeGestureVerified || !ipcDetached || !hostObjectsRemoved ||
            !networkIsolationAttested || !ReviewedExternal(target) ||
            approvedHosts is null) return false;
        bool approved = false;
        foreach (var entry in approvedHosts)
            if (PublicHost(entry) && string.Equals(target.IdnHost, entry,
                StringComparison.OrdinalIgnoreCase)) { approved = true; break; }
        if (!approved || _web.Settings.IsWebMessageEnabled || _web.Settings.AreHostObjectsAllowed)
            return false; // actual host settings, never only caller-supplied booleans
        _externalHost = target.IdnHost;
        _externalMode = true;  // Native IPC is rejected before navigation.
        _nativeReturnPending = false;
        RevokeDocument();     // Cancel stale model/chat jobs and request STOP.
        try { _web.Navigate(target.AbsoluteUri); return true; }
        catch { return false; } // Retain locked external mode on failure.
    }

    internal bool ReturnToReviewedShell()
    {
        if (Volatile.Read(ref _disposed) != 0 || !_externalMode ||
            _nativeReturnPending || !NativeSidMatches()) return false;
        _nativeReturnPending = true;
        RevokeDocument();
        try {
            // Existing bridge still rejects external native messages while the
            // original NOX local document prepares its new channel.
            // IPC stays off until the trusted NOX shell ContentLoading event.
            _web.Navigate(_virtualOrigin.AbsoluteUri); return true;
        } catch {
            _nativeReturnPending = false; // permit another real native Back
            _web.Settings.IsWebMessageEnabled = false; // external quarantine stays
            return false;
        }
    }

    private static bool PublicHost(string? host)
    {
        if (string.IsNullOrWhiteSpace(host) || host.Length > 253 ||
            host.StartsWith(".", StringComparison.Ordinal) ||
            host.EndsWith(".", StringComparison.Ordinal) ||
            host.Contains("..", StringComparison.Ordinal) || host.IndexOf('.') < 1 ||
            IPAddress.TryParse(host, out _) ||
            Uri.CheckHostName(host) != UriHostNameType.Dns) return false;
        foreach (var suffix in new[]{ ".localhost", ".local", ".internal",
            ".invalid", ".test", ".example", ".onion", ".arpa", ".lan", ".home" })
            if (host.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
                return false;
        return true;
    }
    private static bool ReviewedExternal(Uri? target) =>
        target is not null && target.IsAbsoluteUri && target.IsDefaultPort &&
        target.UserInfo.Length == 0 &&
        target.Scheme == Uri.UriSchemeHttps && PublicHost(target.IdnHost);

    private bool IsApprovedExternal(string? raw)
    {
        return Uri.TryCreate(raw, UriKind.Absolute, out var uri) &&
               ReviewedExternal(uri) &&
               string.Equals(uri.IdnHost, _externalHost, StringComparison.OrdinalIgnoreCase);
    }

    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        // Reject an untrusted navigation BEFORE revoking the current trusted
        // document: a denied target must not cancel a live Qwen stream/STOP
        // session that remains on the original authenticated HOME.
        if (_externalMode)
        {
            if (_nativeReturnPending && ExactShellReturn(e.Uri))
            {
                RevokeDocument();
                return;
            }
            // Recheck EVERY redirect; no DNS suffix spoof, insecure scheme or port.
            if (!IsApprovedExternal(e.Uri))
            {
                e.Cancel = true;
                return;
            }
            RevokeDocument();
            return;
        }
        if (!Trusted(e.Uri))
        {
            e.Cancel = true;
            return;
        }
        RevokeDocument();
    }
    private void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        // A failed/redirected Back must allow native retry, NEVER unlock IPC.
        // The original HOME's ContentLoading alone restores local mode.
        if (_externalMode && _nativeReturnPending &&
            (!e.IsSuccess || !ExactShellReturn(_web.Source)))
            _nativeReturnPending = false;
    }
    private void OnNewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        // window.open / target=_blank must never bypass exact-host navigation.
        e.Handled = true;
    }

    private void OnSourceChanged(object? sender, CoreWebView2SourceChangedEventArgs e)
        => RevokeDocument();
    private void OnContentLoading(object? sender, CoreWebView2ContentLoadingEventArgs e)
    {
        if (_nativeReturnPending && ExactShellReturn(_web.Source))
        {
            _externalMode = false;
            _nativeReturnPending = false;
            _externalHost = null;
        }
        if (_rendererAwaitingTrustedContent && _rendererReloadInitiated &&
            !_browserProcessLost && !_externalMode && !_nativeReturnPending &&
            ExactShellReturn(_web.Source))
        {
            _rendererAwaitingTrustedContent = false;
            _rendererReloadInitiated = false;
        }
        RevokeDocument();
    }
    // Telemetry is read only. Never send WebView process paths, command lines,
    // profile directories, or crash-report contents to the shell log.
    private static string SafeFailureModule(string? fullPath)
    {
        if (string.IsNullOrWhiteSpace(fullPath)) return "none";
        try {
            var leaf = System.IO.Path.GetFileName(fullPath.Replace('/', '\\'));
            return leaf.Length > 0 && leaf.Length <= 96 &&
                Regex.IsMatch(leaf, @"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\z",
                              RegexOptions.CultureInvariant) ? leaf : "none";
        } catch (Exception) { return "none"; }
    }

    private static string FormatWebViewProcessFailure(CoreWebView2ProcessFailedEventArgs e)
    {
        // Some pinned SDK versions do not expose FailureSourceModulePath.
        // Its absence is UNKNOWN, not proof that no DLL failed Code Integrity.
        string? modulePath = null;
        try { modulePath = e.GetType().GetProperty("FailureSourceModulePath")?
            .GetValue(e) as string; }
        catch (Exception) { /* Optional metadata is not an admission gate. */ }
        var code = e.ExitCode;
        return "WEBVIEW_PROCESS_FAILED " + e.ProcessFailedKind.ToString() +
            " reason=" + e.Reason.ToString() +
            " exit=" + code.ToString(System.Globalization.CultureInfo.InvariantCulture) +
            " hex=0x" + unchecked((uint)code).ToString("X8",
                System.Globalization.CultureInfo.InvariantCulture) +
            " module=" + SafeFailureModule(modulePath);
    }

    private void OnProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs e)
    {
        RevokeDocument();
        try { _writeDiagnostic(FormatWebViewProcessFailure(e)); }
        catch (Exception) { /* Diagnostics must never interrupt the process-failure fence. */ }
        if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited)
        {
            _browserProcessLost = true;
            _rendererAwaitingTrustedContent = true;
            _rendererReloadInitiated = false;
            // BrowserProcessExited closes THIS CoreWebView2. Notify the original
            // WPF owner to revoke its Python pipe and consent, never Reload a
            // closed Core or create a second UI/backend from the bridge.
            try { _onBrowserProcessExited?.Invoke(_web); }
            catch (Exception) { /* fail closed: _browserProcessLost remains set */ }
            return;
        }
        if (e.ProcessFailedKind != CoreWebView2ProcessFailedKind.RenderProcessExited)
            return;
        _rendererAwaitingTrustedContent = true;
        _rendererReloadInitiated = false;
        try
        {
            if (Volatile.Read(ref _disposed) != 0 || _lifetime.IsCancellationRequested ||
                _browserProcessLost || _externalMode || _nativeReturnPending ||
                !NativeSidMatches() || !ExactShellReturn(_web.Source) ||
                Interlocked.CompareExchange(ref _rendererReloadAttempts, 1, 0) != 0)
                return;
            _rendererReloadInitiated = true;
            _web.Reload();
        }
        catch (Exception) { _rendererReloadInitiated = false; }
    }

    private bool IsCurrent(string source, long epoch) =>
        Volatile.Read(ref _disposed) == 0 && !_externalMode && !_browserProcessLost &&
        !_rendererAwaitingTrustedContent && !_lifetime.IsCancellationRequested &&
        Interlocked.Read(ref _epoch) == epoch && ExactShellReturn(source) && ExactShellReturn(_web.Source) &&
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


    // A transport ACK with an explicit native rejection is NOT a completed
    // model, training, permission or STOP action. The owner remains authoritative.
    // Native result may reject LEARN/SETTINGS after transport-level Accepted.
    // Never present a denied owner, provider, SID, ACL or consent result as done.
    private static bool NativeOwnerStatusDenied(string? status)
    {
        if (string.IsNullOrWhiteSpace(status)) return true;
        // Normalize space/hyphen-delimited native denials before ACK classification.
        var value = Regex.Replace(status.Trim(), @"[\s-]+", "_").ToUpperInvariant();
        if (value is "HOLD" or "DENIED" or "ERROR" or "FAILED" or "REJECTED" or "CANCELLED" or
            "OFFLINE" or "UNAVAILABLE" or "NOT_READY" or "AWAITING_CONSENT" or
            "NEEDS_CONSENT" or "CONSENT_PENDING" or "NOT_AUTHORIZED" or
            "NOT_AUTHENTICATED" or "FORBIDDEN" or
            "BLOCKED" or "REFUSED" or "REVOKED" or "ABORTED" or
            "EXPIRED" or "STOPPED" or "BUSY" or "PENDING" or
             "UNAUTHORIZED" or "NO_CONSENT" or "INVALID" or "STALE" or
             "NOT_INSTALLED" or "TIMED_OUT" or "RIGHTS_MISSING" or
             "ACTION_DISALLOWED") return true;
        return value.EndsWith("_HOLD", StringComparison.Ordinal) ||
               value.EndsWith("_DENIED", StringComparison.Ordinal) ||
               value.EndsWith("_REJECTED", StringComparison.Ordinal) ||
               value.EndsWith("_FAILED", StringComparison.Ordinal) ||
               value.EndsWith("_ERROR", StringComparison.Ordinal) ||
               value.EndsWith("_REQUIRED", StringComparison.Ordinal) ||
               value.EndsWith("_MISMATCH", StringComparison.Ordinal) ||
               value.EndsWith("_UNAVAILABLE", StringComparison.Ordinal) ||
               value.EndsWith("_OFFLINE", StringComparison.Ordinal) ||
               value.StartsWith("NOT_AUTHORIZED", StringComparison.Ordinal) ||
               value.StartsWith("NOT_AUTHENTICATED", StringComparison.Ordinal) ||
               value.EndsWith("_BLOCKED", StringComparison.Ordinal) ||
               value.EndsWith("_REFUSED", StringComparison.Ordinal) ||
               value.EndsWith("_REVOKED", StringComparison.Ordinal) ||
               value.EndsWith("_ABORTED", StringComparison.Ordinal) ||
               value.EndsWith("_EXPIRED", StringComparison.Ordinal) ||
               value.EndsWith("_STOPPED", StringComparison.Ordinal) ||
               value.EndsWith("_CANCELLED", StringComparison.Ordinal) ||
                value.EndsWith("_BUSY", StringComparison.Ordinal) ||
                value.EndsWith("_PENDING", StringComparison.Ordinal) ||
               value.EndsWith("_UNAUTHORIZED", StringComparison.Ordinal) ||
               value.EndsWith("_NO_CONSENT", StringComparison.Ordinal) ||
               value.EndsWith("_INVALID", StringComparison.Ordinal) ||
               value.EndsWith("_STALE", StringComparison.Ordinal) ||
               value.EndsWith("_NOT_INSTALLED", StringComparison.Ordinal) ||
               value.EndsWith("_TIMED_OUT", StringComparison.Ordinal) ||
               value.EndsWith("_RIGHTS_MISSING", StringComparison.Ordinal) ||
               value.EndsWith("_ACTION_DISALLOWED", StringComparison.Ordinal);
    }

    // Original transport and original native owner must BOTH agree on success.
    private static bool NativeResultExplicitlyDenied(JsonElement? candidate, int depth = 0)
    {
        if (candidate is not JsonElement result) return false;
        // A transport ACK cannot hide a denied nested receipt in an array.
        // Preserve normal arrays while bounding provenance parsing fail-closed.
        if (depth >= 4)
            return result.ValueKind switch {
                JsonValueKind.True => false,
                JsonValueKind.String => NativeOwnerStatusDenied(result.GetString()),
                _ => true // At recursion limit malformed owner proof cannot authorize.
            };
        if (result.ValueKind == JsonValueKind.Array)
        {
            if (result.GetArrayLength() > 128) return true;
            foreach (var child in result.EnumerateArray())
                if (NativeResultExplicitlyDenied(child, depth + 1)) return true;
            return false;
        }
        // A transport ACK may carry a scalar native refusal instead of an object.
        // Never promote "HOLD", "DENIED" or JSON false to a completed owner action.
        if (result.ValueKind == JsonValueKind.String)
            return NativeOwnerStatusDenied(result.GetString());
        if (result.ValueKind == JsonValueKind.False) return true;
        // Missing or numeric native owner proof is not a successful operation.
        // This also holds within nested owner/result arrays or objects.
        if (result.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined or JsonValueKind.Number) return true;
        if (result.ValueKind != JsonValueKind.Object) return false;
        foreach (var field in result.EnumerateObject())
        {
            if (field.Name is "ok" or "ack" or "accepted" or "success" or "approved" or "authorized" or "consented" or "ownerConsent" or "nativeConsent" or "permissionGranted" &&
                field.Value.ValueKind != JsonValueKind.True)
                return true;
            if (field.Name is "error" or "errorCode" or "error_code" or
                "errorMessage" or "error_message")
            {
                if (field.Value.ValueKind != JsonValueKind.Null &&
                    (field.Value.ValueKind != JsonValueKind.String ||
                     !string.IsNullOrWhiteSpace(field.Value.GetString())))
                    return true;
            }
            if (field.Name is "status" or "state")
            {
                if (field.Value.ValueKind != JsonValueKind.String ||
                    NativeOwnerStatusDenied(field.Value.GetString()))
                    return true;
            }
            if (field.Name is "result" or "receipt" or "ownerReceipt" or "nativeResult" or "owner" or "ownerResult" or "owner_receipt" or "owner_result" or "native_result" &&
                NativeResultExplicitlyDenied(field.Value, depth + 1))
                return true;
        }
        return false;
    }

    // SETTINGS is an owner-only HKCU operation: the receipt must prove the
    // requested read/write mode and (for writes) the persisted requested bit.
    // A generic transport Accepted=true or an empty object is not proof.
    private static bool NativeAutostartReceiptMatches(JsonElement payload, JsonElement? candidate)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            candidate is not JsonElement receipt || receipt.ValueKind != JsonValueKind.Object)
            return false;
        var requested = payload.EnumerateObject().ToArray();
        if (requested.Length > 1 ||
            (requested.Length == 1 &&
             (requested[0].Name != "enabled" ||
              requested[0].Value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))))
            return false;
        var fields = receipt.EnumerateObject().ToArray();
        if (fields.Length != 2 ||
            fields.Select(f => f.Name).Distinct(StringComparer.Ordinal).Count() != 2 ||
            !receipt.TryGetProperty("enabled", out var actual) ||
            !receipt.TryGetProperty("readOnly", out var readOnly) ||
            actual.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
            readOnly.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            return false;
        if (requested.Length == 0) return readOnly.GetBoolean();
        return !readOnly.GetBoolean() &&
            requested[0].Value.GetBoolean() == actual.GetBoolean();
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (Volatile.Read(ref _disposed) != 0 || _externalMode || _browserProcessLost ||
            _rendererAwaitingTrustedContent || !ExactShellReturn(e.Source) || !ExactShellReturn(_web.Source))
            return;
        var source = e.Source;
        var epoch = Interlocked.Read(ref _epoch);
        var cancel = _document.Token;
        string id = "", route = "";
        // Successful native STOP revokes pending consent and late transport errors.
        long chatErrorEpoch = -1;
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
            if (route is "helion.chat" or "core.chat" or "persona.chat")
                chatErrorEpoch = Interlocked.Read(ref _streamEpoch);
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
            // SETTINGS HKCU is exclusively a Windows/WPF owner operation.
            // Never let an absent native delegate fall through to Python IPC.
            // Reject before prompting consent to a missing owner handler.
            if (route == "system.autostart" && _nativeOwnerAction is null)
            {
                Reply(source, epoch, id, route, "HOLD", "NOX_AUTOSTART_NATIVE_OWNER_REQUIRED");
                return;
            }
            // A previously authorized queued-model STOP must overtake
            // transfers just like chat.stop. SID/ACL and bounded jobId remain
            // enforced by this bridge and by the native P03 owner.
            // A cancellation request is never delayed by the WPF approval
            // dialog for starting work. This exact MENU STOP still requires
            // both its own route ACL and chat.stop ACL in the original owner.
            var isMenuStop = route == "menu.binding" &&
                payload.EnumerateObject().Count() == 1 &&
                payload.TryGetProperty("action", out var menuAction) &&
                menuAction.ValueKind == JsonValueKind.String &&
                menuAction.GetString() == "stop";
            if (route is not ("chat.stop" or "models.cancel") &&
                !isMenuStop &&
                !await _nativeConsent(route, payload.Clone(), cancel))
            {
                Reply(source, epoch, id, route, "HOLD", "NATIVE_CONSENT_DENIED");
                return;
            }
            if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                !_nativeAcl(_ownerWindowsSid, route) ||
                (chatErrorEpoch >= 0 && Interlocked.Read(ref _streamEpoch) != chatErrorEpoch)) return;
            if (route == "browser.open") {
                if (_nativeOwnerAction is null) {
                    Reply(source, epoch, id, route, "HOLD", "BROWSER_NATIVE_OWNER_UNAVAILABLE");
                    return;
                }
                // Only the original native owner can start a browser session.
                // Navigation revokes the source document; do not send false
                // COMPLETED after the page becomes untrusted.
                var navigation = await _nativeOwnerAction(route, payload.Clone(), cancel);
                // A transport-level Accepted=true cannot override the native
                // browser owner's refused, malformed or absent navigation proof.
                // Navigation itself revokes this page; never post a success ACK
                // or re-enable WebView2 IPC after an external document opens.
                var navigationConfirmed = navigation.Accepted &&
                    string.IsNullOrEmpty(navigation.ErrorCode) &&
                    navigation.Result is JsonElement navReceipt &&
                    navReceipt.ValueKind == JsonValueKind.Object &&
                    navReceipt.EnumerateObject().Count() == 1 &&
                    navReceipt.TryGetProperty("status", out var navState) &&
                    navState.ValueKind == JsonValueKind.String &&
                    navState.GetString() == "NAVIGATION_REQUESTED" &&
                    !NativeResultExplicitlyDenied(navigation.Result);
                if (!navigationConfirmed && IsCurrent(source, epoch))
                    Reply(source, epoch, id, route, "HOLD", navigation.ErrorCode ?? "BROWSER_NATIVE_ACK_HOLD");
                return;
            }
            // P03's existing C# queue stays in this WPF host; it must not be
            // replaced by a Python downloader or sent through a second IPC.
            if (_nativeOwnerAction is not null &&
                (route.StartsWith("models.", StringComparison.Ordinal) ||
                 route=="chat.stop" ||
                 route=="system.autostart" ||
                 route=="browser.navidle" || route=="menu.dispatch" ||
                 route=="menu.binding" || route=="selfwrite.ack" ||
                 route=="selflearn.ack" ||
                 route=="chat.commands" && payload.TryGetProperty("action",out var command) &&
                 command.ValueKind==JsonValueKind.String && command.GetString() is string ownerCommand &&
                 (ownerCommand=="training.import" || ownerCommand=="selfbuilder.a1.boot" ||
                  ownerCommand=="selfbuilder.a1.tick")))
            {
                var ownerResult = await _nativeOwnerAction(route, payload.Clone(), cancel);
                if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                    !_nativeAcl(_ownerWindowsSid, route)) return;
                // Stop revokes live chat frames only on affirmative native owner ACK.
                // A denied STOP must not silence a still-active generator in the UI.
                var ownerAccepted = ownerResult.Accepted &&
                    string.IsNullOrEmpty(ownerResult.ErrorCode) &&
                    ownerResult.Result is JsonElement ownerReceipt &&
                    ownerReceipt.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null);
                if (ownerAccepted && NativeResultExplicitlyDenied(ownerResult.Result))
                    ownerAccepted = false;
                // Do not promote a malformed or mismatched SETTINGS receipt to
                // COMPLETED even if the WPF transport accepted the operation.
                if (ownerAccepted && route == "system.autostart" &&
                    !NativeAutostartReceiptMatches(payload, ownerResult.Result))
                    ownerAccepted = false;
                if ((route == "chat.stop" || isMenuStop) && ownerAccepted)
                    Interlocked.Increment(ref _streamEpoch);
                // Owner ACK means a durable job was accepted, NOT that the
                // entire model has been downloaded, imported or installed.
                // Never claim cancellation when the owner reports false.
                var ownerState = ownerAccepted ? "COMPLETED" : "HOLD";
                if (route is "models.pull" or "models.retry" or "models.gguf.import")
                {
                    ownerState = "HOLD";
                    if (ownerAccepted && ownerResult.Result is JsonElement job &&
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
                    ownerState = ownerAccepted &&
                        ownerResult.Result is JsonElement cancelled &&
                        cancelled.ValueKind == JsonValueKind.Object &&
                        cancelled.TryGetProperty("cancelled", out var flag) &&
                        flag.ValueKind == JsonValueKind.True ? "STOP_REQUESTED" : "HOLD";
                }
                else if (route == "chat.stop" || isMenuStop)
                    ownerState = ownerAccepted ? "STOP_REQUESTED" : "HOLD";
                Reply(source, epoch, id, route, ownerState,
                      ownerAccepted ? ownerResult.ErrorCode :
                      (ownerResult.ErrorCode ?? "NATIVE_OWNER_RESULT_HOLD"), ownerResult.Result);
                return;
            }
            // Track only actual model calls; native STOP may overtake the
            // blocking Python worker on navigation, reload or window teardown.
            var isChat = route is "helion.chat" or "core.chat" or "persona.chat";
            var streamEpoch = isChat ? chatErrorEpoch : Interlocked.Read(ref _streamEpoch);
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
                var accepted = result.Accepted &&
                    string.IsNullOrEmpty(result.ErrorCode) &&
                    result.Result is JsonElement nativeReceipt &&
                    nativeReceipt.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null);
                if (accepted && NativeResultExplicitlyDenied(result.Result))
                    accepted = false;
                if (route == "chat.stop" && accepted)
                    Interlocked.Increment(ref _streamEpoch);
                var state = !accepted ? "HOLD" :
                    route == "chat.stop" ? "STOP_REQUESTED" : "COMPLETED";
                Reply(source, epoch, id, route,
                      state, accepted ? result.ErrorCode :
                      (result.ErrorCode ?? "NATIVE_OWNER_RESULT_HOLD"), result.Result);
            }
            finally { if (isChat) Interlocked.Decrement(ref _activeChat); }
        }
        catch (OperationCanceledException) { /* Native STOP/window close: no stale ACK. */ }
        catch (NativePipeHold hold)
        {
            if (RequestId.IsMatch(id) &&
                (chatErrorEpoch < 0 || Interlocked.Read(ref _streamEpoch) == chatErrorEpoch))
                Reply(source, epoch, id, route, "HOLD", hold.Code);
        }
        catch (TimeoutException)
        {
            if (RequestId.IsMatch(id) &&
                (chatErrorEpoch < 0 || Interlocked.Read(ref _streamEpoch) == chatErrorEpoch))
                Reply(source, epoch, id, route, "HOLD", "NATIVE_CHAT_TIMEOUT");
        }
        catch (Exception)
        {
            if (id.Length == 32 && RequestId.IsMatch(id) &&
                (chatErrorEpoch < 0 || Interlocked.Read(ref _streamEpoch) == chatErrorEpoch))
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
        _web.NavigationCompleted -= OnNavigationCompleted;
        _web.NewWindowRequested -= OnNewWindowRequested;
        _web.SourceChanged -= OnSourceChanged;
        _web.ContentLoading -= OnContentLoading;
        _web.ProcessFailed -= OnProcessFailed;
        _lifetime.Dispose();
        // Original WPF host owns and disposes NativePythonPipe/process exactly once.
    }
}
