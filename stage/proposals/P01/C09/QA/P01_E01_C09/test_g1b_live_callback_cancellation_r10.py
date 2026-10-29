"""G1-B R10: source-only regression for native callback-initiated cancellation.

These assertions inspect the existing C09 bridge, not compiled .NET or native
Windows WebView2 behavior. User cancellation must have a terminal UI status
while document-navigation and host-disposal cancellation never get stale ACK.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "Bridge" /
          "P01WebView2NavigationBridge.cs").read_text(encoding="utf-8")
MESSAGE = SOURCE.split("private async void OnWebMessageReceived", 1)[1].split(
    "private bool IsCurrent(", 1)[0]
CATCH = MESSAGE.split("catch (OperationCanceledException)", 1)[1].split(
    "catch (Exception)", 1)[0]


class G1BLiveCallbackCancellationR10(unittest.TestCase):
    def test_native_consent_stage_is_set_before_await(self):
        self.assertLess(MESSAGE.index("awaitingNativeConsent = true;"),
                        MESSAGE.index("await _confirmNativeConsent(routeId, requestLifetime.Token)"))
        self.assertLess(MESSAGE.index("await _confirmNativeConsent(routeId, requestLifetime.Token)"),
                        MESSAGE.index("awaitingNativeConsent = false;"))

    def test_normal_denial_still_reports_rejected(self):
        self.assertIn('if (!consentGranted)', MESSAGE)
        self.assertIn('"REJECTED", "P01_NATIVE_CONSENT_DENIED"', MESSAGE)

    def test_callback_initiated_consent_cancel_reports_rejected(self):
        self.assertIn('awaitingNativeConsent ? "REJECTED" : "HOLD"', CATCH)
        self.assertIn('"P01_NATIVE_CONSENT_CANCELLED"', CATCH)

    def test_callback_initiated_native_cancel_reports_hold(self):
        self.assertIn('"P01_NATIVE_OPERATION_CANCELLED"', CATCH)
        self.assertIn("ReplyIfCurrent(documentSource, documentEpoch", CATCH)

    def test_host_navigation_cancel_must_not_emit_stale_response(self):
        self.assertIn("requestLifetime is not null && !requestLifetime.IsCancellationRequested", CATCH)
        self.assertIn("if (!IsCurrent(documentSource, documentEpoch)", SOURCE)
        self.assertIn("AdvanceDocumentEpoch(newDocument: false);", SOURCE)
        self.assertIn("source.Cancel();", SOURCE)

    def test_native_route_ack_not_inferred_from_task_completion(self):
        self.assertIn("var accepted = await _invokeExistingNativeRoute(routeId, requestLifetime.Token);", MESSAGE)
        self.assertIn('accepted ? "COMPLETED" : "HOLD"', MESSAGE)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', SOURCE)

    def test_replay_limits_origin_popup_and_errors_preserved(self):
        self.assertIn("_seenRequestIds.Contains(requestId)", MESSAGE)
        self.assertIn("MaxPendingNativeRequests = 8", SOURCE)
        self.assertIn("MaxRequestsPerDocument = 1024", SOURCE)
        self.assertIn("args.Cancel = true;", SOURCE)
        self.assertIn("args.Handled = true;", SOURCE)
        self.assertIn('"P01_NATIVE_BRIDGE_ERROR"', MESSAGE)

    def test_one_existing_webview2_host_only(self):
        for forbidden in ("new WebView2(", "new CoreWebView2(", "Process.Start",
                          "HttpListener", "NewWindow ="):
            self.assertNotIn(forbidden, SOURCE)
        for literal in ('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"',
                        "_webView.ProcessFailed += OnProcessFailed;",
                        "_webView.NewWindowRequested -= OnNewWindowRequested;"):
            self.assertIn(literal, SOURCE)


if __name__ == "__main__":
    unittest.main()
