"""G1-B R02: source-level regression checks; NOT native C#/Windows runtime tests."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
TEXT = SOURCE.read_text(encoding="utf-8")


class G1BWebView2EpochR02(unittest.TestCase):
    def test_reload_same_url_invalidates_pending_result(self):
        self.assertIn("_webView.NavigationStarting += OnNavigationStarting;", TEXT)
        self.assertIn("Interlocked.Increment(ref _documentEpoch);", TEXT)
        self.assertIn("var documentEpoch = Interlocked.Read(ref _documentEpoch);", TEXT)
        self.assertIn("Interlocked.Read(ref _documentEpoch) == documentEpoch", TEXT)
        self.assertIn("ReplyIfCurrent(documentSource, documentEpoch", TEXT)

    def test_history_and_source_change_are_not_just_url_comparisons(self):
        self.assertIn("_webView.SourceChanged += OnSourceChanged;", TEXT)
        self.assertIn("CoreWebView2SourceChangedEventArgs", TEXT)
        self.assertIn("string.Equals(current, documentSource, StringComparison.Ordinal);", TEXT)

    def test_previous_completed_action_id_cannot_replay(self):
        self.assertIn("if (!_seenRequestIds.Add(requestId)) return;", TEXT)
        self.assertIn("_seenRequestIds.Clear();", TEXT)
        self.assertIn("_pending.Add((documentEpoch, requestId))", TEXT)
        self.assertIn("_pending.Remove((documentEpoch, requestId))", TEXT)

    def test_cache_bounded_even_if_page_floods_native_bridge(self):
        self.assertIn("MaxRequestsPerDocument = 1024;", TEXT)
        self.assertIn("_seenRequestIds.Count >= MaxRequestsPerDocument", TEXT)
        self.assertIn("P01_DOCUMENT_REQUEST_LIMIT", TEXT)

    def test_consent_precedes_existing_native_dispatch(self):
        handler = TEXT.split("private async void OnWebMessageReceived", 1)[1]
        consent = handler.index("await _confirmNativeConsent(routeId, _lifetime.Token)")
        action = handler.index("await _invokeExistingNativeRoute(routeId, _lifetime.Token)")
        self.assertLess(consent, action)
        self.assertIn("var accepted = await _invokeExistingNativeRoute(routeId, _lifetime.Token);\n"
                      "            if (!IsCurrent(documentSource, documentEpoch) || "
                      "!_isNativeRouteAvailable(routeId)) return;", handler)
        self.assertIn('accepted ? "COMPLETED" : "HOLD"', handler)

    def test_detaches_all_three_event_hooks_on_dispose(self):
        self.assertIn("_webView.WebMessageReceived -= OnWebMessageReceived;", TEXT)
        self.assertIn("_webView.NavigationStarting -= OnNavigationStarting;", TEXT)
        self.assertIn("_webView.SourceChanged -= OnSourceChanged;", TEXT)
        self.assertIn("_lifetime.Cancel();", TEXT)

    def test_no_second_host_or_native_permission_from_javascript(self):
        self.assertIn("CoreWebView2 existingWebView", TEXT)
        self.assertNotIn("new WebView2(", TEXT)
        self.assertNotIn("new CoreWebView2(", TEXT)
        self.assertNotIn("HttpListener", TEXT)
        self.assertNotIn("Process.Start", TEXT)
        self.assertNotIn('TryString(root, "approved"', TEXT)


if __name__ == "__main__":
    unittest.main()
