"""NOX V71: read-only RAM/tmpfs/S03 readiness on existing Vast via V51."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_api=conn.api
def _with_ssh_settle(method,path,key,data=None):
    res=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(13)
    return res

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,json,sqlite3
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_RAM_AUDIT_SCHEMA=NOX_V71_RAM_S03_BASELINE_V1')
m={}
try:
    for line in Path('/proc/meminfo').read_text().splitlines():
        if ':' not in line:continue
        a,b=line.split(':',1)
        if a in ('MemTotal','MemAvailable','MemFree','Cached','SwapTotal','SwapFree','Shmem'):
            m[a]=int(b.strip().split()[0])*1024
    for key in ('MemTotal','MemAvailable','MemFree','Cached','SwapTotal','SwapFree','Shmem'):
        print('NATIVE_RAM_'+key.upper()+'_BYTES='+str(m.get(key,'HOLD')))
except (OSError,ValueError):print('NATIVE_RAM_MEMINFO=HOLD')
# Container memory is authoritative, NOT the much larger host MemAvailable.
# Read only, no path dumps, no S03 data, never infer that cache is already active.
try:
    cgroup=Path('/sys/fs/cgroup')
    maxs=(cgroup/'memory.max').read_text().strip()
    curs=(cgroup/'memory.current').read_text().strip()
    if not maxs.isdecimal() or not curs.isdecimal():
        raise ValueError('cgroup missing or unlimited')
    maxb,current=int(maxs),int(curs)
    if maxb<=0 or current<0 or current>maxb:
        raise ValueError('invalid cgroup')
    print('NATIVE_RAM_CGROUP_MAX_BYTES='+str(maxb))
    print('NATIVE_RAM_CGROUP_CURRENT_BYTES='+str(current))
    vals={}
    for line in (cgroup/'memory.events').read_text().splitlines():
        parts=line.split()
        if len(parts)==2 and parts[0] in ('oom','oom_kill','high'):
            vals[parts[0]]=int(parts[1])
    print('NATIVE_RAM_CGROUP_OOM_KILL_COUNT='+str(vals.get('oom_kill','HOLD')))
    print('NATIVE_RAM_CGROUP_HIGH_EVENT_COUNT='+str(vals.get('high','HOLD')))
    high=(cgroup/'memory.high').read_text().strip()
    print('NATIVE_RAM_CGROUP_MEMORY_HIGH_BYTES='+str(int(high) if high.isdecimal() else 'NONE'))
except (OSError,ValueError):
    print('NATIVE_RAM_CGROUP_VERIFIED=false')
else:
    print('NATIVE_RAM_CGROUP_VERIFIED=true')
for name,location in [('dev_shm','/dev/shm'),('run_shm','/run/shm'),('workspace','/workspace')]:
    p=Path(location)
    try:
        st=os.statvfs(p)
        print('NATIVE_RAM_'+name.upper()+'_FREE_BYTES='+str(st.f_bavail*st.f_frsize))
        print('NATIVE_RAM_'+name.upper()+'_TOTAL_BYTES='+str(st.f_blocks*st.f_frsize))
        print('NATIVE_RAM_'+name.upper()+'_IS_MOUNT='+str(os.path.ismount(p)).lower())
    except OSError:
        print('NATIVE_RAM_'+name.upper()+'_STATUS=HOLD')
for name,p in (('S03_SEED','/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
               ('S03_INFINITE','/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
               ('S03_COPY','/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3')):
    try:
        s=Path(p).stat()
        print('NATIVE_RAM_'+name+'_BYTES='+str(s.st_size))
    except OSError:print('NATIVE_RAM_'+name+'_BYTES=HOLD')
# Bounded per-process memory by known service basenames; no cmdline or secrets logged.
try:
    for pid in ('198698','56525'):
        p=Path('/proc')/pid
        if not p.is_dir():continue
        label='PROXY' if pid=='198698' else 'MAIN_MODEL'
        data={}
        for line in (p/'status').read_text().splitlines():
            if line.startswith(('VmRSS:','VmSize:','RssAnon:','RssFile:')):
                k,x=line.split(':',1)
                data[k]=int(x.strip().split()[0])*1024
        print('NATIVE_RAM_'+label+'_STATS='+json.dumps(data,sort_keys=True))
except (OSError,ValueError):print('NATIVE_RAM_PROCESS_STATUS=HOLD')
print('NATIVE_RAM_SOURCE_DATA_UNCHANGED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__=="__main__":
    conn.REMOTE=REMOTE
    conn.api=_with_ssh_settle
    ok=False
    try:ok=conn.probe()
    except Exception as e:
        val=str(e)
        print("NOX_V71_RAM_PROBE="+val if val.startswith("HOLD_") and len(val)<100 else "NOX_V71_RAM_PROBE=HOLD_NATIVE")
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
