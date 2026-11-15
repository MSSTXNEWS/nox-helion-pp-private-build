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
    if snapshot.get('stop_active') is True:
        out['state']='HOLD_OWNER_STOP'
        return out
    oom_delta=snapshot.get('cgroup_oom_kill_delta',0)
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
    after=used-cache-workspace
    # These two lazy budgets share the SAME cgroup, so count both once.
    if after<0 or used+cache+workspace>ceiling:
        out['state']='HOLD_RAM_BUDGET_INCONSISTENT'
        return out
    out.update({'state':'RAM_CACHE_AND_WORKSPACE_READY','cache_bytes':cache,
                'temporary_workspace_bytes':workspace,
                'free_ram_after_budget_bytes':avail-cache-workspace,
                'tmpfs_free_after_budget_bytes':shm-workspace,
                'cgroup_headroom_after_budget_bytes':limit-used-cache-workspace,
                'cgroup_safe_room_after_budget_bytes':ceiling-used-cache-workspace})
    return out
