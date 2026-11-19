"""NOX V66: read-only measured cache/offload inventory for no-loss server cleanup.

Reuses temporary scoped SSH from V51. No files deleted, source paths exposed
only as fixed allowlisted labels. Prevents touching model/S03/checkpoint trees.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time

_prior_api=conn.api
def _api_with_delay(method,path,key,data=None):
    response=_prior_api(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):time.sleep(15)
    return response

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,time,json,shutil,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V66_OFFLOAD_SAFE_CACHE_INVENTORY_V1')
root=Path('/root/nox')
CACHE={
    'pip':Path('/root/.cache/pip'),
    'uv':Path('/root/.cache/uv'),
    'torch':Path('/root/.cache/torch'),
    'huggingface_hub':Path('/root/.cache/huggingface'),
    'nox_tmp':root/'tmp',
    'nox_cache':root/'cache',
    'workspace_cache':Path('/workspace/.cache'),
    'root_temp':Path('/tmp'),
    'nox_backup':root/'backup',
    'nox_incoming':root/'incoming_t800u',
    'nox_sources':root/'sources',
    'nox_models':root/'models',
    'nox_checkpoints':root/'checkpoints',
    'nox_memory':root/'memory',
    'nox_learning':Path('/root/nox_learn'),
}
ACTIVE={
   'git':False,'pip':False,'uv':False,'hf':False,'huggingface-cli':False,
   'download':False,'rsync':False,'scp':False,'rclone':False,'tar':False,
   'trainer':False,'checkpoint':False,'python':False,
}
open_fds=set()
for name in os.listdir('/proc'):
    if not name.isdigit():continue
    try:
        p=Path('/proc')/name
        comm=(p/'comm').read_text(errors='replace').strip().lower()
        cmd=(p/'cmdline').read_bytes()[:1200].lower()
        for label in ACTIVE:
            if label in comm or label.encode() in cmd:ACTIVE[label]=True
        fd=p/'fd'
        for f in list(fd.iterdir())[:256]:
            try:
                value=os.readlink(f)
                # Paths remain on the remote host only; do not export.
                open_fds.add(value.removesuffix(' (deleted)'))
            except (OSError,ValueError):pass
    except OSError:pass
print('NATIVE_OFFLOAD_ACTIVE_PROCESSES='+json.dumps(ACTIVE,sort_keys=True,separators=(',',':')))
def scan(folder,cap=50000):
    if not folder.is_dir() or folder.is_symlink():return None
    files=0;bytes_=0;old_bytes=0;open_count=0;largest=0;errors=0
    cutoff=time.time()-7*86400
    for parent,dirs,names in os.walk(folder,followlinks=False):
        dirs[:]=[n for n in dirs if n not in ('.ssh','node_modules','.git')][:200]
        for item in names:
            f=Path(parent)/item
            try:
                meta=f.lstat()
                if not stat.S_ISREG(meta.st_mode):continue
                if f.is_symlink():continue
                files+=1;bytes_+=meta.st_size
                if meta.st_mtime<cutoff:old_bytes+=meta.st_size
                if str(f) in open_fds:open_count+=1
                largest=max(largest,meta.st_size)
            except (OSError,ValueError):errors+=1
            if files>=cap:break
        if files>=cap:break
    return {'bytes':bytes_,'files':files,'stale_7d_bytes':old_bytes,
            'open_fds':open_count,'max_file_bytes':largest,
            'errors':errors,'truncated':files>=cap}
for label,path in CACHE.items():
    stats=scan(path,30000 if label=='huggingface_hub' else 20000)
    print('NATIVE_STORAGE_CLASS='+json.dumps({'label':label,'exists':path.exists(),
      'symlink':path.is_symlink(),'stats':stats},separators=(',',':')))
try:
    st=shutil.disk_usage('/workspace')
    print('NATIVE_WORKSPACE_SPACE='+json.dumps({'total_bytes':st.total,'used_bytes':st.used,
       'free_bytes':st.free},separators=(',',':')))
except OSError: print('NATIVE_WORKSPACE_SPACE=HOLD')
for tool in ('rclone','gsutil','gcloud','ssh','age','tar','rsync'):
    print('NATIVE_TOOL_'+tool.upper()+'='+str(bool(shutil.which(tool))).lower())
print('NATIVE_EXTERNAL_DRIVE_CONFIG_PRESENT='+str(
    Path('/root/.config/rclone/rclone.conf').is_file() or Path('/root/.config/gcloud').is_dir()).lower())
# Don't print secrets or rclone remote names.
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    conn.REMOTE=REMOTE
    conn.api=_api_with_delay
    ok=False
    try:ok=conn.probe()
    except Exception as exc:
        reason=str(exc)
        print('NOX_V66_SCAN='+reason if reason.startswith('HOLD_') and len(reason)<90
              else 'NOX_V66_SCAN=HOLD_NATIVE_SSH')
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:
            print('NOX_V66_SCAN=HOLD_SSH_KEY_REVOKE')
            ok=False
    return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
