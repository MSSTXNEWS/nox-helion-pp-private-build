"""V118: single SHA-locked WEB V29 nested bootstrap + catalog navigation repair.

Exact SHA, STOP, idle, native auth, retained backup and immediate rollback.
No original WEB ZIP, model, S03, primary UI page, new backend or GPU changes.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

_BASE_API=ssh.api
def _settled(method,path,key,data=None):
    result=_BASE_API(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):
        time.sleep(12)
    return result

REMOTE=r'''
set -euo pipefail
/root/nox/venv/bin/python - <<'PYREMOTE'
import ast,hashlib,http.cookiejar,json,os,stat,subprocess,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V118_SCHEMA=EXACT_SHA_AUTH_CATALOG_AND_NESTED_BOOTSTRAP_V124')
M=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
P=Path('/root/nox/scripts/chat_proxy.py')
WEB=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-function-catalog.js')
OLD='066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'
PROXY='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
CATALOG='c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'
HEAD_OLD='<head><script src="./native-owner.js"></script>'
HEAD_NEW='<head><script src="/nox-web-v29/native-owner.js"></script>'
BACKUP=M.with_name('nox_v29_chat_bridge.py.v118-'+OLD[:12]+'.bak')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop',
       '/workspace/NOX_STOP','/root/nox/program/STOP')
OLD_ROUTE="""        response=await super().get_response(path,scope)
        if response.status_code != 200 or not (path.endswith('.html') or path in ('.','','/')):
