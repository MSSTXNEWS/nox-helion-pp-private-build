"""V125 exact-SHA install into the existing NOX OneHost (not a second backend).

All changes require STOP/idle/health/resource/SHA admission. Copies ORIGINAL
S03 SQLite snapshot and proxy source before one guarded proxy restart. A
failed postflight rolls back the proxy source; never deletes S03 records.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

_ORIGINAL_API=ssh.api

def _api(method,path,key,data=None):
    result=_ORIGINAL_API(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return result

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast
import hashlib
import http.cookiejar as cookiejar
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_SCHEMA=ORIGINAL_S03_OWNER_FACT_ONEHOST_ROUTE_INSTALL_V1')
PROXY=Path('/root/nox/scripts/chat_proxy.py')
BRIDGE=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
MODULE=Path('/root/nox/scripts/nox_v125_owner_fact_write.py')
OLD_PROXY='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'
OLD_BRIDGE='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'
MODULE_SHA='___MODULE_SHA___'
BACKUP=PROXY.with_name('chat_proxy.py.nox-v125-'+OLD_PROXY[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
ANCHOR='register_nox_v120_s03_memory_views(app, globals())\n'
ADDITION=('from nox_v125_owner_fact_write import register_nox_v125_owner_fact_write\n'
          'register_nox_v125_owner_fact_write(app, globals())\n')
AUTH_OLD="'/api/nox/history','/api/nox/experience','/api/training/status'"
AUTH_NEW="'/api/nox/history','/api/nox/experience','/api/nox/memory/facts','/api/training/status'"

def sha(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(p).exists() for p in STOPS)
def emit(status,**data):
    result={'state':status,'new_backend':False,'new_s03_db':False,
            'model_weights_changed':False,'owner_credentials_exported':False,
            'full_weight_optimizer_steps':0,**data}
    print('NATIVE_V125_INSTALL='+json.dumps(result,sort_keys=True,separators=(',',':'))[:730])
def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status==200
    except Exception:return False
def status():
    try:
        p=subprocess.run(['supervisorctl','status','nox-proxy'],
                         capture_output=True,text=True,timeout=5)
        fields=p.stdout.split()
        return p.returncode==0 and len(fields)>1 and fields[1]=='RUNNING'
    except Exception:return False
def idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            slots=json.loads(r.read(50000))
        return isinstance(slots,list) and len(slots)==6 and all(
            isinstance(x,dict) and
            (x.get('is_processing') if 'is_processing' in x else x.get('processing')) is False
            for x in slots)
    except Exception:return False
def code_for(path,method='GET',data=None,opener=None):
    payload=None if data is None else json.dumps(data).encode('utf8')
    request=urllib.request.Request('http://127.0.0.1:8080'+path,
                method=method,data=payload,
                headers={'Content-Type':'application/json'})
    try:
        caller=opener.open if opener is not None else urllib.request.urlopen
        with caller(request,timeout=5) as resp:
            return resp.status,resp.read(12000)
    except urllib.error.HTTPError as ex:
        return ex.code,ex.read(12000)
    except Exception:return 0,b''
def atomic(new,meta,name):
    temp=PROXY.with_name(name)
    if temp.exists() or temp.is_symlink():
        raise RuntimeError('HOLD_V125_ATOMIC_STAGE_COLLISION')
    with temp.open('xb') as f:
        f.write(new);f.flush();os.fsync(f.fileno())
    os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
    if sha(temp.read_bytes())!=sha(new):
        raise RuntimeError('HOLD_V125_STAGE_HASH')
    os.replace(temp,PROXY)
def restart():
    p=subprocess.run(['supervisorctl','restart','nox-proxy'],
                     capture_output=True,timeout=36)
    if p.returncode!=0:return False
    for _ in range(22):
        if status() and health(8080) and health(8081):return True
        time.sleep(0.6)
    return False
def rollback(previous,meta,new_sha):
    try:
        if sha(PROXY.read_bytes())!=new_sha:return False
        atomic(previous,meta,'.nox-v125-revert.tmp')
        return restart() and sha(PROXY.read_bytes())==OLD_PROXY
    except Exception:return False
def snapshot_s03():
    import s03_memory
    original=Path(s03_memory.DB)
    if not original.is_file() or original.is_symlink():
        raise RuntimeError('HOLD_ORIGINAL_S03_FILE')
    if not 0<original.stat().st_size<268435456:
        raise RuntimeError('HOLD_S03_SIZE_BUDGET')
    if shutil.disk_usage(str(original.parent)).free < (11*1024**3):
        raise RuntimeError('HOLD_S03_BACKUP_DISK_BUDGET')
    destination=original.with_name(original.name+'.nox-v125-verified.sqlite3')
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise RuntimeError('HOLD_S03_BACKUP_SYMLINK')
        with sqlite3.connect('file:'+str(destination)+'?mode=ro',uri=True,timeout=4) as c:
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise RuntimeError('HOLD_S03_EXISTING_BACKUP_CORRUPT')
        return sha(destination.read_bytes()),destination.stat().st_size
    tmp=destination.with_name(destination.name+'.tmp')
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError('HOLD_S03_BACKUP_TEMP_CONFLICT')
    with sqlite3.connect('file:'+str(original)+'?mode=ro',uri=True,timeout=4) as source:
        if source.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_ORIGINAL_S03_QUICK_CHECK')
        with sqlite3.connect(str(tmp),timeout=4) as dest:
            source.backup(dest,pages=128,sleep=0.05)
    os.chmod(tmp,0o600)
    with sqlite3.connect('file:'+str(tmp)+'?mode=ro',uri=True,timeout=4) as chk:
        if chk.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_S03_BACKUP_INTEGRITY')
    if shutil.disk_usage(str(original.parent)).free < (10*1024**3):
        raise RuntimeError('HOLD_S03_POSTBACKUP_DISK_FLOOR')
    os.replace(tmp,destination)
    return sha(destination.read_bytes()),destination.stat().st_size

original=None
meta=None
new_sha=None
patched=False
try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if any(not p.is_file() or p.is_symlink() for p in (PROXY,BRIDGE,MODULE)):
        raise RuntimeError('HOLD_NATIVE_SOURCE_NOT_REGULAR')
    original=PROXY.read_bytes();meta=PROXY.stat()
    module=MODULE.read_bytes()
    if meta.st_uid!=0 or meta.st_size>200000 or sha(original)!=OLD_PROXY:
        raise RuntimeError('HOLD_CONCURRENT_PROXY_SOURCE_SHA')
    if sha(BRIDGE.read_bytes())!=OLD_BRIDGE or sha(module)!=MODULE_SHA:
        raise RuntimeError('HOLD_BRIDGE_OR_STAGED_FACT_SHA')
    ast.parse(module.decode('utf8'));compile(module,str(MODULE),'exec')
    source=original.decode('utf8')
    if (source.count(ANCHOR)!=1 or source.count(AUTH_OLD)!=1
        or source.count('register_nox_v125_owner_fact_write(')!=0):
        raise RuntimeError('HOLD_REGISTRATION_OR_AUTH_ANCHOR')
    modified=source.replace(ANCHOR,ANCHOR+ADDITION,1).replace(AUTH_OLD,AUTH_NEW,1)
    ast.parse(modified);compile(modified,str(PROXY),'exec')
    modified=modified.encode('utf8')
    new_sha=sha(modified)
    if len(modified)>220000:raise RuntimeError('HOLD_V125_PROXY_SIZE')
    if not (health(8080) and health(8081) and status()):
        raise RuntimeError('HOLD_NATIVE_HEALTH')
    pre_http=code_for('/api/nox/memory/facts','POST',{})[0]
    # The route is not yet installed: 404 (not registered) and 401
    # (middleware challenge) are both fail-closed safe preconditions.
    if pre_http not in (401,404):
        raise RuntimeError('HOLD_ANONYMOUS_FACT_ROUTE_PRECHECK')
    for attempt in range(3):
        if stopped() or not idle():
            raise RuntimeError('HOLD_ACTIVE_CHAT_PRECHECK')
        time.sleep(0.6)
    if BACKUP.exists() or BACKUP.is_symlink():
        if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD_PROXY:
            raise RuntimeError('HOLD_PROXY_BACKUP_CONFLICT')
    else:
        with BACKUP.open('xb') as f:
            f.write(original);f.flush();os.fsync(f.fileno())
        os.chmod(BACKUP,stat.S_IMODE(meta.st_mode))
        os.chown(BACKUP,meta.st_uid,meta.st_gid)
    if sha(BACKUP.read_bytes())!=OLD_PROXY:
        raise RuntimeError('HOLD_PROXY_BACKUP_NOT_VERIFIED')
    s03_backup_sha,s03_bytes=snapshot_s03()
    if (stopped() or not idle() or sha(PROXY.read_bytes())!=OLD_PROXY
        or sha(BRIDGE.read_bytes())!=OLD_BRIDGE
        or sha(MODULE.read_bytes())!=MODULE_SHA):
        raise RuntimeError('HOLD_CONCURRENT_CHANGE_BEFORE_WRITE')
    atomic(modified,meta,'.nox-v125-source-stage.tmp')
    patched=True
    if not restart() or stopped() or sha(PROXY.read_bytes())!=new_sha:
        raise RuntimeError('HOLD_POST_INSTALL_HEALTH')
    if code_for('/api/nox/memory/facts','POST',{})[0]!=401:
        raise RuntimeError('HOLD_ANONYMOUS_FACT_AUTH')
    import chat_proxy
    registered=[r for r in chat_proxy.app.routes
                if getattr(r,'path','')=='/api/nox/memory/facts'
                and 'POST' in getattr(r,'methods',set())]
    if len(registered)!=1:
        raise RuntimeError('HOLD_FACT_ROUTE_REGISTRATION')
    if not idle() or not health(8081):
        raise RuntimeError('HOLD_CHAT_POST_INSTALL_ACTIVE')
    # Official owner cookie login and *negative* JSON test, never a fact write here.
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:
        raise RuntimeError('HOLD_OWNER_SECRET')
    jar=cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login,_=code_for('/chat/login','POST',{'password':password},opener)
    password=None
    if login!=200 or not list(jar):
        raise RuntimeError('HOLD_OWNER_LOGIN')
    if code_for('/chat/session',opener=opener)[0]!=200:
        raise RuntimeError('HOLD_OWNER_SESSION')
    status_code,response=code_for('/api/nox/memory/facts','POST',{},opener)
    if status_code!=422 or json.loads(response).get('error')!='INVALID_FACT_KEY':
        raise RuntimeError('HOLD_FACT_ROUTE_OWNER_JSON_CONTRACT')
    try:code_for('/chat/logout','POST',{},opener)
    except Exception:pass
    emit('ORIGINAL_S03_FACT_API_BOUND_AUTH_VERIFIED',
         new_proxy_sha256=new_sha,staged_module_sha256=MODULE_SHA,
         original_s03_backup_sha256=s03_backup_sha,
         s03_backup_bytes=s03_bytes,rollback_source_sha_verified=True,
         anonymous_fact_http=401,owner_bad_payload_http=422,
         new_actual_s03_fact_tested=False,onehost_only=True)
except Exception as exc:
    message=str(exc)
    if patched:
        result=rollback(original,meta,new_sha)
        emit('HOLD_ROLLED_BACK' if result else 'HOLD_ROLLBACK_UNVERIFIED',
             rollback_verified=result,
             reason=message if message.startswith('HOLD_') and len(message)<95
                    else type(exc).__name__)
    else:
        emit(message if message.startswith('HOLD_') and len(message)<95
             else 'HOLD_NATIVE_PRECHECK')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    from pathlib import Path
    import hashlib
    module=Path('nox_runpod/teacher_mesh/v125/owner_fact_write.py').read_bytes()
    expected=hashlib.sha256(module).hexdigest()
    ssh.REMOTE=REMOTE.replace('___MODULE_SHA___',expected)
    ssh.api=_api
    out=io.StringIO()
    connected=False
    detached=False
    try:
        with contextlib.redirect_stdout(out):connected=ssh.probe()
    except Exception:
        print('NOX_V125_INSTALL=HOLD_SSH_CONNECT')
    finally:
        try:
            with contextlib.redirect_stdout(out):detached=ssh.cleanup()
        except Exception:detached=False
    receipts=[]
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V125_INSTALL=') and len(line)<800:
            print(line);receipts.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    passed=(connected and detached and len(receipts)==1 and
            '"state":"ORIGINAL_S03_FACT_API_BOUND_AUTH_VERIFIED"' in receipts[0])
    print('NOX_V125_FACT_API_NATIVE_INSTALL='+('PASS' if passed else 'HOLD'))
    return 0 if passed else 2

if __name__=='__main__':
    raise SystemExit(main())
