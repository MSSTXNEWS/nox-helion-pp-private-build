"""V112 guarded upgrade of the EXISTING authenticated OneHost V108 V29 bridge.

Replace exactly one PINNED Python source file, add ONLY S03 dialog tables
to the existing database, test route registration and owner-auth denials.
No alternate model, no new backend, no new DB, no P02/S03 data removal.
Automatic original-source rollback on service/route failure.
"""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
from pathlib import Path
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE_TEMPLATE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import base64,hashlib,json,os,stat,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V112_NATIVE_REAL_S03_WEB_OWNER_STAGE_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
SITE=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js')
EXPECTED_PROXY='b7ba15d061fc6e518c2798ed42513c1113a115bc314d8cbaa3096a152d206d7f'
EXPECTED_BRIDGE='1bc401535634f6a8856744c0ea62348b3f798d433c3cf7502e442aaf406d5129'
EXPECTED_WEB='d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce'
NEW=base64.b64decode('___SOURCE_BASE64___',validate=True)
NEW_SHA='___SOURCE_SHA256___'
BACKUP=M.with_name('nox_v29_chat_bridge.py.nox-v112-'+EXPECTED_BRIDGE[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(b):return hashlib.sha256(b).hexdigest()
def emit(**kw):print('NATIVE_V112_RESULT='+json.dumps(kw,sort_keys=True,separators=(',',':')))
def stopped():return any(Path(s).exists() for s in STOPS)
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return None
def service():
 try:
  x=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=9)
  fields=x.stdout.split()
  return fields[1] if x.returncode==0 and len(fields)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:items=json.loads(r.read(30000))
  return (isinstance(items,list) and len(items)==6 and
          not any(x.get('is_processing',x.get('processing',False)) for x in items if isinstance(x,dict)))
 except Exception:return False
def atomic(blob,meta,name):
 path=M.with_name(name)
 if path.exists():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 os.chmod(path,stat.S_IMODE(meta.st_mode));os.chown(path,meta.st_uid,meta.st_gid)
 if sha(path.read_bytes())!=sha(blob):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(path,M)
def wait_ready():
 for _ in range(15):
  if service()=='RUNNING' and health(8080)==200 and health(8081)==200:return True
  time.sleep(1)
 return False
def rollback(original,meta):
 try:
  atomic(original,meta,'.nox-v112-rollback.tmp')
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  return wait_ready() and sha(M.read_bytes())==EXPECTED_BRIDGE
 except Exception:return False
def http(path,method):
 request=urllib.request.Request('http://127.0.0.1:8080'+path,
    data=(b'{}' if method=='POST' else None),method=method,
    headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(request,timeout=5) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return 0
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not P.is_file() or P.is_symlink() or not M.is_file() or M.is_symlink():
  raise RuntimeError('HOLD_SOURCE_MISSING_OR_LINKED')
 source=P.read_bytes(); old=M.read_bytes();meta=M.stat()
 if sha(source)!=EXPECTED_PROXY or sha(old)!=EXPECTED_BRIDGE or meta.st_uid!=0:
  raise RuntimeError('HOLD_PINNED_SOURCE_CHANGED')
 if not SITE.is_file() or sha(SITE.read_bytes())!=EXPECTED_WEB:
  raise RuntimeError('HOLD_WEB_SOURCE_SHA')
 if sha(NEW)!=NEW_SHA or not 10000<len(NEW)<60000:
  raise RuntimeError('HOLD_NEW_BRIDGE_SHA')
 compile(NEW,str(M),'exec')
 if health(8080)!=200 or health(8081)!=200 or service()!='RUNNING' or not idle():
  raise RuntimeError('HOLD_ACTIVE_OR_UNHEALTHY_ONEHOST')
 # Isolated native interpreter imports modified bridge BEFORE any live source mutation.
 verify=r'''
import sys
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,'/root/nox/scripts')
import chat_proxy
from fastapi.routing import APIRoute
from starlette.routing import Mount
items=chat_proxy.app.routes
required=('/api/nox/chat/stream','/api/nox/stop','/api/nox/status',
 '/api/ui/capabilities','/api/ui/memory/dialogs/status',
 '/api/ui/memory/dialogs','/api/ui/memory/dialogs/create',
 '/api/ui/memory/dialogs/history','/api/ui/memory/dialogs/update')
registered={r.path for r in items if isinstance(r,APIRoute)}
assert all(p in registered for p in required), 'HOLD_NEW_ROUTE_MISSING'
assert any(isinstance(r,Mount) and r.path=='/nox-web-v29' for r in items),'HOLD_OWNER_SITE_MISSING'
status=next(r for r in items if isinstance(r,APIRoute) and r.path=='/api/nox/status')
assert status.endpoint.__name__=='v29_owner_status','HOLD_LEGACY_STATUS_PRECEDENCE'
print('NOX_V112_ISOLATED_NATIVE_ROUTES_PASS')
'''
 candidates=('/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
             '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3')
 accepted=None
 with tempfile.TemporaryDirectory(prefix='nox-v112-verify-',dir='/root/nox/staging') as name:
  test=Path(name);(test/'chat_proxy.py').write_bytes(source)
  (test/'nox_v29_chat_bridge.py').write_bytes(NEW)
  for candidate in candidates:
   if not Path(candidate).is_file():continue
   result=subprocess.run([candidate,'-c',verify,str(test)],cwd=str(test),
                  capture_output=True,text=True,timeout=23)
   if result.returncode==0 and 'NOX_V112_ISOLATED_NATIVE_ROUTES_PASS' in result.stdout:
    accepted=candidate;break
  if accepted is None:raise RuntimeError('HOLD_ISOLATED_NATIVE_ROUTE_BINDING')
 if stopped() or not idle():raise RuntimeError('HOLD_BUSY_AFTER_PREFLIGHT')
 # Preexisting backup is allowed only when it matches exact original bytes.
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=EXPECTED_BRIDGE:
   raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACKUP.open('xb') as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=EXPECTED_BRIDGE:raise RuntimeError('HOLD_BACKUP_SHA')
 atomic(NEW,meta,'.nox-v112-bridge.tmp')
 try:
  # Additive migration to existing S03; never delete or rewrite native tables.
  migrate=subprocess.run([accepted,'-c',
      "import sys;sys.path.insert(0,'/root/nox/scripts');"
      "from nox_v29_chat_bridge import ensure_dialog_schema;"
      "assert ensure_dialog_schema();print('NOX_V112_EXISTING_S03_SCHEMA_PASS')"],
      cwd='/root/nox/scripts',capture_output=True,text=True,timeout=20)
  if migrate.returncode or 'NOX_V112_EXISTING_S03_SCHEMA_PASS' not in migrate.stdout:
   raise RuntimeError('HOLD_EXISTING_S03_ADDITIVE_MIGRATION')
  if stopped() or not idle():raise RuntimeError('HOLD_BUSY_BEFORE_RESTART')
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=30,check=True)
  if not wait_ready() or sha(M.read_bytes())!=NEW_SHA:
   raise RuntimeError('HOLD_POST_RESTART')
  # Exact runtime interpreter route binding again using installed sources.
  check=verify.replace("sys.path.insert(0,sys.argv[1]);sys.path.insert(1,'/root/nox/scripts')",
      "sys.path.insert(0,'/root/nox/scripts')")
  post=subprocess.run([accepted,'-c',check,'/root/nox/scripts'],
          cwd='/root/nox/scripts',capture_output=True,text=True,timeout=23)
  if post.returncode or 'NOX_V112_ISOLATED_NATIVE_ROUTES_PASS' not in post.stdout:
   raise RuntimeError('HOLD_LIVE_ROUTE_BINDING')
  protected=(('/api/nox/status','GET'),('/api/nox/chat/stream','POST'),
             ('/api/nox/stop','POST'),('/api/ui/capabilities','GET'),
             ('/api/ui/memory/dialogs/status','GET'),
             ('/api/ui/memory/dialogs/create','POST'),
             ('/nox-web-v29/','GET'),('/nox-web-v29/native-owner.js','GET'))
  codes=[http(route,method) for route,method in protected]
  if codes!=[401]*len(protected) or stopped():
   raise RuntimeError('HOLD_OWNER_AUTH_OR_STOP')
  emit(state='V112_NATIVE_S03_WEB_STAGING_BOUND',
       module_sha256=NEW_SHA,proxy_sha256=sha(P.read_bytes()),
       original_backup_verified=True,site_source_verified=True,
       existing_s03_dialog_tables_added=True,
       same_onehost_nox_proxy_running=True,
       unauthenticated_http=codes,
       authorized_browser_e2e_verified=False,
       full_web_92_api_e2e_verified=False,
       model_weights_changed=False,old_home_chat_replaced=False,
       gpu_stop_verified=False)
 except Exception:
  restored=rollback(old,meta)
  emit(state='HOLD_ROLLED_BACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',
       rollback=restored,existing_s03_original_tables_preserved=True)
except Exception as exc:
 message=str(exc)
 emit(state=message if message.startswith('HOLD_') and len(message)<120
      else 'HOLD_V112_PREFLIGHT',live_patched=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    module=Path(__file__).parent/'native_v29_full_bridge.py'
    source=module.read_bytes()
    raw=REMOTE_TEMPLATE.replace('___SOURCE_BASE64___',base64.b64encode(source).decode())
    raw=raw.replace('___SOURCE_SHA256___',hashlib.sha256(source).hexdigest())
    ssh.REMOTE=raw
    orig=ssh.api
    def gate(method,path,key,data=None):
        for idx in range(4):
            try:
                result=orig(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or idx==3:
                    raise
                time.sleep((10,20,40)[idx])
    ssh.api=gate
    captured=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(captured):
            ok=ssh.probe()
    except Exception as ex:
        err=str(ex)
        print('NOX_V112_HOLD='+(err if err.startswith('HOLD_') else 'CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(captured):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    receipt=[]
    for line in captured.getvalue().splitlines():
        if line.startswith('NATIVE_V112_RESULT=') and len(line)<1800:
            print(line);receipt.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    verified=bool(ok and len(receipt)==1 and 'V112_NATIVE_S03_WEB_STAGING_BOUND' in receipt[0])
    print('NOX_V112_NATIVE_DEPLOY_PASS='+str(verified).lower())
    return 0 if verified else 2

if __name__=='__main__':
    raise SystemExit(main())
