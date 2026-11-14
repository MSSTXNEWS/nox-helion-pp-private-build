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
