"""NOX E2: live agent_loop process ownership and route checks; no mutations."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_old=conn.api
def slow_attach(method,path,key,data=None):
    result=_old(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(13)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,ast,subprocess,stat
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_DIAGNOSTIC_SCHEMA=NOX_E2_CHAT_AGENT_PROCESS_BINDINGS_V1')
marks=('agent_loop.py','nox-chat','nox_owner','nox-agent','uvicorn','gunicorn','nox_chat')
pids={}
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        raw=(p/'cmdline').read_bytes()[:3000].decode(errors='replace').lower()
        comm=(p/'comm').read_text().strip()
    except OSError:continue
    matches=[mark for mark in marks if mark.lower() in raw]
    if not matches:continue
    if len(pids)>70:break
    pid=int(p.name)
    pids[pid]=matches
    print('NATIVE_AGENT_PROCESS='+str(pid)+':'+','.join(matches)+':'+re.sub('[^a-zA-Z0-9_-]','',comm[:35]))
try:
    x=subprocess.run(['ss','-H','-ltnp'],capture_output=True,text=True,timeout=6)
    print('NATIVE_AGENT_SS_RC='+str(x.returncode))
    if x.returncode==0:
        for line in x.stdout.splitlines():
            hit=re.search(r'pid=([0-9]+)',line)
            if hit and int(hit.group(1)) in pids:
                port=re.search(r':([0-9]{2,5})\s',line)
                if port:
                    print('NATIVE_AGENT_LISTENER='+hit.group(1)+':'+port.group(1))
except (OSError,subprocess.TimeoutExpired):
    print('NATIVE_AGENT_SS=HOLD')
f=Path('/root/nox/scripts/agent_loop.py')
if f.is_file() and f.stat().st_size<240000:
    try:
        t=ast.parse(f.read_text(encoding='utf-8',errors='replace'))
        s=set()
        for n in ast.walk(t):
            if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('/'):
                if re.fullmatch(r'/[A-Za-z0-9_/{}/.-]{1,110}',n.value) and not n.value.startswith(('/root/','/proc/','/tmp/')):
                    s.add(n.value)
        print('NATIVE_AGENT_PATH_CONSTANTS='+','.join(sorted(s)[:35]))
    except (SyntaxError,OSError):
        print('NATIVE_AGENT_PATH_CONSTANTS=HOLD')
else:print('NATIVE_AGENT_SOURCE=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    conn.REMOTE=REMOTE;conn.api=slow_attach
    good=False
    try:good=conn.probe()
    except Exception as e:
        v=str(e);print('NOX_E2_AGENT_ROUTE='+v if v.startswith('HOLD_') and len(v)<100 else 'NOX_E2_AGENT_ROUTE=HOLD')
    finally:
        try:
            if not conn.cleanup():good=False
        except Exception:good=False
    raise SystemExit(0 if good else 2)
