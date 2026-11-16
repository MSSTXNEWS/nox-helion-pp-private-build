"""Offline/synthetic and immutable-source checks; no model, CUDA, or inference."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
PLAN_SPEC = importlib.util.spec_from_file_location(
    "maya_launch_preflight_v1", HERE / "maya_launch_preflight_v1.py")
PLAN = importlib.util.module_from_spec(PLAN_SPEC)
PLAN_SPEC.loader.exec_module(PLAN)
INSPECT_SPEC = importlib.util.spec_from_file_location(
    "owner_native_inspect_linkage_test", HERE / "owner_native_inspect.py")
INSPECT = importlib.util.module_from_spec(INSPECT_SPEC)
INSPECT_SPEC.loader.exec_module(INSPECT)

MAYA_BASE = "https://raw.githubusercontent.com/mw00/project-maya/c81fab6c9d63cf69b928f92460e0a662b28aa9ec/"


def maya_source(path):
    from urllib.request import urlopen
    with urlopen(MAYA_BASE + path, timeout=20) as response:
        if response.status != 200:
            raise AssertionError(f"{path}: HTTP {response.status}")
        return response.read().decode("utf-8")


def complete_rows():
    # Immutable manifest facts, never a caller-supplied "sha_verified" boolean alone.
    return [{"path": name, "bytes": PLAN.PINNED_FILE_FACTS[name][0],
             "sha256": PLAN.PINNED_FILE_FACTS[name][1], "sha_verified": True}
            for name in PLAN.EXPECTED_FILES]


class MayaLinkageReadOnlyTests(unittest.TestCase):
    def test_readelf_reports_dynamic_needs_without_running_maya(self):
        output = """Dynamic section at offset 0x1000 contains 4 entries:
 0x0000000000000001 (NEEDED) Shared library: [libcudart.so.12]
 0x0000000000000001 (NEEDED) Shared library: [libcublas.so.12]
 0x000000000000001d (RUNPATH) Library runpath: [/usr/local/cuda/lib64]
