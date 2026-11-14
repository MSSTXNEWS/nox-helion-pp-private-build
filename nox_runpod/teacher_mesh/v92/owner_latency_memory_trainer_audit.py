"""NOX V92 read-only verified service: actual owner TTFT timing and stable dialog memory.
No private transcript, tokens, secrets or database values exported.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_api=ssh.api
def settle(method,path,key,data=None):
 out=_api(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return out
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,ast,copy,json,re,statistics,hashlib,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V92_OWNER_LATENCY_AND_STABLE_S03_V1')
def emit(key,d):print(key+'='+json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')))
root=Path('/root/nox/scripts')
for filename,functions in (('memory_hooks.py',('jp_dialog_id','extra_context')),
                           ('agent_loop.py',('owner_completion','stream_tokens','run_tool_loop'))):
 p=root/filename
 if not p.is_file() or p.is_symlink() or p.stat().st_size>500_000:
  emit('NATIVE_FUNCTION_TREE',{'script':filename,'state':'HOLD_SOURCE'});continue
 raw=p.read_bytes()
 tree=ast.parse(raw)
 emit('NATIVE_FUNCTION_TREE',{'script':filename,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
 class Redact(ast.NodeTransformer):
  def visit_Constant(self,n):
   if isinstance(n.value,str):
    safe={'user','assistant','system','content','messages','dialog_id','chat_id','session_id','id',
          'stream','done','delta','role','scope','prompt','cached','token','source','trace','stop','model'}
    return ast.copy_location(ast.Constant(n.value if n.value in safe else 'STR'),n)
   return n
 for node in ast.walk(tree):
  if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in functions:continue
  safe=Redact().visit(copy.deepcopy(node))
  lines=ast.unparse(safe).splitlines()
  emit('NATIVE_FUNCTION_SIZE',{'script':filename,'fn':node.name,'line_count':len(lines),'async':isinstance(node,ast.AsyncFunctionDef)})
  cap=100 if node.name=='owner_completion' else 55
  for i,line in enumerate(lines[:cap]):
   if len(line)>230:line=line[:230]
   print('NATIVE_FN_LINE='+json.dumps({'script':filename,'fn':node.name,'line':i+1,'text':line},ensure_ascii=False,separators=(',',':')))
# Aggregate numeric performance only: never output log messages or user text.
folder=Path('/root/nox/logs')
items=[]
if folder.is_dir():
 for p in folder.glob('*proxy*.log'):
  if p.is_file() and p.stat().st_size<100_000_000:items.append(p)
for path in items[:4]:
 try:
  with path.open('rb') as f:
   f.seek(max(0,path.stat().st_size-120000))
   log=f.read().decode('utf8','replace').splitlines()[-500:]
  cols=('augment_ms','s03_ms','retrieve_ms','enrich_ms','searx_ms','build_ms','ttft_ms')
  vals={k:[] for k in cols}
  for line in log:
   for key in cols:
    m=re.search(r'(?<![A-Za-z0-9_])'+re.escape(key)+r'\s*[:=]\s*(\d{1,7})',line)
    if m:vals[key].append(int(m.group(1)))
  result={}
  for key,v in vals.items():
   if v:result[key]={'count':len(v),'median':round(statistics.median(v),1),'max':max(v)}
  emit('NATIVE_TIMING_AGGREGATE',{'basename':path.name,'sample_lines':len(log),'metrics':result})
 except Exception:pass
# Physical trainer high-level source: safe config statements only.
trainer=root/'train_qlora_35b_t866u.py'
if trainer.is_file() and not trainer.is_symlink() and trainer.stat().st_size<500000:
 raw=trainer.read_bytes()
 try:
  tree=ast.parse(raw)
  emit('NATIVE_VOLTA_SCRIPT',{'sha256':hashlib.sha256(raw).hexdigest(),
    'syntax_ok':True,'bytes':len(raw)})
  needles=('gradient_checkpointing','microbatch','batch_size','max_seq_length','seq_len','max_length',
           'device_map','deepspeed','offload','optim','nf4','torch_dtype','bf16','fp16','training_args')
  matches=[]
  for node in ast.walk(tree):
   if isinstance(node,(ast.Assign,ast.AnnAssign,ast.Call)):
    code=ast.unparse(node)
    if len(code)>260 or not any(x in code.lower() for x in needles):continue
    code=re.sub(r'([\'\"])[^\'\"]{16,}\1','STR',code)
    if len(matches)<65:matches.append({'line':node.lineno,'stmt':code[:250]})
  emit('NATIVE_VOLTA_KNOBS',{'statements':matches})
 except Exception:emit('NATIVE_VOLTA_SCRIPT',{'syntax_ok':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=settle;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V92='+x if x.startswith('HOLD_') else 'NOX_V92=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
if __name__=='__main__':raise SystemExit(main())
