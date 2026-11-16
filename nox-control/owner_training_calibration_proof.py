"""Exact generic AMP-calibration provenance and positive checkpoint proofs.

All reads are local and bounded. A saved zero-update baseline is preserved as
history; it is never relabelled as a successful optimizer update.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path('/root/nox');STATE=ROOT/'state';SCRIPTS=ROOT/'scripts'
OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid';POINTER=STATE/'owner_training_admission.json'
NATIVE_SHA='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
HYBRID_SHA='f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af'
ORIGIN={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
BASELINE_SHA='ba19160382025630d41f8187122bc1f51c7aa3abe2c2a8608e9b8804eeac72fe'
BASELINE_TENSOR='6365775e7b5039a291f49ee92e63de263356b2490be29436699cf786bf1c3b13'
LINEAGE_SHA='b2bc1b3630ba40736acdc309b7aa8ea631a756da4913b425ad2e5efcbd7f74bd'
TRAIN_SCHEMA='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1'
STATE_STARTED='CALIBRATED_OPTIMIZER_CONTINUATION_STARTED'
FILES=('trainer_state.json','optimizer.pt','scheduler.pt','rng_state.pth','scaler.pt',
       'adapter_config.json','adapter_model.safetensors')
MODULES={'owner_training_calibration_proof','owner_training_calibration_guard','owner_training_disk_guard'}
CALIBRATION={'schema':'NOX_OWNER_AMP_CALIBRATION_V1','origin_admission':ORIGIN,
    'checkpoint_receipt_sha256':BASELINE_SHA,'lineage_sha256':LINEAGE_SHA,'start_step':5,'target_step':20,
    'planned_steps':1000,'hybrid_sha256':HYBRID_SHA,'optimizer_state_preserved':True,
    'scaler_state_preserved':True,'rng_state_preserved':True,'successful_optimizer_steps_before':0}


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def json_sha(value):return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def plain(path):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_CALIBRATED_PROOF_SYMLINK')
    return path
def identity(info):return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
def read(path,limit=2*1024**2):
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=limit:fail('HOLD_CALIBRATED_PROOF_FILE_SCOPE')
        raw=stream.read(limit+1);after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        if len(raw)!=before.st_size or identity(before)!=identity(after) or identity(after)!=identity(named):
            fail('HOLD_CALIBRATED_PROOF_READ_RACE')
        return raw
def document(path,limit=2*1024**2):
    value=json.loads(read(path,limit))
    if not isinstance(value,dict):fail('HOLD_CALIBRATED_PROOF_DOCUMENT')
    return value
def file_sha(path,deadline):
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);h=hashlib.sha256()
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=512*1024**2:fail('HOLD_CALIBRATED_PROOF_CHECKPOINT_SIZE')
        while True:
            if time.monotonic()>deadline:fail('HOLD_CALIBRATED_PROOF_HASH_BUDGET')
            raw=stream.read(1024**2)
            if not raw:break
            h.update(raw)
        after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        if identity(before)!=identity(after) or identity(after)!=identity(named):fail('HOLD_CALIBRATED_PROOF_HASH_RACE')
    return h.hexdigest()
def context_value(value):
    if (not isinstance(value,dict) or set(value)!={'request','source_sha','receipt_sha256'}
            or not re.fullmatch('[0-9]{1,24}',str(value.get('request','')))
            or not isinstance(value.get('request'),str)
            or not re.fullmatch('[a-f0-9]{40}',str(value.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(value.get('receipt_sha256','')))):
        fail('HOLD_CALIBRATED_PROOF_CONTEXT')
    return value
def sealed(context):
    context_value(context);raw=read(STATE/('owner_maintenance_'+context['request']+'.json'))
    if digest(raw)!=context['receipt_sha256']:fail('HOLD_CALIBRATED_PROOF_SEALED_RECEIPT')
    record=json.loads(raw)
    if (not isinstance(record,dict) or record.get('request')!=context['request']
            or record.get('source_sha')!=context['source_sha']):fail('HOLD_CALIBRATED_PROOF_RECEIPT_CONTEXT')
    return record


def checkpoint(value,*,baseline=False,rehash=True):
    if not isinstance(value,dict):fail('HOLD_CALIBRATED_PROOF_CHECKPOINT_SCHEMA')
    step,start=value.get('global_step'),value.get('start_step')
    good,skipped=value.get('successful_optimizer_steps'),value.get('skipped_optimizer_steps')
    before,after=value.get('before_tensor_sha256'),value.get('after_tensor_sha256')
    if (value.get('schema')!=TRAIN_SCHEMA or value.get('native_sha256')!=NATIVE_SHA
            or value.get('lineage_sha256')!=LINEAGE_SHA or type(step) is not int or type(start) is not int
            or type(good) is not int or type(skipped) is not int or min(good,skipped)<0 or good+skipped!=step-start
            or type(value.get('loss')) not in (int,float) or not math.isfinite(value['loss'])
            or before!=BASELINE_TENSOR or not re.fullmatch('[a-f0-9]{64}',str(after))
            or value.get('merged') is not False or value.get('live_promoted') is not False):
        fail('HOLD_CALIBRATED_PROOF_COUNTERS_OR_LINEAGE')
    if baseline:
        if (step!=5 or start!=0 or good!=0 or skipped!=5 or after!=before
                or value.get('adapter_delta_verified') is not False):fail('HOLD_CALIBRATED_PROOF_ZERO_BASELINE')
    elif (not 5<step<=20 or start!=5 or good<1 or after==before
          or value.get('adapter_delta_verified') is not True):fail('HOLD_CALIBRATED_PROOF_NO_POSITIVE_UPDATE')
    cp=value.get('checkpoint') or {};hashes=cp.get('files_sha256') or {};path=OUTPUT/('checkpoint-'+str(step))
    if (cp.get('path')!=str(path) or cp.get('global_step')!=step or set(hashes)!=set(FILES)
            or any(not re.fullmatch('[a-f0-9]{64}',str(pin)) for pin in hashes.values())):
        fail('HOLD_CALIBRATED_PROOF_CHECKPOINT_SCOPE')
    if rehash:
        deadline=time.monotonic()+45
        if any(file_sha(path/name,deadline)!=pin for name,pin in hashes.items()):fail('HOLD_CALIBRATED_PROOF_CHECKPOINT_HASH')
        if document(path/'trainer_state.json').get('global_step')!=step:fail('HOLD_CALIBRATED_PROOF_CHECKPOINT_STEP')
    return {'schema':'NOX_OWNER_BOUNDED_OPTIMIZER_PROOF_V1','start_step':start,'global_step':step,
        'successful_optimizer_steps':good,'skipped_optimizer_steps':skipped,'loss':value['loss'],
        'positive_optimizer_updates_verified':not baseline,'adapter_delta_verified':not baseline,
        'lineage_sha256':LINEAGE_SHA,'checkpoint_files_sha256':hashes,'checkpoint_file_count':7,
        'before_tensor_sha256':before,'after_tensor_sha256':after,'merged':False,'quality_gate_passed':False}


def sources(pointer,training_only=False):
    pins=pointer.get('sources') or {}
    if len(pins)!=20 or pins.get(str(SCRIPTS/'hybrid_training_entry.py'))!=HYBRID_SHA:
        fail('HOLD_CALIBRATED_PROOF_TRAINING_SOURCES')
    selected={str(SCRIPTS/'hybrid_training_entry.py'),str(SCRIPTS/'run_train_volta_t866u.sh'),str(STATE/'train_cpu_max.env')}
    if not selected<=set(pins):fail('HOLD_CALIBRATED_PROOF_REQUIRED_SOURCES')
    for name,pin in pins.items():
        path=Path(name)
        if (not re.fullmatch('[a-f0-9]{64}',str(pin))
                or not (path.is_relative_to(ROOT) or path==Path('/root/nox_selfheal.py'))):fail('HOLD_CALIBRATED_PROOF_SOURCE_SCOPE')
        if (not training_only or name in selected) and digest(read(path))!=pin:
            fail('HOLD_CALIBRATED_PROOF_SOURCE_CHANGED')
    if digest(read(SCRIPTS/'train_qlora_35b_t866u.py'))!=NATIVE_SHA:fail('HOLD_CALIBRATED_PROOF_NATIVE_SOURCE')


def calibration_evidence(context,*,require_current=True,rehash=True):
    record=sealed(context);pointer=record.get('admission') or {}
    if (record.get('schema') not in ('NOX_OWNER_TRAINING_RESUME_V1','NOX_OWNER_AMP_CALIBRATION_OBSERVATION_V1')
            or record.get('state') not in ('VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION','AMP_CALIBRATION_CHECKPOINTED_BY_PAUSE')
            or record.get('optimizer_steps_verified') is not True or record.get('continuation_to_1000_started') is not False
            or record.get('chat_health_regression') is True
            or json_sha(record.get('amp_calibration'))!=json_sha(CALIBRATION)
            or json_sha(pointer.get('amp_calibration'))!=json_sha(CALIBRATION)
            or pointer.get('schema')!='NOX_OWNER_TRAINING_ADMISSION_V1' or pointer.get('max_steps')!=20
            or pointer.get('resume') is not True):fail('HOLD_CALIBRATED_PROOF_POSITIVE_CALIBRATION_REQUIRED')
    if record['schema']=='NOX_OWNER_AMP_CALIBRATION_OBSERVATION_V1':
        admission_context=context_value(record.get('observed_admission_context'))
        original=sealed(admission_context)
        if (original.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1'
                or original.get('state')!='AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING'
                or original.get('optimizer_steps_verified') is not False or original.get('training_started') is not True
                or original.get('admission')!=pointer or json_sha(original.get('amp_calibration'))!=json_sha(CALIBRATION)):
            fail('HOLD_CALIBRATED_PROOF_PENDING_ANCESTOR')
    else:admission_context=context
    if record['schema']=='NOX_OWNER_TRAINING_RESUME_V1' and record.get('training_started') is not True:
        fail('HOLD_CALIBRATED_PROOF_INITIAL_RUN_NOT_STARTED')
    if pointer.get('request')!=admission_context['request'] or pointer.get('source_sha')!=admission_context['source_sha']:
        fail('HOLD_CALIBRATED_PROOF_ADMISSION_IDENTITY')
    if require_current:
        if document(POINTER)!=pointer:fail('HOLD_CALIBRATED_PROOF_CURRENT_POINTER')
        sources(pointer)
    zero_origin=sealed(ORIGIN)
    if (zero_origin.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1'
            or (zero_origin.get('admission') or {}).get('max_steps')!=5
            or zero_origin.get('optimizer_steps_verified') is not False):fail('HOLD_CALIBRATED_PROOF_ZERO_ORIGIN')
    raw=read(OUTPUT/'owner_receipt_step_5.json')
    if digest(raw)!=BASELINE_SHA:fail('HOLD_CALIBRATED_PROOF_BASELINE_RECEIPT')
    checkpoint(json.loads(raw),baseline=True,rehash=rehash)
    value=record.get('bounded_update_receipt');proof=checkpoint(value,rehash=rehash)
    if (value.get('state') not in ('VERIFIED_BOUNDED_ADAPTER_UPDATE','CHECKPOINTED_OWNER_STOP')
            or value.get('requested_step')!=20 or value['state']=='VERIFIED_BOUNDED_ADAPTER_UPDATE' and proof['global_step']!=20
            or (record['state']=='VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION')!=(value['state']=='VERIFIED_BOUNDED_ADAPTER_UPDATE')
            or json_sha(record.get('bounded_optimizer_proof'))!=json_sha(proof)):
        fail('HOLD_CALIBRATED_PROOF_BOUNDED_RESULT')
    step_raw=read(OUTPUT/('owner_receipt_step_'+str(proof['global_step'])+'.json'))
    step_value=json.loads(step_raw)
    if json_sha(step_value)!=json_sha({k:v for k,v in value.items() if k not in ('state','requested_step')}):
        fail('HOLD_CALIBRATED_PROOF_SAVED_RECEIPT_CHANGED')
    lineage=document(OUTPUT/'owner_lineage.json')
    if json_sha(lineage)!=LINEAGE_SHA or lineage.get('native_sha256')!=NATIVE_SHA:
        fail('HOLD_CALIBRATED_PROOF_CANONICAL_LINEAGE')
    witness={'schema':'NOX_OWNER_CALIBRATED_CONTINUATION_EVIDENCE_V1','calibration_receipt':context,
        'calibration_admission_context':admission_context,'calibration_admission_sha256':json_sha(pointer),
        'baseline_checkpoint_receipt_sha256':BASELINE_SHA,'baseline_successful_optimizer_steps':0,
        'baseline_skipped_optimizer_steps':5,'positive_checkpoint_receipt_sha256':digest(step_raw),
        'positive_checkpoint_global_step':proof['global_step'],'positive_successful_optimizer_steps':proof['successful_optimizer_steps'],
        'positive_skipped_optimizer_steps':proof['skipped_optimizer_steps'],'lineage_sha256':LINEAGE_SHA,
        'positive_before_tensor_sha256':proof['before_tensor_sha256'],'positive_after_tensor_sha256':proof['after_tensor_sha256'],
        'hybrid_sha256':HYBRID_SHA,'quality_gate_passed':False}
    return record,pointer,lineage,value,witness


def continuation_context(context,*,rehash=False):
    record=sealed(context);pointer=document(POINTER)
    if (record.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or record.get('state')!=STATE_STARTED
            or record.get('optimizer_steps_verified') is not True or record.get('chat_health_regression') is True
            or record.get('training_started') is not True or record.get('continuation_target_steps')!=1000
            or record.get('admission')!=pointer or pointer.get('schema')!='NOX_OWNER_TRAINING_ADMISSION_V1'
            or pointer.get('request')!=context['request'] or pointer.get('source_sha')!=context['source_sha']
            or pointer.get('max_steps')!=1000 or pointer.get('resume') is not True):
        fail('HOLD_CALIBRATED_PROOF_CONTINUATION_REQUIRED')
    expected=record.get('calibration_evidence') or {}
    _,old_pointer,lineage,value,witness=calibration_evidence(expected.get('calibration_receipt'),require_current=False,rehash=rehash)
    if (json_sha(expected)!=json_sha(witness) or json_sha(pointer.get('calibration_evidence'))!=json_sha(witness)
            or json_sha(record.get('bounded_update_receipt'))!=json_sha(value)):
        fail('HOLD_CALIBRATED_PROOF_CONTINUATION_CHAIN')
    old_sources=old_pointer.get('sources') or {};new_sources=pointer.get('sources') or {};wrapper=str(SCRIPTS/'run_train_volta_t866u.sh')
    if (set(old_sources)!=set(new_sources)
            or any(new_sources.get(name)!=pin for name,pin in old_sources.items() if name!=wrapper)):
        fail('HOLD_CALIBRATED_PROOF_UNDECLARED_TRAINING_SOURCE_CHANGE')
    sources(pointer,training_only=True)
    policy=document(STATE/'task_boost_mode.json',16384)
    if (policy.get('mode')!='TASK_BOOST' or policy.get('enabled') is not True
            or policy.get('training_allowed') is not True or policy.get('training_service')!='nox-train-volta-t866u'):
        fail('HOLD_CALIBRATED_PROOF_TRAINING_POLICY')
    modules=pointer.get('continuation_modules') or {}
    if set(modules)!=MODULES or record.get('continuation_modules')!=modules:
        fail('HOLD_CALIBRATED_PROOF_CONTROLLER_MODULES')
    for name,pin in modules.items():
        if not re.fullmatch('[a-f0-9]{64}',str(pin)) or digest(read(SCRIPTS/(name+'.py')))!=pin:
            fail('HOLD_CALIBRATED_PROOF_CONTROLLER_MODULE_CHANGED')
    return pointer,lineage,value
