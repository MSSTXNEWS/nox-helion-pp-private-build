"""V97 NOX WEB V29.3 native source and existing OneHost compatibility gate.

Grounds the exact frozen Drive build already mirrored in Vast incoming. Never
serves public preview or modifies existing routes, models, S03 or checkpoints.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import contextlib,io,time
prev=conn.api
def delayed(method,path,key,data=None):
    response=prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return response
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,os,re,urllib.request,urllib.error,subprocess,shutil
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V97_LATEST_WEB_PHYSICAL_INTEGRATION_GATE_V1')
BASE=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
EXPECTED={
 'index.html':'','chat.html':'','nox-chat.js':'d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce'
}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):
   h.update(chunk)
 return h.hexdigest()
def emit(name,data):print(name+'='+json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')))
if BASE.is_dir() and not BASE.is_symlink():
 files=[]
 for root,dirs,names in os.walk(BASE,followlinks=False):
  dirs[:]=[x for x in dirs if not (Path(root)/x).is_symlink()]
  for name in names:
   p=Path(root)/name
   if p.is_file() and not p.is_symlink():files.append(p)
 counts=len(files)
 size=sum(x.stat().st_size for x in files)
 samples=[]
 for name,sha in EXPECTED.items():
  p=BASE/name
  samples.append({'name':name,'present':p.is_file() and not p.is_symlink(),
    'sha256':digest(p) if p.is_file() and p.stat().st_size<1000000 else None,
    'matches_expected':digest(p)==sha if sha and p.is_file() and p.stat().st_size<1000000 else None})
 preview=(BASE/'index.html').read_text(errors='replace') if (BASE/'index.html').is_file() else ''
 chat=(BASE/'chat.html').read_text(errors='replace') if (BASE/'chat.html').is_file() else ''
 js=(BASE/'nox-chat.js').read_text(errors='replace') if (BASE/'nox-chat.js').is_file() else ''
 emit('NATIVE_WEB_V29_SOURCE',{'folder_present':True,'file_count':counts,
       'sum_bytes':size,'samples':samples,
       'public_preview_banner':('PUBLIC PREVIEW' in preview),
       'chat_uses_native_owner':('NOX_NATIVE_OWNER' in js),
       'chat_native_endpoint':('/api/nox/chat/stream' in js),
       'chat_fallback_endpoint':('/api/chat' in js),
       'native_status_endpoint':('/api/nox/status' in js),
       'contains_home':(BASE/'nox-home.mjs').is_file(),
       'contains_d02_backdrop':(BASE/'nox-eclipse-backdrop.mjs').is_file()})
else:
 emit('NATIVE_WEB_V29_SOURCE',{'folder_present':False})
p=Path('/root/nox/scripts/chat_proxy.py')
if p.is_file() and not p.is_symlink() and p.stat().st_size<150000:
 raw=p.read_bytes();tree=ast.parse(raw)
 paths=[]
 for node in ast.walk(tree):
  if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
  for decorator in node.decorator_list:
   if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.func.attr in ('get','post'):
    if decorator.args and isinstance(decorator.args[0],ast.Constant):
     x=decorator.args[0].value
     if isinstance(x,str) and (x.startswith('/api') or x in ('/','/chat','/health','/v1/chat/completions')):
      paths.append({'method':decorator.func.attr,'path':x,'handler':node.name})
 emit('NATIVE_WEB_EXISTING_PROXY',{'sha256':hashlib.sha256(raw).hexdigest(),
       'routes':sorted(paths,key=lambda x:x['path'])[:90],
       'no_new_backend_created':True})
for path in ('/','/chat','/nox','/nox/index.html','/api/nox/status','/api/nox/chat/stream'):
 for method in ('GET',):
  try:
   req=urllib.request.Request('http://127.0.0.1:8080'+path,method=method,
        headers={'User-Agent':'NOX-V97-Native-ReadOnly/1.0'})
   with urllib.request.urlopen(req,timeout=3) as r:
    code=r.status;ct=r.headers.get('Content-Type','')[:70]
  except urllib.error.HTTPError as exc:code=exc.code;ct=''
  except Exception:code=0;ct=''
  emit('NATIVE_WEB_ROUTE_HEALTH',{'path':path,'http':code,'type':ct})
try:
 s=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
 args=s.stdout.split()
 emit('NATIVE_WEB_OWNER',{'service':'nox-proxy','state':args[1] if len(args)>1 else 'UNKNOWN'})
except Exception:pass
print('NATIVE_WEB_DEPLOYMENT_PERFORMED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    conn.REMOTE=REMOTE;conn.api=delayed
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=conn.probe()
    except Exception as exc:
        s=str(exc)
        print('NOX_V97='+s if s.startswith('HOLD_') else 'NOX_V97=HOLD_NATIVE')
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if not conn.cleanup():ok=False
        except Exception:ok=False
    for row in out.getvalue().splitlines():
        if row.startswith(('NATIVE_WEB_','TEMP_SSH_CLEANUP=')) and len(row)<17000:
            print(row)
    return 0 if ok and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue() else 2
if __name__=='__main__':raise SystemExit(main())
