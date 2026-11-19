"""Evidence-bound overnight FORGE planner. Pure: never launches a process.

One student identity, one S03 and existing native OneHost only. Inputs must come
from an authenticated native inventory, never from assistant prose or web pages.
Training proof is actual changed base-model tensors, optimizer receipt, independent
reload and blind holdout. GGUF quantized inference weights are NOT trainable HF weights.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, re
from typing import Mapping

from nox_runpod.teacher_mesh.v71.disk_budget import SAFETY_FLOOR_BYTES, verify_new_write_space
from nox_runpod.teacher_mesh.v87.gpu1_oom_gate import gpu1_peak_admission

_SHA = re.compile(r'^[a-f0-9]{64}$')
ID='60509551'

@dataclass(frozen=True)
class Limits:
    # Small safety floor; actual checkpoint and optimizer/temp estimates are mandatory.
    disk_reserve_bytes: int = 10_000_000_000
    gpu1_headroom_mib: int = 3072
    ram_reserve_mib: int = 12288
    max_cpu_jobs: int = 8
    max_gpu_jobs: int = 1
    target_utilization_pct: int = 85  # goal, never a forced setpoint


def _verified_sha(x):
    return isinstance(x,str) and _SHA.fullmatch(x) is not None


def _hold(reasons, phase='PREFLIGHT'):
    return {'schema':'NOX_V47_NIGHT_ADMISSION','state':'HOLD','phase':phase,
            'reasons':sorted(set(reasons)),'performed':False,'jobs_enqueued':0,
            'optimizer_steps_executed':0,'live_model_changed':False}


def assess(snapshot, limits=Limits()):
    """Return READY_FOR_NATIVE_OWNER_APPROVAL only with an independently verified preimage.
    The policy never starts even when READY: trusted OneHost must approve and read back.
    """
    if not isinstance(snapshot,Mapping):
        return _hold(['NATIVE_SNAPSHOT_REQUIRED'])
    errors=[]
    if snapshot.get('instance_id')!=ID:errors.append('WRONG_VAST_INSTANCE')
    if snapshot.get('native_verified') is not True:errors.append('NATIVE_STATE_NOT_VERIFIED')
    if snapshot.get('stop_active') is not False:errors.append('STOP_OR_UNVERIFIED_STOP')
    if snapshot.get('chat_gpu0_healthy') is not True:errors.append('FAST_CHAT_NOT_HEALTHY')
    if snapshot.get('s03_native_healthy') is not True:errors.append('S03_UNAVAILABLE')
    gpu=snapshot.get('gpus')
    if (not isinstance(gpu,list) or len(gpu)!=2 or
        sorted(x.get('index') for x in gpu if isinstance(x,dict))!=[0,1]):
        errors.append('REQUIRE_TWO_DISTINCT_GPUS')
    else:
        for row in gpu:
            if 'V100' not in str(row.get('name','')) or row.get('compute_capability') not in ('7.0',70):
                errors.append('VOLTA_SM70_IDENTITY_UNVERIFIED')
            if not isinstance(row.get('vram_free_mib'),int):errors.append('GPU_VRAM_UNVERIFIED')
            if row['index']==1 and row.get('vram_free_mib',0)<limits.gpu1_headroom_mib:
                errors.append('GPU1_INSUFFICIENT_VRAM')
            if row['index']==1 and row.get('in_use_for_training') is True:
                errors.append('GPU1_TRAINER_ALREADY_RUNNING')
    if snapshot.get('cuda_major')!=12:errors.append('CUDA_12_REQUIRED_FOR_V100')
    if snapshot.get('torch_cuda_sm70_verified') is not True:
        errors.append('TORCH_GPU_KERNEL_SM70_UNVERIFIED')
    if snapshot.get('precision')!='fp16':errors.append('V100_FP16_REQUIRED')
    if snapshot.get('uses_flashattention2') is True or snapshot.get('uses_bf16') is True:
        errors.append('VOLTA_UNSUPPORTED_KERNEL_OR_PRECISION')
    if snapshot.get('trainer_step0_root_cause_fixed') is not True:
        errors.append('TRAIN_ERROR_STEP0_NOT_FIXED')
    disk_snapshot=dict(snapshot)
    disk_snapshot['min_free_after_bytes']=limits.disk_reserve_bytes
    disk_gate=verify_new_write_space(disk_snapshot)
    if disk_gate['state']!='READY_FOR_OTHER_NATIVE_GATES':
        errors.append('CHECKPOINT_SPACE_AND_RESERVE_NOT_PROVEN')
    ram=snapshot.get('ram_available_mib')
    if type(ram) is not int or ram < limits.ram_reserve_mib:errors.append('RAM_RESERVE_UNVERIFIED')
    if snapshot.get('offsite_optimizer_restore_verified') is not True:
        errors.append('OPTIMIZER_OFFSITE_RESTORE_UNVERIFIED')
    if snapshot.get('s03_offsite_restore_verified') is not True:
        errors.append('S03_OFFSITE_RESTORE_UNVERIFIED')
    if snapshot.get('train_data_license_verified') is not True or snapshot.get('privacy_sanitized') is not True:
        errors.append('LICENSE_OR_PRIVACY_GATE')
    if snapshot.get('independent_holdout_sealed') is not True:
        errors.append('NO_BLIND_EVALUATION_DATA')
    if snapshot.get('native_owner_write_scope_verified') is not True:
        errors.append('NATIVE_OWNER_SCOPE_NOT_VERIFIED')
    for name in ('trainable_student_sha256','checkpoint_sha256','optimizer_sha256','dataset_sha256','holdout_sha256'):
        if not _verified_sha(snapshot.get(name)):
            errors.append('SHA_MISSING_'+name.upper())
    if snapshot.get('student_format') not in ('HF_SAFETENSORS','HF_PYTORCH'):
        errors.append('TRAINABLE_STUDENT_REQUIRED_GGUF_NOT_TRAINABLE')
    if snapshot.get('no_live_optimizer_process') is not True:
        errors.append('MAY_INTERRUPT_EXISTING_OPTIMIZER')
    # Hardware-aware V87 Volta memory gate prevents V83's repeated CUDA OOM
    # before requesting any native OneHost trainer lease. No GPU work here.
    gpu1=next((x for x in (gpu or []) if isinstance(x,Mapping) and x.get('index')==1),{})
    peak=dict(snapshot)
    peak.update({
        'main_gpu0_student_healthy':snapshot.get('chat_gpu0_healthy'),
        'onehost_gpu1_lease':snapshot.get('training_owner_lease'),
        'gpu1_optimizer_in_flight':False if snapshot.get('no_live_optimizer_process') is True else None,
        'gpu1_free_mib':gpu1.get('vram_free_mib'),
        'gpu1_compute_capability':gpu1.get('compute_capability'),
        'gpu1_name':gpu1.get('name'),
        'torch_cuda_major':snapshot.get('cuda_major'),
        'trainable_base_sha256':snapshot.get('trainable_student_sha256'),
    })
    oom_gate=gpu1_peak_admission(peak)
    if oom_gate['state']!='READY_FOR_OWNER_AND_CHECKPOINT_GATES':
        errors.extend(oom_gate['reasons'])
    if errors:return _hold(errors)
    preimage=sha256(json.dumps(dict(snapshot),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'schema':'NOX_V47_NIGHT_ADMISSION','state':'READY_FOR_NATIVE_OWNER_APPROVAL',
            'performed':False,'jobs_enqueued':0,'optimizer_steps_executed':0,
            'preimage_sha256':preimage,'gpu_index':1,'gpu_count':2,
            'gpu1_max_jobs':limits.max_gpu_jobs,'max_cpu_jobs':limits.max_cpu_jobs,
            'priority':'P0_CHAT>P0_S03>P0_BACKUP>P1_TRAIN',
            'precision':'fp16','allow_driver_upgrade':False,'allow_cu13':False,
            'target_gpu_compute_pct':limits.target_utilization_pct,
            'next':'NATIVE_ONEHOST_SIGNED_APPROVAL_AND_TESTED_SMOKE_ONLY',
            'live_model_changed':False}
