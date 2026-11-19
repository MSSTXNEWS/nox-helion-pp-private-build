"""NOX V108 native inventory of EXISTING local inference endpoints.

Do not send chat prompts to embedding, reranker, safety guard, proxy or S03.
Only read /v1/models and /health; no GPU model loads or service changes.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

old=ssh.api
def attached(method,path,key,data=None):
    result=old(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(13)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json, re, urllib.request, urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V108_SCHEMA=NOX_LOCAL_TEACHER_CAPABILITY_DISCOVERY_V1')
ports=(8081,8082,8083,8084,8085,8086,8087,8088,8089,8090,8091,8092,8093,8094,8095)
def inspect(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/v1/models',timeout=1.8) as response:
            if response.status!=200:return {'port':port,'state':'HOLD_HTTP_'+str(response.status)}
            content=response.read(25000)
        d=json.loads(content)
        rows=d.get('data') if isinstance(d,dict) else None
        if not isinstance(rows,list):return {'port':port,'state':'HOLD_MODEL_SCHEMA'}
        names=[Path(str(r.get('id') or '')).name[:100] for r in rows[:5] if isinstance(r,dict)]
        if not names:return {'port':port,'state':'HOLD_NO_MODELS'}
        kinds=[]
        for name in names:
            low=name.casefold()
            if any(k in low for k in ('embed','bge-','rerank','e5-')):
                kinds.append('EMBEDDING_OR_RERANKER_NOT_CHAT_TEACHER')
            elif any(k in low for k in ('guard','shield','moderation','safety')):
                kinds.append('GUARD_OR_MODERATION_NOT_GENERAL_CHAT_TEACHER')
            elif any(k in low for k in ('qwen','deepseek','llama','mistral','gemma')):
                kinds.append('GENERATIVE_CANDIDATE_NEEDS_CHAT_VERIFICATION')
            else:
                kinds.append('UNKNOWN_CAPABILITY_HOLD')
        return {'port':port,'state':'MODELS_LISTED',
                'model_basenames':names,'model_roles':kinds,
                'no_generation_issued':True}
    except urllib.error.HTTPError as error:
        return {'port':port,'state':'HTTP_'+str(error.code)}
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        return {'port':port,'state':'NOT_RESPONDING'}
for port in ports:
    result=inspect(port)
    if result['state']!='NOT_RESPONDING':
        text=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if len(text)<750:print('NATIVE_V108_PORT='+text)
print('NATIVE_V108_SAFETY_POLICY=NO_EMBEDDING_OR_GUARD_MODEL_AS_CHAT_TEACHER')
print('NATIVE_V108_NO_PRIVATE_CHAT_OR_WEIGHTS_CHANGED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE
    ssh.api=attached
    out=io.StringIO()
    okay=False
    try:
        with contextlib.redirect_stdout(out):okay=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V108_HOLD='+msg if msg.startswith("HOLD_") and len(msg)<100 else "HOLD_NATIVE_ACCESS")
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if not ssh.cleanup():okay=False
        except Exception:
            okay=False
    found=False
    for line in out.getvalue().splitlines():
        if line.startswith(("NATIVE_V108_","TEMP_SSH_CLEANUP=")) and len(line)<800:
            print(line)
        if line.startswith("NATIVE_V108_PORT="):found=True
    print("NOX_V108_NATIVE_TEACHER_DISCOVERY="+("PASS" if okay and found else "HOLD"))
    return 0 if okay and found else 2
if __name__=="__main__":
    raise SystemExit(main())
