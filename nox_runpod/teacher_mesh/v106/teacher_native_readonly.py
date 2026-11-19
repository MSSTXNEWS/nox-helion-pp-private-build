"""V106: read-only native teacher service and model readiness.
No prompts, downloads, tokens, passwords or S03 records leave the server.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,os,re,subprocess,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V106_EXISTING_TEACHER_RUNTIME_READINESS_V1')
def emit(k,value):
 s=json.dumps(value,sort_keys=True,separators=(',',':'))
 if len(s)<1200:print('NATIVE_V106_'+k+'='+s)
stop=any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
for service in ('nox-proxy','nox-teacher-serve-t811u','nox-agent-tuner-t858u'):
 try:
  x=subprocess.run(['supervisorctl','status',service],capture_output=True,text=True,timeout=6)
  w=x.stdout.strip().split()
  pid=int(w[3].strip(',')) if len(w)>3 and w[2]=='pid' and w[3].strip(',').isdigit() else None
  emit('SERVICE',{'name':service,'state':w[1] if len(w)>1 and x.returncode==0 else 'UNKNOWN','pid_present':pid is not None})
  if pid is None:continue
  paths=[Path('/proc')/str(pid)]
  for depth in range(3):
   sub=[]
   for root in paths:
    try:
     for entry in root.parent.iterdir():
      if not entry.name.isdigit():continue
      stat=(entry/'status').read_text(errors='replace')
      m=re.search(r'^PPid:\s*(\d+)',stat,re.M)
      if m and m.group(1)==root.name:sub.append(entry)
    except Exception:pass
   paths+=sub[:12]
   if not sub:break
  for node in paths[:15]:
   try:
    args=[x.decode('utf8','replace') for x in (node/'cmdline').read_bytes().split(b'\0') if x]
    model=[]
    ports=[]
    scripts=[]
    for i,a in enumerate(args):
     if a in ('--model','-m','--model-path') and i+1<len(args):
      model.append(Path(args[i+1]).name[:75])
     if a in ('--port','-p') and i+1<len(args) and args[i+1].isdigit():
      ports.append(int(args[i+1]))
     if a.endswith(('.py','.sh')):scripts.append(Path(a).name[:70])
    if model or ports or scripts:
     emit('PROCESS',{'service':service,'script_basenames':scripts[:3],
      'model_basenames':model[:3],'port_numbers':ports[:3]})
   except Exception:pass
 except Exception as e:emit('SERVICE',{'name':service,'state':'UNKNOWN','error_type':type(e).__name__})
for port in (8080,8081,8082,8084,8090,8091,8092,8096,8110,8111,8112,8120):
 result={}
 for route in ('/health','/v1/models'):
  try:
   req=urllib.request.Request(f'http://127.0.0.1:{port}{route}',method='GET')
   with urllib.request.urlopen(req,timeout=1) as r:
    raw=r.read(8000)
    result[route]={'http':r.status,'is_json':(r.headers.get('content-type','').startswith('application/json'))}
    if route=='/v1/models' and result[route]['is_json']:
     data=json.loads(raw)
     if isinstance(data,dict):
      entries=data.get('data') or []
      result[route]['model_count']=len(entries) if isinstance(entries,list) else None
      result[route]['model_basenames']=[Path(str(x.get('id') or '')).name[:70] for x in entries[:7] if isinstance(x,dict)] if isinstance(entries,list) else []
  except Exception:pass
 if result:emit('PORT',{'port':port,'routes':result})
emit('READINESS',{'stop_active':stop,'internet_teacher_bridge_live_bound':False,
'private_external_prompt_sent':False,'native_teacher_model_loaded_proven':False,
'source_model_discovery_only':True,'weights_changed':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();okay=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=old(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):okay=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V106_HOLD='+(v if v.startswith('HOLD_') and len(v)<90 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V106_','TEMP_SSH_CLEANUP=')):
   print(line[:1250]);lines.append(line)
 passed=bool(okay and any(x.startswith('NATIVE_V106_READINESS=') for x in lines) and
             'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V106_EXISTING_TEACHER_AUDIT_VERIFIED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
