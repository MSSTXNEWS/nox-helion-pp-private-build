"""NOX V108: inspect existing on-demand teacher service without launching models."""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,re,json,subprocess,configparser,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V108_ONDEMAND_TEACHER_CAPABILITY_READONLY_V1')
def emit(name,body):
 x=json.dumps(body,sort_keys=True,separators=(',',':'))
 if len(x)<1600:print('NATIVE_V108_'+name+'='+x)
config=configparser.ConfigParser(interpolation=None,strict=False)
for p in Path('/etc/supervisor/conf.d').glob('*.conf'):
 try:config.read(p)
 except Exception:pass
candidates=[]
for sec in config.sections():
 if not any(x in sec.lower() for x in ('teacher','proxy','tuner')):continue
 command=config.get(sec,'command',fallback='')
 args=re.findall(r'/[A-Za-z0-9_./-]+\.(?:py|sh)',command)
 emit('SUPERVISOR',{'service':sec[:70],'script_basenames':[Path(a).name for a in args[:4]]})
 candidates.extend(args)
candidates.extend(['/root/nox/scripts/teacher_serve_t811u.sh','/root/nox/scripts/teacher_serve_t811u.py'])
seen=set()
for path in candidates:
 if path in seen:continue
 seen.add(path)
 p=Path(path)
 try:
  if not p.is_file() or p.is_symlink() or p.stat().st_size>150000:continue
  raw=p.read_bytes()
  info={'basename':p.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
  text=raw.decode('utf8','replace')
  info['model_basenames']=list(dict.fromkeys(Path(x).name[:90] for x in
    re.findall(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:gguf|safetensors)',text)))[:16]
  info['shell_model_args_present']=any(x in text for x in ('--model','--model-path','--port'))
  info['teacher_calls_via_http']=any(x in text for x in ('/v1/chat/completions','http://127.0.0.1','localhost'))
  info['script_lines']=len(text.splitlines())
  if p.suffix=='.py':
   t=ast.parse(text)
   fn=[n.name for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
   info['function_names']=[x[:60] for x in fn[:35]]
  emit('SCRIPT',info)
 except Exception as e:emit('SCRIPT',{'basename':p.name,'hold':type(e).__name__})
# Known deployed local endpoints from V107, safely mapped by model identity and
# trained function; never issue chat completions to embedding/safety endpoints.
roles=[{'port':8081,'id':'current.gguf','role':'NOX_PRIMARY_CHAT'},
       {'port':8082,'id':'bge-m3-Q4_K_M.gguf','role':'EMBEDDING_ONLY'},
       {'port':8092,'id':'Qwen3Guard-Gen-4B.Q4_K_M.gguf','role':'SAFETY_GUARD_ONLY'}]
emit('EXISTING_ROLES',{'endpoints':roles,
 'distinct_general_reasoner_teacher_currently_verified':False,
 'none_started':True,
 'private_dialogues_sent':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();ok=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=old(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):ok=ssh.probe()
 except Exception as e:
  x=str(e)
  print("NOX_V108_HOLD="+(x if x.startswith('HOLD_') and len(x)<90 else "NATIVE_TRANSPORT"))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:ok=False
  except Exception:ok=False
 rows=[]
 for line in out.getvalue().splitlines():
  if line.startswith(("NATIVE_V108_","TEMP_SSH_CLEANUP=")):
   print(line[:1600]);rows.append(line)
 passed=bool(ok and any(x.startswith('NATIVE_V108_EXISTING_ROLES=') for x in rows))
 print('NOX_V108_LIVE_SERVICE_INVENTORY='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
