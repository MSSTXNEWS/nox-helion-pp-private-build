"""V102 read-only structural evidence of NOX S03 write/commit/readback contract."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
real=ssh.api
def guarded(method,path,key,data=None):
    val=real(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return val
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,json,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V102_S03_SOURCE_BEHAVIOR_V1')
file=Path('/root/nox/scripts/s03_memory.py')
raw=file.read_bytes()
expected='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('HOLD_S03_SOURCE_SHA')
root=ast.parse(raw)
class Redact(ast.NodeTransformer):
 def visit_Constant(self,node):
  if isinstance(node.value,str):
   allowed={'user','assistant','text','segment','provenance','salience','meta','id','sha256','ts','dedup',
            'db','source','dialog_id','session','items','ledger','role','content','source_uri'}
   return ast.copy_location(ast.Constant(node.value if node.value in allowed else 'STR'),node)
  return node
def emit(fn):
 n=next((x for x in root.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==fn),None)
 if n is None:return
 lines=ast.unparse(Redact().visit(copy.deepcopy(n))).splitlines()
 for i,line in enumerate(lines[:90]):
  if len(line)>280:line=line[:280]
  print('NATIVE_S03_FN_LINE='+json.dumps({'fn':fn,'line':i+1,'code':line},ensure_ascii=False,separators=(',',':')))
for fn in ('connect','init_db','remember','persist_turn','recall'):
 emit(fn)
for n in root.body:
 if not isinstance(n,ast.Assign):continue
 names=[x.id for x in n.targets if isinstance(x,ast.Name)]
 if any(x.upper().startswith(('DB','LEDGER','S03','PATH')) for x in names):
  expr=ast.unparse(Redact().visit(copy.deepcopy(n))).strip()
  if len(expr)<220:print('NATIVE_S03_TOP_LEVEL='+expr)
print('NATIVE_S03_NO_RECORDS_EXPORTED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
 ssh.REMOTE=REMOTE;ssh.api=guarded;good=False
 try:good=ssh.probe()
 except Exception as e:
  s=str(e);print('NOX_V102='+s if s.startswith('HOLD_') else 'NOX_V102=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():good=False
  except Exception:good=False
 raise SystemExit(0 if good else 2)
