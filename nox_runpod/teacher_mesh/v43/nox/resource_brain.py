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
    # Existing SHA-verified local models can be mapped without new downloads.
    # No hard 20 GB gate on chat/teacher inference. New writes use V71 budget.
    min_disk_free_bytes: int = 10_000_000_000
    max_loaded_teachers: int = 1
    protected_roles: tuple[str,...] = ('student','chat','optimizer','checkpoint','s03')


def plan_load(request, inventory, policy=Policy()):
    """Return HOLD, ALREADY_LOADED, OWNER_NATIVE_APPROVAL_REQUIRED, or REMOTE_PC.

    Cannot move files from Drive directly into RAM, cannot mix GPU0/GPU1 VRAM,
    cannot evict active trainer/student and never claims execution success.
    """
    if not isinstance(request,dict) or request.get('role') not in ('teacher','image','video'):
        return {'state':'HOLD_INVALID_REQUEST','performed':False}
    # A proposal is meaningful only on an authenticated, complete OneHost
    # snapshot. Missing fields are UNKNOWN, never "idle" or "available".
    if not isinstance(inventory,dict) or inventory.get('native_verified') is not True:
        return {'state':'HOLD_NATIVE_INVENTORY_UNVERIFIED','performed':False}
    models=inventory.get('models');gpus=inventory.get('gpus')
    mid=request.get('model_id')
    if (type(mid) is not str or not mid or not isinstance(models,list)
            or not isinstance(gpus,list)
            or any(not isinstance(m,dict) for m in models)
            or any(not isinstance(g,dict) for g in gpus)):
        return {'state':'HOLD_INVALID_INVENTORY','performed':False}
    if any(type(m.get('loaded')) is not bool for m in models):
        return {'state':'HOLD_MODEL_LOAD_STATE_UNVERIFIED','performed':False}
    if any(m.get('id')==mid and m.get('loaded') is True for m in models):
        return {'state':'ALREADY_LOADED','performed':False,'model_id':mid}
    source=next((m for m in models if m.get('id')==mid),None)
    if not source or source.get('sha_verified') is not True or source.get('approved_license') is not True:
        return {'state':'HOLD_NO_VERIFIED_LOCAL_ASSET','performed':False}
    if inventory.get('stop_active') is not False:
        return {'state':'HOLD_STOP_OR_SENSOR','performed':False}
    if inventory.get('checkpoint_pending') is not False or inventory.get('optimizer_step_active') is not False:
        return {'state':'HOLD_CHECKPOINT_OR_ACTIVE_OPTIMIZER','performed':False}
    if inventory.get('chat_gpu0_healthy') is not True:
        return {'state':'HOLD_CHAT_GPU0_UNVERIFIED','performed':False}
    # An optimizer can be BETWEEN steps while still holding GPU1. Read the
    # lease and trainer/teacher activity explicitly; never infer "idle".
    if (inventory.get('gpu1_trainer_active') is not False
            or inventory.get('gpu1_teacher_in_flight') is not False
            or inventory.get('onehost_gpu1_lease') is not True):
        return {'state':'HOLD_GPU1_BUSY_OR_LEASE_UNVERIFIED','performed':False}
    # This is a loader for ALREADY LOCAL assets, not a model downloader.
    # Never silently fetch a teacher on the almost-full Vast disk.
    if request.get('download_needed') is True or source.get('installed_locally') is not True:
        return {'state':'REMOTE_PC_COLD_OR_DRIVE_ONLY','performed':False,
                'reason':'NO_NEW_MODEL_DOWNLOAD_FROM_RESOURCE_BRAIN'}
    if request.get('new_disk_bytes',0)!=0:
        return {'state':'HOLD_NEW_DISK_WRITE_NEEDS_SEPARATE_VERIFIED_BUDGET',
                'performed':False}
    ram_free=inventory.get('ram_free_mib')
    if type(ram_free) is not int or ram_free<0:
        return {'state':'HOLD_RAM_SENSOR_UNVERIFIED','performed':False}
    # Host MemAvailable is not the OneHost container's usable RAM. GPU1
    # teacher load must preserve chat/cgroup headroom as well as host RAM.
    limit=inventory.get('cgroup_max_bytes')
    used=inventory.get('cgroup_current_bytes')
    if (type(limit) is not int or type(used) is not int
            or limit<=0 or used<0 or used>limit):
        return {'state':'HOLD_CGROUP_RAM_UNVERIFIED','performed':False}
    effective_free=min(ram_free,(limit-used)//(1024*1024))
    if effective_free<policy.min_ram_free_mib:
        return {'state':'REMOTE_PC_OR_HOLD','performed':False,'reason':'CGROUP_OR_HOST_RAM_RESERVE'}
    if request['role'] in ('image','video') and source.get('runtime')!='dedicated_vetted_tool':
        return {'state':'HOLD_DIFFUSION_RUNTIME_NOT_VERIFIED','performed':False}
    peak=request.get('peak_vram_mib')
    if type(peak) is not int or peak<=0:
        return {'state':'HOLD_MISSING_VRAM_ESTIMATE','performed':False}
    # P0 must distinguish two *separate* V100 cards from one forged or
    # aggregated 64 GiB value. Bool/str VRAM readings are not measurements.
    ids=[g.get('id') for g in gpus]
    if (len(ids)!=2 or any(type(x) is not int for x in ids)
            or sorted(ids)!=[0,1]):
        return {'state':'HOLD_GPU_TOPOLOGY_UNVERIFIED','performed':False}
    gpu1=next(g for g in gpus if g['id']==1)
    free=gpu1.get('vram_free_mib')
    if (type(free) is not int or not 0<=free<=32768
            or gpu1.get('protected_student') is not False):
        return {'state':'HOLD_GPU1_NATIVE_SENSOR_UNVERIFIED','performed':False}
    # Memory cannot be pooled across GPU0+GPU1 without a verified separate
    # tensor-parallel admission. Resource Brain never performs that admission.
    fit=free>=peak+policy.min_vram_free_mib
    active_teachers=sum(bool(m.get('loaded')) for m in models if m.get('role')=='teacher')
    if active_teachers>=policy.max_loaded_teachers:
        # only propose native unload of idle teacher owned by NOX, NOT arbitrary process
        # Unknown in-flight/pinned state MUST NOT suggest unloading a model.
        # Only a confirmed idle, explicitly unpinned, OneHost-owned teacher
        # with a valid ID can ever become a *proposal*, never auto-eviction.
        idle=[m['id'] for m in models
              if m.get('loaded') is True and m.get('role')=='teacher'
              and type(m.get('in_flight')) is int and m['in_flight']==0
              and m.get('pinned') is False and m.get('native_owner')=='OneHost'
              and isinstance(m.get('id'),str) and bool(m['id'])]
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
    if (not isinstance(plan,dict) or
            plan.get('state')!='OWNER_NATIVE_APPROVAL_REQUIRED' or
            type(plan.get('target_gpu')) is not int or plan['target_gpu']!=1 or
            plan.get('max_parallel')!=1 or plan.get('no_chat_pause') is not True or
            not isinstance(plan.get('model_id'),str) or not plan['model_id'] or
            plan.get('performed') is not False):
        return {'state':'HOLD_NOT_ADMITTED','performed':False}
    if any(not callable(f) for f in (native_stop,native_authorize,native_act,native_verify,native_readback)):
        return {'state':'HOLD_NATIVE_CALLBACKS_MISSING','performed':False}
    try:
        if native_stop() is not False or native_authorize(plan) is not True:
            return {'state':'HOLD_NATIVE_STOP_OR_SCOPE','performed':False}
        # Re-check after authorization: STOP may have changed during approval.
        if native_stop() is not False:
            return {'state':'HOLD_NATIVE_STOP_RACE','performed':False}
        receipt=native_act(plan)
        if native_verify(plan,receipt) is not True:
            return {'state':'HOLD_EXECUTED_UNVERIFIED','performed':'UNKNOWN'}
        actual=native_readback(plan,receipt)
        if actual.get('model_id')!=plan['model_id'] or actual.get('running') is not True:
            return {'state':'HOLD_NATIVE_READBACK_FAILED','performed':'UNKNOWN'}
        return {'state':'NATIVE_ACTIVATED_VERIFIED','performed':True,'receipt':receipt}
    except Exception:
        return {'state':'HOLD_NATIVE_EXECUTION_ERROR','performed':'UNKNOWN'}
