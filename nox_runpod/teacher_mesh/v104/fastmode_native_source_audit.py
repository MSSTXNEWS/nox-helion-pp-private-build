"""V104: bounded redacted AST owner model-payload mapping, no model/user data."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import contextlib,io,time
orig=ssh.api
def gate(method,path,key,data=None):
    r=orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,copy,hashlib,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V104_CODE_SCHEMA=NOX_REDACTED_MODEL_STREAM_PAYLOAD_V1')
allowed={'stream','messages','model','content','temperature','max_tokens','n_predict','cache_prompt',
         'chat_template_kwargs','enable_thinking','reasoning_budget','tools','tool_choice',
         'user','assistant','system','data','choices','delta','final','usage','DONE',
         'input','output','stop','timeout','body','payload','memory','response','context',
         'think','thinking','low','high','auto','reasoning_content','source','S03'}
class Scrub(ast.NodeTransformer):
    def visit_Constant(self,n):
        if isinstance(n.value,str):
            value=n.value if n.value in allowed else 'REDACTED'
            return ast.copy_location(ast.Constant(value),n)
        return n
for basename in ('agent_loop.py','chat_proxy.py'):
    path=Path('/root/nox/scripts')/basename
    if not path.is_file() or path.is_symlink() or path.stat().st_size>250000:continue
    b=path.read_bytes();t=ast.parse(b)
    print('NATIVE_V104_SOURCE='+json.dumps({'file':basename,'sha256':hashlib.sha256(b).hexdigest(),
                 'size':len(b)},separators=(',',':')))
    funcs=(('stream_tokens','run_tool_loop','owner_completion','stream_generate','chat_stream')
           if basename=='agent_loop.py' else
           ('_proxy_completion','_build_messages','_last_user_text'))
    for n in ast.walk(t):
        if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name not in funcs:continue
        for c in ast.walk(n):
            if isinstance(c,ast.Call):
                fn=c.func.attr if isinstance(c.func,ast.Attribute) else c.func.id if isinstance(c.func,ast.Name) else ''
                if fn in ('post','stream','acreate','create','request','completion','chat_completion'):
                    print('NATIVE_V104_CALL='+json.dumps({'file':basename,'parent':n.name,'method':fn,
                      'line':c.lineno,'kwargs':[x.arg for x in c.keywords][:12]},separators=(',',':')))
        safe=Scrub().visit(copy.deepcopy(n))
        for i,line in enumerate(ast.unparse(safe).splitlines()[:110],1):
            if any(s in line for s in ('request(','.post(','.stream(', 'payload','max_tokens',
                   'stream_tokens','chat_template_kwargs','cache_prompt','owner_completion',
                   'messages','yield','return','httpx','iter_lines','get_reader')):
                print('NATIVE_V104_LINE='+json.dumps({'file':basename,'fn':n.name,'line':i,'code':line[:225]},
                                                   separators=(',',':'))[:580])
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    ssh.REMOTE=REMOTE;ssh.api=gate;stdout=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(stdout):ok=ssh.probe()
    except Exception as e:
        msg=str(e);print('NOX_V104_CODE_HOLD='+msg if msg.startswith('HOLD_') and len(msg)<90 else 'HOLD_NATIVE')
    finally:
        try:
            with contextlib.redirect_stdout(stdout):
                if not ssh.cleanup():ok=False
        except Exception:ok=False
    for line in stdout.getvalue().splitlines():
        if line.startswith(('NATIVE_V104_','TEMP_SSH_CLEANUP=')) and len(line)<780:print(line)
    returncode=0 if ok and 'NATIVE_V104_SOURCE=' in stdout.getvalue() else 2
    raise SystemExit(returncode)
