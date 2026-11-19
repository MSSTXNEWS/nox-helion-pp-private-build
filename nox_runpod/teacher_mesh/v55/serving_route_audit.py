"""NOX V55 read-only identify existing live HTTP serving endpoints.

No POST, no auth material, no prompt or chat history transferred. Reuse
V51 temporary SSH with exact key detach and no new service.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import re,os,ast,json,urllib.request,urllib.error,http.client,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V55_EXISTING_SERVING_ROUTES_READ_ONLY_V1')
ports=[8080,8081,8082,8084,8087,8088,8092,8093,8095,8384,8888,11111,11112]
def small_get(port,path):
    try:
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=.9)
        c.request('GET',path,headers={'Accept':'application/json','Connection':'close'})
        r=c.getresponse()
        status=r.status
        data=r.read(3000)
        c.close()
        try:x=json.loads(data)
        except (ValueError,UnicodeError):x=None
        return status,x
    except (OSError,TimeoutError,http.client.HTTPException):
        return None,None
for port in ports:
    status,info=small_get(port,'/health')
    print('NATIVE_HTTP_'+str(port)+'_HEALTH_STATUS='+str(status or 'HOLD'))
    if isinstance(info,dict):
        safe=[k for k in info.keys() if re.fullmatch('[A-Za-z0-9_]{1,60}',str(k))][:18]
        print('NATIVE_HTTP_'+str(port)+'_HEALTH_KEYS='+','.join(safe))
    status,info=small_get(port,'/v1/models')
    print('NATIVE_HTTP_'+str(port)+'_MODELS_STATUS='+str(status or 'HOLD'))
    if status==200 and isinstance(info,dict):
        data=info.get('data')
        if isinstance(data,list):
            ids=[]
            for item in data[:10]:
                if not isinstance(item,dict):continue
                val=item.get('id')
                if isinstance(val,str) and re.fullmatch('[a-zA-Z0-9_/.:+ -]{1,95}',val):
                    ids.append(val)
            print('NATIVE_HTTP_'+str(port)+'_MODEL_IDS='+json.dumps(ids,ensure_ascii=False))
# Match listener PID and executable name without arguments.
try:
    p=subprocess.run(['ss','-H','-ltnp'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=5)
    for line in p.stdout.splitlines()[:100]:
        m=re.search(r':([0-9]{2,5})\s',line)
        if not m:continue
        port=int(m.group(1))
        if port not in ports:continue
        process=re.search(r'\(\("([^"]{1,70})",pid=([0-9]+)',line)
        if process:
            print('NATIVE_HTTP_'+str(port)+'_PID='+process.group(2))
            print('NATIVE_HTTP_'+str(port)+'_PROGRAM='+process.group(1))
except (OSError,subprocess.TimeoutExpired):pass
# Match native command adapter entry points only by source AST; no code or secrets.
p=Path('/root/nox/scripts/agent_loop.py')
if p.is_file():
    try:
        tree=ast.parse(p.read_text(encoding='utf-8',errors='replace')[:250000])
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in (
                'run_tool_loop','_direct_admin_calls','stream_tokens',
                'owner_completion','apply_confirm'):
                args=[a.arg for a in n.args.posonlyargs+n.args.args+n.args.kwonlyargs]
                print('NATIVE_AGENT_FUNCTION_'+n.name.upper()+'_ARGS='+json.dumps(args[:16]))
                calls=set()
                for q in ast.walk(n):
                    if isinstance(q,ast.Call):
                        if isinstance(q.func,ast.Name):calls.add(q.func.id)
                        elif isinstance(q.func,ast.Attribute):calls.add(q.func.attr)
                safe=[x for x in sorted(calls) if re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,50}',x)]
                print('NATIVE_AGENT_FUNCTION_'+n.name.upper()+'_CALLS='+json.dumps(safe[:40]))
    except (SyntaxError,OSError):print('NATIVE_AGENT_AST=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V55_AUDIT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V55_AUDIT=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print('NOX_V55_SSH_CLEANUP=HOLD')
            ok=False
    raise SystemExit(0 if ok else 2)
