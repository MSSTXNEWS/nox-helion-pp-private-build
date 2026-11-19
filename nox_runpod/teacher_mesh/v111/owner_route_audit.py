"""V111 inspect real owner cookie login, V29 routes and S03 poststream seams.
Read-only. No private owner credentials, cookies or messages exported.
"""
from __future__ import annotations
import contextlib, io, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,urllib.request,urllib.error,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
p=Path('/root/nox/scripts/chat_proxy.py')
raw=p.read_bytes()
tree=ast.parse(raw)
def emit(k,v):
    s=json.dumps(v,sort_keys=True,separators=(',',':'))
    if len(s)<750:print('NATIVE_V111_'+k+'='+s)
emit('SOURCE',{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
selected=('chat_login','chat_session','_read_chat_password','_set_session_cookie','nox_v29_status','_session_ok','_proxy_completion','_s03_persist_pair')
for n in tree.body:
 if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name not in selected:continue
 if n.name=='_proxy_completion':
  source=ast.get_source_segment(raw.decode(),n) or ''
  emit('PROXY_STREAM',{'has_deferred_v98':('_nox_owner_s03_after_stream' in source),
                      'poststream_source_presence':('_agent_final' in source),
                      'source_lines':n.end_lineno-n.lineno+1})
  continue
 if n.name=='_read_chat_password':
  emit('PASSWORD_FUNCTION',{'present':True,'source_lines':n.end_lineno-n.lineno+1})
  continue
 if n.name=='_session_ok':
  emit('SESSION',{'present':True,'source_lines':n.end_lineno-n.lineno+1})
  continue
 if n.name=='_s03_persist_pair':
  emit('PERSIST',{'present':True,'source_lines':n.end_lineno-n.lineno+1})
  continue
 lines=ast.unparse(n).splitlines()
 for i,line in enumerate(lines):
  # Source contains no credential VALUES, but defend against literal leakage.
  if any(s in line.lower() for s in ('password','secret','token','apikey','api_key','passkey')):
   if not line.strip().startswith(('if ','elif ','def ','async def ','@')):continue
  emit('CODE',{'function':n.name,'line':i+1,'code':line[:530]})
for path,method in (('/health','GET'),('/chat/session','GET'),
                    ('/api/nox/chat/stream','POST'),('/api/nox/status','GET')):
 req=urllib.request.Request('http://127.0.0.1:8080'+path,
     data=(b'{}' if method=='POST' else None),
     headers={'Content-Type':'application/json'},method=method)
 try:
  with urllib.request.urlopen(req,timeout=3) as response:code=response.status
 except urllib.error.HTTPError as err:code=err.code
 except Exception:code=None
 emit('ANONYMOUS_ROUTE',{'path':path,'method':method,'http':code})
print('NATIVE_V111_OWNER_AUTH_SESSION_CREATED=false')
print('NATIVE_V111_PRIVATE_RECORDS_EXPORTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    original=ssh.api
    def safeapi(method,path,key,data=None):
        for index in range(4):
            try:
                res=original(method,path,key,data)
                if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
                return res
            except RuntimeError as e:
                if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or index==3:raise
                time.sleep((10,20,40)[index])
    ssh.api=safeapi
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V111_','TEMP_SSH_CLEANUP=')):
            print(line[:900])
    verified=bool(ok and any(x.startswith('NATIVE_V111_SOURCE=') for x in lines)
                  and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
    print('NOX_V111_SAFE_SOURCE_AUDIT='+str(verified).lower())
    return 0 if verified else 2
if __name__=='__main__':raise SystemExit(main())
