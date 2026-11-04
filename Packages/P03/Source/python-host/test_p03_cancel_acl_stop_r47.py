"""P03 STOP/cancel: match canonical PACK01 safe risk while preserving ACL.
Run: python -m unittest -v test_p03_cancel_acl_stop_r47
No Ollama, model weights, Windows, network or second host needed.
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied, P03PortHold, SENSITIVE

class ExistingOwnerWorker:
    def __init__(self):
        self.cancel_calls = 0
        self.pull_calls = 0

    def available(self):
        return True

    def cancel(self, _session, _payload):
        self.cancel_calls += 1
        return {"jobId": "existing", "status": "CANCEL_REQUESTED"}

    def pull(self, _session, _payload):
        self.pull_calls += 1
        return {"jobId": "unexpected"}

class P03CancelStopR47(unittest.TestCase):
    def make(self):
        port = object.__new__(P03OneHostPort)
        port.backend = ExistingOwnerWorker()
        approvals = []
        port.native_approve = lambda *_: approvals.append("called") or True
        return port, approvals

    @staticmethod
    def session(*routes):
        return SimpleNamespace(
            tenant="tenant", principal="principal", chat_id="chat",
            allowed=frozenset(routes), private_approved=frozenset())

    def test_host_safe_cancel_executes_with_acl_but_without_pull_consent(self):
        port, approvals = self.make()
        result = port.execute_backend(
            self.session("models.cancel"), "models.cancel", {"jobId": "existing"})
        self.assertEqual(result, {"jobId": "existing", "status": "CANCEL_REQUESTED"})
        self.assertEqual(port.backend.cancel_calls, 1)
        self.assertEqual(approvals, [])
        self.assertNotIn("models.cancel", SENSITIVE)

    def test_boolean_cancel_is_not_a_real_queue_ack(self):
        port, approvals = self.make()
        def legacy_cancel(_session, _payload):
            port.backend.cancel_calls += 1
            return True
        port.backend.cancel = legacy_cancel
        with self.assertRaisesRegex(P03PortHold, "non-object acknowledgement"):
            port.execute_backend(self.session("models.cancel"),
                                 "models.cancel", {"jobId": "existing"})
        self.assertEqual(port.backend.cancel_calls, 1)
        self.assertEqual(approvals, [])

    def test_unscoped_cancel_cannot_touch_worker(self):
        port, approvals = self.make()
        with self.assertRaises(P03PortDenied):
            port.execute_backend(self.session(), "models.cancel", {"jobId": "existing"})
        self.assertEqual(port.backend.cancel_calls, 0)
        self.assertEqual(approvals, [])

    def test_pull_requires_fresh_native_permission(self):
        port, approvals = self.make()
        with self.assertRaises(P03PortDenied):
            port.execute_backend(self.session("models.pull"), "models.pull",
                                 {"modelTag": "unreviewed"})
        self.assertEqual(port.backend.pull_calls, 0)
        self.assertEqual(approvals, [])
        for route in ("models.pull", "models.gguf.import", "models.retry"):
            self.assertIn(route, SENSITIVE)

if __name__ == "__main__":
    unittest.main()
