// NOX FIN ZAGR V16 / P01 C09. Adapter for the EXISTING WPF WebView2 host.
// Source candidate: this is not a new MainWindow, web server or permission grant.
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace NoxP01;

internal sealed class P01WebView2NavigationBridge : IDisposable
{
    private static readonly Regex RouteId = new(@"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\z", RegexOptions.CultureInvariant);
    private static readonly Regex RequestId = new(@"\A[A-Za-z0-9_-]{1,64}\z", RegexOptions.CultureInvariant);
    private readonly CoreWebView2 _webView;
    private readonly Uri _trustedVirtualOrigin;
    private readonly Func<string, bool> _isNativeRouteAvailable;
    private readonly Func<string, CancellationToken, Task<bool>> _confirmNativeConsent;
    private readonly Func<string, CancellationToken, Task<bool>> _invokeExistingNativeRoute;
    // A pending native callback owns a token linked to the existing host lifetime.
    // Document transitions revoke cooperative native work before its next effect.
    private readonly Dictionary<(long Epoch, string Id), CancellationTokenSource> _pending = new();
    // Completed IDs are also remembered: replay after native ACK must not run twice.
    private readonly HashSet<string> _seenRequestIds = new(StringComparer.Ordinal);
    private const int MaxRequestsPerDocument = 1024;
    // Prevent a page from opening unbounded native dialogs or route callbacks.
    private const int MaxPendingNativeRequests = 8;
    private long _documentEpoch;
    // Cancelling a stale native token may synchronously re-enter WebView2.
    private int _epochRevocationDepth;
    private readonly CancellationTokenSource _lifetime = new();
    private int _disposed;

    // Call on the WPF UI thread after EnsureCoreWebView2Async, using the host's
    // already mapped virtual origin and existing route/consent callbacks.
    internal P01WebView2NavigationBridge(
        CoreWebView2 existingWebView,
        Uri trustedVirtualOrigin,
        Func<string, bool> isNativeRouteAvailable,
        Func<string, CancellationToken, Task<bool>> confirmNativeConsent,
        Func<string, CancellationToken, Task<bool>> invokeExistingNativeRoute)
    {
        _webView = existingWebView ?? throw new ArgumentNullException(nameof(existingWebView));
        _trustedVirtualOrigin = trustedVirtualOrigin ?? throw new ArgumentNullException(nameof(trustedVirtualOrigin));
        if (_trustedVirtualOrigin.Scheme != Uri.UriSchemeHttps || !_trustedVirtualOrigin.IsDefaultPort ||
            _trustedVirtualOrigin.UserInfo.Length != 0 || !IsReservedVirtualHost(_trustedVirtualOrigin.Host) ||
            _trustedVirtualOrigin.AbsolutePath != "/" || _trustedVirtualOrigin.Query.Length != 0 ||
            _trustedVirtualOrigin.Fragment.Length != 0)
            throw new ArgumentException("P01_TRUSTED_WEBVIEW2_VIRTUAL_ORIGIN_REQUIRED", nameof(trustedVirtualOrigin));
        _isNativeRouteAvailable = isNativeRouteAvailable ?? throw new ArgumentNullException(nameof(isNativeRouteAvailable));
        _confirmNativeConsent = confirmNativeConsent ?? throw new ArgumentNullException(nameof(confirmNativeConsent));
        _invokeExistingNativeRoute = invokeExistingNativeRoute ?? throw new ArgumentNullException(nameof(invokeExistingNativeRoute));
        _webView.NavigationStarting += OnNavigationStarting;
        _webView.NewWindowRequested += OnNewWindowRequested;
        _webView.SourceChanged += OnSourceChanged;
        _webView.ContentLoading += OnContentLoading;
        _webView.ProcessFailed += OnProcessFailed;
        _webView.WebMessageReceived += OnWebMessageReceived;
    }

    private static bool IsReservedVirtualHost(string host) =>
        // Reuse the EXISTING explicitly mapped NOX WebView2 virtual host.
        // Never accept arbitrary .local LAN names or external hosts.
        string.Equals(host, "nox.local", StringComparison.OrdinalIgnoreCase) ||
        host.EndsWith(".example", StringComparison.OrdinalIgnoreCase) ||
        host.EndsWith(".invalid", StringComparison.OrdinalIgnoreCase) ||
        host.EndsWith(".test", StringComparison.OrdinalIgnoreCase);

    private bool IsTrustedSource(string source)
    {
        if (!Uri.TryCreate(source, UriKind.Absolute, out var uri)) return false;
        return uri.Scheme == Uri.UriSchemeHttps && uri.UserInfo.Length == 0 &&
               uri.Port == _trustedVirtualOrigin.Port &&
               string.Equals(uri.Host, _trustedVirtualOrigin.Host, StringComparison.OrdinalIgnoreCase);
    }

    private static bool TryString(JsonElement root, string key, out string value)
    {
        value = "";
        if (!root.TryGetProperty(key, out var property) || property.ValueKind != JsonValueKind.String) return false;
        value = property.GetString() ?? "";
        return true;
    }

