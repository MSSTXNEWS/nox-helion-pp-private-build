"""Regression for real P04 QLoRA worker failure statuses (no GPU required)."""
import importlib.util
from pathlib import Path
import unittest

WORKER_PATH = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_p04_qlora_status", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class TrainingFailureStatusTests(unittest.TestCase):
    def test_missing_real_nvidia_inventory_is_hold(self):
        self.assertEqual(worker.classify_training_failure(RuntimeError("NO_NVIDIA_GPU_FOUND")), "HOLD")

    def test_other_verified_missing_gpu_prerequisites_remain_hold(self):
        for code in (
            "NVIDIA_GPU_TELEMETRY_UNAVAILABLE",
            "NVIDIA_GPU_INVENTORY_FAILED",
            "SELECTED_GPU_INDEX_NOT_FOUND",
            "SELECTED_NVIDIA_GPU_NOT_VISIBLE_TO_CUDA",
            "GPU_TEMPERATURE_UNAVAILABLE",
        ):
            with self.subTest(code=code):
                self.assertEqual(worker.classify_training_failure(RuntimeError(code)), "HOLD")

    def test_existing_authorization_holds_remain_hold(self):
        for code in ("RIGHTS_NOT_APPROVED", "DATASET_SHA256_MISMATCH", "MODEL_LOCK_INVALID"):
            with self.subTest(code=code):
                self.assertEqual(worker.classify_training_failure(ValueError(code)), "HOLD")

    def test_unexpected_fault_not_misclassified(self):
        for code in ("PYTHON_IMPORT_BROKEN", "UNEXPECTED_NVIDIA_PROVIDER_CRASH", "OSError"):
            with self.subTest(code=code):
                self.assertEqual(worker.classify_training_failure(RuntimeError(code)), "ERROR")


if __name__ == "__main__":
    unittest.main()
