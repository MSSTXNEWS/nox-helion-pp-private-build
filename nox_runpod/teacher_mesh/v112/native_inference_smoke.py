"""One bounded real inference smoke of existing GPU0 NOX model via native loopback.

Does not authorize a web session or test browser cookie flow. Does not write S03,
change model, alter system prompt, load extra model, or start a service.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

ORIGINAL_API=ssh.api


def settled_api(method,path,key,data=None):
    result=ORIGINAL_API(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return result


REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json
import time
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V112_SCHEMA=NOX_SINGLE_EXISTING_GPU0_TOKEN_TEST_V1')
stops=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')

def emit(status,**details):
    output={'state':status,'one_test_only':True,'s03_modified':False,
            'model_loaded_by_test':False,'weights_modified':False,
            'browser_auth_tested':False,**details}
    print('NATIVE_V112_RESULT='+json.dumps(output,sort_keys=True,separators=(',',':'))[:770])

def stopped():
    return any(Path(x).exists() for x in stops)

def check_idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            slots=json.loads(r.read(60000))
        return (isinstance(slots,list) and len(slots)==6 and all(
            isinstance(x,dict) and (x.get('is_processing') if 'is_processing' in x
                                    else x.get('processing')) is False for x in slots))
    except Exception:
        return False

def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=3) as r:
            return r.status==200
    except Exception:
        return False

try:
    if stopped():raise RuntimeError('HOLD_STOP')
    if not health() or not check_idle():raise RuntimeError('HOLD_MODEL_BUSY_OR_HEALTH')
    with urllib.request.urlopen('http://127.0.0.1:8081/v1/models',timeout=3) as r:
        data=json.loads(r.read(20000))
    models=data.get('data') if isinstance(data,dict) else None
    if not isinstance(models,list) or len(models)!=1 or not isinstance(models[0],dict):
        raise RuntimeError('HOLD_MODEL_AMBIGUITY')
    model=models[0].get('id')
    if not isinstance(model,str) or not 1<=len(model)<=260:
        raise RuntimeError('HOLD_MODEL_IDENTIFIER')
    if any(x in model.lower() for x in ('bge-','embed','guard','moderation','rerank')):
        raise RuntimeError('HOLD_NOT_GENERATIVE_MODEL')
    payload={'model':model,'stream':True,
             'messages':[{'role':'user','content':'Сколько будет 2+2? Ответь одной цифрой.'}],
             'temperature':0,'max_tokens':16}
    if stopped() or not check_idle():
        raise RuntimeError('HOLD_CHAT_BECAME_BUSY')
    start=time.monotonic()
    request=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
             data=json.dumps(payload,ensure_ascii=False).encode('utf8'),
             method='POST',headers={'Content-Type':'application/json'})
    first=None
    text=''
    frame_count=0
    complete=False
    with urllib.request.urlopen(request,timeout=20) as response:
        if response.status!=200:raise RuntimeError('HOLD_RESPONSE_HTTP')
        while frame_count < 120 and time.monotonic()-start < 24:
            raw=response.readline(20000)
            if not raw:break
            if not raw.startswith(b'data:'):continue
            data=raw[5:].strip()
            if data==b'[DONE]':
                complete=True
                break
            try:obj=json.loads(data)
            except (ValueError,UnicodeError):continue
            if not isinstance(obj,dict):continue
            choices=obj.get('choices')
            if not isinstance(choices,list):continue
            for choice in choices:
                if not isinstance(choice,dict):continue
                delta=choice.get('delta')
                if not isinstance(delta,dict):continue
                part=delta.get('content')
                if isinstance(part,str) and part:
                    if first is None:first=time.monotonic()
                    text+=part
                    if len(text)>400:raise RuntimeError('HOLD_UNBOUNDED_OUTPUT')
            frame_count+=1
    if not complete or first is None or not text.strip():
        raise RuntimeError('HOLD_NO_COMPLETED_GENERATIVE_STREAM')
    if stopped() or not health():raise RuntimeError('HOLD_POST_HEALTH_OR_STOP')
    duration=time.monotonic()-start
    correct=('4' in text)
    emit('STREAM_COMPLETED' if correct else 'HOLD_ARITHMETIC_QUALITY',
         first_token_ms=round((first-start)*1000,1),
         total_ms=round(duration*1000,1),
         answer_characters=len(text),answer_contains_four=correct,
         done_frame=True,frames=frame_count,
         only_one_live_generative_model=True)
except Exception as exc:
    reason=str(exc)
    emit(reason if reason.startswith('HOLD_') and len(reason)<80 else 'HOLD_RUNTIME')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


def main():
    ssh.REMOTE=REMOTE
    ssh.api=settled_api
    out=io.StringIO()
    connected=False
    try:
        with contextlib.redirect_stdout(out):
            connected=ssh.probe()
    except Exception:
        print('NOX_V112=HOLD_NATIVE_SSH')
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if not ssh.cleanup():connected=False
        except Exception:
            connected=False
    proof=[]
    cleanup=False
    for line in out.getvalue().splitlines():
        if line.startswith('NATIVE_V112_RESULT=') and len(line)<850:
            print(line);proof.append(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
            cleanup=cleanup or line.endswith('DETACHED_AND_VERIFIED')
    passed=(connected and cleanup and len(proof)==1 and
            '"state":"STREAM_COMPLETED"' in proof[0])
    print('NOX_V112_REAL_MODEL_STREAM='+('PASS' if passed else 'HOLD'))
    return 0 if passed else 2


if __name__=='__main__':
    raise SystemExit(main())
