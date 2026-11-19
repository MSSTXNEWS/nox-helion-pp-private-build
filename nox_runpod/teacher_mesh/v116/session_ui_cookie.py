"""V116: accept valid existing owner cookie at V29 UI routes in same OneHost.

The V112 app owns its own session authorization checks, but the original global
HTTP middleware only accepted API keys for /api/ui/ and /nox-web-v29/. Fix
that gate WITHOUT allowing anonymous requests, new sessions or new backends.

One SHA-pinned native hotfix, STOP, idle slots, backup, rollback and live 401 tests.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,os,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V116_EXISTING_COOKIE_UI_AUTH_FIX_V1')
SOURCE=Path('/root/nox/scripts/chat_proxy.py')
BRIDGE=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
OLD='b7ba15d061fc6e518c2798ed42513c1113a115bc314d8cbaa3096a152d206d7f'
BRIDGE_SHA='066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'
BACKUP=SOURCE.with_name('chat_proxy.py.nox-v116-cookie-backup-'+OLD[:12])
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(p).exists() for p in STOP)
def emit(**v):print('NATIVE_V116_RECEIPT='+json.dumps(v,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:return r.status
 except Exception:return None
def state():
 try:
  r=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
  tokens=r.stdout.split()
  return tokens[1] if r.returncode==0 and len(tokens)>1 else 'UNKNOWN'
 except Exception:return 'UNKNOWN'
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:items=json.loads(r.read(23000))
  return isinstance(items,list) and len(items)==6 and not any(x.get('is_processing',x.get('processing',False)) for x in items if isinstance(x,dict))
 except Exception:return False
def code(path,method):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,
     method=method,data=b'{}' if method=='POST' else None,
     headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=4) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return None
def atomic(data,stat_info,temp):
 if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_TEMP_FILE')
 with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(temp,stat.S_IMODE(stat_info.st_mode))
 os.chown(temp,stat_info.st_uid,stat_info.st_gid)
 if sha(temp.read_bytes())!=sha(data):raise RuntimeError('HOLD_TEMP_SHA')
 os.replace(temp,SOURCE)
def rollback(previous,stat_info):
 try:
  atomic(previous,stat_info,SOURCE.with_name('.nox-v116-cookie-rollback.tmp'))
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=32,check=True)
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    return sha(SOURCE.read_bytes())==OLD
   time.sleep(1)
 except Exception:return False
 return False
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not SOURCE.is_file() or SOURCE.is_symlink() or not BRIDGE.is_file() or BRIDGE.is_symlink():
  raise RuntimeError('HOLD_NO_AUTH_SOURCE')
 previous=SOURCE.read_bytes();meta=SOURCE.stat()
 if meta.st_uid!=0 or len(previous)>170000 or sha(previous)!=OLD:
  raise RuntimeError('HOLD_NATIVE_SOURCE_SHA')
 if sha(BRIDGE.read_bytes())!=BRIDGE_SHA:raise RuntimeError('HOLD_V112_BRIDGE_SHA')
 if state()!='RUNNING' or health(8080)!=200 or health(8081)!=200 or not idle():
  raise RuntimeError('HOLD_ACTIVE_OR_UNHEALTHY')
 text=previous.decode('utf8')
 tree=ast.parse(text)
 auth=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='auth_mw']
 if len(auth)!=1:raise RuntimeError('HOLD_MIDDLEWARE_FUNCTION')
 checks=[x for x in ast.walk(auth[0]) if isinstance(x,ast.Assign)
         and len(x.targets)==1 and isinstance(x.targets[0],ast.Name)
         and x.targets[0].id=='auth']
 if len(checks)!=1:
  emit(state='HOLD_MIDDLEWARE_ANCHOR',auth_assign_count=len(checks))
  raise RuntimeError('HOLD_MIDDLEWARE_ANCHOR')
 auth_line=checks[0].lineno
 original_lines=text.splitlines(keepends=True)
 if not original_lines[auth_line-1].startswith('    ') or original_lines[auth_line-1].startswith('        '):
  raise RuntimeError('HOLD_AUTH_FUNCTION_INDENT')
 rhs=ast.unparse(checks[0].value)
 if 'authorization' not in rhs or 'x-api-key' not in rhs:
  raise RuntimeError('HOLD_AUTH_SOURCE_SEMANTICS')
 if '_nox_v116_valid_owner_ui_session' in text:raise RuntimeError('HOLD_COOKIE_PATCH_ALREADY_PRESENT')
 newguard="""    # _nox_v116_valid_owner_ui_session: SAME existing signed cookie HMAC gate.
    # Only existing owner-authenticated V29 pages and UI routes may pass.
    # Individual V29 handlers apply _session_ok a second time.
    if request.url.path.startswith(('/api/ui/', '/nox-web-v29/')) and _session_ok(request):
        return await call_next(request)
