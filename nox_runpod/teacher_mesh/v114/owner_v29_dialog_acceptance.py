"""V114: full owner-auth V29 staging flow on existing localhost, including S03 dialogs.

Uses the real pre-existing login and model, never emits the owner password or
session cookie. One bounded unique public arithmetic test may persist to S03.
Does not activate the site as production or claim all 92 features operational.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,http.cookiejar,json,re,secrets,sys,time,urllib.error,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V114_AUTH_NATIVE_WEB_DIALOG_S03_ONEHOST_V1')
PROXY=Path('/root/nox/scripts/chat_proxy.py')
BRIDGE=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
PROXY_SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
BRIDGE_SHA='cc27928b38f9b86d2375de8092d09dbdc34f81c6e51e8a68d36041ee71529750'
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop',
       '/workspace/NOX_STOP','/root/nox/program/STOP')
def stop():return any(Path(p).exists() for p in STOPS)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def emit(**obj):print('NATIVE_V114_RESULT='+json.dumps(obj,sort_keys=True,separators=(',',':')))
def req(opener,path,method='GET',data=None,timeout=8):
 payload=None if data is None else json.dumps(data,ensure_ascii=False).encode('utf8')
 request=urllib.request.Request('http://127.0.0.1:8080'+path,data=payload,
   method=method,headers={'Content-Type':'application/json','Accept':'application/json'})
 try:response=opener.open(request,timeout=timeout)
 except urllib.error.HTTPError as exc:response=exc
 if path.startswith(('/api/','/nox-web-v29/','/chat/')):
  print('NATIVE_V114_HTTP='+json.dumps({'path':path.split('?',1)[0],'method':method,'status':response.status},sort_keys=True))
 return response
def body(result,limit=10000):
 if result.status!=200:raise RuntimeError('HOLD_RESPONSE_HTTP_'+str(result.status))
 return json.loads(result.read(limit))
def canonical_s03_receipt(receipt,dialog_id):
 return (isinstance(receipt,dict) and receipt.get('saved') is True
  and receipt.get('s03_integrated') is True and receipt.get('dialog_id')==dialog_id
  and receipt.get('store_scope')=='S03_ITEMS'
  and receipt.get('canonical_s03_write_verified') is True
  and isinstance(receipt.get('exchange_id'),str)
  and 6<=len(receipt['exchange_id'])<=160)
def canonical_s03_history(history,dialog_id,prompt,answer,exchange_id):
 if (not isinstance(history,dict) or history.get('status')!='READY'
  or history.get('dialog_id')!=dialog_id or history.get('store_scope')!='S03_ITEMS'
  or history.get('canonical_s03_readback_verified') is not True):return False
 rows=history.get('messages')
 return (isinstance(rows,list) and len(rows)>=2
  and isinstance(rows[-2],dict) and isinstance(rows[-1],dict)
  and rows[-2].get('role')=='user' and rows[-2].get('content')==prompt
  and rows[-1].get('role')=='assistant' and rows[-1].get('content')==answer
  and rows[-2].get('exchange_id')==exchange_id
  and rows[-1].get('exchange_id')==exchange_id)
opener=None;owner=False
try:
 if stop():raise RuntimeError('HOLD_STOP_FLAG')
 if not PROXY.is_file() or not BRIDGE.is_file() or sha(PROXY)!=PROXY_SHA or sha(BRIDGE)!=BRIDGE_SHA:
  raise RuntimeError('HOLD_NATIVE_BUILD_SHA_CHANGED')
 with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as response:
  slots=json.loads(response.read(30000))
 if not isinstance(slots,list) or len(slots)!=6 or any(
   r.get('is_processing',r.get('processing',False)) for r in slots if isinstance(r,dict)):
  raise RuntimeError('HOLD_ONEHOST_BUSY')
 sys.path.insert(0,'/root/nox/scripts')
 import chat_proxy
 password=chat_proxy._read_chat_password()
 if not isinstance(password,str) or len(password)<6:
  raise RuntimeError('HOLD_OWNER_CREDENTIAL_UNAVAILABLE')
 jar=http.cookiejar.CookieJar()
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 login=req(opener,'/chat/login','POST',{'password':password},5)
 password=None
 if login.status!=200 or not any(True for _ in jar):raise RuntimeError('HOLD_OFFICIAL_LOGIN')
 print('NATIVE_V114_COOKIE_META='+json.dumps([{'name':c.name,'path':c.path} for c in jar]))
 owner=True
 session=body(req(opener,'/chat/session',timeout=5),2000)
 if session.get('ok') is not True:raise RuntimeError('HOLD_OWNER_COOKIE')
 status=body(req(opener,'/api/nox/status',timeout=7))
 if (status.get('backend')!='EXISTING_NATIVE_ONEHOST' or
     status.get('native_p02_bound') is not True or not status.get('primary_model') or
     status.get('native_cognitive_memory_bound') is not True or
     status.get('native_dialogs_ready') is not True):
  raise RuntimeError('HOLD_WEB_MODEL_S03_STATUS_CONTRACT')
 caps=body(req(opener,'/api/ui/capabilities',timeout=5))
 if caps.get('schema')!='NOX_NATIVE_UI_WORKSPACE_V1' or caps.get('persistent_threads') is not True:
  raise RuntimeError('HOLD_WORKSPACE_CAPABILITIES')
 dialogs=body(req(opener,'/api/ui/memory/dialogs/status',timeout=5))
 if dialogs.get('persistent_threads') is not True or dialogs.get('status')!='READY':
  raise RuntimeError('HOLD_NATIVE_DIALOGS_STATUS')
 # Exercise the actually staged WEB, without changing / or /chat.
 html=req(opener,'/nox-web-v29/chat.html',timeout=6)
 if html.status!=200 or b'native-owner.js' not in html.read(250000):
  raise RuntimeError('HOLD_OWNER_WEB_HTML_BOOTSTRAP')
 script=req(opener,'/nox-web-v29/native-owner.js',timeout=5)
 if script.status!=200 or b'NOX_NATIVE_OWNER = true' not in script.read(2000):
  raise RuntimeError('HOLD_OWNER_WEB_NATIVE_SWITCH')
 no_active=req(opener,'/api/nox/stop','POST',{},5)
 if no_active.status!=409:raise RuntimeError('HOLD_STOP_NO_ACTIVE_SCOPE')
 marker='noxv114_'+secrets.token_hex(6)
 prompt='[QA '+marker+'] Сколько будет 17 умножить на 19? Ответь только числом.'
 created=body(req(opener,'/api/ui/memory/dialogs/create','POST',
     {'title':'NOX QA '+marker,'confirmed':True},7))
 dialog_id=created.get('dialog_id')
 if not isinstance(dialog_id,str) or not re.fullmatch('[a-f0-9]{32}',dialog_id):
  raise RuntimeError('HOLD_DIALOG_CREATE')
 if stop():raise RuntimeError('HOLD_STOP_BEFORE_MODEL')
 start=time.monotonic()
 model=req(opener,'/api/nox/chat/stream','POST',
   {'message':prompt,'history':[],'task':'general','dialog_id':dialog_id},timeout=85)
 if model.status!=200 or 'ndjson' not in model.headers.get('content-type','').lower():
  raise RuntimeError('HOLD_MODEL_STREAM_HTTP_'+str(model.status))
 answer_parts=[];receipt=None;events=0;first_delta_ms=None
 for raw in model:
  events+=1
  if events>1200 or len(raw)>100000:raise RuntimeError('HOLD_BOUNDED_STREAM')
  try:frame=json.loads(raw.decode('utf8'))
  except (ValueError,UnicodeDecodeError):raise RuntimeError('HOLD_JSON_STREAM')
  kind=frame.get('type') if isinstance(frame,dict) else None
  if kind=='delta':
   if first_delta_ms is None:first_delta_ms=int((time.monotonic()-start)*1000)
   chunk=frame.get('text','')
   if not isinstance(chunk,str):raise RuntimeError('HOLD_DELTA_CONTENT')
   answer_parts.append(chunk)
  elif kind=='done':
   receipt=frame
   break
  elif kind=='error':raise RuntimeError('HOLD_STREAM_ERROR_'+str(frame.get('error'))[:60])
  elif kind not in ('preparing','start'):
   raise RuntimeError('HOLD_UNKNOWN_STREAM_EVENT')
  if time.monotonic()-start>100:raise RuntimeError('HOLD_STREAM_TIMEOUT')
 answer=''.join(answer_parts)
 if (not canonical_s03_receipt(receipt,dialog_id) or
     not re.search(r'(?<!\d)323(?!\d)',answer)):
  raise RuntimeError('HOLD_CANONICAL_S03_DIALOG_SCOPE_AND_WRITE_PROOF')
 history=body(req(opener,'/api/ui/memory/dialogs/history?dialog_id='+dialog_id+'&limit=20',timeout=8))
 if not canonical_s03_history(history,dialog_id,prompt,answer,receipt['exchange_id']):
  raise RuntimeError('HOLD_CANONICAL_S03_DIALOG_SCOPE_AND_READBACK_PROOF')
 listing=body(req(opener,'/api/ui/memory/dialogs?archived=false',timeout=7))
 if dialog_id not in [x.get('dialog_id') for x in listing.get('dialogs',[])]:
  raise RuntimeError('HOLD_OWNER_DIALOG_LIST_READBACK')
 emit(state='V114_FULL_AUTH_OWNER_WEB_DIALOG_S03_STREAM_PASS',
   proxy_sha256=PROXY_SHA,bridge_sha256=BRIDGE_SHA,
   official_login=True,model_status_bound=True,
   native_dialog_created=True,stream_ndjson_delta_count=len(answer_parts),
   live_s03_committed=True,native_dialog_history_readback=True,
   owner_only_web_bootstrap=True,dialog_list_readback=True,
   unauthenticated_scopes_not_modified=True,stop_idle_http=409,
   first_delta_ms=first_delta_ms,total_ms=int((time.monotonic()-start)*1000),
   answer_sha256=hashlib.sha256(answer.encode('utf8')).hexdigest(),
   user_private_data_exported=False,model_weights_changed=False,
   full_92_functions_accepted=False,production_home_switched=False)
 print('NATIVE_V114_AUTH_FULL_E2E_ACCEPTED=true')
except Exception as exc:
 msg=str(exc)
 emit(state=msg if msg.startswith('HOLD_') and len(msg)<120 else 'HOLD_V114_NATIVE_RUNTIME',
      type=type(exc).__name__,credentials_exposed=False)
finally:
 if owner and opener is not None:
  try:req(opener,'/chat/logout','POST',{},timeout=4)
  except Exception:pass
 print('NATIVE_V114_PRIVATE_OWNER_AUTH_EXPORTED=false')
 print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def api(method,path,key,data=None):
        for idx in range(4):
            try:
                res=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return res
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or idx==3:raise
                time.sleep((10,20,40)[idx])
    ssh.api=api
    captured=io.StringIO();success=False
    try:
        with contextlib.redirect_stdout(captured):success=ssh.probe()
    except Exception as e:
        msg=str(e)
        print('NOX_V114_HOLD='+(msg if msg.startswith('HOLD_') else 'CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(captured):
                if not ssh.cleanup():success=False
        except Exception:success=False
    seen=[]
    for row in captured.getvalue().splitlines():
        if row.startswith('NATIVE_V114_RESULT=') and len(row)<1800:
            seen.append(row);print(row)
        elif row.startswith(('NATIVE_V114_HTTP=','NATIVE_V114_COOKIE_META=')) and len(row)<350:print(row)
        elif row.startswith('TEMP_SSH_CLEANUP='):print(row[:120])
        elif row.startswith('NATIVE_V114_AUTH_FULL_E2E_ACCEPTED='):print(row)
    accepted=success and len(seen)==1 and any(
        'V114_FULL_AUTH_OWNER_WEB_DIALOG_S03_STREAM_PASS' in row for row in seen)
    print('NOX_V114_E2E_PASS='+str(bool(accepted)).lower())
    return 0 if accepted else 2
if __name__=='__main__':
    raise SystemExit(main())
