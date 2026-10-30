"""G2-A R42 focused SOURCE-ONLY native dangerous-consent order regression."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"proposals"/"NOX-PACK01-50"
spec=importlib.util.spec_from_file_location("r42_existing_native_bridge", SRC/"native_bridge.py")
bridge=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=bridge
spec.loader.exec_module(bridge)

class ConsentProbeOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((SRC/"catalog.json").read_text("utf-8"))

    def scope(self, approved=True):
        r=frozenset({"system.backup"}) if approved else frozenset()
        return bridge.NativeSession("tenant","person","chat",allowed=r,private_approved=r)

    def test_probe_revokes_native_approval(self):
        calls=[]; current={"allow":True}
        def probe():
            calls.append("probe"); current["allow"]=False; return True
        def approve(*args):
            calls.append("approve"); return current["allow"]
        host=bridge.NoxPackHost(self.catalog,native_approve=approve)
        host.bind("system.backup",bridge.BoundPort(lambda s,p:calls.append("EXECUTED"),probe,"owner-proof",1))
        with self.assertRaises(bridge.HostDenied):
            host.execute("system.backup",{},self.scope())
        self.assertEqual(calls,["probe","approve"])

    def test_unavailable_never_prompts_or_executes(self):
        calls=[]
        def probe():
            calls.append("probe"); return False
        host=bridge.NoxPackHost(self.catalog,native_approve=lambda *args:calls.append("approve") or True)
        host.bind("system.backup",bridge.BoundPort(lambda s,p:calls.append("EXECUTED"),probe,"owner-proof",1))
        with self.assertRaises(bridge.HostHold):
            host.execute("system.backup",{},self.scope())
        self.assertEqual(calls,["probe"])

    def test_happy_path_and_scope_deny(self):
        calls=[]
        def probe():
            calls.append("probe"); return True
        def approve(*args):
            calls.append("approve"); return True
        def done(s,p):
            calls.append("dispatch"); return {"sourceOnly":True}
        host=bridge.NoxPackHost(self.catalog,native_approve=approve)
        host.bind("system.backup",bridge.BoundPort(done,probe,"owner-proof",1))
        self.assertEqual(host.execute("system.backup",{},self.scope()),{"sourceOnly":True})
        self.assertEqual(calls,["probe","approve","dispatch"])
        calls.clear()
        with self.assertRaises(bridge.HostDenied):
            host.execute("system.backup",{},self.scope(False))
        self.assertEqual(calls,[])

if __name__=="__main__":
    unittest.main()
