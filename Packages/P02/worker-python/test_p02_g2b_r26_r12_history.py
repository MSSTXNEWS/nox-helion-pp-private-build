"""G2-B R26 R12 original-module source regression (not native Windows QA).

Run inside checkout: python -m unittest -v Packages/P02/worker-python/test_p02_g2b_r26_r12_history.py
This tests the actual route module with controlled dependency facades, no devices.
"""
from __future__ import annotations
import importlib.util
import pathlib
import sys
import threading
import types
import unittest
from dataclasses import dataclass
from unittest import mock

WORKER = pathlib.Path(__file__).resolve().parent

def load_owner_module():
    runtime = types.ModuleType("p02_runtime")
    runtime.P02Error = type("P02Error", (Exception,), {})
    class P02Store:
        def history(self, tenant, principal, conversation, limit):
            if not all((tenant, principal, conversation)) or limit != 1:
                raise PermissionError("Invalid test scope")
            return []
    runtime.P02Store = P02Store
    capabilities = types.ModuleType("p02_capabilities")
    @dataclass(frozen=True)
    class Identity:
        tenant: str
        principal: str
        core_id: str
        persona_id: str
        session_id: str
    class LocalVoicePipeline:
        approved_models = True
        def validate_request(self, *args, **kwargs):
            return None
    capabilities.Identity = Identity
    capabilities.LocalVoicePipeline = LocalVoicePipeline
    chat = types.ModuleType("p02_chat_bridge")
    chat.ChatBridge = type("ChatBridge", (), {"_rag_evidence": staticmethod(lambda x: ("", []))})
    with mock.patch.dict(sys.modules, {
        "p02_runtime": runtime, "p02_capabilities": capabilities,
        "p02_chat_bridge": chat,
    }):
        spec = importlib.util.spec_from_file_location("p02_owner_route_ports_g2b_test",
                                                       WORKER / "p02_owner_route_ports.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return mod, P02Store, Identity, LocalVoicePipeline

class OwnerHistorySecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod, cls.Store, cls.Identity, cls.Voice = load_owner_module()
    def scope(self):
        i = self.Identity("tenant-a", "principal-a", "core-a", "persona-a", "session-a")
        return self.mod.NativeScope("tenant-a", "principal-a", "conv-a",
                                    "S-1-5-21-123-456-789", "session-a", i)
    @staticmethod
    def row(**changes):
        r = {"tenant": "tenant-a", "principal": "principal-a", "call_id": "call-a",
             "status": "completed", "started_epoch": 1700000000}
        r.update(changes)
        return r
    def ports(self, provider):
        return self.mod.OwnerTwoPorts(
            store=self.Store(), native_authorize=lambda *_: True,
            native_call_history=provider, owner_ready=lambda *_: True)
    def test_whitelist_private_fields(self):
        result = self.ports(lambda *_: [self.row(secret="PRIVATE")]).calls_history(
            self.scope(), {"limit": 1})
        self.assertEqual(set(result["calls"][0]), {"call_id", "status", "started_epoch"})
        self.assertNotIn("PRIVATE", repr(result))
    def test_single_read_of_validated_fields(self):
        class PoisonedRow(dict):
            def __getitem__(self, key):
                return "FORGED" if key == "call_id" else super().__getitem__(key)
        result = self.ports(lambda *_: [PoisonedRow(self.row())]).calls_history(
            self.scope(), {"limit": 1})
        self.assertEqual(result["calls"][0]["call_id"], "call-a")
    def test_provider_row_revokes_acl(self):
        holder = {}
        class RevocationRow(dict):
            def get(self, key, default=None):
                if key == "call_id":
                    holder["ports"].authorize = lambda *_: False
                return super().get(key, default)
        holder["ports"] = self.ports(lambda *_: [RevocationRow(self.row())])
        with self.assertRaises((PermissionError, self.mod.RouteHold)):
            holder["ports"].calls_history(self.scope(), {"limit": 1})
    def test_provider_row_rebinds_history_owner(self):
        holder = {}
        class RebindRow(dict):
            def get(self, key, default=None):
                if key == "status":
                    holder["ports"].call_history = lambda *_: []
                return super().get(key, default)
        holder["ports"] = self.ports(lambda *_: [RebindRow(self.row())])
        with self.assertRaises(self.mod.RouteHold):
            holder["ports"].calls_history(self.scope(), {"limit": 1})
    def test_cross_tenant_and_bool_timestamp_denied(self):
        for row in (self.row(tenant="OTHER"), self.row(started_epoch=True)):
            with self.subTest(row=row), self.assertRaises(PermissionError):
                self.ports(lambda *_: [row]).calls_history(self.scope(), {"limit": 1})
    def test_missing_native_stop_does_not_consume_capture(self):
        taken = []
        ports = self.mod.OwnerTwoPorts(
            store=self.Store(), native_authorize=lambda *_: True,
            voice_pipeline=self.Voice(),
            native_take_audio=lambda *_: taken.append(1),
            native_mic_consent=lambda *_: True,
            native_store_output_audio=lambda *_: "b"*32,
            native_discard_output_audio=lambda *_: True,
            owner_ready=lambda *_: True)
        with self.assertRaisesRegex(self.mod.RouteHold, "STOP_TOKEN_REQUIRED"):
            ports.captured_voice(self.scope(), {"capture_id": "a"*32}, stop=None)
        self.assertEqual(taken, [])
    def test_browser_cannot_inject_microphone_consent(self):
        with self.assertRaises(PermissionError):
            self.ports(lambda *_: []).captured_voice(
                self.scope(), {"capture_id": "a"*32, "microphone_consent": True},
                stop=threading.Event())

if __name__ == "__main__":
    unittest.main(verbosity=2)
