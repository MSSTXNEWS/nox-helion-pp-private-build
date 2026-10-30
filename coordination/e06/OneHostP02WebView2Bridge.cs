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
        "chat.history", "chat.rag", "chat.voice", "chat.stop", "calls.history"
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
    private readonly Func<string, CancellationToken, Task<bool>> _nativeConsent;
    private readonly HashSet<string> _usedIds = new(StringComparer.Ordinal);
    private readonly CancellationTokenSource _lifetime = new();
    private long _epoch;
    private int _activeChat;
    private int _stopPending;
    private int _disposed;

    // All values here come from the native host, NEVER from a WebMessage.
    internal OneHostP02WebView2Bridge(
        CoreWebView2 existingCore,
        Uri trustedMappedOrigin,
        NativePythonPipe existingHostOwnedPipe,
        string authenticatedWindowsSid,
        Func<string, string, bool> nativeAcl,
        Func<string, CancellationToken, Task<bool>> nativeConsent)
    {
        _web = existingCore ?? throw new ArgumentNullException(nameof(existingCore));
        _virtualOrigin = trustedMappedOrigin ?? throw new ArgumentNullException(nameof(trustedMappedOrigin));
        _existingPipe = existingHostOwnedPipe ?? throw new ArgumentNullException(nameof(existingHostOwnedPipe));
        _nativeAcl = nativeAcl ?? throw new ArgumentNullException(nameof(nativeAcl));
        _nativeConsent = nativeConsent ?? throw new ArgumentNullException(nameof(nativeConsent));
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
        Interlocked.Increment(ref _epoch);
        // Navigating away while a model is executing must request a real
        // owner STOP, not merely suppress its response in WebView2.
        if (Volatile.Read(ref _activeChat) != 0 &&
            Interlocked.CompareExchange(ref _stopPending, 1, 0) == 0)
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
            // STOP must overtake active chat without waiting for a consent dialog.
            if (route != "chat.stop" &&
                !await _nativeConsent(route, _lifetime.Token))
            {
                Reply(source, epoch, id, route, "HOLD", "NATIVE_CONSENT_DENIED");
                return;
            }
            if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                !_nativeAcl(_ownerWindowsSid, route)) return;
            // Track only actual model calls; native STOP may overtake the
            // blocking Python worker on navigation, reload or window teardown.
            var isChat = route is "helion.chat" or "core.chat" or "persona.chat";
            if (isChat) Interlocked.Increment(ref _activeChat);
            try
            {
                var result = await _existingPipe.RequestAsync(
                    route, payload.Clone(), route == "chat.stop"
                        ? TimeSpan.FromSeconds(10) : TimeSpan.FromSeconds(60),
                    _lifetime.Token);
                // Host still re-authorizes after the potentially blocking IPC call.
                if (!IsCurrent(source, epoch) || !NativeSidMatches() ||
                    !_nativeAcl(_ownerWindowsSid, route)) return;
                Reply(source, epoch, id, route,
                      result.Accepted ? "COMPLETED" : "HOLD", result.ErrorCode, result.Result);
            }
            finally { if (isChat) Interlocked.Decrement(ref _activeChat); }
        }
        catch (OperationCanceledException) { /* Native STOP/window close: no stale ACK. */ }
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
        _web.WebMessageReceived -= OnWebMessageReceived;
        _web.NavigationStarting -= OnNavigationStarting;
        _web.SourceChanged -= OnSourceChanged;
        _web.ContentLoading -= OnContentLoading;
        _web.ProcessFailed -= OnProcessFailed;
        _lifetime.Dispose();
        // Original WPF host owns and disposes NativePythonPipe/process exactly once.
    }
}
