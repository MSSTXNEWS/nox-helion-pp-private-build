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
    // Pending keys include the page epoch; a new document may reuse its own IDs.
    private readonly HashSet<(long Epoch, string Id)> _pending = new();
    // Completed IDs are also remembered: replay after native ACK must not run twice.
    private readonly HashSet<string> _seenRequestIds = new(StringComparer.Ordinal);
    private const int MaxRequestsPerDocument = 1024;
    private long _documentEpoch;
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
        _webView.SourceChanged += OnSourceChanged;
        _webView.WebMessageReceived += OnWebMessageReceived;
    }

    private static bool IsReservedVirtualHost(string host) =>
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
    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs args)
        => AdvanceDocumentEpoch();

    private void OnSourceChanged(object? sender, CoreWebView2SourceChangedEventArgs args)
        => AdvanceDocumentEpoch();

    private void AdvanceDocumentEpoch()
    {
        if (Volatile.Read(ref _disposed) != 0) return;
        Interlocked.Increment(ref _documentEpoch);
        _seenRequestIds.Clear();
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (Volatile.Read(ref _disposed) != 0 || !IsTrustedSource(args.Source)) return;
        // Bind this request to the exact source document, not a later same-origin navigation.
        var documentSource = args.Source;
        var documentEpoch = Interlocked.Read(ref _documentEpoch);
        string requestId = "";
        string routeId = "";
        bool reserved = false;
        try
        {
            var raw = args.WebMessageAsJson;
            if (raw.Length > 2048) return;
            using var json = JsonDocument.Parse(raw, new JsonDocumentOptions { MaxDepth = 5 });
            var root = json.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !TryString(root, "kind", out var kind) ||
                !TryString(root, "routeId", out routeId) ||
                !TryString(root, "requestId", out requestId) ||
                !RouteId.IsMatch(routeId) || !RequestId.IsMatch(requestId) ||
                (kind != "navigate" && kind != "action") ||
                (kind == "navigate" && !IsNavigation(routeId)))
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "REJECTED", "P01_BAD_MESSAGE");
                return;
            }
            // A duplicate request ID must not race a false ACK against the first request.
            if (_seenRequestIds.Count >= MaxRequestsPerDocument)
            {
                ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_DOCUMENT_REQUEST_LIMIT");
                return;
            }
            if (!_seenRequestIds.Add(requestId)) return;
            if (!_pending.Add((documentEpoch, requestId))) return;
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
                if (!await _confirmNativeConsent(routeId, _lifetime.Token))
                {
                    ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "REJECTED", "P01_NATIVE_CONSENT_DENIED");
                    return;
                }
                // Consent dialogs can navigate the page or change native capabilities.
                if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            }
            if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            var accepted = await _invokeExistingNativeRoute(routeId, _lifetime.Token);
            if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;
            ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId,
                accepted ? "COMPLETED" : "HOLD", accepted ? "" : "P01_NATIVE_ACK_MISSING");
        }
        catch (OperationCanceledException) { /* disposed host: no stale acknowledgement */ }
        catch (Exception)
        {
            // No exception, file path or native stack is returned to untrusted page JS.
            ReplyIfCurrent(documentSource, documentEpoch, requestId, routeId, "HOLD", "P01_NATIVE_BRIDGE_ERROR");
        }
        finally
        {
            if (reserved) _pending.Remove((documentEpoch, requestId));
        }
    }

    private bool IsCurrent(string documentSource, long documentEpoch)
    {
        if (Volatile.Read(ref _disposed) != 0 || _lifetime.IsCancellationRequested) return false;
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
            _webView.SourceChanged -= OnSourceChanged;
        }
        catch (Exception) { /* native WebView2 may already be disposed */ }
        _lifetime.Cancel();
        _lifetime.Dispose();
        _pending.Clear();
        _seenRequestIds.Clear();
    }
}
