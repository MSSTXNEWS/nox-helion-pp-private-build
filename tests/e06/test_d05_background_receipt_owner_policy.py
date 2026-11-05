"""D05: original P04 receipt may not outlive owner dataset consent/job identity."""
import sys
import unittest
from pathlib import Path
from copy import deepcopy
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from nox_selfbuilder.background_forge import ExistingP04Background, ForgeJob, ForgeHold

class NativeTrainerStub:
    RECEIPT_SCHEMA = "D05-TEST"
    def __init__(self):
        self.receipt = {
            "schema": self.RECEIPT_SCHEMA, "run_id": "run-1", "status": "COMPLETED",
            "model": {"id": "model", "revision": "a"*40, "snapshot_sha256": "d"*64},
            "dataset": {"id": "dataset", "revision": "v1", "license_id": "license",
                        "owner_approval_id": "owner-grant", "train_sha256": "b"*64,
                        "holdout_sha256": "c"*64},
            "checkpoint": {"status": "HASHED", "path": "checkpoints/checkpoint-5",
                           "step": 5, "tree_sha256": "f"*64},
            "adapter_sha256": "e"*64,
            "training": {"profile": "BALANCED", "max_steps": 10, "global_step": 5,
                         "evaluation_status": "VALID", "baseline_eval_loss": .4,
                         "adapter_eval_loss": .3, "train_loss": .2},
        }
        self.manifest = {"rights_status": "APPROVED", "consent_status": "GRANTED",
                         "dataset_id": "dataset", "dataset_revision": "v1",
                         "license_id": "license", "owner_approval_id": "owner-grant"}
    def read_object(self, path):
        name = Path(path).name
        if name == "training-receipt.json": return self.receipt
        if name == "model.lock": return {"model_id": "model"}
        if name == "dataset.json": return self.manifest
        raise AssertionError(name)
    def sha256_file(self, path):
        return {"train.jsonl": "b"*64, "holdout.jsonl": "c"*64}.get(Path(path).name, "a"*64)
    def sha256_tree(self, path):
        return "e"*64 if Path(path).name == "adapter" else "d"*64
    def validated_checkpoint(self, *_): return (5, "f"*64)
    def finite_metric(self, val):
        return val if isinstance(val, (float, int)) else None

class ReceiptOwnerPolicyD05(unittest.TestCase):
    def setUp(self):
        self.background = object.__new__(ExistingP04Background)
        self.background.trainer = NativeTrainerStub()
        self.background._output = lambda path, resume=False: Path("/fake/output")
        self.background._trusted_file = lambda path: str(path)
        fake = Path("/fake")
        self.job = ForgeJob(run_id="run-1", task_id="task-1", base_model_dir=fake/"model",
                            model_lock=fake/"model.lock", model_revision="a"*40,
                            dataset_manifest=fake/"dataset.json", rights_verifier=fake/"rights",
                            train_jsonl=fake/"train.jsonl", holdout_jsonl=fake/"holdout.jsonl",
                            output_dir=fake/"output", profile="BALANCED", steps=10)
    def test_valid_original_candidate(self):
        self.assertEqual(self.background.verified_receipt(self.job)["status"], "COMPLETED")
    def test_owner_policy_drift_rejected_without_training_or_side_effect(self):
        variants = (("training", "profile", "INTENSIVE"),
                    ("training", "max_steps", 20),
                    ("training", "global_step", 11),
                    ("manifest", "consent_status", "REVOKED"),
                    ("manifest", "rights_status", "HOLD"),
                    ("manifest", "license_id", "other-license"),
                    ("manifest", "owner_approval_id", "another-owner"),
                    ("manifest", "dataset_revision", "v2"))
        for target, field, value in variants:
            with self.subTest(field=field):
                trainer = self.background.trainer
                before_receipt, before_manifest = deepcopy(trainer.receipt), deepcopy(trainer.manifest)
                row = trainer.receipt["training"] if target == "training" else trainer.manifest
                row[field] = value
                with self.assertRaises(ForgeHold):
                    self.background.verified_receipt(self.job)
                trainer.receipt, trainer.manifest = before_receipt, before_manifest
                self.assertEqual(self.background.verified_receipt(self.job)["status"], "COMPLETED")

if __name__ == "__main__": unittest.main()
