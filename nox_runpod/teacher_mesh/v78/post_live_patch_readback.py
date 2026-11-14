"""NOX V78: independent post-activation live readback + short main-stream latency."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
orig=ssh.api
def delay(method,path,key,data=None):
 r=orig(method,path,key,data)
 if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
 return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,json,urllib.request,urllib.error,subprocess,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V78_POST_LIVE_PATCH_SMOKE_V1')
src=Path('/root/nox/scripts/chat_proxy.py')
expected='596130dda753d7fed5514a0ae36d8908be8699c804cbb1288f58a410418f043b'
try:sha=hashlib.sha256(src.read_bytes()).hexdigest()
except OSError:sha=None
print('NATIVE_LIVE_PROXY_SHA_MATCH='+str(sha==expected).lower())
try:
 proc=subprocess.run(['supervisorctl','status','nox-proxy'],capture_output=True,text=True,timeout=7)
 fields=proc.stdout.split()
 service=fields[1] if len(fields)>1 else 'UNKNOWN'
except Exception:service='UNKNOWN'
print('NATIVE_CHAT_SERVICE='+service)
for port in (8080,8081):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:status=r.status
 except Exception:status=0
 print('NATIVE_POST_HEALTH_'+str(port)+'='+str(status))
try:
 req=urllib.request.Request('http://127.0.0.1:8081/v1/models')
 with urllib.request.urlopen(req,timeout=4) as r:
  info=json.loads(r.read(16000))
 model=info['data'][0]['id']
 if not model.endswith('/models/current.gguf'):raise ValueError()
 p={'model':model,'stream':True,'max_tokens':35,'temperature':0,
    'messages':[{'role':'user','content':'Ответь одним предложением по-русски: чем проверяемые факты отличаются от предположений?'}]}
 req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
    data=json.dumps(p,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
 start=time.monotonic();first=None;chars=0;done=False
 with urllib.request.urlopen(req,timeout=30) as response:
  for line in response:
   if not line.startswith(b'data:'):continue
   text=line[5:].decode('utf8','replace').strip()
   if text=='[DONE]':done=True;break
   try:ev=json.loads(text)
   except ValueError:continue
   for choice in ev.get('choices',[]):
    part=(choice.get('delta') or {}).get('content','')
    if part:
     if first is None:first=time.monotonic()
     chars+=len(part)
 elapsed=(time.monotonic()-start)*1000
 print('NATIVE_POST_MAIN_STREAM='+json.dumps({'done':done,'chars':chars,
   'first_content_ms':round((first-start)*1000,1) if first else None,
   'e2e_ms':round(elapsed,1),'main_chat_through_proxy_tested':False},separators=(',',':')))
except Exception:
 print('NATIVE_POST_MAIN_STREAM=HOLD_INFERENCE')
print('NATIVE_USER_CHAT_FULL_E2E_VERIFIED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
 ssh.REMOTE=REMOTE;ssh.api=delay
 ok=False
 try:ok=ssh.probe()
 except Exception as exc:
  x=str(exc);print('NOX_V78='+x if x.startswith('HOLD_') else 'NOX_V78=HOLD')
 finally:
  try:
   if not ssh.cleanup():ok=False
  except Exception:ok=False
 raise SystemExit(0 if ok else 2)
