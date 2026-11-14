"""V66 one-shot deletion ONLY of regenerable pip download cache on live NOX.

Never touches S03, models, checkpoints, HF cache, /tmp, /root/nox, or PC.
Owner authorized server cleanup; native STOP and active pip protections.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_old_api=ssh.api
def _delay_api(method,path,key,data=None):
    result=_old_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,shutil,time,json,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V66_REGENERABLE_PIP_CACHE_PURGE_V1')
CACHE=Path('/root/.cache/pip')
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def report(state,**kw):
    data={'schema':'NOX_V66_PIP_PURGE_RECEIPT_V1','state':state,
          'scope':'ONLY_/root/.cache/pip','model_files_touched':False,
          'memory_files_touched':False,'checkpoint_files_touched':False,
          'hf_cache_touched':False,'tmp_files_touched':False}
    data.update(kw)
    print('NATIVE_PIP_CACHE_PURGE='+json.dumps(data,sort_keys=True,separators=(',',':')))
    print('NATIVE_READ_ONLY_COMPLETE=true')
    raise SystemExit(0)
if any(Path(p).exists() for p in STOP_PATHS):
    report('HOLD_GLOBAL_STOP_SIGNAL',purged=False)
try:
    root=Path('/root')
    base=Path('/root/.cache')
    if (root.is_symlink() or base.is_symlink() or CACHE.is_symlink()
        or not root.is_dir() or not base.is_dir() or not CACHE.is_dir()
        or CACHE.resolve(strict=True)!=CACHE):
        report('HOLD_CACHE_NOT_TRUSTED',purged=False)
    if CACHE.stat().st_uid!=0 or base.stat().st_uid!=0:
        report('HOLD_CACHE_OWNERSHIP',purged=False)
except OSError:
    report('HOLD_CACHE_STAT',purged=False)
busy=[]
open_cache_fds=0
for name in os.listdir('/proc'):
    if not name.isdigit():continue
    p=Path('/proc')/name
    try:
        argv=(p/'cmdline').read_bytes()[:2800].replace(b'\x00',b' ').decode(errors='replace').lower()
        comm=(p/'comm').read_text(errors='replace').strip().lower()
        if any(t in argv for t in ('pip install','pip download','pip cache',
             'pip wheel','uv pip','uv sync','hf download','huggingface-cli download')):
            busy.append('package_worker')
        if comm in ('pip','pip3','uv','hf','huggingface-cli'):
            busy.append('package_cli')
        for fd in list((p/'fd').iterdir())[:180]:
            try:
                value=os.readlink(fd)
                if value.startswith(str(CACHE)+'/'):open_cache_fds+=1
            except (OSError,ValueError):pass
    except (OSError,ValueError):continue
if busy or open_cache_fds:
    report('HOLD_CACHE_BUSY',purged=False,busy_process_classes=len(busy),open_fds=open_cache_fds)
snapshot=[]
for parent,dirs,files in os.walk(CACHE,followlinks=False):
    for d in dirs:
        if (Path(parent)/d).is_symlink():
            report('HOLD_SYMLINK_IN_CACHE',purged=False)
    for name in files:
        p=Path(parent)/name
        try:st=p.lstat()
        except OSError:report('HOLD_CACHE_CHANGED',purged=False)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or p.is_symlink():
            report('HOLD_UNSAFE_CACHE_ENTRY',purged=False)
        snapshot.append((p,st.st_ino,st.st_size))
        if len(snapshot)>30000:report('HOLD_CACHE_TOO_MANY_FILES',purged=False)
size=sum(x[2] for x in snapshot)
if not 10_000_000<=size<=1_100_000_000:
    report('HOLD_CACHE_SIZE_OUTSIDE_GUARD',purged=False,bytes=size)
before=shutil.disk_usage('/workspace').free
for p,inode,bytes_ in snapshot:
    try:
        st=p.lstat()
        if st.st_ino!=inode or st.st_size!=bytes_ or not stat.S_ISREG(st.st_mode):
            report('HOLD_CACHE_CHANGED_MIDWAY',purged=False,deleted_count=0)
    except OSError:
        report('HOLD_CACHE_CHANGED_MIDWAY',purged=False,deleted_count=0)
# Exact allowlist and stable snapshot. Cache is safely regenerable from package sources.
deleted=0
deleted_bytes=0
for p,inode,bytes_ in snapshot:
    try:
        st=p.lstat()
        if (st.st_ino!=inode or st.st_size!=bytes_ or not stat.S_ISREG(st.st_mode)
            or st.st_nlink!=1):
            raise OSError('CHANGED')
        p.unlink()
        deleted+=1
        deleted_bytes+=bytes_
    except OSError:
        report('HOLD_PARTIAL_CACHE_PURGE',purged=False,files_deleted=deleted,deleted_bytes=deleted_bytes)
# Empty directories only beneath exact pip root; leave root itself in place.
for base,dirs,files in os.walk(CACHE,topdown=False,followlinks=False):
    if Path(base)==CACHE:continue
    try:
        if not os.listdir(base):Path(base).rmdir()
    except OSError:pass
after=shutil.disk_usage('/workspace').free
remaining=sum(f.stat().st_size for f in CACHE.rglob('*') if f.is_file() and not f.is_symlink())
result='NATIVE_PIP_CACHE_CLEANED' if remaining==0 and deleted==len(snapshot) else 'HOLD_CACHE_REMAINS'
report(result,purged=(result=='NATIVE_PIP_CACHE_CLEANED'),files_deleted=deleted,
       deleted_bytes=deleted_bytes,remaining_cache_bytes=remaining,
       free_before_bytes=before,free_after_bytes=after,free_delta_bytes=after-before)
PYREMOTE
"""

def main()->int:
    import contextlib,io,json
    ssh.REMOTE=REMOTE
    ssh.api=_delay_api
    console=io.StringIO()
    completed=False
    revoked=False
    try:
        with contextlib.redirect_stdout(console):
            completed=ssh.probe()
    except Exception:
        print('NOX_V66_CLEANUP=HOLD_REMOTE_SSH')
    finally:
        try:
            with contextlib.redirect_stdout(console):
                revoked=ssh.cleanup()
        except Exception:
            print('NOX_V66_CLEANUP=HOLD_EPHEMERAL_KEY')
    receipts=[]
    for line in console.getvalue().splitlines():
        if line.startswith('NATIVE_PIP_CACHE_PURGE=') and len(line)<1250:
            try:
                x=json.loads(line.split('=',1)[1])
                if x.get('schema')=='NOX_V66_PIP_PURGE_RECEIPT_V1':
                    print(line)
                    receipts.append(x)
            except (TypeError,ValueError):pass
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    accepted=(completed and revoked and len(receipts)==1 and
         receipts[0].get('state')=='NATIVE_PIP_CACHE_CLEANED' and receipts[0].get('purged') is True)
    print('NOX_V66_NATIVE_SAFE_CACHE_CLEANUP_VERIFIED='+str(bool(accepted)).lower())
    if not accepted:print('NOX_V66_CLEANUP=HOLD_NOT_FULLY_VERIFIED')
    return 0 if accepted else 2

if __name__=='__main__':
    raise SystemExit(main())
