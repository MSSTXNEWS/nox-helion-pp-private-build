"""V94 inspect live optional runtime_enrich provider chain and timeouts, read only."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
previous=ssh.api
def slow(method,path,key,data=None):
 v=previous(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return v
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,hashlib,json,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V94_RUNTIME_ENRICH_SOURCE_READONLY_V1')
path=Path('/root/nox/scripts/runtime_enrich.py')
if not path.is_file() or path.is_symlink() or path.stat().st_size>300000:
 print('NATIVE_ENRICH_SOURCE=HOLD')
else:
 content=path.read_bytes();tree=ast.parse(content)
 print('NATIVE_ENRICH_SOURCE='+json.dumps({'sha256':hashlib.sha256(content).hexdigest(),
        'size_bytes':len(content),'functions':[x.name for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))][:45]},separators=(',',':')))
 class Redact(ast.NodeTransformer):
  def visit_Constant(self,node):
   if isinstance(node.value,str):
    allow={'user','memory','source','content','status','json','timeout','url','data','model',
           'name','text','errors','reason','parts','state','snippet','source_uri'}
    return ast.copy_location(ast.Constant(node.value if node.value in allow else 'STR'),node)
   return node
 for n in ast.walk(tree):
  if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
  if n.name not in ('extra_parts','_active_live','detect_emotion','_port_ok','_http_ok','load_reg'):continue
  code=ast.unparse(Redact().visit(copy.deepcopy(n))).splitlines()[:95]
  for i,line in enumerate(code):
   if len(line)>270:line=line[:270]
   print('NATIVE_ENRICH_CODE='+json.dumps({'fn':n.name,'i':i+1,'line':line},ensure_ascii=False,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=slow;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  s=str(e);print('NOX_V94='+s if s.startswith('HOLD_') else 'NOX_V94=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
