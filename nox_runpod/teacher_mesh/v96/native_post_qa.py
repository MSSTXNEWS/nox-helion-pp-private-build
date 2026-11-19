"""V96 independent native acceptance of V91+V93+V95 existing NOX chat.
No user prompts or records, no production writes or services restarted.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_api=ssh.api
def slow(method,path,key,data=None):
 x=_api(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,time,json,hashlib,urllib.request,urllib.error,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V96_INDEPENDENT_LIVE_GATES_V1')
src=Path('/root/nox/scripts/chat_proxy.py')
expected='68a559781a46f02ea09eddfab6aa425025938d1c447550d18e54511fa1aed017'
actual=hashlib.sha256(src.read_bytes()).hexdigest() if src.is_file() else ''
print('NATIVE_V96_PROXY_SHA_MATCH='+str(actual==expected).lower())
if actual!=expected:raise SystemExit('HOLD_PROXY_SHA_NOT_INSTALLED')
tree=ast.parse(src.read_text())
names={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
required={'_build_messages','_augment','_proxy_completion','_nox_bounded_optional_enrich'}
if not required.issubset(names):raise SystemExit('HOLD_MISSING_NATIVE_PROCESSES')
fn=names['_nox_bounded_optional_enrich']
python_source=ast.get_source_segment(src.read_text(),fn)
prefix='''from concurrent.futures import ThreadPoolExecutor as _NoxPool, TimeoutError as _NoxOptionalTimeout
from threading import BoundedSemaphore as _NoxSemaphore
from pathlib import Path
_NOX_OPTIONAL_ENRICH_POOL = _NoxPool(max_workers=1)
_NOX_OPTIONAL_ENRICH_GATE = _NoxSemaphore(1)
'''
scope={}
exec(compile(prefix+python_source,'<isolated-v95-source-test>','exec'),scope)
call=scope['_nox_bounded_optional_enrich']
started=time.perf_counter()
ret=call(lambda text:(time.sleep(.7),['sample'])[1],'SYNTHETIC')
dt=(time.perf_counter()-started)*1000
blocked=call(lambda text:['unexpected'],'SYNTHETIC')
time.sleep(.74)
fast=call(lambda text:['SYNTHETIC_VALID'],'SYNTHETIC')
scope['_NOX_OPTIONAL_ENRICH_POOL'].shutdown(wait=True)
source_test=(ret==[] and blocked==[] and fast==['SYNTHETIC_VALID'] and dt<=500)
print('NATIVE_V96_OPTIONAL_BUDGET_TEST='+json.dumps({'accepted':source_test,'synthetic_elapsed_ms':round(dt,1),'parallel_submissions_blocked':blocked==[],'fast_output_after_release':fast==['SYNTHETIC_VALID']},separators=(',',':')))
if not source_test:raise SystemExit('HOLD_BUDGET_TEST')
for port in (8080,8081):
 with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=4) as r:status=r.status
 print('NATIVE_V96_HEALTH_'+str(port)+'='+str(status))
 if status!=200:raise SystemExit('HOLD_HEALTH')
with urllib.request.urlopen('http://127.0.0.1:8080/chat',timeout=5) as r:
 html=r.read(120000)
print('NATIVE_V96_V86_PROGRESSIVE_RENDER='+str(b'revealNativeContent' in html).lower())
# Existing supervised trainer status; no new optimizer steps are claimed.
p=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],capture_output=True,text=True,timeout=8)
words=p.stdout.split()
print('NATIVE_V96_VOLTA_STATE='+str(words[1] if len(words)>1 else 'UNKNOWN'))
print('NATIVE_V96_OWNER_CHAT_FULL_E2E_TESTED=false')
print('NATIVE_V96_WEIGHTS_CHANGED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=slow;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  s=str(e);print('NOX_V96='+s if s.startswith('HOLD_') else 'NOX_V96=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
