"""P01 C09 isolated source guard. NOT a native C#/WPF/WebView2 runtime test."""
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = SOURCE.read_text(encoding="utf-8")

class WebView2BridgeSourceGuard(unittest.TestCase):
    def test_only_existing_webview2_host_is_used(self):
        self.assertIn("CoreWebView2 existingWebView", TEXT)
        self.assertIn("_webView.WebMessageReceived += OnWebMessageReceived", TEXT)
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)
        self.assertNotIn("Process.Start", TEXT)

    def test_real_home_menu_core_native_ack_not_visual_click(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', TEXT)
        self.assertIn("_invokeExistingNativeRoute(routeId, _lifetime.Token)", TEXT)
        self.assertIn('accepted ? "COMPLETED" : "HOLD"', TEXT)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', TEXT)

    def test_host_origin_and_document_epoch_are_checked(self):
        self.assertIn("IsTrustedSource(args.Source)", TEXT)
        self.assertIn("uri.Scheme == Uri.UriSchemeHttps", TEXT)
        self.assertIn("_trustedVirtualOrigin.Host", TEXT)
        self.assertIn("IsReservedVirtualHost", TEXT)
        self.assertIn("var current = _webView.Source;", TEXT)
        self.assertIn("string.Equals(current, documentSource", TEXT)
        self.assertIn("catch (Exception) { return false; /* WebView2 may be closing or disposed */ }", TEXT)
        self.assertIn("if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return", TEXT)

    def test_native_consent_cannot_be_supplied_by_page(self):
        self.assertIn('if (kind == "action")', TEXT)
        self.assertIn("await _confirmNativeConsent(routeId, _lifetime.Token)", TEXT)
        self.assertIn("P01_NATIVE_CONSENT_DENIED", TEXT)
        self.assertIn("_isNativeRouteAvailable(routeId)", TEXT)
        self.assertNotIn('TryString(root, "approved"', TEXT)
        self.assertNotIn('TryString(root, "command"', TEXT)

    def test_fail_closed_errors_no_native_exception_leak(self):
        self.assertIn("P01_NATIVE_BRIDGE_ERROR", TEXT)
        self.assertIn("P01_NATIVE_ROUTE_UNAVAILABLE", TEXT)
        self.assertIn("P01_BAD_MESSAGE", TEXT)
        self.assertIn("MaxDepth = 5", TEXT)
        self.assertIn("if (raw.Length > 2048) return", TEXT)
        self.assertNotIn("ex.Message", TEXT)
        self.assertNotIn("exc.ToString()", TEXT)

    def test_duplicate_ids_cancellation_and_detach(self):
        self.assertIn("if (!_pending.Add(requestId))", TEXT)
        self.assertIn("_pending.Remove((documentEpoch, requestId))", TEXT)
        self.assertIn("Interlocked.Exchange(ref _disposed, 1)", TEXT)
        self.assertIn("_webView.WebMessageReceived -= OnWebMessageReceived", TEXT)
        self.assertIn("_lifetime.Cancel()", TEXT)

if __name__ == "__main__":
    unittest.main()
