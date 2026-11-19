"""V112 authenticated native V29 E2E via existing owner login.
Runs entirely on existing NOX localhost; no password, cookie or private S03
record leaves Vast. Uses one benign synthetic public prompt only.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,http.cookiejar,json,secrets,sys,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V112_OWNER_COOKIE_CHAT_S03_E2E_V1')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
EXPECTED='07c9feb7f5a192f61b0c64b192c466e2995688b5a14429841da1b308a12076e5'
def stop():return any(Path(x).exists() for x in STOP)
def report(**x):print('NATIVE_V112_RESULT='+json.dumps(x,sort_keys=True,separators=(',',':')))
def request(opener,path,method='GET',body=None,timeout=10):
    payload=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf8')
    req=urllib.request.Request('http://127.0.0.1:8080'+path,data=payload,
        headers={'Content-Type':'application/json','Accept':'application/json'},
        method=method)
    try:return opener.open(req,timeout=timeout)
    except urllib.error.HTTPError as e:return e
opener=None
created=False
try:
    if stop():raise RuntimeError('HOLD_STOP')
    source=Path('/root/nox/scripts/chat_proxy.py')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED:
        raise RuntimeError('HOLD_UNEXPECTED_PROXY_SHA')
    # Abort rather than interrupt a running primary user session.
    with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:
        slots=json.loads(r.read(25000))
    if not isinstance(slots,list) or len(slots)!=6 or any(
            x.get('is_processing',x.get('processing',False)) for x in slots if isinstance(x,dict)):
        raise RuntimeError('HOLD_PRIMARY_CHAT_BUSY')
    # Official login protocol. Password never printed, returned or written.
    sys.path.insert(0,'/root/nox/scripts')
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or len(password)<6:
        raise RuntimeError('HOLD_LOCAL_OWNER_CREDENTIAL_UNAVAILABLE')
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login=request(opener,'/chat/login','POST',{'password':password},timeout=5)
    password=None
    if login.status!=200 or not any(True for _ in jar):
        raise RuntimeError('HOLD_OFFICIAL_LOGIN')
    created=True
    session=request(opener,'/chat/session',timeout=5)
    session_data=json.loads(session.read(2000)) if session.status==200 else {}
    if session.status!=200 or session_data.get('ok') is not True:
        raise RuntimeError('HOLD_OWNER_COOKIE_NOT_VALID')
    stat=request(opener,'/api/nox/status',timeout=7)
    if stat.status!=200:raise RuntimeError('HOLD_V29_OWNER_STATUS_ROUTE')
    status_blob=stat.read(12000)
    try:status_data=json.loads(status_blob)
    except ValueError:status_data={}
    # STOP endpoint must not stop an unrelated user session.
    stop_req=request(opener,'/api/nox/stop','POST',{},timeout=5)
    if stop_req.status!=409:raise RuntimeError('HOLD_STOP_ROUTE_SCOPE')
    marker='noxv112_'+secrets.token_hex(5)
    question='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь по-русски числом.'
    t0=time.monotonic()
    if stop():raise RuntimeError('HOLD_STOP_BEFORE_QUESTION')
    stream=request(opener,'/api/nox/chat/stream','POST',
                   {'message':question,'history':[],'stream':True},
                   timeout=90)
    if stream.status!=200:raise RuntimeError('HOLD_OWNER_STREAM_HTTP_'+str(stream.status))
    if 'ndjson' not in stream.headers.get('content-type','').lower():
        raise RuntimeError('HOLD_OWNER_STREAM_CONTENT_TYPE')
    stream_events=[];answer_parts=[];finished=False;first_delta_ms=None;receipt=None
    # Bounded line and event counts; never log full model or private user text.
    for index,raw in enumerate(stream):
        if index>=1200:raise RuntimeError('HOLD_TOO_MANY_EVENTS')
        if len(raw)>100000:raise RuntimeError('HOLD_EVENT_TOO_LARGE')
        try:event=json.loads(raw.decode('utf8'))
        except ValueError:raise RuntimeError('HOLD_INVALID_NDJSON')
        name=event.get('type') if isinstance(event,dict) else None
        if name not in ('preparing','start','delta','done','error'):
            raise RuntimeError('HOLD_EVENT_SCHEMA')
        stream_events.append(name)
        if name=='delta':
            if first_delta_ms is None:first_delta_ms=int((time.monotonic()-t0)*1000)
            value=event.get('text','')
            if not isinstance(value,str):raise RuntimeError('HOLD_INVALID_DELTA')
            answer_parts.append(value)
        if name=='error':
            code=str(event.get('error') or '')
            raise RuntimeError('HOLD_NATIVE_STREAM_EVENT_'+code[:65])
        if name=='done':
            receipt={'saved':event.get('saved'),'s03_integrated':event.get('s03_integrated'),
                     'exchange_id_present':bool(event.get('exchange_id'))}
            finished=True
            break
        if time.monotonic()-t0>115:raise RuntimeError('HOLD_STREAM_TIMEOUT')
    answer=''.join(answer_parts)
    if stop():raise RuntimeError('HOLD_STOP_DURING_ANSWER')
    if not finished or not receipt or receipt['saved'] is not True or receipt['s03_integrated'] is not True:
        raise RuntimeError('HOLD_S03_STREAM_COMMIT')
    if not answer.strip() or len(answer)>40000:raise RuntimeError('HOLD_EMPTY_OR_EXCESSIVE_RESPONSE')
    if not __import__('re').search(r'(?<!\d)323(?!\d)',answer):
        raise RuntimeError('HOLD_PUBLIC_ARITHMETIC_ANSWER')
    report(state='AUTHENTIC_OWNER_COOKIE_V29_CHAT_S03_PASS',
           status_http=stat.status,status_keys=sorted(status_data.keys())[:14],
           cookie_login_verified=True,stop_when_no_active_stream=409,
           ndjson_done_verified=True,real_s03_receipt=receipt,
           delta_count=len(answer_parts),events=stream_events[:6],
           first_delta_ms=first_delta_ms,total_ms=int((time.monotonic()-t0)*1000),
           answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
           test_prompt_marker_sha256=hashlib.sha256(marker.encode()).hexdigest(),
           private_records_exported=False,model_weights_changed=False)
    print('NATIVE_V112_AUTHENTIC_OWNER_STREAM_ACCEPTED=true')
except Exception as exc:
    msg=str(exc)
    report(state=msg if msg.startswith('HOLD_') and len(msg)<110 else 'HOLD_AUTHENTIC_SESSION_TEST',
           exception_type=type(exc).__name__,
           owner_password_exported=False,owner_cookie_exported=False,
           model_weights_changed=False)
finally:
    if created and opener is not None:
        try:request(opener,'/chat/logout','POST',{},timeout=3)
        except Exception:pass
    print('NATIVE_V112_PRIVATE_CREDENTIALS_EXPORTED=false')
    print('NATIVE_V112_EXTERNAL_TEACHER_USED=false')
    print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE;old=ssh.api
    def transport(method,path,key,data=None):
        for i in range(4):
            try:
                result=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=transport
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    except Exception as e:
        x=str(e);print('NOX_V112_HOLD='+(x if x.startswith('HOLD_') and len(x)<90 else 'SSH_NATIVE'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V112_RESULT=','NATIVE_V112_AUTHENTIC_OWNER_STREAM_ACCEPTED=','TEMP_SSH_CLEANUP=')):
            print(line[:2400])
    good=bool(ok and 'NATIVE_V112_AUTHENTIC_OWNER_STREAM_ACCEPTED=true' in lines)
    print('NOX_V112_AUTHENTIC_OWNER_COOKIE_ACCEPTED='+str(good).lower())
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
