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


    def test_native_owner_identity_rejects_bool_and_float(self):
        for fake_owner in (True, 1.0, "1"):
            with self.subTest(owner=fake_owner):
                other = bridge.NoxPackHost(json.loads(CATALOG.read_text("utf-8")))
                port = bridge.BoundPort(
                    lambda session, data: "OK", lambda: True,
                    "NATIVE_OWNER_SOURCE_RECEIPT", fake_owner)
                with self.assertRaises(bridge.HostHold):
                    other.bind("media.subtitles", port)
                self.assertFalse(other.ports)

    def test_registered_integer_owner_still_admitted(self):
        self.assertEqual(self.dispatch.ports["media.subtitles"].owner, 1)
        self.assertEqual(self.request({"text": "safe"}), {"status": "owner-executed"})


    def test_reject_mutable_native_route_scopes(self):
        bad = bridge.NativeSession("tenant", "person", "chat",
            allowed={"media.subtitles"}, private_approved=frozenset())
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("media.subtitles", {"text": "safe"}, bad)
        self.assertEqual(self.seen, [])

    def test_reject_string_scopes_not_typed_as_frozenset(self):
        bad = bridge.NativeSession("tenant", "person", "chat",
            allowed=frozenset({"media.subtitles"}),
            private_approved="media.subtitles")
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("media.subtitles", {"text": "safe"}, bad)
        self.assertEqual(self.seen, [])

    def test_reject_approval_outside_active_native_allowed_routes(self):
        bad = bridge.NativeSession("tenant", "person", "chat",
            allowed=frozenset({"media.subtitles"}),
            private_approved=frozenset({"system.pc_control"}))
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("media.subtitles", {"text": "safe"}, bad)
        self.assertEqual(self.seen, [])

    def test_immutable_native_scope_within_allowed_routes_remains_accepted(self):
        allowed = frozenset({"media.subtitles"})
        good = bridge.NativeSession("tenant", "person", "chat",
            allowed=allowed, private_approved=allowed)
        self.assertEqual(
            self.dispatch.execute("media.subtitles", {"text": "safe"}, good),
            {"status": "owner-executed"})
        self.assertEqual(self.seen, [{"text": "safe"}])


    def test_catalog_rejects_boolean_or_float_native_owner(self):
        for bad_owner in (True, 1.0, "1"):
            with self.subTest(bad_owner=bad_owner):
                catalog = json.loads(CATALOG.read_text("utf-8"))
                for row in catalog["actions"]:
                    if row["routeId"] == "media.subtitles":
                        row["owner"] = bad_owner
                with self.assertRaises(ValueError):
                    bridge.NoxPackHost(catalog)

    def test_catalog_rejects_unknown_risk_policy(self):
        catalog = json.loads(CATALOG.read_text("utf-8"))
        for row in catalog["actions"]:
            if row["routeId"] == "media.subtitles":
                row["risk"] = "unverified"
        with self.assertRaises(ValueError):
            bridge.NoxPackHost(catalog)

    def test_original_catalog_owner_risks_remain_valid(self):
        original = json.loads(CATALOG.read_text("utf-8"))
        self.assertEqual(len(bridge.NoxPackHost(original).routes), 50)


    def test_forged_foreign_session_cannot_override_validation(self):
        class FakeSession:
            allowed = frozenset({"media.subtitles"})
            private_approved = frozenset()
            tenant = "tenant"
            principal = "principal"
            chat_id = "chat"
            def validate(self):
                return None
        with self.assertRaisesRegex(bridge.HostDenied, "native session type"):
            self.dispatch.execute("media.subtitles", {"text": "no"}, FakeSession())
        with self.assertRaisesRegex(bridge.HostDenied, "native session type"):
            self.dispatch.advertise(FakeSession())
        self.assertEqual(self.seen, [])

    def test_subclass_native_session_is_not_a_signed_host_identity(self):
        class ForgedSession(bridge.NativeSession):
            def validate(self):
                return None
        forged = ForgedSession("tenant", "principal", "chat",
            allowed=frozenset({"media.subtitles"}))
        with self.assertRaisesRegex(bridge.HostDenied, "native session type"):
            self.dispatch.execute("media.subtitles", {}, forged)
        self.assertEqual(self.seen, [])

    def test_catalog_reordered_task_ids_must_not_bind_route_owners(self):
        catalog = json.loads(CATALOG.read_text("utf-8"))
        catalog["actions"][0]["taskId"], catalog["actions"][1]["taskId"] = (
            catalog["actions"][1]["taskId"], catalog["actions"][0]["taskId"])
        with self.assertRaisesRegex(ValueError, "TaskID"):
            bridge.NoxPackHost(catalog)
        self.assertEqual(self.seen, [])

    def test_unhashable_native_route_is_denied_before_backend(self):
        for route in ([], {}, None, 1):
            with self.subTest(route=repr(route)):
                with self.assertRaises(bridge.HostDenied):
                    self.dispatch.execute(route, {}, self.session)
        self.assertEqual(self.seen, [])

    def test_catalog_rejects_dangerous_route_downgrade(self):
        for target in ("system.pc_control", "calls.dial", "training.start"):
            with self.subTest(route=target):
                catalog = json.loads(CATALOG.read_text("utf-8"))
                next(row for row in catalog["actions"] if row["routeId"] == target)["risk"] = "safe"
                with self.assertRaisesRegex(ValueError, "Immutable native"):
                    bridge.NoxPackHost(catalog)

    def test_catalog_rejects_owner_escalation_and_route_reorder(self):
        catalog = json.loads(CATALOG.read_text("utf-8"))
        next(row for row in catalog["actions"] if row["routeId"] == "system.pc_control")["owner"] = 2
        with self.assertRaisesRegex(ValueError, "Immutable native"):
            bridge.NoxPackHost(catalog)
        catalog = json.loads(CATALOG.read_text("utf-8"))
        catalog["actions"][0]["routeId"], catalog["actions"][1]["routeId"] = (
            catalog["actions"][1]["routeId"], catalog["actions"][0]["routeId"])
        with self.assertRaisesRegex(ValueError, "Immutable native"):
            bridge.NoxPackHost(catalog)

    def test_catalog_post_init_mutation_cannot_silence_native_consent(self):
        catalog = json.loads(CATALOG.read_text("utf-8"))
        observed = []
        dispatcher = bridge.NoxPackHost(catalog)
        dispatcher.bind("system.pc_control", bridge.BoundPort(
            lambda session, args: observed.append(args), lambda: True,
            "SOURCE_TEST_REAL_OWNER_RECEIPT_NOT_WINDOWS", 1))
        selected = next(row for row in catalog["actions"] if row["routeId"] == "system.pc_control")
        selected["risk"] = "safe"
        selected["owner"] = 2
        session = bridge.NativeSession("tenant", "principal", "chat",
            allowed=frozenset({"system.pc_control"}),
            private_approved=frozenset({"system.pc_control"}))
        with self.assertRaisesRegex(bridge.HostDenied, "Fresh native action approval"):
            dispatcher.execute("system.pc_control", {"preview": True}, session)
        self.assertEqual(observed, [])
        self.assertEqual(dispatcher.routes["system.pc_control"]["risk"], "dangerous")
        self.assertEqual(dispatcher.routes["system.pc_control"]["owner"], 1)

    def test_native_policy_is_read_only_after_registration(self):
        with self.assertRaises(TypeError):
            self.dispatch.routes["media.subtitles"]["risk"] = "safe"
        with self.assertRaises(TypeError):
            self.dispatch.routes["media.subtitles"] = {}
        self.assertEqual(self.request({"preview": "normal"}), {"status": "owner-executed"})

    def test_malformed_unhashable_catalog_fails_closed(self):
        for bad in ([], {}, None, True):
            with self.subTest(bad=repr(bad)):
                catalog = json.loads(CATALOG.read_text("utf-8"))
                catalog["actions"][0]["routeId"] = bad
                with self.assertRaises(ValueError):
                    bridge.NoxPackHost(catalog)


if __name__ == "__main__":
    unittest.main()
