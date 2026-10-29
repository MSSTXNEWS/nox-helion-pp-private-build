"""P04 real GPU free-VRAM telemetry parser: offline subprocess mock, never fake hardware proof."""
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("p04_gpu_guard_real_contract", FILE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
GPU = "GPU-12345678-abcd-abcd-abcd-0123456789ab"

class GpuHeadroomTests(unittest.TestCase):
    def test_profiles_use_vendor_free_memory(self):
        response = SimpleNamespace(returncode=0, stdout="11000, 12288\n")
        with patch.object(worker.subprocess, "run", return_value=response) as call:
            for profile in ("ECO", "BALANCED", "INTENSIVE"):
                item = worker.gpu_vram_headroom("nvidia-smi", GPU, profile)
                self.assertEqual(item["free_mib"], 11000)
                self.assertEqual(item["total_mib"], 12288)
                self.assertGreaterEqual(item["gui_reserve_mib"], 1024)
            args = call.call_args.args[0]
            self.assertIn("memory.free,memory.total", args[2])
            self.assertIn("--id=" + GPU, args)

    def test_low_free_memory_blocks_training(self):
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout="1000, 12288\n")):
            with self.assertRaisesRegex(RuntimeError, "GPU_VRAM_INSUFFICIENT_GUI_HEADROOM"):
                worker.gpu_vram_headroom("nvidia-smi", GPU, "BALANCED")

    def test_invalid_or_unavailable_is_not_invented(self):
        for reply in ("N/A, 12288", "12000, 5000", "1024", "", "nan, 12345"):
            with self.subTest(reply=reply):
                with patch.object(worker.subprocess, "run",
                                  return_value=SimpleNamespace(returncode=0, stdout=reply)):
                    with self.assertRaises(RuntimeError):
                        worker.gpu_vram_headroom("nvidia-smi", GPU, "ECO")
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=1, stdout="")):
            with self.assertRaisesRegex(RuntimeError, "GPU_VRAM_TELEMETRY_UNAVAILABLE"):
                worker.gpu_vram_headroom("nvidia-smi", GPU, "ECO")
        with self.assertRaises(ValueError):
            worker.gpu_vram_headroom("nvidia-smi", GPU, "invalid")

if __name__ == "__main__":
    unittest.main()
