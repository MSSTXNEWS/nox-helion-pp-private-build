"""NOX V63: bounded live inventory for installed models, runtimes and services.

No downloads, installations, restarts, memory content or secret exports.
Uses existing V51 authorized Vast SSH and automatic key revocation.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time
_old_api=connection.api
def _delayed_key(method,path,key,data=None):
    r=_old_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(25)
    return r

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,shutil,json,subprocess,importlib.metadata as metadata,hashlib,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_INSTALLATION_INVENTORY_V1')
SERVICES=('nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
          'nox-teacher-serve-t811u','nox-train-worm-t811u')
for name in SERVICES:
    try:
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=8)
        words=p.stdout.strip().split()
        state=words[1] if len(words)>1 else 'UNKNOWN'
        pid=int(words[3].rstrip(',')) if len(words)>3 and words[2]=='pid' and words[3].rstrip(',').isdigit() else None
    except (OSError,subprocess.TimeoutExpired):
        state='UNKNOWN';pid=None
    print('NATIVE_INSTALL_SERVICE='+json.dumps({'service':name,'state':state,'pid':pid},separators=(',',':')))
commands=['python3','hf','huggingface-cli','aria2c','curl','rsync','git','bash','llama-server','nvidia-smi']
print('NATIVE_INSTALL_BINARIES='+json.dumps({x:bool(shutil.which(x)) for x in commands},separators=(',',':')))
libraries=['huggingface_hub','torch','transformers','peft','accelerate','trl','datasets','fastapi','uvicorn']
libs={}
for lib in libraries:
    try:libs[lib]=metadata.version(lib.replace('_','-'))
    except metadata.PackageNotFoundError:
        try:libs[lib]=metadata.version(lib)
        except metadata.PackageNotFoundError:libs[lib]='NOT_FOUND'
print('NATIVE_INSTALL_LIBRARIES='+json.dumps(libs,separators=(',',':')))

roots=[Path('/root/nox/models'),Path('/root/nox/models/teachers'),Path('/root/nox/models/judge')]
seen=set();weights=[]
for root in roots:
    if not root.is_dir():continue
    for path in root.rglob('*'):
        try:
            if not path.is_file():continue
            if path.suffix.lower() not in ('.gguf','.safetensors','.pt','.pth'):continue
            real=str(path.resolve())
            if real in seen:continue
            seen.add(real)
            size=path.stat().st_size
            if size<100_000_000:continue
            if len(weights)<28:
                weights.append({'name':path.name[:80],'size_bytes':size,
                                'active_basename':path.name=='current.gguf',
                                'symlink':path.is_symlink()})
        except (OSError,PermissionError):continue
        if len(seen)>300:break
    if len(seen)>300:break
print('NATIVE_INSTALL_WEIGHT_COUNT='+str(len(seen)))
for item in weights:
    print('NATIVE_INSTALL_WEIGHT='+json.dumps(item,separators=(',',':')))
status_codes={}
for port in (8080,8081,8082,8084,8087,8088,8092,8093,8095,8384):
    url='http://127.0.0.1:'+str(port)+'/health'
    try:
        with urllib.request.urlopen(url,timeout=1.5) as response:code=response.status
    except urllib.error.HTTPError as e:code=e.code
    except (OSError,urllib.error.URLError):code=None
    status_codes[str(port)]=code
print('NATIVE_INSTALL_ENDPOINT_HEALTH='+json.dumps(status_codes,separators=(',',':')))
candidates=[
 Path('/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
 Path('/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
 Path('/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3')
]
result=[]
for p in candidates:
    try:
        if p.is_file() and not p.is_symlink():
            s=p.stat()
            result.append({'basename':p.name,'size_bytes':s.st_size,'mtime_ns':s.st_mtime_ns})
    except OSError:pass
print('NATIVE_INSTALL_S03_CANDIDATES='+json.dumps(result,separators=(',',':')))
try:
    space=shutil.disk_usage('/workspace')
    print('NATIVE_INSTALL_WORKSPACE_DISK='+json.dumps({'total':space.total,'used':space.used,'free':space.free},separators=(',',':')))
except OSError:
    print('NATIVE_INSTALL_WORKSPACE_DISK=HOLD_UNAVAILABLE')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    connection.REMOTE=REMOTE
    connection.api=_delayed_key
    ok=False
    try:ok=connection.probe()
    except Exception as e:
        msg=str(e)
        print("NOX_V63_INSTALL="+msg if msg.startswith("HOLD_") and len(msg)<100 else "NOX_V63_INSTALL=HOLD_NATIVE")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V63_INSTALL=HOLD_KEY_REVOKE")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
