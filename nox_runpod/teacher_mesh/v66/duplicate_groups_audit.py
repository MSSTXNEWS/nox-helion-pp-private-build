"""V66 second stage: classify probable duplicate model groups, no deletion.

Reuses previous V62 size+three-window fingerprints. Returns only group sizes,
file class and whether any candidate is in use/open or checkpoint-related.
Never logs paths and never performs full hash or mutation.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_old_api=conn.api
def _delay(method,path,key,data=None):
    x=_old_api(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(15)
    return x

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
from pathlib import Path
from collections import defaultdict
import os,hashlib,json,stat,subprocess
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V66_PROBABLE_DUPLICATE_CATEGORIES_V1')
roots=[Path('/root/nox'),Path('/root/nox_learn')]
allowed={'.gguf','.safetensors','.bin','.pth','.pt'}
minsize=64*1024*1024
items=[]
inode_seen=set()
for root in roots:
    if not root.is_dir():continue
    for parent,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ('.git','.ssh','.cache','venv','.venv','node_modules','__pycache__')][:140]
        for name in files:
            p=Path(parent)/name
            if p.suffix.lower() not in allowed:continue
            try:
                info=p.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size<minsize:continue
            except OSError:continue
            ino=(info.st_dev,info.st_ino)
            if ino in inode_seen:continue
            inode_seen.add(ino)
            items.append((p,info))
            if len(items)>700:raise SystemExit('HOLD_FILE_COUNT')
opened=set()
for entry in os.listdir('/proc'):
    if not entry.isdigit():continue
    try:
        for fd in list((Path('/proc')/entry/'fd').iterdir())[:300]:
            try:opened.add(os.readlink(fd).removesuffix(' (deleted)'))
            except (OSError,ValueError):pass
    except OSError:pass
groups=defaultdict(list)
for p,info in items:
    h=hashlib.sha256()
    try:
        with p.open('rb') as f:
            for offset in (0,max(0,info.st_size//2-32768),max(0,info.st_size-65536)):
                f.seek(offset)
                if len(chunk:=f.read(65536))!=65536:raise OSError('SHORT_READ')
                h.update(chunk)
    except OSError:raise SystemExit('HOLD_FINGERPRINT_READ')
    groups[(info.st_size,h.hexdigest())].append((p,info))
candidates=[(size,entries) for (size,h),entries in groups.items() if len(entries)>1]
print('NATIVE_DUPLICATE_PROBABLE_GROUPS='+str(len(candidates)))
for idx,(size,entries) in enumerate(sorted(candidates,key=lambda item:-item[0]),1):
    suffixes=sorted(set(p.suffix.lower() for p,_ in entries))
    backup=any(any(x in str(p).lower() for x in ('backup','checkpoint','optim','train','adapter')) for p,_ in entries)
    in_use=sum(str(p) in opened for p,_ in entries)
    active_main=any(str(p)==str(Path('/root/nox/models/current.gguf').resolve(strict=False)) for p,_ in entries)
    all_models=all(str(p).startswith('/root/nox/models/') for p,_ in entries)
    print('NATIVE_DUPLICATE_GROUP='+json.dumps({
      'group':idx,'file_count':len(entries),'each_bytes':size,'potential_reclaim_bytes':size*(len(entries)-1),
      'suffixes':suffixes,'checkpoint_or_training_path':backup,'open_file_count':in_use,
      'current_main_model_member':active_main,'all_under_model_directory':all_models,
      'same_inode':False,'verified_full_sha':False
    },separators=(',',':')))
print('NATIVE_DUPLICATE_NOTE=SMALL_SAMPLES_ONLY_NOT_SAFE_TO_DELETE')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    conn.REMOTE=REMOTE
    conn.api=_delay
    ok=False
    try:ok=conn.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V66_GROUPS='+msg if msg.startswith('HOLD_') and len(msg)<100 else 'NOX_V66_GROUPS=HOLD_NATIVE')
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:
            print('NOX_V66_GROUPS=HOLD_KEY_REVOKE')
            ok=False
    return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
