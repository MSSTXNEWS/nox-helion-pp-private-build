"""V118 guarded native upgrade of existing NOX owner read-only routes.
Adds real data-only handlers to same FastAPI app, no second backend, database,
model or trainer. Every native operation has SHA gate, backup and rollback.
"""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
from pathlib import Path
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MODULE=Path('nox_runpod/teacher_mesh/v118/real_read_surfaces.py')
REMOTE_TEMPLATE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,base64,hashlib,json,os,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V118_GENUINE_OWNER_READ_SURFACES_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v118_real_read_surfaces.py')
OLD='568b5950cfbd263a96a106525f81de8fdc024526fe86fab7765a3c25baa180f8'
CODE=base64.b64decode('___CODE_BASE64___',validate=True)
MODULE_SHA='___CODE_SHA___'
BACKUP=P.with_name('chat_proxy.py.nox-v118-'+OLD[:12]+'.bak')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(p).exists() for p in STOP)
def emit(**kw):print('NATIVE_V118_RECEIPT='+json.dumps(kw,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=4) as r:return r.status
 except Exception:return None
def service():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],text=True,capture_output=True,timeout=7)
  a=p.stdout.split()
  return a[1] if p.returncode==0 and len(a)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:a=json.loads(r.read(26000))
  return isinstance(a,list) and len(a)==6 and not any(
    x.get('is_processing',x.get('processing',False)) for x in a if isinstance(x,dict))
 except Exception:return False
def atomic(path,data,meta,tmp_name):
 tmp=path.with_name(tmp_name)
 if tmp.exists() or tmp.is_symlink():raise RuntimeError('HOLD_ATOMIC_TEMP')
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
 if sha(tmp.read_bytes())!=sha(data):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(tmp,path)
def revert(previous,meta):
 try:
  atomic(P,previous,meta,'.nox-v118-revert.tmp')
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=35,check=True)
  for _ in range(17):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(P.read_bytes())==OLD
   time.sleep(1)
 except Exception:pass
 return False
