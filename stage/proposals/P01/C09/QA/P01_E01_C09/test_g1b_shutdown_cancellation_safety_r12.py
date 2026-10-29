"""G1-B R12: structural regression for exception-safe existing WebView2 host shutdown.

This source-only test does NOT prove compiled WPF, native consent, or Windows
WebView2 behavior. Run from the checked-out loader repository.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "Bridge" /
          "P01WebView2NavigationBridge.cs").read_text(encoding="utf-8")
DISPOSE = SOURCE.split("public void Dispose()", 1)[1]


class G1BShutdownCancellationSafetyR12(unittest.TestCase):
    def test_lifetime_cancel_is_inside_try(self):
        self.assertRegex(DISPOSE, r"try\s*\{\s*_lifetime\.Cancel\(\);")

    def test_third_party_callback_exception_is_contained(self):
        self.assertIn("catch (AggregateException)", DISPOSE)
        self.assertLess(DISPOSE.index("_lifetime.Cancel();"),
                        DISPOSE.index("catch (AggregateException)"))

    def test_cleanup_is_finally_guarded(self):
        finally_code = DISPOSE.split("finally", 1)[1]
        for statement in ("_lifetime.Dispose();", "_pending.Clear();",
                          "_seenRequestIds.Clear();"):
            self.assertIn(statement, finally_code)

    def test_disposed_gate_precedes_cancellation(self):
        self.assertLess(DISPOSE.index("Interlocked.Exchange(ref _disposed, 1)"),
                        DISPOSE.index("_lifetime.Cancel();"))

    def test_original_six_event_handlers_detach_first(self):
        for event in ("WebMessageReceived", "NavigationStarting",
                      "NewWindowRequested", "SourceChanged",
                      "ContentLoading", "ProcessFailed"):
            unsubscribe = f"_webView.{event} -= On{event};"
            self.assertIn(unsubscribe, DISPOSE)
            self.assertLess(DISPOSE.index(unsubscribe),
                            DISPOSE.index("_lifetime.Cancel();"))

    def test_document_revocation_also_contains_callback_exceptions(self):
        revoke = SOURCE.split("private void AdvanceDocumentEpoch", 1)[1].split(
            "private async void OnWebMessageReceived", 1)[0]
        self.assertIn("source.Cancel();", revoke)
        self.assertIn("catch (Exception)", revoke)
        self.assertIn("_pending.Clear();", revoke)

    def test_home_menu_core_remain_real_route_ids(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', SOURCE)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", SOURCE)

    def test_action_requires_current_native_consent(self):
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", SOURCE)
        self.assertIn('"P01_NATIVE_CONSENT_DENIED"', SOURCE)
        self.assertIn('"P01_NATIVE_CONSENT_CANCELLED"', SOURCE)

    def test_navigation_and_windows_origin_guards_survive(self):
        self.assertIn("IsTrustedSource(args.Source)", SOURCE)
        self.assertIn("args.Cancel = true;", SOURCE)
        self.assertIn("args.Handled = true;", SOURCE)
        self.assertIn("P01_TRUSTED_WEBVIEW2_VIRTUAL_ORIGIN_REQUIRED", SOURCE)

    def test_native_ack_error_and_busy_limits_survive(self):
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', SOURCE)
        self.assertIn('"P01_NATIVE_BRIDGE_ERROR"', SOURCE)
        self.assertIn("MaxPendingNativeRequests = 8", SOURCE)

    def test_no_second_webview_or_server(self):
        for forbidden in ("new WebView2(", "new CoreWebView2(",
                          "HttpListener", "Process.Start", "NewWindow ="):
            self.assertNotIn(forbidden, SOURCE)


if __name__ == "__main__":
    unittest.main()
