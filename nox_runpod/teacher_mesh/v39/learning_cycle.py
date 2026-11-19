"""NOX V39: every verified action becomes S03 experience, not an imaginary weight update.

Tasks are executed by the EXISTING OneHost. S03 is the sole durable memory;
FORGE is the sole trainer. No daemon, database, model switch or second scheduler.
"""
from __future__ import annotations
from collections.abc import Callable,Mapping
from dataclasses import dataclass
import hashlib,json,re
from typing import Any
from .native_control import NativeAdmin,Scope

_SHA=re.compile(r'^[a-f0-9]{64}$')
_SOURCE=('s03://','nox-checkpoint://','https://')

@dataclass(frozen=True)
class LearningHost:
    """Trusted callbacks from current OneHost/S03; cannot be model-authored."""
    s03_append:Callable[[Scope,dict],Mapping]
    s03_verify:Callable[[Mapping,dict],bool]
    independently_evaluate:Callable[[Mapping,Mapping],Mapping]
    source_allowed:Callable[[str,Scope],bool]
    owner_opt_in:Callable[[Scope,str],bool]
    native_queue_enqueue:Callable[[dict],Mapping]|None=None
    native_queue_readback:Callable[[Mapping],Mapping]|None=None
    native_backup_verify:Callable[[Scope],Mapping]|None=None
    forge_admission:Callable[[Mapping],Mapping]|None=None
    native_training_receipt:Callable[[str],Mapping]|None=None


def result_hash(value:Mapping)->str:
    # Minimal source-limited metadata, no raw user messages or keys.
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()


