"""V119: verify V118 genuine read endpoints through actual owner cookie session.
No private data, owner password or cookie copied off Vast. No service mutation.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,http.cookiejar,json,sys,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V119_REAL_OWNER_READ_SURFACES_V1')
EXPECTED='58e7fb20eb87e582a3e52486dcc93899affc34aa7b80f029b09696c545353d16'
ROUTES=('/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory',
        '/api/training/status','/api/ui/memory/status')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(p).exists() for p in STOPS)
def emit(v):print('NATIVE_V119_RESULT='+json.dumps(v,separators=(',',':'),sort_keys=True))
def get(opener,path):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,method='GET')
 try:return opener.open(req,timeout=10)
 except urllib.error.HTTPError as ex:return ex
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
login_ok=False
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 file=Path('/root/nox/scripts/chat_proxy.py')
 if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=EXPECTED:
  raise RuntimeError('HOLD_WRONG_NATIVE_SOURCE')
 unauth=urllib.request.build_opener()
 codes=[get(unauth,p).status for p in ROUTES]
 if codes!=[401]*6:raise RuntimeError('HOLD_ANONYMOUS_AUTH')
 from chat_proxy import _read_chat_password
 password=_read_chat_password()
 if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_LOCAL_CREDENTIAL')
 req=urllib.request.Request('http://127.0.0.1:8080/chat/login',
      data=json.dumps({'password':password}).encode(),
      headers={'Content-Type':'application/json'},method='POST')
 with opener.open(req,timeout=8) as response:
  if response.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
 password=None
 login_ok=True
 if get(opener,'/chat/session').status!=200:raise RuntimeError('HOLD_COOKIE_SESSION')
 values={}
 for path in ROUTES:
  with get(opener,path) as r:
   if r.status!=200:raise RuntimeError('HOLD_OWNER_ROUTE_HTTP_'+str(r.status))
   obj=json.loads(r.read(26000))
  if not isinstance(obj,dict):raise RuntimeError('HOLD_REAL_DATA_SHAPE')
  values[path]=obj
 health=values['/api/health']
 activity=values['/api/nox/activity']
 model=values['/api/nox/model']
 memory=values['/api/nox/memory']
 training=values['/api/training/status']
 memory_ui=values['/api/ui/memory/status']
 if not (health.get('chat_http')==200 and health.get('model_http')==200):
  raise RuntimeError('HOLD_REAL_CHAT_MODEL_HEALTH')
 if not (type(activity.get('active_generations')) is int and
         0<=activity['active_generations']<=6 and isinstance(activity.get('busy'),bool)):
  raise RuntimeError('HOLD_REAL_ACTIVE_SLOTS')
 if model.get('status')!='READY' or not model.get('model_id'):
  raise RuntimeError('HOLD_REAL_MODEL_NOT_PRESENT')
 if (memory.get('original_s03_quick_check')!='ok' or
      type(memory.get('s03_items_count')) is not int or memory['s03_items_count']<1 or
      memory['s03_items_count']!=memory_ui.get('s03_items_count')):
  raise RuntimeError('HOLD_NATIVE_S03_COUNTS_MISMATCH')
 if (training.get('full_parameter_no_adapter_verified') is not False or
      training.get('checkpoint_restore_verified') is not False or
      training.get('verified_live') is not False):
  raise RuntimeError('HOLD_FALSE_FULL_TRAINING_CLAIM')
 if stopped():raise RuntimeError('HOLD_STOP_REVOKED')
 emit({'state':'NATIVE_V119_OWNER_REAL_READ_SURFACES_VERIFIED',
       'anonymous_http':codes,'owner_http':[200]*len(ROUTES),
       'chat_and_model_healthy':True,'active_generations':activity['active_generations'],
       'model_id_basename':Path(str(model['model_id'])).name[:70],
       'original_s03_quick_check':'ok','s03_items_count':memory['s03_items_count'],
       'training_supervisor_state':str(training.get('supervisor_state','UNKNOWN'))[:20],
       'full_weight_optimizer_unverified':True,'no_new_backend':True,
       'credentials_exported':False,'private_records_exported':False,
       'services_restarted':False,'weights_changed':False})
 print('NATIVE_V119_OWNER_DATA_HTTP_ACCEPTED=true')
except Exception as exc:
 msg=str(exc)
 emit({'state':msg if msg.startswith('HOLD_') and len(msg)<115 else 'HOLD_NATIVE_OWNER_READ',
       'exception_type':type(exc).__name__,'credentials_exported':False,
       'private_records_exported':False,'weights_changed':False})
finally:
 if login_ok:
  try:
   req=urllib.request.Request('http://127.0.0.1:8080/chat/logout',
       method='POST',data=b'{}',headers={'Content-Type':'application/json'})
   opener.open(req,timeout=4).close()
  except Exception:pass
 print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    original=ssh.api
    def safe(method,path,key,data=None):
        for index in range(4):
            try:
                result=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or index==3:raise
                time.sleep((10,20,40)[index])
    ssh.api=safe
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V119_RESULT=','NATIVE_V119_OWNER_DATA_HTTP_ACCEPTED=','TEMP_SSH_CLEANUP=')):
            print(line[:2400])
    accepted=bool(ok and 'NATIVE_V119_OWNER_DATA_HTTP_ACCEPTED=true' in lines)
    print('NOX_V119_OWNER_REAL_API_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
