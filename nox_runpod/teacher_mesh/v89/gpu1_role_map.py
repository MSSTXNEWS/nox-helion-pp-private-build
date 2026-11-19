"""NOX V89 GPU1 process parent and training-admission read-only owner map."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
p=ssh.api
def delay(method,path,key,data=None):
 x=p(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import subprocess,re,json,os,shlex
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V89_GPU1_SERVICE_OWNER_MAP_V1')
def emit(v):print('NATIVE_GPU_PROC_OWNER='+json.dumps(v,sort_keys=True,separators=(',',':')))
try:
 p=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=9)
 rows=[x.split(',') for x in p.stdout.splitlines() if x.count(',')==2]
except Exception:rows=[]
def proc(pid):
 try:
  raw=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
  args=[x.decode('utf8','replace') for x in raw if x]
  st=(Path('/proc')/str(pid)/'status').read_text(errors='replace')
  parent=re.search(r'^PPid:\s*(\d+)',st,re.M)
  model=None
  for i,a in enumerate(args):
   if a in ('-m','--model','--model-path') and i+1<len(args):
    model=Path(args[i+1]).name[:90]
  return {'pid':pid,'ppid':int(parent.group(1)) if parent else None,
          'comm':(Path('/proc')/str(pid)/'comm').read_text().strip()[:40],
          'script':next((Path(a).name[:80] for a in args if a.endswith(('.py','.sh'))),None),
          'model_basename':model}
 except Exception:return None
try:
 v=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=9)
 supervisors={}
 for line in v.stdout.splitlines():
  m=re.search(r'^(\S+)\s+RUNNING\s+pid\s+(\d+)',line)
  if m:supervisors[int(m.group(2))]=m.group(1)
except Exception:supervisors={}
for row in rows[:35]:
 try:
  gpu,pid,mem=row
  pid=int(pid.strip());m=re.search(r'[0-9]+',mem);mem=int(m.group()) if m else 0
  pp=proc(pid)
  if pp is None:continue
  pp['gpu_uuid_hint']=gpu.strip()[-12:]
  pp['vram_mib']=mem
  ancestors=[];n=pid
  for depth in range(7):
   if n in supervisors:
    ancestors.append(supervisors[n]);break
   ancestor=proc(n)
   if not ancestor or not ancestor['ppid'] or ancestor['ppid']<=1:break
   n=ancestor['ppid']
   if n in supervisors:ancestors.append(supervisors[n]);break
  pp['supervisor_owner']=ancestors[:2]
  emit(pp)
 except Exception:continue
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V89='+v if v.startswith('HOLD_') else 'NOX_V89=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
