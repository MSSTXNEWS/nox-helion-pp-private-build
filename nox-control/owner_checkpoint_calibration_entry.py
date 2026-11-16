#!/usr/bin/env python3
"""Export the saved checkpoint, calibrate preserved AMP state and bind facts.

Each stage retains its own native evidence. The original failed admission is
used unless this exact owner action actually installed a sealed calibration.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
    'owner_native_repair':'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_checkpoint_backup_export':'26e4e3399aae1933023f03e70afe8684e8220e20f76ec071f751848caa28c74f',
    'owner_training_amp_calibration':'516a0ce2c0753bd3813a4d319a96d182197180e627d9bb318f00760d920991ea',
    'owner_training_status':'1688fc70b8663434beed02b6d4488ca8e5f636af71aa8e5498e5606f2b69751a',
    'owner_training_status_entry':'9b938d80a8e8769467b219f0497f00897b4cfe103cfcc693c6a70fea28491301',
}
ORIGIN={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}

def fail(code):raise RuntimeError(code)
def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def safe(exc):
    value=str(exc)
    return value if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',value) else 'HOLD_CHECKPOINT_CALIBRATION_'+type(exc).__name__.upper()
def load(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if not raw or len(raw)>1_000_000 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
        fail('HOLD_CHECKPOINT_CALIBRATION_SOURCE_PIN')
    module=types.ModuleType(name+'_checkpoint_calibration')
    module.__file__='/root/nox/scripts/'+name+'.py'
    sys.modules[module.__name__]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    module.BUNDLE=BUNDLE
    return module

def bind_current_status(request,source):
    status=load('owner_training_status')
    pointer,_=status.document(status.ROOT/'state/owner_training_admission.json')
    if pointer.get('request')==ORIGIN['request'] and pointer.get('source_sha')==ORIGIN['source_sha']:
        context=status.context_value(ORIGIN)
    elif pointer.get('request')==request and pointer.get('source_sha')==source and pointer.get('max_steps')==20:
        receipt,sha=status.document(status.ROOT/'state'/('owner_maintenance_'+request+'.json'),2*1024**2)
        if (receipt.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1'
                or receipt.get('request')!=request or receipt.get('source_sha')!=source
                or receipt.get('admission')!=pointer
                or receipt.get('state') not in ('AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING',
                    'VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION','AMP_CALIBRATION_CHECKPOINTED_BY_PAUSE')):
            fail('HOLD_CHECKPOINT_CALIBRATION_SEALED_ADMISSION')
        context=status.context_value({'request':request,'source_sha':source,'receipt_sha256':sha})
    else:fail('HOLD_CHECKPOINT_CALIBRATION_CURRENT_POINTER')
    status.admission(context)
    old=os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT')
    os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=json.dumps(context,separators=(',',':'))
    try:
        emit('checkpoint_calibration_status_context',context)
        return load('owner_training_status_entry').main()
    finally:
        if old is None:os.environ.pop('NOX_TRAINING_RECOVERY_CONTEXT',None)
        else:os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=old

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        fail('HOLD_CHECKPOINT_CALIBRATION_OWNER_CONTEXT')
    if os.environ.get('NOX_TRAINING_CALIBRATION_CONTEXT'):
        fail('HOLD_CHECKPOINT_CALIBRATION_INITIAL_ONLY')
    helper=load('owner_native_repair')
    target=Path('/root/nox/state')/('owner_checkpoint_calibration_'+request+'.json')
    if target.exists() or target.is_symlink():fail('HOLD_CHECKPOINT_CALIBRATION_REQUEST_USED')
    record={'schema':'NOX_OWNER_CHECKPOINT_CALIBRATION_BATCH_V1','request':request,'source_sha':source,
        'started_at':time.time(),'stages':[],'weights_merged':False,'weights_deleted':0,
        'continuation_to_1000_admitted':False}
    def save():helper.atomic(target,json.dumps(record,sort_keys=True).encode())
    def stage(name,operation):
        item={'stage':name,'started_at':time.time()};record['stages'].append(item);save()
        try:
            code=operation()
            item.update(return_code=0 if code is None else code,state='COMPLETED' if code in (None,0) else 'HOLD')
        except Exception as exc:item.update(return_code=2,state='HOLD',reason=safe(exc))
        item['finished_at']=time.time();save();emit('checkpoint_calibration_stage',item)
    stage('checkpoint5_encrypted_export',lambda:load('owner_checkpoint_backup_export').main())
    stage('bounded_amp_calibration',lambda:load('owner_training_amp_calibration').main())
    stage('training_status_binding',lambda:bind_current_status(request,source))
    success=all(item['return_code']==0 for item in record['stages'])
    record.update(state='VERIFIED_BATCH' if success else 'BATCH_WITH_RECORDED_HOLDS',finished_at=time.time())
    save();emit('checkpoint_calibration_batch_receipt',record)
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('checkpoint_calibration_hold',{'reason':safe(exc)});raise SystemExit(2)
