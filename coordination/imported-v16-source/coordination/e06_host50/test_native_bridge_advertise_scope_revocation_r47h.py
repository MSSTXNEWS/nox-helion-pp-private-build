"""R47H: readiness probes cannot advertise routes after native scope revocation.
Source-component test only; not WPF/native/E07 acceptance.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
spec = importlib.util.spec_from_file_location("nox_r47h_bridge", PACK / "native_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class AdvertiseNativeScopeRevocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((PACK / "catalog.json").read_text("utf-8"))

    def host(self):
        return bridge.NoxPackHost(self.catalog)

    @staticmethod
    def scope(*allowed, private=()):
        return bridge.NativeSession("tenant", "principal", "chat",
                                    frozenset(allowed), frozenset(private))

    def test_sensitive_self_revokes_consent_during_probe(self):
        session = self.scope("chat.history", private=("chat.history",))
        host = self.host()
        def readiness():
            object.__setattr__(session, "private_approved", frozenset())
            return True
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, readiness, "owner2-proof", 2))
        cap = host.advertise(session)["chat.history"]
        self.assertEqual(cap, {"state": "HOLD", "enabled": False, "sourceId": None})

    def test_later_probe_revokes_earlier_safe_acl(self):
        session = self.scope("chat.stop", "models.catalog")
        host = self.host()
        host.bind("chat.stop", bridge.BoundPort(
            lambda *_: None, lambda: True, "stop-owner", 2))
        def readiness():
            object.__setattr__(session, "allowed", frozenset(("models.catalog",)))
            return True
        host.bind("models.catalog", bridge.BoundPort(
            lambda *_: None, readiness, "models-owner", 3))
        result = host.advertise(session)
        self.assertFalse(result["chat.stop"]["enabled"])
        self.assertIsNone(result["chat.stop"]["sourceId"])
        self.assertTrue(result["models.catalog"]["enabled"])

    def test_unchanged_scopes_remain_and_dangerous_stays_hold(self):
        session = self.scope("chat.history", "chat.stop", "system.backup",
                             private=("chat.history", "system.backup"))
        host = self.host()
        host.bind("chat.history", bridge.BoundPort(
            lambda *_: None, lambda: True, "history-owner", 2))
        host.bind("chat.stop", bridge.BoundPort(
            lambda *_: None, lambda: True, "stop-owner", 2))
        host.bind("system.backup", bridge.BoundPort(
            lambda *_: None, lambda: True, "backup-owner", 1))
        caps = host.advertise(session)
        self.assertTrue(caps["chat.history"]["enabled"])
        self.assertTrue(caps["chat.stop"]["enabled"])
        self.assertFalse(caps["system.backup"]["enabled"])

    def test_malformed_callback_scope_fails_closed(self):
        session = self.scope("chat.stop")
        host = self.host()
        def readiness():
            object.__setattr__(session, "allowed", set())
            return True
        host.bind("chat.stop", bridge.BoundPort(
            lambda *_: None, readiness, "stop-owner", 2))
        with self.assertRaises(bridge.HostDenied):
            host.advertise(session)


if __name__ == "__main__":
    unittest.main()
