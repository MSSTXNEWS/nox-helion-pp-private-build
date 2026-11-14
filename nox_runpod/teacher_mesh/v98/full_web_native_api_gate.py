"""NOX V98: fail-closed V29.3 92-route native OneHost acceptance inventory.

Static route existence is only the FIRST gate; it is never represented as a
working function. No deployment, no public preview, no model or S03 mutations.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
old=ssh.api
def delay(method,path,key,data=None):
 x=old(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,ast,hashlib,json,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V98_ALL_WEB_FUNCTIONS_REAL_ROUTE_GATE_V1')
site=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
proxy=Path('/root/nox/scripts/chat_proxy.py')
if not site.is_dir() or not (site/'nox-chat.js').is_file():raise SystemExit('HOLD_FROZEN_WEB_NOT_PRESENT')
assert hashlib.sha256((site/'nox-chat.js').read_bytes()).hexdigest()=='d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce'
required={}
for file in sorted(site.iterdir()):
 if file.suffix not in ('.js','.mjs') or not file.is_file() or file.is_symlink():continue
 text=file.read_text(errors='replace')
 for m in re.finditer(r'''["'](/(?:api|v1)/[a-zA-Z0-9_/?={}&.\-]+)["']''',text):
  route=m.group(1).split('?',1)[0]
  required.setdefault(route,[]).append(file.name)
source=proxy.read_text()
tree=ast.parse(source)
native={}
for obj in ast.walk(tree):
 if not isinstance(obj,(ast.AsyncFunctionDef,ast.FunctionDef)):continue
 for decorator in obj.decorator_list:
  if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Attribute):continue
  if decorator.func.attr not in ('post','get','put','delete','patch','api_route','websocket'):continue
  if not decorator.args or not isinstance(decorator.args[0],ast.Constant):continue
  path=decorator.args[0].value
  if isinstance(path,str) and path.startswith('/'):
   native.setdefault(path,[]).append({'method':decorator.func.attr,'handler':obj.name})
# Match concrete route if registered, or path parameters like /api/jobs/{job_id}.
def matches(path,pattern):
 a=path.strip('/').split('/')
 b=pattern.strip('/').split('/')
 if len(a)!=len(b):return False
 return all(x==y or (y.startswith('{') and y.endswith('}')) for x,y in zip(a,b))
real=set()
unbound=[]
for path in sorted(required):
 bound=next((p for p in native if matches(path,p)),None)
 if bound is None:unbound.append(path)
 else:real.add(path)
def emit(key,data):
 print(key+'='+json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')))
emit('NATIVE_V98_SUMMARY',{'source_sha256':hashlib.sha256((site/'nox-chat.js').read_bytes()).hexdigest(),
 'unique_frontend_api_path_references':len(required),'direct_native_route_matches':len(real),
 'unbound_direct_native_route_count':len(unbound),
 'public_preview_exposes_no_native_training_proof':True,
 'completed_feature_e2e_tests':0,'production_switch_allowed':False,
 'frontend_release_replaces_existing_chat':False,
 'training_own_weights_triggered':False})
for path in unbound[:125]:
 emit('NATIVE_V98_UNBOUND',{'route':path,'source_count':len(set(required[path]))})
for path in sorted(real):
 emit('NATIVE_V98_ROUTE_PRESENT_ONLY',{'route':path,'function_e2e_pass':False,
     'authorisation_e2e_pass':False})
# Live 404 vs protected 401 is just an unauthenticated discoverability probe.
for path in ('/api/nox/status','/api/nox/chat/stream','/api/ui/capabilities','/chat/api',
             '/nox','/health'):
 try:
  request=urllib.request.Request('http://127.0.0.1:8080'+path,
      headers={'User-Agent':'NOX-V98-NO-STUB-READONLY'},method='GET')
  with urllib.request.urlopen(request,timeout=3) as r:code=r.status
 except urllib.error.HTTPError as e:code=e.code
 except Exception:code=0
 emit('NATIVE_V98_HTTP',{'route':path,'method':'GET','status':code})
print('NATIVE_NO_PRODUCTION_MUTATION=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay;good=False
 try:good=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V98='+v if v.startswith('HOLD_') else 'NOX_V98=HOLD_NATIVE')
 finally:
  try:
   if not ssh.cleanup():good=False
  except Exception:good=False
 raise SystemExit(0 if good else 2)
