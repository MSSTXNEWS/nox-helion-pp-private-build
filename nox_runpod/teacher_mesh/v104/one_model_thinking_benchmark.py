"""V104: read-only real direct-model quick-vs-thinking and native proxy option audit.

Authenticated via existing V51, no model changes, private prompts or logs.
Two bounded synthetic probes; no new servers / download / restart.
Fail-closed SSE transport integrity: malformed/oversized/invalid UTF-8 frames are HOLD, not discarded.
"""
from __future__ import annotations
import contextlib,io,json,time,math
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
prev=c.api
def native_timing_evidence(rows):
    """Require two genuine completed native streams, never just an SSH banner."""
    cases = {}
    summary = None
    for row in rows:
        if row.startswith('NATIVE_V104_CASE='):
            try:
                item = json.loads(row.split('=', 1)[1])
            except (TypeError, ValueError):
                return False
            if not isinstance(item, dict) or item.get('label') not in ('default', 'no_thinking'):
                return False
            if item['label'] in cases:
                return False
            cases[item['label']] = item
        elif row.startswith('NATIVE_V104_RESULT='):
            if summary is not None:
                return False
            try:
                summary = json.loads(row.split('=', 1)[1])
            except (TypeError, ValueError):
                return False
    if not isinstance(summary, dict) or set(cases) != {'default', 'no_thinking'}:
        return False
    if (summary.get('state') != 'READ_ONLY_MODEL_PROBES_COMPLETE'
            or summary.get('cases') != 2 or summary.get('completed') != 2
            or summary.get('no_model_config_changed') is not True):
        return False
    for case in cases.values():
        value = case.get('ttft_ms')
        if (case.get('state') != 'COMPLETED'
                or case.get('stream_done') is not True
                or type(value) not in (int, float) or not 0 <= value <= 30000
                or type(case.get('content_chunks')) is not int
                or case['content_chunks'] <= 0):
            return False
        if case.get('finish_reason') not in ('stop','eos_token'):
            return False
        rate = case.get('decode_tokens_per_sec')
        if rate is not None:
            if (type(rate) not in (int,float) or not math.isfinite(rate)
                    or not 0 < rate < 5000
                    or case.get('usage_source') != 'NATIVE_STREAM_USAGE'
                    or type(case.get('completion_tokens')) is not int
                    or case['completion_tokens'] < 2
                    or case.get('reasoning_chunks') != 0):
                return False
        if case.get('usage_negotiation') == 'HTTP_400_FALLBACK_NO_USAGE':
            if rate is not None or case.get('usage_source') != 'UNSUPPORTED_FALLBACK_NO_USAGE':
                return False
    return True

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
# No inference probes if a native STOP is present or the slot state is
# empty, ambiguous, mixed, active, or not explicitly boolean idle.
# This is NOT an exclusive native owner lease, only a fail-closed probe gate.
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/root/nox/program/STOP','/workspace/NOX_STOP')
def idle_slots():
    if any(Path(p).exists() or Path(p).is_symlink() for p in STOP_PATHS):
        return False
    items=get('/slots')
    if not isinstance(items,list) or not items:return False
    for item in items:
        if not isinstance(item,dict):return False
        a=item.get('is_processing')
        b=item.get('processing')
        if any(x is not None and type(x) is not bool for x in (a,b)):return False
        if a is True or b is True:return False
        if a is not False and b is not False:return False
    return True
