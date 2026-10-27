"""Only synthetic preflight contracts; not evidence of Windows CUDA hardware."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[2] / "Packages" / "P04"
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("p04_host_gpu_probe", ROOT / "preflight_local_gpu.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HardwarePreflightContracts(unittest.TestCase):
    def test_non_windows_is_hold_without_running_gpu(self):
        with patch.object(probe.platform, "system", return_value="Linux"), patch.object(
            probe.train_qlora, "nvidia_smi", side_effect=AssertionError("must not launch vendor process")
        ):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("WINDOWS_GPU_HOST_REQUIRED", result["errors"])
        self.assertFalse(result["runtime_training_verified"])

    def test_missing_vendor_probe_holds_even_with_local_packages(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", return_value="1.0"
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("NVIDIA_TELEMETRY_UNAVAILABLE", result["errors"])

    def test_selected_uuid_and_sufficient_actual_free_memory_semantics(self):
        device = {"index": "1", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Test NVIDIA", "memory_total_mib": "12288"}
        cuda = SimpleNamespace(is_available=lambda: True, device_count=lambda: 1)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="fixture"))
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", return_value="fixture"
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
            probe.train_qlora, "gpu_inventory", return_value=[device]
        ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64.0), patch.object(
            probe.train_qlora, "gpu_vram_headroom",
            return_value={"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        ), patch.dict(sys.modules, {"torch": fake_torch}):
            result = probe.inspect("BALANCED", 1)
        self.assertEqual(result["status"], "READY_FOR_AUTHORIZED_TRAINING")
        self.assertEqual(result["gpu"]["free_mib"], 11000)
        self.assertFalse(result["runtime_training_verified"])


if __name__ == "__main__":
    unittest.main()
