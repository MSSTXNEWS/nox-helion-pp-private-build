"""P04 source-level NVIDIA inventory identity/shape gate (mock only; no GPU training)."""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

WORKER_PATH = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("p04_gpu_inventory_identity_r13", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
GPU = "GPU-12345678-1234-1234-1234-123456789abc"

class GpuInventoryIdentityTests(unittest.TestCase):
    def inventory(self, output, status=0):
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=status, stdout=output)) as run:
            result = worker.gpu_inventory("nvidia-smi")
            run.assert_called_once()
            return result

    def test_valid_one_gpu(self):
        rows = self.inventory(f"0, NVIDIA RTX 3060, {GPU}, 12288\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uuid"], GPU)
        self.assertEqual(rows[0]["memory_total_mib"], "12288")

    def test_vendor_failure_and_empty_inventory_hold(self):
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1, stdout="")):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA_GPU_INVENTORY_FAILED"):
                worker.gpu_inventory("nvidia-smi")
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout="")):
            with self.assertRaisesRegex(RuntimeError, "NO_NVIDIA_GPU_FOUND"):
                worker.gpu_inventory("nvidia-smi")

    def test_invalid_or_partial_report_fails_closed(self):
        for bad in (f"0, NVIDIA RTX, {GPU}, N/A\n",
                    f"0, NVIDIA RTX, {GPU}, 12288\nnoise",
                    f"00, NVIDIA RTX, {GPU}, 12288\n",
                    f"0, , {GPU}, 12288\n",
                    f"0, NVIDIA RTX, GPU-?, 12288\n",
                    f"0, NVIDIA RTX, {GPU}, 0\n",
                    f"0, NVIDIA RTX, {GPU}, 12288\n1, NVIDIA RTX, {GPU}, 12288\n"):
            with self.subTest(output=bad), patch.object(
                    worker.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stdout=bad)):
                with self.assertRaisesRegex(RuntimeError, "NVIDIA_GPU_INVENTORY_(INVALID|DUPLICATE)"):
                    worker.gpu_inventory("nvidia-smi")

    def test_repeated_index_is_rejected(self):
        row = f"0, NVIDIA RTX, {GPU}, 12288\n"
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout=row + row)):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA_GPU_INVENTORY_DUPLICATE"):
                worker.gpu_inventory("nvidia-smi")

    def test_timeout_and_missing_executable_hold(self):
        for exception in (subprocess.TimeoutExpired("nvidia-smi", 10), FileNotFoundError()):
            with self.subTest(error=type(exception).__name__), patch.object(
                    worker.subprocess, "run", side_effect=exception):
                with self.assertRaisesRegex(RuntimeError, "NVIDIA_GPU_INVENTORY_FAILED"):
                    worker.gpu_inventory("nvidia-smi")

    def test_new_codes_are_hold_not_verified_hardware(self):
        for code in ("NVIDIA_GPU_INVENTORY_INVALID", "NVIDIA_GPU_INVENTORY_DUPLICATE",
                     "NVIDIA_GPU_INVENTORY_FAILED", "NO_NVIDIA_GPU_FOUND"):
            with self.subTest(code=code):
                self.assertEqual(worker.classify_training_failure(RuntimeError(code)), "HOLD")
        self.assertEqual(worker.classify_training_failure(RuntimeError("UNKNOWN_TRAINER_CRASH")), "ERROR")

if __name__ == "__main__":
    unittest.main()
