"""NOX V101: source-only S03 ledger contracts for real V29.3 receipts.

No mutation. Inspect native function definitions and database table schemas
without returning memory content, credentials or user transcripts.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_orig=ssh.api
def rate(method,path,key,data=None):
 result=_orig(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,sqlite3,os,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V101_NATIVE_S03_RECEIPT_METHODS_V1')
p=Path('/root/nox/scripts/s03_memory.py')
def emit(k,v):print(k+'='+json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')))
if not p.is_file() or p.is_symlink() or p.stat().st_size>300000:
 emit('NATIVE_MEMORY_SOURCE',{'state':'HOLD_S03_SOURCE'});raise SystemExit(2)
raw=p.read_bytes()
tree=ast.parse(raw.decode('utf8'))
emit('NATIVE_MEMORY_SOURCE',{'sha256':hashlib.sha256(raw).hexdigest(),
 'source_bytes':len(raw),'definitions':[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))][:65]})
def redacted(node):
 try:txt=ast.unparse(node)
 except Exception:return '<redacted>'
 if len(txt)>500:return '<long expression>'
 txt=re.sub(r'(["\'])(?:\\.|(?!\1).){10,}\1','<literal>',txt)
 return txt[:400]
for n in tree.body:
 if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
 if n.name not in ('persist_turn','recall','remember','counts','format_for_prompt','_connect','_db','search','get_status','list_turns'):continue
 params=[a.arg for a in n.args.args]
 emit('NATIVE_MEMORY_FUNCTION',{'name':n.name,'params':params,'positional_defaults':len(n.args.defaults),
       'keyword_only':[x.arg for x in n.args.kwonlyargs],
       'returns_shape':[(x.lineno,redacted(x.value)) for x in ast.walk(n) if isinstance(x,ast.Return)][:7]})
# Verify actual seed DB read-only schema, don't output any rows or privacy-sensitive columns from data.
paths=[Path('/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),Path('/root/nox/memory/infinite/nox_infinite_memory.sqlite3')]
for db in paths:
 if not db.is_file() or db.is_symlink():continue
 try:
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as conn:
   conn.execute('PRAGMA query_only=ON')
   tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")][:40]
   cols={}
   for table in tables:
    if not re.fullmatch(r'[A-Za-z_0-9]{1,90}',table):continue
    cols[table]=[r[1] for r in conn.execute('PRAGMA table_info('+table+')')][:35]
  emit('NATIVE_MEMORY_SQLITE_SCHEMA',{'basename':db.name,'tables':cols})
 except Exception:emit('NATIVE_MEMORY_SQLITE_SCHEMA',{'basename':db.name,'state':'HOLD_DB_READ'})
print('NATIVE_S03_PRIVATE_ROW_EXPORTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
 ssh.REMOTE=REMOTE;ssh.api=rate;okay=False
 try:okay=ssh.probe()
 except Exception as e:
  val=str(e);print("NOX_V101="+val if val.startswith("HOLD_") else "NOX_V101=HOLD_NATIVE")
 finally:
  try:
   if not ssh.cleanup():okay=False
  except Exception:okay=False
 raise SystemExit(0 if okay else 2)
