"""NOX P04 fail-closed component regressions, synthetic fixtures only.

Run after the PR7 source is present:
    python -m unittest discover -s tests/P04 -p 'test_*.py'
This suite does not train or download a model and is not runtime/GPU acceptance.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"

def worker():
    if not WORKER.is_file():
        raise AssertionError("NOX_P04_WORKER_ABSENT")
    spec = importlib.util.spec_from_file_location("nox_qlora", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class WorkerSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = worker()

    def test_known_gpu_missing_prerequisites_report_hold(self):
        for reason in (
            "NVIDIA_GPU_TELEMETRY_UNAVAILABLE",
            "SELECTED_GPU_INDEX_NOT_FOUND",
            "SELECTED_NVIDIA_GPU_NOT_VISIBLE_TO_CUDA",
            "GPU_TEMPERATURE_UNAVAILABLE",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(self.mod.classify_training_failure(RuntimeError(reason)), "HOLD")

    def test_other_training_faults_are_not_hidden(self):
        for reason in (
            "UNEXPECTED_TRAINER_FAILURE",
            "SELECTED_NVIDIA_GPU_NOT_VISIBLE_TO_CUDA_MORE",
            "NVIDIA_UNKNOWN_FAILURE",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(self.mod.classify_training_failure(RuntimeError(reason)), "ERROR")

    def test_reject_nonfinite_or_fake_metrics(self):
        for value in (None, True, False, "1.0", float("inf"),
                      float("-inf"), float("nan")):
            with self.subTest(value=repr(value)):
                self.assertIsNone(self.mod.finite_metric(value))
        self.assertEqual(self.mod.finite_metric(0), 0.0)

    def test_model_tree_change_changes_digest(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            file = folder / "fixture.bin"
            file.write_bytes(b"not-weights")
            original = self.mod.sha256_tree(folder)
            file.write_bytes(b"modified-not-weights")
            self.assertNotEqual(original, self.mod.sha256_tree(folder))

    def test_model_identity_requires_valid_revision_and_license(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            model = folder / "model"
            model.mkdir()
            (model / "config.json").write_text("{}", encoding="utf8")
            rev = "a" * 40
            lock_path = folder / "model-lock.json"
            lock = {"schema": "nox-model-lock-v1", "license_status": "APPROVED",
                    "owner_approval_id": "synthetic", "revision": rev,
                    "model_id": "fixture", "snapshot_sha256": self.mod.sha256_tree(model)}
            lock_path.write_text(json.dumps(lock), encoding="utf8")
            self.assertEqual(self.mod.verify_model_lock(lock_path, model, rev)["model_id"], "fixture")
            with self.assertRaises(ValueError):
                self.mod.verify_model_lock(lock_path, model, "b" * 40)
            lock["license_status"] = "UNKNOWN"
            lock_path.write_text(json.dumps(lock), encoding="utf8")
            with self.assertRaises(ValueError):
                self.mod.verify_model_lock(lock_path, model, rev)

    def test_unapproved_dataset_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            train = folder / "train.jsonl"
            holdout = folder / "holdout.jsonl"
            train.write_text('{"text":"synthetic training"}\n', encoding="utf8")
            holdout.write_text('{"text":"synthetic evaluation"}\n', encoding="utf8")
            manifest = folder / "consent.json"
            manifest.write_text(json.dumps({"schema": "nox-dataset-consent-v1",
                                             "rights_status": "UNVERIFIED"}), encoding="utf8")
            with self.assertRaises(ValueError):
                self.mod.verify_manifest(manifest, train, holdout, folder / "verifier")

    def test_empty_training_data_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "data.jsonl"
            path.write_text("\n", encoding="utf8")
            with self.assertRaises(ValueError):
                self.mod.validate_jsonl(path, "TRAIN")

if __name__ == "__main__":
    unittest.main()
