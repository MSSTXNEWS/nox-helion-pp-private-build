"""NOX V47 overnight training handshake; uses real existing OneHost callbacks only.

Does not expose an HTTP endpoint, spawn a worker, or execute arbitrary shell.
A signed owner's approval is required for each mutation. Readback of optimizer
steps, checkpoint and changed weights is independent of queue acceptance.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from .policy import assess

@dataclass(frozen=True)
class OneHostPorts:
    authorize: Callable[[str],bool]
    stop: Callable[[],bool]
    observe: Callable[[],Mapping]
    approve: Callable[[str,str,Mapping],bool]
    stage_smoke: Callable[[Mapping],Mapping]
    verify_stage: Callable[[Mapping],bool]
    readback: Callable[[str],Mapping]
    s03_audit: Callable[[Mapping],Mapping]
    s03_verify: Callable[[Mapping,Mapping],bool]

def stage_native_smoke(host, owner_scope):
    """One *small* smoke only; not autonomous infinite training until proof is real."""
    if not isinstance(owner_scope,str) or not (4<=len(owner_scope)<=128):
        return {'state':'HOLD_OWNER_SCOPE','performed':False}
    attrs=('authorize','stop','observe','approve','stage_smoke','verify_stage','readback','s03_audit','s03_verify')
    if any(not callable(getattr(host,a,None)) for a in attrs):
        return {'state':'HOLD_NATIVE_CALLBACKS','performed':False}
    def gate():
        try:return host.stop() is False and host.authorize(owner_scope) is True
        except Exception:return False
    if not gate():return {'state':'HOLD_STOP_OR_OWNER','performed':False}
    try: snapshot=host.observe()
    except Exception:return {'state':'HOLD_NATIVE_OBSERVATION','performed':False}
    plan=assess(snapshot)
    if plan['state']!='READY_FOR_NATIVE_OWNER_APPROVAL':return plan
    if host.approve(owner_scope,plan['preimage_sha256'],snapshot) is not True:
        return {'state':'HOLD_NOT_APPROVED','performed':False}
    if not gate():return {'state':'HOLD_STOP_REVOKED','performed':False}
    try:
        receipt=host.stage_smoke(plan)
        if not isinstance(receipt,Mapping) or host.verify_stage(receipt) is not True:
            return {'state':'HOLD_SMOKE_UNVERIFIED','performed':'UNKNOWN'}
        # Confirm that stage remains isolated from active student. Stage success
        # does NOT prove changed weights, and NEVER promotes a model.
        if receipt.get('checkpoint_staged') is not True or receipt.get('active_student_unchanged') is not True:
            return {'state':'HOLD_STAGING_INVARIANT','performed':'UNKNOWN'}
        observed=host.readback(str(receipt.get('stage_id','')))
        if (not isinstance(observed,Mapping) or observed.get('stage_id')!=receipt.get('stage_id')
            or observed.get('checkpoint_staged') is not True):
            return {'state':'HOLD_STAGE_READBACK','performed':'UNKNOWN'}
        event={'schema':'NOX_V47_FORGE_STAGING','stage_id':receipt.get('stage_id'),
               'checkpoint_staged':True,'active_student_unchanged':True,
               'preimage_sha256':plan['preimage_sha256'],
               'optimizer_steps_verified':False,'weights_changed_verified':False}
        audit=host.s03_audit(event)
        if host.s03_verify(audit,event) is not True:
            return {'state':'HOLD_S03_DURABILITY','performed':'UNKNOWN'}
    except Exception:
        return {'state':'HOLD_NATIVE_EXECUTION_UNKNOWN','performed':'UNKNOWN'}
    return {'state':'NATIVE_SMOKE_STAGED_VERIFIED','performed':True,
            'weights_changed_verified':False,'optimizer_steps_verified':False,
            'student_preserved':True,'stage_id':receipt['stage_id'],
            'next':'ACTUAL_TRAIN_STEP_AND_INDEPENDENT_HOLDOUT_REQUIRED'}
