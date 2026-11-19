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

class ProgressStallTests(unittest.TestCase):
    def sample(self, counter, at, pid=321, ticks=900):
        return {"native_verified": True, "receipt_sha256": "a" * 64,
                "pid": pid, "start_ticks": ticks, "counter": counter,
                "observed_unix": at, "metric": "optimizer_updates",
                "active": True}

    def test_running_without_useful_progress_needs_diagnosis_not_restart(self):
        before = {"trainer": self.sample(25, 1000)}
        now = {"trainer": self.sample(25, 4000)}
        result = worm.audit_process_progress(now, before, now_unix=4000, grace_seconds=1800)
        self.assertEqual(result["state"], "PROGRESS_AUDITED_ADVISORY_ONLY")
        self.assertEqual(result["suspected_stalls"][0]["action"], "DIAGNOSE_AND_CHANGE_APPROACH")
        self.assertFalse(result["restart_permitted"])
        self.assertEqual(result["mutations"], 0)

    def test_real_optimizer_progress_not_flagged_as_stalled(self):
        result = worm.audit_process_progress(
            {"trainer": self.sample(27, 4000)},
            {"trainer": self.sample(25, 1000)}, now_unix=4000)
        self.assertEqual(result["advancing"][0]["delta"], 2)
        self.assertEqual(result["suspected_stalls"], [])

    def test_pid_replacement_and_long_step_are_not_restarted(self):
        baseline = {"trainer": self.sample(25, 1000)}
        swapped = worm.audit_process_progress(
            {"trainer": self.sample(25, 4000, pid=322)}, baseline, now_unix=4000)
        self.assertEqual(swapped["holds"][0]["reason"], "NEW_PROCESS_BASELINE")
        graceful = worm.audit_process_progress(
            {"trainer": self.sample(25, 1200)}, baseline, now_unix=1200, grace_seconds=1800)
        self.assertEqual(graceful["holds"][0]["reason"], "NORMAL_LONG_STEP_GRACE")

    def test_untrusted_forged_counter_or_no_previous_sample_cannot_trigger_restart(self):
        sample = self.sample(25, 4000)
        untrusted = dict(sample, native_verified=False)
        result = worm.audit_process_progress({"trainer": untrusted}, {"trainer": self.sample(25, 1000)}, now_unix=4000)
        self.assertEqual(result["holds"][0]["reason"], "HOLD_UNVERIFIED_PROGRESS")
        self.assertFalse(result["restart_permitted"])
        missing = worm.audit_process_progress({"trainer": sample}, {}, now_unix=4000)
        self.assertEqual(missing["holds"][0]["reason"], "NEED_TWO_NATIVE_SAMPLES")

    def test_stale_snapshot_cannot_claim_the_trainer_stalled(self):
        before = {"trainer": self.sample(25, 1000)}
        now = {"trainer": self.sample(25, 2900)}
        result = worm.audit_process_progress(now, before, now_unix=4000)
        self.assertEqual(result["suspected_stalls"], [])
        self.assertEqual(result["holds"][0]["reason"], "STALE_NATIVE_PROGRESS_READBACK")

    def test_model_revision_change_requires_fresh_baseline(self):
        before = self.sample(25, 1000)
        before["revision_sha256"] = "a" * 64
        now = self.sample(25, 4000)
        now["revision_sha256"] = "b" * 64
        result = worm.audit_process_progress({"trainer": now}, {"trainer": before},
                                             now_unix=4000)
        self.assertEqual(result["holds"][0]["reason"], "NEW_WORK_REVISION_BASELINE")
        self.assertEqual(result["suspected_stalls"], [])
        del now["revision_sha256"]
        result = worm.audit_process_progress({"trainer": now}, {"trainer": before},
                                             now_unix=4000)
        self.assertEqual(result["holds"][0]["reason"], "HOLD_PROGRESS_REVISION_PROOF")

    def test_queue_audit_emits_stall_report_without_mutating_queue(self):
        observed = observations("RUNNING")
        observed["process_progress_previous"] = {"trainer": self.sample(25, 1000)}
        observed["process_progress_current"] = {"trainer": self.sample(25, 4000)}
        result = worm.audit_native_queue(matrix(), observed, now_unix=4000)
        self.assertEqual(result["process_progress_audit"]["suspected_stalls"][0]["id"], "trainer")
        self.assertEqual(result["native_jobs_restarted"], 0)


if __name__ == "__main__":
    unittest.main()
