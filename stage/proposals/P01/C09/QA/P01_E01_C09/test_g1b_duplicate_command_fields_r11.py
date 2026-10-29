"""G1-B R11: source-only guard against duplicate security-contract JSON keys.

This is a structural source regression, not compiled C#/Windows WebView2 evidence.
The bridge must reject ambiguous requestId/kind/routeId without native dispatch.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "Bridge" /
          "P01WebView2NavigationBridge.cs").read_text(encoding="utf-8")
MESSAGE = SOURCE.split("private async void OnWebMessageReceived", 1)[1].split(
    "private bool IsCurrent(", 1)[0]


class G1BDuplicateCommandFieldsR11(unittest.TestCase):
    def test_json_properties_are_enumerated_before_action_admission(self):
        self.assertIn("foreach (var property in root.EnumerateObject())", MESSAGE)
        self.assertLess(MESSAGE.index("root.EnumerateObject()"),
                        MESSAGE.index('!TryString(root, "kind", out var kind)'))

    def test_three_security_fields_are_counted_exactly(self):
        for fragment in ('property.NameEquals("requestId")',
                         'property.NameEquals("kind")',
                         'property.NameEquals("routeId")'):
            self.assertIn(fragment, MESSAGE)

    def test_duplicate_request_id_never_receives_ambiguous_ack(self):
        duplicate = MESSAGE.index("if (requestIdKeys > 1) return;")
        extract = MESSAGE.index('TryString(root, "requestId", out requestId);')
        self.assertLess(duplicate, extract)

    def test_existing_replay_guard_runs_before_schema_rejection(self):
        guard = MESSAGE.index("if (RequestId.IsMatch(requestId) && _seenRequestIds.Contains(requestId)) return;")
        reject = MESSAGE.index("if (kindKeys > 1 || routeIdKeys > 1)")
        self.assertLess(guard, reject)

    def test_duplicate_kind_or_route_is_rejected_before_dispatch(self):
        reject = MESSAGE.index("if (kindKeys > 1 || routeIdKeys > 1)")
        validate = MESSAGE.index('!TryString(root, "kind", out var kind)')
        self.assertLess(reject, validate)
        self.assertIn('"REJECTED", "P01_BAD_MESSAGE"', MESSAGE[reject:validate])

    def test_malformed_fields_never_allocate_native_pending(self):
        reject = MESSAGE.index("if (kindKeys > 1 || routeIdKeys > 1)")
        pending = MESSAGE.index("_pending.TryAdd((documentEpoch, requestId)")
        self.assertLess(reject, pending)

    def test_replay_ack_and_consent_still_preserved(self):
        self.assertIn("if (!_seenRequestIds.Add(requestId)) return;", MESSAGE)
        self.assertIn("await _confirmNativeConsent(routeId, requestLifetime.Token)", MESSAGE)
        self.assertIn("await _invokeExistingNativeRoute(routeId, requestLifetime.Token)", MESSAGE)
        self.assertIn('nativeAcknowledged = status == "COMPLETED"', SOURCE)

    def test_home_menu_core_and_browser_origin_preserved(self):
        self.assertIn('routeId == "HOME" || routeId == "MENU" || routeId == "CORE"', SOURCE)
        self.assertIn("args.Cancel = true;", SOURCE)
        self.assertIn("args.Handled = true;", SOURCE)
        self.assertIn("IsTrustedSource(args.Source)", SOURCE)
        self.assertIn("MaxPendingNativeRequests = 8", SOURCE)

    def test_existing_host_only_and_source_bounds_unchanged(self):
        self.assertIn("if (raw.Length > 2048) return;", MESSAGE)
        self.assertIn("JsonDocumentOptions { MaxDepth = 5 }", MESSAGE)
        for forbidden in ("new WebView2(", "new CoreWebView2(",
                          "HttpListener", "Process.Start", "NewWindow ="):
            self.assertNotIn(forbidden, SOURCE)


if __name__ == "__main__":
    unittest.main()
