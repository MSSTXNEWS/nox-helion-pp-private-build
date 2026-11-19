"""V125: attach five real owner-only status API routes to EXISTING OneHost.

Preimage is pinned to actual post-V122 bridge SHA. No new daemon, SQLite,
GPU training, checkpoint mutation or PC-control shell. Backup+rollback.
"""
from __future__ import annotations
import ast,base64,contextlib,hashlib,io,time
from pathlib import Path
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MODULE=Path('nox_runpod/teacher_mesh/v125/live_owner_readonly.py')
BRIDGE_SHA='d0590c2a582bd4ad0df5ff26a036284cf1426e31ca41b283cf1695c7726f7cd5'
PROXY_SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
REMOTE_TEMPLATE=r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,base64,hashlib,http.cookiejar as cookiejar,json,os,sqlite3,stat,subprocess,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_SCHEMA=REAL_OWNER_SERVER_TELEMETRY_V1')
P=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
PX=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v125_live_readonly.py')
OLD='___BRIDGE_SHA___'
PX_EXPECTED='___PROXY_SHA___'
B=base64.b64decode('___MODULE_BASE64___',validate=True)
MOD_SHA='___MODULE_SHA___'
ANCHOR='    directory=Path(site_dir) if site_dir is not None else SITE\n'
SNIPPET=("    from nox_v125_live_readonly import register_nox_v125_live_readonly\n"
         "    register_nox_v125_live_readonly(app,trusted)\n")
BACK=P.with_name(P.name+'.nox-v125-'+OLD[:12]+'.bak')
PX_BACK=PX.with_name(PX.name+'.nox-v125-'+PX_EXPECTED[:12]+'.bak')
PROXY_OLD_GUARD="if (request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) or request.url.path in ('/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory','/api/nox/history','/api/nox/experience','/api/training/status')) and _session_ok(request):"
PROXY_NEW_GUARD="if (request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) or request.url.path in ('/api/health','/api/nox/activity','/api/nox/model','/api/nox/memory','/api/nox/history','/api/nox/experience','/api/training/status','/api/status','/api/nox/system/processes','/api/nox/premium/status','/api/nox/premium/capabilities','/api/nox/training/status')) and _session_ok(request):"
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(data):return hashlib.sha256(data).hexdigest()
def file_sha(path):
 return sha(path.read_bytes()) if path.is_file() and not path.is_symlink() else None
def stopped():return any(Path(p).exists() for p in STOP)
def service():
 try:
  p=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=5)
  parts=p.stdout.split()
  return parts[1] if p.returncode==0 and len(parts)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status==200
 except Exception:return False
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:rows=json.loads(r.read(30000))
  return isinstance(rows,list) and len(rows)==6 and all(
   isinstance(x,dict) and x.get('is_processing',x.get('processing',None)) is False for x in rows)
 except Exception:return False
def atomic(dest,data,meta,tmpname):
 tmp=dest.with_name(tmpname)
 if tmp.exists() or tmp.is_symlink():raise RuntimeError('HOLD_TEMP_CONFLICT')
 with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(meta.st_mode));os.chown(tmp,meta.st_uid,meta.st_gid)
 if file_sha(tmp)!=sha(data):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(tmp,dest)
def restart():
 p=subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=20)
 if p.returncode!=0:return False
 for _ in range(18):
  if service()=='RUNNING' and health(8080) and health(8081):return True
  time.sleep(.45)
 return False
def http(op,path):
 request=urllib.request.Request('http://127.0.0.1:8080'+path,method='GET',
                                headers={'Accept':'application/json'})
 try:return op.open(request,timeout=5)
 except urllib.error.HTTPError as e:return e
