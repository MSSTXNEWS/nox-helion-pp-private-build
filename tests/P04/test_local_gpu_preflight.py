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
        cuda = SimpleNamespace(is_initialized=lambda: False, is_available=lambda: True, device_count=lambda: 1)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="12.4"))
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


    def test_g4b_preinitialized_or_unknown_cuda_context_holds_before_vendor_probe(self):
        for cuda in (SimpleNamespace(is_initialized=lambda: True),
                     SimpleNamespace(),
                     SimpleNamespace(is_initialized=lambda: (_ for _ in ()).throw(RuntimeError("broken")))):
            fake_torch = SimpleNamespace(cuda=cuda)
            with self.subTest(cuda=cuda), patch.object(
                probe.platform, "system", return_value="Windows"
            ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.dict(
                sys.modules, {"torch": fake_torch}
            ), patch.object(probe.train_qlora, "nvidia_smi",
                            side_effect=AssertionError("must not probe after CUDA context")):
                result = probe.inspect("BALANCED", 0)
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("CUDA_CONTEXT_PREINITIALIZED_OR_UNVERIFIABLE", result["errors"])
            self.assertFalse(result["runtime_training_verified"])

    def test_g4b_cpu_only_torch_cuda_build_cannot_claim_hardware_ready(self):
        device = {"index": "0", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Synthetic NVIDIA", "memory_total_mib": "12288"}
        cuda = SimpleNamespace(is_initialized=lambda: False,
                               is_available=lambda: True, device_count=lambda: 1)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda=None))
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.platform, "machine", return_value="AMD64"
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
            probe.train_qlora, "gpu_inventory", return_value=[device]
        ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64), patch.object(
            probe.train_qlora, "gpu_vram_headroom",
            return_value={"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        ), patch.dict(sys.modules, {"torch": fake_torch}):
            result = probe.inspect("ECO", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("TORCH_CUDA_BUILD_NOT_CONFIRMED", result["errors"])
        self.assertFalse(result["runtime_training_verified"])


    def test_g4b_vram_snapshot_consistency_blocks_cuda_on_mismatch(self):
        device = {"index": "0", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Test NVIDIA", "memory_total_mib": "12288"}
        good = {"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        cases = (
            ({**good, "total_mib": 12200}, "GPU_INVENTORY_VRAM_TOTAL_MISMATCH"),
            ({**good, "free_mib": 2500}, "GPU_VRAM_TELEMETRY_CONTRACT_INVALID"),
            ({**good, "free_mib": True}, "GPU_VRAM_TELEMETRY_CONTRACT_INVALID"),
            ({"free_mib": 11000, "gui_reserve_mib": 2458}, "GPU_VRAM_TELEMETRY_CONTRACT_INVALID"),
        )
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda: False))
        for snapshot, expected_error in cases:
            with self.subTest(snapshot=snapshot), patch.object(
                probe.platform, "system", return_value="Windows"
            ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.object(
                probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"
            ), patch.object(probe.train_qlora, "gpu_inventory", return_value=[device]), patch.object(
                probe.train_qlora, "gpu_temperature", return_value=64.0
            ), patch.object(probe.train_qlora, "gpu_vram_headroom", return_value=snapshot), patch.dict(
                sys.modules, {"torch": fake_torch}
            ):
                result = probe.inspect("BALANCED", 0)
            self.assertEqual(result["status"], "HOLD")
            self.assertIn(expected_error, result["errors"])
            self.assertIsNone(result["gpu"])
            self.assertFalse(result["runtime_training_verified"])


    def test_g4b_reenumerated_or_mutated_selected_gpu_holds_before_cuda(self):
        for scenario in ("new_uuid_on_second_inventory", "same_object_mutated_during_vram"):
            with self.subTest(scenario=scenario):
                device = {"index": "0", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                          "name": "Synthetic NVIDIA", "memory_total_mib": "12288"}
                changed = {**device, "uuid": "GPU-99999999-9999-9999-9999-999999999999"}
                good = {"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
                inventories = [device] if scenario == "same_object_mutated_during_vram" else [device, changed]

                def read_inventory(_):
                    if scenario == "same_object_mutated_during_vram":
                        return [device]
                    return [inventories.pop(0)]

                def read_memory(*_):
                    if scenario == "same_object_mutated_during_vram":
                        device["uuid"] = changed["uuid"]
                    return good

                fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda: False))
                with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
                    probe.platform, "machine", return_value="AMD64"
                ), patch.object(probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
                    probe.train_qlora, "gpu_inventory", side_effect=read_inventory
                ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64.0), patch.object(
                    probe.train_qlora, "gpu_vram_headroom", side_effect=read_memory
                ), patch.dict(sys.modules, {"torch": fake_torch}):
                    result = probe.inspect("BALANCED", 0)
                self.assertEqual(result["status"], "HOLD")
                self.assertIn("GPU_SELECTION_CHANGED_DURING_PREFLIGHT", result["errors"])
                self.assertIsNone(result["gpu"])
                self.assertFalse(result["runtime_training_verified"])

    def test_g4b_invalid_thermal_sensor_values_hold_before_vram(self):
        device = {"index": "0", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Synthetic NVIDIA", "memory_total_mib": "12288"}
        for temperature in (float("nan"), float("inf"), -1, True, "64"):
            with self.subTest(temperature=temperature), patch.object(
                probe.platform, "system", return_value="Windows"
            ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.object(
                probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"
            ), patch.object(probe.train_qlora, "gpu_inventory", return_value=[device]), patch.object(
                probe.train_qlora, "gpu_temperature", return_value=temperature
            ), patch.object(probe.train_qlora, "gpu_vram_headroom",
                            side_effect=AssertionError("thermal HOLD must not read VRAM")):
                result = probe.inspect("BALANCED", 0)
            self.assertEqual(result["status"], "HOLD")
            self.assertTrue(any(x in result["errors"] for x in
                                ("GPU_TEMPERATURE_UNAVAILABLE", "GPU_THERMAL_HEADROOM_UNAVAILABLE")))
            self.assertIsNone(result["gpu"])

    def test_g4b_r07_cuda_inherited_selector_contract(self):
        selected = "GPU-12345678-1234-1234-1234-123456789012"
        cases = (
            ({"CUDA_VISIBLE_DEVICES": "0"}, "CUDA_PARENT_VISIBLE_DEVICES_CONFLICT"),
            ({"CUDA_VISIBLE_DEVICES": ""}, "CUDA_PARENT_VISIBLE_DEVICES_CONFLICT"),
            ({"CUDA_VISIBLE_DEVICES": "GPU-99999999-9999-9999-9999-999999999999"}, "CUDA_PARENT_VISIBLE_DEVICES_CONFLICT"),
            ({"CUDA_DEVICE_ORDER": "FASTEST_FIRST"}, "CUDA_PARENT_DEVICE_ORDER_CONFLICT"),
        )
        for incoming, expected in cases:
            with self.subTest(incoming=incoming), patch.dict(probe.os.environ, incoming, clear=True):
                previous = dict(probe.os.environ)
                with self.assertRaisesRegex(RuntimeError, expected):
                    probe._require_cuda_parent_selection_compatible(selected)
                self.assertEqual(dict(probe.os.environ), previous)
        with patch.dict(probe.os.environ, {}, clear=True):
            self.assertIsNone(probe._require_cuda_parent_selection_compatible(selected))
        with patch.dict(probe.os.environ, {
            "CUDA_VISIBLE_DEVICES": selected, "CUDA_DEVICE_ORDER": "PCI_BUS_ID"
        }, clear=True):
            self.assertIsNone(probe._require_cuda_parent_selection_compatible(selected))

    def test_g4b_r07_conflicting_parent_cuda_mask_holds_before_torch_import(self):
        selected = "GPU-12345678-1234-1234-1234-123456789012"
        card = {"index": "0", "uuid": selected, "name": "Synthetic NVIDIA",
                "memory_total_mib": "12288"}
        ready_memory = {"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda: False))
        with patch.dict(probe.os.environ, {"CUDA_VISIBLE_DEVICES": "0"}, clear=True), patch.object(
            probe.platform, "system", return_value="Windows"
        ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"
        ), patch.object(probe.train_qlora, "gpu_inventory", return_value=[card]), patch.object(
            probe.train_qlora, "gpu_temperature", return_value=62.0
        ), patch.object(probe.train_qlora, "gpu_vram_headroom", return_value=ready_memory), patch.dict(
            sys.modules, {"torch": fake_torch}
        ):
            result = probe.inspect("BALANCED", 0)
            self.assertEqual(probe.os.environ["CUDA_VISIBLE_DEVICES"], "0")
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("CUDA_PARENT_VISIBLE_DEVICES_CONFLICT", result["errors"])
        self.assertIsNone(result["gpu"])
        self.assertFalse(result["runtime_training_verified"])


    def test_g4b_r08_cuda_selection_restores_clean_parent_after_success(self):
        selected_uuid = "GPU-12345678-1234-1234-1234-123456789012"
        device = {"index": "0", "uuid": selected_uuid,
                  "name": "Synthetic NVIDIA", "memory_total_mib": "12288"}
        memory = {"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        cuda = SimpleNamespace(is_initialized=lambda: False,
                               is_available=lambda: True, device_count=lambda: 1)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="12.4"))
        with patch.dict(probe.os.environ, {}, clear=True), patch.object(
            probe.platform, "system", return_value="Windows"
        ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"
        ), patch.object(probe.train_qlora, "gpu_inventory", return_value=[device]), patch.object(
            probe.train_qlora, "gpu_temperature", return_value=62.0
        ), patch.object(probe.train_qlora, "gpu_vram_headroom", return_value=memory), patch.dict(
            sys.modules, {"torch": fake_torch}
        ):
            report = probe.inspect("BALANCED", 0)
            self.assertNotIn("CUDA_VISIBLE_DEVICES", probe.os.environ)
            self.assertNotIn("CUDA_DEVICE_ORDER", probe.os.environ)
        self.assertEqual(report["status"], "HARDWARE_READY_ONLY")
        self.assertFalse(report["runtime_training_verified"])

    def test_g4b_r08_cuda_selection_restores_parent_after_runtime_error(self):
        selected_uuid = "GPU-12345678-1234-1234-1234-123456789012"
        device = {"index": "0", "uuid": selected_uuid,
                  "name": "Synthetic NVIDIA", "memory_total_mib": "12288"}
        memory = {"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        cuda = SimpleNamespace(is_initialized=lambda: False,
                               is_available=lambda: (_ for _ in ()).throw(RuntimeError("cuda error")))
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="12.4"))
        inherited = {"CUDA_VISIBLE_DEVICES": selected_uuid, "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}
        with patch.dict(probe.os.environ, inherited, clear=True), patch.object(
            probe.platform, "system", return_value="Windows"
        ), patch.object(probe.platform, "machine", return_value="AMD64"), patch.object(
            probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"
        ), patch.object(probe.train_qlora, "gpu_inventory", return_value=[device]), patch.object(
            probe.train_qlora, "gpu_temperature", return_value=62.0
        ), patch.object(probe.train_qlora, "gpu_vram_headroom", return_value=memory), patch.dict(
            sys.modules, {"torch": fake_torch}
        ):
            report = probe.inspect("BALANCED", 0)
            self.assertEqual(dict(probe.os.environ), inherited)
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("TORCH_CUDA_RUNTIME_UNAVAILABLE", report["errors"])
        self.assertFalse(report["runtime_training_verified"])



if __name__ == "__main__":
    unittest.main()
