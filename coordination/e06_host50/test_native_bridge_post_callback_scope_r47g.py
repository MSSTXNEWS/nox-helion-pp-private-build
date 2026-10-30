"""R47G: native callback revocation must fail closed before owner call.

Source-only component regression; Windows WebView2/E07 not claimed.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
spec = importlib.util.spec_from_file_location("nox_r47g_bridge", PACK / "native_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class NativePostCallbackScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((PACK / "catalog.json").read_text(encoding="utf-8"))

    @staticmethod
    def scope(route, sensitive=False):
        return bridge.NativeSession(
            "tenant", "principal", "chat", frozenset([route]),
            frozenset([route]) if sensitive else frozenset())

    def test_readiness_revoke_acl_blocks_safe_dispatch(self):
        scope = self.scope("chat.stop")
        calls = []
        host = bridge.NoxPackHost(self.catalog)
        def revoke():
            # Trusted host callback may invalidate an earlier immutable snapshot.
            object.__setattr__(scope, "allowed", frozenset())
            return True
        host.bind("chat.stop", bridge.BoundPort(
            lambda *_: calls.append("STOP"), revoke, "owner-receipt", 2))
        with self.assertRaises(bridge.HostDenied):
            host.execute("chat.stop", {}, scope)
        self.assertEqual(calls, [], "revoked ACL executed native owner code")

    def test_fresh_approval_revoke_private_scope_blocks_dangerous_dispatch(self):
        scope = self.scope("system.backup", sensitive=True)
        calls = []
        def approve(_session, _route, _payload):
            object.__setattr__(scope, "private_approved", frozenset())
            return True
        host = bridge.NoxPackHost(self.catalog, native_approve=approve)
        host.bind("system.backup", bridge.BoundPort(
            lambda *_: calls.append("backup"), lambda: True, "owner-receipt", 1))
        with self.assertRaises(bridge.HostDenied):
            host.execute("system.backup", {}, scope)
        self.assertEqual(calls, [], "revoked private approval executed backup")

    def test_unchanged_authorized_scope_still_dispatches(self):
        scope = self.scope("chat.history", sensitive=True)
        calls = []
        host = bridge.NoxPackHost(self.catalog)
        host.bind("chat.history", bridge.BoundPort(
            lambda _scope, payload: calls.append(payload) or {"ok": True},
            lambda: True, "owner-receipt", 2))
        self.assertEqual(host.execute("chat.history", {"limit": 1}, scope), {"ok": True})
        self.assertEqual(calls, [{"limit": 1}])


if __name__ == "__main__":
    unittest.main()