def owner_test():
 from chat_proxy import _read_chat_password
 password=_read_chat_password()
 if not isinstance(password,str) or len(password)<6:raise RuntimeError('HOLD_LOCAL_OWNER_CREDENTIAL')
 jar=cookiejar.CookieJar()
 op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 req=urllib.request.Request('http://127.0.0.1:8080/chat/login',
       data=json.dumps({'password':password}).encode('utf8'),
       headers={'Content-Type':'application/json'},method='POST')
 password=None
 with op.open(req,timeout=6) as auth:
  if auth.status!=200:raise RuntimeError('HOLD_LOGIN_HTTP')
 with http(op,'/chat/session') as sess:
  if sess.status!=200 or json.loads(sess.read(2000)).get('ok') is not True:
   raise RuntimeError('HOLD_OWNER_SESSION')
 routes=['/api/status','/api/nox/system/processes','/api/nox/premium/status',
         '/api/nox/premium/capabilities','/api/nox/training/status']
 results=[]
 try:
  for route in routes:
   with http(urllib.request.build_opener(),route) as anon:
    if anon.status!=401:raise RuntimeError('HOLD_ANONYMOUS_'+route.split('/')[-1].upper())
   with http(op,route) as owner:
    if owner.status!=200:raise RuntimeError('HOLD_OWNER_HTTP_'+str(owner.status)+'_'+route.strip('/').replace('/','_').upper()[:40])
    body=json.loads(owner.read(110000))
   if not isinstance(body,dict) or 'status' not in body:
    raise RuntimeError('HOLD_ROUTE_BODY')
   if route=='/api/status':
    if body.get('status')!='READY' or body.get('scope')!='VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC' or not body.get('gpus'):
     raise RuntimeError('HOLD_GPU_METRIC_SOURCE')
   if route=='/api/nox/system/processes':
    if body.get('observed_count',0)<=0 or body.get('read_only') is not True:
     raise RuntimeError('HOLD_NATIVE_PROCESSES')
   if route=='/api/nox/premium/capabilities':
    if body.get('schema')!='NOX_NATIVE_CONTROLLER_V2' or body.get('features',{}).get('training',{}).get('full_weight_optimizer_verified') is not False:
     raise RuntimeError('HOLD_CAPABILITY_SCHEMA')
   if route=='/api/nox/training/status':
    if body.get('verified_live') is not False:
     raise RuntimeError('HOLD_FAKE_TRAINING_STATUS')
   results.append(route)
  with http(op,'/api/nox/status') as original:
   if original.status!=200:raise RuntimeError('HOLD_ORIGINAL_CHAT_STATUS')
 finally:
  try:
   logout=urllib.request.Request('http://127.0.0.1:8080/chat/logout',
      data=b'{}',headers={'Content-Type':'application/json'},method='POST')
   op.open(logout,timeout=3).close()
  except Exception:pass
 return len(results)
def s03_status():
 try:
  import s03_memory
  db=Path(s03_memory.DB)
  if not db.is_file() or db.is_symlink():raise RuntimeError('HOLD_S03_FILE')
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as cx:
   cx.execute('PRAGMA query_only=ON')
   quick=cx.execute('PRAGMA quick_check').fetchone()[0]
  return quick=='ok'
 except Exception:return False
