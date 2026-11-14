"""Minimal V122 change to existing owner-only OneHost, SHA pinned and rollback.
Never replaces the whole bridge, changes models/S03, or creates a second server.
Requires V122 source regression and physical read-only preflight PASS.
"""
from __future__ import annotations
import base64,contextlib,hashlib,io,time
from pathlib import Path
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

SOURCE=Path('nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py')
REMOTE_TEMPLATE=r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import base64,hashlib,http.cookiejar,json,os,stat,subprocess,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V122_OWNER_UI_MINIMAL_SHA_GATED_NATIVE_V1')
P=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
PX=Path('/root/nox/scripts/chat_proxy.py')
WEB=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-ui.js')
OLD='cc27928b38f9b86d2375de8092d09dbdc34f81c6e51e8a68d36041ee71529750'
PX_SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
WEB_SHA='c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765'
OUTPUT_SHA='18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e'
FUN=base64.b64decode('___FUN64___',validate=True).decode('utf-8')
ROUTE=base64.b64decode('___ROUTE64___',validate=True).decode('utf-8')
BACK=P.with_name(P.name+'.nox-v122-'+OLD[:12]+'.bak')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP')
def digest(x):return hashlib.sha256(x).hexdigest()
def sha(p):return digest(p.read_bytes()) if p.is_file() and not p.is_symlink() else None
def stopped():return any(Path(p).exists() for p in STOP)
def service():
 try:
  r=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=4)
  v=r.stdout.split();return v[1] if r.returncode==0 and len(v)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status
 except Exception:return None
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:slots=json.loads(r.read(25000))
  return isinstance(slots,list) and len(slots)==6 and all(isinstance(x,dict) and not x.get('is_processing',x.get('processing',False)) for x in slots)
 except Exception:return False
def atomic(path,blob,meta,tempname):
 temp=path.with_name(tempname)
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_V122_TEMP_COLLISION')
 with temp.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
 if sha(temp)!=digest(blob):raise RuntimeError('HOLD_V122_ATOMIC_DIGEST')
 os.replace(temp,path)
def restart():
 subprocess.run(['supervisorctl','restart','nox-proxy'],timeout=16,check=True,capture_output=True)
 for i in range(12):
  if service()=='RUNNING' and health(8080)==200 and health(8081)==200:return True
  time.sleep(0.5)
 return False
