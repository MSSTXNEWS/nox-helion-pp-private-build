"""V110: actual two existing models teacher evidence -> NOX student synthesis.
Synthetic public arithmetic only; never exposes user dialog or memory, no new LLM.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,re,urllib.request,hashlib,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V110_LIVE_TEACHER_TO_MAIN_NOX_SYNTHESIS_V1')
def emit(x):print('NATIVE_V110_RESULT='+json.dumps(x,sort_keys=True,separators=(',',':')))
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(p).exists() for p in STOP)
def request(port,path,body=None,timeout=5):
 raw=json.dumps(body,ensure_ascii=False).encode('utf8') if body is not None else None
 req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=raw,
       method='POST' if body is not None else 'GET',headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as r:
  if r.status!=200:raise RuntimeError('HOLD_MODEL_HTTP')
  raw=r.read(120001)
 if len(raw)>120000:raise RuntimeError('HOLD_RESPONSE_LIMIT')
 return json.loads(raw)
def model(port):
 a=request(port,'/v1/models')
 data=a.get('data') or []
 return [str(x.get('id') or '') for x in data if isinstance(x,dict) and x.get('id')]
def inference(port,model_id,messages,max_tokens=64,timeout=65):
 res=request(port,'/v1/chat/completions',{'model':model_id,'messages':messages,
         'temperature':0.0,'max_tokens':max_tokens,'stream':False},timeout=timeout)
 choices=res.get('choices') or []
 if not choices:return ''
 return str((choices[0].get('message') or {}).get('content') or '')
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 slots=request(8081,'/slots',timeout=4)
 if not isinstance(slots,list) or len(slots)!=6 or any(bool(x.get('is_processing',x.get('processing',False))) for x in slots if isinstance(x,dict)):
  raise RuntimeError('HOLD_PRIMARY_CHAT_BUSY')
 primary=model(8081);teacher=model(8084)
 if len(primary)!=1 or len(teacher)!=1:raise RuntimeError('HOLD_MODEL_IDENTITIES')
 if 'vikhr-nemo-12b' not in Path(teacher[0]).name.casefold() or Path(primary[0]).name==Path(teacher[0]).name:
  raise RuntimeError('HOLD_NOT_DISTINCT_VERIFIED_TEACHER')
 question='Сколько будет 17 умножить на 19?'
 t0=time.monotonic()
 ta=inference(8084,teacher[0],[{'role':'user','content':question+' Ответь только числом.'}],max_tokens=48,timeout=50)
 if not re.search(r'(?<!\d)323(?!\d)',ta) or stopped():
  raise RuntimeError('HOLD_TEACHER_PUBLIC_EVAL')
 teacher_ms=int((time.monotonic()-t0)*1000)
 if stopped():raise RuntimeError('HOLD_STOP_AFTER_TEACHER')
 evidence='Непроверенный ответ локального учителя: '+ta[:200]+'\nНезависимая арифметическая проверка: 17*19=323.'
 main_msgs=[{'role':'system','content':'Ты NOX. Используй ответ учителя только как справочные данные, критически проверь и сформируй свой краткий ответ на русском.'},
            {'role':'user','content':question+'\n'+evidence}]
 final=inference(8081,primary[0],main_msgs,max_tokens=90,timeout=65)
 if stopped():raise RuntimeError('HOLD_STOP_AFTER_MAIN')
 main_ok=bool(re.search(r'(?<!\d)323(?!\d)',final))
 emit({'state':'NOX_OWN_MODEL_SYNTHESIZED_VERIFIED_TEACHER_EVIDENCE' if main_ok else 'HOLD_MAIN_SYNTHESIS_VALIDITY',
       'teacher_model_basename':Path(teacher[0]).name[:70],
       'main_model_basename':Path(primary[0]).name[:70],
       'teacher_public_eval_valid':True,'main_nox_eval_valid':main_ok,
       'teacher_latency_ms':teacher_ms,'total_latency_ms':int((time.monotonic()-t0)*1000),
       'teacher_answer_sha256':hashlib.sha256(ta.encode('utf8')).hexdigest(),
       'main_answer_sha256':hashlib.sha256(final.encode('utf8')).hexdigest(),
       'user_chat_or_private_s03_exported':False,'new_backend_started':False,
       'student_weights_changed':False,'main_owner_chat_http_cookie_tested':False})
 if main_ok:print('NATIVE_V110_TWO_LIVE_MODELS_ACCEPTED=true')
except Exception as e:
 x=str(e)
 emit({'state':x if x.startswith('HOLD_') and len(x)<90 else 'HOLD_TWO_MODEL_RUNTIME',
       'error_type':type(e).__name__,'user_chat_or_private_s03_exported':False,
       'student_weights_changed':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();good=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=old(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):good=ssh.probe()
 except Exception as e:
  x=str(e);print('NOX_V110_HOLD='+(x if x.startswith('HOLD_') and len(x)<90 else 'SSH_NATIVE'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:good=False
  except Exception:good=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V110_RESULT=','NATIVE_V110_TWO_LIVE_MODELS_ACCEPTED=','TEMP_SSH_CLEANUP=')):
   print(line[:2000]);lines.append(line)
 passed=bool(good and 'NATIVE_V110_TWO_LIVE_MODELS_ACCEPTED=true' in lines)
 print('NOX_V110_LIVE_TEACHER_STUDENT_ACCEPTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
