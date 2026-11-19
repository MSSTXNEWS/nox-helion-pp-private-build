"""V108: bind existing V29 stream routes after all OneHost functions are defined.
No new LLM, DB or scheduler. SHA-pinned, idle-gated, undoable.
Release remains HOLD until authenticated V29 dialog scope, S03 and STOP E2E.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,os,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V108_NATIVE_V29_LATE_ROUTE_BINDING_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
EXPECTED='877af6fb10bc3ce4c456900e063c00f667362017c4fde0fe65b2a802075004ad'
BACKUP=P.with_name('chat_proxy.py.nox-v108-'+EXPECTED[:12]+'.bak')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(p).exists() for p in STOP)
def emit(**kwargs):print('NATIVE_V108_RESULT='+json.dumps(kwargs,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status
 except Exception:return None
def service():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=8)
  fields=p.stdout.split()
  return fields[1] if p.returncode==0 and len(fields)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:items=json.loads(r.read(24000))
  return isinstance(items,list) and len(items)==6 and not any(
     x.get('is_processing',x.get('processing',False)) for x in items if isinstance(x,dict))
 except Exception:return False
def atomic(data,meta,tmp):
 if tmp.exists():raise RuntimeError('HOLD_TEMP_FILE_EXISTS')
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
 if sha(tmp.read_bytes())!=sha(data):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(tmp,P)
def rollback(data,meta):
 try:
  atomic(data,meta,P.with_name('.nox-v108-revert.tmp'))
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  for _ in range(16):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(P.read_bytes())==EXPECTED
   time.sleep(1)
 except Exception:return False
 return False
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink() or not M.is_file() or M.is_symlink():
  raise RuntimeError('HOLD_SOURCE_OR_BRIDGE_MISSING')
 original=P.read_bytes();meta=P.stat()
 if meta.st_uid!=0 or sha(original)!=EXPECTED or len(original)>145000:
  raise RuntimeError('HOLD_SOURCE_SHA_OR_OWNER')
 bridge_source=M.read_bytes()
 if not 5000<len(bridge_source)<20000:raise RuntimeError('HOLD_BRIDGE_SIZE')
 compile(bridge_source,str(M),'exec')
 tree=ast.parse(original)
 names={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 for name in ('_session_ok','_unauthorized','_proxy_completion','nox_status'):
  if name not in names:raise RuntimeError('HOLD_EXISTING_NATIVE_FUNCTION_'+name)
 if 'register_native_v29_chat(' in original.decode():raise RuntimeError('HOLD_ALREADY_REGISTERED')
 if health(8080)!=200 or health(8081)!=200 or service()!='RUNNING' or not idle():
  raise RuntimeError('HOLD_ACTIVE_OR_UNHEALTHY_CHAT')
 # Source is imported as module by supervisord. Add registration only AFTER every
 # named native callback is declared, not above chat_api (which is too early).
 tail="""

# NOX V108: late registration on SAME authenticated OneHost app, not a second API.
from nox_v29_chat_bridge import register_native_v29_chat
register_native_v29_chat(app, globals())

@app.get('/api/nox/status')
async def nox_v29_status(request: Request):
    if not _session_ok(request):
        return _unauthorized()
    return await nox_status()
"""
 # __main__ may call uvicorn.run() and block execution forever.
 # Register before that guard, but after _proxy_completion and nox_status exist.
 guard=[n for n in tree.body if isinstance(n,ast.If)
        and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name)
        and n.test.left.id=='__name__'
        and any(isinstance(v,ast.Constant) and v.value=='__main__' for v in n.test.comparators)]
 if len(guard)!=1:raise RuntimeError('HOLD_UNIQUE_MAIN_GUARD')
 insertion=guard[0].lineno-1
 if max(names[k].end_lineno for k in ('_proxy_completion','_session_ok','_unauthorized','nox_status'))>=insertion+1:
  raise RuntimeError('HOLD_NATIVE_FUNCTIONS_NOT_DEFINED')
 lines=original.decode('utf8').splitlines(keepends=True)
 lines.insert(insertion,tail)
 new=''.join(lines).encode('utf8')
 compile(new,str(P),'exec')
 # Offline route registration proof with the exact same current runtime interpreter.
 # Never forward user data; no test chat generated.
 verify="""
