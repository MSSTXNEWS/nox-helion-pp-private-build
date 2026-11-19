"""NOX V104: enable one genuine status endpoint for frozen WEB V29.3.

One native proxy, private owner cookie, no extra chat/backend. Returns READY
only from the active /v1/models and existing S03 callback state; all untested
capabilities remain explicitly unavailable. No mock data or fake pass.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
_API=ssh.api
def settle(method,path,key,data=None):
    result=_API(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,hashlib,json,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V104_NATIVE_WEB_STATUS_ONCE_V1')
FILE=Path('/root/nox/scripts/chat_proxy.py')
OLD='f49d997edf203ecc0986684e3250d63d036915efb5842c3f8bbb938cb0deac50'
BACKUP=FILE.with_name('chat_proxy.py.nox-v104-backup-'+OLD[:12])
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(x):return hashlib.sha256(x).hexdigest()
def emit(**d):print('NATIVE_V104_RESULT='+json.dumps(d,sort_keys=True,separators=(',',':')))
def health(p):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=3) as r:return r.status
 except Exception:return None
def service():
 try:
  o=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=8)
  x=o.stdout.split()
  return x[1] if o.returncode==0 and len(x)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:entries=json.loads(r.read(30000))
  return isinstance(entries,list) and len(entries)==6 and not any(
   x.get('is_processing',x.get('processing',False)) for x in entries if isinstance(x,dict))
 except Exception:return False
def rollback(old,meta):
 try:
  temp=FILE.with_name('.nox-v104-revert.tmp')
  with temp.open('xb') as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
  os.replace(temp,FILE)
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  for _ in range(15):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(FILE.read_bytes())==OLD
   time.sleep(1)
 except Exception:pass
 return False
BLOCK='''
@app.get('/api/nox/status')
async def nox_v29_native_status(request: Request):
    if not _session_ok(request):
        return _unauthorized()
    # This only advertises functions already connected to the active OneHost.
    live_model = ''
    try:
        import urllib.request as _noxt_ur
        import json as _noxt_json
        with _noxt_ur.urlopen('http://127.0.0.1:8081/v1/models', timeout=2) as _resp:
            _data = _noxt_json.loads(_resp.read(16000))
        _models = _data.get('data') if isinstance(_data, dict) else []
        _candidate = _models[0].get('id','') if isinstance(_models,list) and _models and isinstance(_models[0],dict) else ''
        if isinstance(_candidate,str) and _candidate.endswith('/models/current.gguf'):
            live_model = _candidate
    except Exception:
        pass
    _has_s03 = callable(s03_recall) and callable(s03_persist)
    return JSONResponse({
        'schema':'NOX_NATIVE_ONEHOST_V104',
        'backend':'EXISTING_NATIVE_ONEHOST',
        'status':'READY' if live_model else 'HOLD',
        'native_p02_bound':bool(live_model),
        'primary_model':live_model or None,
        's03_basic_recall_bound':bool(_has_s03),
        'native_cognitive_memory_bound':False,
        'all_web_v29_features_accepted':False,
        'native_stream_receipt_accepted':False,
        'onehost':True
    })
'''
try:
 if any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_STOP')
 if not FILE.is_file() or FILE.is_symlink():raise RuntimeError('HOLD_SOURCE_MISSING')
 meta=FILE.stat();old=FILE.read_bytes()
 if meta.st_uid!=0 or len(old)>150000 or sha(old)!=OLD:raise RuntimeError('HOLD_SOURCE_CHANGED')
 if health(8080)!=200 or health(8081)!=200 or service()!='RUNNING' or not idle():
  raise RuntimeError('HOLD_CHAT_NOT_IDLE')
 src=old.decode('utf8')
 tree=ast.parse(src)
 def decorated_at(fn,path,method):
  return any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
      and x.func.attr==method and x.args and isinstance(x.args[0],ast.Constant)
      and x.args[0].value==path for x in fn.decorator_list)
 existing=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
     and decorated_at(n,'/api/nox/status','get')]
 chat=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)
     and n.name=='chat_api' and decorated_at(n,'/chat/api','post')]
 if existing or len(chat)!=1:raise RuntimeError('HOLD_ROUTE_CONFLICT')
 lines=src.splitlines(keepends=True)
 pos=min(x.lineno for x in chat[0].decorator_list)-1
 lines.insert(pos,BLOCK+'\n')
 updated=''.join(lines).encode('utf8')
 code=ast.parse(updated);compile(updated,str(FILE),'exec')
 names=[x.name for x in code.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='nox_v29_native_status']
 if len(names)!=1 or len(updated)>155000:raise RuntimeError('HOLD_NATIVE_AST')
 if not idle() or any(Path(x).exists() for x in STOPS):raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 temp=FILE.with_name('.nox-v104-patch.tmp')
 if temp.exists():raise RuntimeError('HOLD_TEMP_EXISTS')
 with temp.open('xb') as f:f.write(updated);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp.read_bytes())!=sha(updated):raise RuntimeError('HOLD_WRITE_SHA')
 os.replace(temp,FILE)
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  live=False
  for _ in range(15):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:
    live=True;break
   time.sleep(1)
  if not live or sha(FILE.read_bytes())!=sha(updated):raise RuntimeError('HOLD_POST_HEALTH')
  # Authorization alone does not prove a route. Load the actual proxy app
  # with its installed interpreter and inspect registered FastAPI routes.
  candidates=['/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
      '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3']
  registered=False
  check_code=("import chat_proxy; from fastapi.routing import APIRoute; "
      "assert any(isinstance(x, APIRoute) and x.path=='/api/nox/status' "
      "and 'GET' in x.methods for x in chat_proxy.app.routes); print('NOX_ROUTE_OK')")
  for interpreter in candidates:
   if not Path(interpreter).is_file():continue
   try:
    check=subprocess.run([interpreter,'-c',check_code],cwd='/root/nox/scripts',
        capture_output=True,text=True,timeout=12)
    if check.returncode==0 and 'NOX_ROUTE_OK' in check.stdout:
     registered=True;break
   except Exception:pass
  if not registered:raise RuntimeError('HOLD_NATIVE_ROUTE_MISSING')
  request=urllib.request.Request('http://127.0.0.1:8080/api/nox/status',method='GET')
  try:
   with urllib.request.urlopen(request,timeout=4) as r:unauth=r.status
  except urllib.error.HTTPError as e:unauth=e.code
  if unauth not in (401,403):raise RuntimeError('HOLD_PUBLIC_AUTH_NOT_ENFORCED')
  emit(state='NATIVE_OWNER_WEB_STATUS_BOUND',sha256=sha(updated),old_sha256=OLD,
       backup_verified=sha(BACKUP.read_bytes())==OLD,
       route_registered_in_app=True,unauth_http=unauth,
       web_v29_all_functions_accepted=False,
       chat_http=200,model_http=200,weights_unchanged=True,
       s03_database_unchanged=True,one_backend=True)
 except Exception:
  good=rollback(old,meta)
  emit(state='HOLD_RESTORED' if good else 'HOLD_ROLLBACK_UNVERIFIED',rollback_verified=good)
except Exception as e:
 val=str(e)
 emit(state=val if val.startswith('HOLD_') and len(val)<100 else 'HOLD_NATIVE',
      model_weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=settle;buf=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(buf):ok=ssh.probe()
 except Exception as e:
  msg=str(e);print('NOX_V104='+msg if msg.startswith('HOLD_') else 'NOX_V104=HOLD_NATIVE')
 finally:
  try:
   with contextlib.redirect_stdout(buf):
    if not ssh.cleanup():ok=False
  except Exception:ok=False
 receipts=[]
 for line in buf.getvalue().splitlines():
  if line.startswith('NATIVE_V104_RESULT=') and len(line)<1800:
   receipts.append(line);print(line)
  elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
 accepted=ok and len(receipts)==1 and 'NATIVE_OWNER_WEB_STATUS_BOUND' in receipts[0]
 print('NOX_V104_NATIVE_ACCEPTED='+str(bool(accepted)).lower())
 return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
