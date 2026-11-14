"""NOX E2 V67: reveal only redacted control flow in prestream helper."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_prev=c.api
def api(method,path,key,data=None):
    r=_prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_E2_UNDERSTANDING_PRESTREAM_FLOW_V1')
data=(Path('/proc/198698/cmdline').read_bytes().split(b'\0'))
p=next((Path(x.decode()) for x in data if x.endswith(b'chat_proxy.py')),None)
if not p or not p.is_file():raise SystemExit('HOLD_PROXY_PATH')
t=ast.parse(p.read_text(encoding='utf-8',errors='replace'))
allow=('stream','messages','content','model','max_tokens','error','state',
       'ready','timeout','status','response','tool','text','prompt','messages')
class Redact(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str):
            return ast.copy_location(ast.Constant(value=node.value if node.value in allow else '[REDACTED]'),node)
        return node
targets={'_understanding_http':165,'_wrap_ttft':90,'_build_messages':110,'load_backend':80}
for n in ast.walk(t):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in targets:
        print('NATIVE_HELPER_FN='+n.name)
        safe=Redact().visit(copy.deepcopy(n))
        lines=ast.unparse(safe).splitlines()
        print('NATIVE_HELPER_TOTAL_LINES='+str(len(lines)))
        for i,line in enumerate(lines[:targets[n.name]],1):
            print('NATIVE_HELPER_'+n.name.upper()+'_'+str(i)+'='+line[:260])
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE;c.api=api;ok=False
    try:ok=c.probe()
    except Exception as e:
        v=str(e);print('NOX_E2_HELPER='+v if v.startswith('HOLD_') and len(v)<100 else 'NOX_E2_HELPER=HOLD')
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