"""
NEW_ROUTE="""        response=await super().get_response(path,scope)
        if path.lstrip('/') == 'nox-function-catalog.js' and response.status_code == 200:
            file=Path(getattr(response,'path',''))
            if not file.is_file() or file.is_symlink():
                return Response('HOLD_CATALOG_FILE', status_code=409)
            try:
                js=_catalog_owner_overlay(file.read_bytes())
            except (ValueError, OSError, UnicodeDecodeError):
                return Response('HOLD_CATALOG_SOURCE_PIN', status_code=409)
            return Response(js, media_type='application/javascript', headers={
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        if response.status_code != 200 or not (path.endswith('.html') or path in ('.','','/')):
"""
HELPER="""_FROZEN_V29_CATALOG_SHA = 'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'
_ORIGINAL_CATALOG_LINK = "const path=page=>native?'/nox/'+page:(files[page]||page)+'.html';"
_STAGED_CATALOG_LINK = (
    "const path=page=>native&&location.pathname.startsWith('/nox-web-v29/')?"
    "'/nox-web-v29/'+(files[page]||page)+'.html':"
    "native?'/nox/'+page:(files[page]||page)+'.html';"
)

def _catalog_owner_overlay(raw: bytes, expected_sha: str = _FROZEN_V29_CATALOG_SHA) -> bytes:
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('HOLD_FROZEN_V29_CATALOG_SHA')
    source = raw.decode('utf-8')
    if source.count(_ORIGINAL_CATALOG_LINK) != 1:
        raise ValueError('HOLD_CATALOG_LINK_SOURCE_DRIFT')
    return source.replace(_ORIGINAL_CATALOG_LINK, _STAGED_CATALOG_LINK, 1).encode('utf-8')


"""
def sha(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(x).exists() for x in STOPS)
def emit(status,**details):
    values={'state':status,'weights_unchanged':True,'s03_unchanged':True,
            'frozen_web_unchanged':True,'production_home_switched':False,**details}
    print('NATIVE_V118_RESULT='+json.dumps(values,sort_keys=True,separators=(',',':'))[:760])
def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status==200
    except Exception:return False
def running():
    try:
        r=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
        tokens=r.stdout.split()
        return r.returncode==0 and len(tokens)>1 and tokens[1]=='RUNNING'
    except Exception:return False
def idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            data=json.loads(r.read(60000))
        return isinstance(data,list) and len(data)==6 and all(
            isinstance(x,dict) and
            (x.get('is_processing') if 'is_processing' in x else x.get('processing')) is False
            for x in data)
    except Exception:return False
def http_code(url):
    try:
        with urllib.request.urlopen(url,timeout=5) as r:return r.status
    except urllib.error.HTTPError as e:return e.code
    except Exception:return 0
def atomic(data,meta,name):
    temp=M.with_name(name)
    if temp.exists() or temp.is_symlink():raise RuntimeError('HOLD_TEMP_CONFLICT')
    with temp.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.chmod(temp,stat.S_IMODE(meta.st_mode));os.chown(temp,meta.st_uid,meta.st_gid)
    if sha(temp.read_bytes())!=sha(data):raise RuntimeError('HOLD_STAGE_SHA')
    os.replace(temp,M)
def restart():
    p=subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,timeout=40)
    if p.returncode!=0:return False
    for step in range(18):
        if health(8080) and health(8081) and running():return True
        time.sleep(1)
    return False
def restore(original,meta):
    try:
        atomic(original,meta,'.nox-v118-rollback.tmp')
        return restart() and sha(M.read_bytes())==OLD
    except Exception:return False
def accepted_owner_catalog():
    # Everything stays within Vast localhost. Do not log cookie or password.
    import sys
    sys.path.insert(0,'/root/nox/scripts')
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:return False
    jar=http.cookiejar.CookieJar()
    op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def req(path,method='GET',data=None):
        payload=None if data is None else json.dumps(data).encode('utf8')
        return urllib.request.Request('http://127.0.0.1:8080'+path,
                    data=payload,method=method,headers={'Content-Type':'application/json'})
    try:
        with op.open(req('/chat/login','POST',{'password':password}),timeout=5) as resp:
            if resp.status!=200:return False
        password=None
        if not any(True for _ in jar):return False
        with op.open(req('/chat/session'),timeout=5) as resp:
            session=json.loads(resp.read(2000))
            if resp.status!=200 or session.get('ok') is not True:return False
        with op.open(req('/nox-web-v29/nox-function-catalog.js'),timeout=6) as resp:
            js=resp.read(40000)
            if resp.status!=200 or resp.headers.get('Cache-Control')!='no-store':return False
        if not (b"/nox-web-v29/" in js and b"location.pathname.startsWith" in js
                and sha(WEB.read_bytes())==CATALOG):return False
        for path in ('/nox-web-v29/chat.html','/nox-web-v29/pc/pages/cinema/index.html'):
            with op.open(req(path),timeout=8) as resp:
                if resp.status!=200 or HEAD_NEW.encode() not in resp.read(500000):return False
            if http_code('http://127.0.0.1:8080'+path)!=401:return False
        with op.open(req('/nox-web-v29/native-owner.js'),timeout=6) as resp:
            if resp.status!=200 or b'NOX_NATIVE_OWNER = true;' not in resp.read(2500):return False
        return True
    except Exception:return False
    finally:
        try:
            with op.open(req('/chat/logout','POST',{}),timeout=3):pass
        except Exception:pass
patched=False
try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if any(not f.is_file() or f.is_symlink() for f in (P,M,WEB)):
        raise RuntimeError('HOLD_MISSING_REGULAR_SOURCES')
    before=M.read_bytes();meta=M.stat()
    if meta.st_uid!=0 or meta.st_size>120000 or sha(before)!=OLD or sha(P.read_bytes())!=PROXY:
        raise RuntimeError('HOLD_CONCURRENT_PROXY_OR_BRIDGE_SHA_DRIFT')
    original_cat=WEB.read_bytes()
    if sha(original_cat)!=CATALOG or original_cat.count(b"const path=page=>native?'/nox/'+page")==0:
        raise RuntimeError('HOLD_FROZEN_CATALOG_DRIFT')
    if before.count(OLD_ROUTE.encode())!=1 or b'_catalog_owner_overlay' in before or before.count(b'class _OwnerStatic')!=1:
        raise RuntimeError('HOLD_BRIDGE_STRUCTURE_CHANGED')
    if before.count(HEAD_OLD.encode())!=1 or HEAD_NEW.encode() in before:
        raise RuntimeError('HOLD_NATIVE_OWNER_HEAD_ANCHOR')
    changed=before.decode('utf8').replace('class _OwnerStatic',HELPER+'class _OwnerStatic',1)
    changed=changed.replace(OLD_ROUTE,NEW_ROUTE,1).replace(HEAD_OLD,HEAD_NEW,1).encode('utf8')
    ast.parse(changed.decode('utf8'));compile(changed,str(M),'exec')
    if len(changed)>120000:raise RuntimeError('HOLD_PATCH_TOO_LARGE')
    if not (health(8080) and health(8081) and running()):
        raise RuntimeError('HOLD_EXISTING_SERVICES_UNHEALTHY')
    for attempt in range(3):
        if stopped() or not idle():raise RuntimeError('HOLD_ACTIVE_CHAT')
        time.sleep(1)
    if http_code('http://127.0.0.1:8080/nox-web-v29/nox-function-catalog.js')!=401:
        raise RuntimeError('HOLD_ANONYMOUS_CATALOG_NOT_PROTECTED')
    if BACKUP.exists():
        if BACKUP.is_symlink() or sha(BACKUP.read_bytes())!=OLD:raise RuntimeError('HOLD_BACKUP_CONFLICT')
    else:
        with BACKUP.open('xb') as f:
            f.write(before);f.flush();os.fsync(f.fileno())
        os.chmod(BACKUP,stat.S_IMODE(meta.st_mode));os.chown(BACKUP,meta.st_uid,meta.st_gid)
    if stopped() or not idle() or sha(M.read_bytes())!=OLD or sha(P.read_bytes())!=PROXY:
        raise RuntimeError('HOLD_CONCURRENT_CHANGE_PRE_RESTART')
    atomic(changed,meta,'.nox-v118-staging.tmp')
    patched=True
    if (restart() and sha(M.read_bytes())==sha(changed) and
        http_code('http://127.0.0.1:8080/nox-web-v29/nox-function-catalog.js')==401 and
        accepted_owner_catalog()):
        emit('V118_NATIVE_CATALOG_LINKS_ACTIVE',new_bridge_sha256=sha(changed),
             original_bridge_backup_verified=True,authorized_js_served=True,
             nested_pages_verified=2,anonymous_js_http=401)
    else:
        rolled=restore(before,meta)
        emit('HOLD_ROLLED_BACK' if rolled else 'HOLD_ROLLBACK_UNVERIFIED',
             rollback_verified=rolled)
except Exception as exc:
    reason=str(exc)
    if patched:
        recovered=restore(before,meta)
        emit('HOLD_ROLLED_BACK' if recovered else 'HOLD_ROLLBACK_UNVERIFIED',
             rollback_verified=recovered)
    else:
        emit(reason if reason.startswith('HOLD_') and len(reason)<85 else 'HOLD_V118_PRECHECK')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''


def main():
    ssh.REMOTE=REMOTE
    ssh.api=_settled
    capture=io.StringIO()
    worked=False
    try:
        with contextlib.redirect_stdout(capture):
            worked=ssh.probe()
    except Exception:
        print('NOX_V118=HOLD_NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(capture):
                if not ssh.cleanup():worked=False
        except Exception:worked=False
    rows=[]
    key_revoked=False
    for line in capture.getvalue().splitlines():
        if line.startswith('NATIVE_V118_RESULT=') and len(line)<800:
            rows.append(line)
            print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
            key_revoked=key_revoked or line.endswith('DETACHED_AND_VERIFIED')
    accepted=(worked and key_revoked and len(rows)==1 and
              '"state":"V118_NATIVE_CATALOG_LINKS_ACTIVE"' in rows[0])
    print('NOX_V118_STAGED_CATALOG_LIVE='+('PASS' if accepted else 'HOLD'))
    return 0 if accepted else 2


if __name__=='__main__':
    raise SystemExit(main())
