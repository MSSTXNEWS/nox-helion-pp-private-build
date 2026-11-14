"""R47/P03: exact native owner recheck after asynchronous-feeling consent callback.

No model downloads, no real Ollama, no subprocesses or OS operations.
Run: python -m unittest -v test_p03_native_health_after_consent_r47
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortHold

ROUTE = "models.pull"

class OwnerBackend:
    def __init__(self):
        self.online = True
        self.calls = 0
    def available(self):
        return self.online
    def pull(self, session, payload):
        self.calls += 1
        return {"status": "QUEUED"}

def native_session():
    return SimpleNamespace(tenant="t", principal="p", chat_id="c",
                           allowed={ROUTE}, private_approved={ROUTE})

def owner_port(backend, approve):
    port = object.__new__(P03OneHostPort)
    port.backend = backend
    port.native_approve = approve
    return port

class NativeBackendRecheckR47(unittest.TestCase):
    def test_backend_offline_during_consent_never_queues(self):
        owner = OwnerBackend()
        def approve(*_):
            owner.online = False
            return True
        port = owner_port(owner, approve)
        with self.assertRaises(P03PortHold):
            port.execute_backend(native_session(), ROUTE, {"modelTag": "approved"})
        self.assertEqual(owner.calls, 0)

    def test_owner_method_revoked_during_consent_never_uses_cached_handler(self):
        owner = OwnerBackend()
        def approve(*_):
            owner.pull = None
            return True
        port = owner_port(owner, approve)
        with self.assertRaises(P03PortHold):
            port.execute_backend(native_session(), ROUTE, {"modelTag": "approved"})
        self.assertEqual(owner.calls, 0)

    def test_stable_backend_still_queues_once(self):
        owner = OwnerBackend()
        port = owner_port(owner, lambda *_: True)
        self.assertEqual(port.execute_backend(native_session(), ROUTE, {"modelTag": "approved"}),
                         {"status": "QUEUED"})
        self.assertEqual(owner.calls, 1)

if __name__ == "__main__":
    unittest.main()
