#!/usr/bin/env python3
"""Resume the exact saved AMP calibration state from step5 to at most step20.

The trainer, corpus, model, optimizer, scaler and RNG state remain unchanged.
No continuation to1000 is admitted here. A repeated owner action may observe
an exact sealed pending receipt, but never starts that bounded run a second time.
"""
import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');STATE=ROOT/'state';SCRIPTS=ROOT/'scripts'
OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid';POINTER=STATE/'owner_training_admission.json'
WRAPPER=SCRIPTS/'run_train_volta_t866u.sh';SERVICE='nox-train-volta-t866u'
TRAIN_SCHEMA='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1';SCHEMA='NOX_OWNER_AMP_CALIBRATION_V1'
PENDING='AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING';VERIFIED='VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION'
ORIGIN={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
OBSERVATION_REQUEST='6905989441'
OBSERVATION_SHA='242bd58ab4f99f04aeff1ee6905d3200a0381b9fd140b2c7820f92fffc63b782'
BASELINE_RECEIPT_SHA='ba19160382025630d41f8187122bc1f51c7aa3abe2c2a8608e9b8804eeac72fe'
LINEAGE_SHA='b2bc1b3630ba40736acdc309b7aa8ea631a756da4913b425ad2e5efcbd7f74bd'
BASELINE_TENSOR_SHA='6365775e7b5039a291f49ee92e63de263356b2490be29436699cf786bf1c3b13'
FAILED_HOLD_SHA='0e85d452c042e4b3a28b8cb8825d324ecca837d10857fea55a3b2d8da384183a'
DATASET_SHA='31b0d6983d6bb6e40d05ffca505b4b1d68c9e9212648cd9cd270dedafd79fc1d'
HYBRID_SHA='f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af'
NATIVE_SHA='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
PINS={'owner_native_repair':'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
      'owner_training_resume':'3ea9dd892810255acafac0a188d873e98e16b87c4185466c2e9dd3bce2b0f9bc',
      'owner_training_recovery_entry':'7884571d05a9df7d20fb71dfe8e58feabd4941eeec23534f5ec0e2b28c502854',
      'owner_training_disk_guard':'9fab629c442e572f89dac9f078e43d505c7d93c9feb94ebc34182c56ca5b94e8',
      'owner_training_scaler_probe':'c659e6179086bad59265689e54b6b990ab22c842a82f63885773cee4ce91d686'}
START=5;TARGET=20


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def json_sha(value):return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def safe(exc):
    value=str(exc);return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=PINS[name]:fail('HOLD_AMP_CALIBRATION_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(SCRIPTS/(name+'.py'));sys.modules[name]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module
def context_value(value):
    if (not isinstance(value,dict) or set(value)!={'request','source_sha','receipt_sha256'}
            or not isinstance(value.get('request'),str) or not re.fullmatch('[0-9]{1,24}',value['request'])
            or not re.fullmatch('[a-f0-9]{40}',str(value.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(value.get('receipt_sha256','')))):
        fail('HOLD_AMP_CALIBRATION_CONTEXT')
    return value


def calibration_metadata():
    return {'schema':SCHEMA,'origin_admission':dict(ORIGIN),'checkpoint_receipt_sha256':BASELINE_RECEIPT_SHA,
        'lineage_sha256':LINEAGE_SHA,'start_step':START,'target_step':TARGET,'planned_steps':1000,
        'hybrid_sha256':HYBRID_SHA,'optimizer_state_preserved':True,'scaler_state_preserved':True,
        'rng_state_preserved':True,'successful_optimizer_steps_before':0}


def wrapper_source(helper,request):
    # Use the reviewed hold/STOP/CPU/CUDA wrapper; only the explicit bound changes.
    original=helper.wrapper_source(request,5,True)
    anchor=' --max-steps 5 --planned-steps 1000 --resume\n'
    if original.count(anchor)!=1:fail('HOLD_AMP_CALIBRATION_WRAPPER_ANCHOR')
    return original.replace(anchor,' --max-steps 20 --planned-steps 1000 --resume\n',1).encode()


def sources_unchanged(recovery,pointer):
    pins=pointer.get('sources') or {}
    if (len(pins)!=20 or pins.get(str(SCRIPTS/'hybrid_training_entry.py'))!=HYBRID_SHA
            or digest(recovery.read(SCRIPTS/'train_qlora_35b_t866u.py'))!=NATIVE_SHA):
        fail('HOLD_AMP_CALIBRATION_SOURCE_SET')
    for name,pin in pins.items():
        path=Path(name)
        if (not re.fullmatch('[a-f0-9]{64}',str(pin))
                or not (path.is_relative_to(ROOT) or path==Path('/root/nox_selfheal.py'))
                or digest(recovery.read(path))!=pin):fail('HOLD_AMP_CALIBRATION_SOURCE_CHANGED')


def checkpoint_proof(recovery,helper,value,*,baseline=False):
    """A saved all-skipped state is resumable, but is never a weight update."""
    if not isinstance(value,dict):fail('HOLD_AMP_CALIBRATION_CHECKPOINT_RECEIPT')
    step=value.get('global_step');start=value.get('start_step')
    good=value.get('successful_optimizer_steps');skipped=value.get('skipped_optimizer_steps')
    before=value.get('before_tensor_sha256');after=value.get('after_tensor_sha256')
    if (value.get('schema')!=TRAIN_SCHEMA or value.get('native_sha256')!=NATIVE_SHA
            or value.get('lineage_sha256')!=LINEAGE_SHA or type(step) is not int or type(start) is not int
            or type(good) is not int or type(skipped) is not int or min(good,skipped)<0
            or good+skipped!=step-start or type(value.get('loss')) not in (int,float)
            or not math.isfinite(value['loss']) or value.get('merged') is not False or value.get('live_promoted') is not False
            or before!=BASELINE_TENSOR_SHA or not re.fullmatch('[a-f0-9]{64}',str(after))):
        fail('HOLD_AMP_CALIBRATION_COUNTER_OR_LINEAGE')
    if baseline:
        if (step!=START or start!=0 or good!=0 or skipped!=START or after!=before
                or value.get('adapter_delta_verified') is not False):
            fail('HOLD_AMP_CALIBRATION_EXACT_ZERO_UPDATE_BASELINE')
    elif (not START<step<=TARGET or start!=START or good<1 or after==before
          or value.get('adapter_delta_verified') is not True):
        fail('HOLD_AMP_CALIBRATION_NO_POSITIVE_OPTIMIZER_PROOF')
    cp=value.get('checkpoint') or {};hashes=cp.get('files_sha256') or {};path=OUTPUT/('checkpoint-'+str(step))
    if (cp.get('path')!=str(path) or cp.get('global_step')!=step
            or set(hashes)!=set(helper.CHECKPOINT_NAMES)
            or any(not re.fullmatch('[a-f0-9]{64}',str(pin)) for pin in hashes.values())):
        fail('HOLD_AMP_CALIBRATION_CHECKPOINT_SCOPE')
    for name,pin in hashes.items():
        if recovery.file_sha(path/name)!=pin:fail('HOLD_AMP_CALIBRATION_CHECKPOINT_HASH')
    if recovery.document(path/'trainer_state.json').get('global_step')!=step:
        fail('HOLD_AMP_CALIBRATION_CHECKPOINT_STEP')
    if json_sha(recovery.document(OUTPUT/'owner_lineage.json'))!=LINEAGE_SHA:
        fail('HOLD_AMP_CALIBRATION_LINEAGE_CHANGED')
    return {'schema':'NOX_OWNER_BOUNDED_OPTIMIZER_PROOF_V1','start_step':start,'global_step':step,
        'successful_optimizer_steps':good,'skipped_optimizer_steps':skipped,'loss':value['loss'],
        'positive_optimizer_updates_verified':not baseline,'adapter_delta_verified':not baseline,
        'lineage_sha256':LINEAGE_SHA,'checkpoint_files_sha256':hashes,'checkpoint_file_count':7,
        'before_tensor_sha256':before,'after_tensor_sha256':after,'merged':False,'quality_gate_passed':False}


def original_evidence(recovery,helper):
    raw=recovery.read(STATE/('owner_maintenance_'+ORIGIN['request']+'.json'))
    if digest(raw)!=ORIGIN['receipt_sha256']:fail('HOLD_AMP_CALIBRATION_ORIGIN_RECEIPT')
    old=json.loads(raw);pointer=recovery.document(POINTER)
    if (old.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or old.get('request')!=ORIGIN['request']
            or old.get('source_sha')!=ORIGIN['source_sha'] or old.get('state')!='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING'
            or old.get('optimizer_steps_verified') is not False or pointer!=old.get('admission')
            or pointer.get('max_steps')!=START or pointer.get('resume') is not False):
        fail('HOLD_AMP_CALIBRATION_ORIGIN_ADMISSION')
    observed_raw=recovery.read(STATE/('owner_maintenance_'+OBSERVATION_REQUEST+'.json'))
    if digest(observed_raw)!=OBSERVATION_SHA:fail('HOLD_AMP_CALIBRATION_FAILURE_OBSERVATION')
    observed=json.loads(observed_raw)
    if (observed.get('state')!='HOLD_TRAINING_RECOVERY_OBSERVATION'
            or observed.get('error')!='HOLD_SINGLE_NATIVE_TRAINER_IDENTITY'
            or observed.get('optimizer_steps_verified') is not False):
        fail('HOLD_AMP_CALIBRATION_FAILURE_SCOPE')
    sources_unchanged(recovery,pointer)
    raw=recovery.read(OUTPUT/'owner_receipt_step_5.json')
    if digest(raw)!=BASELINE_RECEIPT_SHA:fail('HOLD_AMP_CALIBRATION_BASELINE_RECEIPT')
    baseline=json.loads(raw);proof=checkpoint_proof(recovery,helper,baseline,baseline=True)
    entries=list(OUTPUT.iterdir())
    if len(entries)>100 or (OUTPUT/'owner_last_result.json').exists():fail('HOLD_AMP_CALIBRATION_OUTPUT_CHANGED')
    checkpoints=[path for path in entries if path.name.startswith('checkpoint-')]
    if ({path.name for path in checkpoints}!={'checkpoint-1','checkpoint-4','checkpoint-5'}
            or any(path.is_symlink() or not path.is_dir() for path in checkpoints)):
        fail('HOLD_AMP_CALIBRATION_LATEST_CHECKPOINT_CHANGED')
    if recovery.file_sha(OUTPUT/'training_text.jsonl',305243573)!=DATASET_SHA:
        fail('HOLD_AMP_CALIBRATION_CORPUS_CHANGED')
    return old,pointer,baseline,proof


def pending_evidence(recovery,helper,context):
    context_value(context);raw=recovery.read(STATE/('owner_maintenance_'+context['request']+'.json'))
    if digest(raw)!=context['receipt_sha256']:fail('HOLD_AMP_CALIBRATION_PENDING_RECEIPT')
    old=json.loads(raw);pointer=recovery.document(POINTER)
    if (old.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or old.get('request')!=context['request']
            or old.get('source_sha')!=context['source_sha'] or old.get('state')!=PENDING
            or old.get('training_started') is not True or old.get('optimizer_steps_verified') is not False
            or old.get('amp_calibration')!=calibration_metadata() or pointer!=old.get('admission')
            or pointer.get('amp_calibration')!=calibration_metadata()
            or pointer.get('max_steps')!=TARGET or pointer.get('resume') is not True):
        fail('HOLD_AMP_CALIBRATION_PENDING_CONTEXT_CHANGED')
    sources_unchanged(recovery,pointer)
    if recovery.read(WRAPPER)!=wrapper_source(helper,context['request']):fail('HOLD_AMP_CALIBRATION_PENDING_WRAPPER')
    starts=[row['data'].get('process') for row in old.get('steps',[])
            if row.get('kind')=='bounded_calibration_started' and isinstance(row.get('data'),dict)]
    if len(starts)!=1 or not isinstance(starts[0],dict):fail('HOLD_AMP_CALIBRATION_START_IDENTITY')
    return old,pointer,starts[0]


def process_identity(helper,resume,expected=None):
    current=resume.prove_training(helper);row=helper.process(current['pid']);args=row.get('argv',[]) if row else []
    options={key:args[i+1] for i,key in enumerate(args[:-1]) if key in ('--max-steps','--planned-steps','--native-sha')}
    if (options!={'--max-steps':'20','--planned-steps':'1000','--native-sha':NATIVE_SHA}
            or '--resume' not in args or '--recover-unstarted' in args):fail('HOLD_AMP_CALIBRATION_PROCESS_ARGUMENTS')
    if expected and any(current.get(key)!=expected.get(key) for key in ('pid','starttime','cuda','service')):
        fail('HOLD_AMP_CALIBRATION_PROCESS_CHANGED')
    return current


def policy_admission(recovery,helper,resume):
    if resume.global_stop():fail('HOLD_AMP_CALIBRATION_OWNER_STOP')
    policy=recovery.document(STATE/'task_boost_mode.json');resume.verify_policy(policy)
    if policy.get('training_allowed') is not True or policy.get('training_service')!=SERVICE:
        fail('HOLD_AMP_CALIBRATION_TRAINING_PERMISSION')
    if any(helper.service_state(name)['state'] not in resume.STOPPED for name in helper.HEAVY_SERVICES):
        fail('HOLD_AMP_CALIBRATION_HEAVY_SERVICE_ACTIVE')
    if shlex.split(helper.program_config(SERVICE).get('command',''))!=['/bin/bash',str(WRAPPER)]:
        fail('HOLD_AMP_CALIBRATION_SERVICE_COMMAND')


def latch_failure(request):
    path=STATE/'TRAIN_HOLD.flag'
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:return False
    with os.fdopen(fd,'wb') as stream:
        stream.write(('OWNER_AMP_CALIBRATION_FAILED request='+request+'\n').encode());stream.flush();os.fsync(stream.fileno())
    return True


def main(observe_context=None):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_AMP_CALIBRATION_OWNER_CONTEXT')
    if observe_context is None and os.environ.get('NOX_TRAINING_CALIBRATION_CONTEXT'):
        try:observe_context=json.loads(os.environ['NOX_TRAINING_CALIBRATION_CONTEXT'])
        except ValueError:fail('HOLD_AMP_CALIBRATION_CONTEXT')
    if observe_context is not None:context_value(observe_context)
    helper=load('owner_native_repair');resume=load('owner_training_resume');recovery=load('owner_training_recovery_entry')
    disk=load('owner_training_disk_guard')
    path=STATE/('owner_maintenance_'+request+'.json')
    if path.exists():fail('HOLD_AMP_CALIBRATION_REQUEST_USED')
    fd=os.open(STATE/'owner_maintenance.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;success=False;released_hold=False
    result={'schema':'NOX_OWNER_TRAINING_RESUME_V1' if observe_context is None else 'NOX_OWNER_AMP_CALIBRATION_OBSERVATION_V1',
        'request':request,'source_sha':source,'started':time.time(),'state':'AMP_CALIBRATION_PREFLIGHT','steps':[],
        'amp_calibration':calibration_metadata(),'training_started':False,'optimizer_steps_verified':False,
        'weights_deleted':0,'checkpoints_deleted':0,'scaler_reset':False,'optimizer_reset':False,
        'continuation_to_1000_started':False,'observed_admission_context':observe_context}
    identity=None;pointer=None;initial_context=observe_context
    backup=ROOT/'backup/owner_training_amp_calibration'/request
    def save():helper.atomic(path,json.dumps(result,indent=2).encode())
    def event(kind,data):result['steps'].append({'kind':kind,'data':data,'time':time.time()});save();emit(kind,data)
    try:
        save();result['chat_before']=helper.health();policy_admission(recovery,helper,resume)
        if observe_context is None:
            old,pointer,baseline,proof=original_evidence(recovery,helper)
            result.update(admission=pointer,baseline_saved_state=proof)
            hold=STATE/'TRAIN_HOLD.flag';pause=STATE/'TRAIN_PAUSE_REQUEST.flag'
            raw=recovery.read(hold,4096)
            if digest(raw)!=FAILED_HOLD_SHA or raw!=('OWNER_HYBRID_FAILED request='+ORIGIN['request']+'\n').encode():
                fail('HOLD_AMP_CALIBRATION_OWNED_FAILURE_FLAG')
            if pause.exists() or pause.is_symlink():fail('HOLD_AMP_CALIBRATION_FOREIGN_PAUSE')
            event('resource_admission',resume.resource_admission(helper))
            lineage=recovery.document(OUTPUT/'owner_lineage.json');budget=disk.checkpoint_budget(lineage,baseline)
            budget['maximum_additional_checkpoints']=TARGET-START+1
            budget['required_free_bytes']=budget['disk_reserve_bytes']+budget['maximum_additional_checkpoints']*budget['checkpoint_budget_bytes']+256*1024**2
            space=os.statvfs(OUTPUT);budget['free_bytes']=space.f_bavail*space.f_frsize
            event('bounded_calibration_disk_admission',budget)
            if budget['free_bytes']<budget['required_free_bytes']:fail('HOLD_AMP_CALIBRATION_DISK_RESERVE')
            lease=os.open(STATE/'forge_training.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                scaler=load('owner_training_scaler_probe').run_probe(OUTPUT/'checkpoint-5',baseline['checkpoint']['files_sha256'])
            finally:os.close(lease)
            if (scaler.get('state')!='SAVED_ZERO_UPDATE_OPTIMIZER_AND_SCALER_VERIFIED'
                    or scaler.get('optimizer_state_entries')!=0 or scaler.get('files_modified') is not False
                    or scaler.get('cuda_initialized') is not False):fail('HOLD_AMP_CALIBRATION_SAVED_SCALER_PROOF')
            event('saved_optimizer_and_scaler_numeric_projection',scaler)
            policy_admission(recovery,helper,resume)
            if disk.plain(backup).exists():fail('HOLD_AMP_CALIBRATION_BACKUP_COLLISION')
            for item in (WRAPPER,POINTER,hold):helper.atomic(backup/item.name,recovery.read(item))
            wrapper=wrapper_source(helper,request);sources_unchanged(recovery,pointer)
            helper.atomic(WRAPPER,wrapper);os.chmod(WRAPPER,0o755)
            if recovery.read(WRAPPER)!=wrapper or helper.command(['bash','-n',str(WRAPPER)],10)[0]:
                fail('HOLD_AMP_CALIBRATION_WRAPPER_READBACK')
            pointer={**pointer,'request':request,'source_sha':source,'wrapper_request':request,'max_steps':TARGET,'resume':True,
                'amp_calibration':calibration_metadata(),'sources':{**pointer['sources'],str(WRAPPER):digest(wrapper)}}
            result.update(admission=pointer,admitted_sources=pointer['sources']);save()
            helper.atomic(POINTER,json.dumps(pointer,indent=2).encode());sources_unchanged(recovery,pointer)
            policy_admission(recovery,helper,resume);resume.resource_admission(helper)
            if (pause.exists() or pause.is_symlink() or digest(recovery.read(hold,4096))!=FAILED_HOLD_SHA
                    or digest(recovery.read(OUTPUT/'owner_receipt_step_5.json'))!=BASELINE_RECEIPT_SHA):
                fail('HOLD_AMP_CALIBRATION_PRESTART_RACE')
            hold.rename(backup/'released_failed_hold');released_hold=True
            rc,_=helper.command(['supervisorctl','start',SERVICE],35)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                try:identity=process_identity(helper,resume);break
                except RuntimeError:time.sleep(.25)
            if identity is None or helper.service_state()['state'] not in ('RUNNING','STARTING'):
                fail('HOLD_AMP_CALIBRATION_START_FAILED')
            result['training_started']=True;event('bounded_calibration_started',{'max_steps':TARGET,'process':identity,'rc':rc})
        else:
            old,pointer,identity=pending_evidence(recovery,helper,observe_context)
            result.update(admission=pointer,admitted_sources=pointer['sources'],baseline_saved_state=old['baseline_saved_state'])
        fcntl.flock(fd,fcntl.LOCK_UN);locked=False
        result['state']=PENDING;save();deadline=time.monotonic()+430;previous=None
        while time.monotonic()<deadline:
            terminal=OUTPUT/'owner_last_result.json'
            if terminal.exists():
                value=recovery.document(terminal)
                if (value.get('state') not in ('VERIFIED_BOUNDED_ADAPTER_UPDATE','CHECKPOINTED_OWNER_STOP')
                        or value.get('requested_step')!=TARGET):fail('HOLD_AMP_CALIBRATION_TERMINAL_SCOPE')
                proof=checkpoint_proof(recovery,helper,value)
                if value['state']=='VERIFIED_BOUNDED_ADAPTER_UPDATE' and proof['global_step']!=TARGET:
                    fail('HOLD_AMP_CALIBRATION_TARGET_NOT_REACHED')
                result.update(state=VERIFIED if value['state']=='VERIFIED_BOUNDED_ADAPTER_UPDATE' else 'AMP_CALIBRATION_CHECKPOINTED_BY_PAUSE',
                    bounded_update_receipt=value,bounded_optimizer_proof=proof,optimizer_steps_verified=True)
                success=True;break
            process_identity(helper,resume,identity)
            progress=helper.progress()
            if progress!=previous:event('native_calibration_progress',progress);previous=progress
            time.sleep(8)
        if result['state']==PENDING:
            process_identity(helper,resume,identity);success=True
        sources_unchanged(recovery,pointer)
        if recovery.document(POINTER)!=pointer:fail('HOLD_AMP_CALIBRATION_CURRENT_ADMISSION_CHANGED')
    except Exception as exc:
        result.update(state='HOLD_TRAINING_AMP_CALIBRATION',error=safe(exc))
        if locked and released_hold:latch_failure(request)
    finally:
        if locked:fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
        result.update(finished=time.time(),service_after=helper.service_state(),chat_after=helper.health(),gpu_after=helper.gpu(),
            progress_after=helper.progress(),hold_retained=(STATE/'TRAIN_HOLD.flag').exists(),pause_retained=(STATE/'TRAIN_PAUSE_REQUEST.flag').exists())
        if result['chat_after'].get('8081')!=200:result['chat_health_regression']=True;success=False
        save();emit('training_amp_calibration_receipt',result)
        current_context={'request':request,'source_sha':source,'receipt_sha256':digest(recovery.read(path))}
        if initial_context is None:initial_context=current_context
        emit('training_amp_calibration_context',{'context':current_context,'admission_context':initial_context,
            'state':result['state'],'pending_context':initial_context if result['state']==PENDING else None,
            'optimizer_steps_verified':result['optimizer_steps_verified'],'continuation_to_1000_started':False})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_amp_calibration_hold',{'reason':safe(exc)});raise SystemExit(2)
