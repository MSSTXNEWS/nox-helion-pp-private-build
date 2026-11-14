"""Apply only the V109 malformed-SSE guard to the EXISTING installed bridge.

Single existing Vast instance and nox-proxy. Never touches weights, S03, STOP,
model scheduler, GPU process or any web page. Exact live source SHA + idle slots
+ native supervisor health must all agree before atomic patch/restart.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

ORIGINAL_API = ssh.api


def settled_api(method, path, key, data=None):
    result = ORIGINAL_API(method, path, key, data)
    if method == "POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return result


REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast
import hashlib
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V111_SCHEMA=NOX_EXACT_SHA_ATOMIC_SSE_GUARD_V1')
P = Path('/root/nox/scripts/chat_proxy.py')
M = Path('/root/nox/scripts/nox_v29_chat_bridge.py')
OLD_PROXY='b7ba15d061fc6e518c2798ed42513c1113a115bc314d8cbaa3096a152d206d7f'
OLD_BRIDGE='1bc401535634f6a8856744c0ea62348b3f798d433c3cf7502e442aaf406d5129'
BACKUP=M.with_name(M.name+'.nox-v111-'+OLD_BRIDGE[:12]+'.bak')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
OLD='''    for choice in obj.get('choices') or []:
        if not isinstance(choice, dict):
            continue
        part = (choice.get('delta') or {}).get('content')
'''
NEW='''    choices = obj.get('choices')
    if not isinstance(choices, list):
        return ('', '')
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get('delta')
        if not isinstance(delta, dict):
            continue
        part = delta.get('content')
'''

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

def result(status, **extra):
    obj={'state':status,'live_model_changed':False,'s03_migrated':False,
         'full_browser_e2e_tested':False,'optimizer_steps_executed':0,**extra}
    print('NATIVE_V111_RESULT='+json.dumps(obj,sort_keys=True,separators=(',',':'))[:780])

def stopped():
    return any(Path(p).exists() for p in STOP)

def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status==200
    except Exception:
        return False

def status():
    try:
        x=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,
                         text=True,timeout=6)
        return x.returncode==0 and len(x.stdout.split())>1 and x.stdout.split()[1]=='RUNNING'
    except Exception:
        return False

def idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            slots=json.loads(r.read(60000))
        return (isinstance(slots,list) and len(slots)==6 and all(
            isinstance(x,dict) and
            (x.get('is_processing') if 'is_processing' in x else x.get('processing')) is False
            for x in slots))
    except Exception:
        return False

def auth_status(route):
    req=urllib.request.Request('http://127.0.0.1:8080'+route,method='POST',
            data=b'{}',headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=4) as r:return r.status
    except urllib.error.HTTPError as e:return e.code
    except Exception:return 0

def atomic(path, data, meta, tmpname):
    temp=path.with_name(tmpname)
    if temp.exists():raise RuntimeError('HOLD_TEMP_CONFLICT')
    with temp.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.chmod(temp,stat.S_IMODE(meta.st_mode))
    os.chown(temp,meta.st_uid,meta.st_gid)
    if digest(temp.read_bytes())!=digest(data):raise RuntimeError('HOLD_TEMP_DIGEST')
    os.replace(temp,path)

def restart():
    cp=subprocess.run(['supervisorctl','restart','nox-proxy'],capture_output=True,
                      timeout=35)
    if cp.returncode!=0:return False
    for attempt in range(20):
        if (health(8080) and health(8081) and status()
            and auth_status('/api/nox/chat/stream')==401
            and auth_status('/api/nox/stop')==401):
            return True
        time.sleep(1)
    return False

def rollback(old, meta):
    try:
        atomic(M,old,meta,'.nox-v111-rollback.tmp')
        return restart() and digest(M.read_bytes())==OLD_BRIDGE
    except Exception:
        return False

try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if not P.is_file() or P.is_symlink() or not M.is_file() or M.is_symlink():
        raise RuntimeError('HOLD_NATIVE_FILES')
    old=M.read_bytes();meta=M.stat()
    if digest(P.read_bytes())!=OLD_PROXY or digest(old)!=OLD_BRIDGE:
        raise RuntimeError('HOLD_LIVE_SOURCE_SHA_DRIFT')
    if meta.st_uid!=0 or meta.st_size>500000:
        raise RuntimeError('HOLD_MODULE_OWNER_OR_SIZE')
    text=old.decode('utf8')
    if text.count(OLD)!=1:
        raise RuntimeError('HOLD_V109_ANCHOR_MISSING_OR_MULTIPLE')
    changed=text.replace(OLD,NEW,1).encode('utf8')
    tree=ast.parse(changed.decode('utf8'))
    funcs={x.name for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
    if '_token_from_delta' not in funcs or 'register_native_v29_chat' not in funcs:
        raise RuntimeError('HOLD_MODULE_ENTRYPOINTS')
    compile(changed,str(M),'exec')
    if not health(8080) or not health(8081) or not status():
        raise RuntimeError('HOLD_CHAT_HEALTH')
    for _ in range(3):
        if stopped() or not idle():
            raise RuntimeError('HOLD_ACTIVE_CHAT')
        time.sleep(1)
    if (auth_status('/api/nox/chat/stream')!=401 or
        auth_status('/api/nox/stop')!=401):
        raise RuntimeError('HOLD_LIVE_AUTH_PRECHECK')
    if BACKUP.exists():
        if BACKUP.is_symlink() or digest(BACKUP.read_bytes())!=OLD_BRIDGE:
            raise RuntimeError('HOLD_BACKUP_SHA_CONFLICT')
    else:
        with BACKUP.open('xb') as f:
            f.write(old);f.flush();os.fsync(f.fileno())
        os.chmod(BACKUP,stat.S_IMODE(meta.st_mode))
        os.chown(BACKUP,meta.st_uid,meta.st_gid)
    if stopped() or not idle() or digest(P.read_bytes())!=OLD_PROXY or digest(M.read_bytes())!=OLD_BRIDGE:
        raise RuntimeError('HOLD_CONCURRENT_CHANGE_BEFORE_APPLY')
    atomic(M,changed,meta,'.nox-v111-stage.tmp')
    if restart() and digest(M.read_bytes())==digest(changed) and digest(P.read_bytes())==OLD_PROXY:
        result('STREAM_DELTA_GUARD_ACTIVE',module_sha256=digest(changed),
               original_sha256=OLD_BRIDGE,backed_up=True,
               health_and_unauthenticated_routes_verified=True)
    else:
        rolled=rollback(old,meta)
        result('HOLD_ROLLED_BACK' if rolled else 'HOLD_ROLLBACK_UNVERIFIED',
               original_sha256=OLD_BRIDGE,rollback_verified=rolled)
except Exception as e:
    s=str(e)
    result(s if s.startswith('HOLD_') and len(s)<95 else 'HOLD_NATIVE_PRECHECK')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


def main():
    ssh.REMOTE = REMOTE
    ssh.api = settled_api
    log=io.StringIO()
    accepted=False
    connected=False
    try:
        with contextlib.redirect_stdout(log):
            connected=ssh.probe()
    except Exception:
        print('NOX_V111=HOLD_SSH')
    finally:
        try:
            with contextlib.redirect_stdout(log):
                if not ssh.cleanup():
                    connected=False
        except Exception:
            connected=False
    cleanup=False
    outcomes=[]
    for line in log.getvalue().splitlines():
        if line.startswith('NATIVE_V111_RESULT=') and len(line)<900:
            print(line)
            outcomes.append(line)
        if line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
            if line.endswith('DETACHED_AND_VERIFIED') or line.endswith('ALREADY_ABSENT'):
                cleanup=True
    accepted=(connected and cleanup and len(outcomes)==1 and
              '"STREAM_DELTA_GUARD_ACTIVE"' in outcomes[0])
    print('NOX_V111_ACTIVATION='+('PASS' if accepted else 'HOLD'))
    return 0 if accepted else 2


if __name__=='__main__':
    raise SystemExit(main())
