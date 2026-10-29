from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "proposals" / "NOX-PACK01-50"))
from native_bridge import (APPROVED_NATIVE_POLICY, NoxPackHost, NativeSession,
                           BoundPort, HostDenied, HostHold)

import unittest
class AdvertiseScopeRegression(unittest.TestCase):
    def host(self):
        catalog = {"version":"NOX-INTEGRATION-PACK-01","actions":[{"taskId":f"NIP01-{i:02d}","routeId":r,"owner":o,"risk":risk} for i,(r,o,risk) in enumerate(APPROVED_NATIVE_POLICY,1)]}
        return NoxPackHost(catalog)
    def test_callback_scope_fence(self):
        scopes=frozenset({"helion.chat","chat.history"})
        changes=[("tenant","other"),("principal","other"),("chat_id","other"),
                 ("allowed",frozenset()),("private_approved",frozenset({"chat.history"})),
                 ("allowed",set(scopes))]
        for field,value in changes:
            for fail in (False,True):
                with self.subTest(field=field,fail=fail):
                    host=self.host()
                    session=NativeSession("t","p","c",scopes)
                    def probe():
                        object.__setattr__(session,field,value)
                        if fail: raise RuntimeError("probe failed after mutation")
                        return True
                    host.bind("helion.chat",BoundPort(lambda s,p:None,probe,"receipt",2))
                    with self.assertRaises(HostDenied):
                        host.advertise(session)
        for ready in (True,False,"error"):
            with self.subTest(unchanged=ready):
                host=self.host()
                session=NativeSession("t","p","c",scopes)
                def probe():
                    if ready=="error": raise RuntimeError("ordinary unavailable")
                    return ready
                host.bind("helion.chat",BoundPort(lambda s,p:None,probe,"receipt",2))
                result=host.advertise(session)
                self.assertEqual(result["helion.chat"]["enabled"],ready is True)
                self.assertEqual(result["helion.chat"]["sourceId"],"receipt" if ready is True else None)
                self.assertEqual(len(result),50)

    def test_callback_cannot_revoke_or_replace_owner_port(self):
        for operation in ("advertise", "execute"):
            for change in ("remove", "replace"):
                for fail in (False, True):
                    with self.subTest(operation=operation, change=change, fail=fail):
                        host=self.host()
                        session=NativeSession("t","p","c",frozenset({"chat.stop"}))
                        calls=[]
                        replacement=BoundPort(lambda s,p:calls.append("replacement"),
                                              lambda:True,"replacement-receipt",2)
                        def probe():
                            if change=="remove":
                                del host.ports["chat.stop"]
                            else:
                                host.ports["chat.stop"]=replacement
                            if fail:
                                raise RuntimeError("probe failed after rebinding")
                            return True
                        host.bind("chat.stop",BoundPort(
                            lambda s,p:calls.append("original"),probe,"receipt",2))
                        with self.assertRaises(HostHold):
                            if operation=="advertise":
                                host.advertise(session)
                            else:
                                host.execute("chat.stop",{},session)
                        self.assertEqual(calls,[])
        host=self.host()
        session=NativeSession("t","p","c",frozenset({"chat.stop"}))
        calls=[]
        host.bind("chat.stop",BoundPort(lambda s,p:calls.append("stop") or
                                      {"stopRequested":True},lambda:True,"receipt",2))
        self.assertTrue(host.advertise(session)["chat.stop"]["enabled"])
        self.assertEqual(host.execute("chat.stop",{},session),{"stopRequested":True})
        self.assertEqual(calls,["stop"])

    def test_later_probe_cannot_revoke_earlier_advertisement(self):
        host=self.host()
        session=NativeSession("t","p","c",frozenset({"helion.chat","chat.stop"}))
        host.bind("helion.chat",BoundPort(lambda s,p:None,lambda:True,"chat-receipt",2))
        def stop_probe():
            del host.ports["helion.chat"]
            return True
        host.bind("chat.stop",BoundPort(lambda s,p:None,stop_probe,"stop-receipt",2))
        with self.assertRaises(HostHold):
            host.advertise(session)

unittest.main()
