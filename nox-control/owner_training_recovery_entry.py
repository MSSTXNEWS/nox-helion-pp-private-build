#!/usr/bin/env python3
"""Recover only the verified unstarted run after the TRL config mismatch.

Retains its exact prepared corpus and base, validates the real constructor
before model loading, and uses the existing single Supervisor/optimizer lineage.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
ENTRY=ROOT/'scripts/hybrid_training_entry.py';WRAPPER=ROOT/'scripts/run_train_volta_t866u.sh'
FAILED_REQUEST='6905113544';FAILED_SOURCE='4c1de82ab1e3307de63a7b60639497841cda6d41'
FAILED_HOLD_SHA='6507ac3ebcf242470f91da192db6e73453acd70e31be9d007e5f7e719f8ec759'
PREPARATION_SHA='bc4edf4bccf50c45ef84da51acb975607d0e86199e8c0301b1091121d879989a'
DATASET_BYTES=305243573
HYBRID_BEFORE='54e1707dd25a7128690e90722ced5885a3fcb347b50126e69e3cac216cf6c557'
HYBRID_AFTER='7a384bbee919bec9b24642cc5f56b930cc986065172d7a334cc682c7ee40e455'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
RESUME_SHA='3ea9dd892810255acafac0a188d873e98e16b87c4185466c2e9dd3bce2b0f9bc'
PREFLIGHT_SHA='0f38d420bebd382cdf422381c0ca5028208f15b37527a306057fa9cdd1d01501'
DISK_GUARD_SHA='f2036aa08282d917ea7ad27b533e31f03dd57ade4f49a8ec5b33dfc2f0fc1d58'
SERVICE='nox-train-volta-t866u';POINTER=STATE/'owner_training_admission.json'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def read(path,limit=2*1024*1024):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_RECOVERY_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:fail('HOLD_RECOVERY_FILE_SCOPE')
        value=stream.read(limit+1)
        if len(value)!=info.st_size:fail('HOLD_RECOVERY_FILE_RACE')
        return value
def document(path,limit=2*1024*1024):
    value=json.loads(read(path,limit))
    if not isinstance(value,dict):fail('HOLD_RECOVERY_JSON_SCHEMA')
    return value
def file_sha(path,expected_bytes=None):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_RECOVERY_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);value=hashlib.sha256()
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size>512*1024*1024
                or expected_bytes is not None and before.st_size!=expected_bytes):fail('HOLD_RECOVERY_HASH_SCOPE')
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
        after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        if any(getattr(before,k)!=getattr(after,k) or getattr(after,k)!=getattr(named,k) for k in fields):
            fail('HOLD_RECOVERY_HASH_RACE')
    return value.hexdigest()
def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_RECOVERY_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'))
    sys.modules[name]=module;exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module,raw


def unstarted_output():
    if OUTPUT.is_symlink() or not OUTPUT.is_dir():fail('HOLD_RECOVERY_OUTPUT_SCOPE')
    if {p.name for p in OUTPUT.iterdir()}!={'owner_preparation.json','training_text.jsonl'}:
        fail('HOLD_RECOVERY_HAS_CHECKPOINT_OR_UNKNOWN_ARTIFACT')
    raw=read(OUTPUT/'owner_preparation.json',64000)
    if digest(raw)!=PREPARATION_SHA:fail('HOLD_RECOVERY_PREPARATION_CHANGED')
    prep=json.loads(raw);dataset_sha=prep.get('dataset_sha256')
    if (prep.get('schema')!='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1'
            or prep.get('native_sha256')!='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
            or prep.get('planned_steps')!=1000 or not re.fullmatch('[a-f0-9]{64}',str(dataset_sha))
            or file_sha(OUTPUT/'training_text.jsonl',DATASET_BYTES)!=dataset_sha):
        fail('HOLD_RECOVERY_PREPARED_DATASET_CHANGED')
    return {'preparation_sha256':PREPARATION_SHA,'dataset_sha256':dataset_sha,'dataset_bytes':DATASET_BYTES,
            'checkpoint_count':0,'optimizer_updates_before_recovery':0,'dataset_reused':True,'base_reused':True}


def failed_admission(helper,resume):
    raw=read(STATE/('owner_maintenance_'+FAILED_REQUEST+'.json'));old=json.loads(raw)
    pointer=document(POINTER)
    if (old.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or old.get('request')!=FAILED_REQUEST
            or old.get('source_sha')!=FAILED_SOURCE or old.get('state')!='HOLD_TRAINING_RESUME'
            or old.get('error')!='HOLD_TRAINER_EXITED_WITHOUT_OPTIMIZER_PROOF'
            or old.get('optimizer_steps_verified') is not False or old.get('admission')!=pointer
            or pointer.get('request')!=FAILED_REQUEST or pointer.get('source_sha')!=FAILED_SOURCE
            or pointer.get('max_steps')!=5 or pointer.get('resume') is not False):
        fail('HOLD_RECOVERY_FAILED_ADMISSION_REQUIRED')
    expected=resume.boost_pins(resume.read_json(STATE/('owner_maintenance_'+resume.BOOST_REQUEST+'.json')))
    upgrade,upgrade_chain=resume.dispatcher_upgrade_evidence();expected.update(upgrade)
    memory,memory_chain=resume.s03_activation_evidence(upgrade_chain);expected.update(memory)
    media_chain=resume.media_acceptance_evidence(upgrade_chain,rehash_outputs=True)
    for key,value in (('dispatcher_upgrade',upgrade_chain),('s03_activation',memory_chain),('media_acceptance',media_chain)):
        if old.get(key)!=value or pointer.get(key)!=value:fail('HOLD_RECOVERY_PRIOR_EVIDENCE_CHANGED')
    backup=ROOT/'backup/owner_training_resume'/FAILED_REQUEST
    for path in resume.CONTROLS:
        previous=read(backup/str(path).lstrip('/'))
        if digest(previous)!=expected[path]:fail('HOLD_RECOVERY_CONTROLLER_BACKUP_PIN')
        expected[path]=digest(resume.patch_permission(previous.decode(),path.name=='nox_selfheal.py').encode())
    expected[WRAPPER]=digest(helper.wrapper_source(FAILED_REQUEST).encode())
    if pointer.get('sources')!={str(p):sha for p,sha in expected.items()}:
        fail('HOLD_RECOVERY_FAILED_SOURCE_SET')
    for path,pin in expected.items():
        if digest(read(path))!=pin:fail('HOLD_RECOVERY_CURRENT_SOURCE_CHANGED')
    if expected[ENTRY]!=HYBRID_BEFORE:fail('HOLD_RECOVERY_HYBRID_PREIMAGE')
    return expected,old,{'request':FAILED_REQUEST,'source_sha':FAILED_SOURCE,'receipt_sha256':digest(raw)},upgrade_chain,memory_chain,media_chain


def recovery_wrapper(helper,request):
    source=helper.wrapper_source(request)
    anchor=' --max-steps 5 --planned-steps 1000\n'
    if source.count(anchor)!=1:fail('HOLD_RECOVERY_WRAPPER_ANCHOR')
    return source.replace(anchor,' --max-steps 5 --planned-steps 1000 --recover-unstarted\n',1).encode()


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_RECOVERY_OWNER_CONTEXT')
    helper,_=load('owner_native_repair',HELPER_SHA);resume,_=load('owner_training_resume',RESUME_SHA)
    preflight,_=load('owner_training_config_preflight',PREFLIGHT_SHA)
    disk,_=load('owner_training_disk_guard',DISK_GUARD_SHA)
    hybrid_raw=base64.b64decode(BUNDLE.get('hybrid_training_entry.py',''),validate=True)
    if digest(hybrid_raw)!=HYBRID_AFTER:fail('HOLD_RECOVERY_NEW_HYBRID_PIN')
    compile(hybrid_raw,'hybrid_training_entry.py','exec')
    receipt=STATE/('owner_maintenance_'+request+'.json')
    if receipt.exists():fail('HOLD_RECOVERY_REQUEST_ALREADY_USED')
    fd=os.open(STATE/'owner_maintenance.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;success=False
    result={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':request,'source_sha':source,
            'boost_request':resume.BOOST_REQUEST,'started':time.time(),'state':'RECOVERY_PREFLIGHT','steps':[],
            'training_started':False,'optimizer_steps_verified':False,'weights_deleted':0,'s03_modified':False}
    backup=ROOT/'backup/owner_training_config_recovery'/request;expected={};pointer=None
    def save():helper.atomic(receipt,json.dumps(result,indent=2).encode())
    def event(kind,data):result['steps'].append({'kind':kind,'data':data,'time':time.time()});save();emit(kind,data)
    def publish(max_steps):
        nonlocal pointer
        pointer={'schema':'NOX_OWNER_TRAINING_ADMISSION_V1','request':request,'source_sha':source,
                 'boost_request':resume.BOOST_REQUEST,'wrapper_request':request,'max_steps':max_steps,'resume':max_steps==1000,
                 'dispatcher_upgrade':result['dispatcher_upgrade'],'s03_activation':result['s03_activation'],
                 'media_acceptance':result['media_acceptance'],'unstarted_recovery':result['unstarted_recovery'],
                 'sources':{str(path):sha for path,sha in expected.items()}}
        result['admission']=pointer;result['admitted_sources']=pointer['sources'];save()
        helper.atomic(POINTER,json.dumps(pointer,indent=2).encode())
    def start(max_steps):
        rc,_=helper.command(['supervisorctl','start',SERVICE],35)
        deadline=time.monotonic()+10;identity=None
        while time.monotonic()<deadline:
            try:identity=resume.prove_training(helper);break
            except RuntimeError:time.sleep(.25)
        if identity is None or helper.service_state()['state'] not in ('RUNNING','STARTING'):
            fail('HOLD_RECOVERY_TRAINER_START')
        result['training_started']=True;event('single_native_training_started',{'max_steps':max_steps,'process':identity,'rc':rc})
    try:
        save();expected,old,old_context,upgrade,memory,media=failed_admission(helper,resume)
        result.update(dispatcher_upgrade=upgrade,s03_activation=memory,media_acceptance=media,
                      chat_before=helper.health(),native_workers=resume.worker_readback(helper))
        policy=document(STATE/'task_boost_mode.json',16000);resume.verify_policy(policy)
        if policy.get('training_allowed') is not True or policy.get('training_service')!=SERVICE:
            fail('HOLD_RECOVERY_SINGLE_TRAINER_PERMISSION')
        if any(helper.service_state(name)['state'] not in resume.STOPPED for name in helper.HEAVY_SERVICES):
            fail('HOLD_RECOVERY_LEGACY_SERVICE_ACTIVE')
        if shlex.split(helper.program_config(SERVICE).get('command',''))!=['/bin/bash',str(WRAPPER)]:
            fail('HOLD_RECOVERY_SERVICE_COMMAND')
        hold=read(STATE/'TRAIN_HOLD.flag',4096)
        if digest(hold)!=FAILED_HOLD_SHA or hold!=('OWNER_HYBRID_FAILED request='+FAILED_REQUEST+'\n').encode():
            fail('HOLD_RECOVERY_FAILED_HOLD_CHANGED')
        if (STATE/'TRAIN_PAUSE_REQUEST.flag').exists() or (STATE/'TRAIN_PAUSE_REQUEST.flag').is_symlink():
            fail('HOLD_RECOVERY_OWNER_OR_MEDIA_PAUSE')
        prepared=unstarted_output();event('verified_unstarted_preparation',prepared)
        event('native_resource_admission',resume.resource_admission(helper))
        lease=os.open(STATE/'forge_training.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            config_proof=preflight.run_preflight(hybrid_raw,read(ROOT/'scripts/train_qlora_35b_t866u.py'))
        finally:os.close(lease)
        event('real_constructor_and_serialization_preflight',config_proof)
        result['unstarted_recovery']={**prepared,'failed_admission':old_context,
            'hybrid_before_sha256':HYBRID_BEFORE,'hybrid_after_sha256':HYBRID_AFTER,
            'failure_hold_sha256':FAILED_HOLD_SHA,'configuration_preflight':config_proof}
        for path in (ENTRY,WRAPPER,POINTER,STATE/'TRAIN_HOLD.flag'):
            helper.atomic(backup/path.name,read(path))
        helper.atomic(ENTRY,hybrid_raw);os.chmod(ENTRY,0o755);expected[ENTRY]=HYBRID_AFTER
        wrapper=recovery_wrapper(helper,request);helper.atomic(WRAPPER,wrapper);os.chmod(WRAPPER,0o755)
        expected[WRAPPER]=digest(wrapper)
        if helper.command(['bash','-n',str(WRAPPER)],10)[0]:fail('HOLD_RECOVERY_WRAPPER_SYNTAX')
        for path,pin in expected.items():
            if digest(read(path))!=pin:fail('HOLD_RECOVERY_INSTALLED_READBACK')
        resume.resource_admission(helper)
        if unstarted_output()!=prepared or digest(read(STATE/'TRAIN_HOLD.flag',4096))!=FAILED_HOLD_SHA:
            fail('HOLD_RECOVERY_PREPARATION_RACE')
        publish(5)
        (STATE/'TRAIN_HOLD.flag').rename(backup/'released_failed_hold')
        start(5);fcntl.flock(fd,fcntl.LOCK_UN);locked=False
        result['state']='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING';save()
        deadline=time.monotonic()+430;candidate=None;previous=None
        while time.monotonic()<deadline:
            terminal=OUTPUT/'owner_last_result.json'
            if terminal.is_file():
                candidate=document(terminal)
                if candidate.get('state')=='CHECKPOINTED_OWNER_STOP':
                    resume.verify_paused_result(helper,candidate)
                    result.update(state='TRAINING_CHECKPOINTED_BY_NEW_PAUSE',checkpointed_result=candidate);success=True;break
                helper.verify_five_result(candidate)
                result.update(five_step_receipt=candidate,optimizer_steps_verified=True)
                event('five_steps_independently_verified',{'global_step':5,'loss':candidate['loss'],
                    'successful_optimizer_steps':candidate['successful_optimizer_steps'],
                    'skipped_optimizer_steps':candidate['skipped_optimizer_steps'],'seven_checkpoint_hashes_verified':True});break
            progress=helper.progress()
            if progress!=previous:event('native_training_progress',progress);previous=progress
            if helper.service_state()['state'] in resume.STOPPED:fail('HOLD_RECOVERY_TRAINER_EXITED_WITHOUT_PROOF')
            time.sleep(8)
        if candidate is None:
            resume.prove_training(helper);result['state']='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING';success=True
        elif result['optimizer_steps_verified']:
            deadline=time.monotonic()+40
            while helper.service_state()['state'] in ('RUNNING','STARTING') and time.monotonic()<deadline:time.sleep(1)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
            resume.resource_admission(helper)
            if (STATE/'TRAIN_PAUSE_REQUEST.flag').exists():
                result['state']='FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED';success=True
            else:
                for path,pin in expected.items():
                    if digest(read(path))!=pin:fail('HOLD_RECOVERY_SOURCE_CHANGED_DURING_TRAINING')
                complete=('OWNER_HYBRID_BOUNDED_COMPLETE request='+request+'\n').encode()
                if read(STATE/'TRAIN_HOLD.flag',4096)!=complete:fail('HOLD_RECOVERY_COMPLETION_FLAG')
                lineage=document(OUTPUT/'owner_lineage.json');budget=disk.checkpoint_budget(lineage,candidate)
                free=os.statvfs(OUTPUT);free_bytes=free.f_bavail*free.f_frsize
                event('continuation_checkpoint_disk_admission',{**budget,'free_bytes':free_bytes})
                if free_bytes<budget['required_free_bytes']:
                    result['state']='FIVE_STEPS_VERIFIED_DISK_RESERVE_RETAINED';success=True
                else:
                    data=helper.wrapper_source(request,1000,True).encode()
                    helper.atomic(backup/'first_five_wrapper.sh',read(WRAPPER));helper.atomic(WRAPPER,data);os.chmod(WRAPPER,0o755)
                    expected[WRAPPER]=digest(data);publish(1000)
                    (STATE/'TRAIN_HOLD.flag').rename(backup/'released_five_step_complete_hold')
                    start(1000);result.update(state='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED',continuation_target_steps=1000);success=True
            fcntl.flock(fd,fcntl.LOCK_UN);locked=False
    except Exception as exc:
        result.update(state='HOLD_TRAINING_CONFIG_RECOVERY',error=safe(exc))
        if locked and not (STATE/'TRAIN_HOLD.flag').exists():
            helper.atomic(STATE/'TRAIN_HOLD.flag',('OWNER_TRAINING_CONFIG_RECOVERY_FAILED request='+request+'\n').encode())
    finally:
        if locked:fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
        result.update(finished=time.time(),service_after=helper.service_state(),chat_after=helper.health(),gpu_after=helper.gpu(),
                      progress_after=helper.progress(),hold_retained=(STATE/'TRAIN_HOLD.flag').exists(),
                      pause_retained=(STATE/'TRAIN_PAUSE_REQUEST.flag').exists())
        if result['chat_after'].get('8081')!=200:result['chat_health_regression']=True;success=False
        save();emit('native_training_resume_receipt',result)
        emit('initial_training_context',{'request':request,'source_sha':source,'receipt_sha256':digest(read(receipt)),
             'state':result['state'],'optimizer_steps_verified':result['optimizer_steps_verified']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_config_recovery_hold',{'reason':safe(exc)});raise SystemExit(2)
