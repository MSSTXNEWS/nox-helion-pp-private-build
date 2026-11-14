"""NOX V103: native API security and exact S03 receipt schema, read-only.

No secret values or private memory records emitted. Scope pin for real WEB V29.3
compatibility; never infer auth from HTTP 401 alone.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
old=ssh.api
def delay(method,path,key,data=None):
 x=old(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,re,sqlite3
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V103_NATIVE_AUTH_DB_SCHEMA_V1')
def emit(k,v):print(k+'='+json.dumps(v,sort_keys=True,separators=(',',':')))
p=Path('/root/nox/scripts/chat_proxy.py')
src=p.read_bytes()
emit('NATIVE_SECURITY_PROXY',{'sha256':hashlib.sha256(src).hexdigest(),
'bytes':len(src)})
tree=ast.parse(src)
for n in tree.body:
 if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
 if n.name not in ('_session_ok','_unauthorized','chat_api','_session_login','chat_login','_is_public_path'):continue
 out={'function':n.name,'args':[x.arg for x in n.args.args]}
 for item in ast.walk(n):
  if isinstance(item,ast.Call) and isinstance(item.func,ast.Attribute) and item.func.attr in ('set_cookie','delete_cookie'):
   out['cookie_call_type']=item.func.attr
   out['cookie_keywords']=[x.arg for x in item.keywords]
   for kw in item.keywords:
    if kw.arg in ('path','secure','httponly','samesite') and isinstance(kw.value,ast.Constant):
     out['cookie_'+kw.arg]=kw.value.value
  if isinstance(item,ast.Return):
   rendered=ast.unparse(item.value) if item.value else ''
   if any(x in rendered for x in ('_session_ok','_unauthorized')):
    out['returns_auth_function']=True
 emit('NATIVE_SECURITY_FUNCTION',out)
s=Path('/root/nox/scripts/s03_memory.py')
raw=s.read_bytes()
if hashlib.sha256(raw).hexdigest()!='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91':
 raise SystemExit('HOLD_S03_SHA')
ns=ast.parse(raw)
for v in ns.body:
 if not isinstance(v,ast.FunctionDef) or v.name not in ('init_db','connect','remember'):continue
 queries=[]
 for node in ast.walk(v):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('execute','executemany'):
   for arg in node.args[:1]:
    if not isinstance(arg,ast.Constant) or not isinstance(arg.value,str):continue
    sql=arg.value.strip()
    if sql[:7].upper() not in ('CREATE ','INSERT ','SELECT ','DELETE ','UPDATE ','PRAGMA '):continue
    if len(sql)>360:continue
    sql=re.sub(r"'[^']*'", "'PARAM'", sql)
    queries.append(sql[:320])
 emit('NATIVE_MEMORY_STATEMENTS',{'method':v.name,'statements':queries[:20]})
# Query exact default S03 database schema from native module, never read any rows.
try:
 import sys
 sys.path.insert(0,'/root/nox/scripts')
 import s03_memory
 db=Path(s03_memory.DB)
 if not db.is_file() or db.is_symlink():raise RuntimeError('HOLD_DB_NOT_A_FILE')
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as con:
  con.execute('PRAGMA query_only=ON')
  names=[x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")][:30]
  tables={}
  for name in names:
   if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,70}',name):continue
   tables[name]=[{'name':r[1],'type':r[2]} for r in con.execute('PRAGMA table_info('+name+')')][:25]
 emit('NATIVE_REAL_S03_SCHEMA',{'basename':db.name,'size_bytes':db.stat().st_size,'tables':tables})
except Exception as ex:
 emit('NATIVE_REAL_S03_SCHEMA',{'state':'HOLD_DB_SCHEMA','error_type':type(ex).__name__})
print('NATIVE_NO_RECORDS_OR_COOKIES_EXPORTED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V103='+v if v.startswith('HOLD_') else 'NOX_V103=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