def emit(**d):print('NATIVE_V125_RESULT='+json.dumps(d,sort_keys=True,separators=(',',':')))
patched_bridge=False;patched_proxy=False;before=None;meta=None;pxbefore=None;pxmeta=None
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if os.getuid()!=0 or file_sha(P)!=OLD or file_sha(PX)!=PX_EXPECTED:
  raise RuntimeError('HOLD_NATIVE_SOURCE_SHA_DRIFT')
 v=os.statvfs('/root/nox')
 if v.f_bavail*v.f_frsize<512*1024*1024:raise RuntimeError('HOLD_DISK_RESERVE')
 if sha(B)!=MOD_SHA or not 3000<=len(B)<=22000:raise RuntimeError('HOLD_SOURCE_MODULE_SHA')
 compile(B,str(M),'exec')
 tree=ast.parse(B)
 if not any(isinstance(n,ast.FunctionDef) and n.name=='register_nox_v125_live_readonly' for n in tree.body):
  raise RuntimeError('HOLD_NEW_ROUTE_MODULE_SCHEMA')
 if service()!='RUNNING' or not health(8080) or not health(8081) or not idle() or not s03_status():
  raise RuntimeError('HOLD_BUSY_OR_S03_HEALTH')
 before=P.read_bytes();meta=P.stat();source=before.decode('utf8')
 if meta.st_uid!=0 or len(source)>160000 or source.count(ANCHOR)!=1 or 'register_nox_v125_live_readonly(' in source:
  raise RuntimeError('HOLD_BRIDGE_SOURCE_ANCHOR')
 changed=source.replace(ANCHOR,SNIPPET+ANCHOR,1).encode('utf8')
 compile(changed,str(P),'exec')
 pxbefore=PX.read_bytes();pxmeta=PX.stat();pxsource=pxbefore.decode('utf8')
 if pxmeta.st_uid!=0 or len(pxsource)>200000 or pxsource.count(PROXY_OLD_GUARD)!=1:
  raise RuntimeError('HOLD_AUTH_GUARD_SOURCE_DRIFT')
 pxchanged=pxsource.replace(PROXY_OLD_GUARD,PROXY_NEW_GUARD,1).encode('utf8')
 compile(pxchanged,str(PX),'exec')
 if M.exists():
  if file_sha(M)!=MOD_SHA:raise RuntimeError('HOLD_NATIVE_MODULE_CONFLICT')
 else:
  atomic(M,B,meta,'.nox-v125-module.tmp')
 if file_sha(M)!=MOD_SHA:raise RuntimeError('HOLD_MODULE_STAGE')
 p=subprocess.run(['/root/nox/venv/bin/python','-c',
   'from nox_v125_live_readonly import register_nox_v125_live_readonly; assert callable(register_nox_v125_live_readonly)'],
   cwd='/root/nox/scripts',capture_output=True,timeout=10)
 if p.returncode!=0:raise RuntimeError('HOLD_NATIVE_IMPORT')
 if file_sha(P)!=OLD or file_sha(PX)!=PX_EXPECTED or stopped() or not idle():
  raise RuntimeError('HOLD_CONCURRENT_SOURCE_OR_CHAT')
 if BACK.exists():
  if file_sha(BACK)!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
 else:
  with BACK.open('xb') as f:f.write(before);f.flush();os.fsync(f.fileno())
  os.chmod(BACK,stat.S_IMODE(meta.st_mode));os.chown(BACK,meta.st_uid,meta.st_gid)
 if file_sha(BACK)!=OLD:raise RuntimeError('HOLD_BACKUP_VERIFY')
 if PX_BACK.exists():
  if file_sha(PX_BACK)!=PX_EXPECTED:raise RuntimeError('HOLD_PROXY_BACKUP_CONFLICT')
 else:
  with PX_BACK.open('xb') as f:f.write(pxbefore);f.flush();os.fsync(f.fileno())
  os.chmod(PX_BACK,stat.S_IMODE(pxmeta.st_mode));os.chown(PX_BACK,pxmeta.st_uid,pxmeta.st_gid)
 if file_sha(PX_BACK)!=PX_EXPECTED:raise RuntimeError('HOLD_PROXY_BACKUP_VERIFY')
 if stopped() or file_sha(P)!=OLD or file_sha(PX)!=PX_EXPECTED or not idle():
  raise RuntimeError('HOLD_CONCURRENT_BEFORE_ATOMIC')
 atomic(PX,pxchanged,pxmeta,'.nox-v125-proxy.tmp')
 patched_proxy=True
 atomic(P,changed,meta,'.nox-v125-bridge.tmp')
 patched_bridge=True
 if not restart() or file_sha(P)!=sha(changed) or file_sha(PX)!=sha(pxchanged) or not s03_status():
  raise RuntimeError('HOLD_POST_RESTART_HEALTH')
 count=owner_test()
 if count!=5 or stopped():raise RuntimeError('HOLD_POST_ROUTE_ACCEPTANCE')
 emit(state='V125_NATIVE_OWNER_READS_ACTIVE',routes_owner_cookie_pass=count,
   routes_anonymous_http401=count,new_bridge_sha256=file_sha(P),
   new_proxy_sha256=file_sha(PX),module_sha256=file_sha(M),
   original_backup_verified=True,original_proxy_backup_verified=True,
   original_s03_quick_check='ok',model_weights_unchanged=True,
   original_frozen_web_unchanged=True,primary_chat_endpoint_preserved=True,
   physical_windows_pc_telemetry_claimed=False)