import sys
sys.path.insert(0,'/root/nox/scripts')
import chat_proxy
paths={getattr(r,'path',''):r for r in chat_proxy.app.routes}
for name in ('/api/nox/chat/stream','/api/nox/stop','/api/nox/status'):
 assert name in paths, 'HOLD_MISSING_ROUTE'
print('NOX_V108_ISOLATED_ROUTES=PASS')
"""
 candidates=('/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
             '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3')
 # A disposable isolated source directory prevents overwriting live source before preflight.
 import tempfile
 with tempfile.TemporaryDirectory(prefix='nox-v108-check-',dir='/root/nox/staging') as d:
  directory=Path(d)
  (directory/'chat_proxy.py').write_bytes(new)
  (directory/'nox_v29_chat_bridge.py').write_bytes(bridge_source)
  # Actual native dependencies resolve through /root/nox/scripts, but the changed
  # chat_proxy resolves first from disposable import location.
  isolated_code=verify.replace("sys.path.insert(0,'/root/nox/scripts')",
      "sys.path.insert(0,"+repr(str(directory))+")\nsys.path.insert(1,'/root/nox/scripts')")
  accepted=False;last=''
  for candidate in candidates:
   if not Path(candidate).is_file():continue
   p=subprocess.run([candidate,'-c',isolated_code],cwd=str(directory),
                    text=True,capture_output=True,timeout=18)
   last='RET_'+str(p.returncode)
   if p.returncode==0 and 'NOX_V108_ISOLATED_ROUTES=PASS' in p.stdout:
    accepted=True;break
  if not accepted:raise RuntimeError('HOLD_ISOLATED_REGISTER_'+last)
 if stopped() or not idle():raise RuntimeError('HOLD_BUSY_DURING_PREFLIGHT')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(original);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=EXPECTED:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(new,meta,P.with_name('.nox-v108-bind.tmp'))
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  ready=False
  for _ in range(16):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:ready=True;break
   time.sleep(1)
  if not ready or sha(P.read_bytes())!=sha(new):raise RuntimeError('HOLD_RESTART_OR_SOURCE')
  codes=[]
  for path,method in (('/api/nox/chat/stream','POST'),('/api/nox/stop','POST'),('/api/nox/status','GET')):
   req=urllib.request.Request('http://127.0.0.1:8080'+path,
       data=(b'{}' if method=='POST' else None),
       headers={'Content-Type':'application/json'},method=method)
   try:
    with urllib.request.urlopen(req,timeout=5) as r:codes.append(r.status)
   except urllib.error.HTTPError as e:codes.append(e.code)
  if codes!=[401,401,401] or stopped():
   emit(state='NATIVE_OWNER_ROUTE_CODES_AUDIT',unauthenticated_http=codes,stop_active=stopped())
   raise RuntimeError('HOLD_OWNER_AUTH_ROUTES')
  emit(state='NATIVE_V29_LATE_ROUTES_REGISTERED',new_sha256=sha(new),
       backup_sha_verified=True,service='nox-proxy',model_health=200,
       unauthenticated_http=codes,owner_login_e2e_verified=False,
       native_s03_recall_unchanged=True,weights_changed=False,
       full_web_compatibility_verified=False)
 except Exception as issue:
  failure=str(issue)
  restored=rollback(original,meta)
  emit(state='HOLD_ROLLED_BACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',rollback=restored,
       failed_gate=failure[:95] if failure.startswith('HOLD_') else type(issue).__name__)
except Exception as exc:
 msg=str(exc)
 emit(state=msg if msg.startswith('HOLD_') and len(msg)<110 else 'HOLD_NATIVE_PREFLIGHT',
      live_patched=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def gate(method,path,key,data=None):
        for attempt in range(4):
            try:
                res=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return res
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
                time.sleep((10,20,40)[attempt])
    ssh.api=gate;out=io.StringIO();okay=False
    try:
        with contextlib.redirect_stdout(out):okay=ssh.probe()
    except Exception as exc:
        s=str(exc)
        print('NOX_V108_HOLD='+(s if s.startswith('HOLD_') else 'NATIVE_CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if not ssh.cleanup():okay=False
        except Exception:okay=False
    lines=[]
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V108_RESULT=') and len(line)<1700:
            lines.append(line);print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
    accepted=bool(okay and len(lines)==1 and 'NATIVE_V29_LATE_ROUTES_REGISTERED' in lines[0])
    print('NOX_V108_NATIVE_PASS='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
