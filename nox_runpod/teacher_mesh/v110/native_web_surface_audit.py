"""NOX V110: one read-only probe of live V29 server contracts, no model/UI/S03 writes."""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,re,urllib.request,urllib.error,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V110_READONLY_V29_CONTRACT_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
M=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
WEB=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js')
def emit(k,v):
 print('NATIVE_V110_'+k+'='+json.dumps(v,sort_keys=True,separators=(',',':')))
def digest(p):
 return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None
emit('FILES',{'proxy_sha':digest(P),'bridge_sha':digest(M),'web_sha':digest(WEB),
              'bridge_size':M.stat().st_size if M.is_file() else 0,
              'late_registration':b'register_native_v29_chat(app' in P.read_bytes() if P.is_file() else False})
def http(path,method='GET'):
 data=b'{}' if method=='POST' else None
 req=urllib.request.Request('http://127.0.0.1:8080'+path, data=data, method=method,
   headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=4) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return 0
paths=[
 ('/health','GET'),('/api/nox/status','GET'),('/api/nox/chat/stream','POST'),
 ('/api/nox/stop','POST'),('/api/ui/capabilities','GET'),
 ('/api/ui/memory/dialogs/status','GET'),('/api/ui/memory/dialogs','GET'),
 ('/api/ui/memory/dialogs/create','POST'),('/api/ui/memory/dialogs/history','GET'),
 ('/api/ui/memory/dialogs/update','POST'),('/api/settings','GET'),
 ('/api/nox/voice/status','GET'),('/api/training/status','GET'),('/api/pc-metrics','GET')]
for path,method in paths:
 emit('HTTP',{'path':path,'method':method,'anonymous_http':http(path,method)})
if P.is_file():
 tree=ast.parse(P.read_text())
 functions={x.name:x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
 for name in ('_session_ok','_unauthorized','_proxy_completion','chat_api','nox_status'):
  x=functions.get(name)
  if x is None:
   emit('FUNCTION',{'name':name,'present':False})
  else:
   emit('FUNCTION',{'name':name,'present':True,'is_async':isinstance(x,ast.AsyncFunctionDef),
    'args':[a.arg for a in x.args.args],'line_count':x.end_lineno-x.lineno+1})
 for label,pattern in [('stream','stream'),('s03','s03'),('dialog','dialog')]:
  hits=[x.name for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and pattern in x.name.lower()]
  emit('NAMED_FUNCTIONS',{'kind':label,'names':hits[:14],'count':len(hits)})
if M.is_file():
 tr=ast.parse(M.read_text())
 for x in tr.body:
  if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)):
   emit('BRIDGE_FN',{'name':x.name,'is_async':isinstance(x,ast.AsyncFunctionDef),'args':[a.arg for a in x.args.args]})
# Scan own native API source filenames only, never memory content or credentials.
base=Path('/root/nox/scripts')
names=sorted(x.name for x in base.glob('*.py') if any(k in x.name.lower() for k in ('s03','dialog','workspace','proxy','memory')))
emit('FILES_INDEX',{'matching_modules':names[:24],'count':len(names)})
try:
 with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as r:
  a=json.loads(r.read(50000))
 emit('SLOTS',{'count':len(a) if isinstance(a,list) else -1,
   'busy':sum(bool(x.get('is_processing',x.get('processing',False))) for x in a if isinstance(x,dict)) if isinstance(a,list) else -1})
except Exception:emit('SLOTS',{'status':'UNKNOWN'})
# Import the installed app in a separate process, read route metadata only.
# This cannot establish functional E2E but distinguishes real route registration from global 401.
PYCODE = '''
import json,sys
sys.path.insert(0,'/root/nox/scripts')
import chat_proxy
from fastapi.routing import APIRoute
from starlette.routing import Mount
for idx,route in enumerate(chat_proxy.app.routes):
 if isinstance(route,Mount) and idx<120:
  print('NOX_MOUNT_JSON='+json.dumps({'index':idx,'path':route.path}))
 elif isinstance(route,APIRoute) and (route.path.startswith('/api/ui/') or route.path.startswith('/api/nox/status')):
  print('NOX_TARGET_ROUTE_JSON='+json.dumps({'index':idx,'path':route.path,'methods':sorted(route.methods),'handler':route.endpoint.__name__,'module':route.endpoint.__module__}))
from starlette.routing import Match
for key in ('/api/nox/status','/api/ui/capabilities','/api/ui/memory/dialogs/status'):
 scope={'type':'http','method':'GET','path':key,'root_path':'','query_string':b'',
        'headers':[],'scheme':'http','server':('127.0.0.1',8080),'client':('127.0.0.1',0),'http_version':'1.1'}
 target=None
 for ix,route in enumerate(chat_proxy.app.routes):
  match,_=route.matches(scope)
  if match==Match.FULL:
   target={'path':key,'index':ix,'route_path':route.path,
     'handler':getattr(getattr(route,'endpoint',None),'__name__','mount')}
   break
 print('NOX_MATCH_JSON='+json.dumps(target))
print('NOX_MIDDLEWARE_JSON='+json.dumps([
 getattr(item.cls,'__name__','UNKNOWN') for item in chat_proxy.app.user_middleware]))
routes=[{'path':r.path,'methods':sorted(r.methods)} for r in chat_proxy.app.routes if isinstance(r,APIRoute)]
print('NOX_ROUTE_INVENTORY_JSON='+json.dumps(routes,separators=(',',':')))
'''
interpreters=['/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
              '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3']
