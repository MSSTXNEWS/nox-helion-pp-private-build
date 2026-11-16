"""Source-only, fail-closed argv profile for pinned Maya DeepSeek on 2x V100.

This module renders an advisory command only. It never launches Maya, creates a
CUDA context, packs files, starts a service, or changes STOP/lease state.
Unknown or absent native evidence remains HOLD.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import maya_launch_preflight_v1 as preflight
import maya_binary_attestation_v1 as binary_attestation
import maya_runtime_memory_budget_v1 as runtime_memory_budget
import maya_gpu_topology_v1 as gpu_topology

MAYA_BINARY = Path(
    "/root/nox/engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4"
)
MAYA_BINARY_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
# These are requested launch parameters, not observed hardware facts.
REQUESTED_GPU_IDS = (0, 1)
REQUESTED_TP = 2

# Conservative first smoke inputs, not measured tuning results.
MAX_CONTEXT = 4096
RESERVE_MIB = 3072
PARALLEL = 1


def build_source_plan(*, owner_stop, observed_binary_sha256,
                      verified_files, tensor_types, model_file_paths,
                      tensor_role_inventory=None, runtime_observation=None,
                      runtime_budget=None):
    """Build exact argv only after all pinned source preflight checks pass."""
    if owner_stop is not False:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if observed_binary_sha256 != MAYA_BINARY_SHA256:
        return {"state": "HOLD_MAYA_BINARY_SHA256", "launchable": False}
    attested = binary_attestation.attest_maya_binary(MAYA_BINARY, MAYA_BINARY_SHA256)
    if attested.get("state") != "BINARY_BUILD_ATTESTED_SOURCE_ONLY":
        return {"state": attested.get("state", "HOLD_MAYA_BINARY_BUILD_UNATTESTED"),
                "launchable": False}

    checked = preflight.evaluate_source_plan(
        stop_present=False,
        gpu_ids=REQUESTED_GPU_IDS,
        tp=REQUESTED_TP,
        max_context=MAX_CONTEXT,
        reserve_mib=RESERVE_MIB,
        verified_files=verified_files,
        tensor_types=tensor_types,
        model_file_paths=model_file_paths,
        tensor_role_inventory=tensor_role_inventory,
    )
    if checked.get("state") != "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE":
        return {"state": checked.get("state", "HOLD_PREFLIGHT_UNKNOWN"),
                "launchable": False}
    if not binary_attestation.binary_identity_matches(
            MAYA_BINARY, attested.get("binary_identity")):
        return {"state": "HOLD_MAYA_BINARY_CHANGED_AFTER_PREFLIGHT", "launchable": False}

    topology = gpu_topology.collect_two_v100_topology()
    if topology.get("state") != "NATIVE_GPU_TOPOLOGY_VERIFIED":
        return {"state": "HOLD_UNVERIFIED_GPU_TOPOLOGY",
                "gpu_topology_state": topology.get("state", "HOLD_NATIVE_GPU_UNKNOWN"),
                "gpu_topology": topology,
                "requested_gpu_ids": list(REQUESTED_GPU_IDS),
                "requested_tensor_parallel": REQUESTED_TP,
                "launchable": False}

    memory = runtime_memory_budget.evaluate_memory_budget(runtime_observation, runtime_budget)
    if memory.get("admission_state") != "PASS_VERIFIED_RUNTIME_MEMORY":
        return {"state": memory.get("state", "HOLD_UNVERIFIED_PROVENANCE"),
                "admission_state": "HOLD_UNVERIFIED_PROVENANCE",
                "gpu_topology": topology,
                "requested_gpu_ids": list(REQUESTED_GPU_IDS),
                "requested_tensor_parallel": REQUESTED_TP,
                "effective_tensor_parallel": "NOT_TESTED_UNTIL_NATIVE_RUNTIME_INFO",
                "launchable": False, "runtime_memory": memory}

    pack_dir = checked["packer_output_dir"]
    argv = [
        str(MAYA_BINARY),
        "--pack", pack_dir,
        "--gpus", ",".join(str(gpu_id) for gpu_id in REQUESTED_GPU_IDS),
        "--tp", str(REQUESTED_TP),
        "--max-context", str(MAX_CONTEXT),
        "--reserve-mib", str(RESERVE_MIB),
        "--expert-profile", "none",
        "--dspark", "none",
        "--parallel", str(PARALLEL),
        "--serve",
    ]
    return {
        "state": "SOURCE_ONLY_COMMAND_READY_NOT_LAUNCHABLE",
        "launchable": False,
        "argv": argv,
        "env": {"CUDA_VISIBLE_DEVICES": ",".join(str(gpu_id) for gpu_id in REQUESTED_GPU_IDS)},
        "model_pack": pack_dir,
        "engine_sha256": MAYA_BINARY_SHA256,
        "binary_build_attestation": attested,
        "gpu_topology": topology,
        "gpu_names": [row["name"] for row in topology["devices"]],
        "gpus": list(topology["visible_ids"]),
        "requested_tensor_parallel": REQUESTED_TP,
        "effective_tensor_parallel": "NOT_TESTED_UNTIL_NATIVE_RUNTIME_INFO",
        "context_tokens": MAX_CONTEXT,
        "vram_reserve_mib": RESERVE_MIB,
        "parallel_requests": PARALLEL,
        "expert_mapping": "GGUF expert source is file-backed; CPU-lane RAM copies depend on Maya mmap-experts=auto and the native RAM budget",
        "mmap_experts_cli": "omitted: Maya default auto is retained; actual RAM-versus-file placement requires runtime readback",
        "kv_cache_fit": memory["state"],
        "runtime_fit": memory["state"],
        "runtime_memory_budget": memory,
        "drafting": "disabled",
        "precision_override": "none; GGUF quantization comes from verified model files",
        "protocol": "Maya stdin/stdout engine protocol; not an HTTP endpoint",
        "measured": False,
    }

