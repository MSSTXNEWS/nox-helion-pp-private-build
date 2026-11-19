"""V121 actual owner-cookie acceptance for genuine S03 history and knowledge views.
Neither private memory content nor credentials leave the original OneHost.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,http.cookiejar,json,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V121_OWNER_REAL_S03_MEMORY_READBACK_V1')
SHA='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad'
URLS=('/api/nox/history','/api/nox/experience?q=NOX',
      '/api/ui/memory/facts/history')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(p).exists() for p in STOPS)
def emit(**data):print('NATIVE_V121='+json.dumps(data,separators=(',',':'),sort_keys=True))
def get(opener,path):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,method='GET')
 try:return opener.open(req,timeout=10)
 except urllib.error.HTTPError as exc:return exc
owner=False
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 file=Path('/root/nox/scripts/chat_proxy.py')
 if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=SHA:
  raise RuntimeError('HOLD_EXPECTED_ONEHOST_SHA')
 anonymous=urllib.request.build_opener()
 anon_codes=[get(anonymous,p).status for p in URLS]
 if anon_codes!=[401,401,401]:raise RuntimeError('HOLD_ANON_MEMORY_ACCESS')
 from chat_proxy import _read_chat_password
 password=_read_chat_password()
 if not isinstance(password,str) or len(password)<6:
  raise RuntimeError('HOLD_LOCAL_OWNER_PASSWORD')
 req=urllib.request.Request('http://127.0.0.1:8080/chat/login',
     data=json.dumps({'password':password}).encode('utf8'),
     headers={'Content-Type':'application/json'},method='POST')
 with opener.open(req,timeout=8) as r:
  if r.status!=200:raise RuntimeError('HOLD_OWNER_LOGIN')
 password=None;owner=True
 with get(opener,'/chat/session') as r:
  if r.status!=200 or json.loads(r.read(2500)).get('ok') is not True:
   raise RuntimeError('HOLD_OWNER_SESSION')
 records=[]
 for path in URLS:
  with get(opener,path) as r:
   if r.status!=200:raise RuntimeError('HOLD_MEMORY_HTTP_'+str(r.status))
   data=json.loads(r.read(300000))
  if not isinstance(data,dict) or data.get('status')!='READY':
   raise RuntimeError('HOLD_NATIVE_MEMORY_SCHEMA')
  rows=data.get('messages') if path=='/api/nox/history' else data.get('events') if '/facts/' in path else data.get('results')
  if not isinstance(rows,list) or len(rows)>50:raise RuntimeError('HOLD_UNBOUNDED_MEMORY_READ')
  if any(not isinstance(row,dict) for row in rows):raise RuntimeError('HOLD_MEMORY_RECORD_TYPE')
  if path=='/api/nox/history':
   if not all(row.get('role') in ('user','assistant') and isinstance(row.get('content'),str) for row in rows):
    raise RuntimeError('HOLD_CHAT_HISTORY_SCHEMA')
  else:
   if not all(isinstance(row.get('content'),str) and isinstance(row.get('source_ref'),str) for row in rows):
    raise RuntimeError('HOLD_KNOWLEDGE_SOURCE_SCHEMA')
  records.append({'route':path.split('?',1)[0],'entries':len(rows),
                  'source':str(data.get('source',''))[:40]})
 if stopped():raise RuntimeError('HOLD_STOP_REVOKED')
 emit(state='LIVE_OWNER_S03_KNOWLEDGE_HISTORY_ROUTES_ACCEPTED',
      anonymous_http=anon_codes,owner_http=[200,200,200],
      real_record_counts=records,live_sqlite_source=True,
      records_transmitted_to_github=False,owner_credentials_exported=False,
      service_restarted=False,model_weights_changed=False)
 print('NATIVE_V121_OWNER_MEMORY_READBACK_PASS=true')
except Exception as ex:
 msg=str(ex)
 emit(state=msg if msg.startswith('HOLD_') and len(msg)<95 else 'HOLD_NATIVE_OWNER_S03',
      error_type=type(ex).__name__,records_transmitted_to_github=False,
      owner_credentials_exported=False,model_weights_changed=False)
finally:
 if owner:
  try:
   req=urllib.request.Request('http://127.0.0.1:8080/chat/logout',
       data=b'{}',headers={'Content-Type':'application/json'},method='POST')
   opener.open(req,timeout=4).close()
  except Exception:pass
 print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    initial=ssh.api
    def gate(method,path,key,data=None):
        for attempt in range(4):
            try:
                result=initial(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as ex:
                if method!='GET' or str(ex)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
                time.sleep((10,20,40)[attempt])
    ssh.api=gate
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    except Exception as exc:
        value=str(exc)
        print('NOX_V121_SSH_HOLD='+(value if value.startswith('HOLD_') and len(value)<90 else 'SSH_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for l in lines:
        if l.startswith(('NATIVE_V121=','NATIVE_V121_OWNER_MEMORY_READBACK_PASS=','SSH_ATTEMPT_','SSH_FAILURE_CLASS=','TEMP_SSH_CLEANUP=')):
            print(l[:2300])
    accepted=bool(ok and 'NATIVE_V121_OWNER_MEMORY_READBACK_PASS=true' in lines)
    print('NOX_V121_OWNER_MEMORY_HTTP_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
