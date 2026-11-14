"""NOX V67 exact live chat_proxy route, streaming, timeout and backpressure audit."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_before=conn.api
def api(method,path,key,data=None):
    r=_before(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,re,hashlib,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_E2_CHAT_PROXY_AST_20261114_V1')
pid='198698'
try:
    raw=(Path('/proc')/pid/'cmdline').read_bytes().split(b'\0')
    options=[Path(t.decode(errors='replace')) for t in raw if t and b'chat_proxy.py' in t]
    p=next((x for x in options if x.name=='chat_proxy.py' and x.is_file()),None)
except OSError:p=None
if p is None:
    print('NATIVE_CHAT_PROXY_SOURCE=HOLD_NOT_RUNNING_OR_PATH')
else:
    b=p.read_bytes()
    if len(b)>600000:raise SystemExit('HOLD_PROXY_TOO_LARGE')
    print('NATIVE_CHAT_PROXY_SHA256='+hashlib.sha256(b).hexdigest())
    print('NATIVE_CHAT_PROXY_SIZE='+str(len(b)))
    try:t=ast.parse(b.decode('utf-8',errors='replace'))
    except SyntaxError:raise SystemExit('HOLD_PROXY_PYTHON_SYNTAX')
    defs=[n for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    print('NATIVE_CHAT_PROXY_FUNC_COUNT='+str(len(defs)))
    for n in defs:
        source_names= ('chat','stream','nox','completion','proxy','history','status','agent')
        if not any(s in n.name.lower() for s in source_names):continue
        if len(n.name)>80 or not re.fullmatch('[A-Za-z0-9_]+',n.name):continue
        calls=[q for q in ast.walk(n) if isinstance(q,ast.Call)]
        called=[]
        for q in calls:
            name=q.func.attr if isinstance(q.func,ast.Attribute) else q.func.id if isinstance(q.func,ast.Name) else ''
            if name and re.fullmatch('[A-Za-z0-9_]{1,70}',name):called.append(name)
        relevant=('StreamingResponse','stream','stream_tokens','aiter_lines','iter_lines','read','aread',
                  'json','aclose','join','sleep','wait_for','asyncio','get','post','request',
                  'run_tool_loop','append','create_task','gather')
        found=[k for k in relevant if k in called]
        text={'function':n.name,'async':isinstance(n,ast.AsyncFunctionDef),
              'yields':sum(isinstance(q,(ast.Yield,ast.YieldFrom)) for q in ast.walk(n)),
              'awaits':sum(isinstance(q,ast.Await) for q in ast.walk(n)),
              'loops':sum(isinstance(q,(ast.For,ast.AsyncFor,ast.While)) for q in ast.walk(n)),
              'calls':found,
              'line_count':n.end_lineno-n.lineno+1 if n.end_lineno else None}
        print('NATIVE_CHAT_PROXY_FUNCTION='+json.dumps(text,sort_keys=True,separators=(',',':')))
    for n in defs:
        for d in n.decorator_list:
            if not isinstance(d,ast.Call) or not d.args:continue
            method=d.func.attr if isinstance(d.func,ast.Attribute) else d.func.id if isinstance(d.func,ast.Name) else ''
            path=d.args[0]
            if isinstance(path,ast.Constant) and isinstance(path.value,str) and re.fullmatch(r'/[A-Za-z0-9/_{}-]{1,130}',path.value):
                if any(q in path.value for q in ('chat','nox','status','stream','history')):
                    print('NATIVE_CHAT_PROXY_ROUTE='+method.upper()+':'+path.value+':'+n.name)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    conn.REMOTE=REMOTE;conn.api=api;ok=False
    try:ok=conn.probe()
    except Exception as e:
        v=str(e);print('NOX_E2_PROXY_AST='+v if v.startswith('HOLD_') and len(v)<100 else 'NOX_E2_PROXY_AST=HOLD')
    finally:
        try:
            if not conn.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
