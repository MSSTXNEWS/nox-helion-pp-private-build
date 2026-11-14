"""NOX V39 native OneHost admin broker.

Mirrors the existing NOX run_admin / V37 native_admin pattern, not a public shell.
All operations require registered trusted OneHost callbacks. This module starts
no daemon, socket, GPU job or backend. No credentials are stored or logged.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable, Mapping
import hashlib
import json
import re
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9._:@/-]{1,160}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
READ = frozenset({
    'server.status','server.gpus','server.memory','server.disk',
    'server.services','server.logs','server.checkpoints',
    'nox.chat.status','nox.cores.status','nox.s03.status','nox.worms.status',
    'nox.queue.status','nox.training.status','nox.teachers.status','nox.model.status',
    'nox.learning.status','nox.skills.status','nox.jobs.status','nox.audit.status',
})
WRITE = frozenset({
    'nox.queue.enqueue','nox.queue.cancel','nox.training.resume','nox.training.pause',
    'nox.teacher.start','nox.teacher.stop','nox.checkpoint.backup',
    'nox.model.activate','nox.service.restart','nox.file.stage_patch',
    'nox.cache.cleanup_approved','nox.forge.distill.enqueue',
    'nox.s03.write_verified',
})
ALL = READ | WRITE
PARAM_KEYS = {
    'nox.queue.enqueue': frozenset({'job_ref','job_sha256','lane','priority'}),
    'nox.queue.cancel': frozenset({'job_id'}),
    'nox.training.resume': frozenset({'checkpoint_sha256','trainer_id','gpu_id'}),
    'nox.training.pause': frozenset({'trainer_id','graceful'}),
    'nox.teacher.start': frozenset({'teacher_id','manifest_sha256','gpu_id'}),
    'nox.teacher.stop': frozenset({'teacher_id','graceful'}),
    'nox.checkpoint.backup': frozenset({'checkpoint_sha256','destination_id'}),
    'nox.model.activate': frozenset({'model_sha256','validation_receipt_sha256'}),
    'nox.service.restart': frozenset({'service_id','preflight_sha256'}),
    'nox.file.stage_patch': frozenset({'patch_sha256','repo_ref','expected_base_sha256'}),
    'nox.cache.cleanup_approved': frozenset({'cleanup_manifest_sha256','backup_receipt_sha256'}),
    'nox.forge.distill.enqueue': frozenset({'distill_manifest_sha256','student_sha256','checkpoint_sha256'}),
    'nox.s03.write_verified': frozenset({'event_ref','event_sha256'}),
}
DANGEROUS = frozenset({'nox.model.activate','nox.service.restart','nox.cache.cleanup_approved', 'nox.file.stage_patch'})
SECRET = re.compile(r'(password|token|cookie|secret|api[_-]?key|private[_-]?key|authorization|credential)', re.I)

@dataclass(frozen=True)
class Scope:
    tenant_id: str
    principal_id: str
    chat_id: str
    def validate(self):
        for x in (self.tenant_id, self.principal_id, self.chat_id):
            if not isinstance(x,str) or not _ID.fullmatch(x):
                raise ValueError('NATIVE_AUTHENTICATED_SCOPE_REQUIRED')


def _sanitized(value: Any, depth: int=0) -> Any:
    """Redact secret fields and bound returned telemetry; NOT a credential vault."""
    if depth>6:return 'MAX_DEPTH'
    if isinstance(value, Mapping):
        return {str(k)[:100]:_sanitized(v,depth+1) for k,v in list(value.items())[:100]
                if not SECRET.search(str(k))}
    if isinstance(value,(tuple,list)):return [_sanitized(v,depth+1) for v in value[:100]]
    if isinstance(value,str):return value[:1000]
    if value is None or type(value) in (bool,int,float):return value
    return 'UNSUPPORTED_VALUE'


def canonical(action:str,target_id:str,scope:Scope,request_id:str,parameters:dict|None=None,preimage_sha256:str|None=None):
    scope.validate()
    if action not in ALL: raise ValueError('ACTION_NOT_ALLOWLISTED')
    if not isinstance(target_id,str) or not _ID.fullmatch(target_id):raise ValueError('BAD_TARGET_ID')
    if not isinstance(request_id,str) or not _ID.fullmatch(request_id):raise ValueError('BAD_REQUEST_ID')
    params=parameters if parameters is not None else {}
    if not isinstance(params,dict) or len(params)>8 or any(SECRET.search(str(k)) for k in params):
        raise ValueError('INVALID_OR_SECRET_PARAMETERS')
    if action in READ and params:raise ValueError('READ_PARAMETERS_NOT_ALLOWED')
    if action in WRITE:
        if not params or set(params)-PARAM_KEYS[action]:raise ValueError('PARAMETER_SCHEMA_VIOLATION')
        for k,v in params.items():
            if not isinstance(v,(str,bool,int)) or (isinstance(v,str) and (not _ID.fullmatch(v) or len(v)>160)):
                raise ValueError('TYPED_PARAMETERS_ONLY')
            if k.endswith('sha256') and not (isinstance(v,str) and _SHA.fullmatch(v)):
                raise ValueError('SHA256_REQUIRED')
        if not isinstance(preimage_sha256,str) or not _SHA.fullmatch(preimage_sha256):
            raise ValueError('EXACT_PREIMAGE_SHA_REQUIRED')
    if preimage_sha256 is not None and not _SHA.fullmatch(preimage_sha256):
        raise ValueError('INVALID_PREIMAGE_SHA')
    request={'action':action,'target_id':target_id,'tenant_id':scope.tenant_id,
             'principal_id':scope.principal_id,'chat_id':scope.chat_id,
             'request_id':request_id,'parameters':params,'preimage_sha256':preimage_sha256}
    raw=json.dumps(request,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return request,hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class HostAdmin:
    """EVERY callback is an actual trusted OneHost function, not LLM text."""
    authorize: Callable[[dict],bool]
    stop: Callable[[],bool]
    registered: Callable[[str],bool]
    inspect: Callable[[dict],Mapping]
    execute: Callable[[dict,str,Mapping],Mapping]|None=None
    approve: Callable[[dict,str,Mapping],bool]|None=None
    verify_execution: Callable[[Mapping,dict,str],bool]|None=None
    readback: Callable[[dict,Mapping],Mapping]|None=None
    audit: Callable[[Mapping],bool]|None=None


class NativeAdmin:
    def __init__(self,host:HostAdmin):
        if not all(callable(getattr(host,name,None)) for name in ('authorize','stop','registered','inspect')):
            raise TypeError('NATIVE_ONEHOST_REQUIRED')
        self.host=host
    def _gate(self,request):
        try:return self.host.stop() is False and self.host.authorize(request) is True
        except Exception:return False
    def invoke(self,action:str,target_id:str,scope:Scope,request_id:str,*,parameters=None,
               preimage_sha256=None,approved_sha256=None):
        try: request,digest=canonical(action,target_id,scope,request_id,parameters,preimage_sha256)
        except (TypeError,ValueError) as e:return {'state':'HOLD_INVALID_REQUEST','reason':str(e),'performed':False}
        if not self._gate(request):return {'state':'HOLD_STOP_OR_SCOPE','performed':False}
        try:
            if self.host.registered(action) is not True:
                return {'state':'HOLD_NATIVE_ACTION_NOT_REGISTERED','action':action,'performed':False}
            before=self.host.inspect(request)
            if not isinstance(before,Mapping):raise TypeError('INVALID_NATIVE_INSPECT')
        except Exception:return {'state':'HOLD_INSPECT_UNAVAILABLE','performed':False}
        if not self._gate(request):return {'state':'HOLD_SCOPE_CHANGED','performed':False}
        if action in READ:
            return {'state':'READ_ONLY_FROM_NATIVE_ONEHOST','action':action,'request_sha256':digest,
                    'data':_sanitized(before),'performed':False,'source':'NATIVE_ONEHOST_REPORT_NOT_EXTERNAL_AUDIT'}
        plan={'action':action,'target_id':target_id,'request_sha256':digest,
              'dangerous':action in DANGEROUS,'preimage_sha256':preimage_sha256,
              'before':_sanitized(before),'performed':False}
        if approved_sha256!=digest:return {'state':'OWNER_EXACT_APPROVAL_REQUIRED','plan':plan,'performed':False}
        h=self.host
        if not all(callable(x) for x in (h.approve,h.execute,h.verify_execution,h.readback,h.audit)):
            return {'state':'HOLD_NATIVE_EXECUTION_PORTS_MISSING','plan':plan,'performed':False}
        if not self._gate(request):return {'state':'HOLD_STOP_OR_SCOPE','performed':False}
        try:
            if h.approve(request,digest,before) is not True:
                return {'state':'HOLD_NATIVE_OWNER_APPROVAL','performed':False}
            if not self._gate(request):return {'state':'HOLD_STOP_OR_SCOPE','performed':False}
            receipt=h.execute(request,digest,before)
            if not isinstance(receipt,Mapping) or h.verify_execution(receipt,request,digest) is not True:
                return {'state':'HOLD_EXECUTED_UNVERIFIED','performed':'UNKNOWN'}
            after=h.readback(request,receipt)
            if not isinstance(after,Mapping):
                return {'state':'HOLD_AFTER_EXEC_UNREADABLE','performed':True}
            audit={'request_sha256':digest,'action':action,'receipt':_sanitized(receipt),
                   'before':_sanitized(before),'after':_sanitized(after)}
            if h.audit(audit) is not True:return {'state':'HOLD_AUDIT_NOT_DURABLE','performed':True}
        except Exception:return {'state':'HOLD_NATIVE_EXECUTION_ERROR','performed':'UNKNOWN'}
        if not self._gate(request):return {'state':'HOLD_POST_EXEC_STOP','performed':True}
        return {'state':'EXECUTED_NATIVE_AND_VERIFIED','performed':True,
                'request_sha256':digest,'action':action,'receipt':_sanitized(receipt),
                'observation':_sanitized(after),'production_accepted':False}


# Existing NOX run_admin actions observed in the live chat; no invented endpoint.
OBSERVED_RUN_ADMIN=frozenset({'training_status','queue_status'})

def observed_run_admin(host_call:Callable[[str],Mapping],action:str):
    if action not in OBSERVED_RUN_ADMIN:
        return {'state':'HOLD_RUN_ADMIN_ACTION_NOT_CONFIRMED'}
    try:data=host_call(action)
    except Exception:return {'state':'HOLD_RUN_ADMIN_UNAVAILABLE'}
    if not isinstance(data,Mapping):return {'state':'HOLD_INVALID_RUN_ADMIN_DATA'}
    return {'state':'NOX_RUN_ADMIN_SELF_REPORT','action':action,'data':_sanitized(data),
            'independent_verified':False}
