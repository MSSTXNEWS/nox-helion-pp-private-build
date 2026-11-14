"""V126: read-only AST/signature inventory of already-installed S03 writer.

Prints no records, database values, owner password, DB path, or secret.
Uses original V51 ephemeral SSH registration with verified cleanup.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,hashlib,json,re,sqlite3
from pathlib import Path
from fastapi.routing import APIRoute
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V126_SCHEMA=S03_NATIVE_WRITER_AST_SIGNATURE_READONLY_V1')
import s03_memory,chat_proxy
path=Path(s03_memory.__file__).resolve()
if not path.is_file() or path.stat().st_size>220000 or path.is_symlink():
 raise RuntimeError('HOLD_ORIGINAL_S03_SOURCE')
code=path.read_bytes()
tree=ast.parse(code)
def names(args):
 out=[a.arg for a in args.posonlyargs+args.args]
 if args.vararg:out.append('*'+args.vararg.arg)
 out += [a.arg for a in args.kwonlyargs]
 if args.kwarg:out.append('**'+args.kwarg.arg)
 return out[:15]
functions=[]
for item in tree.body:
 if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)):
  row={'name':item.name,'args':names(item.args),
       'async':isinstance(item,ast.AsyncFunctionDef)}
  functions.append(row)
print('NATIVE_V126_SOURCE='+json.dumps({'s03_source_sha256':hashlib.sha256(code).hexdigest(),
 'function_count':len(functions),'read_only':True},separators=(',',':')))
for i in range(0,min(len(functions),80),3):
 print('NATIVE_V126_FUNCTIONS='+json.dumps(functions[i:i+3],separators=(',',':')))
db=Path(s03_memory.DB)
if not db.is_file() or db.is_symlink():raise RuntimeError('HOLD_ORIGINAL_S03_DB')
with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as conn:
 conn.execute('PRAGMA query_only=ON')
 columns=[{'name':row[1],'type':row[2],'notnull':bool(row[3]),
           'pk':bool(row[5])} for row in conn.execute('PRAGMA table_info(s03_items)')]
 tables=[str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
 quick=conn.execute('PRAGMA quick_check').fetchone()[0]
 count=conn.execute('SELECT COUNT(*) FROM s03_items').fetchone()[0]
print('NATIVE_V126_S03='+json.dumps({'columns':columns,'quick_check':quick,
 'items':count,'dialog_tables':all(k in tables for k in ('nox_v29_dialogs','nox_v29_dialog_messages')),
 'schema_only_no_values':True},separators=(',',':')))
routes={r.path for r in chat_proxy.app.routes if isinstance(r,APIRoute)}
print('NATIVE_V126_ROUTE='+json.dumps({'write_fact_registered':'/api/nox/memory/facts' in routes,
 'original_onehost_active':True,'all_web_functional_claim':False},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE
    original=ssh.api
    def retry(method,path,key,data=None):
        for i in range(4):
            try:
                result=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=retry
    output=io.StringIO();good=False
    try:
        with contextlib.redirect_stdout(output):good=ssh.probe()
    except Exception as exc:
        value=str(exc)
        print('NOX_V126_TRANSPORT_HOLD='+(value if value.startswith('HOLD_') else 'SSH_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if ssh.cleanup() is not True:good=False
        except Exception:good=False
    rows=output.getvalue().splitlines()
    for row in rows:
        if row.startswith(('NATIVE_V126_','TEMP_SSH_CLEANUP=','SSH_FAILURE_CLASS=')) and len(row)<800:
            print(row)
    required=('NATIVE_V126_SOURCE=','NATIVE_V126_S03=','NATIVE_V126_ROUTE=')
    accepted=good and all(any(line.startswith(k) for line in rows) for k in required)
    accepted=accepted and 'NATIVE_READ_ONLY_COMPLETE=true' in rows
    print('NOX_V126_WRITER_READONLY_ACCEPTED='+str(bool(accepted)).lower())
    return 0 if accepted else 2
if __name__=='__main__':
    raise SystemExit(main())
