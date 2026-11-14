"""NOX V63: one exact, bounded recovery of existing CPU-only agent tuner.

Does not touch the other four services. No replacement backend, model loading,
trainer resume, downloads, cleanup, or driver/service mass restart.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time

_original_api=connection.api
def _delayed_key_api(method,path,key,data=None):
    result=_original_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,configparser,hashlib,re,subprocess,shlex,os,time,shutil,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_AGENT_TUNER_RECOVERY_V1')
TARGET='nox-agent-tuner-t858u'
CONFIG=Path('/etc/supervisor/conf.d/nox-t855u.conf')
SOURCE_SHA='77f01625f1a05425080808f9ce377fb4e4253f45d3ce19892e80aaceebf4c9eb'
CONFIG_SHA='f9ec50e6feb5b39307666b109623234624c30e5c3dd8ec496d7f5d51a69f41b5'
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
# This tuner may run only if it cannot directly invoke GPU trainers, downloads,
# host drivers, service restarts, or destructive cleanup.
RISK=r'train_worm|torchrun|accelerate\s+launch|huggingface-cli\s+download|hf\s+download|supervisorctl\s+(?:restart|stop)|\brm\s+-rf\b|\bkill\s+-9\b|subprocess\.Popen'
def emit(data):
    print('NATIVE_TUNER_RECOVERY='+json.dumps(data,sort_keys=True,separators=(',',':')))
def status():
    p=subprocess.run(['supervisorctl','status',TARGET],capture_output=True,text=True,timeout=10)
    line=p.stdout.strip().splitlines()[0] if p.stdout.strip() else ''
    parts=line.split()
    state=parts[1] if len(parts)>=2 else 'UNKNOWN'
    pid=int(parts[3].rstrip(',')) if len(parts)>3 and parts[2]=='pid' and parts[3].rstrip(',').isdigit() else None
    return {'state':state,'pid':pid,'exit_code':p.returncode}
def gpu():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],
                         capture_output=True,text=True,timeout=8)
        if p.returncode==0:
            return [int(v.strip()) for v in p.stdout.splitlines()[:2] if v.strip().isdigit()]
    except (OSError,subprocess.TimeoutExpired):pass
    return []
def hold(reason,pre=None):
    emit({'state':reason,'service':TARGET,'before':pre,'started':False,
          'restarted_other_services':False,'downloaded_weights':False})
    print('NATIVE_READ_ONLY_COMPLETE=true')
    raise SystemExit(0)
if not CONFIG.is_file() or CONFIG.is_symlink():
    hold('HOLD_CONFIG_NOT_FOUND')
config_bytes=CONFIG.read_bytes()
if hashlib.sha256(config_bytes).hexdigest()!=CONFIG_SHA:
    hold('HOLD_CONFIG_SHA_CHANGED')
conf=configparser.ConfigParser(interpolation=None,strict=False)
conf.read(str(CONFIG))
if not conf.has_section('program:'+TARGET):
    hold('HOLD_CONFIG_PROGRAM_MISSING')
opts=dict(conf.items('program:'+TARGET))
try:argv=shlex.split(opts.get('command',''))
except ValueError:hold('HOLD_COMMAND_PARSE')
sources=[x for x in argv[1:10] if x.lower().endswith('.py') and not x.startswith('-')]
if len(sources)!=1:hold('HOLD_SCRIPT_AMBIGUOUS')
script=Path(sources[0])
if not script.is_absolute() and opts.get('directory'):
    script=Path(opts['directory'])/script
if script.is_symlink() or not script.is_file() or script.stat().st_size>800000:
    hold('HOLD_SCRIPT_NOT_TRUSTED')
source=script.read_bytes()
if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:
    hold('HOLD_SCRIPT_SHA_CHANGED')
text=source.decode('utf-8',errors='replace')
try:tree=ast.parse(text)
except SyntaxError:hold('HOLD_SCRIPT_SYNTAX')
imports=set()
for node in ast.walk(tree):
    if isinstance(node,ast.Import):
        imports.update(a.name.split('.')[0] for a in node.names)
    elif isinstance(node,ast.ImportFrom) and node.module:
        imports.add(node.module.split('.')[0])
if imports.intersection({'torch','transformers','peft','deepspeed','accelerate'}):
    hold('HOLD_GPU_TRAINER_IMPORT')
if re.search(RISK,text,re.I):
    hold('HOLD_TUNER_MUTATION_RISK')
if opts.get('autostart','').lower()!='true' or opts.get('autorestart','').lower()!='true':
    hold('HOLD_NOT_EXPECTED_DAEMON')
if any(Path(p).exists() for p in STOP_PATHS):
    hold('HOLD_GLOBAL_STOP_SIGNAL')
try:
    disk=shutil.disk_usage('/workspace').free
except OSError:hold('HOLD_DISK_UNAVAILABLE')
# Lower than checkpoint reserve (20GB), but tuner is CPU and must not download
# or train weights; preserve at least 16GB for existing processes.
if disk<16_000_000_000:hold('HOLD_DISK_BELOW_CPU_SAFE_FLOOR')
first=status()
if first['state']=='RUNNING':
    emit({'state':'ALREADY_RUNNING','service':TARGET,'pid':first['pid'],
          'started':False,'source_sha256':SOURCE_SHA})
    print('NATIVE_READ_ONLY_COMPLETE=true')
    raise SystemExit(0)
if first['state'] not in ('STOPPED','EXITED'):
    hold('HOLD_UNEXPECTED_INITIAL_STATE',first['state'])
before_gpu=gpu()
if len(before_gpu)!=2:hold('HOLD_GPU_TELEMETRY_MISSING')
if any(Path(p).exists() for p in STOP_PATHS):
    hold('HOLD_STOP_CHANGED')
# Single targeted mutation: supervisor start, never restart, never all.
try:
    action=subprocess.run(['supervisorctl','start',TARGET],capture_output=True,
                          text=True,timeout=20)
except (OSError,subprocess.TimeoutExpired):
    hold('HOLD_SUPERVISOR_START_TIMEOUT',first['state'])
time.sleep(6)
after=status()
after_gpu=gpu()
source_ok=hashlib.sha256(script.read_bytes()).hexdigest()==SOURCE_SHA
config_ok=hashlib.sha256(CONFIG.read_bytes()).hexdigest()==CONFIG_SHA
stop_active=any(Path(p).exists() for p in STOP_PATHS)
gpu_delta=[a-b for a,b in zip(after_gpu,before_gpu)] if len(after_gpu)==2 else None
stable=after['state']=='RUNNING' and after['pid'] and source_ok and config_ok and not stop_active
if gpu_delta is None or any(v>1200 for v in gpu_delta):stable=False
rolled_back=False
if not stable and after['state']=='RUNNING' and after['pid']:
    try:
        rollback=subprocess.run(['supervisorctl','stop',TARGET],capture_output=True,
                            text=True,timeout=15)
        rolled_back=rollback.returncode==0 and status()['state'] in ('STOPPED','EXITED')
    except (OSError,subprocess.TimeoutExpired):rolled_back=False
state='NATIVE_TUNER_RUNNING_VERIFIED' if stable else 'HOLD_TUNER_START_NOT_ACCEPTED'
emit({'service':TARGET,'state':state,'source_sha256':SOURCE_SHA,
      'before_state':first['state'],'after_state':after['state'],
      'action_exit':action.returncode,'pid':after['pid'] if stable else None,
      'config_sha_match':config_ok,'script_sha_match':source_ok,
      'gpu_delta_mb':gpu_delta,'stop_active':stop_active,
      'rollback_verified':rolled_back if not stable else None,
      'started':bool(stable),'other_services_touched':False,
      'weights_or_checkpoints_changed_by_script':'NOT_MEASURED'})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    import contextlib
    import io
    import json
    connection.REMOTE=REMOTE
    connection.api=_delayed_key_api
    transcript=io.StringIO()
    completed=False
    cleanup_ok=False
    try:
        with contextlib.redirect_stdout(transcript):
            completed=connection.probe()
    except Exception as e:
        msg=str(e)
        print("NOX_V63_TUNER="+msg if msg.startswith("HOLD_") and len(msg)<100 else "NOX_V63_TUNER=HOLD_NATIVE_EXECUTION")
    finally:
        try:
            with contextlib.redirect_stdout(transcript):
                cleanup_ok=connection.cleanup()
        except Exception:
            print("NOX_V63_TUNER=HOLD_SSH_KEY_CLEANUP")
            cleanup_ok=False
    seen=[]
    for line in transcript.getvalue().splitlines():
        if line.startswith("NATIVE_TUNER_RECOVERY=") and len(line)<800:
            try:
                value=json.loads(line.split("=",1)[1])
                if isinstance(value,dict) and value.get("service")=="nox-agent-tuner-t858u":
                    seen.append(value)
                    print(line)
            except (ValueError,TypeError):pass
        elif line.startswith(("TEMP_SSH_CLEANUP=","SSH_ROUTE=")) and len(line)<130:
            print(line)
    states=[x.get("state") for x in seen]
    accepted=completed is True and cleanup_ok is True and len(states)==1 and states[0] in (
        "NATIVE_TUNER_RUNNING_VERIFIED","ALREADY_RUNNING")
    print("NOX_V63_TUNER_NATIVE_ACCEPTED="+str(accepted).lower())
    if not accepted:
        print("NOX_V63_TUNER=HOLD_NOT_ACCEPTED_OR_UNVERIFIED")
    return 0 if accepted else 2

if __name__=="__main__":raise SystemExit(main())
