"""NOX V87: actual resource gate for one FP16 base-weight trainer on Volta.

Never infer usable training VRAM from total GPUs (2 x 32GiB cannot silently
be combined). Main NOX current.gguf on GPU0 is untouchable. OneHost owns lease,
STOP, optimizer boundaries and S03 receipts. This module cannot launch work.
"""
from __future__ import annotations

from collections.abc import Mapping
import re

MIB=1024*1024
VRAM_HEADROOM_MIB=3072
MODEL_FORMATS=frozenset(("HF_SAFETENSORS","HF_PYTORCH"))
REQUIRED_FIELDS=("gpu1_model_resident_mib","gpu1_trainable_grad_mib",
    "gpu1_optimizer_state_mib","gpu1_activation_peak_mib",
    "gpu1_kernel_scratch_mib")
_SHA=re.compile(r"^[0-9a-f]{64}$")


def gpu1_peak_admission(snapshot: Mapping) -> dict:
    """Return one bounded native admission vote. A READY is NOT GPU execution.

    Memory estimates MUST be measured or conservatively upper-bounded by a
    validated SM70 profile, and tied to exact model/optimizer/dataset SHA.
    Ordinary Q4 GGUF is inference-only. BF16, FA2 and CUDA 13 kernels HOLD.
    """
    receipt={"schema":"NOX_V87_GPU1_OOM_ADMISSION_V1","performed":False,
             "gpu_index":1,"gpu_count_required":2,
             "main_chat_gpu_index":0,"main_model_changed":False,
             "max_gpu1_training_jobs":1,"new_scheduler":False,
             "model_loaded":False,"optimizer_steps_executed":0,
             "allow_adapter":False,"precision":"fp16",
             "target_compute_pct_when_admitted":85,"reasons":[]}
    if not isinstance(snapshot,Mapping):
        return {**receipt,"state":"HOLD_INVALID_SNAPSHOT","reasons":["NATIVE_TELEMETRY_REQUIRED"]}
    errors=[]
    if snapshot.get("instance_id")!="60509551":
        errors.append("HOLD_WRONG_INSTANCE")
    if snapshot.get("native_verified") is not True:
        errors.append("HOLD_NATIVE_MEASUREMENT_REQUIRED")
    if snapshot.get("stop_active") is not False:
        errors.append("HOLD_STOP")
    if snapshot.get("main_gpu0_student_healthy") is not True:
        errors.append("HOLD_MAIN_CHAT_HEALTH")
    if snapshot.get("chat_state") in ("pending","generating") or snapshot.get("chat_recent") is True:
        errors.append("HOLD_CHAT_P0_PREEMPTS_GPU1")
    if snapshot.get("onehost_gpu1_lease") is not True:
        errors.append("HOLD_ONEHOST_GPU1_LEASE")
    if snapshot.get("gpu1_teacher_in_flight") is not False:
        errors.append("HOLD_TEACHER_ACTIVE_OR_UNKNOWN")
    if snapshot.get("gpu1_optimizer_in_flight") is not False:
        errors.append("HOLD_OPTIMIZER_ACTIVE_OR_UNKNOWN")
    if snapshot.get("student_format") not in MODEL_FORMATS:
        errors.append("HOLD_TRAINABLE_BASE_NOT_HF")
    if snapshot.get("training_mode")!="BASE_WEIGHTS":
        errors.append("HOLD_BASE_WEIGHT_ONLY_NOT_ADAPTER")
    if snapshot.get("torch_cuda_major")!=12 or snapshot.get("gpu1_compute_capability") not in ("7.0",70):
        errors.append("HOLD_VOLTA_SM70_CUDA12")
    if snapshot.get("precision")!="fp16" or snapshot.get("uses_bf16") is not False or snapshot.get("uses_flashattention2") is not False:
        errors.append("HOLD_VOLTA_FP16_KERNELS")
    if snapshot.get("gpu1_name") not in ("Tesla V100-SXM2-32GB","Tesla V100-PCIE-32GB","Tesla V100","V100"):
        errors.append("HOLD_GPU1_IDENTITY")
    if snapshot.get("memory_estimate_verified") is not True:
        errors.append("HOLD_PEAK_ESTIMATE_UNVERIFIED")
    if snapshot.get("microbatch")!=1:
        errors.append("HOLD_MICROBATCH_MUST_BE_ONE")
    if snapshot.get("gradient_checkpointing") is not True:
        errors.append("HOLD_GRADIENT_CHECKPOINTING")
    for sha in ("trainable_base_sha256","tokenizer_sha256","optimizer_profile_sha256"):
        if not isinstance(snapshot.get(sha),str) or not _SHA.fullmatch(snapshot[sha]):
            errors.append("HOLD_SHA_"+sha.upper())
    free=snapshot.get("gpu1_free_mib")
    if type(free) is not int or free<0:
        errors.append("HOLD_GPU1_FREE_VRAM_UNKNOWN")
    components={}
    for name in REQUIRED_FIELDS:
        val=snapshot.get(name)
        if type(val) is not int or val<0:
            errors.append("HOLD_ESTIMATE_"+name.upper())
        else:
            components[name]=val
    if len(components)==len(REQUIRED_FIELDS) and type(free) is int and free>=0:
        # Every component is an upper bound, never a lower bound.
        peak=sum(components.values())
        receipt["conservative_peak_mib"]=peak
        receipt["headroom_after_peak_mib"]=free-peak
        receipt["required_free_mib"]=peak+VRAM_HEADROOM_MIB
        receipt["measured_free_mib"]=free
        if free<peak+VRAM_HEADROOM_MIB:
            errors.append("HOLD_CUDA_OOM_EXPECTED")
        # NVIDIA V100 32GB cannot train 35B FP16 fully resident on GPU1.
        if components["gpu1_model_resident_mib"]>free:
            errors.append("HOLD_MODEL_RESIDENCE_EXCEEDS_GPU1")
    if errors:
        return {**receipt,"state":"HOLD","reasons":sorted(set(errors))}
    return {**receipt,"state":"READY_FOR_OWNER_AND_CHECKPOINT_GATES",
            "reasons":[],"next":"NATIVE_ONEHOST_V47_FULL_CHECKPOINT_RESTORE_HOLDOUT"}
