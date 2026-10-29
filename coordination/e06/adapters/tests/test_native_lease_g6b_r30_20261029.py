"""G6-B R30 source-only native admission regression; never runs PC, SIP, or STOP.

Command (when a Python checkout of this exact branch is available):
python -m unittest discover -s coordination/e06/adapters/tests -p 'test_native_lease_g6b_r30_20261029.py' -v

All owner ports below are inert in-process fakes. This is not Windows E07 QA.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
BRIDGE = ROOT / "proposals" / "NOX-PACK01-50" / "native_bridge.py"
SPEC = importlib.util.spec_from_file_location("g6b_native_bridge_r30", BRIDGE)
assert SPEC is not None and SPEC.loader is not None
native = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = native
SPEC.loader.exec_module(native)

SID = "S-1-5-21-101-202-303-1001"
LEASE = "g6bFixedNativeLeaseMock0123456789AB"


def catalogue():
    return {
        "version": "NOX-INTEGRATION-PACK-01",
        "actions": [
            {"taskId": f"NIP01-{i:02d}", "routeId": route, "owner": owner, "risk": risk}
            for i, (route, owner, risk) in enumerate(native.APPROVED_NATIVE_POLICY, 1)
        ],
    }


def session(*routes, private=(), sid=SID, lease=LEASE):
    return native.NativeSession(
        tenant="tenant-1",
        principal="principal-1",
        chat_id="chat-1",
        allowed=frozenset(routes),
        private_approved=frozenset(private),
        windows_sid=sid,
        session_lease=lease,
    )


class G6BNativeLeaseR30Tests(unittest.TestCase):
    def make_host(self, alive=None, approve=None):
        return native.NoxPackHost(
            catalogue(), native_session_live=alive, native_approve=approve
        )

    def bind_mock(self, host, route, callback=None, ready=None):
        owner = host.routes[route]["owner"]
        if callback is None:
            callback = lambda scope, args: {"mockOnly": True}
        if ready is None:
            ready = lambda: True
        host.bind(route, native.BoundPort(callback, ready, "G6-B-INERT-MOCK", owner))

    def test_canonical_fifty_routes_and_five_dangerous_pins(self):
        self.assertEqual(len(native.ALLOWED_ROUTES), 50)
        self.assertEqual(len(native.APPROVED_NATIVE_POLICY), 50)
        self.assertEqual(sum(risk == "dangerous" for _, _, risk in native.APPROVED_NATIVE_POLICY), 5)
        self.assertEqual(len(self.make_host(alive=lambda s: True).routes), 50)
        broken = catalogue()
        for entry in broken["actions"]:
            if entry["routeId"] == "system.pc_control":
                entry["risk"] = "safe"
        with self.assertRaises(ValueError):
            native.NoxPackHost(broken, native_session_live=lambda s: True)

    def test_missing_sid_and_missing_host_verifier_fail_closed(self):
        scope = session("helion.chat", sid="")
        host = self.make_host(alive=lambda s: True)
        with self.assertRaises(native.HostDenied):
            host.execute("helion.chat", {}, scope)
        missing_verifier = self.make_host()
        with self.assertRaises(native.HostHold):
            missing_verifier.execute("helion.chat", {}, session("helion.chat"))

    def test_all_fifty_routes_deny_revoked_sid_lease_before_mock_owner(self):
        invoked = []
        host = self.make_host(alive=lambda s: False, approve=lambda s, r, p: True)
        for route, owner, risk in native.APPROVED_NATIVE_POLICY:
            self.bind_mock(host, route, callback=lambda s, p: invoked.append(True))
        routes = tuple(native.ALLOWED_ROUTES)
        scope = session(*routes, private=routes)
        for route in routes:
            with self.subTest(route=route):
                with self.assertRaises(native.HostDenied):
                    host.execute(route, {}, scope)
        self.assertEqual(invoked, [])

    def test_sensitive_private_scope_and_fresh_native_dangerous_consent(self):
        route = "system.pc_control"
        invoked = []
        host = self.make_host(alive=lambda s: True, approve=lambda s, r, p: False)
        self.bind_mock(host, route, callback=lambda s, p: invoked.append(True))
        with self.assertRaises(native.HostDenied):
            host.execute(route, {"op": "stop"}, session(route))
        with self.assertRaises(native.HostDenied):
            host.execute(route, {"op": "stop"}, session(route, private=(route,)))
        self.assertEqual(invoked, [])
        allow_host = self.make_host(alive=lambda s: True,
                                    approve=lambda s, r, p: True)
        self.bind_mock(allow_host, route)
        self.assertEqual(allow_host.execute(route, {}, session(route, private=(route,))),
                         {"mockOnly": True})

    def test_revocation_during_consent_blocks_owner_probe_and_call(self):
        state = {"active": True, "probes": 0, "calls": 0}
        def revoke_at_consent(scope, route, payload):
            state["active"] = False
            return True
        def ready():
            state["probes"] += 1
            return True
        def owner(scope, args):
            state["calls"] += 1
        host = self.make_host(alive=lambda s: state["active"], approve=revoke_at_consent)
        self.bind_mock(host, "system.pc_control", callback=owner, ready=ready)
        with self.assertRaises(native.HostDenied):
            host.execute("system.pc_control", {}, session(
                "system.pc_control", private=("system.pc_control",)))
        self.assertEqual((state["probes"], state["calls"]), (0, 0))

    def test_revocation_during_owner_readiness_blocks_call(self):
        state = {"active": True, "calls": 0}
        def ready():
            state["active"] = False
            return True
        def owner(scope, args):
            state["calls"] += 1
        host = self.make_host(alive=lambda s: state["active"])
        self.bind_mock(host, "helion.chat", callback=owner, ready=ready)
        with self.assertRaises(native.HostDenied):
            host.execute("helion.chat", {}, session("helion.chat"))
        self.assertEqual(state["calls"], 0)

    def test_revocation_during_owner_return_blocks_publication(self):
        state = {"active": True}
        def inert_owner(scope, args):
            state["active"] = False
            return {"mustNotPublish": True}
        host = self.make_host(alive=lambda s: state["active"])
        self.bind_mock(host, "helion.chat", callback=inert_owner)
        with self.assertRaises(native.HostDenied):
            host.execute("helion.chat", {}, session("helion.chat"))

    def test_sid_mutation_during_probe_is_denied(self):
        scope = session("helion.chat")
        calls = []
        def mutate_sid():
            object.__setattr__(scope, "windows_sid", "S-1-5-18")
            return True
        host = self.make_host(alive=lambda s: True)
        self.bind_mock(host, "helion.chat", callback=lambda s, p: calls.append(True),
                       ready=mutate_sid)
        with self.assertRaises(native.HostDenied):
            host.execute("helion.chat", {}, scope)
        self.assertEqual(calls, [])

    def test_stop_is_mock_only_and_rejected_after_lease_revocation(self):
        state = {"active": True, "calls": 0}
        def fake_stop(scope, args):
            state["calls"] += 1
            return {"stopRequested": True}
        host = self.make_host(alive=lambda s: state["active"])
        self.bind_mock(host, "chat.stop", callback=fake_stop)
        scope = session("chat.stop")
        self.assertEqual(host.execute("chat.stop", {}, scope), {"stopRequested": True})
        state["active"] = False
        with self.assertRaises(native.HostDenied):
            host.execute("chat.stop", {}, scope)
        self.assertEqual(state["calls"], 1)

    def test_advertise_revoked_and_no_dangerous_preview(self):
        state = {"active": True, "danger_probes": 0}
        host = self.make_host(alive=lambda s: state["active"],
                              approve=lambda s, r, p: True)
        def danger_ready():
            state["danger_probes"] += 1
            return True
        self.bind_mock(host, "system.pc_control", ready=danger_ready)
        self.bind_mock(host, "chat.stop")
        scope = session("chat.stop", "system.pc_control", private=("system.pc_control",))
        states = host.advertise(scope)
        self.assertEqual(len(states), 50)
        self.assertEqual(states["system.pc_control"]["state"], "HOLD")
        self.assertEqual(states["chat.stop"]["state"], "CONNECTED")
        self.assertEqual(state["danger_probes"], 0)
        state["active"] = False
        states = host.advertise(scope)
        self.assertTrue(all(x["state"] == "HOLD" for x in states.values()))


    def test_revocation_verifier_requires_exact_true_not_truthy(self):
        host = self.make_host(alive=lambda scope: 1)
        with self.assertRaises(native.HostDenied):
            host.execute("helion.chat", {}, session("helion.chat"))

    def test_sid_and_lease_format_are_not_page_supplied(self):
        host = self.make_host(alive=lambda scope: True)
        for bad_scope in (
            session("helion.chat", sid="S-1-5-NotAnIdentifier"),
            session("helion.chat", lease="attacker"),
            session("helion.chat", sid=" S-1-5-18 "),
        ):
            with self.subTest(sid=bad_scope.windows_sid, lease=bad_scope.session_lease):
                with self.assertRaises(native.HostDenied):
                    host.execute("helion.chat", {}, bad_scope)

    def test_original_pc_adapter_stop_preview_only_and_sid_scope(self):
        pc_source = (
            ROOT / "coordination" / "e06" / "adapters" /
            "pc_control_owner_port.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from helion.e11.service import E11Service, scope_id", pc_source)
        self.assertIn("session.windows_sid, session.session_lease", pc_source)
        self.assertIn('if op == "stop":', pc_source)
        self.assertIn('elif op == "preview":', pc_source)
        self.assertIn("Native PC identity changed before original owner dispatch", pc_source)
        self.assertNotIn("pc_enable_readonly(", pc_source)
        self.assertNotIn("pc_execute_preview(", pc_source)


    def test_native_sid_and_lease_are_excluded_from_debug_repr(self):
        scope = session("helion.chat")
        description = repr(scope)
        self.assertNotIn(SID, description)
        self.assertNotIn(LEASE, description)


if __name__ == "__main__":
    unittest.main()
