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
                      verified_files, tensor_types, model_file_paths):
    """Build exact argv only after all pinned source preflight checks pass."""
    if owner_stop is not False:
        return {"state": "HOLD_OWNER_STOP", "launchable": False}
    if observed_binary_sha256 != MAYA_BINARY_SHA256:
        return {"state": "HOLD_MAYA_BINARY_SHA256", "launchable": False}
    if not isinstance(gpu_names, (list, tuple)) or tuple(gpu_names) != GPU_NAMES:
        return {"state": "HOLD_TWO_V100_IDENTITY", "launchable": False}

    checked = preflight.evaluate_source_plan(
        stop_present=False,
        gpu_ids=GPU_IDS,
        tp=TP,
        max_context=MAX_CONTEXT,
        reserve_mib=RESERVE_MIB,
        verified_files=verified_files,
        tensor_types=tensor_types,
        model_file_paths=model_file_paths,
    )
    if checked.get("state") != "SOURCE_ONLY_PLAN_READY_NOT_LAUNCHABLE":
        return {"state": checked.get("state", "HOLD_PREFLIGHT_UNKNOWN"),
                "launchable": False}

    # The preceding preflight explicitly proved the pack directory ABSENT.
    # Never expose an executable argv before the reviewed offline packer has
    # produced a complete pack and independent native readback has accepted it.
    # A command template is useful for review, but cannot authorize serving.
    pack_dir = checked["packer_output_dir"]
    argv_template = [
        str(MAYA_BINARY),
        "--pack", pack_dir,
        "--gpus", "0,1",
        "--tp", "2",
        "--max-context", str(MAX_CONTEXT),
        "--reserve-mib", str(RESERVE_MIB),
        "--expert-profile", "none",
        "--mmap-experts", "auto",
        "--dspark", "none",
        "--parallel", str(PARALLEL),
        "--serve",
    ]
    return {
        "state": "SOURCE_ONLY_PACKING_REQUIRED_NOT_LAUNCHABLE",
        "launchable": False,
        "production_serve_ready": False,
        "pack_state": "ABSENT_VERIFIED_REQUIRES_REVIEWED_PACKER",
        "required_next_stage": "OFFLINE_PACK_THEN_OWNER_SHA_AND_STOP_LEASE_READBACK",
        "argv_template_not_executable": argv_template,
        "env": {"CUDA_VISIBLE_DEVICES": "0,1"},
        "model_pack": pack_dir,
        "engine_sha256": MAYA_BINARY_SHA256,
        "gpu_names": list(GPU_NAMES),
        "gpus": list(GPU_IDS),
        "tensor_parallel": TP,
        "context_tokens": MAX_CONTEXT,
        "vram_reserve_mib": RESERVE_MIB,
        "parallel_requests": PARALLEL,
        "expert_mapping": "auto",
        "drafting": "disabled",
        "precision_override": "none; GGUF quantization comes from verified model files",
        "protocol": "Maya stdin/stdout engine protocol; not an HTTP endpoint",
        "measured": False,
    }
