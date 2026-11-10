"""NOX V16 R11: exact existing owner P03 + PACK01 immutable routes interop.

No new host, fake LLM success, network download, GPU or Windows E07 claim.
Run: python -m unittest discover -s tests/e06 -p 'test_immutable_routes_p03_e06_r11.py' -v
"""
from pathlib import Path
from types import MappingProxyType
import copy
import importlib.util
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/"proposals"/"NOX-PACK01-50"
P03=ROOT/"Packages"/"P03"/"Source"/"python-host"
G2=ROOT/"coordination"/"e06"/"adapters"/"g2_space_mobile.py"


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj

pack=module("nox_real_pack01_r11",PACK/"native_bridge.py")
p03=module("nox_real_p03_r11",P03/"p03_onehost_port.py")


class ExistingOwner2Ollama:
    """No fake model download: only an existing Ollama models() shape."""
    def models(self):
        return []


class ImmutableSourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((PACK/"catalog.json").read_text("utf-8"))
        self.host=pack.NoxPackHost(self.catalog)

    def test_canonical_host_routes_are_immutable_mappings(self):
        self.assertIsInstance(self.host.routes,MappingProxyType)
        self.assertEqual(len(self.host.routes),50)
        self.assertIsInstance(self.host.routes["models.catalog"],MappingProxyType)
        with self.assertRaises(TypeError):
            self.host.routes["models.catalog"]["owner"]=1

    def test_original_p03_owner_registers_with_readonly_route_catalog(self):
        owner=p03.P03OneHostPort(ExistingOwner2Ollama())
        registered=owner.register(self.host,pack.BoundPort,
                                  receipt="c"*64)
        self.assertEqual(registered,frozenset({
            "models.catalog","models.installed","models.digest"}))
        self.assertEqual({self.host.ports[r].owner for r in registered},{3})
        session=pack.NativeSession("tenant","principal","room",
            allowed=frozenset(registered))
        cards=self.host.execute("models.catalog",{},session)["models"]
        self.assertEqual(len(cards),30)
        self.assertTrue(all(x["reviewStatus"]=="REVIEW_REQUIRED" for x in cards))

    def test_e06_route_snapshot_matches_original_without_mutation(self):
        original=self.host.routes
        snapshot={route:copy.deepcopy(dict(descriptor))
                  for route,descriptor in original.items()}
        self.assertEqual(snapshot,original)
        self.assertEqual(len(snapshot),50)
        snapshot["models.catalog"]["owner"]=1
        self.assertEqual(original["models.catalog"]["owner"],3)

    def test_e06_source_uses_safe_mapping_syntax(self):
        s=G2.read_text(encoding="utf-8")
        self.assertIn("from collections.abc import Mapping",s)
        self.assertIn('isinstance(getattr(self.host, "routes", None), Mapping)',s)
        self.assertIn('for route, descriptor in self.host.routes.items()',s)
        self.assertNotIn("frozen_routes = copy.deepcopy(self.host.routes)",s)
        self.assertIn('isinstance(self.host.routes, dict)',s)

    def test_p03_uses_mapping_not_mutable_dict_only(self):
        s=(P03/"p03_onehost_port.py").read_text("utf-8")
        self.assertIn("from collections.abc import Mapping",s)
        self.assertIn("isinstance(host_routes, Mapping)",s)
        self.assertIn("isinstance(host_routes.get(route), Mapping)",s)
        self.assertIn("isinstance(routes.get(route), Mapping)",s)

    def test_malformed_route_map_cannot_be_admitted(self):
        owner=p03.P03OneHostPort(ExistingOwner2Ollama())
        self.host.routes={"models.catalog":{"owner":1}}
        with self.assertRaises(p03.P03PortHold):
            owner.register(self.host,pack.BoundPort,receipt="c"*64)
        self.assertFalse(self.host.ports)

if __name__=="__main__":
    unittest.main()