class LearnWhileDoing:
    """Verified receipts -> S03 event -> source-linked skill candidate -> FORGE proposal."""
    def __init__(self,admin:NativeAdmin,host:LearningHost):
        self.admin=admin;self.host=host
        for f in ('s03_append','s03_verify','independently_evaluate','source_allowed','owner_opt_in'):
            if not callable(getattr(host,f,None)):raise TypeError('NATIVE_LEARNING_PORTS_REQUIRED')

    def record_action(self,scope:Scope,action_result:Mapping,*,source_uri:str,
                      event_id:str,learning_label:str):
        scope.validate()
        if not isinstance(action_result,Mapping):return {'state':'HOLD_ACTION_RESULT_INVALID'}
        if action_result.get('state')!='EXECUTED_NATIVE_AND_VERIFIED' or action_result.get('performed') is not True:
            return {'state':'HOLD_NO_VERIFIED_NATIVE_ACTION','s03_written':False}
        if not isinstance(source_uri,str) or not source_uri.startswith(_SOURCE) or len(source_uri)>400:
            return {'state':'HOLD_INVALID_SOURCE','s03_written':False}
        if not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9._:@-]{8,120}',event_id):
            return {'state':'HOLD_EVENT_ID','s03_written':False}
        if not isinstance(learning_label,str) or not 1<=len(learning_label)<=110:
            return {'state':'HOLD_LABEL'}
        try:
            if self.host.source_allowed(source_uri,scope) is not True:
                return {'state':'HOLD_SOURCE_NOT_ALLOWED'}
            observed=self.host.independently_evaluate(action_result['receipt'],action_result['observation'])
            if not isinstance(observed,Mapping) or observed.get('verified') is not True:
                return {'state':'HOLD_ACTION_NOT_INDEPENDENTLY_VERIFIED'}
            score=observed.get('score',0)
            if isinstance(score,bool) or not isinstance(score,(float,int)) or not 0<=score<=1:
                return {'state':'HOLD_INVALID_EVAL'}
            review_ref=observed.get('review_ref')
            if not isinstance(review_ref,str) or not review_ref.startswith(_SOURCE):
                return {'state':'HOLD_REVIEW_PROVENANCE'}
            if self.host.source_allowed(review_ref,scope) is not True:
                return {'state':'HOLD_REVIEW_NOT_ALLOWED'}
            metadata={'action':action_result.get('action'), 'request_sha256':action_result.get('request_sha256'),
                      'outcome_receipt_sha256':result_hash(action_result['receipt']),
                      'observation_sha256':result_hash(action_result['observation']),
                      'eval_score':float(score),'review_ref':review_ref,
                      'lesson_state':'VERIFIED_EXPERIENCE_NOT_NEURAL_WEIGHTS'}
            entry={'schema':'NOX_S03_VERIFIED_ACTION_V39','event_id':event_id,
                   'scope':{'tenant_id':scope.tenant_id,'principal_id':scope.principal_id,
                            'chat_id':scope.chat_id},'source_uri':source_uri,
                   'label':learning_label,'kind':'action_outcome','data':metadata}
            receipt=self.host.s03_append(scope,entry)
            if not isinstance(receipt,Mapping) or self.host.s03_verify(receipt,entry) is not True:
                return {'state':'HOLD_S03_DURABILITY_NOT_VERIFIED','s03_written':'UNKNOWN'}
        except Exception:return {'state':'HOLD_NATIVE_LEARNING_ERROR','s03_written':'UNKNOWN'}
        return {'state':'LEARNED_TO_EXISTING_S03','s03_written':True,
                'event_id':event_id,'s03_receipt_id':str(receipt.get('event_id',''))[:110],
                'lesson_candidate':True,'neural_weights_changed':False,
                'record_sha256':result_hash(entry)}

    def propose_distillation(self,scope:Scope,*,manifest:Mapping):
        """Only a native full-weight FORGE job, teacher-response/logit distillation.

        Does not export any private S03 text into a job; OneHost fetches approved
        content via scoped data references after independent review. NO LoRA.
        """
        scope.validate()
        if not isinstance(manifest,Mapping):return {'state':'HOLD_MANIFEST'}
        fields=('student_sha256','teacher_sha256','dataset_sha256','holdout_sha256',
                'base_checkpoint_sha256','source_manifest_sha256')
        if any(not isinstance(manifest.get(k),str) or not _SHA.fullmatch(manifest[k]) for k in fields):
            return {'state':'HOLD_MISSING_VERIFIED_SHA'}
        if manifest.get('distill_method') not in ('teacher_response_sft','teacher_logits_kl'):
            return {'state':'HOLD_UNKNOWN_DISTILLATION_METHOD'}
        if manifest.get('student_update')!='full_parameters' or manifest.get('uses_adapters') is not False:
            return {'state':'HOLD_ADAPTER_OR_FAKE_FULL_WEIGHTS'}
        if manifest.get('rights_verified') is not True or manifest.get('privacy_verified') is not True or manifest.get('quality_verified') is not True:
            return {'state':'HOLD_DATA_RIGHTS_PRIVACY_QUALITY'}
        n=manifest.get('training_examples',0);h=manifest.get('holdout_examples',0)
        if type(n) is not int or type(h) is not int or n<8 or h<2:
            return {'state':'HOLD_TRAIN_HOLDOUT_INSUFFICIENT'}
        if manifest.get('contains_raw_private_s03') is not False:
            return {'state':'HOLD_PRIVATE_MEMORY_EXPOSURE'}
        if not isinstance(manifest.get('approved_source_ref'),str) or not manifest['approved_source_ref'].startswith(_SOURCE):
            return {'state':'HOLD_SOURCE_REF_REQUIRED'}
        try:
            if (self.host.owner_opt_in(scope,'full_weight_distillation') is not True or
                self.host.source_allowed(manifest['approved_source_ref'],scope) is not True):
                return {'state':'HOLD_OWNER_OR_SOURCE'}
        except Exception:return {'state':'HOLD_OWNER_OR_SOURCE'}
        if not all(callable(getattr(self.host,k,None)) for k in ('native_backup_verify','forge_admission','native_queue_enqueue','native_queue_readback')):
            return {'state':'HOLD_NATIVE_FORGE_CALLBACKS_MISSING'}
        try:
            backup=self.host.native_backup_verify(scope)
            if not isinstance(backup,Mapping) or backup.get('offsite_restore_tested') is not True or backup.get('checkpoint_sha256')!=manifest['base_checkpoint_sha256']:
                return {'state':'HOLD_OFFSITE_RESTORE_NOT_VERIFIED'}
            gate=self.host.forge_admission(manifest)
            if not isinstance(gate,Mapping) or gate.get('state')!='READY_TO_REQUEST_NATIVE_APPROVAL':
                return {'state':'HOLD_GPU_FORGE_ADMISSION','gate':dict(gate) if isinstance(gate,Mapping) else {}}
            if not gate.get('sm70_cuda12_fp16_verified') or gate.get('disk_free_bytes',0)<20_000_000_000:
                return {'state':'HOLD_SM70_OR_DISK'}
            if gate.get('expected_peak_vram_mib',2**60)>gate.get('available_vram_for_training_mib',0):
                return {'state':'HOLD_FULL_WEIGHT_MEMORY_CAPACITY'}
            if gate.get('target_gpu_compute_pct')!=85:
                return {'state':'HOLD_COMPUTE_TARGET_NOT_85'}
            job={'type':'forge.full_parameter_distillation','source_ref':manifest['approved_source_ref'],
                 'distill_manifest_sha256':result_hash(dict(manifest)),
                 'dataset_sha256':manifest['dataset_sha256'],'student_sha256':manifest['student_sha256'],
                 'checkpoint_sha256':manifest['base_checkpoint_sha256'],
                 'priority':'P0','target_gpu_compute_pct':85,
                 'no_raw_prompts_in_queue':True,'owner_id':scope.principal_id}
            ticket=self.host.native_queue_enqueue(job)
            if not isinstance(ticket,Mapping) or not ticket.get('accepted') or not ticket.get('job_id'):
                return {'state':'HOLD_QUEUE_ENQUEUE_NOT_ACCEPTED'}
            readback=self.host.native_queue_readback(ticket)
            if not isinstance(readback,Mapping) or readback.get('job_id')!=ticket['job_id'] or readback.get('state') not in ('pending','running'):
                return {'state':'HOLD_QUEUE_RECEIPT_NOT_VERIFIED'}
            return {'state':'NATIVE_FORGE_JOB_QUEUED','job_id':ticket['job_id'],
                    'queue_state':readback['state'],'source_ref':manifest['approved_source_ref'],
                    'optimizer_steps_verified':0,'weights_changed_verified':False,
                    'target_gpu_compute_pct':85}
        except Exception:return {'state':'HOLD_NATIVE_QUEUE_OR_FORGE_ERROR'}

    def verify_weight_learning(self,job_id:str,*,base_weights_sha256:str):
        """Independent checkpoint readback: no optimizer steps == no neural learning."""
        if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9._:@-]{8,128}',job_id):
            return {'state':'HOLD_JOB_ID'}
        if not isinstance(base_weights_sha256,str) or not _SHA.fullmatch(base_weights_sha256):
            return {'state':'HOLD_BASE_SHA'}
        if not callable(self.host.native_training_receipt):return {'state':'HOLD_NO_TRAINING_RECEIPT_CALLBACK'}
        try:r=self.host.native_training_receipt(job_id)
        except Exception:return {'state':'HOLD_TRAINING_RECEIPT_NOT_READABLE'}
        if not isinstance(r,Mapping) or r.get('native_verified') is not True:
            return {'state':'HOLD_UNVERIFIED_TRAINER'}
        try:
            steps=r.get('optimizer_steps_verified',0)
            changed=r.get('student_weights_sha256')
            checkpoint=r.get('checkpoint_sha256')
            if type(steps) is not int or steps<=0 or not isinstance(changed,str) or not _SHA.fullmatch(changed) or changed==base_weights_sha256:
                return {'state':'HOLD_NO_VERIFIED_WEIGHT_UPDATE'}
            if not isinstance(checkpoint,str) or not _SHA.fullmatch(checkpoint):
                return {'state':'HOLD_CHECKPOINT_NOT_VERIFIED'}
            if (r.get('full_parameter_gradients_verified') is not True or r.get('adapter_only') is not False
                or r.get('holdout_improved') is not True or r.get('regression_passed') is not True
                or r.get('checkpoint_restorable') is not True):
                return {'state':'HOLD_POST_TRAIN_EVALUATION'}
        except Exception:return {'state':'HOLD_MALFORMED_TRAINING_RECEIPT'}
        return {'state':'NEURAL_DISTILLATION_VERIFIED','optimizer_steps_verified':steps,
                'student_weights_sha256':changed,'checkpoint_sha256':checkpoint,
                'release_accepted':False,'automatic_promotion':False}
