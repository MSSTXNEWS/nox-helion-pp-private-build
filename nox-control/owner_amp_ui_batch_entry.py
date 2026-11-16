#!/usr/bin/env python3
"""Run the reviewed static repair, bounded calibration and evidence integration.

Each stage keeps its own native receipt. A failed independent UI stage does not
undo a running trainer. Training status uses only the sealed current admission;
the browser check runs last and never promotes or merges candidate weights.
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
    'owner_chat_reports_state_entry':'db5da19cc935bc6dc476e054923d99c5ec6c26fc43a7d6a8ea3a727b2ba1ea80',
    'owner_training_amp_calibration':'7b2a126d0c8212f446d434652de5260e28fdc5b66a4dce1aaa237775842e8f80',
    'owner_training_status':'72732887e7bf4e4032cb99289b7620301ba48d04d583200464942ebffbd4ff2e',
    'owner_training_status_entry':'1f00315ec965166a06161283f5d79200c1c3c50031c83ffe34b42e867a8a66e7',
    'owner_browser_qa_entry':'8a756011dde849d818ef335e804f1a487115a08a1b524c863659b86dfeb00565',
}

def fail(code):raise RuntimeError(code)
def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def safe(exc):
    value=str(exc)
    return value if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',value) else 'HOLD_BATCH_'+type(exc).__name__.upper()
def load(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if not raw or len(raw)>1_000_000 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
        fail('HOLD_BATCH_SOURCE_PIN')
    module=types.ModuleType(name+'_batch_reviewed')
    module.__file__='/root/nox/scripts/'+name+'.py'
    sys.modules[module.__name__]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    module.BUNDLE=BUNDLE
    return module

def bind_current_status(request,source):
    status=load('owner_training_status')
    pointer,_=status.document(status.ROOT/'state/owner_training_admission.json')
    receipt,sha=status.document(status.ROOT/'state'/('owner_maintenance_'+request+'.json'),2*1024**2)
    if (receipt.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1'
            or receipt.get('request')!=request or receipt.get('source_sha')!=source
            or receipt.get('admission')!=pointer or pointer.get('request')!=request
            or pointer.get('source_sha')!=source or pointer.get('max_steps')!=20
            or receipt.get('state') not in ('AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING',
                'VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION','AMP_CALIBRATION_CHECKPOINTED_BY_PAUSE')):
        fail('HOLD_BATCH_SEALED_CURRENT_CALIBRATION')
    context=status.context_value({'request':request,'source_sha':source,'receipt_sha256':sha})
    status.admission(context)
    old=os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT')
    os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=json.dumps(context,separators=(',',':'))
    try:
        emit('batch_training_status_context',context)
        return load('owner_training_status_entry').main()
    finally:
        if old is None:os.environ.pop('NOX_TRAINING_RECOVERY_CONTEXT',None)
        else:os.environ['NOX_TRAINING_RECOVERY_CONTEXT']=old

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):
        fail('HOLD_BATCH_OWNER_CONTEXT')
    if os.environ.get('NOX_TRAINING_CALIBRATION_CONTEXT'):
        fail('HOLD_BATCH_INITIAL_CALIBRATION_ONLY')
    helper=load('owner_native_repair')
    target=Path('/root/nox/state')/('owner_amp_ui_batch_'+request+'.json')
    if target.exists() or target.is_symlink():fail('HOLD_BATCH_REQUEST_USED')
    started=time.monotonic()
    record={'schema':'NOX_OWNER_AMP_UI_BATCH_V1','request':request,'source_sha':source,
        'started_at':time.time(),'stages':[],'weights_merged':False,'weights_deleted':0,
        'continuation_to_1000_admitted':False}
    def save():helper.atomic(target,json.dumps(record,sort_keys=True).encode())
    def stage(name,operation):
        item={'stage':name,'started_at':time.time()};record['stages'].append(item);save()
        try:
            code=operation()
            item.update(return_code=0 if code is None else code,state='COMPLETED' if code in (None,0) else 'HOLD')
        except Exception as exc:item.update(return_code=2,state='HOLD',reason=safe(exc))
        item['finished_at']=time.time();save();emit('amp_ui_batch_stage',item)
        return item['return_code']
    stage('reports_state',lambda:load('owner_chat_reports_state_entry').main())
    calibration=stage('bounded_amp_calibration',lambda:load('owner_training_amp_calibration').main())
    if calibration==0:
        stage('training_status_binding',lambda:bind_current_status(request,source))
    else:
        record['stages'].append({'stage':'training_status_binding','state':'HOLD',
            'reason':'HOLD_BATCH_CALIBRATION_NOT_ACCEPTED','return_code':2});save()
    if time.monotonic()-started<620:
        stage('browser_acceptance',lambda:load('owner_browser_qa_entry').main())
    else:
        record['stages'].append({'stage':'browser_acceptance','state':'DEFERRED',
            'reason':'HOLD_BATCH_BROWSER_TIME_BUDGET','return_code':2});save()
    success=all(item['return_code']==0 for item in record['stages'])
    record.update(state='VERIFIED_BATCH' if success else 'BATCH_WITH_RECORDED_HOLDS',finished_at=time.time())
    save();emit('amp_ui_batch_receipt',record)
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('amp_ui_batch_hold',{'reason':safe(exc)});raise SystemExit(2)
