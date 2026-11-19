"""NOX V71 safe physical S03 online backup to RAM (:memory:), no disk mutation.

This is only a native smoke; it does not replace the authenticated installed
S03 service. Canonical SQLite/WAL and all chats remain on persistent storage.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_api=conn.api
def settle(method,path,key,data=None):
    result=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
from pathlib import Path
import sqlite3,os,time
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_S03_RAM_SMOKE_SCHEMA=NOX_V71_S03_ONLINE_RAM_SNAPSHOT_V1')
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
    if line.startswith('MemAvailable:'):
        mem['available']=int(line.split()[1])*1024
if mem.get('available',0)<64*1024**3:
    raise SystemExit('HOLD_RAM_CAPACITY')
dbs=[
 ('SEED','/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
 ('INFINITE','/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
 ('COPY','/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3')
]
for label,path in dbs:
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>80_000_000:
        raise SystemExit('HOLD_S03_SOURCE_'+label)
    src=None;mirror=None
    try:
        src=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=8)
        src.execute('PRAGMA query_only=ON')
        mirror=sqlite3.connect(':memory:')
        begin=time.perf_counter()
        src.backup(mirror,pages=256,sleep=0.02)
        checked=mirror.execute('PRAGMA quick_check').fetchone()
        if checked is None or checked[0]!='ok':
            raise SystemExit('HOLD_S03_RAM_INTEGRITY_'+label)
        count=mirror.execute('SELECT count(*) FROM sqlite_master WHERE type="table"').fetchone()[0]
        pages=mirror.execute('PRAGMA page_count').fetchone()[0]
        size=mirror.execute('PRAGMA page_size').fetchone()[0]
        if count<1 or pages<1:
            raise SystemExit('HOLD_S03_RAM_SCHEMA_'+label)
        print('NATIVE_S03_RAM_'+label+'_TABLES='+str(count))
        print('NATIVE_S03_RAM_'+label+'_BYTES='+str(pages*size))
        print('NATIVE_S03_RAM_'+label+'_SNAPSHOT_MS='+str(round((time.perf_counter()-begin)*1000,1)))
        print('NATIVE_S03_RAM_'+label+'_QUICK_CHECK=PASS')
    finally:
        if mirror is not None:mirror.close()
        if src is not None:src.close()
print('NATIVE_S03_CANONICAL_DATABASES_UNTOUCHED=true')
print('NATIVE_S03_RAM_REPLICA_VOLATILE_DISCARDED=true')
print('NATIVE_S03_RAM_SMOKE_NOT_LIVE_ONEHOST_BINDING=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    conn.REMOTE=REMOTE;conn.api=settle;ok=False
    try:ok=conn.probe()
    except Exception as e:
        val=str(e)
        print('NOX_V71_RAM_SMOKE='+val if val.startswith('HOLD_') and len(val)<100 else 'NOX_V71_RAM_SMOKE=HOLD_NATIVE')
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
