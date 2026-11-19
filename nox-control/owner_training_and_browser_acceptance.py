#!/usr/bin/env python3
"""Recover the verified JSONL error and independently verify visible streaming."""
import base64
import hashlib
import json
import re
import sys
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_training_jsonl_recovery':'99a9534fe8f3f8f101786e6bb46c6defab20cbb0fd30d1663e9ae474d1f4ba95',
 'owner_browser_qa_entry':'1e8ca5b13dc58df15c251c2a6f7cf3be56f6ffbd37cf80bc9cd7ba03723404ed',
}

def emit(kind,data):
 print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)

def main():
 started=time.monotonic();stages=[]
 for name,pin in PINS.items():
  if name=='owner_browser_qa_entry' and time.monotonic()-started>610:
   stages.append({'stage':name,'state':'DEFERRED_ACTION_TIME_BUDGET','passed':False});continue
  try:
   raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
   if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('HOLD_TRAIN_BROWSER_SOURCE_PIN')
   module=types.ModuleType(name);module.__file__='/root/nox/scripts/'+name+'.py';sys.modules[name]=module
   exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
   rc=module.main()
   stages.append({'stage':name,'returncode':0 if rc is None else rc,'passed':rc in (None,0)})
  except Exception as exc:
   reason=str(exc);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
   stages.append({'stage':name,'passed':False,'reason':reason})
  emit('training_and_browser_stage',stages[-1])
 good=all(x['passed'] for x in stages)
 emit('training_and_browser_summary',{'stages':stages,'elapsed_seconds':round(time.monotonic()-started,3),
     'training_success_requires_native_optimizer_receipt':True})
 if good:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
 return 0 if good else 2

if __name__=='__main__':raise SystemExit(main())
