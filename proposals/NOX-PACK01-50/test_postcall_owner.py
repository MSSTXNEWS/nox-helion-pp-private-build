"""R60 · exact native owner continuity: only existing PACK01, no P02/mock runtime."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nox_pack01_postcall",ROOT/"native_bridge.py")
pack=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=pack
spec.loader.exec_module(pack)

class NativeOwnerContinuity(unittest.TestCase):
    def setUp(self):
        self.host=pack.NoxPackHost(json.loads((ROOT/"catalog.json").read_text("utf-8")))
        self.scope=pack.NativeSession("tenant","principal","conversation",
                                      allowed=frozenset({"chat.model"}))

    def bind(self,callback):
        self.host.bind("chat.model",pack.BoundPort(
            callback,lambda:True,"OWNER2-PINNED-READONLY",2))

    def test_owner_removed_during_callback_never_returns_stale_result(self):
        def revoked(scope,payload):
            self.host.ports.pop("chat.model")
            return {"models":["MUST_NOT_LEAK"]}
        self.bind(revoked)
        with self.assertRaisesRegex(pack.HostHold,"owner changed"):
            self.host.execute("chat.model",{},self.scope)

    def test_owner_rebound_during_callback_never_returns_stale_result(self):
        def changed(scope,payload):
            self.host.ports["chat.model"]=pack.BoundPort(
                lambda s,p:{"models":[]},lambda:True,"DIFFERENT_OWNER_INSTANCE",2)
            return {"models":["MUST_NOT_LEAK"]}
        self.bind(changed)
        with self.assertRaisesRegex(pack.HostHold,"owner changed"):
            self.host.execute("chat.model",{},self.scope)

    def test_unchanged_owner_returns_actual_result(self):
        self.bind(lambda scope,payload:{"models":["existing-owner-model"]})
        self.assertEqual(self.host.execute("chat.model",{},self.scope),
                         {"models":["existing-owner-model"]})

if __name__=="__main__":
    unittest.main()
