"""D05: original P04 owner queue ACK requires a real, durable S03 claim."""
from pathlib import Path
from dataclasses import asdict
import hashlib
import json
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
            def verified_receipt(_, job):
                # Trusted native P04 returns this only after archive/hash checks.
                return {"status": "PAUSED"}
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

    def test_resume_requires_verified_paused_checkpoint_before_queue_claim(self):
        # Interrupted RUNNING resume without original P04 evidence must not
        # consume the owner's existing SQLite S03 task with a terminal HOLD.
        for proof in (None, {}, {"status": "STOPPED"},
                      {"status": "COMPLETED"}, {"status": "HOLD"}):
            with self.subTest(proof=proof):
                self.port.background.verified_receipt = lambda job, p=proof: p
                with self.assertRaisesRegex(ForgeHold, "RESUME_PAUSED_PROOF_HOLD"):
                    self.port.resume(self.scope, {"job_id": "configured-job"})
                self.assertEqual(self.calls, [])
        for error in (FileNotFoundError, ValueError, ForgeHold, PermissionError):
            with self.subTest(error=error):
                def missing(job, error=error):
                    raise error("P04_CHECKPOINT_MISSING_OR_INVALID")
                self.port.background.verified_receipt = missing
                with self.assertRaisesRegex(ForgeHold, "RESUME_PAUSED_PROOF_HOLD"):
                    self.port.resume(self.scope, {"job_id": "configured-job"})
                self.assertEqual(self.calls, [])
        self.port.background.verified_receipt = lambda job: {"status": "PAUSED"}
        queued = self.port.resume(self.scope, {"job_id": "configured-job"})
        self.assertEqual(queued["status"], "QUEUED")
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


class OwnerRecordedTrainingEvidence(unittest.TestCase):
    """A receipt file alone cannot prove native owner consent or SQLite RESULT."""

    def setUp(self):
        class Trainer:
            def sha256_file(_, path): return "a" * 64
        class Background:
            trainer = Trainer()
            def verified_receipt(_, job):
                return {"status":"COMPLETED", "training":{"adapter_eval_loss":0.2},
                        "checkpoint":{"path":"checkpoints/step-1"}}
            def event_snapshot(_, job): return []
        root=Path("/native-owner-placeholder")
        self.job=ForgeJob(run_id="native-run-1",task_id="task-1",base_model_dir=root,
            model_lock=root,model_revision="a"*40,dataset_manifest=root,
            rights_verifier=root,train_jsonl=root,holdout_jsonl=root,output_dir=root)
        job_seal=hashlib.sha256(json.dumps(asdict(self.job),sort_keys=True,default=str).encode()).hexdigest()
        self.row={"kind":"FORGE","task_id":42,"payload":{"run_id":"native-run-1",
                   "task_id":"task-1","job_sha256":job_seal},
                  "state":"ADAPTER_CANDIDATE_PENDING_E07",
                  "result":{"status":"ADAPTER_CANDIDATE_PENDING_E07",
                            "run_id":"native-run-1","receipt_sha256":"a"*64,
                            "weights_updated":False,"activation_allowed":False}}
        self.scope=object()
        self.port=ExistingP04NativePorts(Background(),
            job_resolver=lambda scope,jid:self.job,
            last_run=lambda *a:None,native_submit=lambda *a,**kw:None,
            durable_result=lambda *a:self.row)

    def test_exact_recorded_result_allows_candidate_only(self):
        result=self.port.evaluate(self.scope,{"job_id":"native-run-1"})
        self.assertEqual(result["status"],"CANDIDATE_ONLY")
        self.assertIs(result["activation_allowed"],False)
        self.assertIs(result["weights_updated"],False)
        self.assertIsNotNone(self.port.checkpoints(self.scope,{"job_id":"native-run-1"})["checkpoint"])

    def test_unrecorded_status_or_wrong_receipt_fails_closed(self):
        import copy
        original=copy.deepcopy(self.row)
        variants=[]
        for key,value in (("kind","SELF_WRITE"),("state","RUNNING"),("task_id",True)):
            row=copy.deepcopy(original);row[key]=value;variants.append(row)
        for key,value in (("run_id","other-job"),("receipt_sha256","b"*64),
                          ("weights_updated",True),("activation_allowed",True),
                          ("status","COMPLETED")):
            row=copy.deepcopy(original);row["result"][key]=value;variants.append(row)
        for key,value in (("run_id","other-job"),("task_id","other-task"),
                          ("job_sha256","b"*40)):
            row=copy.deepcopy(original);row["payload"][key]=value;variants.append(row)
        variants += [None,{},{"state":"ADAPTER_CANDIDATE_PENDING_E07"}]
        for row in variants:
            with self.subTest(row=row):
                self.row=row
                self.assertEqual(self.port.evaluate(self.scope,{"job_id":"native-run-1"})["status"],"HOLD")
                self.assertIsNone(self.port.checkpoints(self.scope,{"job_id":"native-run-1"})["checkpoint"])

    def test_missing_owner_callback_fails_closed(self):
        self.port.durable_result=None
        self.assertEqual(self.port.evaluate(self.scope,{"job_id":"native-run-1"})["status"],"HOLD")


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
