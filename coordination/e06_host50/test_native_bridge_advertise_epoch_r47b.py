"""Host50 R47b: owner readiness may revoke already advertised native routes.
Source-only: never claim Windows WebView2 or E07 acceptance from this test.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
spec = importlib.util.spec_from_file_location("nox_r47b_bridge", PACK / "native_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class AdvertiseEpochTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((PACK / "catalog.json").read_text(encoding="utf-8"))

    @staticmethod
    def session(*routes, private=()):
        return bridge.NativeSession("tenant", "principal", "chat",
                                    frozenset(routes), frozenset(private))

    def test_owner_revokes_itself_during_probe(self):
        host = bridge.NoxPackHost(self.catalog)
        def probe():
            host.ports.pop("chat.history", None)
            return True
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, probe, "original-owner-receipt", 2))
        item = host.advertise(self.session("chat.history", private=("chat.history",)))["chat.history"]
        self.assertEqual(item, {"state": "HOLD", "enabled": False, "sourceId": None})

    def test_later_probe_revokes_earlier_enabled_route(self):
        host = bridge.NoxPackHost(self.catalog)
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, lambda: True, "original-owner-receipt", 2))
        def later_probe():
            host.ports.pop("chat.history", None)
            return True
        host.bind("models.catalog", bridge.BoundPort(
            lambda *_: None, later_probe, "second-owner-receipt", 3))
        states = host.advertise(self.session(
            "chat.history", "models.catalog", private=("chat.history",)))
        self.assertFalse(states["chat.history"]["enabled"])
        self.assertIsNone(states["chat.history"]["sourceId"])
        self.assertTrue(states["models.catalog"]["enabled"])

    def test_unchanged_owner_and_native_scope_still_preserved(self):
        host = bridge.NoxPackHost(self.catalog)
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, lambda: True, "current-owner-receipt", 2))
        host.bind("system.backup", bridge.BoundPort(
            lambda *_: None, lambda: True, "backup-owner-receipt", 1))
        states = host.advertise(self.session(
            "chat.history", "system.backup", private=("chat.history", "system.backup")))
        self.assertTrue(states["chat.history"]["enabled"])
        self.assertEqual(states["chat.history"]["sourceId"], "current-owner-receipt")
        self.assertFalse(states["system.backup"]["enabled"])
        self.assertFalse(host.advertise(self.session("chat.history"))["chat.history"]["enabled"])


if __name__ == "__main__":
    unittest.main()
