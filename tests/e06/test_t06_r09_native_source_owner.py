"""T06 R09 one-target source regression for native source and owner ports.
Real local classes are imported; mocks never count as installed services.
"""
import unittest
import json
import sys
import importlib.util
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "proposals" / "NOX-PACK01-50"
G2 = ROOT / "coordination" / "e06" / "adapters"
WORKER = ROOT / "Packages" / "P02" / "worker-python"
sys.path.insert(0, str(G2))
sys.path.insert(0, str(WORKER))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

pack = load("nox_r09_existing_host", PACK / "native_bridge.py")
g2 = load("nox_r09_existing_binder", G2 / "g2_space_mobile.py")
from p02_owner_route_ports import OwnerTwoPorts


class T06NativeOwnerSource(unittest.TestCase):
    def test_native_owner_bindings_and_signed_source_hold(self):
        catalog = json.loads((PACK / "catalog.json").read_text(encoding="utf-8"))
        host = pack.NoxPackHost(catalog)
        original_routes = host.routes
        class BaseP02:
            def register(self, dispatcher, *, receipt):
                for route in sorted(g2.P02_REQUIRED):
                    dispatcher.bind(route, pack.BoundPort(
                        lambda s, p: {"status": "TEST_ONLY"}, lambda: False,
                        receipt, 2))
                return frozenset(g2.P02_REQUIRED)
        class BaseP03:
            def register(self, dispatcher, port_type, *, receipt):
                for route in sorted(g2.P03_REQUIRED):
                    dispatcher.bind(route, port_type(
                        lambda s, p: {"status": "TEST_ONLY"}, lambda: False,
                        receipt, 3))
                return frozenset(g2.P03_REQUIRED)
        class E05:
            def available(self, route): return False
        sources = {"P02": "b"*64, "P03": "c"*64, "P05": "d"*64}
        source = "a"*64
        extra = object.__new__(OwnerTwoPorts)
        extra.route_methods = lambda: {
            route: (lambda scope, payload, r=route: {"route": r})
            for route in ("chat.rag", "chat.voice", "calls.history")}
        extra.available = lambda route: False
        opts = dict(
            existing_p02=BaseP02(), existing_p03=BaseP03(),
            e05=E05(), mobile=None, existing_p02_voice=None,
            source_lock_sha256=source, owner_receipts_sha256=sources,
            verify_original_preimages=lambda s, r: s == source and r == sources,
            existing_host_mutation_lock=RLock())
        with self.assertRaises(g2.G2Hold):
            g2.G2OneHostBinder(host, pack.BoundPort,
                owner2_additional_ports=extra, **opts)
        self.assertFalse(host.ports)
        bound = g2.G2OneHostBinder(
            host, pack.BoundPort, owner2_additional_ports=extra,
            native_scope_from_session=lambda session: session, **opts).bind()
        self.assertEqual(bound, g2.P02_REQUIRED | g2.P03_REQUIRED |
            {"chat.rag", "chat.voice", "calls.history"})
        self.assertIs(host.routes, original_routes)
        for route in ("chat.rag", "chat.voice", "calls.history"):
            self.assertEqual(host.ports[route].owner, 2)
            self.assertFalse(host.ports[route].available())

        # Regression: the legacy voice path and new OwnerTwoPorts can both
        # advertise calls.history. Reuse exactly one route on the same host.
        class LegacyVoice:
            def available(self, route): return route == "calls.history"
            def call_history(self, session, payload): return {"calls": []}

        legacy = LegacyVoice()
        dual_host = pack.NoxPackHost(catalog)
        dual_options = dict(opts, existing_p02_voice=legacy)
        dual_routes = g2.G2OneHostBinder(
            dual_host, pack.BoundPort, owner2_additional_ports=extra,
            native_scope_from_session=lambda session: session,
            **dual_options).bind()
        self.assertEqual(dual_routes, bound)
        self.assertEqual(dual_host.ports["calls.history"].owner, 2)
        self.assertEqual(len(dual_host.ports), len(dual_routes))
        self.assertFalse(dual_host.ports["calls.history"].available())

        # Backward compatibility: without OwnerTwoPorts, the original voice
        # adapter still owns calls.history; no function is silently removed.
        legacy_host = pack.NoxPackHost(catalog)
        legacy_routes = g2.G2OneHostBinder(
            legacy_host, pack.BoundPort, **dual_options).bind()
        self.assertIn("calls.history", legacy_routes)
        self.assertNotIn("chat.rag", legacy_routes)
        self.assertTrue(legacy_host.ports["calls.history"].available())


if __name__ == "__main__":
    unittest.main()
