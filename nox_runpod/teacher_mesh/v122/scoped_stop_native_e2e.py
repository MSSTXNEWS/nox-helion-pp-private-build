"""NOX V122: one non-destructive owner-session scoped STOP acceptance on OneHost.

Proves that STOP belongs to the initiating owner cookie, that the native NDJSON
stream ends without a saved 'done' receipt, and that model slots become idle.
No service restart, model download, code replacement or training step.
No owner cookie, password, model answer or private S03 record exported.
"""
from __future__ import annotations

import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

ORIGINAL_API = ssh.api

def settled(method, path, key, data=None):
    result = ORIGINAL_API(method, path, key, data)
    if method == 'POST' and path.endswith('/ssh/'):
        time.sleep(12)
    return result

REMOTE = r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib
import http.cookiejar as cookiejar
import json
import queue
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V122_SCHEMA=NOX_REAL_OWNER_COOKIE_STOP_ISOLATION_V1')
PROXY_SHA = '4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
BRIDGE_SHA = '066ed91555a9a6251420b5897a040eda13a03b3d6c2d85b936e384c5f4113cd4'
STOP_FILES = ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
              '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
BASE = 'http://127.0.0.1:8080'

def emit(state, **data):
    receipt = {'state':state, 'one_synthetic_owner_turn':True,
               'proxy_restart':False, 'model_weights_changed':False,
               'backend_gpu_stop_verified':False,
               'private_records_exported':False,
               'owner_credentials_exported':False, **data}
    print('NATIVE_V122_RESULT='+json.dumps(
        receipt,sort_keys=True,separators=(',',':'))[:700])

def stopped():
    return any(Path(p).exists() for p in STOP_FILES)

def slots():
    with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
        rows=json.loads(r.read(30000))
    if not isinstance(rows,list) or len(rows)!=6 or not all(
        isinstance(x,dict) and
        isinstance((x.get('is_processing') if 'is_processing' in x else x.get('processing')),bool)
        for x in rows):
        raise RuntimeError('HOLD_MODEL_SLOTS_UNVERIFIED')
    return [x.get('is_processing') if 'is_processing' in x else x.get('processing') for x in rows]

def post(opener, path, payload, timeout=7):
    req=urllib.request.Request(BASE+path,method='POST',
        data=json.dumps(payload,ensure_ascii=False).encode('utf8'),
        headers={'Content-Type':'application/json'})
    try:
        return opener.open(req,timeout=timeout)
    except urllib.error.HTTPError as e:
        return e

def get(opener, path, timeout=5):
    req=urllib.request.Request(BASE+path,method='GET')
    try:
        return opener.open(req,timeout=timeout)
    except urllib.error.HTTPError as e:
        return e

def login(password):
    jar=cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with post(opener,'/chat/login',{'password':password}) as r:
        if r.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
    if not list(jar):raise RuntimeError('HOLD_SIGNED_OWNER_COOKIE_MISSING')
    with get(opener,'/chat/session') as r:
        if r.status!=200 or json.loads(r.read(2000)).get('ok') is not True:
            raise RuntimeError('HOLD_OWNER_SESSION_NOT_BOUND')
    return opener,jar

def scope(jar):
    data=sorted((c.name,c.value,c.path) for c in jar)
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()

owner_a=None
owner_b=None
stream_response=[None]
thread=[None]
q=queue.Queue(maxsize=4)
done=threading.Event()
seen_delta=threading.Event()
answer_events={'deltas':0,'done':False,'error':None,'http':None}
marker='noxv122stop_'+secrets.token_hex(6)

def worker():
    try:
        req=post(owner_a,'/api/nox/chat/stream',
                 {'message':'[QA '+marker+'] Перечисли числа от 1 до 90 через запятую, ничего не пропускай.',
                  'history':[],'stream':True},timeout=38)
        stream_response[0]=req
        answer_events['http']=req.status
        if req.status!=200:
            return
        for index,line in enumerate(req):
            if index>=600 or len(line)>80000:
                answer_events['error']='HOLD_OUTPUT_BOUNDS'
                break
            try:frame=json.loads(line)
            except (ValueError,TypeError):
                answer_events['error']='HOLD_NDJSON_PARSE'
                break
            kind=frame.get('type') if isinstance(frame,dict) else None
            if kind=='delta':
                answer_events['deltas']+=1
                seen_delta.set()
            elif kind=='error':
                answer_events['error']=str(frame.get('error',''))[:80]
                break
            elif kind=='done':
                answer_events['done']=True
                break
            elif kind not in ('preparing','start'):
                answer_events['error']='HOLD_UNKNOWN_STREAM_EVENT'
                break
    except Exception:
        answer_events['error']='HOLD_STREAM_TRANSPORT'
    finally:
        if stream_response[0] is not None:
            try:stream_response[0].close()
            except Exception:pass
        done.set()

def close_sessions():
    for session in (owner_a,owner_b):
        if session is not None:
            try:post(session,'/chat/logout',{},timeout=3).close()
            except Exception:pass

