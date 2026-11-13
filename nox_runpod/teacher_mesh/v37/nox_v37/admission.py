"""NOX V37 2×V100 resource admission and safe optimizer-step boundary policy.

Compute occupancy target (85-95%) is a throughput target, not a memory limit.
VRAM is per-GPU. Never allocate additional jobs against summed GPU memory.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Budget:
    reserve_vram_mib:int=3072
    gpu_peak_soft_mib:int=29000
    disk_reserve_bytes:int=20_000_000_000
    ram_reserve_mib:int=12_288
    gpu_temp_max_c:int=80
    target_compute_low:int=85
    target_compute_high:int=95


def admission(probe, *, gpu_idx:int, new_job_peak_mib:int, checkpoint_bytes:int,
              external_checkpoint_verified:bool, allow_unknown_cuda:bool=False, budget=Budget()):
    reasons=[]
    gpus=probe.get('gpus') or []
    if len(gpus)!=2 or sorted(g.get('index') for g in gpus)!=[0,1]:
        return {'state':'HOLD','reason':['TWO_GPU_TELEMETRY_REQUIRED'],'launch':False}
    if gpu_idx not in (0,1):return {'state':'HOLD','reason':['BAD_GPU_INDEX'],'launch':False}
    if not isinstance(new_job_peak_mib,int) or new_job_peak_mib<=0:reasons.append('PEAK_VRAM_ESTIMATE_REQUIRED')
    target=gpus[gpu_idx]
    if 'V100' not in target.get('name',''):reasons.append('NOT_VOLTA_V100')
    if target.get('vram_total_mib',0)<30000:reasons.append('EXPECTED_32GB_CARD_NOT_FOUND')
    if target.get('temp_core_c',999)>=budget.gpu_temp_max_c:reasons.append('TEMPERATURE_HOLD')
    if target.get('vram_free_mib',0)<new_job_peak_mib+budget.reserve_vram_mib:reasons.append('VRAM_HEADROOM_TOO_LOW')
    if target.get('vram_used_mib',999999)+new_job_peak_mib>budget.gpu_peak_soft_mib:
        reasons.append('VRAM_SOFT_LIMIT')
    ram=probe.get('ram') or {}
    if ram.get('available_mib',0)<budget.ram_reserve_mib:reasons.append('RAM_RESERVE_LOW')
    disk=probe.get('disk') or {}
    if disk.get('free_bytes',0)<max(budget.disk_reserve_bytes,checkpoint_bytes*2+2_000_000_000):
        reasons.append('DISK_CHECKPOINT_SPACE')
    if not external_checkpoint_verified:reasons.append('NO_DURABLE_BACKUP_RECEIPT')
    if not allow_unknown_cuda:
        abi=probe.get('runtime_abi') or {}
        if abi.get('capabilities')!=[[7,0],[7,0]] or not str(abi.get('torch_cuda','')).startswith('12.'):
            reasons.append('CUDA_TORCH_SM70_NOT_PROVEN')
        if abi.get('bf16') is not False:reasons.append('VOLTA_FP16_ONLY')
    return {'state':'READY_TO_REQUEST_NATIVE_APPROVAL' if not reasons else 'HOLD',
            'reason':reasons,'launch':False,'gpu_index':gpu_idx,
            'compute_target_pct':[budget.target_compute_low,budget.target_compute_high]}


def tune_next_microbatch(*,microbatch:int,accumulation:int,target_effective:int,
                         peak_vram_mib:int,hard_cap_mib:int,oom:bool=False):
    """Suggest settings for NEXT checkpoint-safe segment, never mutate live process.
    Does not guarantee effective batch; effective count returned for caller evaluation.
    """
    if min(microbatch,accumulation,target_effective,hard_cap_mib)<1:raise ValueError('NONPOSITIVE_TUNER_INPUT')
    if oom or peak_vram_mib>=hard_cap_mib:
        new_micro=max(1,microbatch//2)
    elif peak_vram_mib<hard_cap_mib*0.72 and microbatch<8:
        new_micro=microbatch+1
    else:new_micro=microbatch
    new_acc=max(1,(target_effective+new_micro-1)//new_micro)
    return {'microbatch_next':new_micro,'gradient_accumulation_next':new_acc,
            'effective_microbatch_next':new_micro*new_acc,'state':'PROPOSAL_AFTER_CHECKPOINT_ONLY'}
