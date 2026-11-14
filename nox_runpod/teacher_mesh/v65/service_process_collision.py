"""V65: read-only Supervisor/child-process collision audit for NOX 5 services."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_orig_api=conn.api
def _delayed_api(method,path,key,data=None):
    result=_orig_api(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(24)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,json,re,shutil,socket
from pathlib import Path
SERVICES={
 'nox-agent-tuner-t858u':'nox_agent_tuner_t858u.py',
 'nox-downloads-t802u':'download_t802u.sh',
 'nox-teacher-bringup':'teacher_bringup_t802u.sh',
 'nox-teacher-serve-t811u':'teacher_serve_t811u.sh',
 'nox-train-worm-t811u':'train_worm_t811u.py',
}
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V65_SERVICE_PROCESS_COLLISION_V1')

def process(pid):
    try:
        p=Path('/proc')/str(pid)
        raw=(p/'stat').read_text().split()
        comm=(p/'comm').read_text().strip()
        return {'pid':int(pid),'ppid':int(raw[3]),'comm':comm[:40]}
    except (OSError,ValueError,IndexError):return None

def snapshot():
    p=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=10)
    states={}
    for line in p.stdout.splitlines()[:320]:
        cols=line.strip().split()
        if len(cols)>1 and cols[0] in SERVICES:
            state=cols[1]
            pid=int(cols[3].rstrip(',')) if len(cols)>3 and cols[2]=='pid' and cols[3].rstrip(',').isdigit() else None
            states[cols[0]]={'supervisor_state':state,'supervisor_pid':pid}
    associations={k:[] for k in SERVICES}
    for item in os.listdir('/proc'):
        if not item.isdigit():continue
        try:args=(Path('/proc')/item/'cmdline').read_bytes()[:2200]
        except OSError:continue
        for key,script in SERVICES.items():
            if script.encode() in args or key.encode() in args:
                info=process(item)
                if info is not None and len(associations[key])<6:
                    associations[key].append(info)
    return states,associations
s1,a1=snapshot()
time.sleep(4)
s2,a2=snapshot()
for service in SERVICES:
    print('NATIVE_SERVICE_LIFECYCLE='+json.dumps({
      'service':service,
      'status_before':s1.get(service),
      'status_after':s2.get(service),
      'linked_processes_before':a1[service],
      'linked_processes_after':a2[service],
      'stable_supervisor_state':s1.get(service)==s2.get(service),
      'stable_associated_pids':sorted(x['pid'] for x in a1[service])==sorted(x['pid'] for x in a2[service]),
     },separators=(',',':')))
health={}
from urllib import request,error
for port in (8080,8081,8084,8087,8088,8095):
    try:
        with request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=1.5) as r:
            health[str(port)]=r.status
    except error.HTTPError as e:health[str(port)]=e.code
    except (OSError,error.URLError):health[str(port)]=None
print('NATIVE_SERVICE_HTTP_HEALTH='+json.dumps(health,separators=(',',':')))
try:free=shutil.disk_usage('/workspace').free
except OSError:free=None
print('NATIVE_DISK_FREE_BYTES='+str(free))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    conn.REMOTE=REMOTE;conn.api=_delayed_api
    ok=False
    try:ok=conn.probe()
    except Exception as e:
        val=str(e)
        print('NOX_V65_COLLISION='+val if val.startswith('HOLD_') and len(val)<90 else 'NOX_V65_COLLISION=HOLD_NATIVE')
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:
            print('NOX_V65_COLLISION=HOLD_KEY_CLEANUP')
            ok=False
    return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
