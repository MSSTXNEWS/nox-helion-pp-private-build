"""G1-B R04: WebView2 failure/lifecycle SOURCE ONLY, no native Windows test."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = SOURCE.read_text(encoding="utf-8")


class G1BWebView2ProcessFailureR04(unittest.TestCase):
    def test_existing_host_subscribes_and_detaches_process_failure(self):
        self.assertIn("_webView.ProcessFailed += OnProcessFailed;", TEXT)
        self.assertIn("_webView.ProcessFailed -= OnProcessFailed;", TEXT)
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)

    def test_process_failure_invalidates_pending_native_ack(self):
        start = TEXT.index("private void OnProcessFailed")
        end = TEXT.index("private void AdvanceDocumentEpoch", start)
        handler = TEXT[start:end]
        self.assertIn("CoreWebView2ProcessFailedEventArgs args", handler)
        self.assertIn("AdvanceDocumentEpoch(newDocument: false)", handler)
        self.assertNotIn("_seenRequestIds.Clear()", handler)

    def test_epoch_change_retires_old_pending_without_releasing_nonce(self):
        start = TEXT.index("private void AdvanceDocumentEpoch")
        end = TEXT.index("private async void OnWebMessageReceived", start)
        block = TEXT[start:end]
        self.assertIn("Interlocked.Increment(ref _documentEpoch)", block)
        self.assertIn("_pending.Clear();", block)
        self.assertIn("if (newDocument) _seenRequestIds.Clear();", block)
        self.assertNotIn("newDocument: true", block)

    def test_native_consent_and_ack_pinned_to_current_epoch(self):
        self.assertIn("IsTrustedSource(args.Source)", TEXT)
        self.assertIn("Interlocked.Read(ref _documentEpoch) == documentEpoch", TEXT)
        self.assertIn("await _confirmNativeConsent(routeId, _lifetime.Token)", TEXT)
        self.assertIn("if (!IsCurrent(documentSource, documentEpoch) || !_isNativeRouteAvailable(routeId)) return;", TEXT)
        self.assertIn("var accepted = await _invokeExistingNativeRoute(routeId, _lifetime.Token);", TEXT)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', TEXT)

    def test_routes_error_and_replay_remain_fail_closed(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', TEXT)
        self.assertIn("P01_NATIVE_BRIDGE_ERROR", TEXT)
        self.assertIn("P01_NATIVE_ACK_MISSING", TEXT)
        self.assertIn("if (!_seenRequestIds.Add(requestId)) return;", TEXT)


if __name__ == "__main__":
    unittest.main()
