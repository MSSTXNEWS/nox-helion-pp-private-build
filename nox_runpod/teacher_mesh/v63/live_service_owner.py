"""NOX V64: read-only attribution of active chat HTTP listener to supervisor unit."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import re,subprocess,os
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
try:
    out=subprocess.run(['ss','-H','-ltnp'],capture_output=True,text=True,timeout=7)
    rows=out.stdout.splitlines()
except (OSError,subprocess.TimeoutExpired):rows=[]
seen=set()
for port in (8080,8081,8095):
    for line in rows:
        m=re.search(r':'+str(port)+r'\s',line)
        if not m:continue
        p=re.search(r'pid=(\d+)',line)
        if not p:continue
        pid=int(p.group(1))
        if (port,pid) in seen:continue
        seen.add((port,pid))
        print('NATIVE_LISTENER_'+str(port)+'_PID='+str(pid))
        for index in range(4):
            try:
                raw=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
                argv=[v.decode('utf-8','replace') for v in raw if v]
                cmd=' '.join(argv)[:3000].lower()
                tokens=('uvicorn','gunicorn','agent_loop','fastapi','python','nox','proxy','http','8080','8095')
                flags=[x for x in tokens if x in cmd]
                print('NATIVE_PORT_'+str(port)+'_PROC'+str(index)+'_FLAGS='+','.join(flags))
                status=(Path('/proc')/str(pid)/'status').read_text()
                parent=re.search(r'(?m)^PPid:\s+(\d+)',status)
                ppid=int(parent.group(1)) if parent else 0
                print('NATIVE_PORT_'+str(port)+'_PROC'+str(index)+'_PID='+str(pid))
                if ppid==0 or ppid==1:break
                pid=ppid
            except OSError:break
try:
    s=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=7)
    if s.returncode==0:
        for line in s.stdout.splitlines():
            m=re.match(r'^([A-Za-z0-9_.:@-]{1,90})\s+(RUNNING|STARTING|BACKOFF|STOPPED)\s+pid\s+(\d+)',line)
            if m:
                name,state,pid=m.groups()
                if 'nox' in name.lower() or 'agent' in name.lower():
                    print('NATIVE_SERVICE_'+name+'='+state+':'+pid)
except (OSError,subprocess.TimeoutExpired):pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as e:
        v=str(e)
        print('NATIVE_OWNER_PROBE='+v if v.startswith('HOLD_') else 'NATIVE_OWNER_PROBE=HOLD')
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
