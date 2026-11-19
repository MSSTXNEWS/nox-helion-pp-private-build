"""NOX PRIME cgroup-aware RAM resource admission for the EXISTING OneHost.

Host MemAvailable is NOT the container memory budget (Vast native #60509551
reported ~404GB host RAM but ~194GB cgroup limit). All proposals are lazy;
nothing is downloaded, written to SSD, allocated, or launched here.
Canonical S03 remains in persistent SQLite/WAL with scoped revisioned RAM cache.
"""
from __future__ import annotations
from collections.abc import Mapping

GIB=1024**3
MIB=1024**2
RAM_RESERVE=32*GIB
SHM_RESERVE=4*GIB
CGROUP_RESERVE=12*GIB
MAX_CGROUP_USED_PERCENT=85
MAX_S03_CACHE=256*MIB
MAX_RAM_WORKSPACE=16*GIB


def plan_ram(snapshot:Mapping)->dict:
    out={'schema':'NOX_PRIME_RAM_PLAN_V2_CGROUP_SAFE',
         'state':'HOLD_NATIVE_RAM_TELEMETRY','performed':False,
         's03_canonical':'PERSISTENT_SQLITE_WAL',
         's03_cache_location':'RAM_OF_EXISTING_ONEHOST_PROCESS',
         'tmp_location':'/dev/shm/nox-prime',
         'memory_services_restarted':False,'new_memory_server':False,
         'cache_bytes':0,'temporary_workspace_bytes':0,
         'warm_cache_requires_native_revision':True,
         'cgroup_limit_verified':False,'allocation_mode':'LAZY_ON_USE_ONLY',
         'disk_model_cache_created':False,'model_weights_downloaded':False}
    if not isinstance(snapshot,Mapping):
        return out
    avail=snapshot.get('ram_available_bytes')
    shm=snapshot.get('shm_free_bytes')
    if any(type(x) is not int or x < 0 for x in (avail,shm)):
        return out
    if snapshot.get('native_ram_verified') is not True:
        return out
    # Host /proc/meminfo can exceed cgroup by hundreds of GB: fail CLOSED.
    if snapshot.get('native_cgroup_verified') is not True:
        out['state']='HOLD_NATIVE_CGROUP_TELEMETRY'
        return out
    limit=snapshot.get('cgroup_memory_max_bytes')
    used=snapshot.get('cgroup_memory_current_bytes')
    if (type(limit) is not int or type(used) is not int or
        limit<=0 or used<0 or used>limit):
        out['state']='HOLD_INVALID_CGROUP_LIMIT_OR_USAGE'
        return out
    out['cgroup_limit_verified']=True
    out['cgroup_max_bytes']=limit
    out['cgroup_current_bytes']=used
    out['cgroup_actual_headroom_bytes']=limit-used
    # Admission is forbidden unless native STOP was explicitly checked and
    # found inactive; an absent sensor is not proof that STOP is disabled.
    if snapshot.get('stop_active') is not False:
        out['state']=('HOLD_OWNER_STOP' if snapshot.get('stop_active') is True
                      else 'HOLD_STOP_NOT_VERIFIED')
        return out
    # memory.events provides cumulative counters. Only a verified delta from
    # native observations can attest no *new* OOM; defaulting missing to zero
    # silently admitted allocations on an uninspected host.
    if snapshot.get('native_cgroup_oom_delta_verified') is not True:
        out['state']='HOLD_UNVERIFIED_OOM_DELTA'
        return out
    oom_delta=snapshot.get('cgroup_oom_kill_delta')
    if type(oom_delta) is not int or oom_delta<0:
        out['state']='HOLD_UNVERIFIED_OOM_DELTA'
        return out
    if oom_delta>0:
        out['state']='HOLD_RECENT_CGROUP_OOM'
        return out
    high=snapshot.get('cgroup_memory_high_bytes')
    if high is not None and (type(high) is not int or high<=0):
        out['state']='HOLD_INVALID_CGROUP_MEMORY_HIGH'
        return out
    # Advisory 85% ceiling, never a target to fill; high limit may be stricter.
    ceiling=min(limit*MAX_CGROUP_USED_PERCENT//100,limit-CGROUP_RESERVE)
    if high is not None:
        ceiling=min(ceiling,high)
    out['cgroup_safe_ceiling_bytes']=max(0,ceiling)
    free_for_ephemeral=min(max(0,avail-RAM_RESERVE),max(0,ceiling-used))
    cache=min(MAX_S03_CACHE,free_for_ephemeral//32)
    workspace=min(MAX_RAM_WORKSPACE,free_for_ephemeral//4,
                  max(0,shm-SHM_RESERVE))
    if cache < 8*MIB:
        out['state']='HOLD_RAM_CACHE_HEADROOM'
        return out
    # Without authoritative S03 ACL+revision callbacks, no shared S03 cache.
    if snapshot.get('s03_native_revision_verified') is not True:
        out['state']='RAM_CAPACITY_READY_S03_CACHE_HOLD_REVISION'
        out['temporary_workspace_bytes']=workspace
        return out
    # These two lazy budgets share the SAME cgroup, so count both once.
    if used+cache+workspace>ceiling:
        out['state']='HOLD_RAM_BUDGET_INCONSISTENT'
        return out
    out.update({'state':'RAM_CACHE_AND_WORKSPACE_READY','cache_bytes':cache,
                'temporary_workspace_bytes':workspace,
                'free_ram_after_budget_bytes':avail-cache-workspace,
                'tmpfs_free_after_budget_bytes':shm-workspace,
                'cgroup_headroom_after_budget_bytes':limit-used-cache-workspace,
                'cgroup_safe_room_after_budget_bytes':ceiling-used-cache-workspace})
    return out


# This extends the EXISTING RAM planner. It does not download, allocate or
# activate a second model. Physical warm-up uses only native V95/V99 owner
# callbacks and must be independently measured.
import re as _re
WEIGHT_WARM_MAX_BYTES=2*GIB
WEIGHT_WARM_RESERVE_BYTES=12*GIB
WEIGHT_WARM_CGROUP_TARGET=0.85
_SHA256=_re.compile(r"^[0-9a-f]{64}$")


def plan_warm_weight(snapshot:Mapping,candidate:Mapping)->dict:
    """P0: bounded, reclaimable OS page cache on existing OneHost only.

    LOCAL_VERIFIED -> read-only page-cache candidate with NO new SSD files.
    REMOTE_VERIFIED -> HOLD until a verified, streaming RAM-only loader exists.
    Neither mode writes S03 or implies an active GPU model or optimizer step.
    """
    out={'schema':'NOX_PRIME_WARM_WEIGHT_POLICY_V1',
         'state':'HOLD_NATIVE_WEIGHT_CACHE_ADMISSION','performed':False,
         'new_disk_bytes':0,'diskless_model_loader_running':False,
         'canonical_weights_delete_allowed':False,
         'new_backend':False,'new_model_instance':False,
         's03_canonical':'PERSISTENT_SQLITE_WAL','ram_kind':'RECLAIMABLE_OS_PAGE_CACHE',
         'gpu0_chat_priority':'P0','gpu1_new_trainer_allowed':False,
         'warm_bytes_budget':0,'physical_warmup_verified':False}
    if not isinstance(snapshot,Mapping) or not isinstance(candidate,Mapping):
        return out
    if (snapshot.get('native_ram_verified') is not True
            or snapshot.get('owner_authorized') is not True):
        out['state']='HOLD_OWNER_NATIVE_RAM_EVIDENCE'
        return out
    if snapshot.get('stop_active') is not False:
        out['state']='HOLD_STOP_OR_UNKNOWN'
        return out
    if snapshot.get('chat_gpu0_healthy') is not True:
        out['state']='HOLD_CHAT_HEALTH'
        return out
    # Page-cache warmup competes with the canonical S03 WAL/retrieval IO.
    # An unhealthy or unverified original memory service always wins.
    if snapshot.get('s03_native_healthy') is not True:
        out['state']='HOLD_S03_HEALTH_NOT_VERIFIED'
        return out
    # The original V71 RAM planner already fails closed on cgroup trust/OOM;
    # warming an OS page cache must obey those same admission conditions.
    if snapshot.get('native_cgroup_verified') is not True:
        out['state']='HOLD_NATIVE_CGROUP_TELEMETRY'
        return out
    if snapshot.get('native_cgroup_oom_delta_verified') is not True:
        out['state']='HOLD_UNVERIFIED_OOM_DELTA'
        return out
    oom_delta=snapshot.get('cgroup_oom_kill_delta')
    if type(oom_delta) is not int or oom_delta<0:
        out['state']='HOLD_UNVERIFIED_OOM_DELTA'
        return out
    if oom_delta>0:
        out['state']='HOLD_RECENT_CGROUP_OOM'
        return out
    # First-token responsiveness always wins over prefetch.
    if (snapshot.get('chat_state')!='idle'
            or type(snapshot.get('prime_active_streams')) is not int
            or snapshot.get('prime_active_streams')!=0
            or type(snapshot.get('seconds_since_chat_activity')) not in (int,float)
            or not 45<=snapshot['seconds_since_chat_activity']<=1e9):
        out['state']='HOLD_CHAT_ACTIVE_OR_RECENT'
        return out
    if (candidate.get('license_verified') is not True
            or candidate.get('sha_verified') is not True
            or not isinstance(candidate.get('sha256'),str)
            or not _SHA256.fullmatch(candidate['sha256'])
            or candidate.get('kind') not in ('GGUF','HF_SAFETENSORS','MODULE')):
        out['state']='HOLD_UNVERIFIED_WEIGHT_SOURCE'
        return out
    if candidate.get('source_state')=='REMOTE_VERIFIED':
        out['state']='HOLD_RAM_ONLY_REMOTE_LOADER_NOT_NATIVE_BOUND'
        out['next']='AUTHORIZE_STREAMING_VERIFIED_REMOTE_TO_TMPFS_WITHOUT_SSD'
        return out
    if candidate.get('source_state')!='LOCAL_VERIFIED':
        out['state']='HOLD_SOURCE_NOT_LOCAL'
        return out
    if candidate.get('in_use') is not False or candidate.get('source_file_open') is not False:
        out['state']='HOLD_WEIGHT_FILE_IN_USE_OR_UNKNOWN'
        return out
    size=candidate.get('size_bytes')
    if type(size) is not int or size<64*MIB:
        out['state']='HOLD_MODEL_SIZE_NOT_MEASURED'
        return out
    # Native V71 uses cgroup_memory_*; allow old keys, but fail closed if
    # competing samples disagree. The larger host memory is never a fallback.
    cap=snapshot.get('cgroup_memory_max_bytes',snapshot.get('cgroup_max_bytes'))
    current=snapshot.get('cgroup_memory_current_bytes',snapshot.get('cgroup_current_bytes'))
    available=snapshot.get('ram_available_bytes')
    if (('cgroup_memory_max_bytes' in snapshot and 'cgroup_max_bytes' in snapshot
             and snapshot['cgroup_memory_max_bytes']!=snapshot['cgroup_max_bytes'])
            or ('cgroup_memory_current_bytes' in snapshot and 'cgroup_current_bytes' in snapshot
             and snapshot['cgroup_memory_current_bytes']!=snapshot['cgroup_current_bytes'])
            or any(type(v) is not int or v<0 for v in (cap,current,available))
            or cap<=0 or current>=cap):
        out['state']='HOLD_CGROUP_OR_RAM_SENSOR'
        return out
    high=snapshot.get('cgroup_memory_high_bytes')
    if high is not None and (type(high) is not int or high<=0):
        out['state']='HOLD_CGROUP_MEMORY_HIGH_SENSOR'
        return out
    # Reclaimable page cache still charges cgroup.current. Respect memory.high
    # when it is tighter than both the 85% ceiling and mandatory chat reserve.
    ceiling=min(int(cap*WEIGHT_WARM_CGROUP_TARGET),cap-WEIGHT_WARM_RESERVE_BYTES)
    if high is not None:
        ceiling=min(ceiling,high)
    headroom=min(ceiling-current,
                 available-WEIGHT_WARM_RESERVE_BYTES)
    warm=min(size,WEIGHT_WARM_MAX_BYTES,max(0,headroom))
    out.update({'cgroup_max_bytes':cap,'cgroup_current_bytes':current})
    # Fail closed: a HOLD must never advertise bytes that a native consumer
    # could mistakenly interpret as authorization to warm the page cache.
    if warm<64*MIB:
        out['state']='HOLD_RAM_HEADROOM_FOR_CHAT'
        out['headroom_after_budget_bytes']=cap-current
        return out
    out['headroom_after_budget_bytes']=cap-current-warm
    out['warm_bytes_budget']=warm
    out['state']='READY_FOR_EXISTING_V95_V99_OWNER_PAGECACHE_WARMUP'
    out['next']='NATIVE_ONESHOT_WARM_WITH_STOP_CHAT_IOPREEMPT_AND_CGROUP_READBACK'
    return out
