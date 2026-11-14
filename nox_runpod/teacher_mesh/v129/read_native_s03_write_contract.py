"""V129 native READ ONLY S03 write-contract inspection; no record text exported."""
from __future__ import annotations
import contextlib, io, json, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,hashlib,inspect,json,sqlite3
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V129_READONLY_S03_WRITER_CONTRACT_V1')
p=Path('/root/nox/scripts/s03_memory.py')
if not p.is_file() or p.is_symlink():raise RuntimeError('HOLD_S03_FILE')
raw=p.read_bytes()
tree=ast.parse(raw)
import s03_memory
db=Path(s03_memory.DB)
if not db.is_file() or db.is_symlink():raise RuntimeError('HOLD_S03_DB')
def emit(label,record):
 value=json.dumps(record,separators=(',',':'),sort_keys=True)
 if len(value)<680:print('NATIVE_V129_'+label+'='+value)
emit('SOURCE',{'sha256':hashlib.sha256(raw).hexdigest(),
 'bytes':len(raw),'db_basename':db.name,'safe_read_only':True})
fnames=('remember','persist_turn','recall','connect','init_db','store_fact','remember_fact','write_fact','add_memory')
for name in fnames:
 fn=getattr(s03_memory,name,None)
 node=next((n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name),None)
 if not callable(fn) or node is None:continue
 parameters=[x.arg for x in node.args.posonlyargs+node.args.args+node.args.kwonlyargs]
 calls=sorted({n.func.id if isinstance(n.func,ast.Name) else n.func.attr
  for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,(ast.Name,ast.Attribute))
 })[:28]
 emit('FUNC_'+name.upper(),{'parameters':parameters[:25],
 'vararg':node.args.vararg.arg if node.args.vararg else None,
 'varkw':node.args.kwarg.arg if node.args.kwarg else None,
 'async':isinstance(node,ast.AsyncFunctionDef),'calls':calls,
 'line_count':node.end_lineno-node.lineno+1})
with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as con:
 con.execute('PRAGMA query_only=ON')
 tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
 for name in ('s03_items','s03_ledger','nox_v29_dialogs','nox_v29_dialog_messages'):
  if name not in tables:continue
  cols=[{'name':r[1],'type':r[2],'nonnull':bool(r[3])} for r in con.execute('PRAGMA table_info("'+name+'")')]
  emit('TABLE_'+name.upper(),{'table':name,'columns':cols[:14]})
 emit('INTEGRITY',{'quick_check_ok':con.execute('PRAGMA quick_check').fetchone()[0]=='ok',
  'has_ledger':'s03_ledger' in tables,'has_items':'s03_items' in tables,
  'tables_count':len(tables),'private_rows_exported':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def safe(method,path,key,data=None):
        for i in range(4):
            try:
                val=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return val
            except RuntimeError as ex:
                if method!='GET' or str(ex)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=safe
    stream=io.StringIO();transport=False;clean=False
    try:
        with contextlib.redirect_stdout(stream):transport=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V129_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<90 else 'HOLD_NATIVE_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(stream):clean=ssh.cleanup()
        except Exception:clean=False
    lines=stream.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V129_','TEMP_SSH_CLEANUP=')) and len(line)<800:print(line)
    accepted=bool(transport and clean and
      any(x.startswith('NATIVE_V129_INTEGRITY=') and '"quick_check_ok":true' in x for x in lines)
      and 'NATIVE_READ_ONLY_COMPLETE=true' in lines)
    print('NOX_V129_S03_SOURCE_READ_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2

if __name__=='__main__':raise SystemExit(main())
