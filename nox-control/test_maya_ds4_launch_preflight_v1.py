"""Offline/synthetic and immutable-source checks; no model, CUDA, or inference."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
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
        self.assertEqual(got["state"], "AVAILABLE_PATHS_ONLY")
        self.assertNotIn("compatible", str(got).lower())
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
        with patch.object(PLAN, "observe_packer_output", return_value={
                "state": "PACKER_OUTPUT_ABSENT_VERIFIED",
                "model_dir": "/synthetic/model",
                "output_dir": "/synthetic/model/maya-ds4"}):
            got = PLAN.evaluate_source_plan(
                stop_present=False, gpu_ids=(0, 1), tp=2, max_context=65536,
                reserve_mib=1024, verified_files=complete_rows(),
                tensor_types=("BF16", "Q5_K", "Q6_K", "Q8_0", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6)
        self.assertEqual(got["state"], "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE")
        self.assertFalse(got["launchable"])
        self.assertEqual(got["unique_verified_files"], 6)
        self.assertEqual(got["unique_bytes"], 248_834_257_920)
        self.assertIn("--serve", got["command_contract"])
        self.assertEqual(got["packer_model_dir"], "/synthetic/model")
        self.assertEqual(got["packer_output_dir"], "/synthetic/model/maya-ds4")
        self.assertTrue(got["packer_non_clobber_precondition"])
        self.assertEqual(got["model_content_sha256"], "VERIFIED_AGAINST_PINNED_FACTS")
        self.assertEqual(got["model_tensor_inventory"], "NOT_TESTED_BY_SOURCE_PREFLIGHT")
        self.assertEqual(got["runtime_abi"], "NOT_TESTED")
        self.assertEqual(got["sm70_execution"], "NOT_TESTED")
        self.assertEqual(got["runtime_compatibility"], "NOT_TESTED")

    def test_output_observation_rejects_existing_directory_symlink_and_unknown_paths(self):
        names = PLAN.EXPECTED_FILES
        payloads = {name: ("fixture:" + name).encode() for name in names}
        facts = {name: (len(data), hashlib.sha256(data).hexdigest())
                 for name, data in payloads.items()}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(PLAN, "PINNED_FILE_FACTS", facts):
            model = Path(tmp) / "model"
            model.mkdir()
            paths = []
            for name, data in payloads.items():
                path = model / name
                path.write_bytes(data)
                paths.append(path)
            absent = PLAN.observe_packer_output(paths)
            self.assertEqual(absent["state"], "PACKER_OUTPUT_ABSENT_VERIFIED")
            # Same path/name/size is not enough: bad bytes must fail the pinned digest.
            original = paths[0].read_bytes()
            paths[0].write_bytes(b"x" * len(original))
            self.assertEqual(PLAN.observe_packer_output(paths)["state"],
                             "HOLD_PACKER_MODEL_SHA256_MISMATCH")
            paths[0].write_bytes(original)
            self.assertEqual(PLAN.observe_packer_output(paths)["state"],
                             "PACKER_OUTPUT_ABSENT_VERIFIED")
            self.assertEqual(absent["output_dir"], str(model / "maya-ds4"))
            self.assertFalse((model / "maya-ds4").exists())

            output = model / "maya-ds4"
            output.mkdir()
            self.assertEqual(PLAN.observe_packer_output(paths)["state"],
                             "HOLD_PACKER_OUTPUT_EXISTS")
            output.rmdir()

            target = Path(tmp) / "existing-output"
            target.mkdir()
            output.symlink_to(target, target_is_directory=True)
            self.assertEqual(PLAN.observe_packer_output(paths)["state"],
                             "HOLD_PACKER_OUTPUT_EXISTS")
            output.unlink()

            self.assertEqual(PLAN.observe_packer_output(None)["state"],
                             "HOLD_PACKER_MODEL_PATH_UNKNOWN")
            self.assertEqual(PLAN.observe_packer_output(
                [Path(tmp) / "missing" / name for name in names])["state"],
                "HOLD_PACKER_MODEL_INPUT_MISSING")
            self.assertEqual(PLAN.observe_packer_output(paths[:-1])["state"],
                             "HOLD_PACKER_MODEL_PATH_UNKNOWN")

    def test_caller_cannot_spoof_output_absence_boolean(self):
        with self.assertRaises(TypeError):
            PLAN.evaluate_source_plan(
                stop_present=False, gpu_ids=(0, 1), tp=2, max_context=4096,
                reserve_mib=1024, verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                packer_output_absent=True)

    def test_source_plan_without_path_observation_holds(self):
        got = PLAN.evaluate_source_plan(
            stop_present=False, gpu_ids=(0, 1), tp=2, max_context=4096,
            reserve_mib=1024, verified_files=complete_rows(),
            tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(got["state"], "HOLD_PACKER_MODEL_PATH_UNKNOWN")

    def test_exact_manifest_and_packer_shard_contract(self):
        expected = tuple(
            [f"DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000{i}-of-00006.gguf"
             for i in range(1, 6)] +
            ["DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"])
        self.assertEqual(PLAN.EXPECTED_FILES, expected)
        self.assertEqual(len(set(PLAN.EXPECTED_FILES)), 6)
        self.assertEqual(set(PLAN.PINNED_FILE_FACTS), set(PLAN.EXPECTED_FILES))
        packer = maya_source("tools/ds4/pack_gguf.py")
        # Maya requires five supplied trunk files plus the omitted logical 00006
        # shard and an explicit Engram source when split.count is six.
        self.assertIn('ap.add_argument("--shards", nargs="+",', packer)
        self.assertIn('ap.add_argument("--without", nargs="+", default=[]', packer)
        self.assertIn('ap.add_argument("--engram"', packer)
        self.assertIn("split != len(gs) + len(a.without)", packer)
        self.assertIn("if a.without and not a.engram:", packer)
        self.assertIn('model / "maya-ds4"', packer)
        self.assertIn('open("w")', packer)
        self.assertIn('open("wb")', packer)

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

    def test_unconfirmed_fp8_fp4_or_mxfp_kernels_are_rejected(self):
        for unsupported in ("FP8_E4M3", "MXFP8", "FP4", "MXFP4"):
            with self.subTest(tensor_type=unsupported):
                got = PLAN.evaluate_source_plan(
                    stop_present=False, gpu_ids=(0, 1), tp=2, max_context=65536,
                    reserve_mib=1024, verified_files=complete_rows(),
                    tensor_types=("BF16", "IQ2_XXS", "IQ4_NL", unsupported))
                self.assertEqual(got["state"], "HOLD_UNCONFIRMED_TENSOR_KERNEL")
                self.assertIn(unsupported, got["unknown_types"])

    def test_invalid_gpu_context_or_reserve_holds(self):
        common = dict(stop_present=False, verified_files=complete_rows(),
                      tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"))
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0,), tp=1, max_context=65536,
                         reserve_mib=1024, **common)["state"], "HOLD_TWO_V100_TP2_REQUIRED")
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0, 1), tp=2, max_context=0,
                         reserve_mib=1024, **common)["state"], "HOLD_CONTEXT_EXPLICIT_OR_TOO_LARGE")
        self.assertEqual(PLAN.evaluate_source_plan(gpu_ids=(0, 1), tp=2, max_context=65536,
                         reserve_mib=0, **common)["state"], "HOLD_POSITIVE_MEMORY_RESERVE_REQUIRED")

    def test_hash_reader_rejects_symlinks_even_with_identical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.gguf"
            path.write_bytes(b"safe-original")
            self.assertEqual(PLAN._sha256_file(path),
                             hashlib.sha256(b"safe-original").hexdigest())
            link = Path(tmp) / "alias.gguf"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                PLAN._sha256_file(link)

    def test_hash_reader_holds_when_name_replaced_during_read(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.gguf"
            replacement = Path(tmp) / "replacement.gguf"
            path.write_bytes(b"same-content")
            replacement.write_bytes(b"same-content")
            original_fstat = os.fstat
            calls = [0]
            def replace_on_second_fstat(fd):
                calls[0] += 1
                if calls[0] == 2:
                    os.replace(replacement, path)
                return original_fstat(fd)
            with patch.object(PLAN.os, "fstat", side_effect=replace_on_second_fstat):
                with self.assertRaises(OSError):
                    PLAN._sha256_file(path)
            self.assertEqual(calls[0], 2)

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


class MayaV14PackReadinessTests(unittest.TestCase):
    """Isolated source-only safety regressions; never execute Maya or pack weights."""

    def _profile(self):
        spec = importlib.util.spec_from_file_location(
            "maya_ds4_v100_launch_profile_v14_test",
            HERE / "maya_ds4_v100_launch_profile_v1.py")
        profile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile)
        return profile

    def test_absent_pack_never_exposes_executable_serve_argv(self):
        profile = self._profile()
        observed = {"state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
                    "packer_output_dir": "/synthetic/pinned/maya-ds4"}
        with patch.object(profile.preflight, "evaluate_source_plan", return_value=observed) as gate:
            result = profile.build_source_plan(
                owner_stop=False, observed_binary_sha256=profile.MAYA_BINARY_SHA256,
                gpu_names=profile.GPU_NAMES, verified_files=[],
                tensor_types=[], model_file_paths=[])
        self.assertEqual(result["state"], "SOURCE_ONLY_PACKING_REQUIRED_NOT_LAUNCHABLE")
        self.assertFalse(result["launchable"])
        self.assertFalse(result["production_serve_ready"])
        self.assertEqual(result["pack_state"], "ABSENT_VERIFIED_REQUIRES_REVIEWED_PACKER")
        self.assertNotIn("argv", result)
        template = result["argv_template_not_executable"]
        self.assertEqual(template[0], str(profile.MAYA_BINARY))
        self.assertEqual(template[template.index("--pack") + 1], observed["packer_output_dir"])
        self.assertIn("--serve", template)
        self.assertEqual(gate.call_count, 1)

    def test_failed_source_preflight_never_returns_even_a_template(self):
        profile = self._profile()
        with patch.object(profile.preflight, "evaluate_source_plan",
                          return_value={"state": "HOLD_PACKER_MODEL_SHA256_MISMATCH"}):
            result = profile.build_source_plan(
                owner_stop=False, observed_binary_sha256=profile.MAYA_BINARY_SHA256,
                gpu_names=profile.GPU_NAMES, verified_files=[],
                tensor_types=[], model_file_paths=[])
        self.assertEqual(result["state"], "HOLD_PACKER_MODEL_SHA256_MISMATCH")
        self.assertNotIn("argv_template_not_executable", result)
        self.assertNotIn("argv", result)

    def test_owner_stop_and_bad_binary_prevent_template_calculation(self):
        profile = self._profile()
        with patch.object(profile.preflight, "evaluate_source_plan") as gate:
            for stop, sha, expected in (
                (True, profile.MAYA_BINARY_SHA256, "HOLD_OWNER_STOP"),
                (None, profile.MAYA_BINARY_SHA256, "HOLD_OWNER_STOP"),
                (False, "0" * 64, "HOLD_MAYA_BINARY_SHA256"),
            ):
                result = profile.build_source_plan(
                    owner_stop=stop, observed_binary_sha256=sha,
                    gpu_names=profile.GPU_NAMES, verified_files=[],
                    tensor_types=[], model_file_paths=[])
                self.assertEqual(result["state"], expected)
                self.assertNotIn("argv", result)
                self.assertNotIn("argv_template_not_executable", result)
            gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
