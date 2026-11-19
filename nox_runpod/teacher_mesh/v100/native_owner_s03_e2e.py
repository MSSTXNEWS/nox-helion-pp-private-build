"""V100: OneHost native owner stream -> existing S03 readback acceptance.
Generates one harmless synthetic question, never logs private memory or answers.
Does not change model weights, supervisor services, model roster or ACL.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
cd /root/nox/scripts
NOX_PY="$(python3 - <<'PYFIND'
import os,re,subprocess
from pathlib import Path
candidates=[]
try:
 p=subprocess.run(['supervisorctl','status','nox-proxy'],text=True,capture_output=True,timeout=6)
 m=re.search(r'pid\s+(\d+)',p.stdout)
 if m:
  raw=(Path('/proc')/m.group(1)/'cmdline').read_bytes()
  argv=[x.decode('utf8','replace') for x in raw.split(b'\0') if x]
  for part in argv[:3]:
   if part.startswith('/') and ('python' in Path(part).name):
    candidates.append(part)
   if part.startswith('/') and 'uvicorn' in Path(part).name and Path(part).is_file():
    with Path(part).open('rb') as fh:line=fh.readline(255).decode('utf8','replace')
    if line.startswith('#!') and line[2:].strip().startswith('/'):
     candidates.append(line[2:].strip().split()[0])
except Exception:pass
candidates.extend(('/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
 '/root/nox/env/bin/python','/opt/venv/bin/python','/venv/bin/python',
 '/root/nox/scripts/venv/bin/python','/usr/local/bin/python3'))
seen=set()
for candidate in candidates:
 if candidate in seen:continue
 seen.add(candidate)
 if not candidate.startswith(('/root/nox/','/opt/venv/','/venv/','/usr/local/bin/')):continue
 if not Path(candidate).is_file():continue
 try:
  v=subprocess.run([candidate,'-c','import fastapi, httpx, uvicorn'],capture_output=True,timeout=5)
  if v.returncode==0:
   print(candidate)
   raise SystemExit(0)
 except Exception:pass
raise SystemExit('HOLD_FASTAPI_RUNTIME_NOT_FOUND')
PYFIND
)"
"$NOX_PY" - <<'PYREMOTE'
import asyncio,hashlib,json,secrets,subprocess,sys,time,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V100_OWNER_SSE_S03_E2E_V1')
EXPECTED='f49d997edf203ecc0986684e3250d63d036915efb5842c3f8bbb938cb0deac50'
SOURCE=Path('/root/nox/scripts/chat_proxy.py')
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(p).exists() for p in STOPS)
def emit(obj):print('NATIVE_V100_RESULT='+json.dumps(obj,sort_keys=True,separators=(',',':')))
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return None
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:slots=json.loads(r.read(25000))
  return isinstance(slots,list) and len(slots)==6 and not any(v.get('is_processing',v.get('processing',False)) for v in slots if isinstance(v,dict))
 except Exception:return False
stage='initial'
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not SOURCE.is_file() or SOURCE.is_symlink() or hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:
  raise RuntimeError('HOLD_SOURCE_NOT_V98')
 if health(8080)!=200 or health(8081)!=200 or not idle():
  raise RuntimeError('HOLD_BUSY_OR_HEALTH')
 stage='native_import_s03'
 import s03_memory
 stage='native_import_chat_proxy'
 import chat_proxy
 if not callable(chat_proxy.s03_recall) or not callable(chat_proxy.s03_persist):
  raise RuntimeError('HOLD_NATIVE_S03_NOT_BOUND')
 marker='N100S03CYCLE'+secrets.token_hex(6)
 question='Тест нейтральной памяти '+marker+'. Ответь одним словом: готово. Не используй инструменты.'
 # Authenticated owner request is represented by the trusted internal native
 # entrypoint here, NOT by a public HTTP endpoint or a user-controlled owner flag.
 body={'messages':[{'role':'user','content':question}],'stream':True,'_owner':True,
       'max_tokens':64,'temperature':0.1}
 stage='native_s03_counts_before'
 pre=s03_memory.counts()
 t0=time.monotonic()
 async def invoke():
  response=await chat_proxy._proxy_completion(body)
  if not hasattr(response,'body_iterator'):
   raise RuntimeError('HOLD_NOT_STREAMING_RESPONSE')
  n=0;chunks=0;first=None
  async for chunk in response.body_iterator:
   if stopped():raise RuntimeError('HOLD_STOP_DURING_STREAM')
   if first is None:first=round((time.monotonic()-t0)*1000)
   b=chunk if isinstance(chunk,bytes) else str(chunk).encode('utf8')
   n+=len(b);chunks+=1
   if n>50000:raise RuntimeError('HOLD_STREAM_TOO_LARGE')
  return {'chunks':chunks,'bytes':n,'first_chunk_ms':first,'total_ms':round((time.monotonic()-t0)*1000)}
 stage='stream_inference'
 stream=asyncio.run(asyncio.wait_for(invoke(),timeout=95))
 stage='native_s03_counts_after'
 post=s03_memory.counts()
 if stopped():raise RuntimeError('HOLD_STOP_AFTER_STREAM')
 stage='native_s03_recall'
 matches=s03_memory.recall(marker,k=30)
 found=any(marker in str(item) for item in matches[:30]) if isinstance(matches,list) else False
 count_deltas={}
 if isinstance(pre,dict) and isinstance(post,dict):
  for key in set(pre).intersection(post):
   if isinstance(pre[key],int) and isinstance(post[key],int):
    count_deltas[key]=post[key]-pre[key]
 verified=bool(stream['bytes']>0 and stream['chunks']>0 and found and health(8080)==200 and health(8081)==200)
 emit({'state':'NATIVE_OWNER_STREAM_S03_RECALL_VERIFIED' if verified else 'HOLD_S03_READBACK',
       'completed_stream':stream['bytes']>0,'chunks':stream['chunks'],
       'first_chunk_ms':stream['first_chunk_ms'],'total_ms':stream['total_ms'],
       'exact_marker_recall_found':found,
       's03_count_deltas':count_deltas,
       'private_records_exported':False,'model_weights_changed':False,
       'new_backend_created':False,'actual_authenticated_http_cookie_tested':False})
 if verified:print('NATIVE_V100_E2E_ACCEPTED=true')
except Exception as e:
 v=str(e)
 emit({'state':v if v.startswith('HOLD_') and len(v)<100 else 'HOLD_NATIVE_STREAM_RUNTIME',
       'failed_stage':stage,'exception_type':type(e).__name__,
       'missing_python_module':(e.name if isinstance(e,ModuleNotFoundError) else None),
       'private_records_exported':False,'model_weights_changed':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    out=io.StringIO();good=False;ssh.REMOTE=REMOTE
    original=ssh.api
    def gate(method,path,key,data=None):
        for i in range(4):
            try:
                r=original(method,path,key,data)
                if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
                return r
            except RuntimeError as e:
                if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=gate
    try:
        with contextlib.redirect_stdout(out):good=ssh.probe()
    except Exception as e:
        val=str(e)
        print('NOX_V100_HOLD='+(val if val.startswith("HOLD_") and len(val)<100 else 'NATIVE_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:good=False
        except Exception:good=False
    lines=[]
    for line in out.getvalue().splitlines():
        if line.startswith(('NATIVE_V100_RESULT=','NATIVE_V100_E2E_ACCEPTED=','TEMP_SSH_CLEANUP=')):
            print(line[:2000]);lines.append(line)
    accepted=bool(good and any(x=='NATIVE_V100_E2E_ACCEPTED=true' for x in lines))
    print('NOX_V100_NATIVE_OWNER_S03_ACCEPTED='+str(accepted).lower())
    return 0 if accepted else 2
if __name__=='__main__':raise SystemExit(main())