"""
        cp = type("Completed", (), {"returncode": 0, "stdout": output})()
        pin = {"state": "SHA_PIN_MATCH_ELF_ONLY", "observed_sha256": "a" * 64, "bytes": 71289520}
        with patch.object(INSPECT, "maya_p0_binary_readback", return_value=pin), \
             patch.object(INSPECT.shutil, "which", return_value="/usr/bin/readelf"), \
             patch.object(INSPECT.subprocess, "run", return_value=cp) as run:
            got = INSPECT.maya_elf_linkage_readback(Path("/tmp/nox"))
        self.assertEqual(got["state"], "ELF_LINKAGE_READ_ONLY")
        self.assertEqual(got["needed_sonames"], ["libcudart.so.12", "libcublas.so.12"])
        self.assertFalse(got["cuda_driver_direct_needed"])
        self.assertTrue(got["cuda_driver_expected_at_runtime"])
        self.assertEqual(got["dependency_resolution"], "NOT_TESTED")
        self.assertTrue(got["cublas_needed"])
        self.assertTrue(got["cuda_runtime_needed"])
        self.assertFalse(got["maya_executable_invoked"])
        self.assertFalse(got["cuda_context_created"])
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/readelf")
        self.assertNotIn(str(Path("/tmp/nox") / "engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4"),
                          run.call_args.args[0][0][0])

    def test_hash_mismatch_blocks_readelf(self):
        pin = {"state": "HOLD_BINARY_SHA_MISMATCH", "observed_sha256": "0" * 64}
        with patch.object(INSPECT, "maya_p0_binary_readback", return_value=pin), \
             patch.object(INSPECT.subprocess, "run") as run:
            got = INSPECT.maya_elf_linkage_readback(Path("/tmp/nox"))
        self.assertEqual(got["state"], "HOLD_BINARY_PIN")
        run.assert_not_called()

    def test_ldconfig_cache_paths_are_stat_only(self):
        import tempfile
        names = ("libcuda.so.1", "libcudart.so.12", "libcublas.so.12", "libcublasLt.so.12")
        with tempfile.TemporaryDirectory() as temp:
            lines = []
            for name in names:
                path = Path(temp) / name
                path.write_bytes(b"synthetic-link-target")
                lines.append(f"\t{name} (libc6,x86-64) => {path}")
            cp = type("Completed", (), {"returncode": 0, "stdout": "\n".join(lines)})()
            with patch.object(INSPECT.shutil, "which", return_value="/sbin/ldconfig"), \
                 patch.object(INSPECT.subprocess, "run", return_value=cp) as run:
                got = INSPECT.maya_dependency_path_readback({
                    "state": "ELF_LINKAGE_READ_ONLY", "rpath": []})
        self.assertEqual(got["state"], "AVAILABLE_PATHS_ONLY")
        self.assertEqual(got["cuda_toolkit_path_version_hint"], "UNKNOWN")
        self.assertEqual(got["runtime_abi"], "NOT_TESTED")
        self.assertFalse(got["maya_executable_invoked"])
        self.assertFalse(got["cuda_context_created"])
        self.assertTrue(all(row["present"] for row in got["libraries"].values()))
        self.assertEqual(run.call_args.args[0], ["/sbin/ldconfig", "-p"])
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_missing_cublaslt_path_is_hold(self):
        import tempfile
        names = ("libcuda.so.1", "libcudart.so.12", "libcublas.so.12")
        with tempfile.TemporaryDirectory() as temp:
            lines = []
            for name in names:
                path = Path(temp) / name
                path.write_bytes(b"synthetic-link-target")
                lines.append(f"\t{name} (libc6,x86-64) => {path}")
            cp = type("Completed", (), {"returncode": 0, "stdout": "\n".join(lines)})()
            with patch.object(INSPECT.shutil, "which", return_value="/sbin/ldconfig"), \
                 patch.object(INSPECT.subprocess, "run", return_value=cp):
                got = INSPECT.maya_dependency_path_readback({
                    "state": "ELF_LINKAGE_READ_ONLY", "rpath": []})
        self.assertEqual(got["state"], "HOLD_REQUIRED_LIBRARY_PATH_MISSING")
        self.assertFalse(got["libraries"]["libcublasLt.so.12"]["present"])


class MayaLaunchPlanTests(unittest.TestCase):
    def test_stop_blocks_launch_even_with_complete_inputs(self):
        got = PLAN.evaluate_source_plan(
            stop_present=True, gpu_ids=(0, 1), tp=2, max_context=65536,
            reserve_mib=1024, verified_files=complete_rows(),
            tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(got["state"], "HOLD_OWNER_STOP")
        self.assertFalse(got["launchable"])

    def test_complete_inputs_produce_non_launchable_plan_only(self):
        got = PLAN.evaluate_source_plan(
            stop_present=False, gpu_ids=(0, 1), tp=2, max_context=65536,
            reserve_mib=1024, verified_files=complete_rows(),
            tensor_types=("BF16", "Q5_K", "Q6_K", "Q8_0", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(got["state"], "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE")
        self.assertFalse(got["launchable"])
        self.assertEqual(got["unique_verified_files"], 6)
        self.assertEqual(got["unique_bytes"], 248_834_257_920)
        self.assertIn("--serve", got["command_contract"])

    def test_missing_engram_or_bad_digest_holds(self):
        rows = complete_rows()[:-1]
        args = dict(stop_present=False, gpu_ids=(0, 1), tp=2, max_context=65536,
                    reserve_mib=1024, verified_files=rows,
                    tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(PLAN.evaluate_source_plan(**args)["state"],
                         "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED")
        rows = complete_rows()
        rows[0]["sha256"] = "abc"
        args["verified_files"] = rows
        self.assertEqual(PLAN.evaluate_source_plan(**args)["state"],
                         "HOLD_SIZE_OR_SHA256_UNVERIFIED")

    def test_duplicate_or_synthetic_weight_attestation_fails_closed(self):
        base=dict(stop_present=False, gpu_ids=(0, 1), tp=2, max_context=4096,
                  reserve_mib=1024, tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        rows=complete_rows()
        duplicated=rows + [dict(rows[0])]
        self.assertEqual(PLAN.evaluate_source_plan(verified_files=duplicated, **base)["state"],
                         "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED")
        forged=complete_rows()
        forged[1]["sha256"]="a"*64
        self.assertEqual(PLAN.evaluate_source_plan(verified_files=forged, **base)["state"],
                         "HOLD_SIZE_OR_SHA256_UNVERIFIED")
        wrong_size=complete_rows()
        wrong_size[3]["bytes"]+=1
        self.assertEqual(PLAN.evaluate_source_plan(verified_files=wrong_size, **base)["state"],
                         "HOLD_SIZE_OR_SHA256_UNVERIFIED")

    def test_unknown_stop_or_malformed_native_attestations_hold_without_exception(self):
        common = dict(stop_present=False, gpu_ids=(0, 1), tp=2,
                      max_context=4096, reserve_mib=1024,
                      verified_files=complete_rows(),
                      tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        for unknown_stop in (None, "", 0, [], {}):
            with self.subTest(owner_stop=repr(unknown_stop)):
                self.assertEqual(PLAN.evaluate_source_plan(
                    **{**common, "stop_present": unknown_stop})["state"],
                    "HOLD_OWNER_STOP")
        for gpu in (None, "01", (False, True), [0, "1"], {"a": 0}):
            with self.subTest(gpu_ids=repr(gpu)):
                self.assertEqual(PLAN.evaluate_source_plan(
                    **{**common, "gpu_ids": gpu})["state"],
                    "HOLD_TWO_V100_TP2_REQUIRED")
        for tensors in (None, "IQ2_XXS", ({"bad": 1},), (1, "IQ2_XXS")):
            with self.subTest(tensor_types=repr(tensors)):
                self.assertEqual(PLAN.evaluate_source_plan(
                    **{**common, "tensor_types": tensors})["state"],
                    "HOLD_UNCONFIRMED_TENSOR_KERNEL")
        invalid = complete_rows()
        invalid[0]["path"] = []
        self.assertEqual(PLAN.evaluate_source_plan(
            **{**common, "verified_files": invalid})["state"],
            "HOLD_ALL_FIVE_SHARDS_AND_ENGRAM_REQUIRED")

    def test_unconfirmed_fp8_is_rejected(self):
        got = PLAN.evaluate_source_plan(
            stop_present=False, gpu_ids=(0, 1), tp=2, max_context=65536,
            reserve_mib=1024, verified_files=complete_rows(),
            tensor_types=("BF16", "IQ2_XXS", "IQ4_NL", "FP8_E4M3"))
        self.assertEqual(got["state"], "HOLD_UNCONFIRMED_TENSOR_KERNEL")
        self.assertIn("FP8_E4M3", got["unknown_types"])

    def test_invalid_gpu_context_or_reserve_holds(self):
        common = dict(stop_present=False, verified_files=complete_rows(),
                      tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0,), tp=1, max_context=65536,
                         reserve_mib=1024, **common)["state"], "HOLD_TWO_V100_TP2_REQUIRED")
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0, 1), tp=2, max_context=0,
                         reserve_mib=1024, **common)["state"], "HOLD_CONTEXT_EXPLICIT_OR_TOO_LARGE")
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0, 1), tp=2, max_context=65536,
                         reserve_mib=0, **common)["state"], "HOLD_POSITIVE_MEMORY_RESERVE_REQUIRED")

    def test_pinned_maya_source_contract(self):
        packer = maya_source("tools/ds4/pack_gguf.py")
        iq = maya_source("src/ds4/ds4_iq.cu")
        bf = maya_source("src/ds4/ds4_gguf.cu")
        main = maya_source("src/ds4/ds4_main.cpp")
        cmake = maya_source("CMakeLists.txt")
        setup = maya_source("docs/SETUP.md")
        self.assertIn('16: ("IQ2_XXS", 256, 66)', packer)
        self.assertIn('20: ("IQ4_NL", 32, 18)', packer)
        self.assertIn("template <> struct Ty<kIQ2_XXS>", iq)
        self.assertIn("case kIQ2_XXS: F(kIQ2_XXS); break;", iq)
        self.assertIn("bf16_mv_kernel", bf)
        self.assertIn("__uint_as_float(q.x << 16)", bf)
        self.assertNotIn("__nv_bfloat16", bf)
        self.assertIn('else if (a == "--gpus")', main)
        for option in ('--tp', '--max-context', '--reserve-mib', '--serve'):
            self.assertIn(option, main)
        self.assertIn("Volta (sm_70: GLM, maya-ds4 and maya-mm3 run on V100s)", cmake)
        self.assertIn("tensor parallel across pairs of equal GPUs", setup)
        self.assertIn("64K", setup)


if __name__ == "__main__":
    unittest.main()
