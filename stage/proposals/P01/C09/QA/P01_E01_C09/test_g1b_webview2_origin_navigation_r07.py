"""G1-B R07: source-only regressions for WebView2 off-origin top-level navigation.

These assertions inspect the real C09 adapter, not a fake WebView2 runtime.
They do not assert native Windows consent, button behavior or release readiness.
"""
from pathlib import Path
import unittest

BRIDGE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = BRIDGE.read_text(encoding="utf-8")
NAV = TEXT.split("private void OnNavigationStarting", 1)[1].split(
    "private void OnSourceChanged", 1
)[0]


class G1BWebView2OriginNavigationR07(unittest.TestCase):
    def test_top_level_untrusted_navigation_is_cancelled(self):
        self.assertIn("CoreWebView2NavigationStartingEventArgs args", NAV)
        self.assertIn("if (!IsTrustedSource(args.Uri))", NAV)
        self.assertIn("args.Cancel = true;", NAV)

    def test_origin_guard_reuses_existing_mapped_https_host_gate(self):
        guard = TEXT.split("private bool IsTrustedSource(", 1)[1].split(
            "private static bool TryString", 1
        )[0]
        self.assertIn("Uri.UriSchemeHttps", guard)
        self.assertIn("_trustedVirtualOrigin.Port", guard)
        self.assertIn("_trustedVirtualOrigin.Host", guard)
        self.assertIn("uri.UserInfo.Length == 0", guard)
        self.assertIn("IsTrustedSource(args.Uri)", NAV)

    def test_cancel_does_not_leave_native_consent_attached_to_old_document(self):
        self.assertLess(
            NAV.index("AdvanceDocumentEpoch(newDocument: false);"),
            NAV.index("args.Cancel = true;"),
        )
        self.assertIn("_pending.Clear();", TEXT)
        self.assertIn("source.Cancel();", TEXT)
        self.assertIn("_seenRequestIds.Contains(requestId)", TEXT)

    def test_existing_home_menu_core_action_and_ack_remain(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', TEXT)
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", TEXT)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", TEXT)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', TEXT)

    def test_one_existing_host_with_registered_and_unregistered_navigation(self):
        self.assertIn("_webView.NavigationStarting += OnNavigationStarting;", TEXT)
        self.assertIn("_webView.NavigationStarting -= OnNavigationStarting;", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)


if __name__ == "__main__":
    unittest.main()
