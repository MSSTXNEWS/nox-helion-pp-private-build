"""V63: verify actual service stability and service-specific Python environments.

Read-only native V51 SSH. Inspect no user data, tokens, optimizer state or
command arguments; avoid false claims based on system Python alone.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time

_origin=connection.api
def _delay(method,path,key,data=None):
    value=_origin(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(25)
    return value

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,shutil,shlex,configparser,subprocess,time,json,importlib.metadata as md
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_RUNTIME_DEPENDENCY_GATE_V1')
targets=['nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
         'nox-teacher-serve-t811u','nox-train-worm-t811u']
files=[
 '/etc/supervisor/conf.d/nox-t855u.conf',
 '/etc/supervisor/conf.d/nox-t802u.conf',
 '/etc/supervisor/conf.d/nox-t811u.conf',
]
def service(name):
    try:
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=9)
        col=p.stdout.strip().split()
        return {'status':col[1] if len(col)>1 else 'UNKNOWN',
                'pid':int(col[3].rstrip(',')) if len(col)>3 and col[2]=='pid' and col[3].rstrip(',').isdigit() else None}
    except (OSError,subprocess.TimeoutExpired):return {'status':'UNKNOWN','pid':None}
def config(name):
    for f in files:
        ini=configparser.ConfigParser(interpolation=None,strict=False)
        try:ini.read(f)
        except (OSError,configparser.Error):continue
        sec='program:'+name
        if ini.has_section(sec):return dict(ini.items(sec))
    return {}
def python_for(name):
    opts=config(name)
    try:args=shlex.split(opts.get('command',''))
    except ValueError:return None
    if not args:return None
    exe=args[0]
    if not Path(exe).is_absolute():exe=shutil.which(exe)
    if exe and Path(exe).is_file() and Path(exe).name.startswith('python'):
        return exe
    return None
packages=('huggingface-hub','torch','transformers','peft','accelerate','trl','datasets')
pycmd=python_for('nox-train-worm-t811u')
versions={}
if pycmd:
    expression="import importlib.metadata as m,json;names="+repr(packages)+";d={};\nfor name in names:\n try:d[name]=m.version(name)\n except m.PackageNotFoundError:d[name]='NOT_FOUND'\nprint(json.dumps(d))"
    try:
        p=subprocess.run([pycmd,'-c',expression],capture_output=True,text=True,timeout=10)
        if p.returncode==0:versions=json.loads(p.stdout[:5000])
    except (OSError,subprocess.TimeoutExpired,ValueError):pass
print('NATIVE_TRAINER_PYTHON_EXACT_EXISTS='+str(bool(pycmd)).lower())
print('NATIVE_TRAINER_DEPS='+json.dumps(versions,separators=(',',':')))
for delay in (0,8):
    if delay:time.sleep(delay)
    sample={name:service(name) for name in targets}
    print('NATIVE_SUPERVISOR_STABILITY_'+str(delay)+'S='+json.dumps(sample,separators=(',',':')))
cli_candidates=(
 '/root/.local/bin/hf','/usr/local/bin/hf',
 '/root/nox/.venv/bin/hf','/root/nox/venv/bin/hf',
 '/root/nox/env/bin/hf','/opt/venv/bin/hf'
)
seen=[Path(p) for p in cli_candidates if Path(p).is_file()]
print('NATIVE_HF_CLI_CANDIDATE_COUNT='+str(len(seen)))
server_bins=(
 '/root/nox/bin/llama-server',
 '/root/nox/llama.cpp/build/bin/llama-server',
 '/root/nox/program/bin/llama-server',
 '/usr/local/bin/llama-server',
 '/opt/llama.cpp/build/bin/llama-server'
)
print('NATIVE_LLAMA_EXECUTABLE_CANDIDATES='+str(sum(Path(p).is_file() for p in server_bins)))
try:
    disk=shutil.disk_usage('/workspace').free
except OSError:disk=None
print('NATIVE_WORKSPACE_FREE_BYTES='+str(disk))
print('NATIVE_TRAIN_WORM_ADMISSION='+('HOLD_DISK_RESERVE' if disk is None or disk<20_000_000_000 else 'NEEDS_NATIVE_BACKUP_OPTIMIZER_PRECHECK'))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    connection.REMOTE=REMOTE
    connection.api=_delay
    good=False
    try:good=connection.probe()
    except Exception as e:
        msg=str(e)
        print("NOX_V63_RUNTIME="+msg if msg.startswith("HOLD_") and len(msg)<90 else "NOX_V63_RUNTIME=HOLD_NATIVE")
    finally:
        try:
            if not connection.cleanup():good=False
        except Exception:
            print("NOX_V63_RUNTIME=HOLD_KEY")
            good=False
    return 0 if good else 2

if __name__=="__main__":raise SystemExit(main())
