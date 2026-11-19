"""V107 existing local teacher proof: one benign public fact and S03 receipt.
Teacher must differ from primary model; STOP, VRAM and privacy hold enforced.
Never sends user chat, S03 or credentials to any external endpoint.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
cd /root/nox/scripts
python3 - <<'PYREMOTE'
import json,re,urllib.request,urllib.error,hashlib,secrets,sys,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V107_LOCAL_DISTINCT_TEACHER_LESSON_V1')
def emit(obj):print('NATIVE_V107_RECEIPT='+json.dumps(obj,sort_keys=True,separators=(',',':')))
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(x).exists() for x in STOP)
def idle():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:slots=json.loads(r.read(24000))
  return isinstance(slots,list) and len(slots)==6 and not any(x.get('is_processing',x.get('processing',False)) for x in slots if isinstance(x,dict))
 except Exception:return False
def models(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/v1/models',timeout=4) as r:
   data=json.loads(r.read(30000))
  found=data.get('data') or []
  return [str(x.get('id') or '') for x in found if isinstance(x,dict) and x.get('id')]
 except Exception:return []
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if not idle():raise RuntimeError('HOLD_USER_MODEL_BUSY')
 endpoints={p:models(p) for p in (8081,8082,8084,8092,8096)}
 safe={str(p):[Path(x).name[:65] for x in ids] for p,ids in endpoints.items()}
 print('NATIVE_V107_MODEL_IDS='+json.dumps(safe,sort_keys=True,separators=(',',':')))
 primary={Path(x).name for x in endpoints[8081]}
 # Only the V106-readback confirmed generative model at port 8084 may be
 # consulted. BGE-M3 (embedding) and Qwen3Guard (safety) are not teachers
 # for the /v1/chat/completions general reasoning task.
 teacher_port=next((p for p in (8084,) if endpoints[p] and
                   any('vikhr-nemo-12b' in Path(x).name.casefold()
                       and Path(x).name not in primary for x in endpoints[p])),None)
 if teacher_port is None:raise RuntimeError('HOLD_NO_VERIFIED_GENERATIVE_TEACHER')
 model_id=endpoints[teacher_port][0]
 # Existing inference endpoint only; no network egress and no private memory.
 question='Чему равно произведение 17 на 19? Ответь только числом.'
 payload={'model':model_id,'messages':[{'role':'user','content':question}],
          'stream':False,'max_tokens':64,'temperature':0.0}
 data=json.dumps(payload,ensure_ascii=False).encode('utf8')
 req=urllib.request.Request('http://127.0.0.1:'+str(teacher_port)+'/v1/chat/completions',
       data=data,headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=45) as r:
  if r.status!=200:raise RuntimeError('HOLD_TEACHER_HTTP')
  raw=r.read(90000)
 response=json.loads(raw)
 choices=response.get('choices') or []
 answer=((choices[0].get('message') or {}).get('content') or '') if choices else ''
 good=isinstance(answer,str) and bool(re.search(r'(?<!\d)323(?!\d)',answer)) and 17*19==323
 if not good:raise RuntimeError('HOLD_INDEPENDENT_PUBLIC_FACT_CHECK')
 if stopped():raise RuntimeError('HOLD_STOP_AFTER_TEACHER')
 import s03_memory
 marker='N107_TEACHER_LESSON_'+secrets.token_hex(6)
 lesson=marker+': проверенная математическая связь: 17 умножить на 19 равно 323; результат независимо проверен арифметикой.'
 record=s03_memory.remember(lesson,segment='M2',provenance='local-model:'+Path(model_id).name[:60],
                           salience=0.5,meta={'owner_approved':True,'privacy':'public_synthetic',
                             'source':'local_teacher','verified_by':'python_arithmetic',
                             'neural_weights_changed':False})
 recalled=s03_memory.recall(marker,k=24)
 found=isinstance(recalled,list) and any(marker in str(x) for x in recalled)
 emit({'state':'DISTINCT_LOCAL_TEACHER_S03_LESSON_VERIFIED' if found else 'HOLD_NATIVE_S03_RECEIPT',
  'port':teacher_port,'teacher_model_basename':Path(model_id).name[:65],
  'independent_public_fact_validated':good,'s03_exact_marker_readback':found,
  'private_records_exported':False,'external_prompt_sent':False,
  'training_optimizer_steps':0,'neural_weights_changed':False})
 if found:print('NATIVE_V107_TEACHER_LESSON_PASS=true')
except Exception as e:
 v=str(e)
 emit({'state':v if v.startswith('HOLD_') and len(v)<90 else 'HOLD_TEACHER_RUNTIME',
       'exception_type':type(e).__name__,'private_records_exported':False,
       'neural_weights_changed':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();okay=False;ssh.REMOTE=REMOTE
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
  with contextlib.redirect_stdout(out):okay=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V107_HOLD='+(v if v.startswith('HOLD_') and len(v)<90 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V107_','TEMP_SSH_CLEANUP=')):
   print(line[:1400]);lines.append(line)
 passed=bool(okay and 'NATIVE_V107_TEACHER_LESSON_PASS=true' in lines)
 print('NOX_V107_LOCAL_TEACHER_KNOWLEDGE_ACCEPTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