def anonymous(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return None
def owner_checks():
 from chat_proxy import _read_chat_password
 secret=_read_chat_password()
 if not isinstance(secret,str) or len(secret)<6:raise RuntimeError('HOLD_V122_LOCAL_OWNER_SECRET')
 jar=http.cookiejar.CookieJar()
 client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 request=urllib.request.Request('http://127.0.0.1:8080/chat/login',data=json.dumps({'password':secret}).encode('utf8'),headers={'Content-Type':'application/json'},method='POST')
 secret=None
 with client.open(request,timeout=5) as r:
  if r.status!=200:raise RuntimeError('HOLD_V122_OWNER_LOGIN')
 with client.open('http://127.0.0.1:8080/chat/session',timeout=4) as r:
  if r.status!=200 or json.loads(r.read(2500)).get('ok') is not True:raise RuntimeError('HOLD_V122_SIGNED_SESSION')
 for endpoint in ('/api/nox/status','/api/nox/history','/api/nox/experience?q=NOX'):
  with client.open('http://127.0.0.1:8080'+endpoint,timeout=4) as r:
   if r.status!=200 or not isinstance(json.loads(r.read(250000)),dict):raise RuntimeError('HOLD_V122_S03_READBACK')
 with client.open('http://127.0.0.1:8080/nox-web-v29/nox-ui.js',timeout=5) as r:
  if r.status!=200:raise RuntimeError('HOLD_V122_NATIVE_JS_HTTP')
  result=digest(r.read(80000))
 try:
  logout=urllib.request.Request('http://127.0.0.1:8080/chat/logout',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
  client.open(logout,timeout=3).close()
 except Exception:pass
 return result
def emit(**values):print('NATIVE_V122_APPLY='+json.dumps(values,separators=(',',':'),sort_keys=True))
changed=False;before=None;meta=None
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if sha(P)!=OLD or sha(PX)!=PX_SHA or sha(WEB)!=WEB_SHA:raise RuntimeError('HOLD_CONCURRENT_SOURCE_SHA_DRIFT')
 if os.getuid()!=0 or service()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or not idle():raise RuntimeError('HOLD_NATIVE_BUSY')
 if not (1500<len(FUN)<5000 and 250<len(ROUTE)<1200):raise RuntimeError('HOLD_PATCH_BOUNDS')
 meta=P.stat();before=P.read_bytes();text=before.decode('utf8')
 anchor='class _OwnerStatic(StaticFiles):\n'
 response='        response=await super().get_response(path,scope)\n'
 if meta.st_uid!=0 or len(before)>120000 or text.count(anchor)!=1 or text.count(response)!=1:raise RuntimeError('HOLD_LIVE_ANCHORS')
 if '_overlay_v122_owner_ui' in text or 'HOLD_V122_NOX_UI_SOURCE_PIN' in text:raise RuntimeError('HOLD_ALREADY_INSTALLED')
 if 'import hashlib' not in text or 'from fastapi.responses import ' not in text:raise RuntimeError('HOLD_SOURCE_IMPORTS')
 next_text=text.replace(anchor,FUN+anchor,1).replace(response,response+ROUTE,1)
 compile(next_text,str(P),'exec')
 if len(next_text)>150000:raise RuntimeError('HOLD_NEW_BRIDGE_LENGTH')
 namespace={'hashlib':hashlib};exec(FUN,namespace)
 if digest(namespace['_overlay_v122_owner_ui'](WEB.read_bytes()))!=OUTPUT_SHA:raise RuntimeError('HOLD_PATCHED_JS_SHA')
 if sha(BACK) not in (None,OLD):raise RuntimeError('HOLD_BACKUP_COLLISION')
 if stopped() or not idle():raise RuntimeError('HOLD_NEW_CHAT_ACTIVITY')
 if not BACK.exists():
  with BACK.open('xb') as f:f.write(before);f.flush();os.fsync(f.fileno())
  os.chmod(BACK,stat.S_IMODE(meta.st_mode));os.chown(BACK,meta.st_uid,meta.st_gid)
 if sha(BACK)!=OLD:raise RuntimeError('HOLD_BACKUP_CHECK')
 atomic(P,next_text.encode('utf8'),meta,'.nox-v122-shadow.tmp');changed=True
 if not restart():raise RuntimeError('HOLD_POST_RESTART_HEALTH')
 if sha(WEB)!=WEB_SHA or sha(PX)!=PX_SHA:raise RuntimeError('HOLD_ORIGINAL_FILES_CHANGED')
 if anonymous('/nox-web-v29/nox-ui.js')!=401 or anonymous('/api/nox/activity')!=401:raise RuntimeError('HOLD_ANONYMOUS_AUTH')
 if owner_checks()!=OUTPUT_SHA:raise RuntimeError('HOLD_OWNER_COOKIE_SHADOW_SHA')
 emit(state='V122_LIVE_OWNER_UI_ACCEPTED',new_bridge_sha256=sha(P),backup_sha256=sha(BACK),frozen_source_sha256=sha(WEB),owner_js_sha256=OUTPUT_SHA,anonymous_http=[401,401],owner_http=200,original_s03_untouched=True,model_weights_changed=False,llama_restarted=False,proxy_restarted=True)
except Exception as ex:
 reason=str(ex)
 if not reason.startswith('HOLD_') or len(reason)>100:reason='HOLD_UNEXPECTED_'+type(ex).__name__
 rollback=None
 if changed:
  try:
   atomic(P,before,meta,'.nox-v122-revert.tmp')
   rollback=bool(restart() and sha(P)==OLD and health(8081)==200)
  except Exception:rollback=False
 emit(state=('HOLD_ROLLED_BACK' if rollback else 'HOLD_ROLLBACK_UNVERIFIED') if changed else reason,failed_gate=reason,rollback=rollback,model_weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    src=SOURCE.read_text(encoding='utf8')
    fun_marker='_V122_FROZEN_NOX_UI_SHA = '
    class_marker='class _OwnerStatic(StaticFiles):\n'
    response_marker='        response=await super().get_response(path,scope)\n'
    catalog_marker="        if path.lstrip('/') == 'nox-function-catalog.js'"
    if any(src.count(x)!=1 for x in (fun_marker,class_marker,response_marker,catalog_marker)):
        raise RuntimeError('HOLD_RUNNER_V122_SOURCE_ANCHORS')
    import ast
    tree=ast.parse(src)
    first=next(n.lineno for n in tree.body if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='_V122_FROZEN_NOX_UI_SHA' for t in n.targets))
    end=next(n.end_lineno for n in tree.body if isinstance(n,ast.FunctionDef)
             and n.name=='_overlay_v122_owner_ui')
    fragment=[n for n in tree.body if first<=n.lineno<=end]
    if len(fragment)!=3 or [type(n).__name__ for n in fragment]!=['Assign','Assign','FunctionDef']:
        raise RuntimeError('HOLD_RUNNER_PATCH_OVERREACH')
    fun=''.join(src.splitlines(keepends=True)[first-1:end])+'\n\n'
    route=src.split(response_marker,1)[1].split(catalog_marker,1)[0]
    if 'def _overlay_v122_owner_ui' not in fun or 'HOLD_V122_NOX_UI_SOURCE_PIN' not in route:
        raise RuntimeError('HOLD_RUNNER_PATCH_SOURCE')
    compile(fun,'<native shadow function>','exec')
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___FUN64___',base64.b64encode(fun.encode()).decode())
    ssh.REMOTE=ssh.REMOTE.replace('___ROUTE64___',base64.b64encode(route.encode()).decode())
    old=ssh.api
    def api(method,path,key,data=None):
        for i in range(4):
            try:
                result=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=api
    output=io.StringIO();transport=False;clean=False
    try:
        with contextlib.redirect_stdout(output):transport=ssh.probe()
    except Exception as exc:
        reason=str(exc)
        print('NOX_V122_INSTALL_TRANSPORT_HOLD='+(reason if reason.startswith('HOLD_') and len(reason)<90 else 'HOLD_SSH'))
    finally:
        try:
            with contextlib.redirect_stdout(output):clean=ssh.cleanup()
        except Exception:clean=False
    lines=output.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V122_APPLY=','TEMP_SSH_CLEANUP=')) and len(line)<1800:print(line)
    receipts=[line.split('=',1)[1] for line in lines if line.startswith('NATIVE_V122_APPLY=')]
    accepted=bool(transport and clean and len(receipts)==1 and 'V122_LIVE_OWNER_UI_ACCEPTED' in receipts[0]
                  and 'NATIVE_READ_ONLY_COMPLETE=true' in lines)
    print('NOX_V122_NATIVE_OWNER_UI_INSTALL_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