if not idle_slots():
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
def do(label,extra,include_usage=True):
    if not idle_slots():return {'label':label,'state':'HOLD_BUSY_STOP_OR_UNTRUSTED_SLOTS'}
    request={'model':name,'stream':True,'max_tokens':64,'temperature':0,
      'messages':[{'role':'user','content':'Ответь одним словом: готово.'}]}
    # Some existing OpenAI-compatible runtimes reject include_usage with HTTP 400.
    # Negotiate once; no persistent service/model changes.
    if include_usage:request['stream_options']={'include_usage':True}
    request.update(extra)
    req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
      data=json.dumps(request,ensure_ascii=False).encode('utf-8'),
      headers={'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    start=time.monotonic();first_content=None;last_content=None;finish=None;done=False;content_chunks=0;reasoning_chunks=0;completion_tokens=None
    try:
        with urllib.request.urlopen(req,timeout=12) as r:
            if r.status!=200:return {'state':'HOLD_HTTP'}
            for raw in r:
                if time.monotonic()-start>15:break
                if len(raw)>16000:return {'label':label,'state':'HOLD_SSE_OVERSIZE'}
                try:t=raw.decode('utf8','strict').strip()
                except UnicodeDecodeError:return {'label':label,'state':'HOLD_SSE_UTF8_INVALID'}
                if not t.startswith('data:'):continue
                payload=t[5:].strip()
                if payload=='[DONE]':done=True;break
                try:v=json.loads(payload)
                except ValueError:return {'label':label,'state':'HOLD_SSE_JSON_INVALID'}
                if not isinstance(v,dict):return {'label':label,'state':'HOLD_SSE_NONOBJECT'}
                # Error frames are not successful generation, even if
                # a later finish_reason and [DONE] arrive.
                if v.get('error') is not None:
                    return {'label':label,'state':'HOLD_SSE_REMOTE_ERROR'}
                choices=v.get('choices',[])
                if not isinstance(choices,list):
                    return {'label':label,'state':'HOLD_SSE_CHOICES_SCHEMA'}
                usage=v.get('usage')
                if isinstance(usage,dict):
                    count=usage.get('completion_tokens')
                    if type(count) is int and 0<count<=8192:completion_tokens=count
                for c in choices:
                    if not isinstance(c,dict):
                        return {'label':label,'state':'HOLD_SSE_CHOICES_SCHEMA'}
                    delta=c.get('delta')
                    if delta is None:delta={}
                    if not isinstance(delta,dict):
                        return {'label':label,'state':'HOLD_SSE_DELTA_SCHEMA'}
                    if isinstance(delta,dict) and isinstance(delta.get('content'),str) and delta['content']:
                        content_chunks+=1
                        last_content=time.monotonic()
                        if first_content is None:first_content=last_content
                    if isinstance(delta,dict) and delta.get('reasoning_content'):
                        reasoning_chunks+=1
                    if c.get('finish_reason'):finish=c['finish_reason']
        return {'label':label,'state':'COMPLETED' if done and first_content is not None and finish in ('stop','eos_token') else 'HOLD_INCOMPLETE',
           'ttft_ms':round((first_content-start)*1000,1) if first_content else None,
           'total_ms':round((time.monotonic()-start)*1000,1),
           'content_chunks':content_chunks,'reasoning_chunks':reasoning_chunks,
           'decode_tokens_per_sec':round((completion_tokens-1)/(last_content-first_content),2) if completion_tokens and completion_tokens>1 and reasoning_chunks==0 and last_content and first_content and last_content>first_content else None,
           'finish_reason':str(finish)[:20] if finish else None,
           'stream_done':done,'usage_source':'NATIVE_STREAM_USAGE' if completion_tokens is not None else ('HOLD_NO_STREAM_USAGE' if include_usage else 'UNSUPPORTED_FALLBACK_NO_USAGE'),
           'completion_tokens':completion_tokens,'user_content_exported':False}
    except urllib.error.HTTPError as e:return {'label':label,'state':'HOLD_HTTP_'+str(e.code)}
    except Exception as e:return {'label':label,'state':'HOLD_'+type(e).__name__}
results=[]
for label,extra in [('default',{}),
                    ('no_thinking',{'chat_template_kwargs':{'enable_thinking':False}})]:
    if not idle_slots():
        results.append({'label':label,'state':'HOLD_CHAT_BECAME_BUSY_STOP_OR_UNTRUSTED_SLOTS'});break
    x=do(label,extra)
    if x.get('state')=='HOLD_HTTP_400':
        # The first request was rejected before streaming. Only one retry,
        # only if the original OneHost model is currently idle. Preserve
        # real TTFT in engines that do not support stream_options.
        if not idle_slots():
            x={'label':label,'state':'HOLD_CHAT_BUSY_BEFORE_FALLBACK'}
        else:
            x=do(label,extra,include_usage=False)
            x['usage_negotiation']='HTTP_400_FALLBACK_NO_USAGE'
    results.append(x);emit('CASE',x)
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
    accepted=ok and native_timing_evidence(rows)
    print('NOX_V104_TIMINGS_VERIFIED='+str(bool(accepted)).lower())
    raise SystemExit(0 if accepted else 2)
