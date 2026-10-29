from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "proposals" / "NOX-PACK01-50"))
from native_bridge import (APPROVED_NATIVE_POLICY, NoxPackHost, NativeSession,
                           BoundPort, HostDenied)

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
unittest.main()
