"""G1-B R09 SOURCE ONLY: malformed duplicate requestId must not send contradictory ACK.
This tests source invariants; it does not compile C#, start WPF or assert native runtime.
"""
from pathlib import Path
import unittest

BRIDGE = Path(__file__).resolve().parents[2] / "Bridge" / "P01WebView2NavigationBridge.cs"
SOURCE = BRIDGE.read_text(encoding="utf-8")
MESSAGE = SOURCE.split("private async void OnWebMessageReceived", 1)[1].split(
    "private bool IsCurrent(", 1
)[0]


class G1BMalformedRequestIdReplayR09(unittest.TestCase):
    def test_read_json_once_with_size_and_depth_bounds(self):
        self.assertIn("if (raw.Length > 2048) return;", MESSAGE)
        self.assertIn("JsonDocumentOptions { MaxDepth = 5 }", MESSAGE)

    def test_request_id_extracted_independently_of_kind(self):
        extract = MESSAGE.index('TryString(root, "requestId", out requestId);')
        validate = MESSAGE.index('!TryString(root, "kind", out var kind)')
        self.assertLess(extract, validate)

    def test_duplicate_detection_before_bad_message_response(self):
        replay = MESSAGE.index(
            "if (RequestId.IsMatch(requestId) && _seenRequestIds.Contains(requestId)) return;"
        )
        bad_message = MESSAGE.index('"P01_BAD_MESSAGE"')
        self.assertLess(replay, bad_message)

    def test_duplicate_check_requires_regex_valid_request_id(self):
        self.assertEqual(MESSAGE.count(
            "RequestId.IsMatch(requestId) && _seenRequestIds.Contains(requestId)"
        ), 1)
        self.assertIn("if (root.ValueKind == JsonValueKind.Object)", MESSAGE)

    def test_new_malformed_messages_still_fail_closed(self):
        self.assertIn('"REJECTED", "P01_BAD_MESSAGE"', MESSAGE)
        self.assertIn('!RouteId.IsMatch(routeId) || !RequestId.IsMatch(requestId)', MESSAGE)

    def test_quota_and_parallel_limit_still_apply(self):
        self.assertIn("MaxRequestsPerDocument = 1024", SOURCE)
        self.assertIn("MaxPendingNativeRequests = 8", SOURCE)
        self.assertIn('"P01_DOCUMENT_REQUEST_LIMIT"', MESSAGE)
        self.assertIn('"P01_NATIVE_BUSY"', MESSAGE)

    def test_home_menu_core_native_consent_and_ack_unchanged(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', SOURCE)
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", SOURCE)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", SOURCE)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', SOURCE)

    def test_one_host_origin_popup_and_failure_guards_unchanged(self):
        for literal in ("_webView.NavigationStarting += OnNavigationStarting;",
                        "_webView.NewWindowRequested += OnNewWindowRequested;",
                        "_webView.ProcessFailed += OnProcessFailed;",
                        "args.Handled = true;", "args.Cancel = true;"):
            self.assertIn(literal, SOURCE)
        for forbidden in ("new WebView2(", "new CoreWebView2(", "Process.Start",
                          "HttpListener", "NewWindow ="):
            self.assertNotIn(forbidden, SOURCE)


if __name__ == "__main__":
    unittest.main()
