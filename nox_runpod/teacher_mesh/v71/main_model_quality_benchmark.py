"""Read-only live NOX main GGUF quality and latency baseline (3 public synthetic prompts).

This DOES NOT score overall intelligence, prove distillation, or modify weights.
Only use the installed 8081 /models/current.gguf llama-server, never teachers.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_original=ssh.api
def _delay(method,path,key,data=None):
    result=_original(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,time,urllib.request,urllib.error,re,statistics
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V71_MAIN_MODEL_SYNTHETIC_BENCH_V1')
base='http://127.0.0.1:8081'
try:
    req=urllib.request.Request(base+'/v1/models',headers={'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r: catalog=json.loads(r.read(20000))
    models=catalog.get('data',[]) if isinstance(catalog,dict) else []
    model=models[0]['id']
    if not isinstance(model,str) or not model.endswith('/models/current.gguf'):
        raise ValueError('unverified_model')
except Exception:
    raise SystemExit('HOLD_MAIN_MODEL_ID_UNVERIFIED')
cases=[
 ('ru_arithmetic','Ответь только числом: сколько будет 17 + 25?', '42'),
 ('es_arithmetic','Responde solo con un numero: cuanto es 9 por 7?', '63'),
 ('ru_logic','Ответь одним числом: если у тебя 3 яблока и тебе дали еще 4, сколько яблок?', '7')
]
results=[]
for label,prompt,expected in cases:
    payload={'model':model,'messages':[{'role':'user','content':prompt}],
             'temperature':0,'max_tokens':64,'stream':True}
    req=urllib.request.Request(base+'/v1/chat/completions',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    started=time.monotonic();first=None;answer=[];done=False
    try:
        with urllib.request.urlopen(req,timeout=40) as resp:
            if resp.status!=200:raise ValueError('http')
            for chunk in resp:
                if len(chunk)>16000:continue
                line=chunk.decode('utf-8','replace').strip()
                if not line.startswith('data:'):continue
                raw=line[5:].strip()
                if raw=='[DONE]':done=True;break
                try:event=json.loads(raw)
                except ValueError:continue
                choices=event.get('choices',[]) if isinstance(event,dict) else []
                if choices and isinstance(choices[0],dict):
                    part=(choices[0].get('delta') or {}).get('content')
                    if isinstance(part,str) and part:
                        if first is None:first=time.monotonic()
                        answer.append(part[:1000])
        elapsed=(time.monotonic()-started)*1000
        text=''.join(answer).strip()
        # Only a deliberately strict score on three simple prompts.
        exact=bool(done and re.fullmatch(r'[^0-9]*'+expected+r'[^0-9]*',text))
        result={'test':label,'stream_done':done,'response_nonempty':bool(text),
                'exact_expected':exact,'first_ms':round((first-started)*1000) if first else None,
                'total_ms':round(elapsed),'chars':len(text)}
    except Exception:
        result={'test':label,'state':'HOLD_REQUEST_ERROR','exact_expected':False}
    results.append(result)
    print('NATIVE_BENCH_CASE='+json.dumps(result,separators=(',',':')))
valid=[x for x in results if x.get('stream_done')]
print('NATIVE_BENCH_SUMMARY='+json.dumps({
    'cases':len(results),'stream_completed':len(valid),
    'basic_exact_correct':sum(x.get('exact_expected') is True for x in results),
    'ttft_median_ms':statistics.median([x['first_ms'] for x in valid if x.get('first_ms') is not None]) if valid else None,
    'overall_intelligence_verified':False,'weights_changed':False,
    's03_connected_to_main_chat_verified':False,
    'teacher_fusion_verified':False,'user_chat_route_tested':False
},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    ssh.REMOTE=REMOTE;ssh.api=_delay;okay=False
    try:okay=ssh.probe()
    except Exception as exc:
        error=str(exc)
        print('NOX_V71='+error if error.startswith('HOLD_') else 'NOX_V71=HOLD_REMOTE')
    finally:
        try:
            if not ssh.cleanup():okay=False
        except Exception:okay=False
    raise SystemExit(0 if okay else 2)