    private static bool IsNavigation(string routeId) =>
        routeId == "HOME" || routeId == "MENU" || routeId == "CORE";

    // A URL is NOT a document identity: reload, away-and-back and history updates
    // may restore identical URLs while an action is awaiting native consent.
    // Starting a navigation revokes any in-flight native ACK. The old page may
    // survive when the navigation is canceled, so its replay IDs stay reserved.
    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs args)
    {
        // WebView2 must stay on the pre-mapped local HTTPS virtual origin.
        // External documents belong to native host routing, never this bridge.
        // Revoke pending native work even when an unsafe navigation is cancelled.
        AdvanceDocumentEpoch(newDocument: false);
        if (!IsTrustedSource(args.Uri))
            args.Cancel = true;
    }

    // Fragment/history changes invalidate in-flight replies but do not create
    // a fresh document. Clearing replay IDs here would allow action replay.
    // NewWindowRequested is independent of NavigationStarting. Without a handler,
    // window.open() and target=_blank may create a popup outside the pinned origin
    // gate. This loader has ONE existing WPF WebView2 host: never supply NewWindow
    // or silently launch a browser. Approved external links belong to the owner host.
    private void OnNewWindowRequested(object? sender, CoreWebView2NewWindowRequestedEventArgs args)
    {
        args.Handled = true;
    }

    private void OnSourceChanged(object? sender, CoreWebView2SourceChangedEventArgs args)
        => AdvanceDocumentEpoch(newDocument: args.IsNewDocument);

    // Same-URL reloads can skip SourceChanged. ContentLoading is the document
    // boundary at which a new page may legitimately reuse request IDs.
    private void OnContentLoading(object? sender, CoreWebView2ContentLoadingEventArgs args)
        => AdvanceDocumentEpoch(newDocument: true);

    // WebView2 process failure may leave Source unchanged while native consent
    // or a route callback is awaiting. Fail closed: invalidate its document
    // epoch without releasing request IDs belonging to a surviving page.
    private void OnProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs args)
        => AdvanceDocumentEpoch(newDocument: false);

    private void AdvanceDocumentEpoch(bool newDocument)
    {
        if (Volatile.Read(ref _disposed) != 0) return;
        Interlocked.Increment(ref _epochRevocationDepth);
        try
        {
            Interlocked.Increment(ref _documentEpoch);
            // Clear before cancelling: callbacks may synchronously re-enter WPF.
            var stale = new List<CancellationTokenSource>(_pending.Values);
            _pending.Clear();
            foreach (var source in stale)
            {
                try { source.Cancel(); }
                catch (Exception) { /* third-party callbacks cannot revive stale authority */ }
            }
            if (newDocument) _seenRequestIds.Clear();
        }
        finally { Interlocked.Decrement(ref _epochRevocationDepth); }
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (Volatile.Read(ref _disposed) != 0 || Volatile.Read(ref _epochRevocationDepth) != 0 ||
            !IsTrustedSource(args.Source)) return;
        // Bind this request to the exact source document, not a later same-origin navigation.
        var documentSource = args.Source;
        var documentEpoch = Interlocked.Read(ref _documentEpoch);
        string requestId = "";
        string routeId = "";
        bool reserved = false;
        bool awaitingNativeConsent = false;
        CancellationTokenSource? requestLifetime = null;
        try
        {
            var raw = args.WebMessageAsJson;
            if (raw.Length > 2048) return;
            using var json = JsonDocument.Parse(raw, new JsonDocumentOptions { MaxDepth = 5 });
            var root = json.RootElement;
            // Extract requestId before validating other fields. A malformed replay
            // of a reserved ID must not emit REJECTED while its native operation
            // can still finish with COMPLETED; keep exactly one reply authority.
            if (root.ValueKind == JsonValueKind.Object)
            {
                // JSON permits repeated keys; different parsers may select different
                // command fields. Never authorize or ACK an ambiguous UI request.
                int requestIdKeys = 0;
                int kindKeys = 0;
                int routeIdKeys = 0;
                foreach (var property in root.EnumerateObject())
                {
                    if (property.NameEquals("requestId")) requestIdKeys++;
                    else if (property.NameEquals("kind")) kindKeys++;
                    else if (property.NameEquals("routeId")) routeIdKeys++;
                }
                // A duplicate requestId has no uniquely addressable reply channel.
                if (requestIdKeys > 1) return;
                TryString(root, "requestId", out requestId);
                if (RequestId.IsMatch(requestId) && _seenRequestIds.Contains(requestId)) return;
                // A unique, fresh requestId can receive a terminal schema rejection.
                // Neither malformed path reserves an ID or invokes native callbacks.
                if (kindKeys > 1 || routeIdKeys > 1)
                {
                    ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId,
                        "REJECTED", "P01_BAD_MESSAGE");
                    return;
                }
            }
            if (root.ValueKind != JsonValueKind.Object ||
                !TryString(root, "kind", out var kind) ||
                !TryString(root, "routeId", out routeId) ||
                !RouteId.IsMatch(routeId) || !RequestId.IsMatch(requestId) ||
                (kind != "navigate" && kind != "action") ||
                (kind == "navigate" && !IsNavigation(routeId)))
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "REJECTED", "P01_BAD_MESSAGE");
                return;
            }
            // A completed or in-flight request must never receive a contradictory HOLD
            // simply because the document quota was reached after its original ACK.
            if (_seenRequestIds.Count >= MaxRequestsPerDocument)
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_DOCUMENT_REQUEST_LIMIT");
                return;
            }
            // Bound concurrent native confirmations and callbacks. A busy request
            // is not reserved and can safely retry with the same request ID.
            if (_pending.Count >= MaxPendingNativeRequests)
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_NATIVE_BUSY");
                return;
            }
            if (!_seenRequestIds.Add(requestId)) return;
            requestLifetime = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            if (!_pending.TryAdd((documentEpoch, requestId), requestLifetime)) return;
            reserved = true;
            if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId))
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_NATIVE_ROUTE_UNAVAILABLE");
                return;
            }
            // Any non-navigation button action must receive NEW consent in native WPF.
            // Never accept JS-supplied approval, role, capability or executable arguments.
            if (kind == "action")
            {
                awaitingNativeConsent = true;
                var consentGranted = await _confirmNativeConsent(routeId, requestLifetime.Token);
                awaitingNativeConsent = false;
                if (!consentGranted)
                {
                    ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "REJECTED", "P01_NATIVE_CONSENT_DENIED");
                    return;
                }
                // Consent dialogs can navigate the page or change native capabilities.
                if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            }
            if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            var accepted = await _invokeExistingNativeRoute(routeId, requestLifetime.Token);
            if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId,
                accepted ? "COMPLETED" : "HOLD", accepted ? "" : "P01_NATIVE_ACK_MISSING");
        }
        catch (OperationCanceledException)
        {
            // A native callback may cancel its own task while the document stays
            // alive. Report that cancellation instead of leaving the UI waiting.
            // A revoked document/host token must never receive a stale reply.
            if (requestLifetime is not null && !requestLifetime.IsCancellationRequested)
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId,
                    awaitingNativeConsent ? "REJECTED" : "HOLD",
                    awaitingNativeConsent ? "P01_NATIVE_CONSENT_CANCELLED" : "P01_NATIVE_OPERATION_CANCELLED");
        }
        catch (Exception)
        {
            // No exception, file path or native stack is returned to untrusted page JS.
            ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_NATIVE_BRIDGE_ERROR");
        }
        finally
        {
            if (reserved) _pending.Remove((documentEpoch, requestId));
            requestLifetime?.Dispose();
        }
    }

    private bool IsCurrent(string documentSource, long documentEpoch)
    {
        if (Volatile.Read(ref _disposed) != 0 || Volatile.Read(ref _epochRevocationDepth) != 0 ||
            _lifetime.IsCancellationRequested) return false;
        try
        {
            var current = _webView.Source;
            return Interlocked.Read(ref _documentEpoch) == documentEpoch && IsTrustedSource(current) &&
                   string.Equals(current, documentSource, StringComparison.Ordinal);
        }
        catch (Exception) { return false; /* WebView2 may be closing or disposed */ }
    }

    private void ReplyIfCurrent(string documentSource, long documentEpoch, string requestId, string routeId, string status, string error)
    {
        if (!IsCurrent(documentSource, documentEpoch) || !RequestId.IsMatch(requestId)) return;
        try
        {
            _webView.PostWebMessageAsJson(JsonSerializer.Serialize(new
            {
                kind = "p01Result", requestId, routeId, status, error,
                nativeAcknowledged = status == "COMPLETED"
            }));
        }
        catch (Exception) { /* destroying/closing WebView2 must not crash WPF */ }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        try
        {
            _webView.WebMessageReceived -= OnWebMessageReceived;
            _webView.NavigationStarting -= OnNavigationStarting;
            _webView.NewWindowRequested -= OnNewWindowRequested;
            _webView.SourceChanged -= OnSourceChanged;
            _webView.ContentLoading -= OnContentLoading;
            _webView.ProcessFailed -= OnProcessFailed;
        }
        catch (Exception) { /* native WebView2 may already be disposed */ }
        // Linked native route callbacks may throw while Cancel invokes them.
        // The existing host is already closed to new messages; cleanup must
        // complete even when a third-party cancellation callback fails.
        try
        {
            _lifetime.Cancel();
        }
        catch (AggregateException)
        {
            // CancellationTokenSource.Cancel wraps callback failures.
            // Never allow that exception to tear down the WPF host shutdown.
        }
        finally
        {
            _lifetime.Dispose();
            _pending.Clear();
            _seenRequestIds.Clear();
        }
    }
}
