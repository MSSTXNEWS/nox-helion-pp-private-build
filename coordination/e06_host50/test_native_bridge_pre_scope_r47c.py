"""R47c Host50: do not probe unauthorized owner services during advertise.

Source-only tests; no Windows native/WebView2 or E07 acceptance claimed.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
spec = importlib.util.spec_from_file_location("nox_r47c_bridge", PACK / "native_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class NativePreScopeProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((PACK / "catalog.json").read_text(encoding="utf-8"))

    @staticmethod
    def session(routes, private=()):
        return bridge.NativeSession("tenant", "principal", "chat",
                                    frozenset(routes), frozenset(private))

    def test_sensitive_scope_not_granted_skips_owner_probe(self):
        host = bridge.NoxPackHost(self.catalog)
        calls = []
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, lambda: calls.append("sensitive") or True, "owner-receipt", 2))
        result = host.advertise(self.session(["chat.history"]))
        self.assertEqual(calls, [], "Unauthorized session invoked owner callback")
        self.assertEqual(result["chat.history"], {"state":"HOLD", "enabled":False, "sourceId":None})

    def test_dangerous_is_not_advertised_or_probed_but_execute_needs_consent(self):
        calls = []
        approvals = []
        host = bridge.NoxPackHost(self.catalog, native_approve=lambda *_: approvals.append(1) or True)
        host.bind("system.backup", bridge.BoundPort(
            lambda *_: {"complete":True},
            lambda: calls.append("probe") or True, "owner-receipt", 1))
        session = self.session(["system.backup"], ["system.backup"])
        self.assertFalse(host.advertise(session)["system.backup"]["enabled"])
        self.assertEqual(calls, [], "Dangerous capability probe invoked before explicit action")
        self.assertEqual(host.execute("system.backup", {}, session), {"complete":True})
        self.assertEqual((len(calls), len(approvals)), (1, 1))

    def test_authorized_safe_and_private_sensitive_routes_still_connected(self):
        host = bridge.NoxPackHost(self.catalog)
        seen = []
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, lambda: seen.append("sensitive") or True, "receipt-sensitive", 2))
        host.bind("models.catalog", bridge.BoundPort(
            lambda *_: None, lambda: seen.append("safe") or True, "receipt-safe", 3))
        states = host.advertise(self.session(
            ["chat.history", "models.catalog"], ["chat.history"]))
        self.assertEqual(seen, ["sensitive", "safe"])
        self.assertTrue(states["chat.history"]["enabled"])
        self.assertTrue(states["models.catalog"]["enabled"])
        self.assertEqual(states["chat.history"]["sourceId"], "receipt-sensitive")


if __name__ == "__main__":
    unittest.main()
