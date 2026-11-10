"""NOX V16 E06 independent security regression for the existing P02 ingress.

Owner E06 / QA only. DO NOT rewrite Packages/P02 owner source.
Run: python -m unittest discover -s tests/e06 -p 'test_p02_native_route_shape_r11.py' -v
The correct release behavior is a ProtocolHold on malformed JSON route types,
not a raw TypeError propagating out of the native boundary.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/P02/worker-python/p02_native_ingress.py"


class _ExistingOwnerDispatcher:
    def __init__(self):
        self.calls = []

    def execute(self, route, payload, session):
        self.calls.append((route, payload, session))
        return {"ok": True}


class NativeRouteShapeR11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise AssertionError(f"Required actual P02 owner source missing: {SOURCE}")
        spec = importlib.util.spec_from_file_location("nox_p02_r11_exact_owner", SOURCE)
        if spec is None or spec.loader is None:
            raise AssertionError("P02 module import loader missing")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.owner = mod

    def setUp(self):
        self.dispatcher = _ExistingOwnerDispatcher()
        self.session = object()
        self.ingress = self.owner.NativeIngress(
            self.dispatcher, lambda: self.session, expected_run_id="E06-R11"
        )

    @staticmethod
    def frame(route, nonce="a" * 32, payload=None):
        return json.dumps({
            "protocol": "NOX-P02-NATIVE-v1",
            "requestId": nonce,
            "route": route,
            "payload": {} if payload is None else payload,
            "runId": "E06-R11",
        }, separators=(",", ":")).encode("utf-8")

    def assert_denied_without_dispatch(self, route):
        # Release contract: malformed/unhashable JSON route values never escape
        # as Python TypeError, never reach owner side effects, and do not succeed.
        with self.assertRaises(self.owner.ProtocolHold):
            self.ingress.handle(self.frame(route))
        self.assertEqual([], self.dispatcher.calls)

    def test_array_route_is_managed_hold(self):
        self.assert_denied_without_dispatch([])

    def test_object_route_is_managed_hold(self):
        self.assert_denied_without_dispatch({"route": "helion.chat"})

    def test_null_route_is_managed_hold(self):
        self.assert_denied_without_dispatch(None)

    def test_numeric_route_is_managed_hold(self):
        self.assert_denied_without_dispatch(42)

    def test_wrong_string_route_is_managed_hold(self):
        self.assert_denied_without_dispatch("not.a.route")

    def test_known_route_reaches_only_injected_dispatcher(self):
        out = json.loads(self.ingress.handle(self.frame("chat.history")))
        self.assertEqual(out["status"], "OK")
        self.assertEqual(len(self.dispatcher.calls), 1)
        self.assertEqual(self.dispatcher.calls[0][0], "chat.history")
        self.assertIs(self.dispatcher.calls[0][2], self.session)

    def test_page_authority_claim_rejected(self):
        with self.assertRaises(self.owner.ProtocolHold):
            self.ingress.handle(self.frame("chat.history", payload={"principal": "attacker"}))
        self.assertEqual([], self.dispatcher.calls)


if __name__ == "__main__":
    unittest.main()