for interpreter in interpreters:
 if not Path(interpreter).is_file():continue
 try:
  proc=subprocess.run([interpreter,'-c',PYCODE],cwd='/root/nox/scripts',
                      text=True,capture_output=True,timeout=18)
  line=next((v for v in proc.stdout.splitlines() if v.startswith('NOX_ROUTE_INVENTORY_JSON=')),None)
  if proc.returncode or line is None:continue
  got=json.loads(line.split('=',1)[1])
  for row in proc.stdout.splitlines():
   if row.startswith(('NOX_MOUNT_JSON=','NOX_TARGET_ROUTE_JSON=','NOX_MATCH_JSON=','NOX_MIDDLEWARE_JSON=')):
    emit('ROUTE_ORDER',json.loads(row.split('=',1)[1]))
  emit('REGISTERED_ROUTES_COUNT',{'count':len(got)})
  for route in sorted(got,key=lambda x:x['path']):
   if route['path'].startswith('/api/'):
    emit('APP_ROUTE',route)
  break
 except (OSError,subprocess.TimeoutExpired,ValueError):continue
else:emit('REGISTERED_ROUTES_COUNT',{'status':'HOLD_APP_IMPORT_FAILED'})
# Query S03 table names and owner native status *shape*, never records or credentials.
# No model text is generated by this read-only diagnostic.
DETAILS = '''
import asyncio,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,'/root/nox/scripts')
import chat_proxy
try:
 import s03_memory
 db=Path(s03_memory.DB)
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as conn:
  names=[x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
  cols=[x[1] for x in conn.execute('PRAGMA table_info(s03_items)')]
 print('NOX_S03_DB_META_JSON='+json.dumps({'db_file':db.is_file(),'tables':names[:30],
  's03_items_columns':cols,'has_dialog_table':any('dialog' in x.lower() for x in names)}))
except Exception as e:
 print('NOX_S03_DB_META_JSON='+json.dumps({'status':'HOLD_METADATA','type':type(e).__name__}))
async def status():
 try:
  ret=await chat_proxy.nox_status()
  val=ret if isinstance(ret,dict) else json.loads(ret.body) if hasattr(ret,'body') else {}
  if not isinstance(val,dict):val={}
  print('NOX_STATUS_META_JSON='+json.dumps({'keys':sorted(val)[:50],
   'native_p02_bound':val.get('native_p02_bound') is True,
   'backend_existing':val.get('backend')=='EXISTING_NATIVE_ONEHOST',
   'has_primary_model':bool(val.get('primary_model')),
   'native_memory_bound':val.get('native_cognitive_memory_bound') is True}))
 except Exception as e:
  print('NOX_STATUS_META_JSON='+json.dumps({'status':'HOLD_STATUS_METADATA','type':type(e).__name__}))
asyncio.run(status())
'''
for interpreter in interpreters:
 if not Path(interpreter).is_file():continue
 try:
  proc=subprocess.run([interpreter,'-c',DETAILS],cwd='/root/nox/scripts',
                      text=True,capture_output=True,timeout=18)
  for row in proc.stdout.splitlines():
   for k in ('NOX_S03_DB_META_JSON=','NOX_STATUS_META_JSON='):
    if row.startswith(k):emit('METADATA',{'kind':k[:-1],'body':json.loads(row.split('=',1)[1])})
  if proc.returncode==0:break
 except (OSError,subprocess.TimeoutExpired,ValueError):continue
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    original=ssh.api
    def api(method,path,key,data=None):
        r=original(method,path,key,data)
        if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
        return r
    ssh.REMOTE=REMOTE;ssh.api=api
    out=io.StringIO();okay=False
    try:
        with contextlib.redirect_stdout(out):okay=ssh.probe()
    except Exception as e:
        s=str(e)
        print('NOX_V110_HOLD='+(s if s.startswith('HOLD_') else 'CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if not ssh.cleanup():okay=False
        except Exception:okay=False
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V110_') and len(line)<800:
            print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):print(line[:120])
    print('NOX_V110_NATIVE_PROBE='+str(bool(okay)).lower())
    return 0 if okay else 2
if __name__=='__main__':raise SystemExit(main())
