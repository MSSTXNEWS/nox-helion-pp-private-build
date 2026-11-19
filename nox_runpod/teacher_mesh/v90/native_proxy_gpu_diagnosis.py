"""NOX V90 read-only: live proxy E2E gates + sanitized AST source/namespace map.
No credentials/record bodies/admin mutations; synthetic prompts only.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
base=ssh.api
def delay(method,path,key,data=None):
 r=base(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,ast,copy,time,json,re,subprocess,urllib.request,urllib.error,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V90_PROXY_TTFT_GPU1_ADMISSION_V1')
def emit(k,x):print(k+'='+json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
p=Path('/root/nox/scripts/chat_proxy.py')
expected='596130dda753d7fed5514a0ae36d8908be8699c804cbb1288f58a410418f043b'
raw=p.read_bytes() if p.is_file() else b''
emit('NATIVE_PROXY_SHA',{'verified':hashlib.sha256(raw).hexdigest()==expected,'bytes':len(raw)})
if hashlib.sha256(raw).hexdigest()==expected:
 tree=ast.parse(raw.decode())
 class Redact(ast.NodeTransformer):
  def visit_Constant(self,node):
   if isinstance(node.value,str):
    safe={'stream','model','messages','role','content','delta','reasoning_content','choices','status','error',
      'data:','[DONE]','true','false','Authorization','Accept','application/json','text/event-stream',
      'user','assistant','tool','session','queue','progress','max_tokens','temperature','trace','owner'}
    return ast.copy_location(ast.Constant(value=node.value if node.value in safe else 'STR'),node)
   return node
 names={'_proxy_completion':150,'chat_api':40,'_build_messages':65,'_understanding_http':70,'_wrap_ttft':55}
 for n in ast.walk(tree):
  if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef)) and n.name in names:
   safe=Redact().visit(copy.deepcopy(n))
   lines=ast.unparse(safe).splitlines()[:names[n.name]]
   for i,line in enumerate(lines):
    if len(line)>260:line=line[:260]
    print('NATIVE_PROXY_AST_'+n.name.upper()+'_'+str(i+1)+'='+line)
# Run direct model and public-proxy endpoint smoke. Never use credentials.
for label,url in (('MODEL','http://127.0.0.1:8081/v1/chat/completions'),
                  ('PROXY','http://127.0.0.1:8080/v1/chat/completions')):
 payload={'messages':[{'role':'user','content':'Ответь одним словом: да.'}],
          'temperature':0,'max_tokens':16,'stream':True}
 if label=='MODEL':
  try:
   with urllib.request.urlopen('http://127.0.0.1:8081/v1/models',timeout=4) as r:
    name=json.loads(r.read(16000)).get('data',[{}])[0].get('id','')
   if name.endswith('/models/current.gguf'):payload['model']=name
  except Exception:pass
 request=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),
     headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
 start=time.monotonic();first=None;count=0;done=False
 try:
  with urllib.request.urlopen(request,timeout=20) as response:
   status=response.status
   for chunk in response:
    if time.monotonic()-start>22:break
    if not chunk.startswith(b'data:'):continue
    body=chunk[5:].strip()
    if body==b'[DONE]':done=True;break
    try:result=json.loads(body)
    except Exception:continue
    for v in result.get('choices',[]):
     text=(v.get('delta') or {}).get('content')
     if text:
      count+=1
      if first is None:first=time.monotonic()
   emit('NATIVE_SYNTHETIC_LATENCY',{'endpoint':label,'status':status,'chunks':count,'done':done,
       'first_ms':round((first-start)*1000,1) if first else None,
       'e2e_ms':round((time.monotonic()-start)*1000,1)})
 except urllib.error.HTTPError as e:
  emit('NATIVE_SYNTHETIC_LATENCY',{'endpoint':label,'http':e.code,'need_native_auth':e.code in (401,403)})
 except Exception as e:
  emit('NATIVE_SYNTHETIC_LATENCY',{'endpoint':label,'state':'HOLD_'+type(e).__name__})
try:
 gpu=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'],
     capture_output=True,text=True,timeout=10)
 rows=[]
 for line in gpu.stdout.splitlines()[:25]:
  x=[z.strip() for z in line.split(',')]
  if len(x)!=3:continue
  try:
   pid=int(x[1]);memory=int(re.search(r'[0-9]+',x[2]).group(0))
  except Exception:continue
  proc=Path('/proc')/str(pid)
  obj={'uuid_suffix':x[0][-12:],'pid':pid,'used_mib':memory,'pid_visible_in_container':proc.exists()}
  if proc.exists():
   try:
    cmd=(proc/'cmdline').read_bytes().split(b'\x00')
    obj['basename']=next((Path(c.decode('utf8','replace')).name[:75] for c in cmd if c.endswith((b'.py',b'.sh'))),'UNKNOWN')
    m=re.search(r'PPid:\s*(\d+)',(proc/'status').read_text(),re.M)
    obj['ppid']=int(m.group(1)) if m else None
   except Exception:pass
  rows.append(obj)
 emit('NATIVE_GPU_PROCESSES',{'query_status':gpu.returncode,'rows':rows})
except Exception:emit('NATIVE_GPU_PROCESSES',{'state':'HOLD_NVIDIA_SMI'})
print('NATIVE_NO_LIVE_MUTATIONS=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=delay;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V90='+x if x.startswith('HOLD_') else 'NOX_V90=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
if __name__=='__main__':raise SystemExit(main())
