"""NOX V79: read-only live OneHost teacher/S03 readiness.
Uses the existing ephemeral SSH bridge and always revokes its temporary key.
No remote command execution from model text, no model downloads, no service restarts.
"""
from __future__ import annotations
import contextlib
import io
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json, os, stat, subprocess, urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V79_TEACHER_S03_READINESS_V1')
def emit(name,obj): print(name+'='+json.dumps(obj,separators=(',',':'),sort_keys=True))
stop=any(Path(p).exists() for p in
 ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
emit('NATIVE_STOP',{'active':stop})
for service in ('nox-proxy','nox-teacher-serve-t811u','nox-agent-tuner-t858u'):
 try:
  p=subprocess.run(['supervisorctl','status',service],text=True,capture_output=True,timeout=7)
  fields=p.stdout.split()
  emit('NATIVE_SERVICE',{'name':service,'state':fields[1] if p.returncode==0 and len(fields)>1 else 'UNKNOWN'})
 except Exception: emit('NATIVE_SERVICE',{'name':service,'state':'UNKNOWN'})
for port in (8080,8081):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
   emit('NATIVE_HEALTH',{'port':port,'code':r.status})
 except Exception:emit('NATIVE_HEALTH',{'port':port,'code':None})
# Identify native interface signatures WITHOUT reading secrets, raw chats, or model weights.
for path in (Path('/root/nox/scripts/chat_proxy.py'),Path('/root/nox/scripts/train_worm_t811u.py')):
 try:
  if not path.is_file() or path.is_symlink() or path.stat().st_size>120000:continue
  import ast,hashlib
  raw=path.read_bytes();tree=ast.parse(raw)
  names=sorted({n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))})
  keywords=('s03','memory','rag','model','teacher','proxy','stream','chat','stop','persist')
  selected=[n for n in names if any(w in n.lower() for w in keywords)]
  emit('NATIVE_CODE',{'name':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'callbacks':selected[:65]})
 except Exception:emit('NATIVE_CODE',{'name':path.name,'state':'HOLD_READ'})
# Never treat a process/port as authenticated transport or S03 durability proof.
print('NATIVE_TEACHER_PRIVATE_INFERENCE_BOUND=false')
print('NATIVE_S03_WRITE_READBACK_VERIFIED=false')
print('NATIVE_WEIGHT_TRAINING_STARTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    output = io.StringIO()
    ok = False
    try:
        conn.REMOTE = REMOTE
        with contextlib.redirect_stdout(output):
            ok = bool(conn.probe())
    except Exception as exc:
        msg = str(exc)
        print('NOX_V79_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<90 else 'NATIVE_CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if conn.cleanup() is not True:
                    ok = False
        except Exception:
            ok = False
            print('NOX_V79_HOLD=SSH_CLEANUP')
    result = output.getvalue()
    for line in result.splitlines():
        if line.startswith(('NATIVE_','TEMP_SSH_CLEANUP=')) and len(line)<2500:
            print(line)
    verified = ok and 'NATIVE_READ_ONLY_COMPLETE=true' in result and 'NATIVE_AUDIT_SCHEMA=NOX_V79_TEACHER_S03_READINESS_V1' in result
    print('NOX_V79_READ_ONLY_PROBE_VERIFIED='+str(verified).lower())
    return 0 if verified else 2

if __name__=='__main__':
    raise SystemExit(main())
