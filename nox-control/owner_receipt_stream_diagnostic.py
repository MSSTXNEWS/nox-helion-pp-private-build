#!/usr/bin/env python3
"""Read the completed training receipt and diagnose one ordinary UI response."""
import base64
import hashlib
import json
import re
import sys
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_calibration_receipt_read':'a892db54e793d27c4d328e4ac07ee02cdfe2f11aea339c6edf6f4f7301a90338',
 'owner_chat_runtime_snapshot':'9d2edece94c186f2774e93d74b8855b9a1933f8804cb814daffca5e720231f1d',
 'owner_browser_transport_qa_entry':'6919392eaec25ced6b1d3174ad402577239a015a3935a13adedd6ee926678f01',
}
def emit(kind,value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':'),allow_nan=False),flush=True)
def load(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if not raw or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=PINS[name]:
        raise RuntimeError('HOLD_RECEIPT_STREAM_SOURCE_PIN')
    value=types.ModuleType(name+'_receipt_stream')
    value.__file__='<'+name+'>';sys.modules[value.__name__]=value
    exec(compile(raw,value.__file__,'exec'),value.__dict__);value.BUNDLE=BUNDLE
    return value
def main():
    stages=[]
    def stage(name,operation):
        try:
            result=operation()
            item={'stage':name,'return_code':result if type(result) is int else 0}
        except Exception as exc:
            text=str(exc)
            reason=text if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+',text) else 'HOLD_RECEIPT_STREAM_'+type(exc).__name__.upper()
            item={'stage':name,'return_code':2,'reason':reason}
        stages.append(item);emit('receipt_stream_stage',item)
    stage('actual_training_receipts',lambda:load('owner_calibration_receipt_read').main())
    def snapshot(phase):
        emit('chat_runtime_'+phase,load('owner_chat_runtime_snapshot').snapshot())
    stage('runtime_before',lambda:snapshot('before'))
    stage('one_chat_transport_diagnostic',lambda:load('owner_browser_transport_qa_entry').main())
    stage('runtime_after',lambda:snapshot('after'))
    good=all(row['return_code']==0 for row in stages)
    emit('receipt_stream_diagnostic_summary',{'stages':stages,'training_control_performed':False,
         'weights_changed':False,'backup_ciphertext_exported':False})
    if good:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
