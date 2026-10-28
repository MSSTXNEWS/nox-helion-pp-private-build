"""NOX V16 PACK01: byte-accurate admission to the single existing native dispatcher.
Runs without Windows, Ollama, SIP, GPU or another host.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "proposals" / "NOX-PACK01-50" / "native_bridge.py"
CATALOG = ROOT / "proposals" / "NOX-PACK01-50" / "catalog.json"
spec = importlib.util.spec_from_file_location("nox_pack01_utf8_owner_test", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class NativeWireGuard(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.dispatch = bridge.NoxPackHost(json.loads(CATALOG.read_text("utf-8")))
        self.dispatch.bind("media.subtitles", bridge.BoundPort(
            lambda session, payload: self.seen.append(payload) or {"status": "owner-executed"},
            lambda: True, "NATIVE_SOURCE_UNIT_RECEIPT_NOT_RELEASE", 1))
        self.session = bridge.NativeSession("test_tenant", "test_owner", "test_chat",
            allowed=frozenset({"media.subtitles"}))

    def request(self, payload):
        return self.dispatch.execute("media.subtitles", payload, self.session)

    def deny_before_owner(self, payload):
        with self.assertRaises(bridge.HostDenied):
            self.request(payload)
        self.assertEqual(self.seen, [])

    def test_many_emoji_rejected_by_utf8_bytes(self):
        data = {"text": "🎬" * 550000}
        self.assertLess(len(json.dumps(data, ensure_ascii=False)), 2097152)
        self.assertGreater(len(json.dumps(data, ensure_ascii=False).encode("utf-8")), 2097152)
        self.deny_before_owner(data)

    def test_regular_russian_spanish_unicode_succeeds(self):
        value = {"text": "Привет · Hola 🎬"}
        self.assertEqual(self.request(value), {"status": "owner-executed"})
        self.assertEqual(self.seen, [value])

    def test_nonfinite_number_never_reaches_owner(self):
        self.deny_before_owner({"score": float("nan")})

    def test_infinite_number_never_reaches_owner(self):
        self.deny_before_owner({"score": float("inf")})

    def test_nonjson_value_never_reaches_owner(self):
        self.deny_before_owner({"bad": object()})

    def test_lone_unicode_surrogate_never_reaches_owner(self):
        self.deny_before_owner({"text": "\ud800"})

    def test_recursive_json_never_reaches_owner(self):
        cyclic = []
        cyclic.append(cyclic)
        self.deny_before_owner({"nested": cyclic})

    def test_risky_route_still_requires_native_approval(self):
        self.dispatch.bind("system.pc_control", bridge.BoundPort(
            lambda session, payload: self.seen.append(("danger", payload)) or {"status": "ok"},
            lambda: True, "NATIVE_DANGER_SOURCE_RECEIPT", 1))
        privileged = bridge.NativeSession("test_tenant", "test_owner", "test_chat",
            allowed=frozenset({"system.pc_control"}),
            private_approved=frozenset({"system.pc_control"}))
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("system.pc_control", {"mode": "preview"}, privileged)
        self.assertEqual(self.seen, [])


    def test_native_approval_must_not_mutate_executed_payload(self):
        payload = {"target": {"name": "original"}}
        approved = []
        def approve(session, route, approved_copy):
            approved.append(approved_copy)
            approved_copy["target"]["name"] = "changed-during-consent"
            payload["target"]["name"] = "changed-by-caller"
            return True
        self.dispatch.native_approve = approve
        self.dispatch.bind("system.pc_control", bridge.BoundPort(
            lambda session, data: self.seen.append(data) or {"done": True},
            lambda: True, "NATIVE_EXACT_ACTION_RECEIPT", 1))
        privileged = bridge.NativeSession("test_tenant", "test_owner", "test_chat",
            allowed=frozenset({"system.pc_control"}),
            private_approved=frozenset({"system.pc_control"}))
        result = self.dispatch.execute("system.pc_control", payload, privileged)
        self.assertEqual(result, {"done": True})
        self.assertEqual(approved[0]["target"]["name"], "changed-during-consent")
        self.assertEqual(self.seen, [{"target": {"name": "original"}}])

    def test_backend_availability_callback_cannot_swap_request_data(self):
        original = {"text": "original"}
        other = bridge.NoxPackHost(json.loads(CATALOG.read_text("utf-8")))
        def readiness():
            original["text"] = "swapped-on-ready-check"
            return True
        observed = []
        other.bind("media.subtitles", bridge.BoundPort(
            lambda session, data: observed.append(data) or "OK",
            readiness, "NATIVE_PROBE_RECEIPT", 1))
        self.assertEqual(other.execute("media.subtitles", original, self.session), "OK")
        self.assertEqual(observed, [{"text": "original"}])

    def test_nested_payload_snapshot_is_separate_from_original(self):
        payload = {"nested": [{"value": "before"}]}
        result = self.request(payload)
        payload["nested"][0]["value"] = "after"
        self.assertEqual(result, {"status": "owner-executed"})
        self.assertEqual(self.seen, [{"nested": [{"value": "before"}]}])


if __name__ == "__main__":
    unittest.main()
