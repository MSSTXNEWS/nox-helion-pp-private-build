"""NOX E2 V67: sanitized AST for exact existing authenticated proxy flow."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_orig=c.api
def guarded(method,path,key,data=None):
    r=_orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,os
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V67_SANITIZED_PROXY_FLOW_V1')
root=Path('/proc/198698/cmdline')
try:
    parts=root.read_bytes().split(b'\0')
    file=next((Path(x.decode()) for x in parts if x.endswith(b'chat_proxy.py')),None)
except (OSError,ValueError):file=None
if file is None or not file.is_file():
    raise SystemExit('HOLD_PROXY_SOURCE')
blob=file.read_text(encoding='utf-8',errors='replace')
if len(blob)>200000:raise SystemExit('HOLD_LARGE_PROXY')
tree=ast.parse(blob)
allowed=('stream','messages','content','model','max_tokens','delta','data:','[DONE]',
         'choices','Authorization','Accept','text/event-stream','application/json','status',
         'error','temperature','user','assistant','tool','response','state','session')
class Redact(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str):
            return ast.copy_location(ast.Constant(value=node.value if node.value in allowed else '[REDACTED]'),node)
        return node
targets={'chat_api':35,'chat':10,'_proxy_completion':135,'_ops_agent_http':35,'_understanding_http':85,'_build_messages':70,'_trim_ctx':50,'_wrap_ttft':50}
for n in ast.walk(tree):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in targets:
        safe=Redact().visit(copy.deepcopy(n))
        for k,line in enumerate(ast.unparse(safe).splitlines()[:targets[n.name]]):
            if len(line)>240:line=line[:240]
            print('NATIVE_FLOW_'+n.name.upper()+'_'+str(k+1)+'='+line)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE;c.api=guarded;ok=False
    try:ok=c.probe()
    except Exception as e:
        v=str(e);print('NOX_E2_PROXY_FLOW='+v if v.startswith('HOLD_') and len(v)<100 else 'NOX_E2_PROXY_FLOW=HOLD')
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
