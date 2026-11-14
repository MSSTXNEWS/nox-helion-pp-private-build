"""NOX E2 urgent single-pass native chat diagnosis; no writes, restarts, or user messages."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time

# V51 attach may precede sshd authorized_keys propagation: add bounded wait
# for this one probe, without modifying the shared OneHost implementation.
_api=c.api
def _api_ready(method,path,key,data=None):
    r=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(13)
    return r

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,time,urllib.request,urllib.error,subprocess,re,os
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_E2_URGENT_CHAT_READONLY_V1')

def get(port, path, timeout=2):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=timeout) as r:
            return r.status,r.read(180000)
    except urllib.error.HTTPError as e:
        return e.code,b''
    except (OSError,TimeoutError):
        return 0,b''
for p in (8080,8081,8082,8095):
    status,_=get(p,'/health')
    print('NATIVE_CHAT_PORT_'+str(p)+'_HEALTH='+str(status))

status,raw=get(8081,'/slots',3)
print('NATIVE_CHAT_SLOTS_HTTP='+str(status))
active=None
if status==200:
    try:
        slots=json.loads(raw)
        if isinstance(slots,list):
            active=sum(bool(s.get('is_processing')) for s in slots if isinstance(s,dict))
            print('NATIVE_CHAT_SLOTS_COUNT='+str(len(slots)))
            print('NATIVE_CHAT_SLOTS_ACTIVE='+str(active))
            states={}
            for s in slots:
                if isinstance(s,dict):
                    state=str(s.get('state','UNKNOWN'))[:24]
                    if re.fullmatch(r'[A-Za-z0-9_-]+',state):
                        states[state]=states.get(state,0)+1
            print('NATIVE_CHAT_SLOT_STATES='+json.dumps(states,separators=(',',':')))
    except (TypeError,ValueError):
        print('NATIVE_CHAT_SLOTS=HOLD_PARSE')

try:
    ps=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if ps.returncode==0:
        for l in ps.stdout.splitlines()[:2]:
            if re.fullmatch(r'[0-9 ,]+',l):
                print('NATIVE_CHAT_GPU='+l.replace(' ',''))
except (OSError,subprocess.TimeoutExpired):
    print('NATIVE_CHAT_GPU=HOLD')

try:
    stat=os.statvfs('/workspace')
    print('NATIVE_CHAT_DISK_FREE_BYTES='+str(stat.f_frsize*stat.f_bavail))
except OSError:
    print('NATIVE_CHAT_DISK_FREE_BYTES=HOLD')

# Never dump process arguments, environment, logs or chat history.
try:
    process=subprocess.run(['ps','-eo','comm='],capture_output=True,text=True,timeout=6)
    text=process.stdout.lower().splitlines()
    for term in ('llama','python','torchrun'):
        print('NATIVE_CHAT_PROCESS_'+term.upper()+'='+str(sum(term in c for c in text)))
except (OSError,subprocess.TimeoutExpired):
    print('NATIVE_CHAT_PROCESS_INVENTORY=HOLD')

status,raw=get(8081,'/v1/models',3)
model=None
if status==200:
    try:
        models=json.loads(raw).get('data',[])
        if models and isinstance(models[0],dict):
            value=models[0].get('id')
            if isinstance(value,str) and value.endswith('/models/current.gguf'):
                model=value
    except (ValueError,TypeError,KeyError):pass
print('NATIVE_CHAT_MAIN_MODEL_HEALTH='+('PASS' if model else 'HOLD'))

# Run one synthetic, tiny direct test only when no active slots. Distinguishes
# model stall from the agent frontend without evicting a live user conversation.
if model and active==0:
    payload={'model':model,'messages':[{'role':'user','content':'Ответь одним словом: готово.'}],
             'temperature':0,'max_tokens':16,'stream':True}
    req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    start=time.monotonic()
    first=None
    done=False
    try:
        with urllib.request.urlopen(req,timeout=13) as response:
            print('NATIVE_CHAT_SYNTHETIC_STATUS='+str(response.status))
            for raw in response:
                if time.monotonic()-start>20:break
                if len(raw)>20000:continue
                line=raw.decode('utf-8','replace').strip()
                if not line.startswith('data:'):continue
                value=line[5:].strip()
                if value=='[DONE]':
                    done=True;break
                try:ev=json.loads(value)
                except ValueError:continue
                for choice in (ev.get('choices') or []):
                    delta=choice.get('delta') if isinstance(choice,dict) else None
                    if isinstance(delta,dict) and delta.get('content') and first is None:
                        first=time.monotonic()
        if first is None:
            print('NATIVE_CHAT_SYNTHETIC_RESULT=HOLD_NO_TEXT')
        else:
            print('NATIVE_CHAT_SYNTHETIC_TTFT_MS='+str(round((first-start)*1000,1)))
            print('NATIVE_CHAT_SYNTHETIC_E2E_MS='+str(round((time.monotonic()-start)*1000,1)))
            print('NATIVE_CHAT_SYNTHETIC_DONE='+str(done).lower())
    except Exception:
        print('NATIVE_CHAT_SYNTHETIC_RESULT=HOLD_TIMEOUT_OR_RESPONSE')
else:
    print('NATIVE_CHAT_SYNTHETIC_RESULT=SKIPPED_BUSY_OR_UNVERIFIED')
print('NATIVE_CHAT_SOURCE_MODIFIED=false')
print('NATIVE_CHAT_SERVICE_RESTARTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__=="__main__":
    c.REMOTE=REMOTE
    c.api=_api_ready
    ok=False
    try:
        ok=c.probe()
    except Exception as exc:
        msg=str(exc)
        print("NOX_E2_CHAT_PROBE="+msg if msg.startswith("HOLD_") and len(msg)<92 else "NOX_E2_CHAT_PROBE=HOLD_NATIVE")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print("NOX_E2_CHAT_PROBE=HOLD_SSH_KEY_REVOKE")
            ok=False
    raise SystemExit(0 if ok else 2)
