#!/usr/bin/env python3
"""Continue the sealed pending training observation, then verify the chat UI."""
import base64
import hashlib
import json
import os
import re
import sys
import time
import types
import urllib.request

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
CONTEXT={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
         'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
PINS={
 'owner_training_jsonl_observe':'8b6eb5270bf5fbab1a3a58db82affde86e64fe019e838cff76b26aab5bda5251',
 'owner_browser_qa_entry':'1e8ca5b13dc58df15c251c2a6f7cf3be56f6ffbd37cf80bc9cd7ba03723404ed',
}

def emit(kind,data):
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)

def wait_idle():
 deadline=time.monotonic()+40;checks=0
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 while time.monotonic()<deadline:
  with opener.open('http://127.0.0.1:8081/slots',timeout=3) as response:raw=response.read(100001)
  if len(raw)>100000:raise RuntimeError('HOLD_OBSERVE_SLOTS_SIZE')
  value=json.loads(raw)
  if not isinstance(value,list) or not 1<=len(value)<=16:raise RuntimeError('HOLD_OBSERVE_SLOTS_SCHEMA')
  checks+=1;busy=0
  for slot in value:
   if not isinstance(slot,dict):raise RuntimeError('HOLD_OBSERVE_SLOTS_SCHEMA')
   flags=[slot[k] for k in ('is_processing','processing') if k in slot]
   if not flags or any(type(x) is not bool for x in flags) or len(set(flags))!=1:
    raise RuntimeError('HOLD_OBSERVE_SLOTS_UNKNOWN')
   busy+=int(flags[0])
  if busy==0:return {'state':'IDLE_OBSERVED','checks':checks,'slots':len(value),'busy':0}
  time.sleep(2)
 raise RuntimeError('HOLD_FOREGROUND_CHAT_BUSY')

def main():
 started=time.monotonic();stages=[]
 os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=json.dumps(CONTEXT,separators=(',',':'))
 for name,pin in PINS.items():
  if name=='owner_browser_qa_entry' and time.monotonic()-started>610:
   stages.append({'stage':name,'state':'DEFERRED_ACTION_TIME_BUDGET','passed':False});continue
  try:
   raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
   if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('HOLD_OBSERVE_CHAT_SOURCE_PIN')
   module=types.ModuleType(name);module.__file__='/root/nox/scripts/'+name+'.py';sys.modules[name]=module
   exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
   if name=='owner_browser_qa_entry':emit('quiet_slot_observation',wait_idle())
   rc=module.main()
   stages.append({'stage':name,'returncode':0 if rc is None else rc,'passed':rc in (None,0)})
  except Exception as exc:
   reason=str(exc);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
   stages.append({'stage':name,'passed':False,'reason':reason})
  emit('training_observe_chat_stage',stages[-1])
 good=all(x['passed'] for x in stages)
 emit('training_observe_chat_summary',{'stages':stages,'elapsed_seconds':round(time.monotonic()-started,3),
      'initial_training_restarted':False,'training_success_requires_native_optimizer_receipt':True})
 if good:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 0 if good else 2

if __name__=='__main__':raise SystemExit(main())
