"""Print redacted AST source of existing NOX chat functions, no strings or secrets."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
p=Path('/root/nox/scripts/agent_loop.py')
try:
    root=ast.parse(p.read_text(encoding='utf-8',errors='replace'))
except Exception:
    print('NATIVE_SAFE_SOURCE=HOLD')
    print('NATIVE_READ_ONLY_COMPLETE=true')
    raise SystemExit(0)

ALLOW={
'model','messages','stream','temperature','max_tokens','tools','tool_choice','user',
'assistant','system','content','choices','delta','finish_reason','data:',
'status','done','text','tool_calls','function','arguments','name','response',
'role','id','type','result','error','stop','chat','max_steps','limit','deep',
'owner','analysis','tool','completed','reason','command','ok',
'message','prompt','required','none','auto','nox','usage',
}
class Safe(ast.NodeTransformer):
    def visit_Constant(self, n):
        if isinstance(n.value,str) and n.value not in ALLOW:
            return ast.copy_location(ast.Constant(value='<redacted>'),n)
        return n
    def visit_JoinedStr(self,n):
        return ast.copy_location(ast.Constant(value='<formatted-redacted>'),n)

for q in ast.walk(root):
    if not isinstance(q,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
    if q.name not in ('run_tool_loop','owner_completion','stream_tokens'):continue
    z=copy.deepcopy(q)
    z.decorator_list=[]
    z=Safe().visit(z)
    try:raw=ast.unparse(z)
    except Exception:
        print('NATIVE_SAFE_SOURCE_'+q.name.upper()+'=HOLD_UNPARSE')
        continue
    if len(raw)>38000:
        print('NATIVE_SAFE_SOURCE_'+q.name.upper()+'=HOLD_TOO_LARGE')
        continue
    print('NATIVE_SAFE_SOURCE_'+q.name.upper()+'_LINES='+str(len(raw.splitlines())))
    for i,line in enumerate(raw.splitlines(),1):
        line=line.strip()
        if not line:continue
        if len(line)>680:line=line[:680]+'<truncated>'
        print('NATIVE_SAFE_SRC_'+q.name.upper()+'_'+str(i).zfill(3)+'='+line)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    good=False
    try:good=c.probe()
    except Exception as ex:
        x=str(ex)
        print('NATIVE_SAFE_SOURCE_RESULT='+x if x.startswith('HOLD_') else 'NATIVE_SAFE_SOURCE_RESULT=HOLD_EXCEPTION')
    finally:
        try:
            if not c.cleanup():good=False
        except Exception:good=False
    raise SystemExit(0 if good else 2)
