"""NOX PRIME RAM resource brain (pure, OneHost-owned).

Keep S03 canonical on persistent SQLite/WAL. Only verified scoped read-through
cache, temporary processing and disposable indexes may use RAM or /dev/shm.
All budgets are based on live native MemAvailable + tmpfs free, not installed RAM.
No huge up-front allocation, memory-service fork, mount change or file deletion.
"""
from __future__ import annotations
from collections.abc import Mapping

GIB=1024**3
MIB=1024**2
RAM_RESERVE=32*GIB
SHM_RESERVE=4*GIB
MAX_S03_CACHE=256*MIB
MAX_RAM_WORKSPACE=16*GIB


def plan_ram(snapshot:Mapping)->dict:
    out={'schema':'NOX_PRIME_RAM_PLAN_V1','state':'HOLD_NATIVE_RAM_TELEMETRY',
         'performed':False,'s03_canonical':'PERSISTENT_SQLITE_WAL',
         's03_cache_location':'RAM_OF_EXISTING_ONEHOST_PROCESS',
         'tmp_location':'/dev/shm/nox-prime',
         'memory_services_restarted':False,'new_memory_server':False,
         'cache_bytes':0,'temporary_workspace_bytes':0,
         'warm_cache_requires_native_revision':True}
    if not isinstance(snapshot,Mapping):
        return out
    avail=snapshot.get('ram_available_bytes')
    shm=snapshot.get('shm_free_bytes')
    if any(type(x) is not int or x < 0 for x in (avail,shm)):
        return out
    if snapshot.get('native_ram_verified') is not True:
        return out
    # A RAM mirror is safe only if the installed owner has authoritative ACL and
    # S03 revision/invalidation callbacks. No unsafe unscoped shared cache.
    revision_verified=snapshot.get('s03_native_revision_verified') is True
    free_for_ephemeral=max(0,avail-RAM_RESERVE)
    cache=min(MAX_S03_CACHE,free_for_ephemeral//32)
    work=min(MAX_RAM_WORKSPACE,free_for_ephemeral//4,max(0,shm-SHM_RESERVE))
    if cache < 8*MIB:
        out['state']='HOLD_RAM_CACHE_HEADROOM'
        return out
    if not revision_verified:
        out['state']='RAM_CAPACITY_READY_S03_CACHE_HOLD_REVISION'
        out['temporary_workspace_bytes']=work
        return out
    out.update({'state':'RAM_CACHE_AND_WORKSPACE_READY','cache_bytes':cache,
                'temporary_workspace_bytes':work,
                'free_ram_after_budget_bytes':avail-cache-work,
                'tmpfs_free_after_budget_bytes':shm-work,
                'allocation_mode':'LAZY_ON_USE_ONLY'})
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
    cap=snapshot.get('cgroup_max_bytes')
    current=snapshot.get('cgroup_current_bytes')
    available=snapshot.get('ram_available_bytes')
    if (any(type(v) is not int or v<0 for v in (cap,current,available))
            or cap<=0 or current>=cap):
        out['state']='HOLD_CGROUP_OR_RAM_SENSOR'
        return out
    # No promise to fill all RAM: use 85% cgroup utilization cap plus a
    # hard reserve. Pages are reclaimed automatically on memory pressure.
    headroom=min(int(cap*WEIGHT_WARM_CGROUP_TARGET)-current,
                 cap-current-WEIGHT_WARM_RESERVE_BYTES,
                 available-WEIGHT_WARM_RESERVE_BYTES)
    warm=min(size,WEIGHT_WARM_MAX_BYTES,max(0,headroom))
    out.update({'cgroup_max_bytes':cap,'cgroup_current_bytes':current,
                'headroom_after_budget_bytes':cap-current-warm,
                'warm_bytes_budget':warm})
    if warm<64*MIB:
        out['state']='HOLD_RAM_HEADROOM_FOR_CHAT'
        return out
    out['state']='READY_FOR_EXISTING_V95_V99_OWNER_PAGECACHE_WARMUP'
    out['next']='NATIVE_ONESHOT_WARM_WITH_STOP_CHAT_IOPREEMPT_AND_CGROUP_READBACK'
    return out
