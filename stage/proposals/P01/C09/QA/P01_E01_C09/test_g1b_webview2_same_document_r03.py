"""G1-B R03: source-only WebView2 document lifecycle regression."""
from pathlib import Path
import unittest

TEXT = (Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs").read_text(encoding="utf-8")

class G1BDocumentLifecycleR03(unittest.TestCase):
    def test_same_document_change_keeps_request_ids(self):
        self.assertIn("AdvanceDocumentEpoch(newDocument: args.IsNewDocument)", TEXT)
        self.assertIn("if (newDocument) _seenRequestIds.Clear();", TEXT)

    def test_same_url_reload_resets_document(self):
        self.assertIn("CoreWebView2ContentLoadingEventArgs args", TEXT)
        self.assertIn("AdvanceDocumentEpoch(newDocument: true)", TEXT)

    def test_navigation_start_does_not_release_nonce(self):
        self.assertIn("AdvanceDocumentEpoch(newDocument: false)", TEXT)

    def test_existing_host_unsubscribes_content_loading(self):
        self.assertIn("_webView.ContentLoading += OnContentLoading;", TEXT)
        self.assertIn("_webView.ContentLoading -= OnContentLoading;", TEXT)

    def test_native_ack_and_consent_remain_protected(self):
        self.assertIn("IsTrustedSource(args.Source)", TEXT)
        self.assertIn("await _confirmNativeConsent", TEXT)
        self.assertIn("if (!_seenRequestIds.Add(requestId)) return;", TEXT)

if __name__ == "__main__":
    unittest.main()
