#!/usr/bin/env python3
"""Observe the exact pending LF recovery; continue only its proven checkpoint."""
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
ROOT=Path('/root/nox');STATE=ROOT/'state'
JSONL_ENTRY_SHA='99a9534fe8f3f8f101786e6bb46c6defab20cbb0fd30d1663e9ae474d1f4ba95'
OBSERVER_SHA='86d5df3f3df60d7cd10b65ed275a5272031eb0cb698dc73f6077ed12953751a5'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_JSONL_OBSERVE_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'));sys.modules[name]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module


def read_context():
    try:value=json.loads(os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT',''))
    except ValueError:fail('HOLD_JSONL_OBSERVE_PENDING_CONTEXT')
    if (not isinstance(value,dict) or set(value)!={'request','source_sha','receipt_sha256'}
            or not str(value.get('request','')).isdigit()
            or not re.fullmatch('[a-f0-9]{40}',str(value.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(value.get('receipt_sha256','')))):
        fail('HOLD_JSONL_OBSERVE_PENDING_CONTEXT')
    return value


def configure_observer(entry,observer):
    def reviewed_recovery():
        recovery=entry.load('owner_training_recovery_entry',entry.RECOVERY_SHA)
        corpus=entry.load('owner_training_corpus_probe',entry.CORPUS_PROBE_SHA)
        entry.configure_recovery(recovery,corpus)
        return recovery
    # Only context/source constants and pure validators change. The observer
    # never calls recovery.main or reads/parses the large corpus during training.
    observer.load_recovery=reviewed_recovery
    return reviewed_recovery()


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_JSONL_OBSERVE_OWNER_CONTEXT')
    initial_context=read_context()
    if initial_context['request']==request:fail('HOLD_JSONL_OBSERVE_NEW_REQUEST_REQUIRED')
    entry=load('owner_training_jsonl_recovery',JSONL_ENTRY_SHA)
    observer=load('owner_training_recovery_observe',OBSERVER_SHA)
    recovery=configure_observer(entry,observer);helper,_=recovery.load('owner_native_repair',recovery.HELPER_SHA)
    chain=entry.load('owner_training_recovery_chain',entry.CHAIN_SHA);chain.GUARD_SHA=entry.GUARD_SHA
    installer=entry.load('owner_training_disk_guard_entry',entry.INSTALLER_SHA);installer.GUARD_SHA=entry.GUARD_SHA
    guard=entry.load('owner_training_disk_guard',entry.GUARD_SHA)
    receipt=STATE/('owner_training_jsonl_observation_'+request+'.json')
    if receipt.exists():fail('HOLD_JSONL_OBSERVE_REQUEST_USED')
    record={'schema':'NOX_OWNER_TRAINING_JSONL_OBSERVATION_V1','request':request,'source_sha':source,
        'started_at':time.time(),'state':'PREFLIGHT','stages':[],'initial_admission':None,
        'observed_initial_admission':initial_context,'initial_training_restarted':False,
        'trainer_killed':False,'weights_deleted':0,'checkpoints_deleted':0}
    def save():helper.atomic(receipt,json.dumps(record,indent=2).encode())
    success=False
    try:
        reservation=recovery.read(STATE/'train_wants_gpu1',4096);record['teacher_reservation_sha256']=digest(reservation);save()
        rc=observer.main(initial_context);native,context=chain.sealed_result(recovery,request,source)
        record['initial_admission']=context
        record['stages'].append({'stage':'OBSERVE_EXISTING_FIRST_FIVE','state':native.get('state'),'returncode':rc,
            'optimizer_steps_verified':native.get('optimizer_steps_verified')})
        if recovery.read(STATE/'train_wants_gpu1',4096)!=reservation:
            if native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':record['checkpoint_pause']=chain.pause_unprotected(guard,context)
            fail('HOLD_JSONL_OBSERVE_RESERVATION_CHANGED')
        if rc!=0:record['state']='JSONL_OBSERVATION_HELD'
        elif native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':
            stage,success=chain.install_guard_or_pause(recovery,installer,guard,context)
            record['stages'].append({'stage':'DISK_GUARD',**stage})
            record['state']='FIVE_STEPS_AND_GUARDED_CONTINUATION_VERIFIED' if success else 'FIVE_STEPS_VERIFIED_GUARD_PENDING_CHECKPOINT_PAUSE'
        elif native.get('state')=='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING':
            record['state']='INITIAL_TRAINING_RUNNING_PROOF_PENDING';record['observation_context']=initial_context;success=True
        elif native.get('state') in ('TRAINING_CHECKPOINTED_BY_NEW_PAUSE','FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED',
                                    'FIVE_STEPS_VERIFIED_DISK_RESERVE_RETAINED'):
            record['state']=native['state'];success=True
        else:fail('HOLD_JSONL_OBSERVE_UNKNOWN_RESULT')
    except Exception as exc:record.update(state='HOLD_TRAINING_JSONL_OBSERVATION',reason=safe(exc))
    finally:
        record.update(finished_at=time.time(),service_after=helper.service_state(),chat_after=helper.health())
        save();emit('training_jsonl_observation_receipt',record)
        emit('training_jsonl_observation_context',{'request':request,'source_sha':source,
            'receipt_sha256':digest(recovery.read(receipt)),'state':record['state'],
            'initial_admission':record['initial_admission'],'observation_context':record.get('observation_context')})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_jsonl_observation_hold',{'reason':safe(exc)});raise SystemExit(2)
