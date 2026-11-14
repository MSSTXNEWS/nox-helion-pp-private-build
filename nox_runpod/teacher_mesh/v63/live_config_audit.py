"""NOX V63: safe config and tool-loop latency audit on installed OneHost."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,os,re,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_TOOL_LOOP_AND_LLAMA_FLAGS_V1')

src=Path('/root/nox/scripts/agent_loop.py')
if src.is_file():
    try:
        t=ast.parse(src.read_text(encoding='utf-8',errors='replace'))
        wanted={'run_tool_loop','owner_completion','stream_tokens'}
        for node in ast.walk(t):
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in wanted:
                continue
            all_nodes=list(ast.walk(node))
            calls=[p for p in all_nodes if isinstance(p,ast.Call)]
            for action in ('stream_tokens','await','nox_run_admin','query','tool_call','create_task','gather'):
                count=sum(((isinstance(x.func,ast.Name) and x.func.id==action)
                           or (isinstance(x.func,ast.Attribute) and x.func.attr==action))
                          for x in calls)
                if count:print('NATIVE_'+node.name.upper()+'_'+action.upper()+'_CALLS='+str(count))
            loops=[p for p in all_nodes if isinstance(p,(ast.For,ast.AsyncFor,ast.While))]
            print('NATIVE_'+node.name.upper()+'_LOOP_COUNT='+str(len(loops)))
            print('NATIVE_'+node.name.upper()+'_YIELD_COUNT='+str(sum(isinstance(p,(ast.Yield,ast.YieldFrom)) for p in all_nodes)))
            for q in all_nodes:
                if isinstance(q,ast.Call) and isinstance(q.func,ast.Name) and q.func.id=='range' and q.args:
                    n=q.args[-1]
                    if isinstance(n,ast.Constant) and isinstance(n.value,int):
                        print('NATIVE_'+node.name.upper()+'_FIXED_LOOP_BOUND='+str(n.value))
            for q in all_nodes:
                if isinstance(q,ast.Dict):
                    for k,v in zip(q.keys,q.values):
                        if isinstance(k,ast.Constant) and k.value in ('max_tokens','max_new_tokens','n_predict','stream','temperature'):
                            if isinstance(v,ast.Constant) and isinstance(v.value,(int,float,bool)):
                                print('NATIVE_'+node.name.upper()+'_REQUEST_'+str(k.value).upper()+'='+str(v.value))
    except (OSError,SyntaxError):
        print('NATIVE_AGENT_LOOP_AST=HOLD')
else:
    print('NATIVE_AGENT_LOOP_AST=HOLD_MISSING')

safe=('--ctx-size','-c','--parallel','-np','--threads','-t','--threads-batch','-tb','--n-gpu-layers','-ngl','--batch-size','-b','--ubatch-size','-ub','--flash-attn','--cache-type-k','--cache-type-v','--split-mode','--no-mmap','--mlock','--cont-batching')
boolean={'--flash-attn','--no-mmap','--mlock','--cont-batching'}
pid=None
try:
    out=subprocess.run(['ss','-H','-ltnp'],capture_output=True,text=True,timeout=5).stdout
    for line in out.splitlines():
        if re.search(r'(?:^|\s)(?:[0-9.:]+:)?8081\s',line):
            hit=re.search(r'pid=([0-9]+)',line)
            if hit:
                pid=int(hit.group(1));break
except (OSError,subprocess.TimeoutExpired):pass
if pid is None:
    print('NATIVE_MAIN_MODEL_FLAGS=HOLD_NO_PID')
else:
    print('NATIVE_MAIN_MODEL_PID_KNOWN=true')
    try:
        cmd=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0')
        arguments=[s.decode('utf-8','replace')[:512] for s in cmd if s][:300]
        for i,s in enumerate(arguments):
            if s in safe:
                tag='NATIVE_LLAMA_FLAG_'+re.sub('[^A-Za-z0-9]','_',s).upper()
                if s in boolean:
                    print(tag+'=true')
                elif i+1<len(arguments) and re.fullmatch(r'[0-9.]{1,15}|[a-z_-]{1,25}',arguments[i+1]):
                    print(tag+'='+arguments[i+1])
                else:print(tag+'=HOLD_REDACTED')
    except OSError:print('NATIVE_MAIN_MODEL_FLAGS=HOLD_PROC')

print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    connection.REMOTE=REMOTE
    ok=False
    try:ok=connection.probe()
    except Exception as exc:print('NATIVE_TOOL_AUDIT='+str(exc) if str(exc).startswith('HOLD_') else 'NATIVE_TOOL_AUDIT=HOLD')
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
