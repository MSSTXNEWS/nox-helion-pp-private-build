"""G1-B R08: source-only guard for WebView2 window.open/target=_blank.
No WebView2 process, WPF host, binary, browser, installer, CI or consent is run.
"""
from pathlib import Path
import re
import unittest

BRIDGE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
SOURCE = BRIDGE.read_text(encoding="utf-8")


class G1BWebView2SingleHostPopupR08(unittest.TestCase):
    def test_new_window_event_registered_once(self):
        self.assertEqual(
            SOURCE.count("_webView.NewWindowRequested += OnNewWindowRequested;"), 1
        )

    def test_unhandled_popups_cannot_use_default_webview2_window(self):
        match = re.search(
            r"private void OnNewWindowRequested\([^)]*\)\s*\{(?P<body>.*?)\n    \}",
            SOURCE, re.S
        )
        self.assertIsNotNone(match)
        self.assertIn("CoreWebView2NewWindowRequestedEventArgs args", match.group(0))
        no_comments = re.sub(r"//[^\n]*", "", match.group("body")).strip()
        self.assertEqual(no_comments, "args.Handled = true;")

    def test_popup_is_not_treated_as_top_level_navigation(self):
        handler = SOURCE.split("private void OnNewWindowRequested", 1)[1].split(
            "private void OnSourceChanged", 1
        )[0]
        self.assertNotIn("AdvanceDocumentEpoch(", handler)
        self.assertNotIn("args.Cancel =", handler)

    def test_detaches_popup_handler_on_dispose(self):
        self.assertEqual(
            SOURCE.count("_webView.NewWindowRequested -= OnNewWindowRequested;"), 1
        )
        dispose = SOURCE.split("public void Dispose()", 1)[1]
        self.assertLess(
            dispose.index("_webView.NewWindowRequested -= OnNewWindowRequested;"),
            dispose.index("_lifetime.Cancel();")
        )

    def test_existing_external_main_frame_navigation_remains_guarded(self):
        nav = SOURCE.split("private void OnNavigationStarting", 1)[1].split(
            "private void OnNewWindowRequested", 1
        )[0]
        self.assertIn("if (!IsTrustedSource(args.Uri))", nav)
        self.assertIn("args.Cancel = true;", nav)

    def test_home_menu_core_and_native_consent_unchanged(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', SOURCE)
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", SOURCE)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", SOURCE)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', SOURCE)

    def test_no_new_host_or_external_launcher_added(self):
        for forbidden in ("new WebView2(", "new CoreWebView2(",
                          "HttpListener", "Process.Start", "NewWindow ="):
            self.assertNotIn(forbidden, SOURCE)

    def test_existing_backpressure_replay_and_error_hold_still_present(self):
        self.assertIn("MaxPendingNativeRequests = 8", SOURCE)
        self.assertIn("_seenRequestIds.Contains(requestId)", SOURCE)
        self.assertIn("P01_NATIVE_BRIDGE_ERROR", SOURCE)
        self.assertIn("P01_NATIVE_BUSY", SOURCE)


if __name__ == "__main__":
    unittest.main()
