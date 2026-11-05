"""D05: original P04 owner queue ACK requires a real, durable S03 claim."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from nox_selfbuilder.background_forge import ForgeJob
from nox_selfbuilder.p04_forge_bridge import ExistingP04NativePorts, ForgeHold


class DurableForgeOwnerAck(unittest.TestCase):
    def setUp(self):
        root = Path("/owner-only-placeholder-not-read")
        self.job = ForgeJob(
            run_id="runtime-run-1", task_id="task-1", base_model_dir=root,
            model_lock=root, model_revision="a" * 40, dataset_manifest=root,
            rights_verifier=root, train_jsonl=root, holdout_jsonl=root,
            output_dir=root)
        self.receipt = {
            "status": "QUEUED", "task_id": 42,
            "durable_s03": True, "execution_completed": False}
        self.calls = []
        class Background:
            def run_one(_, job, **kwargs):
                raise AssertionError("No training is executed by the ACK test")
        self.port = ExistingP04NativePorts(
            Background(),
            job_resolver=lambda scope, job_id: self.job if job_id == "configured-job" else None,
            last_run=lambda scope, job: None,
            native_submit=lambda scope, job, callback: self.calls.append((scope, job, callback)) or self.receipt)
        self.scope = object()

    def test_start_ack_matches_configured_selection_and_durable_s03_only(self):
        result = self.port.start(self.scope, {"job_id": "configured-job"})
        self.assertEqual((result["job_id"], result["task_id"], result["status"]),
                         ("configured-job", 42, "QUEUED"))
        self.assertIs(result["ack"], True)
        self.assertIs(result["durable_s03"], True)
        self.assertIs(result["training_completed"], False)
        self.assertIs(result["weights_updated"], False)
        self.assertIs(result["activation_allowed"], False)
        self.assertEqual(len(self.calls), 1)

    def test_resume_uses_the_same_durable_queue_proof(self):
        result = self.port.resume(self.scope, {"job_id": "configured-job"})
        self.assertEqual(result["job_id"], "configured-job")
        self.assertIs(result["execution_completed"], False)

    def test_holds_on_missing_or_forged_queue_proof(self):
        bad = [
            None, {}, {"status": "COMPLETED", "task_id": 42,
                "durable_s03": True, "execution_completed": False},
            {"status": "QUEUED", "task_id": True,
                "durable_s03": True, "execution_completed": False},
            {"status": "QUEUED", "task_id": 0,
                "durable_s03": True, "execution_completed": False},
            {"status": "QUEUED", "task_id": 42,
                "durable_s03": False, "execution_completed": False},
            {"status": "QUEUED", "task_id": 42,
                "durable_s03": True, "execution_completed": True},
            {**self.receipt, "weights_updated": True},
            {**self.receipt, "ack": True}]
        for receipt in bad:
            with self.subTest(receipt=receipt):
                self.receipt = receipt
                with self.assertRaisesRegex(ForgeHold, "DURABLE_S03_QUEUE_ACK_HOLD"):
                    self.port.start(self.scope, {"job_id": "configured-job"})

    def test_unapproved_renderer_job_never_reaches_submit(self):
        with self.assertRaises(ForgeHold):
            self.port.start(self.scope, {"job_id": "unapproved"})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
