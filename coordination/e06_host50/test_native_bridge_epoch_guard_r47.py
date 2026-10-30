"""Owner G2-A R47: stale native port must not execute after revocation.

SOURCE-ONLY; Windows WebView2/ACL/STOP/E07 acceptance is separate.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "proposals" / "NOX-PACK01-50"
spec = importlib.util.spec_from_file_location("r47_existing_native_bridge", SRC / "native_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class NativeOwnerEpochGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((SRC / "catalog.json").read_text(encoding="utf-8"))

    @staticmethod
    def scope():
        routes = frozenset({"system.backup"})
        return bridge.NativeSession("tenant", "principal", "chat", routes, routes)

    def test_probe_or_consent_revocation_never_dispatches_stale_port(self):
        for mode in ("probe_revokes", "consent_revokes", "consent_replaces"):
            with self.subTest(mode=mode):
                called = []
                host = bridge.NoxPackHost(self.catalog)
                def probe():
                    called.append("probe")
                    if mode == "probe_revokes":
                        host.ports.pop("system.backup")
                    return True
                def approve(*_):
                    called.append("approve")
                    if mode == "consent_revokes":
                        host.ports.pop("system.backup")
                    elif mode == "consent_replaces":
                        host.ports["system.backup"] = bridge.BoundPort(
                            lambda *_: called.append("replacement"), lambda: True,
                            "owner-rebound", 1)
                    return True
                host.native_approve = approve
                host.bind("system.backup", bridge.BoundPort(
                    lambda *_: called.append("STALE_EXECUTED"), probe, "owner-original", 1))
                with self.assertRaises(bridge.HostHold):
                    host.execute("system.backup", {}, self.scope())
                self.assertNotIn("STALE_EXECUTED", called)
                self.assertNotIn("replacement", called)

    def test_unchanged_owner_still_executes_after_fresh_consent(self):
        called = []
        host = bridge.NoxPackHost(self.catalog,
            native_approve=lambda *_: called.append("consent") or True)
        host.bind("system.backup", bridge.BoundPort(
            lambda *_: called.append("EXECUTED") or {"ok": True},
            lambda: called.append("probe") or True, "owner-proof", 1))
        self.assertEqual(host.execute("system.backup", {}, self.scope()), {"ok": True})
        self.assertEqual(called, ["probe", "consent", "EXECUTED"])

if __name__ == "__main__":
    unittest.main()
