"""NOX V135: no-adapter full-base 8B+ ZeRO-3 CPU-offload plan for existing OneHost.

Source-only until the owner returns a signed LIVE OneHost resource/restore receipt.
Does NOT create a new VM/scheduler/HTTP backend or alter GGUF/S03.
GPU0 stays for interactive P02; V100 GPU1 (SM70) is the training candidate.
Actual full weights steps count only after optimizer+checkpoint+holdout proof.
"""
from __future__ import annotations
from collections.abc import Mapping
import hashlib,json,math,re
from typing import Any

GIB=1024**3
MIB=1024**2
_SHA=re.compile(r"^[0-9a-f]{64}$")
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
SCHEMA='NOX_V135_FULL_BASE_Z3_CPU_OFFLOAD_ADMISSION_V1'
DOCS={
    'deepspeed_zero3':'https://deepspeed.readthedocs.io/en/latest/zero3.html',
    'hf_deepspeed':'https://huggingface.co/docs/transformers/main/deepspeed',
    'gkd':'https://huggingface.co/docs/trl/main/gkd_trainer',
}
MAX_TRAIN_STEPS=50000
MAX_TOKENS=1024
RAM_RESERVE=24*GIB
DISK_RESERVE=10_000_000_000
CHAT_GPU0_MIB=3072
GPU1_RESERVE_MIB=4096

def sha256_manifest(obj:Mapping)->str:
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()

def _valid_sha(value)->bool:return isinstance(value,str) and _SHA.fullmatch(value) is not None

def zero3_cpu_config(*,micro_batch=1,grad_accum=16,learning_rate=5e-6)->dict:
    """Trainer passes exact DeepSpeed config; no LoRA/QLoRA/PEFT anywhere."""
    if (type(micro_batch) is not int or micro_batch!=1
       or type(grad_accum) is not int or not 1<=grad_accum<=128
       or type(learning_rate) is not float or not 0<learning_rate<=2e-5):
        raise ValueError('HOLD_V135_SAFE_OPTIMIZER_CONFIG')
    return {
        'train_batch_size':micro_batch*grad_accum,
        'train_micro_batch_size_per_gpu':micro_batch,
        'gradient_accumulation_steps':grad_accum,
        'gradient_clipping':1.0,
        'steps_per_print':10,
        'wall_clock_breakdown':False,
        'fp16':{'enabled':True,'loss_scale':0,
                'initial_scale_power':12,'loss_scale_window':1000,
                'hysteresis':2,'min_loss_scale':1},
        'bf16':{'enabled':False},
        'zero_optimization':{
            'stage':3,
            'offload_optimizer':{'device':'cpu','pin_memory':False},
            'offload_param':{'device':'cpu','pin_memory':False},
            'overlap_comm':False,
            'contiguous_gradients':True,
            'reduce_scatter':True,
            'reduce_bucket_size':10_000_000,
            'stage3_prefetch_bucket_size':10_000_000,
            'stage3_param_persistence_threshold':10_000,
            'stage3_max_live_parameters':40_000_000,
            'stage3_max_reuse_distance':40_000_000,
            'stage3_gather_16bit_weights_on_model_save':False
        },
        'optimizer':{
            'type':'AdamW',
            'params':{'lr':learning_rate,'betas':[0.9,0.95],
                      'eps':1e-8,'weight_decay':0.01}
        }
    }

def required_cpu_bytes(params:int)->int:
    """FP16 weights + FP32 master + Adam m/v + FP32 gradients + overhead.

    Intentionally conservative 20 B/parameter plus 24 GiB chat/system margin.
    This is an admission bound, NOT an observed RAM usage claim.
    """
    if type(params) is not int or params<=0 or params>150_000_000_000:
        raise ValueError('HOLD_PARAMETER_COUNT')
    return params*20+RAM_RESERVE

