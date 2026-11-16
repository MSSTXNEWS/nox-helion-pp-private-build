#!/usr/bin/env python3
"""Bounded storage inspection and a quiet-slot check of the existing chat UI."""
import base64
import hashlib
import json
import re
import sys
import time
import types
import urllib.request

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_training_failure_probe':'8065ef2887dfc599cd12cd761e01f229b1c3e10a1f59b91dc5b3faefaa28a282',
 'owner_storage_remaining_audit':'b2f4c15500865532223e67275f86c9a51033f857a2b9534c27edeecf91cd054f',
 'owner_browser_qa_entry':'39da4fd758c48269a6c9ca1bfb1412f2214b3e2aa1bcab371a2550acafb2a9b0',
}

def emit(kind,data):
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)

def load(name):
 raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
 if hashlib.sha256(raw).hexdigest()!=PINS[name]:raise RuntimeError('HOLD_REMAINING_BATCH_SOURCE_PIN')
 module=types.ModuleType(name);module.__file__='/root/nox/scripts/'+name+'.py';sys.modules[name]=module
 exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
 return module

def wait_idle():
 deadline=time.monotonic()+40;checks=0
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 while time.monotonic()<deadline:
  with opener.open('http://127.0.0.1:8081/slots',timeout=3) as response:raw=response.read(100001)
  if len(raw)>100000:raise RuntimeError('HOLD_REMAINING_SLOTS_SIZE')
  value=json.loads(raw)
  if not isinstance(value,list) or not 1<=len(value)<=16:raise RuntimeError('HOLD_REMAINING_SLOTS_SCHEMA')
  checks+=1;busy=0
  for slot in value:
   if not isinstance(slot,dict):raise RuntimeError('HOLD_REMAINING_SLOTS_SCHEMA')
   flags=[slot[k] for k in ('is_processing','processing') if k in slot]
   if not flags or any(type(x) is not bool for x in flags) or len(set(flags))!=1:
    raise RuntimeError('HOLD_REMAINING_SLOTS_UNKNOWN')
   busy+=int(flags[0])
  if busy==0:return {'state':'IDLE_OBSERVED','checks':checks,'slots':len(value),'busy':0}
  time.sleep(2)
 raise RuntimeError('HOLD_FOREGROUND_CHAT_BUSY')

def main():
 stages=[]
 for name in ('owner_training_failure_probe','owner_storage_remaining_audit','owner_browser_qa_entry'):
  try:
   module=load(name)
   if name=='owner_browser_qa_entry':emit('quiet_slot_observation',wait_idle())
   rc=module.main()
   good=rc in (None,0)
   stages.append({'stage':name,'passed':good,'returncode':0 if rc is None else rc})
  except Exception as exc:
   reason=str(exc);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
   stages.append({'stage':name,'passed':False,'reason':reason})
  emit('remaining_verification_stage',stages[-1])
 good=all(x['passed'] for x in stages)
 emit('remaining_verification_summary',{'stages':stages,'training_control_performed':False})
 if good:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 0 if good else 2

if __name__=='__main__':raise SystemExit(main())
