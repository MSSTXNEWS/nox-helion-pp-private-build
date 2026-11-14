"""NOX V63: inspect live response streaming architecture via syntax facts only."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
p=Path('/root/nox/scripts/agent_loop.py')
if not p.is_file():
    print('NATIVE_AGENT_LOOP_SOURCE=HOLD_MISSING')
else:
    s=p.read_text(encoding='utf-8',errors='replace')
    print('NATIVE_AGENT_LOOP_SHA256='+hashlib.sha256(s.encode('utf-8')).hexdigest())
    print('NATIVE_AGENT_LOOP_BYTES='+str(len(s.encode('utf-8'))))
    try:
        mod=ast.parse(s)
    except SyntaxError:
        print('NATIVE_AGENT_LOOP_AST=HOLD_SYNTAX')
    else:
        defs=[x for x in ast.walk(mod) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))]
        print('NATIVE_AGENT_LOOP_FUNCTION_COUNT='+str(len(defs)))
        chosen=['stream_tokens','run_tool_loop','owner_completion','stream_generate','chat','chat_stream','streaming_response','model_stream','generate']
        for fn in defs:
            if fn.name not in chosen:continue
            sub=list(ast.walk(fn))
            yield_nodes=sum(isinstance(x,(ast.Yield,ast.YieldFrom)) for x in sub)
            await_nodes=sum(isinstance(x,ast.Await) for x in sub)
            calls=[x.func.id if isinstance(x.func,ast.Name) else x.func.attr if isinstance(x.func,ast.Attribute) else '' for x in sub if isinstance(x,ast.Call)]
            names=['aiter_lines','append','join','stream','iter_lines','asyncio','sleep','create_task','gather','yield','StreamingResponse']
            found=','.join(x for x in names if x in calls)
            has_plain_return=sum(isinstance(x,ast.Return) for x in sub)
            print('NATIVE_AGENT_'+fn.name.upper()+'_ASYNC='+str(isinstance(fn,ast.AsyncFunctionDef)))
            print('NATIVE_AGENT_'+fn.name.upper()+'_YIELD_NODES='+str(yield_nodes))
            print('NATIVE_AGENT_'+fn.name.upper()+'_AWAIT_NODES='+str(await_nodes))
            print('NATIVE_AGENT_'+fn.name.upper()+'_RETURN_NODES='+str(has_plain_return))
            print('NATIVE_AGENT_'+fn.name.upper()+'_CALLS='+found)
        callers=[]
        for fn in defs:
            if any(isinstance(q,ast.Call) and
                   (isinstance(q.func,ast.Name) and q.func.id=='stream_tokens' or
                    isinstance(q.func,ast.Attribute) and q.func.attr=='stream_tokens')
                   for q in ast.walk(fn)):
                if re.fullmatch('[A-Za-z0-9_]{1,60}',fn.name):
                    callers.append(fn.name)
        print('NATIVE_AGENT_STREAM_TOKENS_CALLER_COUNT='+str(len(callers)))
        print('NATIVE_AGENT_STREAM_TOKENS_CALLERS='+','.join(sorted(set(callers))[:12]))

j=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js')
if j.is_file() and j.stat().st_size<1_000_000:
    js=j.read_text(encoding='utf-8',errors='replace')
    print('NATIVE_WEB_ORIGINAL_SHA256='+hashlib.sha256(js.encode('utf-8')).hexdigest())
    for pat,label in [('getReader','READER'),('EventSource','EVENT_SOURCE'),
                      ('response.text','RESPONSE_TEXT'),('ReadableStream','READABLE_STREAM'),
                      ('TextDecoder','TEXT_DECODER'),('requestAnimationFrame','RAF')]:
        print('NATIVE_WEB_'+label+'_COUNT='+str(js.count(pat)))
else: print('NATIVE_WEB_ORIGINAL=HOLD_NOT_FOUND')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    connection.REMOTE=REMOTE
    ok=False
    try:ok=connection.probe()
    except Exception as exc:
        print('NATIVE_STREAM_PROBE='+str(exc) if str(exc).startswith('HOLD_') else 'NATIVE_STREAM_PROBE=HOLD')
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            ok=False
            print('NATIVE_TEMP_KEY_CLEANUP=HOLD')
    raise SystemExit(0 if ok else 2)
