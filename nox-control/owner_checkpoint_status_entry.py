#!/usr/bin/env python3
"""Bind actual stopped-training evidence and export its exact saved checkpoint."""
import base64
import hashlib
import json
import os
import re
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={'owner_training_status_entry':'1f00315ec965166a06161283f5d79200c1c3c50031c83ffe34b42e867a8a66e7',
      'owner_checkpoint_backup_export':'a8b7d140c02fa27e2d7839ddb42e12652e0499b956f6faea88e54c5b5e4f59e9'}
ORIGIN={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
def load(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
        raise RuntimeError('HOLD_CHECKPOINT_STATUS_BUNDLE')
    value=types.ModuleType(name+'_checkpoint_status');sys.modules[value.__name__]=value
    exec(compile(raw,'<'+name+'>','exec'),value.__dict__);value.BUNDLE=BUNDLE
    return value
def emit(value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_status_stage','data':value},separators=(',',':')),flush=True)
def stage(name):
    try:
        code=load(name).main()
        value={'stage':name,'return_code':0 if code is None else code,'state':'COMPLETED' if code in (None,0) else 'HOLD'}
    except Exception as exc:
        message=str(exc)
        reason=message if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',message) else 'HOLD_CHECKPOINT_STATUS_'+type(exc).__name__.upper()
        value={'stage':name,'return_code':2,'state':'HOLD','reason':reason}
    emit(value);return value['return_code']
def main():
    previous=os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT')
    os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=json.dumps(ORIGIN,separators=(',',':'))
    try:status=stage('owner_training_status_entry')
    finally:
        if previous is None:os.environ.pop('NOX_TRAINING_RECOVERY_CONTEXT',None)
        else:os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=previous
    backup=stage('owner_checkpoint_backup_export')
    if status==0 and backup==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if status==0 and backup==0 else 2
if __name__=='__main__':raise SystemExit(main())
