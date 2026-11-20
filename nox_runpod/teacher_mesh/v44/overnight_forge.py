"""NOX V44: host-owned FP16 training segment with real parameter updates.

This module is an implementation for the EXISTING NOX OneHost/FORGE worker,
not a daemon, CLI, remote shell, scheduler, teacher, or chat server.
Production is fail-closed without verified GPU1/SM70/CUDA12/backup/STOP.
There is no LoRA, PEFT, automatic model promotion, or fake training receipt.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping, Iterable
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any

SHA = re.compile(r"^[a-f0-9]{64}$")

@dataclass(frozen=True)
class HostPorts:
    """Trusted native OneHost callbacks (do not take values from model text)."""
    stop_active: Callable[[], bool]
    authorize: Callable[[Mapping], bool]
    inspect: Callable[[], Mapping]
    holdout: Callable[[Any], Mapping]
    checkpoint: Callable[[Any, Any, Mapping], Mapping]
    verify_checkpoint: Callable[[Mapping], bool]
    verify_restore: Callable[[Mapping], bool]
    genesis_receipt: Callable[[Mapping], bool]
    rollback: Callable[[], bool]


def _digest_model(model) -> str:
    """Hash all actual tensor bytes, not GGUF name, timestamp, or JSON only."""
    import torch
    h = sha256()
    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode('utf-8') + b'\0')
        if not isinstance(tensor, torch.Tensor):
            raise ValueError('NON_TENSOR_STATE')
        a = tensor.detach().to(device='cpu').contiguous()
        h.update(str(a.dtype).encode() + b':' + str(tuple(a.shape)).encode() + b'\0')
        h.update(a.view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


def production_admission(state: Mapping, *, requested_job_sha: str, params: int) -> dict:
    """Strict gate for new full-parameter training; never guesses GPU availability."""
    reasons=[]
    if not SHA.fullmatch(requested_job_sha or ''): reasons.append('SIGNED_JOB_DIGEST_MISSING')
    if state.get('instance_id') != '60509551': reasons.append('WRONG_VAST_INSTANCE')
    gpus = state.get('gpus', [])
    if not isinstance(gpus, list) or len(gpus) != 2:
        reasons.append('TWO_GPU_READBACK_MISSING')
    else:
        for g in gpus:
            if not isinstance(g, dict) or 'V100' not in str(g.get('name', '')) or g.get('sm') != 70:
                reasons.append('VOLTA_SM70_NOT_VERIFIED')
        gpu1=next((g for g in gpus if isinstance(g,dict) and g.get('index')==1),{})
        if gpu1.get('vram_free_mib', 0) < 4096: reasons.append('GPU1_LOW_FREE_VRAM')
        if gpu1.get('temp_c', 100) >= 80: reasons.append('GPU1_TEMPERATURE_HOLD')
        if gpu1.get('trainer_running') is not False: reasons.append('GPU1_ALREADY_OWNED_OR_UNKNOWN')
        gpu0=next((g for g in gpus if isinstance(g,dict) and g.get('index')==0),{})
        if gpu0.get('protected_chat') is not True: reasons.append('GPU0_CHAT_NOT_PROTECTED')
    if not str(state.get('torch_cuda', '')).startswith('12.'):
        reasons.append('CUDA12_SM70_NOT_VERIFIED')
    if state.get('bf16_supported') is not False:reasons.append('VOLTA_MUST_USE_FP16')
    if not isinstance(params, int) or params<=0:reasons.append('TRAINABLE_PARAMETER_COUNT_MISSING')
    if state.get('full_parameter_optimizer_memory_fit') is not True:
        reasons.append('FULL_PARAMETER_OPTIMIZER_FIT_NOT_VERIFIED')
    if state.get('ram_free_mib', 0) < 12288: reasons.append('RAM_RESERVE')
    disk_free = state.get('disk_free_bytes', 0)
    predicted = state.get('checkpoint_bytes_required', 0)
    if not isinstance(predicted,int) or predicted<=0 or disk_free < max(20_000_000_000, predicted*2 + 2_000_000_000):
        reasons.append('DISK_FOR_TWO_CHECKPOINTS_AND_RESERVE')
    for k in ('base_weights_sha256','train_dataset_sha256','holdout_sha256',
              'checkpoint_sha256','optimizer_state_sha256'):
        if not SHA.fullmatch(str(state.get(k, ''))):reasons.append('MISSING_'+k.upper())
    for k in ('offsite_checkpoint_restored','s03_restore_verified','stop_available',
              'owner_grant_verified','source_licenses_verified','holdout_disjoint'):
        if state.get(k) is not True:reasons.append('MISSING_'+k.upper())
    return {'state':'READY_FOR_ONEHOST' if not reasons else 'HOLD',
            'reasons':reasons, 'admitted':not reasons, 'executed':False,
            'gpu1_compute_target_pct':[85,95],'gpu0_chat_priority':True}


def _safe_rollback(host: HostPorts, state: str) -> dict:
    try:ok=host.rollback() is True
    except Exception:ok=False
    return {'state':state if ok else 'URGENT_ROLLBACK_FAILED',
            'rollback_verified':ok,'weights_active_changed':False if ok else 'UNKNOWN'}


def train_segment(*, model, optimizer, batches: Iterable[Mapping], host: HostPorts,
                  job: Mapping, max_optimizer_steps: int = 20,
                  gradient_accumulation: int = 4,
                  cpu_test_mode: bool = False) -> dict:
    """Actually backpropagate, step optimizer, checkpoint and verify candidate.

    Production: GPU1 only, FP16, full parameters, signed owner OneHost job.
    Test: explicit CPU-test flag bypasses only hardware admission; NEVER a live receipt.
    Trusted host supplies pre-tokenized legal training batches and independent
    disjoint holdout; candidate is never auto-activated in running chatbot.
    """
    import torch
    if not isinstance(job, Mapping) or not isinstance(host, HostPorts):
        return {'state':'HOLD_NATIVE_PORTS_OR_JOB','optimizer_steps':0}
    if type(max_optimizer_steps) is not int or not 1<=max_optimizer_steps<=10000:
        return {'state':'HOLD_STEPS','optimizer_steps':0}
    if type(gradient_accumulation) is not int or not 1<=gradient_accumulation<=512:
        return {'state':'HOLD_ACCUMULATION','optimizer_steps':0}
    required=('stop_active','authorize','inspect','holdout','checkpoint',
              'verify_checkpoint','verify_restore','genesis_receipt','rollback')
    if any(not callable(getattr(host,n,None)) for n in required):
        return {'state':'HOLD_NATIVE_CALLBACKS','optimizer_steps':0}
    if host.stop_active() is not False or host.authorize(job) is not True:
        return {'state':'HOLD_STOP_OR_OWNER','optimizer_steps':0}
    state=host.inspect()
    if not isinstance(state,Mapping):return {'state':'HOLD_INVALID_LIVE_STATE','optimizer_steps':0}
    student_params=list(model.parameters())
    if not student_params or any(not p.requires_grad for p in student_params):
        return {'state':'HOLD_NOT_FULL_PARAMETER_TRAINING','optimizer_steps':0}
    if any(any(w in n.lower() for w in ('lora_', 'ia3_', 'adapter')) for n,_ in model.named_parameters()):
        return {'state':'HOLD_ADAPTER_PRESENT','optimizer_steps':0}
    opt_ids={id(p) for g in optimizer.param_groups for p in g['params']}
    if opt_ids != {id(p) for p in student_params}:
        return {'state':'HOLD_OPTIMIZER_NOT_ALL_PARAMETERS','optimizer_steps':0}
    requested_sha=job.get('request_sha256','')
    if not cpu_test_mode:
        gate=production_admission(state,requested_job_sha=requested_sha,
                                  params=sum(p.numel() for p in student_params))
        if not gate['admitted']:return {'state':'HOLD_ADMISSION','gate':gate,'optimizer_steps':0}
        if (not torch.cuda.is_available() or torch.cuda.device_count()<2
                or torch.cuda.get_device_capability(1)!=(7,0)
                or not str(torch.version.cuda).startswith('12.')):
            return {'state':'HOLD_RUNTIME_NOT_VOLTA_CUDA12','optimizer_steps':0}
        if any(p.device.type!='cuda' or p.device.index!=1 for p in student_params):
            return {'state':'HOLD_MODEL_NOT_EXCLUSIVELY_GPU1','optimizer_steps':0}
    device=student_params[0].device
    if cpu_test_mode and device.type!='cpu':
        return {'state':'HOLD_TEST_MUST_RUN_ON_CPU','optimizer_steps':0}
    pre_sha=_digest_model(model)
    if not cpu_test_mode and pre_sha != state.get('base_weights_sha256'):
        return {'state':'HOLD_BASE_WEIGHTS_SHA_MISMATCH','optimizer_steps':0}
    before=host.holdout(model)
    if (not isinstance(before,Mapping) or before.get('verified') is not True
            or not isinstance(before.get('loss'),(int,float)) or not math.isfinite(before['loss'])):
        return {'state':'HOLD_UNVERIFIED_BASE_HOLDOUT','optimizer_steps':0}
    scaler = torch.amp.GradScaler('cuda', enabled=(device.type=='cuda'))
    optimizer.zero_grad(set_to_none=True)
    performed=0; micro=0; skipped=0
    model.train()
    try:
        for batch in batches:
            if performed>=max_optimizer_steps:break
            if host.stop_active() is not False:
                return _safe_rollback(host,'HOLD_STOP_REQUESTED') | {'optimizer_steps':performed}
            if not isinstance(batch,Mapping) or not batch or 'labels' not in batch:
                return _safe_rollback(host,'HOLD_UNTRUSTED_BATCH') | {'optimizer_steps':performed}
            tensors={k:v.to(device,non_blocking=True) for k,v in batch.items()}
            with torch.autocast(device_type=device.type,dtype=torch.float16 if device.type=='cuda' else torch.bfloat16,
                                enabled=device.type=='cuda'):
                loss=model(**tensors).loss
            if not bool(torch.isfinite(loss).item()):
                return _safe_rollback(host,'HOLD_NONFINITE_LOSS') | {'optimizer_steps':performed}
            scaler.scale(loss/gradient_accumulation).backward()
            micro+=1
            if micro % gradient_accumulation:continue
            scaler.unscale_(optimizer)
            norm=torch.nn.utils.clip_grad_norm_(student_params,1.0,error_if_nonfinite=False)
            if not bool(torch.isfinite(norm).item()):
                return _safe_rollback(host,'HOLD_NONFINITE_GRADIENT') | {'optimizer_steps':performed}
            scale_before=scaler.get_scale()
            scaler.step(optimizer);scaler.update()
            scale_after=scaler.get_scale()
            optimizer.zero_grad(set_to_none=True)
            if scale_after < scale_before:
                skipped+=1
            else:
                performed+=1
        if performed<1:
            return _safe_rollback(host,'HOLD_NO_REAL_OPTIMIZER_STEPS') | {'optimizer_steps':0}
        post_sha=_digest_model(model)
        if pre_sha==post_sha:
            return _safe_rollback(host,'HOLD_WEIGHT_HASH_UNCHANGED') | {'optimizer_steps':performed}
        after=host.holdout(model)
        if not isinstance(after,Mapping) or after.get('verified') is not True or not isinstance(after.get('loss'),(int,float)) or not math.isfinite(after['loss']):
            return _safe_rollback(host,'HOLD_POST_HOLDOUT') | {'optimizer_steps':performed}
        if not (after['loss'] < before['loss'] and after.get('regression_pass') is True):
            return _safe_rollback(host,'HOLD_NO_INDEPENDENT_IMPROVEMENT') | {'optimizer_steps':performed}
        receipt=host.checkpoint(model,optimizer,{'request_sha256':requested_sha,'optimizer_steps':performed,
                          'base_weights_sha256':pre_sha,'candidate_weights_sha256':post_sha,
                          'holdout_before':before['loss'],'holdout_after':after['loss']})
        if not isinstance(receipt,Mapping) or not SHA.fullmatch(str(receipt.get('sha256',''))):
            return _safe_rollback(host,'HOLD_CHECKPOINT_MISSING') | {'optimizer_steps':performed}
        if host.verify_checkpoint(receipt) is not True or host.verify_restore(receipt) is not True:
            return _safe_rollback(host,'HOLD_CHECKPOINT_RELOAD_FAIL') | {'optimizer_steps':performed}
        evidence={'schema':'NOX_V44_VERIFIED_CANDIDATE','request_sha256':requested_sha,
                  'base_weights_sha256':pre_sha,'candidate_weights_sha256':post_sha,
                  'checkpoint_sha256':receipt['sha256'],'optimizer_steps':performed,
                  'skipped_steps':skipped,'holdout_loss_before':before['loss'],
                  'holdout_loss_after':after['loss'],'cpu_test_mode':cpu_test_mode,
                  'active_model_switched':False}
        if host.genesis_receipt(evidence) is not True:
            return {'state':'HOLD_GENESIS_RECEIPT','optimizer_steps':performed,'candidate_saved':True,
                    'active_model_switched':False}
        return {'state':'CPU_UNIT_TEST_REAL_TENSOR_UPDATE' if cpu_test_mode else 'TRAINED_CANDIDATE_NOT_ACTIVATED',
                **evidence}
    except Exception as exc:
        # Do not expose prompt text or secrets; do not swallow rollback errors.
        return _safe_rollback(host,'HOLD_TRAIN_EXCEPTION') | {'error_type':type(exc).__name__,
                            'optimizer_steps':performed}
