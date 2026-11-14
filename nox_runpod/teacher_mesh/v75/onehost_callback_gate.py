"""NOX V75: native chat callback and service-reload readiness; no mutation."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,subprocess,json,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V75_ONEHOST_CALLBACK_GATE_V1')
root=Path('/workspace/nox_mega_stage_verified/v38')
mod=['synaptic_brain.py','durable_runtime.py','native_bridge_v38.py']
for name in mod:
 try:
  source=(root/name).read_bytes()
  compile(source,name,'exec')
  print('NATIVE_STAGE_MODULE='+json.dumps({'name':name,'syntax':'PASS','bytes':len(source)},separators=(',',':')))
 except Exception:
  print('NATIVE_STAGE_MODULE='+json.dumps({'name':name,'syntax':'HOLD'},separators=(',',':')))
try:
 ps=subprocess.run(['ps','-eo','pid=,ppid=,comm=,args='],capture_output=True,text=True,timeout=7)
 proxies=[]
 for row in ps.stdout.splitlines():
  if 'chat_proxy.py' not in row:continue
  fields=row.split(maxsplit=3)
  if len(fields)<3:continue
  if fields[2] not in ('python','python3','uvicorn'):continue
  try:pid,ppid=int(fields[0]),int(fields[1])
  except ValueError:continue
  proxies.append({'pid':pid,'ppid':ppid,'comm':fields[2]})
 print('NATIVE_CHAT_PROXY_PROCESSES='+json.dumps(proxies[:8],separators=(',',':')))
except Exception:
 proxies=[]
 print('NATIVE_CHAT_PROXY_PROCESSES=HOLD')
try:
 x=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=10)
 owner=[]
 for line in x.stdout.splitlines()[:160]:
  f=line.split()
  if len(f)<2:continue
  for p in proxies:
   if ('pid '+str(p['pid'])+',') in line:
    owner.append({'service':f[0][:80],'state':f[1],'pid':p['pid']})
 print('NATIVE_PROXY_SUPERVISOR_OWNER='+json.dumps(owner,separators=(',',':')))
except Exception:print('NATIVE_PROXY_SUPERVISOR_OWNER=HOLD')
for port in (8080,8081):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as rsp:
   print('NATIVE_HEALTH_'+str(port)+'='+str(rsp.status))
 except Exception:print('NATIVE_HEALTH_'+str(port)+'=HOLD')
for file in (Path('/root/nox/chat_proxy.py'),Path('/root/nox/agent_loop.py')):
 if not file.is_file():continue
 try:
  src=file.read_bytes()
  if len(src)>600000:continue
  tree=ast.parse(src)
  names=sorted({n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
    and any(word in n.name.lower() for word in ('s03','memory','recall','model','stream','owner','chat','persist','stop'))})
  print('NATIVE_HOST_FUNCTION_NAMES='+json.dumps({'file':file.name,'names':names[:80]},separators=(',',':')))
 except Exception:pass
print('NATIVE_ONEHOST_CALLBACK_BINDING_DONE=false')
print('NATIVE_LIVE_PROXY_RESTARTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
 c.REMOTE=REMOTE;ok=False
 try:ok=c.probe()
 except Exception as exc:
  v=str(exc);print('NOX_V75='+v if v.startswith('HOLD_') else 'NOX_V75=HOLD')
 finally:
  try:
   if not c.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
