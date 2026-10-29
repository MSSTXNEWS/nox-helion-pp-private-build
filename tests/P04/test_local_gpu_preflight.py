"""Only synthetic preflight contracts; not evidence of Windows CUDA hardware."""
from __future__ import annotations

import importlib.util
from email.message import Message
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

# Synthetic boundary fixtures, not a resolved/release dependency set.
VERSIONS = {"torch": "2.4.0+cu124", "transformers": "4.51.0", "peft": "0.15.0",
            "trl": "0.19.0", "accelerate": "1.6.0", "datasets": "3.6.0",
            "bitsandbytes": "0.45.0", "safetensors": "0.5.0"}


class HardwarePreflightContracts(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(probe.metadata, "metadata", return_value=Message())
        self.package_metadata = patcher.start()
        self.addCleanup(patcher.stop)

    def metadata_result(self, *, python=None, dependencies=()):
        value = Message()
        if python is not None:
            value["Requires-Python"] = python
        for dependency in dependencies:
            value["Requires-Dist"] = dependency
        self.package_metadata.return_value = value
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            return probe.inspect("BALANCED", 0)

    def test_requires_python_must_be_a_nonempty_singleton(self):
        for constraints in ((">=3", ">=99"), (">=99", ">=3"), (">=3", ">=3"), ("",), ("  ",)):
            with self.subTest(constraints=constraints):
                value = Message()
                for constraint in constraints:
                    value["Requires-Python"] = constraint
                self.package_metadata.return_value = value
                with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
                    probe.metadata, "version", side_effect=VERSIONS.__getitem__
                ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
                    result = probe.inspect("BALANCED", 0)
                self.assertIn("PACKAGE_DEPENDENCY_METADATA_INVALID:torch", result["errors"])
                self.assertEqual(result["dependency_metadata_status"], "HOLD")

    def test_installed_package_python_requirement_is_enforced(self):
        result = self.metadata_result(python=">=99")
        self.assertIn("PACKAGE_PYTHON_INCOMPATIBLE:torch", result["errors"])
        self.assertEqual(result["dependency_metadata_status"], "HOLD")

    def test_declared_active_dependency_conflict_is_hold(self):
        result = self.metadata_result(dependencies=("transformers>=4.99",))
        self.assertIn("PACKAGE_DEPENDENCY_INCOMPATIBLE:peft:transformers", result["errors"])

    def test_missing_active_dependency_is_hold(self):
        value = Message()
        value["Requires-Dist"] = "missing-runtime>=1"
        self.package_metadata.return_value = value
        def version(name):
            if name == "missing-runtime":
                raise probe.metadata.PackageNotFoundError(name)
            return VERSIONS[name]
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=version
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertIn("PACKAGE_DEPENDENCY_MISSING:peft:missing-runtime", result["errors"])

    def test_unselected_optional_and_false_environment_markers_do_not_require_packages(self):
        result = self.metadata_result(python=">=3", dependencies=(
            'missing-runtime>=1; extra == "optional-feature"',
            'missing-runtime>=1; python_version < "2"',
            'transformers>=4.51; python_version >= "3"'))
        self.assertEqual(result["dependency_metadata_status"], "DIRECT_BASE_METADATA_CHECK_PASSED")
        self.assertFalse(any(error.startswith("PACKAGE_DEPENDENCY_") for error in result["errors"]))
        self.assertFalse(result["dependency_lock_verified"])

    def test_invalid_metadata_and_direct_urls_are_not_compatible_evidence(self):
        for raw, expected in (("not a requirement !!!", "PACKAGE_DEPENDENCY_METADATA_INVALID:torch"),
                              ("torch @ https://example.invalid/torch.whl", "PACKAGE_DEPENDENCY_URL_UNVERIFIED:torch:torch")):
            with self.subTest(raw=raw):
                result = self.metadata_result(dependencies=(raw,))
                self.assertIn(expected, result["errors"])

    def test_declared_extras_are_reported_without_claiming_full_dependency_closure(self):
        result = self.metadata_result(dependencies=("transformers[extra-feature]>=4.51",))
        self.assertIn("transformers[extra-feature]", result["dependency_extras_unverified"])
        self.assertFalse(result["runtime_compatibility_verified"])

    def test_metadata_disappearing_after_version_probe_returns_hold(self):
        self.package_metadata.side_effect = probe.metadata.PackageNotFoundError("removed-during-probe")
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertIn("PACKAGE_DEPENDENCY_METADATA_INVALID:torch", result["errors"])

    def test_marker_requiring_unavailable_metadata_context_returns_hold(self):
        result = self.metadata_result(dependencies=('torch; extras == "feature"',))
        self.assertIn("PACKAGE_DEPENDENCY_METADATA_INVALID:torch", result["errors"])

    def test_installed_versions_outside_declared_ranges_are_hold(self):
        for package, version in (("torch", "2.3.0"), ("transformers", "5.0.0"),
                                 ("peft", "1.0.0"), ("trl", "0.18.9"),
                                 ("datasets", "5.0.0"), ("torch", "invalid")):
            versions = {**VERSIONS, package: version}
            with self.subTest(package=package, version=version), patch.object(
                probe.platform, "system", return_value="Windows"
            ), patch.object(probe.metadata, "version", side_effect=versions.__getitem__), patch.object(
                probe.train_qlora, "nvidia_smi", return_value=None
            ):
                result = probe.inspect("BALANCED", 0)
                self.assertEqual(result["status"], "HOLD")
                error = "PACKAGE_METADATA_INVALID:" if version == "invalid" else "PACKAGE_VERSION_OUT_OF_RANGE:"
                self.assertIn(error + package, result["errors"])

    def test_compatible_ranges_are_not_a_resolved_release_lock(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["dependency_status"], "RANGE_CHECK_PASSED")
        self.assertFalse(result["dependency_lock_verified"])
        self.assertFalse(result["runtime_compatibility_verified"])
        self.assertEqual(result["packages"]["torch"]["version"], "2.4.0+cu124")

    def test_missing_declared_contract_never_bypasses_version_checks(self):
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None), patch.object(
            probe.Path, "read_text", side_effect=FileNotFoundError("missing package payload")
        ):
            result = probe.inspect("BALANCED", 0)
        self.assertIn("DECLARED_DEPENDENCY_CONTRACT_UNAVAILABLE", result["errors"])
    def test_invalid_host_arguments_hold_before_any_dependency_or_gpu_probe(self):
        for profile, index, reason in ((None, 0, "GPU_PROFILE_INVALID"),
                                      ([], 0, "GPU_PROFILE_INVALID"),
                                      ("unknown", 0, "GPU_PROFILE_INVALID"),
                                      ("ECO", True, "GPU_INDEX_INVALID"),
                                      ("ECO", -1, "GPU_INDEX_INVALID"),
                                      ("ECO", "0", "GPU_INDEX_INVALID")):
            with self.subTest(profile=profile, index=index), patch.object(
                probe.metadata, "version", side_effect=AssertionError("invalid settings must not probe packages")
            ), patch.object(probe.train_qlora, "nvidia_smi", side_effect=AssertionError("no GPU process")):
                result = probe.inspect(profile, index)
                self.assertEqual(result["status"], "HOLD")
                self.assertIn(reason, result["errors"])

    def test_broken_installed_metadata_is_reported_not_installed(self):
        for invalid in (None, "", "  ", 12):
            with self.subTest(invalid=invalid), patch.object(probe.platform, "system", return_value="Linux"), patch.object(
                probe.metadata, "version", return_value=invalid
            ):
                result = probe.inspect("BALANCED", 0)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["packages"]["torch"]["state"], "INVALID")
                self.assertIn("PACKAGE_METADATA_INVALID:torch", result["errors"])

    def test_unreadable_metadata_returns_structured_hold(self):
        with patch.object(probe.platform, "system", return_value="Linux"), patch.object(
            probe.metadata, "version", side_effect=ValueError("malformed installation metadata")
        ):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["packages"]["torch"]["state"], "INVALID")
        self.assertIn("PACKAGE_METADATA_INVALID:torch", result["errors"])

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
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value=None):
            result = probe.inspect("BALANCED", 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("NVIDIA_TELEMETRY_UNAVAILABLE", result["errors"])

    def test_selected_uuid_and_sufficient_actual_free_memory_semantics(self):
        device = {"index": "1", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Test NVIDIA", "memory_total_mib": "12288"}
        cuda = SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                               is_initialized=lambda: False)
        fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="fixture"))
        with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
            probe.metadata, "version", side_effect=VERSIONS.__getitem__
        ), patch.object(probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
            probe.train_qlora, "gpu_inventory", return_value=[device]
        ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64.0), patch.object(
            probe.train_qlora, "gpu_vram_headroom",
            return_value={"free_mib": 11000, "total_mib": 12288, "gui_reserve_mib": 2458}
        ), patch.dict(sys.modules, {"torch": fake_torch}):
            result = probe.inspect("BALANCED", 1)
        self.assertEqual(result["status"], "HARDWARE_READY_ONLY")
        self.assertFalse(result["model_license_verified"])
        self.assertFalse(result["dataset_rights_verified"])
        self.assertEqual(result["gpu"]["free_mib"], 11000)
        self.assertFalse(result["runtime_training_verified"])

    def test_preflight_restores_cuda_environment_and_rejects_initialized_runtime(self):
        device = {"index": "0", "uuid": "GPU-12345678-1234-1234-1234-123456789012",
                  "name": "Test NVIDIA", "memory_total_mib": "12288"}
        for initialized, available in ((False, True), (False, False), (True, True)):
            with self.subTest(initialized=initialized, available=available):
                calls = []
                def is_available():
                    calls.append(True)
                    self.assertEqual(probe.os.environ["CUDA_VISIBLE_DEVICES"], device["uuid"])
                    return available
                cuda = SimpleNamespace(is_available=is_available, device_count=lambda: 1,
                                       is_initialized=lambda: initialized)
                fake_torch = SimpleNamespace(cuda=cuda, version=SimpleNamespace(cuda="fixture"))
                with patch.object(probe.platform, "system", return_value="Windows"), patch.object(
                    probe.metadata, "version", side_effect=VERSIONS.__getitem__
                ), patch.object(probe.train_qlora, "nvidia_smi", return_value="nvidia-smi"), patch.object(
                    probe.train_qlora, "gpu_inventory", return_value=[device]
                ), patch.object(probe.train_qlora, "gpu_temperature", return_value=64.0), patch.object(
                    probe.train_qlora, "gpu_vram_headroom", return_value={"free_mib": 11000}
                ), patch.dict(sys.modules, {"torch": fake_torch}), patch.dict(
                    probe.os.environ, {"CUDA_VISIBLE_DEVICES": "original-device"}, clear=True
                ):
                    result = probe.inspect("BALANCED", 0)
                    self.assertEqual(probe.os.environ.get("CUDA_VISIBLE_DEVICES"), "original-device")
                    self.assertNotIn("CUDA_DEVICE_ORDER", probe.os.environ)
                if initialized:
                    self.assertEqual(result["status"], "HOLD")
                    self.assertIn("CUDA_PREFLIGHT_FRESH_PROCESS_REQUIRED", result["errors"])
                    self.assertFalse(calls)
                else:
                    self.assertEqual(result["status"], "HARDWARE_READY_ONLY" if available else "HOLD")


if __name__ == "__main__":
    unittest.main()
