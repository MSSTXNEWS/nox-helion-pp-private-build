"""NOX V63: bounded live chat-latency diagnosis using existing V51 secure SSH.

Exactly one current student / llama-server, no teacher requests, no process
management, no secret or user-chat export. Temporary SSH key detached via V51.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,time,statistics,urllib.request,urllib.error,subprocess,re,sys,hashlib
from collections import Counter
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NOX_V63_DIAGNOSTIC_SCHEMA=NOX_MAIN_CHAT_LATENCY_V1')

def health(port,path='/health',timeout=2.5):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=timeout) as response:
            body=response.read(8000)
            return response.status,body
    except urllib.error.HTTPError as ex:return ex.code,b''
    except (TimeoutError,OSError):return None,b''

for port in (8080,8081,8082,8084,8087,8088,8092,8093,8095):
    status,_=health(port)
    print(f'NOX_HTTP_{port}_HEALTH='+str(status if status is not None else 'HOLD'))

try:
    with urllib.request.urlopen('http://127.0.0.1:8081/v1/models',timeout=3) as r:
        models=json.load(r).get('data',[])
    model=models[0].get('id') if models else None
    if not isinstance(model,str) or not model.endswith('/models/current.gguf'):
        raise RuntimeError('HOLD_WRONG_STUDENT')
    print('NOX_MAIN_STUDENT_VERIFIED=true')
except Exception:
    raise SystemExit('HOLD_MODEL_NOT_VERIFIED')

def snapshots():
    try:
        r=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free,temperature.gpu','--format=csv,noheader,nounits'],
             capture_output=True,text=True,timeout=7)
        if r.returncode==0:
            for line in r.stdout.splitlines()[:2]:
                if re.fullmatch(r'[0-9 ,]+',line):
                    print('NOX_GPU='+line.replace(' ',''))
    except (OSError,subprocess.TimeoutExpired):pass
snapshots()

try:
    status,body=health(8081,'/slots')
    if status==200:
        slots=json.loads(body)
        if isinstance(slots,list):
            total=len(slots)
            processing=sum(bool(slot.get('is_processing')) for slot in slots if isinstance(slot,dict))
            print('NOX_LLAMA_SLOTS='+str(total))
            print('NOX_LLAMA_SLOTS_PROCESSING='+str(processing))
        else:print('NOX_LLAMA_SLOTS=HOLD_SCHEMA')
    else:print('NOX_LLAMA_SLOTS=HOLD_HTTP_'+str(status))
except Exception:print('NOX_LLAMA_SLOTS=HOLD')

try:
    r=subprocess.run(['ps','-eo','comm='],capture_output=True,text=True,timeout=6)
    names=r.stdout.lower().splitlines()
    for term in ('llama','python','supervis','torchrun'):
        print('NOX_PROCESS_'+term.upper()+'_COUNT='+str(sum(term in name for name in names)))
except (OSError,subprocess.TimeoutExpired):pass

cases=[('short_ru','Ответь одним словом: готово.',24),
       ('short_math','Сколько будет 17 плюс 25? Ответь только числом.',32),
       ('medium_ru','Дай три коротких совета по безопасной работе с компьютером.',96),
       ('short_es','Responde solo con una palabra: listo.',24)]
out=[]
for tag,prompt,max_tokens in cases:
    payload={'model':model,'messages':[{'role':'user','content':prompt}],
            'temperature':0,'stream':True,'max_tokens':max_tokens}
    req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
        data=json.dumps(payload,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    start=time.perf_counter();first=None;tokens=0;done=False;chunks=0
    try:
        with urllib.request.urlopen(req,timeout=45) as response:
            if response.status!=200:raise RuntimeError('HOLD_STREAM_HTTP')
            for raw in response:
                if len(raw)>12000:continue
                line=raw.decode('utf-8','replace').strip()
                if not line.startswith('data:'):continue
                b=line[5:].strip()
                if b=='[DONE]':
                    done=True;break
                try:d=json.loads(b)
                except (ValueError,UnicodeError):continue
                if isinstance(d,dict):
                    choices=d.get('choices') or []
                    if isinstance(choices,list) and choices and isinstance(choices[0],dict):
                        delta=choices[0].get('delta') or {}
                        if isinstance(delta,dict):
                            text=delta.get('content') or ''
                            if isinstance(text,str) and text:
                                chunks+=1
                                if first is None:first=time.perf_counter()
                    use=d.get('usage') or {}
                    if isinstance(use,dict) and isinstance(use.get('completion_tokens'),int):
                        tokens=use['completion_tokens']
        elapsed=(time.perf_counter()-start)*1000
        if first is None:raise RuntimeError('HOLD_NO_CONTENT')
        ttft=(first-start)*1000
        out.append((tag,round(ttft,1),round(elapsed,1),chunks,tokens,done))
        print('NOX_CASE='+tag+',TTFT_MS='+str(round(ttft,1))+',E2E_MS='+str(round(elapsed,1))+',CHUNKS='+str(chunks)+',USAGE_TOKENS='+str(tokens or 'UNKNOWN')+',DONE='+str(done))
    except Exception:
        print('NOX_CASE='+tag+',RESULT=HOLD_TIMEOUT_OR_STREAM')
        continue

if len(out)>=3:
    ttft=sorted(x[1] for x in out)
    e2e=sorted(x[2] for x in out)
    print('NOX_SAMPLE_TTFT_P50_MS='+str(round(statistics.median(ttft),1)))
    print('NOX_SAMPLE_TTFT_P95_NEAREST_MS='+str(ttft[-1]))
    print('NOX_SAMPLE_E2E_P50_MS='+str(round(statistics.median(e2e),1)))
    print('NOX_SAMPLE_E2E_P95_NEAREST_MS='+str(e2e[-1]))
    print('NOX_LATENCY_SAMPLE_COUNT='+str(len(out)))
    print('NOX_LATENCY_SCOPE=DIRECT_MODEL_SYNTHETIC_NOT_FULL_UI_S03')
    print('NOX_READ_ONLY_COMPLETE=true')
else:
    print('NOX_LATENCY_RESULT=HOLD_INSUFFICIENT_SAMPLES')
    print('NOX_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__ == "__main__":
    connection.REMOTE = REMOTE
    ok = False
    try:
        ok = connection.probe()
    except Exception as exc:
        reason = str(exc)
        print("NOX_V63_STATE="+reason if reason.startswith("HOLD_") else
              "NOX_V63_STATE=HOLD_NATIVE_PROBE")
    finally:
        try:
            if not connection.cleanup():
                ok = False
                print("NOX_V63_KEY_CLEANUP=HOLD")
        except Exception:
            ok = False
            print("NOX_V63_KEY_CLEANUP=HOLD_EXCEPTION")
    raise SystemExit(0 if ok else 2)
