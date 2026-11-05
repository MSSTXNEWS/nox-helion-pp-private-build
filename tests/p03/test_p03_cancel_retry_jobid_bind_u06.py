"""Exact native job-identity protection for existing P03 cancel/retry ports."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages" / "P03" / "Source" / "python-host" / "p03_onehost_port.py"
spec = importlib.util.spec_from_file_location("p03_owner_jobid_u06", SOURCE)
assert spec and spec.loader
p03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p03)

class Owner:
    def __init__(self, result):
        self.result, self.calls = result, 0
    def available(self):
        return True
    def cancel(self, _session, _args):
        self.calls += 1
        return self.result
    def retry(self, _session, _args):
        self.calls += 1
        return self.result

def setup(route, result):
    port = p03.P03OneHostPort.__new__(p03.P03OneHostPort)
    port.backend = Owner(result)
    port.native_approve = lambda *_: True
    scope = SimpleNamespace(tenant="tenant", principal="owner", chat_id="chat",
                            allowed=frozenset({route}),
                            private_approved=frozenset({route}))
    return port, scope

class ExactOwnerJobAckTests(unittest.TestCase):
    def test_cancel_wrong_job_ack_holds(self):
        port, scope = setup("models.cancel", {"jobId": "other", "status": "CANCEL_REQUESTED"})
        with self.assertRaisesRegex(p03.P03PortHold, "identity mismatch"):
            port.execute_backend(scope, "models.cancel", {"jobId": "existing"})
        self.assertEqual(port.backend.calls, 1)

    def test_retry_wrong_job_ack_holds(self):
        port, scope = setup("models.retry", {"jobId": "other", "status": "QUEUED"})
        with self.assertRaisesRegex(p03.P03PortHold, "identity mismatch"):
            port.execute_backend(scope, "models.retry", {"jobId": "existing"})
        self.assertEqual(port.backend.calls, 1)

    def test_cancel_missing_or_unsafe_job_is_denied_before_mutation(self):
        for job_id in (None, "", " two ", "with/slash", True, 42, "x"*129):
            with self.subTest(job_id=job_id):
                port, scope = setup("models.cancel", {"jobId": "existing", "status": "CANCEL_REQUESTED"})
                args = {} if job_id is None else {"jobId": job_id}
                with self.assertRaises(p03.P03PortDenied):
                    port.execute_backend(scope, "models.cancel", args)
                self.assertEqual(port.backend.calls, 0)

    def test_retry_missing_job_no_native_consent_or_mutation(self):
        port, scope = setup("models.retry", {"jobId": "existing", "status": "QUEUED"})
        consent_calls = []
        port.native_approve = lambda *_: consent_calls.append(True) or True
        with self.assertRaises(p03.P03PortDenied):
            port.execute_backend(scope, "models.retry", {})
        self.assertEqual(port.backend.calls, 0)
        self.assertEqual(consent_calls, [])

    def test_cancel_unbound_ack_denied(self):
        port, scope = setup("models.cancel", {"status": "CANCEL_REQUESTED"})
        with self.assertRaisesRegex(p03.P03PortHold, "identity mismatch"):
            port.execute_backend(scope, "models.cancel", {"jobId": "existing"})

    def test_valid_cancel_preserves_existing_backend_reply(self):
        receipt = {"jobId": "existing", "status": "CANCEL_REQUESTED"}
        port, scope = setup("models.cancel", receipt)
        self.assertEqual(port.execute_backend(scope, "models.cancel", {"jobId": "existing"}), receipt)
        self.assertEqual(port.backend.calls, 1)

    def test_valid_retry_preserves_existing_backend_reply(self):
        receipt = {"jobId": "existing", "status": "QUEUED"}
        port, scope = setup("models.retry", receipt)
        self.assertEqual(port.execute_backend(scope, "models.retry", {"jobId": "existing"}), receipt)
        self.assertEqual(port.backend.calls, 1)

if __name__ == "__main__":
    unittest.main()