try:
    if stopped():raise RuntimeError('HOLD_STOP')
    proxy=Path('/root/nox/scripts/chat_proxy.py')
    bridge=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
    if not proxy.is_file() or proxy.is_symlink() or not bridge.is_file() or bridge.is_symlink():
        raise RuntimeError('HOLD_NATIVE_FILES')
    if (hashlib.sha256(proxy.read_bytes()).hexdigest()!=PROXY_SHA or
        hashlib.sha256(bridge.read_bytes()).hexdigest()!=BRIDGE_SHA):
        raise RuntimeError('HOLD_LIVE_SHA_DRIFT')
    if any(slots()):raise RuntimeError('HOLD_OWNER_CHAT_BUSY')
    with urllib.request.urlopen(BASE+'/health',timeout=3) as r:
        if r.status!=200:raise RuntimeError('HOLD_PROXY_HEALTH')
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:
        raise RuntimeError('HOLD_OWNER_LOCAL_AUTH_MISSING')
    owner_a,jar_a=login(password)
    owner_b,jar_b=login(password)
    password=None
    if scope(jar_a)==scope(jar_b):
        raise RuntimeError('HOLD_OWNER_SESSION_SCOPE_NOT_DISTINCT')
    with post(owner_b,'/api/nox/stop',{}) as r:
        if r.status!=409:raise RuntimeError('HOLD_SECOND_COOKIE_STOP_BASELINE')

    thread[0]=threading.Thread(target=worker,daemon=True)
    thread[0].start()
    if not seen_delta.wait(16):
        raise RuntimeError('HOLD_NO_NATIVE_FIRST_DELTA')
    if done.is_set():
        raise RuntimeError('HOLD_MODEL_FINISHED_BEFORE_STOP')

    # The second valid owner cookie must NOT cancel the first cookie's stream.
    with post(owner_b,'/api/nox/stop',{}) as r:
        cross_code=r.status
    if cross_code!=409:
        raise RuntimeError('HOLD_STOP_SESSION_ISOLATION')
    with post(owner_a,'/api/nox/stop',{}) as r:
        own_code=r.status
        response=json.loads(r.read(5000)) if own_code==200 else {}
    if own_code!=200 or response.get('status')!='STOP_REQUESTED':
        raise RuntimeError('HOLD_NATIVE_STOP_NOT_ACKNOWLEDGED')
    if response.get('gpu_stop_verified') is not False:
        raise RuntimeError('HOLD_GPU_STOP_ATTESTATION_UNEXPECTED')
    if not done.wait(20):
        raise RuntimeError('HOLD_STOP_STREAM_DID_NOT_FINISH')
    if answer_events['done'] or answer_events['error']!='STREAM_STOP_REQUESTED':
        raise RuntimeError('HOLD_STOP_MISSING_TERMINAL_ERROR')
    if answer_events['http']!=200:
        raise RuntimeError('HOLD_OWNER_STREAM_HTTP')
    quiet=False
    for count in range(14):
        if stopped():raise RuntimeError('HOLD_STOP_DURING_ACCEPTANCE')
        if not any(slots()):
            quiet=True
            break
        time.sleep(.5)
    if not quiet:
        raise RuntimeError('HOLD_MODEL_SLOTS_NOT_IDLE_AFTER_STOP')

    # Verify the existing S03 file was not given a completed QA exchange.
    import s03_memory
    db=Path(s03_memory.DB)
    if not db.is_file() or db.is_symlink():
        raise RuntimeError('HOLD_NATIVE_S03_NOT_FOUND')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as con:
        con.execute('PRAGMA query_only=ON')
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_S03_INTEGRITY')
        qa_count=con.execute('SELECT COUNT(*) FROM s03_items WHERE instr(text,?)>0',(marker,)).fetchone()[0]
    if qa_count:
        raise RuntimeError('HOLD_CANCELLED_QA_EXCHANGE_IN_S03')
    emit('V122_OWNER_STOP_S03_ISOLATION_PASS',
         own_stop_http=own_code,other_cookie_stop_http=cross_code,
         ndjson_stop_event=True,s03_cancelled_exchange_absent=True,
         s03_quick_check='ok',model_slots_idle_after=True,
         first_delta_seen=True,
         streamed_delta_count=answer_events['deltas'])
except Exception as exc:
    reason=str(exc)
    emit(reason if reason.startswith('HOLD_') and len(reason)<95 else 'HOLD_V122_STOP_RUNTIME',
         first_delta_seen=seen_delta.is_set(),stream_done=answer_events['done'],
         session_isolation_proven=False)
finally:
    # STOP only this test owner's scope; never touch a global stop file.
    if thread[0] is not None and thread[0].is_alive() and owner_a is not None:
        try:post(owner_a,'/api/nox/stop',{},timeout=4).close()
        except Exception:pass
        if stream_response[0] is not None:
            try:stream_response[0].close()
            except Exception:pass
        thread[0].join(2)
    close_sessions()
    print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    ssh.REMOTE=REMOTE
    ssh.api=settled
    log=io.StringIO()
    connected=False
    try:
        with contextlib.redirect_stdout(log):
            connected=ssh.probe()
    except Exception:
        print('NOX_V122=HOLD_NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(log):
                if not ssh.cleanup():
                    connected=False
        except Exception:
            connected=False
    receipts=[]
    revoked=False
    for line in log.getvalue().splitlines():
        if line.startswith('NATIVE_V122_RESULT=') and len(line)<800:
            print(line)
            receipts.append(line)
        if line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
            revoked=revoked or line.endswith('DETACHED_AND_VERIFIED')
    verified=(connected and revoked and len(receipts)==1 and
              '"state":"V122_OWNER_STOP_S03_ISOLATION_PASS"' in receipts[0])
    print('NOX_V122_REAL_STOP_ACCEPTED='+str(verified).lower())
    return 0 if verified else 2

if __name__=='__main__':
    raise SystemExit(main())
