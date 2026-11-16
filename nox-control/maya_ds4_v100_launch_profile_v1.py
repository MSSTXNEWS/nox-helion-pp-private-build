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
import maya_memory_admission_v1 as memory_admission

MAYA_BINARY = Path(
    "/root/nox/engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4"
)
MAYA_BINARY_SHA256 = "3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20"
GPU_NAMES = ("Tesla V100-SXM2-32GB", "Tesla V100-SXM2-32GB")
GPU_IDS = (0, 1)
TP = 2

# Conservative first smoke inputs, not measured tuning results.
MAX_CONTEXT = 4096
RESERVE_MIB = 3072
PARALLEL = 1


def build_source_plan(*, owner_stop, observed_binary_sha256, gpu_names,
                      verified_files, tensor_types, model_file_paths,
                      tensor_role_inventory=None, memory_snapshot=None,
                      memory_budget=None, now_seconds=None):
    """Build exact argv only after all pinned source preflight checks pass."""
    if owner_stop is not False:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if observed_binary_sha256 != MAYA_BINARY_SHA256:
        return {"state": "HOLD_MAYA_BINARY_SHA256", "launchable": False}
    if not isinstance(gpu_names, (list, tuple)) or tuple(gpu_names) != GPU_NAMES:
        return {"state": "HOLD_TWO_V100_IDENTITY", "launchable": False}

    attested = binary_attestation.attest_maya_binary(MAYA_BINARY, MAYA_BINARY_SHA256)
    if attested.get("state") != "BINARY_BUILD_ATTESTED_SOURCE_ONLY":
        return {"state": attested.get("state", "HOLD_MAYA_BINARY_BUILD_UNATTESTED"),
                "launchable": False}

    memory = memory_admission.evaluate_memory_admission(
        snapshot=memory_snapshot,
        budget=memory_budget,
        now_seconds=now_seconds,
        required_context_tokens=MAX_CONTEXT,
        minimum_gpu_reserve_bytes=RESERVE_MIB * 1024 * 1024,
    )
    if memory.get("state") != "MEMORY_ADMISSION_PASS_SOURCE_ONLY":
        return {"state": memory.get("state", "HOLD_MEMORY_ADMISSION_UNKNOWN"),
                "launchable": False, "memory_admission": memory}

    checked = preflight.evaluate_source_plan(
        stop_present=False,
        gpu_ids=GPU_IDS,
        tp=TP,
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

    pack_dir = checked["packer_output_dir"]
    argv = [
        str(MAYA_BINARY),
        "--pack", pack_dir,
        "--gpus", "0,1",
        "--tp", "2",
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
        "env": {"CUDA_VISIBLE_DEVICES": "0,1"},
        "model_pack": pack_dir,
        "engine_sha256": MAYA_BINARY_SHA256,
        "binary_build_attestation": attested,
        "memory_admission": memory,
        "gpu_names": list(GPU_NAMES),
        "gpus": list(GPU_IDS),
        "tensor_parallel": TP,
        "context_tokens": MAX_CONTEXT,
        "vram_reserve_mib": RESERVE_MIB,
        "parallel_requests": PARALLEL,
        "expert_mapping": "GGUF hot experts in VRAM cache; CPU-lane experts read in-place from model files",
        "mmap_experts_cli": "omitted: Maya forces file-backed CPU-lane experts for GGUF; --mmap-experts does not change that path",
        "kv_cache_fit": "HOLD_LIVE_VRAM_AND_RAM_READBACK_REQUIRED",
        "runtime_fit": "HOLD_LIVE_FREE_MEMORY_PREFLIGHT_REQUIRED",
        "drafting": "disabled",
        "precision_override": "none; GGUF quantization comes from verified model files",
        "protocol": "Maya stdin/stdout engine protocol; not an HTTP endpoint",
        "measured": False,
    }

