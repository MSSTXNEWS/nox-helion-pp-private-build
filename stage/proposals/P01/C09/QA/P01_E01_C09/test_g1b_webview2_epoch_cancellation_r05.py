"""G1-B R05: epoch-scoped cancellation SOURCE ONLY; native WPF/WebView2 remains HOLD."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = SOURCE.read_text(encoding="utf-8")


class G1BEpochCancellationR05(unittest.TestCase):
    def _part(self, start, end):
        return TEXT[TEXT.index(start):TEXT.index(end, TEXT.index(start))]

    def test_existing_webview_host_only(self):
        self.assertIn("_webView.WebMessageReceived += OnWebMessageReceived;", TEXT)
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)

    def test_pending_native_lease_is_scoped_to_epoch(self):
        self.assertIn("Dictionary<(long Epoch, string Id), CancellationTokenSource> _pending", TEXT)
        self.assertIn("CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token)", TEXT)
        self.assertIn("_pending.TryAdd((documentEpoch, requestId), requestLifetime)", TEXT)

    def test_epoch_revokes_pending_before_reentrant_callbacks(self):
        method = self._part("private void AdvanceDocumentEpoch", "private async void OnWebMessageReceived")
        self.assertIn("new List<CancellationTokenSource>(_pending.Values)", method)
        self.assertLess(method.index("_pending.Clear();"), method.index("source.Cancel();"))
        self.assertLess(method.index("Interlocked.Increment(ref _documentEpoch)"), method.index("_pending.Clear();"))
        self.assertIn("if (newDocument) _seenRequestIds.Clear();", method)

    def test_process_failure_and_navigation_revoke_epoch(self):
        self.assertIn("_webView.NavigationStarting += OnNavigationStarting;", TEXT)
        self.assertIn("_webView.SourceChanged += OnSourceChanged;", TEXT)
        self.assertIn("_webView.ContentLoading += OnContentLoading;", TEXT)
        self.assertIn("_webView.ProcessFailed += OnProcessFailed;", TEXT)
        self.assertIn("_webView.ProcessFailed -= OnProcessFailed;", TEXT)
        self.assertIn("AdvanceDocumentEpoch(newDocument: false)", TEXT)

    def test_consent_and_native_route_use_same_revocable_token(self):
        handler = self._part("private async void OnWebMessageReceived", "private bool IsCurrent")
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", handler)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", handler)
        self.assertNotIn("await _confirmNativeConsent(routeId, _lifetime.Token)", handler)
        self.assertNotIn("await _invokeExistingNativeRoute(routeId, _lifetime.Token)", handler)
        self.assertIn("requestLifetime?.Dispose();", handler)

    def test_epoch_revocation_blocks_reentrant_native_authority(self):
        self.assertIn("private int _epochRevocationDepth;", TEXT)
        epoch = self._part("private void AdvanceDocumentEpoch", "private async void OnWebMessageReceived")
        self.assertIn("Interlocked.Increment(ref _epochRevocationDepth);", epoch)
        self.assertIn("finally { Interlocked.Decrement(ref _epochRevocationDepth); }", epoch)
        handler = self._part("private async void OnWebMessageReceived", "private bool IsCurrent")
        current = self._part("private bool IsCurrent", "private void ReplyIfCurrent")
        self.assertIn("Volatile.Read(ref _epochRevocationDepth) != 0", handler)
        self.assertIn("Volatile.Read(ref _epochRevocationDepth) != 0", current)

    def test_home_menu_core_origin_and_ack_require_native(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', TEXT)
        self.assertIn("IsTrustedSource(args.Source)", TEXT)
        self.assertIn("_trustedVirtualOrigin.Scheme != Uri.UriSchemeHttps", TEXT)
        self.assertIn("if (!_seenRequestIds.Add(requestId)) return;", TEXT)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', TEXT)
        self.assertIn("P01_NATIVE_ACK_MISSING", TEXT)
        self.assertIn("P01_NATIVE_BRIDGE_ERROR", TEXT)


if __name__ == "__main__":
    unittest.main()
