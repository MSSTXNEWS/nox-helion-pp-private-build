"""V104: read-only real direct-model quick-vs-thinking and native proxy option audit.

Authenticated via existing V51, no model changes, private prompts or logs.
Two bounded synthetic probes; no new servers / download / restart.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
prev=c.api
def gate(method,path,key,data=None):
    r=prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,re,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V104_SCHEMA=NOX_ONE_MODEL_THINKING_SWITCH_TIMINGS_V1')
def emit(k,val):
    print('NATIVE_V104_'+k+'='+json.dumps(val,sort_keys=True,separators=(',',':'))[:700])
def get(path,timeout=3):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081'+path,timeout=timeout) as r:
            return json.load(r)
    except Exception:return None
source=Path('/root/nox/scripts/chat_proxy.py')
if source.is_file() and source.stat().st_size<180000:
    s=source.read_text(encoding='utf8',errors='replace')
    names=('enable_thinking','chat_template_kwargs','max_tokens','n_predict','reasoning_budget',
           'stream','temperature','cache_prompt','_proxy_completion','owner_completion')
    emit('PROXY_SOURCE',{'sha256':hashlib.sha256(s.encode()).hexdigest(),
                         'references':{n:s.count(n) for n in names}})
slots=get('/slots')
if not isinstance(slots,list) or any(x.get('is_processing',x.get('processing',False)) for x in slots if isinstance(x,dict)):
    emit('RESULT',{'state':'HOLD_CHAT_BUSY_NO_SYNTHETIC_PROBES'})
    print('NATIVE_READ_ONLY_COMPLETE=true');raise SystemExit(0)
mods=get('/v1/models')
name=None
if isinstance(mods,dict):
    a=mods.get('data',[])
    if isinstance(a,list) and a and isinstance(a[0],dict):
        x=a[0].get('id')
        if isinstance(x,str) and x.endswith('/models/current.gguf'):name=x
if not name:
    emit('RESULT',{'state':'HOLD_ONE_NOX_MODEL_UNVERIFIED'})
    print('NATIVE_READ_ONLY_COMPLETE=true');raise SystemExit(0)
def do(label,extra):
    if not isinstance(get('/slots'),list):return {'state':'HOLD_SLOTS'}
    request={'model':name,'stream':True,'max_tokens':64,'temperature':0,
      'messages':[{'role':'user','content':'Ответь одним словом: готово.'}]}
    request.update(extra)
    req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
      data=json.dumps(request,ensure_ascii=False).encode('utf-8'),
      headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    start=time.monotonic();first_content=None;finish=None;done=False;content_chunks=0;reasoning_chunks=0
    try:
        with urllib.request.urlopen(req,timeout=12) as r:
            if r.status!=200:return {'state':'HOLD_HTTP'}
            for raw in r:
                if time.monotonic()-start>15:break
                if len(raw)>16000:continue
                t=raw.decode('utf8','replace').strip()
                if not t.startswith('data:'):continue
                payload=t[5:].strip()
                if payload=='[DONE]':done=True;break
                try:v=json.loads(payload)
                except ValueError:continue
                for c in (v.get('choices') or []):
                    if not isinstance(c,dict):continue
                    delta=c.get('delta') or {}
                    if isinstance(delta,dict) and isinstance(delta.get('content'),str) and delta['content']:
                        content_chunks+=1
                        if first_content is None:first_content=time.monotonic()
                    if isinstance(delta,dict) and delta.get('reasoning_content'):
                        reasoning_chunks+=1
                    if c.get('finish_reason'):finish=c['finish_reason']
        return {'label':label,'state':'COMPLETED' if done else 'HOLD_INCOMPLETE',
           'ttft_ms':round((first_content-start)*1000,1) if first_content else None,
           'total_ms':round((time.monotonic()-start)*1000,1),
           'content_chunks':content_chunks,'reasoning_chunks':reasoning_chunks,
           'finish_reason':str(finish)[:20] if finish else None,
           'stream_done':done,'user_content_exported':False}
    except urllib.error.HTTPError as e:return {'label':label,'state':'HOLD_HTTP_'+str(e.code)}
    except Exception as e:return {'label':label,'state':'HOLD_'+type(e).__name__}
results=[]
for label,extra in [('default',{}),
                    ('no_thinking',{'chat_template_kwargs':{'enable_thinking':False}})]:
    slots=get('/slots')
    if not isinstance(slots,list) or any(x.get('is_processing',x.get('processing',False)) for x in slots if isinstance(x,dict)):
        results.append({'label':label,'state':'HOLD_CHAT_BECAME_BUSY'});break
    x=do(label,extra);results.append(x);emit('CASE',x)
emit('RESULT',{'state':'READ_ONLY_MODEL_PROBES_COMPLETE','cases':len(results),
   'completed':sum(x.get('state')=='COMPLETED' for x in results),
   'no_model_config_changed':True})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
    c.REMOTE=REMOTE;c.api=gate;buf=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buf):ok=c.probe()
    except Exception as e:
        v=str(e);print('NOX_V104_HOLD='+v if v.startswith('HOLD_') and len(v)<90 else 'NOX_V104_HOLD=NATIVE')
    finally:
        try:
            with contextlib.redirect_stdout(buf):
                if not c.cleanup():ok=False
        except Exception:ok=False
    rows=[x for x in buf.getvalue().splitlines() if x.startswith(('NATIVE_V104_','TEMP_SSH_CLEANUP='))]
    for x in rows:print(x[:790])
    accepted=ok and any(x.startswith('NATIVE_V104_RESULT=') for x in rows)
    print('NOX_V104_TIMINGS_VERIFIED='+str(bool(accepted)).lower())
    raise SystemExit(0 if accepted else 2)
