"""Only synthetic preflight contracts; not evidence of Windows CUDA hardware."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from packaging.tags import Tag
import unittest

ROOT = Path(__file__).resolve().parents[2] / "Packages" / "P04"
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("p04_host_gpu_probe", ROOT / "preflight_local_gpu.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
VERSIONS = {"torch": "2.4.0+cu124", "transformers": "4.51.0", "peft": "0.15.0",
            "trl": "0.19.0", "accelerate": "1.6.0", "datasets": "3.6.0",
            "bitsandbytes": "0.45.0", "safetensors": "0.5.0"}


class HardwarePreflightContracts(unittest.TestCase):
    def setUp(self):
        # Synthetic universal WHEEL metadata tests the PyPA contract parser,
        # not target Windows CUDA binary compatibility or original wheel SHA.
        # Simulate target Windows CPython wheel tags explicitly. Mocking only
        # platform.system() cannot alter packaging.tags.sys_tags() on Linux.
        self._fixture_distribution = lambda package: SimpleNamespace(
            read_text=lambda _: "Wheel-Version: 1.0\nTag: " + (
                "cp311-cp311-win_amd64" if package == "torch" else
                "py3-none-win_amd64" if package == "bitsandbytes" else
                "py3-none-any") + "\n"
        )
        for name, replacement in (("version", VERSIONS.__getitem__),
                                  ("distribution", self._fixture_distribution)):
            patcher = patch.object(probe.metadata, name, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        tags = [Tag("cp311", "cp311", "win_amd64"),
                Tag("py3", "none", "win_amd64"), Tag("py3", "none", "any")]
        patcher = patch("packaging.tags.sys_tags", return_value=tags)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_non_windows_is_hold_without_running_gpu(self):
        with patch.object(probe.platform, "system", return_value="Linux"), patch.object(
            probe.train_qlora, "nvidia_smi", side_effect=AssertionError("must not launch vendor process")
        ):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("WINDOWS_GPU_HOST_REQUIRED", result["errors"])
        self.assertFalse(result["runtime_training_verified"])

    def test_g4b_rejects_unsupported_windows_cpu_abi_before_vendor_probe(self):
        for cpu, maxsize in (("ARM64", (1 << 63) - 1),
                             ("x86", (1 << 31) - 1),
                             ("AMD64", (1 << 31) - 1)):
            with self.subTest(cpu=cpu, maxsize=maxsize), patch.object(
                probe.platform, "system", return_value="Windows"
            ), patch.object(probe.platform, "machine", return_value=cpu), patch.object(
                probe.sys, "maxsize", maxsize
            ), patch.object(probe.metadata, "version", return_value="fixture"), patch.object(
                probe.train_qlora, "nvidia_smi",
                side_effect=AssertionError("incompatible worker must not probe GPU")
            ):
                result = probe.inspect("BALANCED", 0)
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("WINDOWS_AMD64_64BIT_PYTHON_REQUIRED", result["errors"])

    def test_g4b_supported_amd64_64bit_reaches_existing_vendor_gate(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.platform, "machine", return_value="AMD64"
        ), patch.object(probe.sys, "maxsize", (1 << 63) - 1), patch.object(
            probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertNotIn("WINDOWS_AMD64_64BIT_PYTHON_REQUIRED", result["errors"])
        self.assertIn("NVIDIA_TELEMETRY_UNAVAILABLE", result["errors"])
        self.assertEqual(result["status"], "HOLD")

    def test_missing_vendor_probe_holds_even_with_local_packages(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("NVIDIA_TELEMETRY_UNAVAILABLE", result["errors"])

    def test_selected_uuid_and_sufficient_actual_free_memory_semantics(self):
        device = {"index": "1", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Test NVIDIA", "memory_total_mib": "12288"}
        cuda = SimpleNamespace(is_available=lambda: True, device_count=lambda: 1)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="fixture"))
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
            probe.train_qlora, "gpu_inventory", return_value=[device]
        ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64.0), patch.object(
            probe.train_qlora, "gpu_vram_headroom",
            return_value={"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        ), patch.dict(sys.modules, {"torch": fake_torch}):
            result = probe.inspect("BALANCED", 1)
        self.assertEqual(result["status"], "HARDWARE_READY_ONLY")
        self.assertFalse(result["model_license_verified"])
        self.assertFalse(result["dataset_rights_verified"])
        self.assertFalse(result["dependency_lock_verified"])
        self.assertFalse(result["wheel_artifact_sha256_verified"])
        self.assertEqual(result["wheel_abi_status"], "INSTALLED_ROOT_TAG_MATCH_ONLY")
        self.assertEqual(result["gpu"]["free_mib"], 11000)
        self.assertFalse(result["runtime_training_verified"])


    def test_g4b_pypa_version_outside_declared_range_blocks_telemetry(self):
        versions = {**VERSIONS, "torch": "2.3.0"}
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=versions.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", side_effect=AssertionError("must hold")):
            result = probe.inspect("BALANCED", 0)
        self.assertIn("PACKAGE_VERSION_OUT_OF_RANGE:torch", result["errors"])
        self.assertEqual(result["wheel_abi_status"], "HOLD")

    def test_g4b_incompatible_wheel_tag_blocks_telemetry(self):
        installed = SimpleNamespace(read_text=lambda name: "Wheel-Version: 1.0\nTag: cp310-cp310-win_amd64\n")
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "distribution", return_value=installed
        ), patch.object(probe.train_qlora, "nvidia_smi", side_effect=AssertionError("must hold")):
            result = probe.inspect("BALANCED", 0)
        self.assertIn("WHEEL_ABI_TAG_MISMATCH:torch", result["errors"])
        self.assertEqual(result["status"], "HOLD")

    def test_g4b_gpu_native_dependencies_reject_universal_only_metadata(self):
        for root in ("torch", "bitsandbytes"):
            with self.subTest(root=root):
                def dist_for(name):
                    if name == root:
                        return SimpleNamespace(read_text=lambda _: "Wheel-Version: 1.0\nTag: py3-none-any\n")
                    return self._fixture_distribution(name)
                with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
                    probe.metadata, "distribution", side_effect=dist_for
                ), patch.object(probe.train_qlora, "nvidia_smi",
                                side_effect=AssertionError("native ABI HOLD before vendor")):
                    result = probe.inspect("BALANCED", 0)
                self.assertIn("GPU_NATIVE_WIN_AMD64_WHEEL_REQUIRED:" + root, result["errors"])
                self.assertEqual(result["status"], "HOLD")
                self.assertFalse(result["runtime_training_verified"])

    def test_g4b_missing_or_ambiguous_wheel_metadata_blocks_telemetry(self):
        for text in (None, "Wheel-Version: 1.0\nWheel-Version: 1.0\nTag: py3-none-any\n",
                     "Wheel-Version: 1.0\n"):
            installed = SimpleNamespace(read_text=lambda name: text)
            with self.subTest(text=text), patch.object(probe.platform, "system", return_value="Windows"), patch.object(
                probe.metadata, "distribution", return_value=installed
            ), patch.object(probe.train_qlora, "nvidia_smi", side_effect=AssertionError("must hold")):
                result = probe.inspect("BALANCED", 0)
            self.assertIn("WHEEL_METADATA_INVALID:torch", result["errors"])

    def test_g4b_compatible_installed_wheel_does_not_claim_cuda_or_hash_proof(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("ECO", 0)
        self.assertEqual(result["wheel_abi_status"], "INSTALLED_ROOT_TAG_MATCH_ONLY")
        self.assertFalse(result["dependency_lock_verified"])
        self.assertFalse(result["wheel_artifact_sha256_verified"])
        self.assertFalse(result["runtime_training_verified"])
        self.assertIn("NVIDIA_TELEMETRY_UNAVAILABLE", result["errors"])

if __name__ == "__main__":
    unittest.main()
