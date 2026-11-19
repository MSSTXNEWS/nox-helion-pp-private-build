"""NOX V100 read-only: trace real native FastAPI route owners for V29.3.

92 frontend paths are NOT automatically real features. Resolve installed
FastAPI/Router decorators, include_router/mount source, and bounded local HTTP.
Never call mutating endpoints or inspect private records.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
_orig=ssh.api
def guarded(method,path,key,data=None):
    out=_orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return out
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,re,json,hashlib,urllib.request,urllib.error,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V100_EXISTING_BACKEND_ROUTE_COVERAGE_V1')
ROOT=Path('/root/nox')
WEB=ROOT/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
sources=[]
for p in WEB.glob('*'):
    if p.suffix not in ('.js','.mjs') or not p.is_file() or p.is_symlink():continue
    sources.append(p)
expected=set()
for f in sources:
    data=f.read_text(errors='replace')
    for m in re.finditer(r'''["'](/(?:api|v1)/[A-Za-z0-9_/?={}&.\-]+)["']''',data):
        expected.add(m.group(1).split('?',1)[0].rstrip('/'))
print('NATIVE_WEB_EXPECTED_ROUTES='+str(len(expected)))
seen_files=0
routes={}
compositions=[]
directories=[ROOT/'scripts',ROOT/'nox_web',ROOT/'app',ROOT/'web',ROOT/'server',ROOT/'services']
for base in directories:
    if not base.is_dir() or base.is_symlink():continue
    for parent,dirs,files in os.walk(base,followlinks=False):
        depth=len(Path(parent).relative_to(base).parts)
        dirs[:]=sorted(d for d in dirs if not (Path(parent)/d).is_symlink() and not d.startswith('.')) if depth<4 else []
        for fn in files:
            if not fn.endswith('.py'):continue
            p=Path(parent)/fn
            try:
                if p.is_symlink() or p.stat().st_size>300000:continue
                tree=ast.parse(p.read_bytes())
            except (OSError,SyntaxError,UnicodeError):continue
            seen_files+=1
            for node in ast.walk(tree):
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute):continue
                        if decorator.func.attr not in ('get','post','put','delete','patch','api_route','websocket'):continue
                        if not decorator.args or not isinstance(decorator.args[0],ast.Constant):continue
                        route=decorator.args[0].value
                        if not isinstance(route,str) or not route.startswith('/'):continue
                        info={'method':decorator.func.attr,'handler':node.name[:65],
                              'module':p.name[:90]}
                        routes.setdefault(route.rstrip('/'),[]).append(info)
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('include_router','mount'):
                    if len(compositions)>50:continue
                    prefix=next((k.value.value for k in node.keywords if k.arg=='prefix' and isinstance(k.value,ast.Constant) and isinstance(k.value.value,str)),None)
                    path=node.args[0].value if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str) else None
                    compositions.append({'file':p.name[:90],'kind':node.func.attr,'path':path,'prefix':prefix})
        if seen_files>4000:break
    if seen_files>4000:break
def matches(front,real):
    a=front.strip('/').split('/');b=real.strip('/').split('/')
    return len(a)==len(b) and all(x==y or (y.startswith('{') and y.endswith('}')) for x,y in zip(a,b))
matched={}
for wanted in sorted(expected):
    owners=[(actual,m) for actual,mods in routes.items() if matches(wanted,actual) for m in mods]
    if owners:matched[wanted]=owners
print('NATIVE_REAL_BACKEND_MAP='+json.dumps({'python_files_parsed':seen_files,'native_route_paths':len(routes),
    'required_v29_routes':len(expected),'exact_native_matches':len(matched),
    'unmatched_routes':len(expected)-len(matched),'mounts':compositions[:35]},sort_keys=True,separators=(',',':')))
for frontend,owners in sorted(matched.items()):
    print('NATIVE_ROUTE_OWNER='+json.dumps({'frontend':frontend,'matches':owners[:4]},sort_keys=True,separators=(',',':')))
# These are only source declarations, not proven operational actions.
for wanted in sorted(expected):
    if wanted not in matched and wanted in ('/api/chat','/api/nox/chat/stream','/api/nox/status',
            '/api/nox/stop','/api/nox/training/status','/api/s03/remember','/api/voice/transcribe',
            '/api/projects','/api/ui/capabilities'):
        print('NATIVE_UNBOUND_CRITICAL='+wanted)
print('NATIVE_ROUTE_SOURCE_ONLY=true')
print('NATIVE_ALL_FEATURES_ACCEPTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE;ssh.api=guarded
    buf=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buf):ok=ssh.probe()
    except Exception as exc:
        msg=str(exc);print("NOX_V100="+msg if msg.startswith("HOLD_") else "NOX_V100=HOLD_NATIVE")
    finally:
        try:
            with contextlib.redirect_stdout(buf):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    for row in buf.getvalue().splitlines():
        if row.startswith(('NATIVE_REAL_BACKEND_MAP=','NATIVE_ROUTE_OWNER=','NATIVE_UNBOUND_CRITICAL=',
            'NATIVE_WEB_EXPECTED_ROUTES=','NATIVE_READ_ONLY_COMPLETE=','TEMP_SSH_CLEANUP=')):
            print(row[:2400])
    return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
