#!/usr/bin/env python3
"""Read two ciphertext pages and compare the exact admitted training sources."""
import base64
import hashlib
import json
import re
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={'owner_checkpoint_page_action':'a27efe5a8b29990c43a5530fe9265be42b0c1dc704d1b9183afb0ef658155948',
      'owner_training_source_delta':'898f42129d6a66c4e31bd59bd775ef14f8cfe5628252493d8f307ee54f2e6aed'}

def stage(name):
    try:
        raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
        if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
            raise RuntimeError('HOLD_BACKUP_SOURCE_BUNDLE_PIN')
        module=types.ModuleType('_nox_'+name);sys.modules[module.__name__]=module
        exec(compile(raw,'<'+name+'>','exec'),module.__dict__);module.BUNDLE=BUNDLE
        code=module.main()
        result={'stage':name,'return_code':0 if code is None else code,'state':'COMPLETED' if code in (None,0) else 'HOLD'}
    except Exception as exc:
        reason=str(exc)
        if not re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',reason):reason='HOLD_BACKUP_SOURCE_'+type(exc).__name__.upper()
        result={'stage':name,'return_code':2,'state':'HOLD','reason':reason}
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'backup_source_stage','data':result},separators=(',',':')),flush=True)
    return result['return_code']

def main():
    backup=stage('owner_checkpoint_page_action')
    sources=stage('owner_training_source_delta')
    if backup==0 and sources==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if backup==0 and sources==0 else 2

if __name__=='__main__':raise SystemExit(main())
