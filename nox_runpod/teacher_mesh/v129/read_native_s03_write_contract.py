"""V129 native READ ONLY S03 write-contract inspection; no record text exported."""
from __future__ import annotations
import contextlib, io, json, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

V129_COMPLETION_MARKERS = ("NATIVE_READ_ONLY_COMPLETE=true",)
V129_MAX_OUTPUT_LINE_CHARS = 7000


REMOTE=r'''set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,hashlib,json,os,stat,sqlite3
from pathlib import Path

MODULE_PATH=Path('/root/nox/scripts/s03_memory.py')
MODULE_ROOT=Path('/root/nox')
MODULE_ALLOWLIST=(MODULE_PATH,)
MAX_SOURCE_BYTES=2_000_000
WRITER_NAMES=('remember','persist_turn','recall','readback','read_memory',
              'store_fact','remember_fact','write_fact','add_memory')
TABLE_ALLOWLIST=('s03_items','s03_ledger')

def _hold(code):
    raise RuntimeError(code)

def _path_no_symlinks(path,root):
    path=Path(path)
    root=Path(root)
    if not path.is_absolute() or not root.is_absolute():
        _hold('HOLD_S03_PATH_NOT_ABSOLUTE')
    try:
        path.relative_to(root)
    except ValueError:
        _hold('HOLD_S03_PATH_OUTSIDE_ROOT')
    if '..' in path.parts:
        _hold('HOLD_S03_PATH_NOT_NORMALIZED')
    current=Path(path.anchor)
    for part in path.parts[1:]:
        current=current/part
        try:
            mode=os.lstat(current).st_mode
        except FileNotFoundError:
            _hold('HOLD_S03_PATH_MISSING')
        except OSError:
            _hold('HOLD_S03_PATH_UNREADABLE')
        if stat.S_ISLNK(mode):
            _hold('HOLD_S03_PATH_SYMLINK')
    return path

def _read_allowlisted_source(path,allowed_paths,root,max_bytes):
    path=Path(path)
    allowed={Path(item) for item in allowed_paths}
    if path not in allowed:
        _hold('HOLD_S03_MODULE_PATH_NOT_ALLOWLISTED')
    path=_path_no_symlinks(path,root)
    try:
        fd=os.open(str(path),os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    except FileNotFoundError:
        _hold('HOLD_S03_SOURCE_MISSING')
    except OSError:
        _hold('HOLD_S03_SOURCE_OPEN')
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            _hold('HOLD_S03_SOURCE_NOT_REGULAR')
        if info.st_size<1 or info.st_size>max_bytes:
            _hold('HOLD_S03_SOURCE_SIZE')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw=stream.read(max_bytes+1)
        if len(raw)<1 or len(raw)>max_bytes:
            _hold('HOLD_S03_SOURCE_SIZE')
        return raw
    finally:
        os.close(fd)

def _safe_type(node):
    if node is None:return 'UNANNOTATED'
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):
        base=_safe_type(node.value)
        if base.startswith('UNSAFE_') or not node.attr.isidentifier():return 'UNSAFE_ANNOTATION'
        return base+'.'+node.attr
    if isinstance(node,ast.Subscript):
        base=_safe_type(node.value);item=_safe_type(node.slice)
        if base.startswith('UNSAFE_') or item.startswith('UNSAFE_'):return 'UNSAFE_ANNOTATION'
        return base+'['+item+']'
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.BitOr):
        left=_safe_type(node.left);right=_safe_type(node.right)
        if left.startswith('UNSAFE_') or right.startswith('UNSAFE_'):return 'UNSAFE_ANNOTATION'
        return left+' | '+right
    if isinstance(node,ast.Tuple):
        items=[_safe_type(x) for x in node.elts]
        return 'UNSAFE_ANNOTATION' if any(x.startswith('UNSAFE_') for x in items) else ', '.join(items)
    if isinstance(node,ast.Constant) and node.value is None:return 'None'
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return 'FORWARD_REF'
    return 'UNSAFE_ANNOTATION'

def _writer_contract(raw):
    tree=ast.parse(raw)
    contract=[]
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in WRITER_NAMES:
            continue
        args=node.args
        params=[x.arg for x in args.posonlyargs+args.args+args.kwonlyargs]
        if args.vararg:params.append('*'+args.vararg.arg)
        if args.kwarg:params.append('**'+args.kwarg.arg)
        if any(not x.lstrip('*').isidentifier() for x in params):_hold('HOLD_S03_SIGNATURE')
        contract.append({'name':node.name,'async':isinstance(node,ast.AsyncFunctionDef),
            'parameters':params[:32],'defaults':len(args.defaults)+sum(x is not None for x in args.kw_defaults),
            'return_type':_safe_type(node.returns)})
    return {'functions':contract,'private_source_exported':False}

def _eval_path_expr(node,env):
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return Path(node.value)
    if isinstance(node,ast.Name) and node.id in env:return Path(env[node.id])
    if isinstance(node,ast.Attribute) and node.attr=='parent':
        base=_eval_path_expr(node.value,env)
        return base.parent if base is not None else None
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
        base=_eval_path_expr(node.left,env)
        if base is None:return None
        if isinstance(node.right,ast.Constant) and isinstance(node.right.value,str):return base/node.right.value
        return None
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('Path','PurePath'):
        if len(node.args)!=1 or node.keywords:return None
        return _eval_path_expr(node.args[0],env)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('resolve','absolute'):
        if node.args or node.keywords:return None
        base=_eval_path_expr(node.func.value,env)
        if base is None:return None
        return Path(os.path.normpath(os.path.abspath(str(base))))
    return None

def _database_path(raw,module_path,root):
    tree=ast.parse(raw)
    env={'__file__':Path(module_path)}
    database=None
    for node in tree.body:
        targets=[];value=None
        if isinstance(node,ast.Assign):
            targets=[x.id for x in node.targets if isinstance(x,ast.Name)];value=node.value
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name):
            targets=[node.target.id];value=node.value
        if not targets or value is None:continue
        resolved=_eval_path_expr(value,env)
        if resolved is not None:
            for target in targets:
                env[target]=resolved
                if target=='DB':database=resolved
    if database is None:_hold('HOLD_S03_DB_PATH_EXPRESSION')
    database=_path_no_symlinks(database,root)
    try:mode=os.lstat(database).st_mode
    except FileNotFoundError:_hold('HOLD_S03_DB_MISSING')
    if not stat.S_ISREG(mode):_hold('HOLD_S03_DB_NOT_REGULAR')
    return database

def _schema_snapshot(db_path,root,table_names):
    db_path=_path_no_symlinks(db_path,root)
    try:
        if not stat.S_ISREG(os.lstat(db_path).st_mode):_hold('HOLD_S03_DB_NOT_REGULAR')
        con=sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True,timeout=4)
    except RuntimeError:raise
    except (OSError,sqlite3.Error,ValueError):_hold('HOLD_S03_DB_READONLY_OPEN')
    result={'tables':[],'private_rows_exported':False,'read_only':True}
    try:
        con.execute('PRAGMA query_only=ON')
        for name in table_names:
            if not isinstance(name,str) or not name.isidentifier():_hold('HOLD_S03_TABLE_ALLOWLIST')
            found=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
            if found is None:continue
            quoted='"'+name.replace('"','""')+'"'
            columns=[]
            for row in con.execute('PRAGMA table_info('+quoted+')'):
                columns.append({'name':str(row[1]),'type':str(row[2] or ''),
                                'notnull':bool(row[3]),'primary_key':bool(row[5])})
            indexes=[]
            for row in con.execute('PRAGMA index_list('+quoted+')'):
                idx=str(row[1]);idxq='"'+idx.replace('"','""')+'"'
                idxcols=[str(x[2]) for x in con.execute('PRAGMA index_info('+idxq+')') if x[2] is not None]
                indexes.append({'name':idx,'unique':bool(row[2]),'columns':idxcols[:32]})
            result['tables'].append({'name':name,'columns':columns[:32],'indexes':indexes[:32]})
        return result
    except (OSError,sqlite3.Error,ValueError):_hold('HOLD_S03_SCHEMA_READ')
    finally:con.close()

raw=_read_allowlisted_source(MODULE_PATH,MODULE_ALLOWLIST,MODULE_ROOT,MAX_SOURCE_BYTES)
module_sha=hashlib.sha256(raw).hexdigest()
contract=_writer_contract(raw)
db=_database_path(raw,MODULE_PATH,MODULE_ROOT)
schema=_schema_snapshot(db,MODULE_ROOT,TABLE_ALLOWLIST)
def emit(label,value):
    text=json.dumps(value,separators=(',',':'),sort_keys=True)
    if len(text)>6000:_hold('HOLD_S03_AUDIT_OUTPUT_SIZE')
    print('NATIVE_V129_'+label+'='+text)
emit('SOURCE',{'module_path':str(MODULE_PATH),'sha256':module_sha,'bytes':len(raw),
               'allowlist_match':True,'safe_ast_only':True})
emit('WRITER_CONTRACT',contract)
emit('SCHEMA',schema)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE'''
def source_read_accepted(transport, clean, lines):
    return bool(transport and clean and isinstance(lines,(list,tuple))
      and any(isinstance(x,str) and x.startswith('NATIVE_V129_SOURCE=') for x in lines)
      and any(isinstance(x,str) and x.startswith('NATIVE_V129_WRITER_CONTRACT=') for x in lines)
      and any(isinstance(x,str) and x.startswith('NATIVE_V129_SCHEMA=') for x in lines)
      and 'NATIVE_READ_ONLY_COMPLETE=true' in lines)


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
        with contextlib.redirect_stdout(stream):
            transport=ssh.probe(required_completion_markers=V129_COMPLETION_MARKERS,
                                 max_output_line_chars=V129_MAX_OUTPUT_LINE_CHARS)
    except Exception as exc:
        msg=str(exc)
        print('NOX_V129_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<90 else 'HOLD_NATIVE_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(stream):clean=ssh.cleanup()
        except Exception:clean=False
    lines=stream.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V129_','TEMP_SSH_CLEANUP=')) and len(line)<7000:print(line)
    accepted=source_read_accepted(transport,clean,lines)
    print('NOX_V129_S03_SOURCE_READ_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2

if __name__=='__main__':raise SystemExit(main())