def fullbase_admission(native:Mapping|None,*,teacher_lanes:tuple[str,...]=())->dict:
    """Pure policy. No reading private training examples and no live actions."""
    out={
        'schema':SCHEMA,'state':'HOLD','native_training_started':False,
        'optimizer_steps_verified':0,'weights_changed_verified':False,
        'checkpoint_written':False,'new_instance_created':False,
        'uses_adapters':False,'full_parameter_training_requested':True,
        'one_student_only':True,'gpu0_owner_chat_reserved':True,
        'gpu1_training_exclusive':True,'gpu1_compute_target_pct_after_admission':85,
        'gpu1_vram_target_pct':None,'dependencies':DOCS,'reasons':[]
    }
    if not isinstance(native,Mapping):
        out['reasons']=['HOLD_SIGNED_NATIVE_INVENTORY'];return out
    reasons=out['reasons']
    boolean_conditions=[
        ('native_signed_owner_receipt','HOLD_NATIVE_SIGNATURE'),
        ('instance_id_verified','HOLD_VAST_OR_INSTANCE_ACCESS'),
        ('model_shards_complete_sha_verified','HOLD_HF_BASE_SHARDS'),
        ('onehost_original_main_chat_healthy','HOLD_P02_CHAT'),
        ('s03_integrity_verified','HOLD_S03'),
        ('owner_approved_training','HOLD_OWNER_APPROVAL'),
        ('no_shared_gpu_scheduler','HOLD_COMPETING_SCHEDULER'),
        ('live_gpu1_lease','HOLD_GPU1_EXCLUSIVE_LEASE'),
        ('teacher_dataset_rights_verified','HOLD_TEACHER_DATA_LICENSE'),
        ('teacher_dataset_privacy_verified','HOLD_PRIVATE_TRAINING_DATA'),
        ('disjoint_holdout_verified','HOLD_TRAIN_HOLDOUT_LEAKAGE'),
        ('offsite_owner_checkpoint_restore_verified','HOLD_OFFSITE_RESTORE'),
        ('offsite_s03_restore_verified','HOLD_S03_RESTORE'),
        ('external_checkpoint_storage_prepared','HOLD_EXTERNAL_CKPT_STORAGE'),
        ('fp16_sm70_deepspeed_abi_verified','HOLD_CUDA_SM70_DEEPSPEED'),
        ('existing_student_identity_sha_verified','HOLD_STUDENT_SHA'),
        ('zero3_checkpoint_reload_tested','HOLD_ZERO3_RESUME'),
        ('optimizer_is_full_base_no_peft','HOLD_ADAPTER_OR_PARTIAL_WEIGHTS'),
    ]
    for key,reason in boolean_conditions:
        if native.get(key) is not True:reasons.append(reason)
    if native.get('native_stop_active') is not False:
        reasons.append('HOLD_STOP_ACTIVE_OR_UNKNOWN')
    if native.get('existing_chat_priority')!='P0':
        reasons.append('HOLD_P0_CHAT_PRIORITY')
    if native.get('student_checkpoint_format')!='HF_SAFETENSORS':
        reasons.append('HOLD_TRAINABLE_HF_NOT_GGUF')
    if native.get('gpu0_role')!='CHAT_ONLY' or native.get('gpu1_role')!='TRAINING_EXCLUSIVE':
        reasons.append('HOLD_GPU_ROLE_SPLIT')
    if native.get('gpu1_name') not in ('Tesla V100-SXM2-32GB','Tesla V100-PCIE-32GB',
                                      'NVIDIA Tesla V100','Tesla V100'):
        reasons.append('HOLD_GPU1_V100_IDENTITY')
    if native.get('precision')!='fp16':
        reasons.append('HOLD_V100_FP16_ONLY')
    for name in ('cpu_cgroup_max_bytes','cpu_cgroup_current_bytes','cpu_mem_available_bytes',
                 'gpu0_free_mib','gpu1_free_mib','gpu1_measured_peak_mib',
                 'checkpoint_required_new_bytes','disk_free_bytes','student_param_count',
                 'student_shard_bytes','train_rows','holdout_rows'):
        value=native.get(name)
        if type(value) is not int or value<0:
            reasons.append('HOLD_MEASURED_'+name.upper())
    if all(type(native.get(n)) is int for n in
           ('cpu_cgroup_max_bytes','cpu_cgroup_current_bytes','cpu_mem_available_bytes','student_param_count')):
        limit,current,available,params=(native[k] for k in
           ('cpu_cgroup_max_bytes','cpu_cgroup_current_bytes','cpu_mem_available_bytes','student_param_count'))
        try:required=required_cpu_bytes(params)
        except ValueError:
            reasons.append('HOLD_PARAM_COUNT');required=None
        if required is not None:
            out.update({'student_param_count':params,'estimated_cpu_total_required_bytes':required,
                        'cgroup_limit_bytes':limit,'cgroup_used_bytes':current,
                        'cpu_available_bytes_observed':available})
            if limit<=0 or current>limit or limit-current<required or available<required:
                reasons.append('HOLD_ZERO3_CPU_OFFLOAD_MEMORY')
    gpu0=native.get('gpu0_free_mib')
    gpu1=native.get('gpu1_free_mib')
    peak=native.get('gpu1_measured_peak_mib')
    if type(gpu0) is int and gpu0<CHAT_GPU0_MIB:reasons.append('HOLD_CHAT_GPU0_HEADROOM')
    if type(gpu1) is int and type(peak) is int:
        out.update({'observed_gpu1_free_mib':gpu1,'expected_gpu1_measured_peak_mib':peak})
        if peak<=0 or gpu1-peak<GPU1_RESERVE_MIB:
            reasons.append('HOLD_GPU1_PEAK_OR_MARGIN')
    disk,checkpoint=native.get('disk_free_bytes'),native.get('checkpoint_required_new_bytes')
    if type(disk) is int and type(checkpoint) is int:
        out.update({'disk_free_bytes':disk,'checkpoint_required_new_bytes':checkpoint})
        if checkpoint<=0 or disk-checkpoint<DISK_RESERVE:
            reasons.append('HOLD_LOCAL_CHECKPOINT_DISK_BUDGET')
    if type(native.get('student_shard_bytes')) is int and native.get('student_shard_bytes')==0:
        reasons.append('HOLD_HF_WEIGHT_SHARDS_EMPTY')
    if type(native.get('train_rows')) is int and native['train_rows']<300:
        reasons.append('HOLD_TRAIN_ROWS')
    if type(native.get('holdout_rows')) is int and native['holdout_rows']<30:
        reasons.append('HOLD_HOLDOUT_ROWS')
    for name in ('hf_weight_index_sha256','student_base_sha256',
                 'train_dataset_sha256','holdout_dataset_sha256',
                 'offsite_checkpoint_manifest_sha256'):
        if not _valid_sha(native.get(name)):
            reasons.append('HOLD_SHA_'+name.upper())
    # A verified flag cannot override byte-identical train and holdout evidence.
    if (_valid_sha(native.get('train_dataset_sha256'))
        and native['train_dataset_sha256']==native.get('holdout_dataset_sha256')):
        reasons.append('HOLD_TRAIN_HOLDOUT_LEAKAGE')
    # Enforce teacher scheduling policy without making a competing scheduler.
    allowed=('qwen-language','deepseek-reasoning','coder','owner-verified-knowledge')
    if len(set(teacher_lanes))!=len(teacher_lanes) or any(x not in allowed for x in teacher_lanes):
        reasons.append('HOLD_TEACHER_LANE_SCHEMA')
    if native.get('teacher_slots_not_colocated_with_gpu1') is not True:
        reasons.append('HOLD_TEACHERS_OCCUPY_GPU1')
    if native.get('gpu1_automatic_85pct_overcommit_disabled') is not True:
        reasons.append('HOLD_OVERCOMMIT_UNSAFE')
    out['reasons']=sorted(set(reasons))
    if not out['reasons']:
        out['state']='READY_FOR_SIGNED_ONEHOST_TRAINING_START'
        out['source_plan_only']=True
        out['deepspeed']=zero3_cpu_config()
    return out