"""
 original_lines.insert(auth_line-1,newguard)
 patched=''.join(original_lines)
 ast.parse(patched);compile(patched,str(SOURCE),'exec')
 middleware=[n for n in ast.parse(patched).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='auth_mw'][0]
 assert sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_session_ok'
            for n in ast.walk(middleware))>=1
 new=patched.encode('utf8')
 if len(new)>175000:raise RuntimeError('HOLD_PATCH_BYTES')
 if stopped() or not idle():raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
 if BACKUP.exists():
  if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_EXISTING_BACKUP_SHA')
 else:
  with BACKUP.open('xb') as f:f.write(previous);f.flush();os.fsync(f.fileno())
  os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
 if sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_VERIFY')
 atomic(new,meta,SOURCE.with_name('.nox-v116-cookie-patch.tmp'))
 try:
  subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=32,check=True)
  healthy=False
  for _ in range(18):
   if state()=='RUNNING' and health(8080)==200 and health(8081)==200:
    healthy=True;break
   time.sleep(1)
  if not healthy or sha(SOURCE.read_bytes())!=sha(new) or stopped():
   raise RuntimeError('HOLD_AFTER_RESTART')
  routes=[
   ('/api/ui/capabilities','GET'),
   ('/api/ui/memory/dialogs/status','GET'),
   ('/api/ui/memory/dialogs','GET'),
   ('/nox-web-v29/chat.html','GET'),
   ('/api/nox/status','GET'),
   ('/api/nox/chat/stream','POST')]
  codes=[code(path,method) for path,method in routes]
  if codes!=[401]*len(routes):raise RuntimeError('HOLD_UNAUTHORIZED_SESSION_BYPASS')
  emit(state='NATIVE_COOKIE_V29_UI_GATE_INSTALLED',new_sha256=sha(new),
       backup_sha_verified=True,service='nox-proxy',model_health=200,
       anonymous_http=codes,existing_cookie_HMAC_required=True,
       owner_cookie_e2e_tested=False,
       existing_s03_untouched=True,weights_changed=False)
 except Exception as ex:
  success=rollback(previous,meta)
  error=str(ex)
  emit(state='HOLD_ROLLED_BACK' if success else 'HOLD_ROLLBACK_UNVERIFIED',
       rollback=success,failed_gate=error if error.startswith('HOLD_') and len(error)<100 else type(ex).__name__)
except Exception as exc:
 x=str(exc)
 emit(state=x if x.startswith('HOLD_') and len(x)<110 else 'HOLD_NATIVE_AUTH_SOURCE',
      source_changed=False,weights_changed=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def settle(method,path,key,data=None):
        for index in range(4):
            try:
                value=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return value
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or index==3:raise
                time.sleep((10,20,40)[index])
    ssh.api=settle;out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    except Exception as ex:
        s=str(ex)
        print('NOX_V116_HOLD='+(s if s.startswith('HOLD_') and len(s)<100 else 'SSH_NATIVE'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    rows=[]
    for row in out.getvalue().splitlines():
        if row.startswith('NATIVE_V116_RECEIPT=') and len(row)<2200:
            rows.append(row);print(row)
        elif row.startswith('TEMP_SSH_CLEANUP='):print(row[:110])
    good=bool(ok and len(rows)==1 and 'NATIVE_COOKIE_V29_UI_GATE_INSTALLED' in rows[0])
    print('NOX_V116_NATIVE_COOKIE_GATE_PASS='+str(good).lower())
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
