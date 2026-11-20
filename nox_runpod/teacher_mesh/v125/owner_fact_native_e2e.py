"""V125 physical owner-cookie SAVE → original S03 → existing V120 history.

One innocuous synthetic note only. No password, owner cookie, S03 contents or
user text leaves the existing Vast OneHost; no restarts or model modifications.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

_ORIGINAL_API=ssh.api

def transport(method,path,key,data=None):
    for attempt in range(4):
        try:
            result=_ORIGINAL_API(method,path,key,data)
            if method=="POST" and path.endswith("/ssh/"):
                time.sleep(12)
            return result
        except RuntimeError as exc:
            if method!="GET" or str(exc)!="HOLD_VAST_API_HTTP_429" or attempt==3:
                raise
            time.sleep((10,20,40)[attempt])

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib
import http.cookiejar as cookiejar
import json
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_SCHEMA=OWNER_COOKIE_FACT_ORIGINAL_S03_HISTORY_REAL_E2E_V1')
PROXY=Path('/root/nox/scripts/chat_proxy.py')
MODULE=Path('/root/nox/scripts/nox_v125_owner_fact_write.py')
BACKUP=Path('/root/nox/scripts/chat_proxy.py.nox-v125-e79aa0747511.bak')
OLD='e79aa0747511cf010f79f72150fc4e64b36b9c9ccea3b09d788a6306c63c0c95'
MODULE_SHA='341174f4c6376edcdeee6bde46d4ae5269ce9785190c853f4cb49647a3fcb4e0'
ANCHOR='register_nox_v120_s03_memory_views(app, globals())\n'
ADDITION=('from nox_v125_owner_fact_write import register_nox_v125_owner_fact_write\n'
          'register_nox_v125_owner_fact_write(app, globals())\n')
AUTH_OLD="'/api/nox/history','/api/nox/experience','/api/training/status'"
AUTH_NEW="'/api/nox/history','/api/nox/experience','/api/nox/memory/facts','/api/training/status'"
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')

def digest(data):return hashlib.sha256(data).hexdigest()
def stopped():return any(Path(p).exists() for p in STOPS)
def request(opener,path,method='GET',body=None):
    payload=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf8')
    req=urllib.request.Request('http://127.0.0.1:8080'+path,
              data=payload,method=method,
              headers={'Content-Type':'application/json'})
    try:
        return opener.open(req,timeout=11)
    except urllib.error.HTTPError as e:
        return e
def emit(state,**kw):
    obj={'state':state,'model_weights_changed':False,'services_restarted':False,
         'user_credentials_exported':False,'private_records_exported':False,**kw}
    print('NATIVE_V125_FACT_E2E='+json.dumps(obj,sort_keys=True,separators=(',',':'))[:760])

signed=None
logged=False
try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if not BACKUP.is_file() or BACKUP.is_symlink() or not PROXY.is_file() or PROXY.is_symlink():
        raise RuntimeError('HOLD_ORIGINAL_SOURCE_BACKUP')
    old_bytes=BACKUP.read_bytes()
    if digest(old_bytes)!=OLD or digest(MODULE.read_bytes())!=MODULE_SHA:
        raise RuntimeError('HOLD_NATIVE_SOURCE_BACKUP_SHA')
    before=old_bytes.decode('utf8')
    if before.count(ANCHOR)!=1 or before.count(AUTH_OLD)!=1:
        raise RuntimeError('HOLD_INSTALL_SOURCE_ANCHORS')
    expected=digest(before.replace(ANCHOR,ANCHOR+ADDITION,1)
                    .replace(AUTH_OLD,AUTH_NEW,1).encode('utf8'))
    if digest(PROXY.read_bytes())!=expected:
        raise RuntimeError('HOLD_V125_LIVE_PROXY_SHA_DRIFT')
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:
        raise RuntimeError('HOLD_LOCAL_OWNER_SECRET')
    jar=cookiejar.CookieJar()
    signed=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with request(signed,'/chat/login','POST',{'password':password}) as r:
        if r.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
    password=None
    if not list(jar):raise RuntimeError('HOLD_OWNER_COOKIE_MISSING')
    logged=True
    with request(signed,'/chat/session') as r:
        if r.status!=200 or json.loads(r.read(2500)).get('ok') is not True:
            raise RuntimeError('HOLD_OWNER_COOKIE_SESSION')
    unsigned=urllib.request.build_opener()
    with request(unsigned,'/api/nox/memory/facts','POST',{}) as r:
        if r.status!=401:raise RuntimeError('HOLD_UNAUTHENTICATED_FACT_API')
    import s03_memory
    db=Path(s03_memory.DB)
    if not db.is_file() or db.is_symlink():
        raise RuntimeError('HOLD_ORIGINAL_S03_MISSING')
    # Reuse the last *synthetic V125 QA row* if one exists. Reruns never
    # pollute user memory with another test record.
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as con:
        con.execute('PRAGMA query_only=ON')
        previous=con.execute(
          "SELECT text,provenance,meta FROM s03_items "
          "WHERE provenance LIKE 'owner-fact:NOX-V125-QA-%|NOX-LOCAL-QA-VERIFIED' "
          "ORDER BY ts DESC LIMIT 1").fetchone()
    reused_qa=previous is not None
    if reused_qa:
        text,provenance,stored_meta=previous
        marker=provenance.split('|',1)[0].removeprefix('owner-fact:')
        meta=json.loads(stored_meta) if isinstance(stored_meta,str) else {}
        valid_from=meta.get('valid_from')
        if (meta.get('source_sha256')!=digest(text.encode('utf8'))
            or meta.get('owner_confirmed') is not True
            or not isinstance(valid_from,str)):
            raise RuntimeError('HOLD_PREVIOUS_QA_SOURCE_META')
    else:
        marker='NOX-V125-QA-'+secrets.token_hex(5)
        text='Контроль сохранения в S03: 17 × 19 = 323. Идентификатор: '+marker
        provenance='owner-fact:'+marker+'|NOX-LOCAL-QA-VERIFIED'
        valid_from=datetime.now(timezone.utc).isoformat()
    content_sha=digest(text.encode('utf8'))
    payload={'fact_key':marker,'content':text,'source_ref':'NOX-LOCAL-QA-VERIFIED',
             'source_sha256':content_sha,'valid_from':valid_from}
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as con:
        before_count=con.execute(
          'SELECT COUNT(*) FROM s03_items WHERE provenance=?',(provenance,)).fetchone()[0]
    if before_count!=int(reused_qa):
        raise RuntimeError('HOLD_PREEXISTING_QA_DUPLICATES')
    if stopped():raise RuntimeError('HOLD_STOP_BEFORE_FACT_POST')
    with request(signed,'/api/nox/memory/facts','POST',payload) as r:
        if r.status!=200:raise RuntimeError('HOLD_OWNER_FACT_POST_'+str(r.status))
        answer=json.loads(r.read(16000))
    record_id=answer.get('event_id')
    if (answer.get('status')!='SAVED' or answer.get('s03_integrated') is not True
        or answer.get('saved') is not True or answer.get('deduplicated') is not reused_qa
        or not isinstance(record_id,str) or not record_id):
        raise RuntimeError('HOLD_NATIVE_FACT_WRITE_RECEIPT')
    with request(signed,'/api/nox/memory/facts','POST',payload) as r:
        if r.status!=200:raise RuntimeError('HOLD_OWNER_FACT_IDEMPOTENCE_HTTP')
        repeat=json.loads(r.read(16000))
    if (repeat.get('event_id')!=record_id or
        repeat.get('deduplicated') is not True):
        raise RuntimeError('HOLD_NATIVE_FACT_DEDUPLICATION')
    path='/api/ui/memory/facts/history?fact_key='+urllib.parse.quote(marker,safe='')
    with request(signed,path) as r:
        if r.status!=200:raise RuntimeError('HOLD_EXISTING_HISTORY_HTTP')
        hist=json.loads(r.read(140000))
    events=hist.get('events') if isinstance(hist,dict) else None
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as con:
        con.execute('PRAGMA query_only=ON')
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_POSTFACT_S03_QUICKCHECK')
        rows=con.execute(
           'SELECT id,segment,sha256,meta,text FROM s03_items WHERE provenance=?',
           (provenance,)).fetchall()
    if len(rows)!=1 or rows[0][0]!=record_id or rows[0][1]!='M2' or rows[0][4]!=text:
        raise RuntimeError('HOLD_ORIGINAL_S03_FACT_ROW')
    internal_sha=rows[0][2]
    source_meta=json.loads(rows[0][3]) if isinstance(rows[0][3],str) else {}
    if (source_meta.get('source_sha256')!=content_sha
        or source_meta.get('owner_confirmed') is not True):
        raise RuntimeError('HOLD_ORIGINAL_S03_SOURCE_META')
    # The native S03 internal digest is NOT the source content checksum.
    # V120 history must reflect the original S03 row SHA, while source content
    # SHA is independently protected in source_meta.
    if (hist.get('status')!='READY' or not isinstance(events,list)
        or not any(isinstance(x,dict) and x.get('id')==record_id
                   and x.get('content')==text
                   and x.get('source_sha256')==internal_sha for x in events)):
        raise RuntimeError('HOLD_FACT_NOT_FOUND_IN_EXISTING_HISTORY')
    if stopped():raise RuntimeError('HOLD_STOP_AFTER_FACT')
    with urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=4) as r:
        if r.status!=200:raise RuntimeError('HOLD_MODEL_HEALTH_AFTER_FACT')
    emit('EXISTING_OWNER_FACT_TO_S03_HISTORY_PASS',
         anonymous_http=401,owner_fact_http=200,
         saved_once=True,dedup_verified=True,
         native_s03_row_count=1,existing_history_readback=True,
         s03_integrity='ok',model_http=200,
         original_qa_fact_new=(not reused_qa),
         reused_existing_synthetic_fact=reused_qa,
         source_checksum_metadata_verified=True)
    print('NATIVE_V125_OWNER_FACT_S03_E2E_ACCEPTED=true')
except Exception as exc:
    cause=str(exc)
    emit(cause if cause.startswith('HOLD_') and len(cause)<90 else 'HOLD_V125_NATIVE_FACT_E2E')
finally:
    if logged and signed is not None:
        try:request(signed,'/chat/logout','POST',{}).close()
        except Exception:pass
    print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    ssh.REMOTE=REMOTE
    ssh.api=transport
    capture=io.StringIO()
    connected=False
    detached=False
    try:
        with contextlib.redirect_stdout(capture):connected=ssh.probe()
    except Exception as exc:
        reason=str(exc)
        print('NOX_V125_FACT_E2E='+(reason if reason.startswith('HOLD_') and len(reason)<96
                                    else 'HOLD_NATIVE_SSH'))
    finally:
        try:
            with contextlib.redirect_stdout(capture):detached=ssh.cleanup()
        except Exception:detached=False
    receipts=[]
    success=False
    for line in capture.getvalue().splitlines():
        if line.startswith('NATIVE_V125_FACT_E2E=') and len(line)<800:
            print(line);receipts.append(line)
        elif line.startswith('NATIVE_V125_OWNER_FACT_S03_E2E_ACCEPTED='):
            print(line);success=success or line.endswith('=true')
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    okay=(connected and detached and success and len(receipts)==1
          and '"state":"EXISTING_OWNER_FACT_TO_S03_HISTORY_PASS"' in receipts[0])
    print('NOX_V125_REAL_OWNER_FACT_PERSISTENCE='+('PASS' if okay else 'HOLD'))
    return 0 if okay else 2

if __name__=='__main__':
    raise SystemExit(main())