def anon(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return None
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink() or not 4000<len(CODE)<20000 or sha(CODE)!=MODULE_SHA:
  raise RuntimeError('HOLD_SOURCE_OR_MODULE_SHA')
 meta=P.stat();previous=P.read_bytes()
 if meta.st_uid!=0 or sha(previous)!=OLD or len(previous)>180000:
  raise RuntimeError('HOLD_EXPECTED_ONEHOST_SHA')
 if service()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or not idle():
  raise RuntimeError('HOLD_BUSY_OR_HEALTH')
 module_ast=ast.parse(CODE)
 compile(CODE,str(M),'exec')
 if not any(isinstance(x,ast.FunctionDef) and x.name=='register_nox_v118_real_read_surfaces' for x in module_ast.body):
  raise RuntimeError('HOLD_MODULE_REGISTRATION')
 original=previous.decode('utf8')
 boot='register_native_v29_chat(app, globals())\n'
 extra='from nox_v118_real_read_surfaces import register_nox_v118_real_read_surfaces\nregister_nox_v118_real_read_surfaces(app, globals())\n'
 if original.count(boot)!=1 or 'register_nox_v118_real_read_surfaces(' in original:
  raise RuntimeError('HOLD_ONEHOST_REGISTER_ANCHOR')
 # The existing V116 owner HMAC cookie path is broadened ONLY to these read-only APIs.
 oldguard="if request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) and _session_ok(request):"
 newguard="if (request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) or request.url.path in ('/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory','/api/training/status')) and _session_ok(request):"
 if original.count(oldguard)!=1 or original.count('_nox_v116_valid_owner_ui_session')!=1:
  raise RuntimeError('HOLD_EXISTING_COOKIE_GUARD')
 changed=original.replace(boot,boot+extra,1).replace(oldguard,newguard,1)
 compile(changed,str(P),'exec')
 if len(changed)>195000:raise RuntimeError('HOLD_NEW_SOURCE_SIZE')
 if M.exists():
  if M.is_symlink() or sha(M.read_bytes())!=MODULE_SHA:
   raise RuntimeError('HOLD_MODULE_CONFLICT')
 else:
  # Module installed inert. It cannot be called before the OneHost restart.
  atomic(M,CODE,meta,'.nox-v118-module.tmp')
 # Native runtime isolated import: no user requests or credentials.
 isolated="""
import sys
sys.path.insert(0,'/root/nox/scripts')
from nox_v118_real_read_surfaces import register_nox_v118_real_read_surfaces
assert callable(register_nox_v118_real_read_surfaces)
print('NOX_V118_IMPORTED')
"""
 chk=subprocess.run(['/root/nox/venv/bin/python','-c',isolated],
                   text=True,capture_output=True,timeout=14)
 if chk.returncode!=0 or 'NOX_V118_IMPORTED' not in chk.stdout:
  raise RuntimeError('HOLD_NATIVE_MODULE_IMPORT')
 if stopped() or not idle():raise RuntimeError('HOLD_CHAT_BUSY_AFTER_CHECK')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:
   raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(previous);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(P,changed.encode('utf8'),meta,'.nox-v118-proxy.tmp')
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=35,check=True)
  ready=False
  for _ in range(18):
   if service()=='RUNNING' and health(8080)==200 and health(8081)==200:
    ready=True;break
   time.sleep(1)
  if not ready or sha(P.read_bytes())!=sha(changed.encode('utf8')) or stopped():
   raise RuntimeError('HOLD_NATIVE_POST_RESTART')
  paths=['/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory','/api/training/status','/api/ui/memory/status']
  anon_codes=[anon(p) for p in paths]
  if anon_codes!=[401]*len(paths):raise RuntimeError('HOLD_ANONYMOUS_AUTH_BYPASS')
  emit(state='NATIVE_V118_REAL_DATA_ROUTES_BOUND',new_proxy_sha256=sha(P.read_bytes()),
       module_sha256=MODULE_SHA,old_backup_sha_verified=True,
       unauthenticated_codes=anon_codes,registered_new_routes=paths,
       same_noX_host=True,no_new_db=True,services_healthy=True,
       real_owner_e2e_verified=False,private_data_exported=False,
       model_weights_changed=False)
 except Exception as exc:
  did=revert(previous,meta)
  msg=str(exc)
  emit(state='HOLD_ROLLED_BACK' if did else 'HOLD_ROLLBACK_UNVERIFIED',
       rollback=did,failed_gate=msg if msg.startswith('HOLD_') and len(msg)<100 else type(exc).__name__)
except Exception as exc:
 msg=str(exc)
 emit(state=msg if msg.startswith('HOLD_') and len(msg)<110 else 'HOLD_NATIVE_PREFLIGHT',
      model_weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    code=MODULE.read_bytes()
    compile(code,str(MODULE),'exec')
    script=REMOTE_TEMPLATE.replace('___CODE_BASE64___',base64.b64encode(code).decode())
    script=script.replace('___CODE_SHA___',hashlib.sha256(code).hexdigest())
    ssh.REMOTE=script
    original=ssh.api
    def gate(method,path,key,data=None):
        for i in range(4):
            try:
                val=original(method,path,key,data)
                if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
                return val
            except RuntimeError as exc:
                if method!="GET" or str(exc)!="HOLD_VAST_API_HTTP_429" or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=gate
    output=io.StringIO();okay=False
    try:
        with contextlib.redirect_stdout(output):okay=ssh.probe()
    except Exception as exc:
        msg=str(exc);print('NOX_V118_HOLD='+(msg if msg.startswith('HOLD_') else 'SSH_NATIVE'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if ssh.cleanup() is not True:okay=False
        except Exception:okay=False
    receipts=[]
    for line in output.getvalue().splitlines():
        if line.startswith('NATIVE_V118_RECEIPT=') and len(line)<2000:
            print(line);receipts.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:150])
    passed=bool(okay and len(receipts)==1 and 'NATIVE_V118_REAL_DATA_ROUTES_BOUND' in receipts[0])
    print('NOX_V118_REAL_NATIVE_ROUTES_ACCEPTED='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
