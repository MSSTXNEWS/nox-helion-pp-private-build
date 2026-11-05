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
            native_submit=lambda scope, job, callback, **kw: self.calls.append((scope, job, callback, kw)) or self.receipt)
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
        self.assertEqual(self.calls[0][3], {})

    def test_resume_uses_the_same_durable_queue_proof(self):
        result = self.port.resume(self.scope, {"job_id": "configured-job"})
        self.assertEqual(result["job_id"], "configured-job")
        self.assertIs(result["execution_completed"], False)
        self.assertEqual(self.calls[-1][3], {"resume": True})

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


class InterruptedOriginalS03Resume(unittest.TestCase):
    """The original owner queue must not strand an interrupted GPU task."""

    def setUp(self):
        from types import SimpleNamespace
        from nox_selfbuilder.onehost_queue import NativeWorkQueue
        class Actor:
            def call(self, fn):
                raise AssertionError("No real SQLite write in route admission test")
        self.scope = SimpleNamespace(tenant="local", principal="owner", chat_id="chat")
        self.job = SimpleNamespace(run_id="native-job")
        self.queue = NativeWorkQueue(Actor(), authorize=lambda *a: True,
                                     stop_requested=lambda: False, stop_epoch=lambda: 1)
        self.queue._forge_jobs[(("local","owner","chat"),"native-job")] = (42,self.job)
        self.calls = []
        self.queue._start = lambda *a, **kw: self.calls.append((a,kw)) or {
            "status":"QUEUED","task_id":42,"durable_s03":True,"execution_completed":False}

    def set_state(self, state, interrupted=False):
        self.queue.get = lambda scope, tid: {"state":state, **(
            {"runtime_state":"INTERRUPTED_HOLD"} if interrupted else {})}

    def test_explicit_owner_resume_only_for_paused_or_interrupted(self):
        from nox_selfbuilder.onehost_queue import NativeQueueHold
        self.set_state("RUNNING", True)
        with self.assertRaisesRegex(NativeQueueHold,"FORGE_START_REQUIRES"):
            self.queue.submit(self.scope,self.job,lambda:None)
        self.assertEqual(self.calls, [])
        self.queue.submit(self.scope,self.job,lambda:None,resume=True)
        a, kw = self.calls.pop()
        self.assertEqual(a[3], "training.resume")
        self.assertEqual(kw["allowed_states"], ("PAUSED",))
        self.assertIs(kw["recover_interrupted"], True)
        self.set_state("RUNNING", False)
        with self.assertRaisesRegex(NativeQueueHold,"FORGE_RESUME_REQUIRES"):
            self.queue.submit(self.scope,self.job,lambda:None,resume=True)
        self.set_state("PAUSED")
        self.queue.submit(self.scope,self.job,lambda:None,resume=True)
        self.assertEqual(self.calls.pop()[0][3], "training.resume")
        self.set_state("QUEUED")
        with self.assertRaisesRegex(NativeQueueHold,"FORGE_RESUME_REQUIRES"):
            self.queue.submit(self.scope,self.job,lambda:None,resume=True)
        self.queue.submit(self.scope,self.job,lambda:None)
        self.assertEqual(self.calls.pop()[0][3], "training.start")

    def test_claim_cannot_recover_without_native_resume_fence(self):
        # This test exercises the actual queue route; the original _start
        # rechecks the native owner grant inside the SQLite CLAIM transaction.
        from nox_selfbuilder.onehost_queue import NativeQueueHold
        self.set_state("RUNNING", True)
        for invalid in (None, 1, "true"):
            with self.assertRaises(PermissionError):
                self.queue.submit(self.scope,self.job,lambda:None,resume=invalid)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
