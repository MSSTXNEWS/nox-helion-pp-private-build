"""NOX V56: one bounded live main-model streaming smoke + read-only API map.

Only the observed existing 8081 current.gguf llama-server is tested.
No chat history or private prompts are read; no model/scheduler changes.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,re,time,urllib.request,urllib.error
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V56_MAIN_MODEL_STREAM_SMOKE_V1')
for port in (8080,8095,11111,11112):
    try:
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/openapi.json',
            headers={'Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=2.5) as response:
            status=response.status
            body=response.read(50000)
        x=json.loads(body)
        paths=x.get('paths',{}) if isinstance(x,dict) else {}
        if not isinstance(paths,dict):paths={}
        print('NATIVE_API_'+str(port)+'_OPENAPI_STATUS='+str(status))
        print('NATIVE_API_'+str(port)+'_ROUTE_COUNT='+str(len(paths)))
        categories={x:0 for x in ('health','chat','admin','queue','memory','models','tools')}
        for path in paths:
            for cat in categories:
                if cat in str(path).lower():categories[cat]+=1
        print('NATIVE_API_'+str(port)+'_ROUTE_CATEGORIES='+json.dumps(categories,separators=(',',':')))
    except (OSError,ValueError,urllib.error.HTTPError,TimeoutError):
        print('NATIVE_API_'+str(port)+'_OPENAPI_STATUS=HOLD')
base='http://127.0.0.1:8081'
try:
    req=urllib.request.Request(base+'/v1/models',headers={'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=4) as response:
        obj=json.loads(response.read(12000))
    entries=obj.get('data') if isinstance(obj,dict) else None
    if not isinstance(entries,list) or not entries:
        raise RuntimeError('HOLD_MAIN_MODEL_NOT_LISTED')
    model=entries[0].get('id')
    if not isinstance(model,str) or not model.endswith('/models/current.gguf'):
        raise RuntimeError('HOLD_UNEXPECTED_MAIN_MODEL')
    print('NATIVE_MAIN_MODEL_IDENTIFIED=true')
except Exception:
    raise SystemExit('HOLD_NO_VERIFIED_MAIN_MODEL_8081')
payload={
    'model':model,'messages':[{'role':'user','content':'Ответь одним словом: готово.'}],
    'temperature':0,'max_tokens':16,'stream':True,
}
req=urllib.request.Request(base+'/v1/chat/completions',
    data=json.dumps(payload,ensure_ascii=False).encode(),
    headers={'Content-Type':'application/json','Accept':'text/event-stream'},
    method='POST')
start=time.perf_counter()
first=None
chunks=0
usage_tokens=None
try:
    with urllib.request.urlopen(req,timeout=40) as response:
        print('NATIVE_MAIN_STREAM_HTTP_STATUS='+str(response.status))
        if response.status!=200:raise RuntimeError('HOLD_STREAM_HTTP')
        for raw in response:
            if len(raw)>12000:continue
            line=raw.decode('utf-8','replace').strip()
            if not line.startswith('data:'):continue
            body=line[5:].strip()
            if body=='[DONE]':break
            try:ev=json.loads(body)
            except ValueError:continue
            if isinstance(ev,dict):
                use=ev.get('usage')
                if isinstance(use,dict) and isinstance(use.get('completion_tokens'),int):
                    usage_tokens=use['completion_tokens']
                choices=ev.get('choices') or []
                if isinstance(choices,list) and choices and isinstance(choices[0],dict):
                    delta=choices[0].get('delta') or {}
                    if isinstance(delta,dict) and delta.get('content'):
                        chunks+=1
                        if first is None:first=time.perf_counter()
    end=time.perf_counter()
    if first is None:raise RuntimeError('HOLD_STREAM_NO_TEXT')
    print('NATIVE_MAIN_STREAM_FIRST_CONTENT_MS='+str(round((first-start)*1000,2)))
    print('NATIVE_MAIN_STREAM_END_TO_END_MS='+str(round((end-start)*1000,2)))
    print('NATIVE_MAIN_STREAM_CHUNKS='+str(chunks))
    print('NATIVE_MAIN_STREAM_TOKENS='+str(usage_tokens if usage_tokens is not None else 'UNKNOWN'))
    print('NATIVE_MAIN_STREAM_RESULT=PASS_ONE_PROMPT')
except Exception as exc:
    print('NATIVE_MAIN_STREAM_RESULT='+str(exc) if str(exc).startswith('HOLD_') else 'NATIVE_MAIN_STREAM_RESULT=HOLD_INFERENCE')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print('NOX_V56_AUDIT='+str(exc) if str(exc).startswith('HOLD_') else 'NOX_V56_AUDIT=HOLD')
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print('NOX_V56_SSH_CLEANUP=HOLD')
            ok=False
    raise SystemExit(0 if ok else 2)
