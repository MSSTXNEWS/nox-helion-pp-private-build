#!/usr/bin/env python3
"""One finite, pinned reindex → native S03 activation handoff.

The activation consumes the exact immutable reindex receipt produced during
this owner action. A local failure leaves training held and reports the stage;
no maintenance lease is held while BGE re-embeds the existing memory index.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

REINDEX_SHA='1ca061458b8c5a59ce425567ec08153b53ef84ddabc1e5235e3a2ce043017732'
ACTIVATION_SHA='1bc460aef03822d754597954757fa0809220a2964ca31f3ac8bb301d3fb51347'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)


def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_S03_RECOVERY_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__='/root/nox/scripts/'+name+'.py'
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_S03_RECOVERY_CONTEXT')
    reindex=load('owner_s03_content_reindex_entry',REINDEX_SHA)
    activation=load('owner_s03_activate_entry',ACTIVATION_SHA)
    if reindex.GATEWAY_SHA!=activation.GATEWAY_SHA or activation.REINDEX_ENTRY_SHA!=REINDEX_SHA:
        fail('HOLD_S03_RECOVERY_SOURCE_CHAIN')
    result=reindex.main()
    if result:
        emit('s03_recovery_stage',{'stage':'CONTENT_REINDEX','state':'BLOCKED','training_released':False})
        return result
    path=reindex.STATE/('content_reindex_'+request+'.json')
    raw=reindex.read(path);gateway=reindex.load_gateway()
    record=reindex.validate_record(json.loads(raw),request,source,gateway)
    receipt_sha=digest(raw)
    settings={'NOX_S03_PREPARE_REQUEST':reindex.PREPARE_REQUEST,'NOX_S03_PREPARE_SHA256':reindex.PREPARE_SHA,
              'NOX_S03_REINDEX_SHA256':receipt_sha}
    previous={key:os.environ.get(key) for key in settings}
    try:
        os.environ.update(settings)
        result=activation.main()
    finally:
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    if result:
        emit('s03_recovery_stage',{'stage':'LIVE_ACTIVATION','state':'BLOCKED',
                                 'reindex_receipt_sha256':receipt_sha,'training_released':False})
        return result
    activation_path=activation.STATE/'owner_s03'/('activation_'+request+'.json')
    activation_raw=activation.read(activation_path);accepted=json.loads(activation_raw)
    if (accepted.get('schema')!='NOX_OWNER_S03_ACTIVATION_V1'
            or accepted.get('request')!=request or accepted.get('source_sha')!=source
            or accepted.get('state')!='LIVE_SHARED_SEMANTIC_MEMORY_AND_NATIVE_INDEX_VERIFIED'
            or accepted.get('content_reindex',{}).get('receipt_sha256')!=receipt_sha):
        fail('HOLD_S03_RECOVERY_ACTIVATION_RECEIPT')
    emit('s03_activation_context',{'request':request,'source_sha':source,
         'receipt_sha256':digest(activation_raw),'content_reindex_receipt_sha256':receipt_sha,
         'gateway_sha256':activation.GATEWAY_SHA,'dispatcher_sha256':accepted.get('dispatcher_after_sha256'),
         'lifecycle_config_sha256':accepted.get('lifecycle_config_sha256'),
         'state':accepted['state'],'training_released':False})
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        reason=str(exc)
        emit('s03_recovery_hold',{'reason':reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__})
        raise SystemExit(2)
