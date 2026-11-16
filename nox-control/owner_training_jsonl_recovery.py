#!/usr/bin/env python3
"""One explicit recovery of the verified Unicode/JSONL failure, then disk guard.

The first reviewed recovery/guard algorithms remain pinned. This entry supplies
only the new failed-receipt/source transition and a pre-model LF parsing gate.
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
ROOT=Path('/root/nox');STATE=ROOT/'state'
RECOVERY_SHA='7884571d05a9df7d20fb71dfe8e58feabd4941eeec23534f5ec0e2b28c502854'
CHAIN_SHA='c4ed149ca4d5164ac7b9670c82f97c9eaaa65356cfdfcf911a0d88171d7098fa'
INSTALLER_SHA='59ea8ac37bdec4c990950aeef9c4ab7283f633cb300ee6384007111efd06d86c'
CORPUS_PROBE_SHA='fe4cf2b8e434febcd33d90088d18ddbbca51d2ba634beff6e0b47b0f70a4e678'
GUARD_SHA='9fab629c442e572f89dac9f078e43d505c7d93c9feb94ebc34182c56ca5b94e8'
FAILED_REQUEST='6905505383';FAILED_SOURCE='e5ff890d7424eb2abaa2e8d6188ca03759d4dc68'
FAILED_RECEIPT_SHA='250ad99af3269cf8bd7856a63696cbd410a7caf2a5a7a451106bc44f8fe7cd5b'
FAILED_HOLD_SHA='fa33a72e510f39b4330e1db138ec23929f63e5eda22f9948c1b1d94f37b3e985'
HYBRID_BEFORE='7a384bbee919bec9b24642cc5f56b930cc986065172d7a334cc682c7ee40e455'
HYBRID_AFTER='f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af'
DATASET_SHA='31b0d6983d6bb6e40d05ffca505b4b1d68c9e9212648cd9cd270dedafd79fc1d'
ORIGINAL_ADMISSION='6905113544'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_JSONL_RECOVERY_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'));sys.modules[name]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module


def failed_evidence(recovery,helper,resume):
    raw=recovery.read(STATE/('owner_maintenance_'+FAILED_REQUEST+'.json'))
    if digest(raw)!=FAILED_RECEIPT_SHA:fail('HOLD_JSONL_RECOVERY_FAILED_RECEIPT_PIN')
    old=json.loads(raw);pointer=recovery.document(recovery.POINTER)
    prior=old.get('unstarted_recovery') or {};config=prior.get('configuration_preflight') or {}
    if (old.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or old.get('request')!=FAILED_REQUEST
            or old.get('source_sha')!=FAILED_SOURCE or old.get('state')!='HOLD_TRAINING_CONFIG_RECOVERY'
            or old.get('error')!='HOLD_RECOVERY_TRAINER_EXITED_WITHOUT_PROOF'
            or old.get('optimizer_steps_verified') is not False or pointer!=old.get('admission')
            or pointer.get('request')!=FAILED_REQUEST or pointer.get('source_sha')!=FAILED_SOURCE
            or pointer.get('max_steps')!=5 or pointer.get('resume') is not False
            or prior.get('preparation_sha256')!=recovery.PREPARATION_SHA
            or prior.get('dataset_sha256')!=DATASET_SHA or prior.get('dataset_bytes')!=recovery.DATASET_BYTES
            or prior.get('checkpoint_count')!=0 or prior.get('optimizer_updates_before_recovery')!=0
            or config.get('state')!='INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED'
            or config.get('hybrid_sha256')!=HYBRID_BEFORE
            or (prior.get('failed_admission') or {}).get('request')!=ORIGINAL_ADMISSION):
        fail('HOLD_JSONL_RECOVERY_FAILED_LINEAGE')
    expected=resume.boost_pins(resume.read_json(STATE/('owner_maintenance_'+resume.BOOST_REQUEST+'.json')))
    upgrade,upgrade_chain=resume.dispatcher_upgrade_evidence();expected.update(upgrade)
    memory,memory_chain=resume.s03_activation_evidence(upgrade_chain);expected.update(memory)
    media_chain=resume.media_acceptance_evidence(upgrade_chain,rehash_outputs=True)
    for key,value in (('dispatcher_upgrade',upgrade_chain),('s03_activation',memory_chain),('media_acceptance',media_chain)):
        if old.get(key)!=value or pointer.get(key)!=value:fail('HOLD_JSONL_RECOVERY_PRIOR_CHAIN_CHANGED')
    backup=ROOT/'backup/owner_training_resume'/ORIGINAL_ADMISSION
    for path in resume.CONTROLS:
        previous=recovery.read(backup/str(path).lstrip('/'))
        if digest(previous)!=expected[path]:fail('HOLD_JSONL_RECOVERY_CONTROLLER_BACKUP')
        expected[path]=digest(resume.patch_permission(previous.decode(),path.name=='nox_selfheal.py').encode())
    expected[recovery.ENTRY]=HYBRID_BEFORE
    expected[recovery.WRAPPER]=digest(recovery.recovery_wrapper(helper,FAILED_REQUEST))
    if pointer.get('sources')!={str(path):pin for path,pin in expected.items()}:
        fail('HOLD_JSONL_RECOVERY_CURRENT_SOURCE_SET')
    for path,pin in expected.items():
        if digest(recovery.read(path))!=pin:fail('HOLD_JSONL_RECOVERY_CURRENT_SOURCE_CHANGED')
    context={'request':FAILED_REQUEST,'source_sha':FAILED_SOURCE,'receipt_sha256':FAILED_RECEIPT_SHA}
    return expected,old,context,upgrade_chain,memory_chain,media_chain


def configure_recovery(recovery,corpus):
    # Explicit, reviewed transition constants only; do not weaken any service,
    # checkpoint, stop, resource, source, or previous ownership gate in main().
    recovery.FAILED_REQUEST=FAILED_REQUEST;recovery.FAILED_SOURCE=FAILED_SOURCE
    recovery.FAILED_HOLD_SHA=FAILED_HOLD_SHA
    recovery.HYBRID_BEFORE=HYBRID_BEFORE;recovery.HYBRID_AFTER=HYBRID_AFTER
    recovery.DISK_GUARD_SHA=GUARD_SHA
    recovery.failed_admission=lambda helper,resume:failed_evidence(recovery,helper,resume)
    original_preparation=recovery.unstarted_output;cached=[]
    def checked_preparation():
        prepared=original_preparation()
        if prepared.get('dataset_sha256')!=DATASET_SHA:fail('HOLD_JSONL_RECOVERY_DATASET_CHANGED')
        if not cached:
            proof=corpus.read_only_probe()
            if (proof.get('state')!='EXACT_DATASET_DELIMITERS_VERIFIED' or proof.get('dataset_sha256')!=DATASET_SHA
                    or proof.get('source_bytes')!=recovery.DATASET_BYTES or proof.get('full_sha256_verified') is not True
                    or proof.get('lf_jsonl_valid') is not True or proof.get('actual_lf_valid_records')!=136714
                    or proof.get('actual_lf_invalid_records')!=0 or proof.get('legacy_splitlines_invalid') is not True
                    or (proof.get('first_legacy_failure') or {}).get('exception')!='JSONDecodeError'):
                fail('HOLD_JSONL_RECOVERY_LF_PREFLIGHT')
            cached.append(proof)
        return {**prepared,'jsonl_lf_preflight':cached[0]}
    recovery.unstarted_output=checked_preparation


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_JSONL_RECOVERY_OWNER_CONTEXT')
    recovery=load('owner_training_recovery_entry',RECOVERY_SHA)
    corpus=load('owner_training_corpus_probe',CORPUS_PROBE_SHA);configure_recovery(recovery,corpus)
    chain=load('owner_training_recovery_chain',CHAIN_SHA);chain.GUARD_SHA=GUARD_SHA
    installer=load('owner_training_disk_guard_entry',INSTALLER_SHA);installer.GUARD_SHA=GUARD_SHA
    guard=load('owner_training_disk_guard',GUARD_SHA)
    helper,_=recovery.load('owner_native_repair',recovery.HELPER_SHA)
    receipt=STATE/('owner_training_jsonl_recovery_chain_'+request+'.json')
    if receipt.exists():fail('HOLD_JSONL_RECOVERY_REQUEST_USED')
    record={'schema':'NOX_OWNER_TRAINING_JSONL_RECOVERY_CHAIN_V1','request':request,'source_sha':source,
        'started_at':time.time(),'state':'PREFLIGHT','stages':[],'initial_admission':None,
        'failed_admission':{'request':FAILED_REQUEST,'source_sha':FAILED_SOURCE,'receipt_sha256':FAILED_RECEIPT_SHA},
        'dataset_sha256':DATASET_SHA,'dataset_rewritten':False,'trainer_killed':False,'weights_deleted':0,'checkpoints_deleted':0}
    def save():helper.atomic(receipt,json.dumps(record,indent=2).encode())
    success=False
    try:
        reservation=recovery.read(STATE/'train_wants_gpu1',4096);record['teacher_reservation_sha256']=digest(reservation);save()
        rc=recovery.main();native,context=chain.sealed_result(recovery,request,source)
        record['initial_admission']=context
        record['stages'].append({'stage':'LF_JSONL_RECOVERY','state':native.get('state'),'returncode':rc,
            'optimizer_steps_verified':native.get('optimizer_steps_verified')})
        if recovery.read(STATE/'train_wants_gpu1',4096)!=reservation:
            if native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':record['checkpoint_pause']=chain.pause_unprotected(guard,context)
            fail('HOLD_JSONL_RECOVERY_RESERVATION_CHANGED')
        if rc!=0:record['state']='JSONL_RECOVERY_HELD'
        elif native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':
            stage,success=chain.install_guard_or_pause(recovery,installer,guard,context)
            record['stages'].append({'stage':'DISK_GUARD',**stage})
            record['state']='FIVE_STEPS_AND_GUARDED_CONTINUATION_VERIFIED' if success else 'FIVE_STEPS_VERIFIED_GUARD_PENDING_CHECKPOINT_PAUSE'
        elif native.get('state')=='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING':
            record['state']='INITIAL_TRAINING_RUNNING_PROOF_PENDING';record['observation_context']=context;success=True
        elif native.get('state') in ('TRAINING_CHECKPOINTED_BY_NEW_PAUSE','FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED',
                                    'FIVE_STEPS_VERIFIED_DISK_RESERVE_RETAINED'):
            record['state']=native['state'];success=True
        else:fail('HOLD_JSONL_RECOVERY_UNKNOWN_RESULT')
    except Exception as exc:record.update(state='HOLD_TRAINING_JSONL_RECOVERY',reason=safe(exc))
    finally:
        record.update(finished_at=time.time(),service_after=helper.service_state(),chat_after=helper.health())
        save();emit('training_jsonl_recovery_chain_receipt',record)
        emit('training_jsonl_recovery_chain_context',{'request':request,'source_sha':source,
            'receipt_sha256':digest(recovery.read(receipt)),'state':record['state'],'initial_admission':record['initial_admission']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_jsonl_recovery_hold',{'reason':safe(exc)});raise SystemExit(2)
