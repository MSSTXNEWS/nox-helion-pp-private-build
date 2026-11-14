"""NOX V43 Resource Brain: plans ONLY, no raw process kill or root shell.

Invoke from existing authorized OneHost with real GPU/RAM/process and queue data.
NOX remains a single student/identity. Each teacher tool must have native ownership,
STOP, idempotent receipt and independent readback before actual state change.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Policy:
    min_vram_free_mib: int = 3072
    min_ram_free_mib: int = 12288
    min_disk_free_bytes: int = 20_000_000_000
    max_loaded_teachers: int = 1
    protected_roles: tuple[str,...] = ('student','chat','optimizer','checkpoint','s03')


def plan_load(request, inventory, policy=Policy()):
    """Return HOLD, ALREADY_LOADED, OWNER_NATIVE_APPROVAL_REQUIRED, or REMOTE_PC.

    Cannot move files from Drive directly into RAM, cannot mix GPU0/GPU1 VRAM,
    cannot evict active trainer/student and never claims execution success.
    """
    if not isinstance(request,dict) or request.get('role') not in ('teacher','image','video'):
        return {'state':'HOLD_INVALID_REQUEST','performed':False}
    models=inventory.get('models',[]);gpus=inventory.get('gpus',[])
    mid=request.get('model_id')
    if not isinstance(mid,str) or not mid or not isinstance(models,list) or not isinstance(gpus,list):
        return {'state':'HOLD_INVALID_INVENTORY','performed':False}
    if any(m.get('id')==mid and m.get('loaded') is True for m in models):
        return {'state':'ALREADY_LOADED','performed':False,'model_id':mid}
    source=next((m for m in models if m.get('id')==mid),None)
    if not source or source.get('sha_verified') is not True or source.get('approved_license') is not True:
        return {'state':'HOLD_NO_VERIFIED_LOCAL_ASSET','performed':False}
    if inventory.get('stop_active') is not False:
        return {'state':'HOLD_STOP_OR_SENSOR','performed':False}
    if inventory.get('checkpoint_pending') is True or inventory.get('optimizer_step_active') is True:
        return {'state':'HOLD_CHECKPOINT_OR_ACTIVE_OPTIMIZER','performed':False}
    if inventory.get('disk_free_bytes',0)<policy.min_disk_free_bytes:
        return {'state':'REMOTE_PC_COLD_OR_DRIVE_ONLY','performed':False,'reason':'VAST_DISK_BELOW_RESERVE'}
    if inventory.get('ram_free_mib',0)<policy.min_ram_free_mib:
        return {'state':'REMOTE_PC_OR_HOLD','performed':False,'reason':'RAM_RESERVE'}
    if request['role'] in ('image','video') and source.get('runtime')!='dedicated_vetted_tool':
        return {'state':'HOLD_DIFFUSION_RUNTIME_NOT_VERIFIED','performed':False}
    peak=request.get('peak_vram_mib')
    if not isinstance(peak,int) or peak<=0:return {'state':'HOLD_MISSING_VRAM_ESTIMATE','performed':False}
    # Per GPU limits: memory in 2 separate cards cannot be added unless native
    # scheduler has explicitly validated tensor parallel for this model.
    fit=[g for g in gpus if isinstance(g,dict) and g.get('id')==1
         and g.get('vram_free_mib',0)>=peak+policy.min_vram_free_mib
         and g.get('protected_student') is not True]
    active_teachers=sum(bool(m.get('loaded')) for m in models if m.get('role')=='teacher')
    if active_teachers>=policy.max_loaded_teachers:
        # only propose native unload of idle teacher owned by NOX, NOT arbitrary process
        idle=[m['id'] for m in models if m.get('loaded') and m.get('role')=='teacher'
              and m.get('in_flight',0)==0 and not m.get('pinned') and m.get('native_owner')=='OneHost']
        return {'state':'OWNER_NATIVE_UNLOAD_AND_RETRY_REQUIRED' if idle else 'HOLD_TEACHER_LIMIT',
                'unload_candidates':idle,'performed':False}
    if not fit:
        return {'state':'REMOTE_PC_OR_HOLD','performed':False,'reason':'GPU1_INSUFFICIENT_VRAM_OR_NOT_AVAILABLE'}
    return {'state':'OWNER_NATIVE_APPROVAL_REQUIRED','target_gpu':1,'model_id':mid,
            'max_parallel':1,'performed':False,'no_chat_pause':True}


def apply_native_plan(plan, *, native_stop, native_authorize, native_act, native_verify, native_readback):
    """Only the EXISTING OneHost can apply a preapproved action; no shell.

    Real host must check signed approval and resource preimage itself. The
    function does not guess any auth token or create an HTTP endpoint.
    """
    if plan.get('state')!='OWNER_NATIVE_APPROVAL_REQUIRED':
        return {'state':'HOLD_NOT_ADMITTED','performed':False}
    if any(not callable(f) for f in (native_stop,native_authorize,native_act,native_verify,native_readback)):
        return {'state':'HOLD_NATIVE_CALLBACKS_MISSING','performed':False}
    try:
        if native_stop() is not False or native_authorize(plan) is not True:
            return {'state':'HOLD_NATIVE_STOP_OR_SCOPE','performed':False}
        receipt=native_act(plan)
        if native_verify(plan,receipt) is not True:
            return {'state':'HOLD_EXECUTED_UNVERIFIED','performed':'UNKNOWN'}
        actual=native_readback(plan,receipt)
        if actual.get('model_id')!=plan['model_id'] or actual.get('running') is not True:
            return {'state':'HOLD_NATIVE_READBACK_FAILED','performed':'UNKNOWN'}
        return {'state':'NATIVE_ACTIVATED_VERIFIED','performed':True,'receipt':receipt}
    except Exception:
        return {'state':'HOLD_NATIVE_EXECUTION_ERROR','performed':'UNKNOWN'}
