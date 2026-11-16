#!/usr/bin/env python3
"""Retrieve two ciphertext pages and finish the independently reviewed UI check."""
import base64
import hashlib
import json
import re
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={'owner_checkpoint_page_action':'361fda8a8e488d4e7bde475e51e294effed446e0a07398972c664537efd3e79b',
      'owner_browser_release_qa_entry':'b98ac868d49221200c662daff0919fccdbce001a4a3ea1e4f69bb8a1c4339d78'}

def stage(name):
    try:
        raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
        if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
            raise RuntimeError('HOLD_BACKUP_UI_BUNDLE_PIN')
        module=types.ModuleType('_nox_'+name);sys.modules[module.__name__]=module
        exec(compile(raw,'<'+name+'>','exec'),module.__dict__);module.BUNDLE=BUNDLE
        code=module.main()
        result={'stage':name,'return_code':0 if code is None else code,'state':'COMPLETED' if code in (None,0) else 'HOLD'}
    except Exception as exc:
        reason=str(exc)
        if not re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',reason):reason='HOLD_BACKUP_UI_'+type(exc).__name__.upper()
        result={'stage':name,'return_code':2,'state':'HOLD','reason':reason}
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'backup_ui_stage','data':result},separators=(',',':')),flush=True)
    return result['return_code']

def main():
    backup=stage('owner_checkpoint_page_action')
    browser=stage('owner_browser_release_qa_entry')
    if backup==0 and browser==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if backup==0 and browser==0 else 2

if __name__=='__main__':raise SystemExit(main())
