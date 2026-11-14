"""V85: source-pinned STAGING ONLY of V84 on existing Vast NOX.
No chat restart, no S03 writes, no model reload, no training claim.
"""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
from pathlib import Path
import shlex
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

MODULE=Path("nox_runpod/teacher_mesh/v84/memory_native.py")
def main():
    original=MODULE.read_bytes()
    compile(original,str(MODULE),"exec")
    expected=hashlib.sha256(original).hexdigest()
    payload=base64.b64encode(original).decode()
    remote_script=r"""
import base64, hashlib, os, pathlib, stat, json
from pathlib import Path
TARGET=Path('/root/nox/staging/nox_v84_memory_native.py')
EXPECTED=__SHA__
RAW=base64.b64decode(__BODY__)
def emit(state,**kwargs):
 print('NATIVE_V85='+json.dumps({'state':state,**kwargs},sort_keys=True,separators=(',',':')))
try:
 stop=any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
 if stop:raise RuntimeError('HOLD_STOP')
 if hashlib.sha256(RAW).hexdigest()!=EXPECTED:raise RuntimeError('HOLD_SOURCE_SHA')
 if TARGET.parent.is_symlink():raise RuntimeError('HOLD_DIRECTORY_SYMLINK')
 TARGET.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 if TARGET.exists() and TARGET.is_symlink():raise RuntimeError('HOLD_STAGE_SYMLINK')
 current_sha=hashlib.sha256(TARGET.read_bytes()).hexdigest() if TARGET.exists() else None
 OLD='731331ecaeeddd15d28de8eff931cbad6b51485c7c1e32e44a23a15bdb744c04'
 if current_sha==EXPECTED:
  emit('ALREADY_STAGED_VERIFIED',sha256=EXPECTED)
 elif current_sha is None or current_sha==OLD:
  if current_sha==OLD:
   backup=TARGET.with_name('nox_v84_memory_native.pre_acl_fix.py')
   if backup.exists():
    if backup.is_symlink() or hashlib.sha256(backup.read_bytes()).hexdigest()!=OLD:
     raise RuntimeError('HOLD_BACKUP_CONFLICT')
   else:
    fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:
     f.write(TARGET.read_bytes());f.flush();os.fsync(f.fileno())
    if hashlib.sha256(backup.read_bytes()).hexdigest()!=OLD:raise RuntimeError('HOLD_BACKUP_VERIFY')
  temp=TARGET.with_name('.nox_v84_stage.tmp')
  if temp.exists():raise RuntimeError('HOLD_TEMP_EXISTS')
  fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  try:
   with os.fdopen(fd,'wb') as f:
    f.write(RAW);f.flush();os.fsync(f.fileno())
   compile(temp.read_bytes(),str(TARGET),'exec')
   os.replace(temp,TARGET)
  finally:
   temp.unlink(missing_ok=True)
  if hashlib.sha256(TARGET.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('HOLD_STAGE_READBACK')
  emit('STAGED_SOURCE_SHA_VERIFIED',sha256=EXPECTED,replaced_known_version=current_sha==OLD)
 else:
  raise RuntimeError('HOLD_EXISTING_STAGE_CONFLICT')
 # staging only; no import into active OneHost.
 print('NATIVE_S03_DATABASE_MUTATED=false')
 print('NATIVE_CHAT_RESTARTED=false')
 print('NATIVE_MODEL_WEIGHTS_CHANGED=false')
 print('NATIVE_TRAINING_STARTED=false')
except Exception as exc:
 emit(str(exc) if str(exc).startswith('HOLD_') else 'HOLD_STAGE_ERROR')
print('NATIVE_READ_ONLY_COMPLETE=true')
"""
    script=remote_script.replace("__SHA__",repr(expected)).replace("__BODY__",repr(payload))
    conn.REMOTE="set -euo pipefail\npython3 - <<'PYREMOTE'\nprint('NOX_NATIVE_V51_SSH_EXECUTED=true')\n"+script+"\nPYREMOTE\n"
    api=conn.api
    def settled(method,path,key,data=None):
        result=api(method,path,key,data)
        if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
        return result
    conn.api=settled
    output=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(output):ok=conn.probe()
    except Exception as exc:
        print("V85_HOLD="+(str(exc)[:90] if str(exc).startswith('HOLD_') else 'NATIVE_CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if conn.cleanup() is not True:ok=False
        except Exception:ok=False
    for line in output.getvalue().splitlines():
        if line.startswith(('NATIVE_V85=','NATIVE_S03_','NATIVE_CHAT_','NATIVE_MODEL_','NATIVE_TRAINING_','TEMP_SSH_CLEANUP=')):
            print(line[:700])
    passed=ok and any('"state":"STAGED_SOURCE_SHA_VERIFIED"' in line or '"state":"ALREADY_STAGED_VERIFIED"' in line for line in output.getvalue().splitlines())
    print('NOX_V85_STAGING_VERIFIED='+str(bool(passed)).lower())
    return 0 if passed else 2

if __name__=='__main__':raise SystemExit(main())
