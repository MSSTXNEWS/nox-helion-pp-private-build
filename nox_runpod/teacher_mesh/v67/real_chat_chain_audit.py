"""NOX E2 V67: identify actual OneHost request route and potential stall. Read-only."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time

_prior=c.api
def _api(method,path,key,data=None):
    r=_prior(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,urllib.request,urllib.error,json,http.client,re,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V67_EXISTING_CHAT_CHAIN_ROUTES_V1')
p=Path('/root/nox/scripts/agent_loop.py')
if p.is_file() and p.stat().st_size<300000:
    try:
        tree=ast.parse(p.read_text(encoding='utf-8',errors='replace'))
        fun=[x for x in ast.walk(tree) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))]
        for n in fun:
            if n.name in ('owner_completion','run_tool_loop','stream_tokens'):
                print('NATIVE_AGENT_FUNC='+n.name)
                print('NATIVE_AGENT_ASYNC='+str(isinstance(n,ast.AsyncFunctionDef)).lower())
                print('NATIVE_AGENT_YIELDS='+str(sum(isinstance(y,ast.Yield) for y in ast.walk(n))))
                string_constants=[]
                for child in ast.walk(n):
                    if isinstance(child,ast.Constant) and isinstance(child.value,str) and len(child.value)<50:
                        if child.value in ('stream','false','true','/v1/chat/completions','/chat/completions','/nox/chat'):
                            string_constants.append(child.value)
                print('NATIVE_AGENT_KNOWN_STRINGS='+','.join(sorted(set(string_constants))))
            for dec in n.decorator_list:
                if not isinstance(dec,ast.Call):continue
                funname=dec.func.attr if isinstance(dec.func,ast.Attribute) else dec.func.id if isinstance(dec.func,ast.Name) else None
                if funname not in ('post','get','api_route','websocket'):continue
                if not dec.args:continue
                if isinstance(dec.args[0],ast.Constant) and isinstance(dec.args[0].value,str):
                    path=dec.args[0].value
                    if re.fullmatch(r'/[a-zA-Z0-9/_{}-]{1,130}',path):
                        print('NATIVE_AGENT_DECORATED_ROUTE='+funname.upper()+':'+path+':'+n.name)
    except (OSError,SyntaxError):
        print('NATIVE_AGENT_AST=HOLD')
else:print('NATIVE_AGENT_AST=HOLD_MISSING')
# Independent local HTTP openapi, emit paths only not content or auth.
for port in (8080,8095,11111,11112):
    try:
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
        conn.request('GET','/openapi.json',headers={'Accept':'application/json'})
        rsp=conn.getresponse();data=rsp.read(140000);conn.close()
        routes=json.loads(data).get('paths',{}) if rsp.status==200 else {}
        relevant=[]
        for path,methods in routes.items():
            if not isinstance(methods,dict):continue
            if re.fullmatch(r'/[a-zA-Z0-9/_{}-]{1,120}',path):
                if any(w in path.lower() for w in ('chat','agent','model','resonance','stream','queue','task')):
                    relevant.append([path,sorted([m for m in methods if m in ('get','post','put','delete')])])
        print('NATIVE_ROUTES_'+str(port)+'_HTTP='+str(rsp.status))
        print('NATIVE_ROUTES_'+str(port)+'_RELEVANT='+json.dumps(relevant[:22],separators=(',',':')))
    except (OSError,ValueError,TimeoutError):
        print('NATIVE_ROUTES_'+str(port)+'=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
    c.REMOTE=REMOTE;c.api=_api
    ok=False
    try:ok=c.probe()
    except Exception as e:
        v=str(e);print("NOX_E2_CHAIN="+v if v.startswith("HOLD_") and len(v)<100 else "NOX_E2_CHAIN=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
