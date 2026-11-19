"""NOX V68 read-only weights lineage / cleanup admission on the existing Vast host.

No weight modifications, no download, no service restart, no deletion. Prints only
bounded metadata and basename/hash hints. Never interpret matching size as SHA.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_api=ssh.api
def _delay(method,path,key,data=None):
    out=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return out

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,json,hashlib,subprocess,shutil
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V68_WEIGHTS_ADMISSION_READONLY_V1')
ROOT=Path('/root/nox')
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
active=ROOT/'models/current.gguf'
def hint(p):
    return hashlib.sha256(str(p).encode()).hexdigest()[:16]
def report(label,data):
    print(label+'='+json.dumps(data,sort_keys=True,separators=(',',':')))
try:
    state=active.lstat()
    resolved=active.resolve(strict=True)
    if not resolved.is_file():raise RuntimeError()
    st=resolved.stat()
    report('NATIVE_ACTIVE_MODEL',{'present':True,'is_symlink':active.is_symlink(),
      'bytes':st.st_size,'target_basename':resolved.name[:90],
      'target_path_sha_hint':hint(resolved),'mtime_ns':st.st_mtime_ns,
      'sha256_full_verified':False})
except (OSError,RuntimeError):
    report('NATIVE_ACTIVE_MODEL',{'present':False,'sha256_full_verified':False})
for name in ('nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
             'nox-teacher-serve-t811u','nox-train-worm-t811u'):
    try:
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=6)
        words=p.stdout.strip().split()
        result=words[1] if p.returncode==0 and len(words)>1 else 'UNKNOWN'
    except (OSError,subprocess.TimeoutExpired):result='UNKNOWN'
    print('NATIVE_SERVICE='+json.dumps({'service':name,'state':result},separators=(',',':')))
candidates=(ROOT/'models',ROOT/'models/teachers',ROOT/'models/judge',
            ROOT/'checkpoints',ROOT/'training',ROOT/'forge')
observed=set()
weights=[]
suffixes={'.gguf','.safetensors','.pt','.pth','.ckpt'}
for base in candidates:
    if not base.exists() or not base.is_dir() or base.is_symlink():continue
    for root,dirs,files in os.walk(base,followlinks=False):
        depth=len(Path(root).relative_to(base).parts)
        dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink()] if depth<4 else []
        for fn in files:
            path=Path(root)/fn
            try:
                if path.suffix.lower() not in suffixes:continue
                st=path.stat()
                if not path.is_file() or st.st_size<50_000_000:continue
                inode=(st.st_dev,st.st_ino)
                if inode in observed:continue
                observed.add(inode)
                if len(weights)<70:
                    weights.append({'basename':path.name[:90],
                       'bytes':st.st_size,'symlink':path.is_symlink(),
                       'location_hint':hint(path.parent),'suffix':path.suffix.lower(),
                       'is_current_inode':active.exists() and inode==(active.stat().st_dev,active.stat().st_ino),
                       'full_sha_verified':False})
            except (OSError,PermissionError):continue
        if len(observed)>1000:break
    if len(observed)>1000:break
report('NATIVE_WEIGHT_INVENTORY',{'count_sampled':len(observed),'truncated':len(observed)>70,'items':weights[:70]})
disk=shutil.disk_usage('/workspace')
stop=any(Path(x).exists() for x in STOP_PATHS)
report('NATIVE_ADMISSION',{'disk_free_bytes':disk.free,'stop_active':stop,
 'download_new_weights_allowed':disk.free>=20_000_000_000 and not stop,
 'destructive_weight_cleanup_allowed':False,
 'reason':'OFFSITE_FULL_RESTORE_AND_COMPATIBILITY_NOT_VERIFIED',
 'merge_mode':'DISTILLATION_OR_SAME_ARCHITECTURE_VERIFIED_CHECKPOINT_ONLY',
 'complete_model_SHA_verified':False,'full_offsite_restore_verified':False,
 'no_weight_changes':True,'no_training_started':True})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    ssh.REMOTE=REMOTE
    ssh.api=_delay
    ok=False
    try:ok=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V68='+msg if msg.startswith('HOLD_') and len(msg)<100 else 'NOX_V68=HOLD_NATIVE_EXECUTION')
    finally:
        try:
            if not ssh.cleanup():ok=False
        except Exception:
            print('NOX_V68=HOLD_TEMP_KEY_REVOKE')
            ok=False
    return 0 if ok else 2

if __name__=='__main__':
    raise SystemExit(main())
