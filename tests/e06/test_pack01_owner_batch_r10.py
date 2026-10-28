"""NOX V16: seven P01 source routes bind ONLY to existing native owner methods.
Run: python -m unittest discover -s tests/e06 -p test_pack01_owner_batch_r10.py -v

Mock owner methods exercise actual NoxPackHost/bind_owner_methods. They do not
provide Windows media, browsers, PC control or E07 runtime acceptance.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/"proposals"/"NOX-PACK01-50"
spec=importlib.util.spec_from_file_location("nox_native_owner_batch_r10", PACK/"native_bridge.py")
bridge=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=bridge
spec.loader.exec_module(bridge)

ROUTES={
    "media.player":"media_player",
    "media.subtitles":"media_subtitles",
    "browser.open":"browser_open",
    "browser.bookmarks":"browser_bookmarks",
    "system.update":"system_update",
    "system.backup":"system_backup",
    "system.pc_control":"system_pc_control",
}
RECEIPT="b"*64

class ExistingOwnerOne:
    def __init__(self):
        self.calls=[]
    def _call(self,route,s,p):
        self.calls.append((route,s.tenant,dict(p)))
        return {"owner":1,"route":route,"accepted_in_test":True}
    def media_player(self,s,p): return self._call("media.player",s,p)
    def media_subtitles(self,s,p): return self._call("media.subtitles",s,p)
    def browser_open(self,s,p): return self._call("browser.open",s,p)
    def browser_bookmarks(self,s,p): return self._call("browser.bookmarks",s,p)
    def system_update(self,s,p): return self._call("system.update",s,p)
    def system_backup(self,s,p): return self._call("system.backup",s,p)
    def system_pc_control(self,s,p): return self._call("system.pc_control",s,p)

class NativeOwnerBatchTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((PACK/"catalog.json").read_text(encoding="utf-8"))
        self.host=bridge.NoxPackHost(self.catalog,native_approve=lambda s,r,p:True)
        self.owner=ExistingOwnerOne()
        self.session=bridge.NativeSession("test_tenant","person","room",
            allowed=frozenset(ROUTES),
            private_approved=frozenset(ROUTES))

    def register(self, methods=None, *, receipt=RECEIPT, probe=lambda:True, owner=1):
        return bridge.bind_owner_methods(
            self.host, owner, self.owner, ROUTES if methods is None else methods,
            receipt=receipt, probe=probe)

    def test_all_seven_native_methods_bound_to_single_existing_host(self):
        result=self.register()
        self.assertEqual(result,frozenset(ROUTES))
        self.assertEqual(set(self.host.ports),set(ROUTES))
        self.assertEqual({p.owner for p in self.host.ports.values()},{1})
        self.assertEqual({p.evidence_id for p in self.host.ports.values()},{RECEIPT})

    def test_real_provider_call_still_required_before_success(self):
        self.register()
        value=self.host.execute("media.player",{"request":"native-selected-media"},self.session)
        self.assertEqual(value["route"],"media.player")
        self.assertEqual(self.owner.calls[0][0],"media.player")

    def test_missing_last_method_cannot_leave_first_six_bound(self):
        methods={**ROUTES,"system.pc_control":"missing_method"}
        with self.assertRaises(bridge.HostHold):
            self.register(methods)
        self.assertFalse(self.host.ports)

    def test_cross_owner_route_fails_before_any_write(self):
        methods={**ROUTES,"chat.voice":"media_player"}
        with self.assertRaises(bridge.HostDenied):
            self.register(methods)
        self.assertFalse(self.host.ports)

    def test_no_handler_replacement_or_second_port(self):
        pre=bridge.BoundPort(lambda s,p:{"previous":True},lambda:True,RECEIPT,1)
        self.host.bind("media.player",pre)
        with self.assertRaises(bridge.HostDenied):
            self.register()
        self.assertIs(self.host.ports["media.player"],pre)
        self.assertEqual(len(self.host.ports),1)

    def test_dangerous_action_requires_real_native_consent_provider(self):
        self.host.native_approve=None
        with self.assertRaises(bridge.HostHold):
            self.register()
        self.assertFalse(self.host.ports)

    def test_unverified_owner_receipt_cannot_bind(self):
        with self.assertRaises(bridge.HostHold):
            self.register(receipt="placeholder")
        self.assertFalse(self.host.ports)

    def test_bool_owner_does_not_masquerade_as_p01(self):
        with self.assertRaises(bridge.HostDenied):
            self.register(owner=True)
        self.assertFalse(self.host.ports)

    def test_missing_owner_native_health_is_hold(self):
        with self.assertRaises(bridge.HostHold):
            self.register(probe=None)
        self.assertFalse(self.host.ports)

    def test_unavailable_provider_does_not_enable_route(self):
        self.register(probe=lambda:False)
        self.assertFalse(self.host.advertise(self.session)["media.player"]["enabled"])
        with self.assertRaises(bridge.HostHold):
            self.host.execute("media.player",{},self.session)
        self.assertFalse(self.owner.calls)

    def test_no_native_sensitive_consent_means_denied(self):
        self.register()
        scope=bridge.NativeSession("test_tenant","person","room",
            allowed=frozenset(ROUTES),private_approved=frozenset())
        with self.assertRaises(bridge.HostDenied):
            self.host.execute("media.player",{},scope)
        self.assertFalse(self.owner.calls)

    def test_bind_writes_then_raises_restores_existing_registry(self):
        previous=bridge.BoundPort(lambda s,p:{"prior":True},lambda:True,"prior",2)
        self.host.bind("chat.history",previous)
        original=self.host.bind
        def interrupted(route,port):
            original(route,port)
            if route=="browser.bookmarks":
                raise RuntimeError("simulated write-then-error")
        self.host.bind=interrupted
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(set(self.host.ports),{"chat.history"})
        self.assertIs(self.host.ports["chat.history"],previous)

    def test_method_names_must_be_trusted_literals(self):
        methods={"media.player":"__class__.__mro__"}
        with self.assertRaises(bridge.HostDenied):
            self.register(methods)
        self.assertFalse(self.host.ports)

    def test_preflight_provider_getattr_failure_does_not_partial_bind(self):
        class Faulty:
            def media_player(self,s,p): return {"ok":True}
            def __getattr__(self,name):
                raise RuntimeError("native callback discovery failed")
        self.owner=Faulty()
        with self.assertRaises(bridge.HostHold):
            self.register()
        self.assertFalse(self.host.ports)


    def test_failed_batch_does_not_erase_other_owner_registration(self):
        external=bridge.BoundPort(
            lambda s,p:{"unrelated":True},lambda:True,
            "already-reviewed",2)
        original=self.host.bind
        def interrupted(route,port):
            original(route,port)
            if route=="media.subtitles":
                original("chat.history",external)
            if route=="browser.bookmarks":
                raise RuntimeError("batch interrupted after separate owner's registration")
        self.host.bind=interrupted
        with self.assertRaises(RuntimeError):
            self.register()
        self.assertEqual(set(self.host.ports),{"chat.history"})
        self.assertIs(self.host.ports["chat.history"],external)


    def test_read_only_mappingproxy_from_latest_native_owner_is_supported(self):
        from types import MappingProxyType
        self.host.routes=MappingProxyType({
            key:MappingProxyType(dict(value))
            for key,value in self.host.routes.items()})
        self.assertEqual(self.register(),frozenset(ROUTES))
        self.assertEqual(len(self.host.ports),7)
        with self.assertRaises(TypeError):
            self.host.routes["media.player"]["owner"]=2

if __name__=="__main__":
    unittest.main()
