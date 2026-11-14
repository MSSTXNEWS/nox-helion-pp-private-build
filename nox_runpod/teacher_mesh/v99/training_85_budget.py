"""NOX PRIME V99: measured 85%-target training resource budget for existing OneHost.

Pure policy, not a GPU scheduler or an optimizer. Compute utilization target
is 85% on an *admitted* GPU1 training job, not GPU memory allocation. The owner
chat stays on GPU0 with immediate P0 priority. CPU worker cap is 85% of visible
threads only under idle-chat and queue ownership; RAM is limited by the
*container cgroup* at 85%, never by misleading host MemAvailable.

No adapters, false consciousness, phantom job IDs, model switches, or overcommit.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import floor

TARGET_PERCENT=85
CGROUP_RATIO=0.85
GIB=1024**3
DISK_FLOOR_BYTES=10_000_000_000
GPU1_MIN_UNUSED_MIB=3072
RAM_UNCOMMITTED_MIN_BYTES=12*GIB
PREP_WORKER_START=4
PREP_WORKER_MAX=68


def resource_plan(live:Mapping)->dict:
    result={
        "schema":"NOX_V99_TRAINING_FIRST_RESOURCE_BUDGET_V1",
        "performed":False,
        "priority":"FULL_BASE_WEIGHT_TRAINING_FIRST_WITH_P0_RESONANCE",
        "target_compute_utilization_pct":TARGET_PERCENT,
        "training_gpu_index":1,
        "chat_gpu_index":0,
        "student_model_count":1,
        "new_scheduler":False,
        "new_backend":False,
        "training_started":False,
        "optimizer_steps_verified":0,
        "weight_changes_verified":False,
        "ram_cache_is_reclaimable":True,
        "disk_floor_for_new_writes_bytes":DISK_FLOOR_BYTES,
        "cpu_data_preparation":"HOLD",
        "gpu1_base_weight_training":"HOLD",
        "reasons":[],
    }
    if not isinstance(live,Mapping):
        return {**result,"reasons":["HOLD_NATIVE_TELEMETRY"]}
    reasons=result["reasons"]
    if live.get("native_verified") is not True:
        reasons.append("HOLD_NATIVE_TELEMETRY")
    if live.get("owner_authorized") is not True:
        reasons.append("HOLD_NATIVE_OWNER")
    if live.get("stop_active") is not False:
        reasons.append("HOLD_STOP")
    if live.get("chat_gpu0_healthy") is not True:
        reasons.append("HOLD_CHAT_MODEL")
    if live.get("s03_native_healthy") is not True:
        reasons.append("HOLD_S03")

    cpus=live.get("cpu_affinity_count")
    if type(cpus) is not int or not 2<=cpus<=4096:
        reasons.append("HOLD_CPU_COUNT")
    else:
        cap=max(1,min(PREP_WORKER_MAX,floor(cpus*CGROUP_RATIO)))
        result["cpu_worker_cap_when_chat_idle"]=cap
        result["cpu_workers_start"]=min(PREP_WORKER_START,cap)
        result["cpu_threads_reserved_for_chat"]=cpus-cap
        result["cpu_autoscale_needs_throughput_and_chat_p95"]=True
        result["cpu_limit_not_forced_utilization"]=True

    limit=live.get("cgroup_max_bytes")
    current=live.get("cgroup_current_bytes")
    if type(limit) is not int or type(current) is not int or limit<=0 or current<0:
        reasons.append("HOLD_CGROUP_LIMIT")
    else:
        ram_target=floor(limit*CGROUP_RATIO)
        headroom=max(0,ram_target-current)
        result.update({
           "cgroup_memory_limit_bytes":limit,
           "cgroup_memory_current_bytes":current,
           "ram_cache_85pct_target_bytes":ram_target,
           "ram_new_cache_budget_bytes":min(24*GIB, max(0,headroom)),
           "cgroup_current_utilization_pct":round(current*100/limit,1),
        })
        if limit-current<RAM_UNCOMMITTED_MIN_BYTES:
            reasons.append("HOLD_MEMORY_CHAT_RESERVE")
        if headroom<1*GIB:
            reasons.append("HOLD_RAM_85PCT_TARGET_REACHED")

    chat=live.get("chat_state")
    if chat not in ("idle","pending","generating"):
        reasons.append("HOLD_CHAT_STATE")
    if live.get("chat_recent") is not False or chat!="idle":
        reasons.append("CHAT_P0_PREEMPTS_BACKGROUND")
    if (not reasons and live.get("cpu_preparation_verified") is True
            and "cpu_worker_cap_when_chat_idle" in result):
        result["cpu_data_preparation"]="READY_FOR_EXISTING_ONEHOST_CPU_QUEUE"
    else:
        result["cpu_data_preparation"]="HOLD_OR_IDLE_REQUIRED"

    free=live.get("gpu1_free_mib")
    peak=live.get("gpu1_peak_training_mib")
    if type(free) is not int or not 0<=free<=65536:
        reasons.append("HOLD_GPU1_FREE_VRAM")
    if (type(peak) is not int or peak<=0 or
        live.get("gpu1_peak_profile_verified") is not True):
        reasons.append("HOLD_GPU1_MODEL_OPTIMIZER_PEAK")
    if type(free) is int and type(peak) is int and peak>0:
        result["gpu1_measured_free_mib"]=free
        result["gpu1_training_peak_expected_mib"]=peak
        result["gpu1_residual_after_expected_mib"]=free-peak
        if free<peak+GPU1_MIN_UNUSED_MIB:
            reasons.append("HOLD_GPU1_CUDA_OOM_EXPECTED")
    if live.get("gpu1_trainer_active") is not False or live.get("gpu1_teacher_active") is not False:
        reasons.append("HOLD_GPU1_EXISTING_WORK")
    if live.get("onehost_gpu1_lease") is not True:
        reasons.append("HOLD_GPU1_ONEHOST_LEASE")
    if live.get("trainable_student_format")!="HF_BASE_SAFETENSORS":
        reasons.append("HOLD_NOX_TRAINABLE_BASE_REQUIRED")
    if live.get("full_weight_training") is not True or live.get("uses_lora") is not False:
        reasons.append("HOLD_NO_ADAPTER_DIRECT_BASE_ONLY")
    if live.get("precision")!="fp16" or live.get("sm70_cuda_abi_verified") is not True:
        reasons.append("HOLD_VOLTA_FP16_ABI")
    if live.get("checkpoint_owner_key_restore_verified") is not True:
        reasons.append("HOLD_CHECKPOINT_OWNER_RESTORE")
    if live.get("train_holdout_license_privacy_verified") is not True:
        reasons.append("HOLD_TRAIN_HOLDOUT_RIGHTS")
    disk=live.get("disk_free_bytes")
    write=live.get("estimated_full_checkpoint_temp_bytes")
    if (type(disk) is not int or type(write) is not int or write<=0
            or live.get("checkpoint_write_budget_verified") is not True
            or disk-write<DISK_FLOOR_BYTES):
        reasons.append("HOLD_CHECKPOINT_DISK_BUDGET")
    if not reasons:
        result["gpu1_base_weight_training"]="READY_FOR_EXISTING_ONEHOST_ONE_JOB"
        result["cpu_data_preparation"]="READY_FOR_EXISTING_ONEHOST_CPU_QUEUE"
        result["recommended_gpu1_compute_target_pct"]=TARGET_PERCENT
        result["gpu1_vram_target_pct"]=None
        result["next"]="NATIVE_ONEHOST_SIGNED_OPTIMIZER_STEP_AND_CHECKPOINT_RECEIPT"
    else:
        result["gpu1_base_weight_training"]="HOLD_PROTECTED"
    result["reasons"]=list(dict.fromkeys(reasons))
    return result
