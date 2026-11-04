"""P03 real owner port: no nullable retry ACK may look like a successful job.
Run in Packages/P03/Source/python-host: python -m unittest -v test_p03_retry_null_ack_r47
No models, network, weight downloads, Windows, or CI needed.
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortHold

class Backend:
    def __init__(self, value):
        self.value, self.calls = value, 0
    def available(self):
        return True
    def retry(self, _session, _payload):
        self.calls += 1
        return self.value

class P03NullableOwnerAckR47(unittest.TestCase):
    def make(self, result):
        port = object.__new__(P03OneHostPort)
        port.backend = Backend(result)
        port.native_approve = lambda *_: True
        session = SimpleNamespace(tenant="t", principal="p", chat_id="c",
                                  allowed={"models.retry"},
                                  private_approved={"models.retry"})
        return port, session

    def test_missing_retry_ack_holds_without_double_execution(self):
        port, session = self.make(None)
        with self.assertRaises(P03PortHold):
            port.execute_backend(session, "models.retry", {"jobId": "existing"})
        self.assertEqual(port.backend.calls, 1)

    def test_confirmed_retry_job_passthrough(self):
        result = {"jobId": "existing", "status": "QUEUED"}
        port, session = self.make(result)
        self.assertEqual(port.execute_backend(session, "models.retry", {"jobId": "existing"}), result)
        self.assertEqual(port.backend.calls, 1)

    def test_explicit_false_not_promoted_to_success(self):
        port, session = self.make(False)
        with self.assertRaisesRegex(P03PortHold, "non-object acknowledgement"):
            port.execute_backend(session, "models.retry", {"jobId": "existing"})
        self.assertEqual(port.backend.calls, 1)

if __name__ == "__main__":
    unittest.main()
