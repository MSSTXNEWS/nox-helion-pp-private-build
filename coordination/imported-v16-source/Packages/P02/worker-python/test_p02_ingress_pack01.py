"""Read-only cross-owner exercise of the REAL pinned PACK01 dispatcher."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

from p02_native_ingress import NativeIngress, ProtocolHold


@unittest.skipUnless(os.environ.get("NOX_PACK01_CHECKOUT"), "PACK01 source not pinned")
class RealPack01BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ["NOX_PACK01_CHECKOUT"])
        spec = importlib.util.spec_from_file_location("native_bridge_p02_ingress", root / "native_bridge.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Exact pinned PACK01 missing")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.pack = module
        cls.catalog = json.loads((root / "catalog.json").read_text("utf-8"))

    def setUp(self):
        self.dispatcher = self.pack.NoxPackHost(self.catalog)
        self.calls = []
        self.dispatcher.bind("chat.model", self.pack.BoundPort(
            lambda s,a: self.calls.append((s.principal,a)) or {"models": ["verified-installed-tag"]},
            lambda: True, "OWNER2-READONLY-PIN", 2))
        self.scope = self.pack.NativeSession(
            "tenant", "alice", "chat", allowed=frozenset({"chat.model"}))
        self.ingress = NativeIngress(self.dispatcher, lambda:self.scope,
                                    expected_run_id="NOX-E02-INGRESS-PIN")

    def frame(self, i, route="chat.model", payload=None):
        return json.dumps({"protocol":"NOX-P02-NATIVE-v1",
            "runId":"NOX-E02-INGRESS-PIN", "requestId":f"{i:032x}",
            "route":route, "payload":payload or {}}, separators=(",",":")).encode()

    def test_trusted_native_user_reaches_only_existing_owner_port(self):
        data = json.loads(self.ingress.handle(self.frame(1)))
        self.assertEqual(data["result"]["models"], ["verified-installed-tag"])
        self.assertEqual(self.calls, [("alice",{})])

    def test_unbound_and_sensitive_routes_hold(self):
        for i, route in enumerate(("chat.rag","chat.voice","calls.history"),2):
            with self.subTest(route=route):
                with self.assertRaises(ProtocolHold): self.ingress.handle(self.frame(i,route))
        self.assertFalse(self.calls)

    def test_session_permissions_are_native_not_page(self):
        self.scope = self.pack.NativeSession("tenant","alice","chat",allowed=frozenset())
        with self.assertRaises(ProtocolHold):self.ingress.handle(self.frame(5))
        with self.assertRaises(ProtocolHold):self.ingress.handle(self.frame(6,payload={"principal":"other"}))
        self.assertFalse(self.calls)

    def test_denies_unsafe_routes_even_when_pack01_has_them(self):
        for i, route in enumerate(("system.pc_control","models.pull","calls.dial"),7):
            with self.subTest(route=route):
                with self.assertRaises(ProtocolHold):self.ingress.handle(self.frame(i,route))
        self.assertFalse(self.calls)
