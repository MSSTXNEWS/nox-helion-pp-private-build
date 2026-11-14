"""One-patch native V29 chat adapter install. Exactly one existing OneHost."""
from __future__ import annotations
import base64,hashlib,contextlib,io,time
from pathlib import Path
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
_api=ssh.api
def attach(method,path,key,data=None):
    r=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE_TEMPLATE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,base64,hashlib,json,os,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V106_V29_REAL_BRIDGE_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
OLD='877af6fb10bc3ce4c456900e063c00f667362017c4fde0fe65b2a802075004ad'
B=base64.b64decode('___BRIDGE_BASE64___',validate=True)
BSHA='___BRIDGE_SHA___'
BACKUP=P.with_name('chat_proxy.py.nox-v106-'+OLD[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/.stop','/workspace/NOX_STOP')
def sha(x):return hashlib.sha256(x).hexdigest()
def stop():return any(Path(x).exists() for x in STOPS)
def emit(**x):print('NATIVE_V106_RESULT='+json.dumps(x,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=4) as r:return r.status
 except Exception:return None
def service():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
  x=p.stdout.split();return x[1] if p.returncode==0 and len(x)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:slots=json.loads(r.read(30000))
  return isinstance(slots,list) and len(slots)==6 and not any(
      x.get('is_processing',x.get('processing',False)) for x in slots if isinstance(x,dict))
 except Exception:return False
def atomic(path,blob,meta,tempname):
 temp=path.with_name(tempname)
 if temp.exists():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with temp.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(blob):raise RuntimeError('HOLD_ATOMIC_SHA')
 os.replace(temp,path)
def revert(blob,meta):
 try:
  atomic(P,blob,meta,'.nox-v106-rollback.tmp')
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  for _ in range(15):
   if health(8080)==200 and health(8081)==200 and service()=='RUNNING':
    return sha(P.read_bytes())==OLD
   time.sleep(1)
 except Exception:pass
 return False
try:
 if stop():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink():raise RuntimeError('HOLD_PROXY_SOURCE')
 meta=P.stat();original=P.read_bytes()
 if sha(original)!=OLD or meta.st_uid!=0:raise RuntimeError('HOLD_SOURCE_SHA_CHANGED')
 if sha(B)!=BSHA or not 1000<len(B)<22000:raise RuntimeError('HOLD_BRIDGE_SHA')
 compile(B,str(M),'exec')
 if health(8080)!=200 or health(8081)!=200 or service()!='RUNNING' or not idle():
  raise RuntimeError('HOLD_ACTIVE_CHAT_OR_HEALTH')
 src=original.decode('utf8');tree=ast.parse(src)
 if any(getattr(x,'name','')=='native_v29_chat_stream' for x in tree.body):
  raise RuntimeError('HOLD_ROUTE_ALREADY_ACTIVE')
 chat=next((x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='chat_api'),None)
 if not chat or not chat.decorator_list:raise RuntimeError('HOLD_CHAT_ROUTE_NOT_FOUND')
 if 'register_native_v29_chat(' in src:raise RuntimeError('HOLD_BRIDGE_ALREADY_REGISTERED')
 # V106 originally inserted registration before the chat handlers existed.
 # Register ONLY after all module-level functions have been defined (on import),
 # preserving the existing FastAPI app, S03 and owner session validation.
 handler=next((x for x in tree.body if isinstance(x,(ast.AsyncFunctionDef,ast.FunctionDef))
               and x.name=='_proxy_completion'),None)
 if handler is None or not callable(getattr(ast,'parse',None)):
  raise RuntimeError('HOLD_NATIVE_OWNER_HANDLER_NOT_DEFINED')
 lines=src.splitlines(keepends=True)
 if lines and not lines[-1].endswith('\n'):lines.append('\n')
 lines.append('\n# NOX V108 native WEB compatibility registration (same app/owner)\n')
 lines.append('from nox_v29_chat_bridge import register_native_v29_chat\n')
 lines.append('register_native_v29_chat(app, globals())\n')
 changed=''.join(lines).encode('utf8')
 compile(changed,str(P),'exec')
 if len(changed)>160000:raise RuntimeError('HOLD_PATCH_SIZE')
 if M.exists():
  if M.is_symlink() or sha(M.read_bytes())!=BSHA:raise RuntimeError('HOLD_BRIDGE_CONFLICT')
 else:
  atomic(M,B,meta,'.nox-v106-module.tmp')
 if stop() or not idle():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 atomic(P,changed,meta,'.nox-v106-route.tmp')
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  good=False
  for _ in range(15):
   if health(8080)==200 and health(8081)==200 and service()=='RUNNING':
    good=True;break
   time.sleep(1)
  if not good or sha(P.read_bytes())!=sha(changed):raise RuntimeError('HOLD_PROXY_RESTART')
  candidates=('/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
              '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3')
  code=("import chat_proxy; from fastapi.routing import APIRoute; "
        "assert all(any(isinstance(r,APIRoute) and r.path==p and 'POST' in r.methods "
        "for r in chat_proxy.app.routes) for p in ('/api/nox/chat/stream','/api/nox/stop'));"
        " print('ROUTES_VERIFIED')")
  registered=False
  for interpreter in candidates:
   if not Path(interpreter).is_file():continue
   cp=subprocess.run([interpreter,'-c',code],cwd='/root/nox/scripts',capture_output=True,text=True,timeout=12)
   if cp.returncode==0 and 'ROUTES_VERIFIED' in cp.stdout:registered=True;break
  if not registered:raise RuntimeError('HOLD_REGISTERED_ROUTES_NOT_VERIFIED')
  codes=[]
  for route in ('/api/nox/chat/stream','/api/nox/stop'):
   req=urllib.request.Request('http://127.0.0.1:8080'+route,
       data=b'{}',method='POST',headers={'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=4) as r:result=r.status
   except urllib.error.HTTPError as e:result=e.code
   codes.append(result)
  if codes!=[401,401]:raise RuntimeError('HOLD_AUTH_NOT_ENFORCED')
  emit(state='NATIVE_V29_STREAM_AND_SESSION_STOP_BOUND',new_sha256=sha(changed),
       bridge_sha256=BSHA,backup_verified=sha(BACKUP.read_bytes())==OLD,
       route_registration_verified=True,unauthenticated_http=codes,
       chat_http=200,model_http=200,full_web_92_functions_complete=False,
       real_authenticated_browser_e2e_tested=False,
       model_weights_unchanged=True,s03_data_unmodified_by_install=True)
 except Exception:
  did=revert(original,meta)
  emit(state='HOLD_ROLLED_BACK' if did else 'HOLD_ROLLBACK_UNVERIFIED',rollback=did)
except Exception as exc:
 s=str(exc)
 emit(state=s if s.startswith('HOLD_') and len(s)<90 else 'HOLD_NATIVE_PRECHECK',
      weights_unchanged=True)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    source=Path(__file__).parent.parent/'v105'/'native_v29_chat_bridge.py'
    code=source.read_bytes()
    remote=REMOTE_TEMPLATE.replace('___BRIDGE_SHA___',hashlib.sha256(code).hexdigest())
    remote=remote.replace('___BRIDGE_BASE64___',base64.b64encode(code).decode())
    ssh.REMOTE=remote;ssh.api=attach
    log=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(log):ok=ssh.probe()
    except Exception as exc:
        s=str(exc);print('NOX_V106='+s if s.startswith('HOLD_') else 'NOX_V106=HOLD_TRANSPORT')
    finally:
        try:
            with contextlib.redirect_stdout(log):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    rows=[]
    for line in log.getvalue().splitlines():
        if line.startswith('NATIVE_V106_RESULT=') and len(line)<1800:
            rows.append(line);print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
    accepted=ok and len(rows)==1 and 'NATIVE_V29_STREAM_AND_SESSION_STOP_BOUND' in rows[0]
    print('NOX_V106_NATIVE_ACCEPTED='+str(bool(accepted)).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
