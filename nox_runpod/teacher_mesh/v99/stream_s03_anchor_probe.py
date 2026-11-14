"""V99: read-only anchor counters on active OneHost. No secrets or private texts."""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
p=Path('/root/nox/scripts/chat_proxy.py')
raw=p.read_bytes();src=raw.decode('utf-8');tree=ast.parse(src)
anchor="            resp = await owner_completion(url, payload, _last_user_text(body), stream)\n            resp = _wrap_ttft(resp, t_gate, _utext)\n"
prior="                ans = payload.get('_agent_final') or ''"
simple="            resp = _wrap_ttft(resp, t_gate, _utext)\n"
print("NATIVE_V99_ANCHORS="+json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
'owner_and_wrap_exact':src.count(anchor),'immediate_final_exact':src.count(prior),
'wrap_only_exact':src.count(simple),'existing_stream_wrap':'_nox_owner_s03_after_stream' in src},
sort_keys=True,separators=(',',':')))
functions={x.name:x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
f=functions['_proxy_completion']
for x in ast.walk(f):
 if isinstance(x,(ast.Call)) and isinstance(x.func,ast.Name) and x.func.id in ('owner_completion','_wrap_ttft','_s03_persist_pair'):
  print("NATIVE_V99_CALL="+json.dumps({'fn':x.func.id,'lineno':x.lineno,'col':x.col_offset},sort_keys=True))
for x in ast.walk(f):
 if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ans' for t in x.targets):
  print("NATIVE_V99_ASSIGN="+json.dumps({'line':x.lineno,'col':x.col_offset,'value_node':type(x.value).__name__},sort_keys=True))
# Source is intentionally not exported, only structural counters.
print('NATIVE_V99_PRIVATE_DATA_EXPORTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();okay=False;ssh.REMOTE=REMOTE
 original=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=original(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep([10,20,40][i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):okay=ssh.probe()
 except Exception as e:print("NOX_V99_HOLD="+(str(e) if str(e).startswith('HOLD_') else 'SSH_ROUTE'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 rows=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V99_','TEMP_SSH_CLEANUP=')):
   print(line[:1300]);rows.append(line)
 passed=bool(okay and any(x.startswith('NATIVE_V99_ANCHORS=') for x in rows) and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V99_READONLY_ANCHOR_SCAN='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
