#!/usr/bin/env python3
"""Bind the actual failed resume and measure a lossless checkpoint transfer."""
import base64
import hashlib
import json
import os
import re
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={'owner_training_status_entry':'9b938d80a8e8769467b219f0497f00897b4cfe103cfcc693c6a70fea28491301',
      'owner_training_restore_probe':'00edcbcc0d57a215aa30b42e77661edd3a58b4b5714f4144f334e04c2cff6e30',
      'owner_checkpoint_backup_size_probe':'dcfc277d026bd67e7986c83de096283a4e596b100b9d917d66d7077400ea44ae'}
ORIGIN={'request':'6906626126','source_sha':'c88d33ed8fbacaf58238921f600ec7641782b516',
        'receipt_sha256':'8981703e8b6e65a23b4556d2eac06a851561a3cc8159716d6d740c32bcf10d2c'}
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
    restore=stage('owner_training_restore_probe')
    backup=stage('owner_checkpoint_backup_size_probe')
    if status==0 and restore==0 and backup==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if status==0 and restore==0 and backup==0 else 2
if __name__=='__main__':raise SystemExit(main())
