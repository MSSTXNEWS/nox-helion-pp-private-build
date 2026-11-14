"""NOX: bounded native read-only live hang and source configuration inspection.

Reuses existing authenticated V51. No user prompt/history, no writes/restarts.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,urllib.request,urllib.error,subprocess,json,re,os,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V64_HANG_DIAGNOSTIC_V1')

def fetch(port,path,timeout=2.5):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=timeout) as resp:
            raw=resp.read(24000)
            return resp.status,raw
    except urllib.error.HTTPError as ex:return ex.code,b''
    except (OSError,TimeoutError):return None,b''

for port in (8080,8081,8095):
    status,_=fetch(port,'/health')
    print(f'NATIVE_HEALTH_{port}='+str(status if status else 'HOLD'))
status,raw=fetch(8081,'/slots')
if status==200:
    try:
        data=json.loads(raw)
        if isinstance(data,list):
            print('NATIVE_MAIN_SLOTS_COUNT='+str(len(data)))
            print('NATIVE_MAIN_SLOTS_ACTIVE='+str(sum(bool(s.get('is_processing')) for s in data if isinstance(s,dict))))
            for slot in data[:8]:
                if not isinstance(slot,dict):continue
                idx=slot.get('id')
                if type(idx) is not int:continue
                state={k:slot.get(k) for k in ('id','is_processing','n_ctx','n_past','n_predict','n_decoded','n_remaining') if k in slot and type(slot[k]) in (bool,int)}
                print('NATIVE_SLOT_STATE='+json.dumps(state,separators=(',',':')))
    except (ValueError,TypeError):print('NATIVE_MAIN_SLOTS=HOLD_SCHEMA')
else: print('NATIVE_MAIN_SLOTS=HOLD_HTTP_'+str(status))
status,raw=fetch(8081,'/metrics')
if status==200:
    text=raw.decode('utf-8','replace')
    for field in ('llamacpp:requests_processing','llamacpp:requests_deferred',
                  'llamacpp:kv_cache_usage_ratio','llamacpp:prompt_tokens_total',
                  'llamacpp:predicted_tokens_total'):
        matches=re.findall(r'(?m)^'+re.escape(field)+r'(?:\{[^{}]{0,100}\})?\s+([0-9.eE+-]+)$',text)
        if matches:print('NATIVE_METRIC_'+re.sub('[^a-zA-Z0-9]','_',field).upper()+'='+matches[0])

p=Path('/root/nox/scripts/agent_loop.py')
if not p.is_file():print('NATIVE_AGENT_SOURCE=HOLD_NOT_FOUND')
else:
    try:t=ast.parse(p.read_text(encoding='utf-8',errors='replace'))
    except (OSError,SyntaxError):print('NATIVE_AGENT_SOURCE=HOLD_AST')
    else:
        for fn in ast.walk(t):
            if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) or fn.name not in ('run_tool_loop','stream_tokens','owner_completion'):
                continue
            key='NATIVE_FUNC_'+fn.name.upper()
            print(key+'_LOC='+str(fn.lineno)+':'+str(fn.end_lineno))
            print(key+'_ARGS='+','.join(a.arg for a in fn.args.args if re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]{0,40}',a.arg)))
            nodes=list(ast.walk(fn))
            for nd in nodes:
                if isinstance(nd,(ast.For,ast.AsyncFor)) and isinstance(nd.iter,ast.Call) and isinstance(nd.iter.func,ast.Name) and nd.iter.func.id=='range':
                    args=[]
                    for a in nd.iter.args:
                        if isinstance(a,ast.Constant) and type(a.value) is int:args.append(str(a.value))
                        elif isinstance(a,ast.Name):args.append(a.id)
                    if args:print(key+'_RANGE_'+str(nd.lineno)+'='+','.join(args))
                if isinstance(nd,(ast.Assign,ast.AnnAssign)):
                    v=nd.value
                    if not isinstance(v,ast.Constant) or type(v.value) not in (int,bool,float):continue
                    targets=nd.targets if isinstance(nd,ast.Assign) else [nd.target]
                    for trg in targets:
                        if isinstance(trg,ast.Name) and re.search('max|round|limit|timeout|budget|token|depth|step',trg.id,re.I):
                            print(key+'_BOUND_'+str(nd.lineno)+'_'+trg.id.upper()+'='+str(v.value))
                if isinstance(nd,ast.Dict):
                    for k,v in zip(nd.keys,nd.values):
                        if isinstance(k,ast.Constant) and k.value in ('stream','max_tokens','n_predict','temperature','tools','tool_choice'):
                            if isinstance(v,ast.Constant) and type(v.value) in (bool,int,float,str):
                                value=str(v.value)[:25] if not isinstance(v.value,str) else 'STR'
                            elif isinstance(v,ast.Name):value='VAR_'+v.id
                            else:value=type(v).__name__
                            print(key+'_PAYLOAD_'+str(nd.lineno)+'_'+str(k.value).upper()+'='+value)
            for nd in nodes:
                if isinstance(nd,ast.Call) and isinstance(nd.func,(ast.Name,ast.Attribute)):
                    name=nd.func.id if isinstance(nd.func,ast.Name) else nd.func.attr
                    if name in ('stream_tokens','StreamingResponse','asyncio','sleep','join','run_tool_loop'):
                        print(key+'_CALL_'+str(nd.lineno)+'='+name)
        print('NATIVE_AGENT_SOURCE_AST=PASS')

try:
    ps=subprocess.run(['supervisorctl','status'],capture_output=True,text=True,timeout=6)
    if ps.returncode==0:
        for line in ps.stdout.splitlines()[:50]:
            parts=line.split()
            if len(parts)>1 and re.fullmatch('[a-zA-Z0-9_.:@-]{1,70}',parts[0]):
                print('NATIVE_SERVICE='+parts[0]+':'+parts[1][:20])
except (OSError,subprocess.TimeoutExpired):pass

try:
    gpu=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if gpu.returncode==0:
        for s in gpu.stdout.splitlines()[:2]:
            if re.fullmatch(r'[0-9, ]{3,80}',s):print('NATIVE_GPU='+s.replace(' ',''))
except (OSError,subprocess.TimeoutExpired):pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as e:
        err=str(e)
        print('NATIVE_V64_RESULT='+err if err.startswith('HOLD_') else 'NATIVE_V64_RESULT=HOLD_EXCEPTION')
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
