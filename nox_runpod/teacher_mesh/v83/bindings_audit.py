"""V83 one-shot native S03 binding and trainer endpoint structural audit.

Redacted AST fragments: never export passwords, HTTP auth values, chat text or
S03 records. Existing owner authorization remains immutable.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
prev=conn.api
def settle(method,path,key,data=None):
    r=prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(13)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,hashlib,json,os,re,subprocess,sqlite3
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_BIND_SCHEMA=NOX_E2_LIVE_S03_CALLBACK_MAPPING_V1')
src=Path('/root/nox/scripts/chat_proxy.py')
if not src.is_file() or src.is_symlink() or src.stat().st_size>130000:
    print('NATIVE_BIND_SOURCE=HOLD');print('NATIVE_READ_ONLY_COMPLETE=true');raise SystemExit(0)
buf=src.read_bytes()
print('NATIVE_BIND_PROXY_SHA256='+hashlib.sha256(buf).hexdigest())
t=ast.parse(buf)
known={'role','content','source_uri','verified','superseded','segment','tenant','principal',
      'chat_id','user','assistant','memory','s03','model','stream','max_tokens',
      'source','text','messages','session','question','query','answer','status',
      'kind','scope','id','created_at','dialog_id','write','read','limit'}
class Safe(ast.NodeTransformer):
    def visit_Constant(self,n):
        if isinstance(n.value,str):
            value=n.value
            return ast.copy_location(ast.Constant(value=value if value in known else '<REDACTED>'),n)
        return n
wanted={'_s03_augment':88,'_s03_persist_pair':115,'_s03_user_from_payload':45,
        's03_recall_api':75,'s03_remember_api':70,
        '_build_messages':48,'_proxy_completion':45,'_session_ok':50}
for node in t.body:
    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in wanted:continue
    copy_node=Safe().visit(copy.deepcopy(node))
    lines=ast.unparse(copy_node).splitlines()
    print('NATIVE_BIND_FUNC='+node.name+',LINES='+str(len(lines)))
    for i,line in enumerate(lines[:wanted[node.name]],1):
        if len(line)>280:line=line[:280]
        print('NATIVE_BIND_AST_'+node.name.upper()+'_'+str(i)+'='+line)
imports=[]
for n in t.body:
    if isinstance(n,ast.Import):
        for a in n.names:
            if any(s in a.name.lower() for s in ('s03','memory','brain','sqlite','agent','rag')):
                imports.append(a.name)
    if isinstance(n,ast.ImportFrom) and n.module:
        if any(s in n.module.lower() for s in ('s03','memory','brain','agent','rag')):
            imports.append(n.module)
print('NATIVE_BIND_IMPORTS='+json.dumps(sorted(set(imports))[:25]))
names=[]
for n in t.body:
    if isinstance(n,(ast.Assign,ast.AnnAssign)):
        targets=n.targets if isinstance(n,ast.Assign) else [n.target]
        for target in targets:
            if isinstance(target,ast.Name) and any(s in target.id for s in ('NOX_MEM','S03','MEMORY')):
                names.append(target.id)
print('NATIVE_BIND_MEMORY_GLOBALS='+json.dumps(sorted(set(names))[:25]))
# Only schema/columns - never private rows or chat histories.
db=Path('/root/nox/memory/infinite/nox_infinite_memory.sqlite3')
if db.is_file() and not db.is_symlink():
    try:
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=5) as cx:
            cx.execute('PRAGMA query_only=ON')
            out=[]
            for (name,) in cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 40"):
                if not re.fullmatch('[A-Za-z0-9_]{1,70}',name):continue
                if any(s in name.lower() for s in ('memory','fact','genesis','skill','brain','segment','dialog','message','event')):
                    cols=[r[1] for r in cx.execute('PRAGMA table_info("'+name+'")') if isinstance(r[1],str) and re.fullmatch('[A-Za-z0-9_]{1,70}',r[1])]
                    out.append({'table':name,'columns':cols[:18]})
            print('NATIVE_BIND_DB_SCHEMA='+json.dumps(out[:12],sort_keys=True,separators=(',',':'))[:700])
    except Exception:
        print('NATIVE_BIND_DB_SCHEMA=HOLD')
# supervisor status and config pathname only, not command flags/secrets.
try:
    p=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],capture_output=True,text=True,timeout=6)
    f=p.stdout.strip().split()
    print('NATIVE_BIND_VOLTA_SERVICE='+json.dumps({'state':f[1] if len(f)>1 else 'UNKNOWN','cli_rc':p.returncode},separators=(',',':')))
except Exception:print('NATIVE_BIND_VOLTA_SERVICE=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    conn.REMOTE=REMOTE;conn.api=settle
    f=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(f):ok=conn.probe()
    except Exception as e:
        v=str(e)
        print('NOX_BIND_RESULT='+v if v.startswith('HOLD_') and len(v)<100 else 'NOX_BIND_RESULT=HOLD_NATIVE')
    finally:
        try:
            with contextlib.redirect_stdout(f):
                if not conn.cleanup():ok=False
        except Exception:ok=False
    for s in f.getvalue().splitlines():
        if s.startswith(('NATIVE_BIND_','TEMP_SSH_CLEANUP=')) and len(s)<800:
            print(s)
    print('NOX_BIND_READ_ONLY_PASS='+str(ok).lower())
    return 0 if ok else 2
if __name__=='__main__':
    raise SystemExit(main())
