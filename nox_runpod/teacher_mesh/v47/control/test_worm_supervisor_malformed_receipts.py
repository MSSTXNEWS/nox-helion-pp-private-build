"""Regression tests: hostile/corrupt native receipts must not crash OneHost audit."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name("worm_supervisor.py")
spec = importlib.util.spec_from_file_location("nox_worm_supervisor_tested", MODULE)
worm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worm)

def matrix():
    return {"tasks": [{"task_id": f"NOX-V46-{n:02d}"} for n in range(1, 61)]}

def observations(state):
    return {
        "native_verified": True,
        "s03_native_verified": True,
        "native_queue_verified": True,
        "stop_active": False,
        "student_serving": True,
        "task_status": {
            "NOX-V46-01": {
                "task_id": "NOX-V46-01",
                "native_verified": True,
                "receipt_sha256": "a" * 64,
                "state": state,
                "job_id": "native-job-01",
            }
        },
    }

class MalformedReceiptTests(unittest.TestCase):
    def test_unhashable_state_values_fail_closed(self):
        for malformed in ([], {}, {"status": "RUNNING"}, ["FAILED"]):
            with self.subTest(value=malformed):
                report = worm.audit_native_queue(matrix(), observations(malformed), now_unix=1730000000)
                self.assertEqual(report["state"], "NATIVE_QUEUE_RECONCILED_PROPOSALS_ONLY")
                self.assertEqual(report["untrusted_count"], 1)
                self.assertEqual(report["native_jobs_started"], 0)
                self.assertEqual(report["native_jobs_restarted"], 0)
                self.assertEqual(report["retry_eligible_proposals"], [])
                self.assertIn("NOX-V46-01", report["protected_task_ids"])

    def test_unknown_state_is_protected(self):
        report = worm.audit_native_queue(matrix(), observations("UNEXPECTED"), now_unix=1730000000)
        self.assertEqual(report["untrusted_count"], 1)
        self.assertIn("NOX-V46-01", report["protected_task_ids"])

    def test_valid_failed_receipt_without_recovery_proof_cannot_restart(self):
        report = worm.audit_native_queue(matrix(), observations("FAILED"), now_unix=1730000000)
        self.assertEqual(report["native_registered_verified"], 1)
        self.assertEqual(report["retry_eligible_proposals"], [])

    def test_missing_native_gates_halt_audit(self):
        observed = observations("RUNNING")
        observed["stop_active"] = True
        report = worm.audit_native_queue(matrix(), observed, now_unix=1730000000)
        self.assertEqual(report["state"], "HOLD_NATIVE_OWNER_STOP_S03_OR_CHAT")

if __name__ == "__main__":
    unittest.main()
