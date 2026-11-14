"""V107: why the authentic V29 bridge failed post-install? No production writes."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
initial=ssh.api
def wait_attach(method,path,key,data=None):
 val=initial(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return val
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,subprocess,os,stat,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V107_BRIDGE_POSTINSTALL_FAILURE_FORENSICS_V1')
P=Path('/root/nox/scripts/chat_proxy.py')
B=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
src=P.read_bytes()
print('NATIVE_V107_PROXY='+json.dumps({'sha256':hashlib.sha256(src).hexdigest(),
    'size':len(src),'bridge_registration_in_live':b'register_native_v29_chat(app' in src},separators=(',',':')))
print('NATIVE_V107_MODULE='+json.dumps({'present':B.is_file(),'size':B.stat().st_size if B.is_file() else 0,
    'mode':oct(stat.S_IMODE(B.stat().st_mode)) if B.is_file() else None},separators=(',',':')))
if not B.is_file():raise SystemExit('HOLD_NO_STAGED_BRIDGE')
test_source='''
import sys,types,ast
sys.path.insert(0,'/root/nox/scripts')
from pathlib import Path
base=Path('/root/nox/scripts/chat_proxy.py').read_text()
from nox_v29_chat_bridge import register_native_v29_chat
tree=ast.parse(base)
chat=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='chat_api')
lines=base.splitlines(keepends=True)
position=min(d.lineno for d in chat.decorator_list)-1
lines.insert(position,'from nox_v29_chat_bridge import register_native_v29_chat\\nregister_native_v29_chat(app, globals())\\n\\n')
changed=''.join(lines)
code=compile(changed,'/root/nox/scripts/chat_proxy.py','exec')
scope={'__name__':'nox_v107_isolated','__file__':'/root/nox/scripts/chat_proxy.py'}
exec(code,scope,scope)
from fastapi.routing import APIRoute
routes={r.path for r in scope['app'].routes if isinstance(r,APIRoute)}
assert '/api/nox/status' in routes
assert '/api/nox/chat/stream' in routes
assert '/api/nox/stop' in routes
print('ISOLATED_BRIDGE_REGISTERED')
'''
for candidate in ('/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
  '/opt/venv/bin/python','/venv/bin/python','/usr/local/bin/python3'):
 p=Path(candidate)
 if not p.is_file():continue
 try:
  cmd=subprocess.run([str(p),'-c',test_source],cwd='/root/nox/scripts',
        capture_output=True,text=True,timeout=18)
  lines=(cmd.stderr or '').splitlines()
  kinds=[]
  for x in lines[-8:]:
   if x.startswith(('ModuleNotFoundError:','ImportError:','RuntimeError:','AssertionError:','TypeError:','SyntaxError:','ValueError:','NameError:','KeyError:')):
    kinds.append(x.split(':',1)[0])
  report={'interpreter_basename':p.name,'interpreter_prefix':p.parent.parent.name,
      'returncode':cmd.returncode,'isolated_registered':'ISOLATED_BRIDGE_REGISTERED' in cmd.stdout,
      'failure_types':kinds,
      'safe_hold_code':next((x.split(':',1)[1].strip()[:85] for x in lines[-8:]
          if x.startswith('RuntimeError: HOLD_')),None)}
  print('NATIVE_V107_RESULT='+json.dumps(report,separators=(',',':')))
  if report['isolated_registered']:break
 except Exception as ex:
  print('NATIVE_V107_RESULT='+json.dumps({'interpreter_basename':p.name,
         'failure_type':type(ex).__name__},separators=(',',':')))
print('NATIVE_V107_NO_PRODUCTION_MUTATION=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 ssh.REMOTE=REMOTE;ssh.api=wait_attach;ok=False
 try:ok=ssh.probe()
 except Exception as e:
  val=str(e);print('NOX_V107='+val if val.startswith('HOLD_') else 'NOX_V107=HOLD_TRANSPORT')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
if __name__=='__main__':raise SystemExit(main())
