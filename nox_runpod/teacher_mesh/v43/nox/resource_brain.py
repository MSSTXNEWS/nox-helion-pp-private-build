"""NOX V43 Resource Brain: plans ONLY, no raw process kill or root shell.

Invoke from existing authorized OneHost with real GPU/RAM/process and queue data.
NOX remains a single student/identity. Each teacher tool must have native ownership,
STOP, idempotent receipt and independent readback before actual state change.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

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
        # A matching model name on GPU0 (or an unowned process) is not proof
        # of a safe GPU1 activation. Require fresh native readback, not a
        # caller-supplied proposal or an optimistic verifier alone.
        if (not isinstance(actual,dict) or actual.get('model_id')!=plan['model_id']
                or actual.get('running') is not True
                or type(actual.get('gpu_id')) is not int or actual['gpu_id']!=1
                or actual.get('native_owner')!='OneHost'
                or actual.get('onehost_gpu1_lease') is not True
                or actual.get('stop_active') is not False):
            return {'state':'HOLD_NATIVE_READBACK_FAILED','performed':'UNKNOWN'}
        if native_stop() is not False:
            return {'state':'HOLD_NATIVE_STOP_AFTER_READBACK','performed':'UNKNOWN'}
        return {'state':'NATIVE_ACTIVATED_VERIFIED','performed':True,'receipt':receipt}
    except Exception:
        return {'state':'HOLD_NATIVE_EXECUTION_ERROR','performed':'UNKNOWN'}


# GPU0/GPU1 control hooks for the EXISTING OneHost Resource Brain.
# These pure admission functions DO NOT spawn services, install packages,
# hard-cap physical GPU load, stop arbitrary PIDs or prove live deployment.
from collections.abc import Mapping as _Mapping


@dataclass(frozen=True)
class AdaptiveTargets:
    steady_low_pct: int = 80
    steady_high_pct: int = 85
    peak_soft_ceiling_pct: int = 95
    gpu_vram_reserve_mib: int = 4096
    min_cgroup_headroom_bytes: int = 12 * 1024**3
    min_disk_free_bytes: int = 10_000_000_000
    pause_new_work_at_celsius: int = 70

    def __post_init__(self):
        if not (0 < self.steady_low_pct < self.steady_high_pct
                < self.peak_soft_ceiling_pct <= 100):
            raise ValueError('HOLD_UNSAFE_GPU_UTILIZATION_TARGETS')


def _gpu_entry(snapshot, gpu_id):
    if type(gpu_id) is not int or gpu_id not in (0, 1):
        return None
    gpus=snapshot.get('gpus')
    if not isinstance(gpus,list) or len(gpus)!=2 or any(not isinstance(g,_Mapping) for g in gpus):
        return None
    ids=[g.get('id') for g in gpus]
    if any(type(x) is not int for x in ids) or sorted(ids)!=[0,1]:
        return None
    return next(g for g in gpus if g['id']==gpu_id)


def _has_headroom(snapshot, entry, targets):
    utilization=entry.get('utilization_pct')
    free=entry.get('vram_free_mib')
    temp=entry.get('temperature_c')
    disk=snapshot.get('disk_free_bytes')
    limit=snapshot.get('cgroup_max_bytes')
    used=snapshot.get('cgroup_current_bytes')
    if (type(utilization) is not int or not 0<=utilization<=100
            or type(free) is not int or not 0<=free<=32768
            or type(temp) is not int or not 0<=temp<=110
            or type(disk) is not int or disk<0
            or type(limit) is not int or limit<=0
            or type(used) is not int or not 0<=used<=limit):
        return False,'HOLD_GPU_MEMORY_THERMAL_OR_CGROUP_SENSOR'
    if (temp>=targets.pause_new_work_at_celsius
            or free<targets.gpu_vram_reserve_mib
            or limit-used<targets.min_cgroup_headroom_bytes
            or disk<targets.min_disk_free_bytes):
        return False,'HOLD_GPU_THERMAL_VRAM_DISK_OR_CGROUP_RESERVE'
    return True,None


def plan_adaptive_gpu(snapshot, gpu_id, targets=AdaptiveTargets()):
    """80-85% useful steady scheduling; up to 95% brief peak, NOT a hardware cap.

    Only the existing owner runtime may adjust its own queue/batching.
    No dummy workload, forced GPU busy-loop or parallel training process.
    """
    base={'performed':False,'gpu_id':gpu_id,'steady_target_pct':[80,85],
          'peak_soft_ceiling_pct':95,'hard_gpu_util_cap_guaranteed':False,
          'new_process_started':False,'no_competing_trainer':True}
    if not isinstance(snapshot,_Mapping) or snapshot.get('native_verified') is not True:
        return {**base,'state':'HOLD_NATIVE_INVENTORY'}
    g=_gpu_entry(snapshot,gpu_id)
    if g is None or g.get('native_owner')!='OneHost':
        return {**base,'state':'HOLD_GPU_OWNER_TOPOLOGY'}
    latches=snapshot.get('manual_stop_latched')
    if not isinstance(latches,_Mapping) or latches.get(str(gpu_id)) is not False:
        return {**base,'state':'HOLD_MANUAL_STOP_LATCHED'}
    if snapshot.get('stop_active') is not False:
        return {**base,'state':'HOLD_GLOBAL_STOP'}
    if snapshot.get('onehost_gpu_lease',{}).get(str(gpu_id)) is not True:
        return {**base,'state':'HOLD_GPU_OWNER_LEASE'}
    if gpu_id==1 and (snapshot.get('gpu1_trainer_owner_verified') is not True
                      or snapshot.get('gpu1_checkpoint_safe') is not True):
        return {**base,'state':'HOLD_GPU1_TRAINER_CHECKPOINT_UNKNOWN'}
    ok,reason=_has_headroom(snapshot,g,targets)
    if not ok:return {**base,'state':reason}
    demand=snapshot.get('pending_useful_work',{}).get(str(gpu_id))
    if type(demand) is not int or demand<0:
        return {**base,'state':'HOLD_QUEUE_DEMAND_SENSOR'}
    if demand==0:
        return {**base,'state':'IDLE_NO_ARTIFICIAL_GPU_LOAD'}
    current=g['utilization_pct']
    if current>=targets.peak_soft_ceiling_pct:
        return {**base,'state':'BACKPRESSURE_AT_95_PCT','admit_more':False}
    if current>=targets.steady_high_pct:
        return {**base,'state':'PEAK_EXISTING_WORK_ONLY','admit_more':False}
    if current>=targets.steady_low_pct:
        return {**base,'state':'STEADY_80_85_PCT','admit_more':False}
    return {**base,'state':'OWNER_QUEUE_TUNING_CANDIDATE','admit_more':True,
            'action':'TUNE_EXISTING_BATCH_WITHOUT_NEW_PROCESS'}


def plan_gpu_stop(snapshot, gpu_id):
    """Manual STOP is latched before quiesce/save; never kill unknown processes."""
    if not isinstance(snapshot,_Mapping) or snapshot.get('native_verified') is not True:
        return {'state':'HOLD_NATIVE_INVENTORY','performed':False}
    g=_gpu_entry(snapshot,gpu_id)
    if g is None or g.get('native_owner')!='OneHost':
        return {'state':'HOLD_UNOWNED_GPU_PROCESS','performed':False}
    if snapshot.get('onehost_gpu_lease',{}).get(str(gpu_id)) is not True:
        return {'state':'HOLD_NO_OWNER_GPU_LEASE','performed':False}
    if snapshot.get('manual_stop_latched',{}).get(str(gpu_id)) is True:
        return {'state':'ALREADY_MANUALLY_STOP_LATCHED','performed':False}
    return {'state':'OWNER_NATIVE_STOP_REQUIRED','gpu_id':gpu_id,
            'manual_stop_latched_after':True,'performed':False}


def execute_gpu_stop(plan, *, authorize, latch_stop, quiesce,
                     save_progress, verify_progress, stop_owned, readback):
    """Order: owner grant → durable STOP latch → drain → save → verify → STOP.

    If anything fails after latching, keep STOP active and return HOLD.
    GPU0 save verifies original S03, GPU1 verifies full optimizer checkpoint.
    """
    if (not isinstance(plan,_Mapping) or plan.get('state')!='OWNER_NATIVE_STOP_REQUIRED'
            or type(plan.get('gpu_id')) is not int or plan['gpu_id'] not in (0,1)):
        return {'state':'HOLD_STOP_NOT_ADMITTED','performed':False}
    callbacks=(authorize,latch_stop,quiesce,save_progress,
               verify_progress,stop_owned,readback)
    if any(not callable(f) for f in callbacks):
        return {'state':'HOLD_STOP_CALLBACKS_MISSING','performed':False}
    latched=False
    try:
        if authorize(plan) is not True:
            return {'state':'HOLD_STOP_NOT_AUTHORIZED','performed':False}
        if latch_stop(plan) is not True:
            return {'state':'HOLD_STOP_LATCH_NOT_DURABLE','performed':False}
        latched=True
        if quiesce(plan) is not True:
            return {'state':'HOLD_STOP_LATCHED_QUIESCE','performed':False,
                    'manual_stop_latched':True}
        proof=save_progress(plan)
        if not isinstance(proof,_Mapping) or verify_progress(plan,proof) is not True:
            return {'state':'HOLD_STOP_LATCHED_SAVE_UNVERIFIED','performed':False,
                    'manual_stop_latched':True}
        if plan['gpu_id']==0:
            valid=proof.get('s03_fsync_verified') is True
        else:
            valid=(proof.get('checkpoint_sha_verified') is True
                   and proof.get('optimizer_state_verified') is True
                   and proof.get('offsite_restore_verified') is True)
        if not valid:
            return {'state':'HOLD_STOP_LATCHED_PERSISTENCE','performed':False,
                    'manual_stop_latched':True}
        if stop_owned(plan,proof) is not True:
            return {'state':'HOLD_STOP_LATCHED_OWNER_STOP','performed':'UNKNOWN',
                    'manual_stop_latched':True}
        actual=readback(plan)
        if (not isinstance(actual,_Mapping) or actual.get('gpu_id')!=plan['gpu_id']
                or actual.get('native_owner')!='OneHost'
                or actual.get('owned_process_running') is not False
                or actual.get('manual_stop_latched') is not True):
            return {'state':'HOLD_STOP_LATCHED_READBACK','performed':'UNKNOWN',
                    'manual_stop_latched':True}
        return {'state':'NATIVE_GPU_STOP_VERIFIED','gpu_id':plan['gpu_id'],
                'performed':True,'manual_stop_latched':True}
    except Exception:
        return {'state':'HOLD_STOP_NATIVE_EXCEPTION','performed':'UNKNOWN' if latched else False,
                'manual_stop_latched':latched}


def plan_gpu_recovery(snapshot, gpu_id, *, max_attempts=2):
    """Only unexpected failure may auto-recover. Manual STOP never auto-resumes."""
    if not isinstance(snapshot,_Mapping) or snapshot.get('native_verified') is not True:
        return {'state':'HOLD_NATIVE_RECOVERY_INVENTORY','performed':False}
    g=_gpu_entry(snapshot,gpu_id)
    if g is None or g.get('native_owner')!='OneHost':
        return {'state':'HOLD_RECOVERY_OWNER','performed':False}
    if (snapshot.get('stop_active') is not False
            or snapshot.get('manual_stop_latched',{}).get(str(gpu_id)) is not False):
        return {'state':'HOLD_MANUAL_STOP_REQUIRES_EXPLICIT_RESUME','performed':False}
    if (snapshot.get('onehost_gpu_lease',{}).get(str(gpu_id)) is not True
            or snapshot.get('unexpected_owner_process_failure',{}).get(str(gpu_id)) is not True):
        return {'state':'HOLD_NO_OWNED_CRASH_OR_LEASE','performed':False}
    attempts=snapshot.get('restart_attempts',{}).get(str(gpu_id))
    elapsed=snapshot.get('seconds_since_restart',{}).get(str(gpu_id))
    if (type(max_attempts) is not int or not 1<=max_attempts<=2
            or type(attempts) is not int or not 0<=attempts<max_attempts
            or type(elapsed) not in (int,float) or not math.isfinite(elapsed)
            or elapsed<60):
        return {'state':'HOLD_RESTART_BACKOFF_OR_BUDGET','performed':False}
    if gpu_id==0 and snapshot.get('s03_restorable') is not True:
        return {'state':'HOLD_S03_RESTORE_UNVERIFIED','performed':False}
    if gpu_id==1 and (snapshot.get('checkpoint_optimizer_restorable') is not True
                      or snapshot.get('offsite_restore_verified') is not True):
        return {'state':'HOLD_GPU1_OPTIMIZER_RESTORE_UNVERIFIED','performed':False}
    ok,reason=_has_headroom(snapshot,g,AdaptiveTargets())
    if not ok:return {'state':reason,'performed':False}
    return {'state':'OWNER_NATIVE_RECOVERY_ADMITTED','gpu_id':gpu_id,
            'owner_process_only':True,'performed':False,
            'max_attempts':max_attempts,'backoff_seconds':60}


def execute_gpu_recovery(plan, *, authorize, stop_state, restore,
                         start_existing, readback):
    """Use the *existing* OneHost start callback only. Never spawn second daemon."""
    if (not isinstance(plan,_Mapping) or plan.get('state')!='OWNER_NATIVE_RECOVERY_ADMITTED'
            or type(plan.get('gpu_id')) is not int or plan['gpu_id'] not in (0,1)):
        return {'state':'HOLD_RECOVERY_NOT_ADMITTED','performed':False}
    if any(not callable(f) for f in (authorize,stop_state,restore,start_existing,readback)):
        return {'state':'HOLD_RECOVERY_CALLBACKS_MISSING','performed':False}
    try:
        if authorize(plan) is not True or stop_state(plan) is not False:
            return {'state':'HOLD_RECOVERY_OWNER_OR_STOP','performed':False}
        if restore(plan) is not True:
            return {'state':'HOLD_RECOVERY_RESTORE','performed':False}
        if stop_state(plan) is not False:
            return {'state':'HOLD_RECOVERY_STOP_RACE','performed':False}
        if start_existing(plan) is not True:
            return {'state':'HOLD_RECOVERY_START_UNVERIFIED','performed':'UNKNOWN'}
        actual=readback(plan)
        if (not isinstance(actual,_Mapping) or type(actual.get('gpu_id')) is not int
                or actual['gpu_id']!=plan['gpu_id']
                or actual.get('native_owner')!='OneHost'
                or actual.get('owned_process_running') is not True
                or actual.get('manual_stop_latched') is not False
                or actual.get('onehost_gpu_lease') is not True
                or actual.get('stop_active') is not False
                or type(actual.get('pid')) is not int or actual['pid']<=0
                or type(actual.get('start_ticks')) is not int or actual['start_ticks']<=0
                or actual.get('heartbeat_fresh_after_restart') is not True):
            return {'state':'HOLD_RECOVERY_READBACK','performed':'UNKNOWN'}
        # A Supervisor RUNNING flag or stale process snapshot alone cannot
        # prove recovery. Require a native useful-progress receipt after the
        # restart: a successful optimizer update on GPU1, or a completed job
        # on GPU0. Counts must not be bools, strings or cumulative old steps.
        if plan['gpu_id']==1:
            updates=actual.get('new_successful_optimizer_updates_after_restart')
            useful=type(updates) is int and updates>0
        else:
            useful=(actual.get('new_completed_job_after_restart') is True)
        if not useful:
            return {'state':'HOLD_RECOVERY_NO_NEW_USEFUL_PROGRESS','performed':'UNKNOWN'}
        if stop_state(plan) is not False:
            return {'state':'HOLD_RECOVERY_STOP_AFTER_READBACK','performed':'UNKNOWN'}
        return {'state':'NATIVE_OWNER_PROCESS_RECOVERED','gpu_id':plan['gpu_id'],
                'performed':True,'pid':actual['pid'],'start_ticks':actual['start_ticks']}
    except Exception:
        return {'state':'HOLD_RECOVERY_EXCEPTION','performed':'UNKNOWN'}

