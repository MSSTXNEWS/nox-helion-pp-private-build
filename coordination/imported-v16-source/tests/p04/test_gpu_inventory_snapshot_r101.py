"""Hardware inventory and UUID-scoped VRAM identity must agree. Source-only tests."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# No CUDA, NVIDIA driver, downloads or training is needed for a fail-closed
# contract regression. The production preflight source is imported unchanged.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packages" / "P04"))
try:
    import train_qlora  # original engine, import has no GPU side effects
except ImportError:
    raise
import preflight_local_gpu as preflight

UUID = "GPU-123e4567-e89b-12d3-a456-426614174000"


class InventoryVramIdentity(unittest.TestCase):
    def run_gate(self, total):
        with (mock.patch.object(preflight.platform, "system", return_value="Windows"),
              mock.patch.object(preflight.metadata, "version", return_value="1.0"),
              mock.patch.object(train_qlora, "nvidia_smi", return_value="nvidia-smi"),
              mock.patch.object(train_qlora, "gpu_inventory", return_value=[{
                  "index": "0", "name": "NVIDIA Test",
                  "uuid": UUID, "memory_total_mib": "12288",
              }]),
              mock.patch.object(train_qlora, "gpu_temperature", return_value=44),
              mock.patch.object(train_qlora, "gpu_vram_headroom", return_value={
                  "free_mib": 7000, "total_mib": total, "gui_reserve_mib": 2500,
              }),
              mock.patch.object(preflight, "_run_cuda_probe_isolated", return_value={
                  "cuda_runtime": "12.4", "cuda_device_count": 1,
              }) as probe):
            report = preflight.inspect("BALANCED", 0)
            return report, probe.call_count

    def test_mismatch_holds_before_cuda(self):
        report, probes = self.run_gate(8192)
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("GPU_TOTAL_MEMORY_SNAPSHOT_DRIFT", report["errors"])
        self.assertEqual(probes, 0)

    def test_missing_total_holds_before_cuda(self):
        report, probes = self.run_gate(None)
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("GPU_TOTAL_MEMORY_SNAPSHOT_DRIFT", report["errors"])
        self.assertEqual(probes, 0)

    def test_matching_inventory_only_means_hardware_ready(self):
        report, probes = self.run_gate(12288)
        self.assertEqual(report["status"], "HARDWARE_READY_ONLY")
        self.assertEqual(report["gpu"]["total_mib"], 12288)
        self.assertEqual(probes, 1)
        self.assertFalse(report["runtime_training_verified"])
        self.assertFalse(report["model_license_verified"])


if __name__ == "__main__":
    unittest.main()