except Exception as exc:
 reason=str(exc)
 if not reason.startswith('HOLD_') or len(reason)>100:reason='HOLD_V125_'+type(exc).__name__
 if patched_bridge or patched_proxy:
  try:
   if patched_bridge:
    atomic(P,before,meta,'.nox-v125-rollback.tmp')
   if patched_proxy:
    atomic(PX,pxbefore,pxmeta,'.nox-v125-proxy-rollback.tmp')
   restored=restart() and file_sha(P)==OLD and file_sha(PX)==PX_EXPECTED
  except Exception:restored=False
  emit(state='HOLD_ROLLED_BACK' if restored else 'HOLD_ROLLBACK_UNVERIFIED',
       reason=reason,rollback_verified=restored,model_weights_unchanged=True)
 else:
  emit(state=reason,live_changes=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


def main():
    raw=MODULE.read_bytes()
    if not 3000<=len(raw)<=22000:
        raise RuntimeError('HOLD_V125_LOCAL_MODULE_SIZE')
    tree=ast.parse(raw)
    if not any(isinstance(n,ast.FunctionDef) and n.name=='register_nox_v125_live_readonly' for n in tree.body):
        raise RuntimeError('HOLD_V125_LOCAL_SOURCE')
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___BRIDGE_SHA___',BRIDGE_SHA)
    ssh.REMOTE=ssh.REMOTE.replace('___PROXY_SHA___',PROXY_SHA)
    ssh.REMOTE=ssh.REMOTE.replace('___MODULE_SHA___',hashlib.sha256(raw).hexdigest())
    ssh.REMOTE=ssh.REMOTE.replace('___MODULE_BASE64___',base64.b64encode(raw).decode())
    original=ssh.api
    def retry(method,path,key,data=None):
        for attempt in range(4):
            try:
                output=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return output
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or attempt==3:
                    raise
                time.sleep((10,20,40)[attempt])
    ssh.api=retry
    output=io.StringIO()
    good=False
    try:
        with contextlib.redirect_stdout(output):good=ssh.probe()
    except Exception as exc:
        reason=str(exc)
        print('NOX_V125_CONNECTION_HOLD='+(reason if reason.startswith('HOLD_') else 'SSH_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if ssh.cleanup() is not True:good=False
        except Exception:good=False
    proof=[]
    for line in output.getvalue().splitlines():
        if line.startswith('NATIVE_V125_RESULT=') and len(line)<800:
            proof.append(line)
            print(line)
        elif line.startswith(('TEMP_SSH_CLEANUP=','SSH_FAILURE_CLASS=','SSH_ATTEMPT_')):
            print(line[:170])
    passed=bool(good and len(proof)==1 and
         'V125_NATIVE_OWNER_READS_ACTIVE' in proof[0] and
         'NATIVE_READ_ONLY_COMPLETE=true' in output.getvalue())
    print('NOX_V125_NATIVE_OWNER_API='+('PASS' if passed else 'HOLD'))
    return 0 if passed else 2

if __name__=='__main__':
    raise SystemExit(main())
