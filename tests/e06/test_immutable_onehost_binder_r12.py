"""NOX V16: E06 source binding to immutable existing PACK01 OneHost.

Component tests use the real production NoxPackHost and G2OneHostBinder.
Owner ports are deliberately unavailable test fixtures, not a functioning
Ollama, ModelCenter, GPU or E07 Windows release.
"""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from types import MappingProxyType

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/"proposals"/"NOX-PACK01-50"
ADAPTER=ROOT/"coordination"/"e06"/"adapters"
sys.path.insert(0,str(ADAPTER))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

pack=load("nox_real_pack_r12",PACK/"native_bridge.py")
g2=load("nox_real_g2_r12",ADAPTER/"g2_space_mobile.py")
P02=g2.P02_REQUIRED
P03=g2.P03_REQUIRED

class SourceOnlyP02:
    def register(self,host,*,receipt):
        for route in sorted(P02):
            host.bind(route,pack.BoundPort(lambda s,p:{"status":"TEST_ONLY"},
                lambda:False,receipt,2))
        return frozenset(P02)

class SourceOnlyP03:
    def register(self,host,port_type,*,receipt):
        for route in sorted(P03):
            host.bind(route,port_type(lambda s,p:{"status":"TEST_ONLY"},
                lambda:False,receipt,3))
        return frozenset(P03)

class SourceOnlyE05:
    def available(self,_route):
        return False

class FrozenHostBinder(unittest.TestCase):
    def setUp(self):
        catalog=json.loads((PACK/"catalog.json").read_text("utf-8"))
        self.host=pack.NoxPackHost(catalog)
        self.before=self.host.routes
        self.lock=threading.RLock()
        self.p02=SourceOnlyP02()
        self.p03=SourceOnlyP03()
        self.preimage_calls=0

    def bind(self,p02=None,seal=None):
        def original_preimage(source,receipts):
            self.preimage_calls+=1
            return source=="a"*64 and receipts=={"P02":"b"*64,"P03":"c"*64,"P05":"d"*64}
        return g2.G2OneHostBinder(self.host,pack.BoundPort,
            existing_p02=self.p02 if p02 is None else p02,
            existing_p03=self.p03,e05=SourceOnlyE05(),mobile=None,
            existing_p02_voice=None,source_lock_sha256="a"*64 if seal is None else seal,
            owner_receipts_sha256={"P02":"b"*64,"P03":"c"*64,"P05":"d"*64},
            verify_original_preimages=original_preimage,
            existing_host_mutation_lock=self.lock).bind()

    def test_original_single_immutable_registry_can_admit_valid_owner_ports(self):
        self.assertIsInstance(self.host.routes,MappingProxyType)
        result=self.bind()
        self.assertEqual(result,P02|P03)
        self.assertEqual(len(self.host.ports),len(result))
        self.assertIs(self.host.routes,self.before)
        self.assertEqual(self.preimage_calls,2)
        for route in result:
            self.assertFalse(self.host.ports[route].available())

    def test_malicious_original_route_map_swap_rollback_restores_same_object(self):
        baseline=self.p02
        class EvilOwner:
            def register(_,host,*,receipt):
                approved=baseline.register(host,receipt=receipt)
                host.routes={"models.catalog":{"owner":1}}
                return approved
        with self.assertRaises(g2.G2Hold):
            self.bind(p02=EvilOwner())
        self.assertIs(self.host.routes,self.before)
        self.assertIsInstance(self.host.routes,MappingProxyType)
        self.assertFalse(self.host.ports)
        self.assertEqual(self.host.routes["models.catalog"]["owner"],3)

    def test_immutable_registry_rejects_new_direct_owner_edit(self):
        with self.assertRaises(TypeError):
            self.host.routes["models.catalog"]["owner"]=2
        self.assertIs(self.host.routes,self.before)

    def test_p04_readonly_owner_receipt_and_native_readiness(self):
        class ReadOnlyP04:
            def native_permission(self, session, route): return False
            def review_dataset(self, session): return {"status":"TEST_ONLY"}
            def inspect_checkpoint(self, session): return {"status":"TEST_ONLY"}
        def preimage(source, receipts):
            return source=="a"*64 and receipts=={
                "P02":"b"*64, "P03":"c"*64, "P05":"d"*64, "P04":"e"*64}
        kwargs=dict(existing_p02=self.p02, existing_p03=self.p03,
                    e05=SourceOnlyE05(), mobile=None, existing_p02_voice=None,
                    source_lock_sha256="a"*64, verify_original_preimages=preimage,
                    existing_host_mutation_lock=self.lock,
                    p04_readonly=ReadOnlyP04(), p04_ready=lambda name:False)
        with self.assertRaisesRegex(g2.G2Hold, "P04"):
            g2.G2OneHostBinder(self.host, pack.BoundPort,
                owner_receipts_sha256={"P02":"b"*64,"P03":"c"*64,"P05":"d"*64},
                **kwargs).bind()
        self.assertFalse(self.host.ports)
        bound=g2.G2OneHostBinder(self.host, pack.BoundPort,
            owner_receipts_sha256={
                "P02":"b"*64,"P03":"c"*64,"P05":"d"*64,"P04":"e"*64},
            **kwargs).bind()
        self.assertTrue({"datasets.review","training.checkpoints"}.issubset(bound))
        for route in ("datasets.review","training.checkpoints"):
            self.assertEqual(self.host.ports[route].owner,4)
            self.assertEqual(self.host.ports[route].evidence_id,"e"*64)
            self.assertFalse(self.host.ports[route].available())
        self.assertIs(self.host.routes,self.before)

    def test_source_lock_missing_prevents_any_native_mutation(self):
        with self.assertRaises(g2.G2Hold):
            self.bind(seal="invalid")
        self.assertFalse(self.host.ports)
        self.assertIs(self.host.routes,self.before)

if __name__=="__main__":
    unittest.main()
