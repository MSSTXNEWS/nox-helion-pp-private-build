"""Offline/synthetic and immutable-source checks; no model, CUDA, or inference."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_maya_binary_attestation_v1 import MayaBinaryAttestationTests  # noqa: F401
from test_maya_runtime_memory_budget_v1 import MayaRuntimeMemoryBudgetTests  # noqa: F401

HERE = Path(__file__).parent
PLAN_SPEC = importlib.util.spec_from_file_location(
    "maya_launch_preflight_v1", HERE / "maya_launch_preflight_v1.py")
PLAN = importlib.util.module_from_spec(PLAN_SPEC)
PLAN_SPEC.loader.exec_module(PLAN)
INSPECT_SPEC = importlib.util.spec_from_file_location(
    "owner_native_inspect_linkage_test", HERE / "owner_native_inspect.py")
INSPECT = importlib.util.module_from_spec(INSPECT_SPEC)
INSPECT_SPEC.loader.exec_module(INSPECT)
PROFILE_SPEC = importlib.util.spec_from_file_location(
    "maya_ds4_v100_launch_profile_v1", HERE / "maya_ds4_v100_launch_profile_v1.py")
PROFILE = importlib.util.module_from_spec(PROFILE_SPEC)
PROFILE_SPEC.loader.exec_module(PROFILE)
MEMORY_SPEC = importlib.util.spec_from_file_location(
    "maya_runtime_memory_budget_v1", HERE / "maya_runtime_memory_budget_v1.py")
MEMORY = importlib.util.module_from_spec(MEMORY_SPEC)
MEMORY_SPEC.loader.exec_module(MEMORY)
BINARY_OK = {
    "state": "BINARY_BUILD_ATTESTED_SOURCE_ONLY",
    "binary_identity": {"st_dev": 1, "st_ino": 2, "st_size": 3,
                        "st_mtime_ns": 4, "st_ctime_ns": 5},
}

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


def synthetic_memory_inputs():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    gib = 1024 ** 3
    observation = {
        "readback_id": "fixture-owner-native-001",
        "gpus": [
            {"id": 0, "name": MEMORY.GPU_NAME, "total_bytes": 32 * gib,
             "free_bytes": 24 * gib, "captured_at": stamp, "source": "nvidia-smi"},
            {"id": 1, "name": MEMORY.GPU_NAME, "total_bytes": 32 * gib,
             "free_bytes": 24 * gib, "captured_at": stamp, "source": "nvidia-smi"},
        ],
        "cgroup": {"current_bytes": 16 * gib, "max_bytes": 48 * gib,
                   "captured_at": stamp, "source": "cgroup-v2"},
    }
    budget = {
        "gpu_ids": [0, 1],
        "context_tokens": 4096,
        "model_resident_bytes_by_gpu": [4 * gib, 4 * gib],
        "activation_bytes_by_gpu": [2 * gib, 2 * gib],
        "kv_cache_bytes_by_gpu": [8 * gib, 8 * gib],
        "gpu_reserve_bytes_by_gpu": [3 * gib, 3 * gib],
        "host_model_resident_bytes": 8 * gib,
        "host_activation_bytes": 1 * gib,
        "host_kv_cache_bytes": 0,
        "host_reserve_bytes": 4 * gib,
    }
    return observation, budget


def synthetic_tensor_roles():
    # GGUF-order dimensions; synthetic metadata only, never weight bytes.
    rows = [{"name": "token_embd.weight", "dtype": "Q5_K", "dims": [5120, 32000]}]
    for layer in range(40):
        rows.extend([
            {"name": f"blk.{layer}.ffn_gate_inp.weight", "dtype": "Q8_0", "dims": [5120, 384]},
            {"name": f"blk.{layer}.exp_probs_b.bias", "dtype": "F32", "dims": [384]},
            {"name": f"blk.{layer}.ffn_gate_exps.weight", "dtype": "IQ2_XXS", "dims": [5120, 384]},
            {"name": f"blk.{layer}.ffn_up_exps.weight", "dtype": "IQ2_XXS", "dims": [5120, 384]},
            {"name": f"blk.{layer}.ffn_down_exps.weight", "dtype": "IQ2_XXS", "dims": [384, 5120]},
        ])
    rows.append({"name": "blk.2.engram_embd.weight", "dtype": "IQ4_NL", "dims": [512, 1000]})
    return rows


def synthetic_gpu_stdout(*, second_uuid="GPU-bbbbbbbb-1111-2222-3333-555555555555",
                         first_free_mib="24576", second_free_mib="24576",
                         first_index="0", second_index="1", second_cc="7.0"):
    return "\\n".join([
        f"{first_index},GPU-aaaaaaaa-1111-2222-3333-444444444444,Tesla V100-SXM2-32GB,7.0,32768,{first_free_mib}",
        f"{second_index},{second_uuid},Tesla V100-SXM2-32GB,{second_cc},32768,{second_free_mib}",
    ]) + "\\n"


class MayaGpuTopologyTests(unittest.TestCase):
    def completed(self, stdout, returncode=0):
        return type("Completed", (), {"returncode": returncode, "stdout": stdout,
                                      "stderr": ""})()

    def test_direct_receipt_carries_unique_uuid_sm70_visible_ids_and_fresh_vram(self):
        with patch.object(PROFILE.gpu_topology.subprocess, "run",
                          return_value=self.completed(synthetic_gpu_stdout())), \
             patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            got = PROFILE.gpu_topology.collect_two_v100_topology()
        self.assertEqual(got["state"], "NATIVE_GPU_TOPOLOGY_VERIFIED")
        self.assertTrue(got["native_gpu_readback_verified"])
        self.assertFalse(got["launchable"])
        self.assertEqual(got["visible_ids"], [0, 1])
        self.assertEqual(got["device_uuids"], [
            "GPU-aaaaaaaa-1111-2222-3333-444444444444",
            "GPU-bbbbbbbb-1111-2222-3333-555555555555",
        ])
        self.assertEqual([row["compute_capability"] for row in got["devices"]], ["7.0", "7.0"])
        self.assertTrue(all(row["free_bytes"] > 0 for row in got["devices"]))
        self.assertEqual(got["visibility_binding"],
                         "CUDA_VISIBLE_DEVICES is pinned to this ordered UUID list; Maya --gpus uses visible ordinals")

    def test_missing_or_malformed_native_receipt_holds(self):
        with patch.object(PROFILE.gpu_topology.subprocess, "run",
                          side_effect=FileNotFoundError("nvidia-smi absent")):
            missing = PROFILE.gpu_topology.collect_two_v100_topology()
        self.assertEqual(missing["state"], "HOLD_NATIVE_GPU_COLLECTOR_UNAVAILABLE")
        self.assertFalse(missing["native_gpu_readback_verified"])
        self.assertFalse(missing["launchable"])
        with patch.object(PROFILE.gpu_topology.subprocess, "run",
                          return_value=self.completed(synthetic_gpu_stdout(second_uuid="GPU-aaaaaaaa-1111-2222-3333-444444444444"))), \
             patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            duplicate = PROFILE.gpu_topology.collect_two_v100_topology()
        self.assertEqual(duplicate["state"], "HOLD_NATIVE_GPU_TOPOLOGY")
        self.assertFalse(duplicate["launchable"])

    def test_wrong_sm_or_stale_native_query_holds(self):
        with patch.object(PROFILE.gpu_topology.subprocess, "run",
                          return_value=self.completed(synthetic_gpu_stdout(second_cc="8.0"))), \
             patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            wrong_sm = PROFILE.gpu_topology.collect_two_v100_topology()
        self.assertEqual(wrong_sm["state"], "HOLD_NATIVE_GPU_SM")
        self.assertFalse(wrong_sm["launchable"])
        with patch.object(PROFILE.gpu_topology.subprocess, "run",
                          return_value=self.completed(synthetic_gpu_stdout())), \
             patch.object(PROFILE.gpu_topology.time, "monotonic_ns",
                          side_effect=[1, 10_000_000_002]):
            stale = PROFILE.gpu_topology.collect_two_v100_topology()
        self.assertEqual(stale["state"], "HOLD_NATIVE_GPU_READBACK_STALE")
        self.assertFalse(stale["native_gpu_readback_verified"])
        self.assertFalse(stale["launchable"])

    def test_collector_accepts_no_caller_inventory_or_clock(self):
        with self.assertRaises(TypeError):
            PROFILE.gpu_topology.collect_two_v100_topology(
                inventory=synthetic_gpu_stdout(), now_utc="2026-11-16T00:00:00Z")


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


    def test_profile_holds_without_runtime_memory_observation(self):
        checked = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/synthetic/model/maya-ds4",
        }
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches", return_value=True), \
                patch.object(PROFILE.preflight, "evaluate_source_plan", return_value=checked), \
                patch.object(PROFILE.gpu_topology.subprocess, "run",
                             return_value=type("Completed", (), {"returncode": 1, "stdout": "",
                                                                 "stderr": "no native GPU telemetry"})()):
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                tensor_role_inventory=synthetic_tensor_roles(),
            )
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_GPU_TOPOLOGY")
        self.assertEqual(got["gpu_topology_state"], "HOLD_NATIVE_GPU_QUERY_FAILED")
        self.assertFalse(got["launchable"])
        self.assertNotIn("argv", got)

class MayaLaunchPlanTests(unittest.TestCase):

    def test_iq2_xxs_embedding_and_router_are_rejected(self):
        roles = synthetic_tensor_roles()
        next(row for row in roles if row["name"] == "token_embd.weight")["dtype"] = "IQ2_XXS"
        self.assertEqual(PLAN.validate_tensor_role_inventory(roles)["state"],
                         "HOLD_UNSUPPORTED_ROLE_DTYPE")
        roles = synthetic_tensor_roles()
        next(row for row in roles if row["name"] == "blk.0.ffn_gate_inp.weight")["dtype"] = "IQ2_XXS"
        got = PLAN.validate_tensor_role_inventory(roles)
        self.assertEqual(got["state"], "HOLD_UNSUPPORTED_ROLE_DTYPE")
        self.assertEqual(got["role"], "router")

    def test_iq2_xxs_expert_gate_up_down_and_iq4_nl_engram_are_allowed(self):
        got = PLAN.validate_tensor_role_inventory(synthetic_tensor_roles())
        self.assertEqual(got["state"], "ROLE_DTYPE_METADATA_PASS")
        self.assertEqual(got["roles_checked"]["routed_expert_layers"], 40)
        self.assertEqual(got["roles_checked"]["engram_tables"], 1)

    def test_expert_and_engram_roles_fail_closed_on_mismatch_or_bad_blocks(self):
        roles = synthetic_tensor_roles()
        next(row for row in roles if row["name"] == "blk.0.ffn_gate_exps.weight")["dtype"] = "IQ3_XXS"
        self.assertEqual(PLAN.validate_tensor_role_inventory(roles)["state"],
                         "HOLD_UNSUPPORTED_ROLE_DTYPE")
        roles = synthetic_tensor_roles()
        roles[-1]["dims"][0] = 510
        self.assertEqual(PLAN.validate_tensor_role_inventory(roles)["state"],
                         "HOLD_ENGRAM_IQ4_NL_BLOCK_ALIGNMENT")
        roles = synthetic_tensor_roles()
        roles[-1]["dtype"] = "IQ2_XXS"
        self.assertEqual(PLAN.validate_tensor_role_inventory(roles)["state"],
                         "HOLD_UNSUPPORTED_ROLE_DTYPE")

    def test_successful_source_plan_requires_role_metadata(self):
        with patch.object(PLAN, "observe_packer_output", return_value={
                "state": "PACKER_OUTPUT_ABSENT_VERIFIED",
                "model_dir": "/synthetic/model", "output_dir": "/synthetic/model/maya-ds4"}):
            got = PLAN.evaluate_source_plan(
                stop_present=False, gpu_ids=(0, 1), tp=2, max_context=4096,
                reserve_mib=1024, verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6)
        self.assertEqual(got["state"], "HOLD_TENSOR_ROLE_INVENTORY_REQUIRED")
        self.assertFalse(got["launchable"])
    def test_v100_profile_uses_supported_cli_and_omits_ineffective_gguf_mmap_flag(self):
        fake_preflight = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/synthetic/model/maya-ds4",
        }
        observation, budget = synthetic_memory_inputs()
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches", return_value=True), \
                patch.object(PROFILE.preflight, "evaluate_source_plan", return_value=fake_preflight), \
                patch.object(PROFILE.gpu_topology.subprocess, "run",
                             return_value=type("Completed", (), {"returncode": 0,
                                 "stdout": synthetic_gpu_stdout(), "stderr": ""})()), \
                patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                runtime_observation=observation,
                runtime_budget=budget)
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["runtime_memory"]["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["runtime_memory"]["arithmetic_state"], "WITHIN_REPORTED_CAPACITY")
        self.assertFalse(got["launchable"])
        self.assertNotIn("argv", got)
        self.assertFalse(got["runtime_memory"]["telemetry_authenticated"])

    def test_profile_rejects_caller_forged_gpu_inventory_or_receipt(self):
        self.assertFalse(hasattr(PROFILE, "GPU_NAMES"))
        with self.assertRaises(TypeError):
            PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                gpu_names=["Tesla V100", "Tesla V100"],
                gpu_receipt={"state": "NATIVE_GPU_TOPOLOGY_VERIFIED",
                             "uuid": "caller-forged", "visible_ids": [0, 1]})

    def test_synthetic_native_receipt_binds_visible_ordinals_to_uuid_and_keeps_cpu_lane_conditional(self):
        fake_preflight = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/synthetic/model/maya-ds4",
        }
        fake_memory = {"state": "SYNTHETIC_MEMORY_PASS_ONLY",
                       "admission_state": "PASS_VERIFIED_RUNTIME_MEMORY"}
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches", return_value=True), \
                patch.object(PROFILE.preflight, "evaluate_source_plan", return_value=fake_preflight), \
                patch.object(PROFILE.gpu_topology.subprocess, "run",
                             return_value=type("Completed", (), {"returncode": 0,
                                 "stdout": synthetic_gpu_stdout(), "stderr": ""})()), \
                patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]), \
                patch.object(PROFILE.runtime_memory_budget, "evaluate_memory_budget",
                             return_value=fake_memory):
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                tensor_role_inventory=synthetic_tensor_roles())
        self.assertEqual(got["state"], "SOURCE_ONLY_COMMAND_READY_NOT_LAUNCHABLE")
        self.assertFalse(got["launchable"])
        self.assertEqual(got["env"]["CUDA_VISIBLE_DEVICES"],
                         "GPU-aaaaaaaa-1111-2222-3333-444444444444,"
                         "GPU-bbbbbbbb-1111-2222-3333-555555555555")
        self.assertEqual(got["gpus"], [0, 1])
        self.assertEqual(got["gpu_names"], ["Tesla V100-SXM2-32GB", "Tesla V100-SXM2-32GB"])
        self.assertEqual(got["requested_tensor_parallel"], 2)
        self.assertEqual(got["effective_tensor_parallel"],
                         "NOT_TESTED_UNTIL_NATIVE_RUNTIME_INFO")
        self.assertIn("mmap-experts=auto", got["expert_mapping"])
        self.assertIn("depend on Maya mmap-experts=auto and the native RAM budget",
                      got["expert_mapping"])
        self.assertIn("omitted: Maya default auto is retained", got["mmap_experts_cli"])
        self.assertNotIn("--mmap-experts", got["mmap_experts_cli"])

    def test_v100_profile_holds_unknown_stop_before_preflight(self):
        with patch.object(PROFILE.preflight, "evaluate_source_plan") as evaluate:
            got = PROFILE.build_source_plan(
                owner_stop=None,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6)
        self.assertEqual(got["state"], "HOLD_OWNER_STOP")
        self.assertFalse(got["launchable"])
        evaluate.assert_not_called()

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
                tensor_role_inventory=synthetic_tensor_roles(),
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
        self.assertEqual(got["model_tensor_inventory"], "ROLE_DTYPE_CHECKED_FOR_SUPPLIED_METADATA_ONLY")
        self.assertEqual(got["role_dtype_gate"]["state"], "ROLE_DTYPE_METADATA_PASS")
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


class MayaLaunchProfileCliContractTests(unittest.TestCase):
    def test_profile_uses_only_pinned_maya_cli_and_keeps_live_fit_on_hold(self):
        checked = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/synthetic/model/maya-ds4",
        }
        observation, budget = synthetic_memory_inputs()
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches", return_value=True), \
                patch.object(PROFILE.preflight, "evaluate_source_plan", return_value=checked), \
                patch.object(PROFILE.gpu_topology.subprocess, "run",
                             return_value=type("Completed", (), {"returncode": 0,
                                 "stdout": synthetic_gpu_stdout(), "stderr": ""})()), \
                patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                runtime_observation=observation,
                runtime_budget=budget,
            )
        self.assertEqual(got["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["runtime_memory"]["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(got["runtime_memory"]["arithmetic_state"], "WITHIN_REPORTED_CAPACITY")
        self.assertFalse(got["launchable"])
        self.assertNotIn("argv", got)
        self.assertFalse(got["runtime_memory"]["telemetry_authenticated"])
    def test_profile_holds_without_local_sm70_binary_attestation(self):
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value={"state": "HOLD_MAYA_CMAKE_CUDA_ARCHITECTURES"}) as attest, \
                patch.object(PROFILE.preflight, "evaluate_source_plan") as run:
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                tensor_role_inventory=synthetic_tensor_roles(),
            )
        self.assertEqual(got["state"], "HOLD_MAYA_CMAKE_CUDA_ARCHITECTURES")
        self.assertFalse(got["launchable"])
        attest.assert_called_once_with(PROFILE.MAYA_BINARY, PROFILE.MAYA_BINARY_SHA256)
        run.assert_not_called()

    def test_profile_holds_if_binary_path_changes_during_model_preflight(self):
        checked = {
            "state": "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE",
            "packer_output_dir": "/synthetic/model/maya-ds4",
        }
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches",
                             return_value=False) as same_file, \
                patch.object(PROFILE.preflight, "evaluate_source_plan", return_value=checked):
            got = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                tensor_role_inventory=synthetic_tensor_roles(),
            )
        self.assertEqual(got["state"], "HOLD_MAYA_BINARY_CHANGED_AFTER_PREFLIGHT")
        self.assertFalse(got["launchable"])
        same_file.assert_called_once_with(PROFILE.MAYA_BINARY, BINARY_OK["binary_identity"])

    def test_profile_stop_and_unknown_stop_block_before_preflight(self):
        for stop in (True, None, 0, "unknown"):
            with self.subTest(owner_stop=repr(stop)):
                with patch.object(PROFILE.preflight, "evaluate_source_plan") as run:
                    got = PROFILE.build_source_plan(
                        owner_stop=stop,
                        observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                                verified_files=complete_rows(),
                        tensor_types=("BF16", "IQ2_XXS", "IQ4_NL"),
                        model_file_paths=["synthetic"] * 6,
                    )
                self.assertEqual(got["state"], "HOLD_OWNER_STOP")
                self.assertFalse(got["launchable"])
                run.assert_not_called()

    def test_pinned_maya_source_exposes_supported_cli_and_gguf_mapping_contract(self):
        main = maya_source("src/ds4/ds4_main.cpp")
        model = maya_source("src/ds4/ds4_model.cu")
        for option in ("--gpus", "--tp", "--max-context", "--reserve-mib",
                       "--cpu-threads", "--prefill-chunk", "--mmap-experts", "--parallel",
                       "--serve"):
            self.assertIn(option, main)
        self.assertIn("if (pk.gguf) file_experts = true;", model)
        self.assertIn("file_experts", model)


    def test_integrated_profile_forwards_role_map_and_holds_when_missing(self):
        packed = {
            "state": "PACKER_OUTPUT_ABSENT_VERIFIED",
            "model_dir": "/synthetic/model",
            "output_dir": "/synthetic/model/maya-ds4",
        }
        with patch.object(PROFILE.binary_attestation, "attest_maya_binary",
                          return_value=BINARY_OK), \
                patch.object(PROFILE.binary_attestation, "binary_identity_matches", return_value=True), \
                patch.object(PROFILE.preflight, "observe_packer_output", return_value=packed), \
                patch.object(PROFILE.gpu_topology.subprocess, "run",
                             return_value=type("Completed", (), {"returncode": 0,
                                 "stdout": synthetic_gpu_stdout(), "stderr": ""})()), \
                patch.object(PROFILE.gpu_topology.time, "monotonic_ns", side_effect=[1, 2]):
            missing = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "Q5_K", "Q6_K", "Q8_0", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
            )
            self.assertEqual(missing["state"], "HOLD_TENSOR_ROLE_INVENTORY_REQUIRED")
            self.assertFalse(missing["launchable"])
            ready = PROFILE.build_source_plan(
                owner_stop=False,
                observed_binary_sha256=PROFILE.MAYA_BINARY_SHA256,
                verified_files=complete_rows(),
                tensor_types=("BF16", "Q5_K", "Q6_K", "Q8_0", "IQ2_XXS", "IQ4_NL"),
                model_file_paths=["synthetic"] * 6,
                tensor_role_inventory=synthetic_tensor_roles(),
                runtime_observation=synthetic_memory_inputs()[0],
                runtime_budget=synthetic_memory_inputs()[1],
            )
        self.assertEqual(ready["state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(ready["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertEqual(ready["runtime_memory"]["admission_state"], "HOLD_UNVERIFIED_PROVENANCE")
        self.assertFalse(ready["launchable"])
        self.assertNotIn("argv", ready)


if __name__ == "__main__":
    unittest.main()

