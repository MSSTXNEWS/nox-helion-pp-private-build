"""G1-B R06: WebView2 native admission/backpressure SOURCE guard (not Windows acceptance)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = SOURCE.read_text(encoding="utf-8")
HANDLER = TEXT.split("private async void OnWebMessageReceived", 1)[1].split(
    "private bool IsCurrent", 1
)[0]


class G1BWebView2AdmissionLimitsR06(unittest.TestCase):
    def test_pending_native_work_is_independently_bounded(self):
        self.assertIn("private const int MaxPendingNativeRequests = 8;", TEXT)
        self.assertIn("private const int MaxRequestsPerDocument = 1024;", TEXT)
        self.assertIn("if (_pending.Count >= MaxPendingNativeRequests)", HANDLER)

    def test_replay_is_suppressed_before_quota_error(self):
        self.assertLess(
            HANDLER.index("if (_seenRequestIds.Contains(requestId)) return;"),
            HANDLER.index("if (_seenRequestIds.Count >= MaxRequestsPerDocument)"),
        )
        self.assertLess(
            HANDLER.index("if (_seenRequestIds.Count >= MaxRequestsPerDocument)"),
            HANDLER.index("if (_pending.Count >= MaxPendingNativeRequests)"),
        )

    def test_native_busy_is_fail_closed_without_consuming_request_id(self):
        busy_start = HANDLER.index("if (_pending.Count >= MaxPendingNativeRequests)")
        reserve_at = HANDLER.index("if (!_seenRequestIds.Add(requestId)) return;")
        busy = HANDLER[busy_start:reserve_at]
        self.assertIn('"HOLD", "P01_NATIVE_BUSY"', busy)
        self.assertIn("return;", busy)
        self.assertNotIn("_seenRequestIds.Add(", busy)
        self.assertNotIn("_invokeExistingNativeRoute(", busy)
        self.assertNotIn("_confirmNativeConsent(", busy)

    def test_busy_gate_precedes_native_lease_creation(self):
        self.assertLess(
            HANDLER.index("if (_pending.Count >= MaxPendingNativeRequests)"),
            HANDLER.index("CancellationTokenSource.CreateLinkedTokenSource("),
        )
        self.assertLess(
            HANDLER.index("if (!_seenRequestIds.Add(requestId)) return;"),
            HANDLER.index("_pending.TryAdd((documentEpoch, requestId), requestLifetime)"),
        )

    def test_home_menu_core_and_native_ack_are_preserved(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', TEXT)
        self.assertIn("IsTrustedSource(args.Source)", HANDLER)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", HANDLER)
        self.assertIn('accepted ? "COMPLETED" : "HOLD"', HANDLER)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', TEXT)

    def test_action_consent_cannot_be_authorized_by_web_message(self):
        self.assertIn('if (kind == "action")', HANDLER)
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", HANDLER)
        self.assertIn("P01_NATIVE_CONSENT_DENIED", HANDLER)
        self.assertNotIn('TryString(root, "approved"', HANDLER)

    def test_navigation_and_process_failure_revoke_pending(self):
        self.assertIn("_webView.NavigationStarting += OnNavigationStarting;", TEXT)
        self.assertIn("_webView.ProcessFailed += OnProcessFailed;", TEXT)
        epoch = TEXT.split("private void AdvanceDocumentEpoch", 1)[1].split(
            "private async void OnWebMessageReceived", 1
        )[0]
        self.assertIn("source.Cancel();", epoch)
        self.assertLess(epoch.index("_pending.Clear();"), epoch.index("source.Cancel();"))
        self.assertIn("if (newDocument) _seenRequestIds.Clear();", epoch)

    def test_source_guard_has_no_stale_r01_delegate_contracts(self):
        guard = (ROOT / "QA" / "P01_E01_C09" /
                 "test_webview2_bridge_source.py").read_text(encoding="utf-8")
        self.assertIn("_invokeExistingNativeRoute(routeId, requestLifetime.Token)", guard)
        self.assertIn("_confirmNativeConsent(routeId, requestLifetime.Token)", guard)
        self.assertIn("_pending.TryAdd((documentEpoch, requestId), requestLifetime)", guard)
        self.assertNotIn("_invokeExistingNativeRoute(routeId, _lifetime.Token)", guard)
        self.assertNotIn("_confirmNativeConsent(routeId, _lifetime.Token)", guard)

    def test_no_second_host_or_install_build_logic(self):
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)
        self.assertNotIn("Process.Start", TEXT)


if __name__ == "__main__":
    unittest.main()
