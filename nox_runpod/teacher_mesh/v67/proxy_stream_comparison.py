"""NOX V67: compare direct llama-server and native proxy first-byte behavior."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time
base=connection.api
def gate(method,path,key,data=None):
    r=base(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,time,urllib.request,urllib.error
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V67_PROXY_VS_MAIN_LATENCY_V1')
payload={'messages':[{'role':'user','content':'Ответь одним словом: да.'}],
         'max_tokens':16,'temperature':0,'stream':True}
for label,base in [('model','http://127.0.0.1:8081/v1/chat/completions'),
                   ('proxy','http://127.0.0.1:8080/v1/chat/completions')]:
    req=urllib.request.Request(base,data=json.dumps(payload,ensure_ascii=False).encode(),
         headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    start=time.monotonic();first=None;end=None;status=0;chunks=0;done=False;ctype=''
    try:
        with urllib.request.urlopen(req,timeout=16) as rsp:
            status=rsp.status
            ctype=rsp.headers.get('Content-Type','').split(';')[0][:60]
            for raw in rsp:
                if time.monotonic()-start>18:break
                if len(raw)>12000:continue
                line=raw.decode('utf-8','replace').strip()
                if line.startswith('data:'):
                    value=line[5:].strip()
                    if value=='[DONE]':
                        done=True;break
                    try:entry=json.loads(value)
                    except ValueError:continue
                    for item in (entry.get('choices') or []):
                        if not isinstance(item,dict):continue
                        delta=item.get('delta') or {}
                        if isinstance(delta,dict) and delta.get('content'):
                            chunks+=1
                            if first is None:first=time.monotonic()
                elif first is None and ctype!='text/event-stream' and line:
                    first=time.monotonic()
        end=time.monotonic()
        print('NATIVE_COMPARE_'+label.upper()+'_STATUS='+str(status))
        print('NATIVE_COMPARE_'+label.upper()+'_CONTENT_TYPE='+ctype.replace('/','_'))
        print('NATIVE_COMPARE_'+label.upper()+'_FIRST_MS='+str(round((first-start)*1000,1)) if first else 'NATIVE_COMPARE_'+label.upper()+'_FIRST=NONE')
        print('NATIVE_COMPARE_'+label.upper()+'_E2E_MS='+str(round((end-start)*1000,1)))
        print('NATIVE_COMPARE_'+label.upper()+'_CHUNKS='+str(chunks))
        print('NATIVE_COMPARE_'+label.upper()+'_DONE='+str(done).lower())
    except urllib.error.HTTPError as e:
        print('NATIVE_COMPARE_'+label.upper()+'_HTTP_ERROR='+str(e.code))
    except Exception as e:
        print('NATIVE_COMPARE_'+label.upper()+'_RESULT=HOLD_'+type(e).__name__)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
    connection.REMOTE=REMOTE;connection.api=gate;ok=False
    try:ok=connection.probe()
    except Exception as e:
        v=str(e);print("NOX_E2_COMPARISON="+v if v.startswith("HOLD_") and len(v)<100 else "NOX_E2_COMPARISON=HOLD")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:ok=False
    raise SystemExit(0 if ok else 2)
