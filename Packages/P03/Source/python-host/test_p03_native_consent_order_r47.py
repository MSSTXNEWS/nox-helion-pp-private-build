"""R47 exact owner3 module regression: no consent before readiness, no stale native scope."""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied, P03PortHold

ROUTE = "models.pull"
def session():
    return SimpleNamespace(tenant="t", principal="p", chat_id="c",
        allowed={ROUTE}, private_approved={ROUTE})
class Backend:
    def __init__(self, ready=True): self.ready=ready; self.calls=0
    def available(self): return self.ready
    def pull(self, session, payload): self.calls+=1; return {"status":"QUEUED"}
def port(backend, approve):
    p=object.__new__(P03OneHostPort)
    p.backend=backend; p.native_approve=approve
    return p
class NativeConsentR47(unittest.TestCase):
    def test_unavailable_backend_does_not_prompt(self):
        b=Backend(False); approvals=[]
        p=port(b, lambda *args: approvals.append(True) or True)
        with self.assertRaises(P03PortHold): p.execute_backend(session(), ROUTE, {})
        self.assertEqual(approvals, []); self.assertEqual(b.calls, 0)
    def test_revoked_consent_cannot_enqueue(self):
        b=Backend()
        def approve(s, *_): s.private_approved.clear(); return True
        p=port(b, approve)
        with self.assertRaises(P03PortDenied): p.execute_backend(session(), ROUTE, {})
        self.assertEqual(b.calls, 0)
    def test_backend_replacement_cannot_use_stale_handler(self):
        b=Backend(); newer=Backend(); p=port(b, lambda *_: True)
        def approve(*_): p.backend=newer; return True
        p.native_approve=approve
        with self.assertRaises(P03PortHold): p.execute_backend(session(), ROUTE, {})
        self.assertEqual((b.calls,newer.calls),(0,0))
    def test_consent_callback_mutated_model_tag_denied(self):
        b=Backend()
        def approve(_session, _route, payload):
            payload["modelTag"]="unapproved"; return True
        p=port(b, approve)
        with self.assertRaises(P03PortDenied):
            p.execute_backend(session(), ROUTE, {"modelTag":"approved"})
        self.assertEqual(b.calls, 0)
    def test_consent_callback_nested_payload_mutation_denied(self):
        b=Backend()
        def approve(_session, _route, payload):
            payload["options"]["digest"]="changed"; return True
        p=port(b, approve)
        with self.assertRaises(P03PortDenied):
            p.execute_backend(session(), ROUTE, {"modelTag":"approved","options":{"digest":"original"}})
        self.assertEqual(b.calls, 0)
    def test_unmodified_approved_payload_still_queues(self):
        b=Backend(); p=port(b, lambda *_: True)
        self.assertEqual(p.execute_backend(session(), ROUTE, {"modelTag":"approved"}), {"status":"QUEUED"})
        self.assertEqual(b.calls, 1)
if __name__=="__main__": unittest.main()
