"""Read-only inventory of installed NOX dependency capabilities and model artifacts.

Uses proven V51 temporary SSH transport; no package installation, downloads,
model load, services restart, DB changes or secret export.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time

_prior_api=ssh.api
def _api_with_propagation(method,path,key,data=None):
    r=_prior_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,shutil,json,subprocess,hashlib
from pathlib import Path
from importlib import metadata
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_DEPENDENCY_ACCEPTANCE_V1')
commands=('hf','huggingface-cli','aria2c','curl','wget','rsync','llama-server',
          'nvidia-smi','supervisorctl','python','python3','git','git-lfs','ffmpeg')
present={name:bool(shutil.which(name)) for name in commands}
print('NATIVE_COMMAND_AVAILABILITY='+json.dumps(present,separators=(',',':')))

packages=('huggingface-hub','torch','transformers','accelerate','peft','datasets','trl','safetensors','llama-cpp-python')
versions={}
for name in packages:
    try:
        v=metadata.version(name)
        versions[name]=v[:40]
    except metadata.PackageNotFoundError:
        versions[name]=None
print('NATIVE_PYTHON_PACKAGE_VERSIONS='+json.dumps(versions,separators=(',',':')))

paths={
 'student_main':'/root/nox/models/current.gguf',
 'student_s03':'/root/nox/memory/infinite/nox_infinite_memory.sqlite3',
 'frozen_chat':'/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/chat.html',
 'frozen_resonance':'/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/resonance.html',
 'main_serve_script':'/root/nox/scripts/teacher_serve_t811u.sh',
 'download_script':'/root/nox/scripts/download_t802u.sh',
 'tuner_script':'/root/nox/scripts/nox_agent_tuner_t858u.py',
 'train_worm':'/root/nox/scripts/train_worm_t811u.py',
 'onehost_bridge_v49':'/root/nox/nox_runpod/teacher_mesh/v49/onehost_bridge.py',
}
for label,p in paths.items():
    obj=Path(p)
    try:
        if not obj.is_file() or obj.is_symlink():
            print('NATIVE_FILE='+json.dumps({'label':label,'exists':False},separators=(',',':')))
            continue
        size=obj.stat().st_size
        sha=None
        if label in ('frozen_chat','frozen_resonance','tuner_script','download_script') and size<=3000000:
            sha=hashlib.sha256(obj.read_bytes()).hexdigest()
        print('NATIVE_FILE='+json.dumps({'label':label,'exists':True,'size_bytes':size,'sha256':sha},separators=(',',':')))
    except OSError:
        print('NATIVE_FILE='+json.dumps({'label':label,'exists':False,'error':'FILE_UNAVAILABLE'},separators=(',',':')))

try:
    free=shutil.disk_usage('/workspace').free
except OSError:free=None
print('NATIVE_DISK_FREE_BYTES='+str(free))
print('NATIVE_RECOMMENDED_RESERVE_GB=20')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    ssh.REMOTE=REMOTE
    ssh.api=_api_with_propagation
    ok=False
    try: ok=ssh.probe()
    except Exception as e:
        s=str(e)
        print("NOX_V63_PACKAGE="+s if s.startswith("HOLD_") and len(s)<90 else "NOX_V63_PACKAGE=HOLD_NATIVE")
    finally:
        try:
            if not ssh.cleanup():ok=False
        except Exception:
            print("NOX_V63_PACKAGE=HOLD_KEY_REVOCATION")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":
    raise SystemExit(main())