def native_checkpoint_acceptance(receipt:Mapping|None)->dict:
    """Independent evidence required before saying NOX own weights improved."""
    if not isinstance(receipt,Mapping):
        return {'state':'HOLD_CHECKPOINT_RECEIPT','weights_changed_verified':False}
    required=('native_signed_owner_receipt','full_base_parameters_updated',
              'optimizer_state_present','s03_untouched','main_chat_healthy',
              'student_hf_checkpoint_sha_verified','checkpoint_external_restored',
              'model_reloaded_heldout_verified','no_adapters')
    problems=[x for x in required if receipt.get(x) is not True]
    steps=receipt.get('optimizer_steps_actual')
    if type(steps) is not int or steps<1:problems.append('optimizer_steps_actual')
    for sha in ('before_base_weight_sha256','after_base_weight_sha256',
                'restored_base_weight_sha256','checkpoint_manifest_sha256'):
        if not _valid_sha(receipt.get(sha)):problems.append(sha)
    if (receipt.get('after_base_weight_sha256')==
        receipt.get('before_base_weight_sha256')):
        problems.append('UNCHANGED_BASE_WEIGHTS')
    if receipt.get('after_base_weight_sha256')!=receipt.get('restored_base_weight_sha256'):
        problems.append('CHECKPOINT_RESTORE_MISMATCH')
    return {'state':'ACCEPTED_REAL_BASE_WEIGHT_TRAINING' if not problems else 'HOLD',
            'reasons':problems,'optimizer_steps_verified':steps if not problems else 0,
            'weights_changed_verified':not problems,
            'original_model_promoted':False}
