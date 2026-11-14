"""Read-only on-host V125 synthetic QA fact vs existing V120 owner history.

Only booleans/counters are exported, never owner password/cookie/record contents,
identity, DB filename or memory text. No new fact, restart or database write.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

BASE_API=ssh.api

def api(method,path,key,data=None):
    result=BASE_API(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):
        time.sleep(12)
    return result

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib
import http.cookiejar as cookiejar
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_QA_SCHEMA=READONLY_ORIGINAL_S03_V120_HISTORY_DIFF_V1')

def emit(**data):
    print('NATIVE_V125_QA_DIFF='+json.dumps(data,sort_keys=True,separators=(',',':'))[:750])
def get(opener,path):
    req=urllib.request.Request('http://127.0.0.1:8080'+path,method='GET')
    try:return opener.open(req,timeout=8)
    except urllib.error.HTTPError as e:return e
def post(opener,path,data):
    req=urllib.request.Request('http://127.0.0.1:8080'+path,
         method='POST',data=json.dumps(data).encode(),
         headers={'Content-Type':'application/json'})
    try:return opener.open(req,timeout=7)
    except urllib.error.HTTPError as e:return e

op=None
logged=False
try:
    import s03_memory
    path=Path(s03_memory.DB)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError('HOLD_ORIGINAL_S03_DB')
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=4) as db:
        db.execute('PRAGMA query_only=ON')
        integrity=db.execute('PRAGMA quick_check').fetchone()[0]
        rows=db.execute(
            "SELECT id,segment,text,provenance,sha256,meta FROM s03_items "
            "WHERE provenance LIKE 'owner-fact:NOX-V125-QA-%|NOX-LOCAL-QA-VERIFIED' "
            "ORDER BY ts DESC LIMIT 3").fetchall()
    if not rows:
        emit(state='HOLD_NO_SYNTHETIC_QA_FACT',synthetic_count=0,
             s03_ok=(integrity=='ok'),native_writes=False)
    else:
        row=rows[0]
        record_id,segment,content,provenance,stored_sha,meta_json=row
        meta=json.loads(meta_json) if isinstance(meta_json,str) else {}
        key=provenance.split('|',1)[0].removeprefix('owner-fact:')
        expected_sha=hashlib.sha256(content.encode()).hexdigest()
        from chat_proxy import _read_chat_password
        password=_read_chat_password()
        if not isinstance(password,str) or len(password)<6:
            raise RuntimeError('HOLD_OWNER_PASSWORD')
        jar=cookiejar.CookieJar()
        op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with post(op,'/chat/login',{'password':password}) as r:
            if r.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
        password=None
        logged=True
        if not list(jar):raise RuntimeError('HOLD_COOKIE_NOT_BOUND')
        endpoint='/api/ui/memory/facts/history?fact_key='+urllib.parse.quote(key,safe='')
        with get(op,endpoint) as r:
            history_http=r.status
            body=r.read(150000)
        history=json.loads(body) if history_http==200 else {}
        events=history.get('events') if isinstance(history,dict) else None
        if not isinstance(events,list):events=[]
        same_id=[e for e in events if isinstance(e,dict) and e.get('id')==record_id]
        same_content=[e for e in same_id if e.get('content')==content]
        same_sha=[e for e in same_content if e.get('source_sha256')==stored_sha]
        emit(state='S03_NATIVE_QA_HISTORY_COMPARED',
             synthetic_count=len(rows),s03_ok=(integrity=='ok'),
             segment_is_m2=(segment=='M2'),
             original_sha_matches_content=(stored_sha==expected_sha),
             owner_history_http=history_http,
             history_status_ready=(history.get('status')=='READY'),
             history_events_count=len(events),
             record_id_found=bool(same_id),
             content_match=bool(same_content),
             history_native_sha_match=bool(same_sha),
             meta_source_sha_matches_content=(meta.get('source_sha256')==expected_sha),
             owner_meta_confirmed=(meta.get('owner_confirmed') is True),
             module_cookie_verified=True,
             private_data_exported=False,native_writes=False)
except Exception as exc:
    reason=str(exc)
    emit(state=reason if reason.startswith('HOLD_') else 'HOLD_NATIVE_AUDIT',
         private_data_exported=False,native_writes=False)
finally:
    if logged and op is not None:
        try:post(op,'/chat/logout',{}).close()
        except Exception:pass
    print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''

def main():
    ssh.REMOTE=REMOTE
    ssh.api=api
    out=io.StringIO()
    live=False
    detached=False
    try:
        with contextlib.redirect_stdout(out):live=ssh.probe()
    except Exception:
        print('NOX_V125_QA=HOLD_TRANSPORT')
    finally:
        try:
            with contextlib.redirect_stdout(out):detached=ssh.cleanup()
        except Exception:detached=False
    receipts=[]
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V125_QA_DIFF=') and len(line)<800:
            print(line);receipts.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    accepted=live and detached and len(receipts)==1 and 'S03_NATIVE_QA_HISTORY_COMPARED' in receipts[0]
    print('NOX_V125_READONLY_HISTORY_AUDIT='+('PASS' if accepted else 'HOLD'))
    return 0 if accepted else 2

if __name__=='__main__':
    raise SystemExit(main())
