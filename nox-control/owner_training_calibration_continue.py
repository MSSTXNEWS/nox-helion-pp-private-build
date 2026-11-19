#!/usr/bin/env python3
"""Admit one generic positive calibration checkpoint to the existing1000 run.

The positive bounded proof, zero-update baseline, and all original receipts
remain distinct and immutable. Guard installation has its own receipt; a guard
failure requests a checkpoint pause instead of leaving an unprotected run.
"""
import base64
import fcntl
import hashlib
import json
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
OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid';WRAPPER=SCRIPTS/'run_train_volta_t866u.sh'
POINTER=STATE/'owner_training_admission.json';SERVICE='nox-train-volta-t866u'
EXTERNAL_STOP=Path('/workspace/NOX_STOP')
PINS={'owner_native_repair':'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
      'owner_training_resume':'3ea9dd892810255acafac0a188d873e98e16b87c4185466c2e9dd3bce2b0f9bc',
      'owner_training_disk_guard':'9fab629c442e572f89dac9f078e43d505c7d93c9feb94ebc34182c56ca5b94e8',
      'owner_training_recovery_chain':'c4ed149ca4d5164ac7b9670c82f97c9eaaa65356cfdfcf911a0d88171d7098fa',
      'owner_training_calibration_proof':'e8a804a0e9450f4c69aa04c6b8d3daa7feecfa75b934343d13459b3ade30a63d',
      'owner_training_calibration_guard':'a6db1e6ec25db95ccf2de976538fb450e65e9dd8ee97990ed757588b2155d27c',
      'owner_training_calibration_guard_entry':'46c1d2a0843b463531e2be63df9c816297dc847ffd69dd2dee4c39e75f83977a'}
INSTALL_NAMES=('owner_training_calibration_proof','owner_training_calibration_guard','owner_training_disk_guard')


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def bundled(name):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=PINS[name]:fail('HOLD_CALIBRATED_CONTINUATION_BUNDLE_PIN')
    return raw
def load(name):
    raw=bundled(name);module=types.ModuleType(name);module.__file__=str(SCRIPTS/(name+'.py'));sys.modules[name]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module
def latch_hold(request):
    try:fd=os.open(STATE/'TRAIN_HOLD.flag',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:return False
    with os.fdopen(fd,'wb') as stream:
        stream.write(('OWNER_CALIBRATED_CONTINUATION_FAILED request='+request+'\n').encode());stream.flush();os.fsync(stream.fileno())
    directory=os.open(STATE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return True


def global_stop():
    return any(path.exists() or path.is_symlink() for path in
        (ROOT/'STOP',ROOT/'STOP.flag',ROOT/'stop.flag',ROOT/'.stop',ROOT/'program/STOP',STATE/'STOP',EXTERNAL_STOP))


def policy(proof,helper,resume):
    if global_stop():fail('HOLD_CALIBRATED_CONTINUATION_OWNER_STOP')
    value=proof.document(STATE/'task_boost_mode.json',16384);resume.verify_policy(value)
    if value.get('training_allowed') is not True or value.get('training_service')!=SERVICE:
        fail('HOLD_CALIBRATED_CONTINUATION_PERMISSION')
    if any(helper.service_state(name)['state'] not in resume.STOPPED for name in helper.HEAVY_SERVICES):
        fail('HOLD_CALIBRATED_CONTINUATION_HEAVY_SERVICE')
    if shlex.split(helper.program_config(SERVICE).get('command',''))!=['/bin/bash',str(WRAPPER)]:
        fail('HOLD_CALIBRATED_CONTINUATION_SERVICE_COMMAND')


def latest_matches(proof,value):
    paths=list(OUTPUT.iterdir())
    if len(paths)>2048:fail('HOLD_CALIBRATED_CONTINUATION_OUTPUT_BOUND')
    steps=[]
    for path in paths:
        if not path.name.startswith('checkpoint-'):continue
        match=re.fullmatch('checkpoint-([0-9]{1,4})',path.name)
        if not match or path.is_symlink() or not path.is_dir():fail('HOLD_CALIBRATED_CONTINUATION_CHECKPOINT_PATH')
        steps.append(int(match[1]))
    if not steps or max(steps)!=value['global_step']:fail('HOLD_CALIBRATED_CONTINUATION_NEWER_CHECKPOINT')
    if proof.json_sha(proof.document(OUTPUT/'owner_last_result.json'))!=proof.json_sha(value):
        fail('HOLD_CALIBRATED_CONTINUATION_TERMINAL_CHANGED')


def prepare_modules(proof,helper,backup):
    result={}
    for name in INSTALL_NAMES:
        raw=bundled(name);path=proof.plain(SCRIPTS/(name+'.py'));compile(raw,str(path),'exec')
        if path.exists():
            if digest(proof.read(path))!=PINS[name]:fail('HOLD_CALIBRATED_CONTINUATION_MODULE_CONFLICT')
        else:
            helper.atomic(path,raw);os.chmod(path,0o644)
        if digest(proof.read(path))!=PINS[name]:fail('HOLD_CALIBRATED_CONTINUATION_MODULE_READBACK')
        result[name]=PINS[name]
    return result


def admit(context,request,source):
    proof=load('owner_training_calibration_proof');helper=load('owner_native_repair')
    resume=load('owner_training_resume');guard=load('owner_training_calibration_guard');base_guard=load('owner_training_disk_guard')
    proof.context_value(context)
    path=STATE/('owner_maintenance_'+request+'.json')
    if path.exists():fail('HOLD_CALIBRATED_CONTINUATION_REQUEST_USED')
    fd=os.open(proof.plain(STATE/'owner_maintenance.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);released=False;success=False
    result={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':request,'source_sha':source,'started':time.time(),
        'state':'CALIBRATED_CONTINUATION_PREFLIGHT','steps':[],'training_started':False,'optimizer_steps_verified':False,
        'scaler_reset':False,'optimizer_reset':False,'weights_deleted':0,'checkpoints_deleted':0,
        'verified_calibration_context':context,'source_files_modified':[]}
    backup=ROOT/'backup/owner_calibrated_continuation'/request
    def save():helper.atomic(path,json.dumps(result,indent=2).encode())
    def event(kind,data):result['steps'].append({'kind':kind,'data':data,'time':time.time()});save();emit(kind,data)
    try:
        save();policy(proof,helper,resume)
        previous,old_pointer,lineage,value,witness=proof.calibration_evidence(context,require_current=True,rehash=True)
        latest_matches(proof,value)
        result.update(calibration_evidence=witness,bounded_update_receipt=value,optimizer_steps_verified=True,
            admitted_sources=old_pointer['sources'],admission=old_pointer,chat_before=helper.health())
        for key in ('boost_request','dispatcher_upgrade','s03_activation','media_acceptance'):
            if key in old_pointer:result[key]=old_pointer[key]
        pause=STATE/'TRAIN_PAUSE_REQUEST.flag';hold=STATE/'TRAIN_HOLD.flag'
        if pause.exists() or pause.is_symlink():
            result['state']='CALIBRATION_VERIFIED_OWNER_PAUSE_RETAINED';success=True
        else:
            deadline=time.monotonic()+40
            while helper.service_state()['state'] in ('RUNNING','STARTING') and time.monotonic()<deadline:
                if global_stop():fail('HOLD_CALIBRATED_CONTINUATION_OWNER_STOP')
                time.sleep(1)
            event('native_resource_admission',resume.resource_admission(helper))
            expected_hold=('OWNER_HYBRID_BOUNDED_COMPLETE request='+old_pointer['wrapper_request']+'\n').encode()
            if proof.read(hold,4096)!=expected_hold:fail('HOLD_CALIBRATED_CONTINUATION_COMPLETION_FLAG')
            budget=guard.budget_for(lineage,value,base_guard,proof);space=os.statvfs(OUTPUT)
            budget['free_bytes']=space.f_bavail*space.f_frsize;event('continuation_checkpoint_disk_admission',budget)
            if budget['free_bytes']<budget['required_free_bytes']:
                result['state']='CALIBRATION_VERIFIED_DISK_RESERVE_RETAINED';success=True
            else:
                if proof.plain(backup).exists():fail('HOLD_CALIBRATED_CONTINUATION_BACKUP_COLLISION')
                for file in (WRAPPER,POINTER,hold):helper.atomic(backup/file.name,proof.read(file))
                policy(proof,helper,resume)
                modules=prepare_modules(proof,helper,backup)
                wrapper=helper.wrapper_source(request,1000,True).encode()
                proof.sources(old_pointer);helper.atomic(WRAPPER,wrapper);os.chmod(WRAPPER,0o755)
                if proof.read(WRAPPER)!=wrapper or helper.command(['bash','-n',str(WRAPPER)],10)[0]:
                    fail('HOLD_CALIBRATED_CONTINUATION_WRAPPER_READBACK')
                pointer={k:v for k,v in old_pointer.items() if k!='amp_calibration'}
                pointer.update(request=request,source_sha=source,wrapper_request=request,max_steps=1000,resume=True,
                    calibration_evidence=witness,continuation_modules=modules,
                    sources={**old_pointer['sources'],str(WRAPPER):digest(wrapper)})
                result.update(admission=pointer,admitted_sources=pointer['sources'],continuation_modules=modules,
                    source_files_modified=[str(WRAPPER)])
                save();helper.atomic(POINTER,json.dumps(pointer,indent=2).encode());proof.sources(pointer)
                policy(proof,helper,resume);resume.resource_admission(helper);latest_matches(proof,value)
                if global_stop() or pause.exists() or pause.is_symlink() or proof.read(hold,4096)!=expected_hold:
                    fail('HOLD_CALIBRATED_CONTINUATION_PRESTART_FLAG_RACE')
                hold.rename(backup/'released_calibration_completion_hold');released=True
                rc,_=helper.command(['supervisorctl','start',SERVICE],35)
                end=time.monotonic()+10;identity=None
                while time.monotonic()<end:
                    try:
                        identity=base_guard.trainer_process()
                        if identity is not None:break
                    except RuntimeError:pass
                    time.sleep(.25)
                if identity is None or helper.service_state()['state'] not in ('RUNNING','STARTING'):
                    fail('HOLD_CALIBRATED_CONTINUATION_START')
                event('single_native_training_started',{'max_steps':1000,'process':identity,'rc':rc,
                    'resume_checkpoint_global_step':value['global_step'],'planned_steps':1000})
                result.update(state=proof.STATE_STARTED,training_started=True,continuation_target_steps=1000)
                success=True
    except Exception as exc:
        result.update(state='HOLD_CALIBRATED_CONTINUATION',error=safe(exc))
        if released:latch_hold(request)
    finally:
        result.update(finished=time.time(),service_after=helper.service_state(),chat_after=helper.health(),
            gpu_after=helper.gpu(),progress_after=helper.progress(),hold_retained=(STATE/'TRAIN_HOLD.flag').exists(),
            pause_retained=(STATE/'TRAIN_PAUSE_REQUEST.flag').exists())
        if result['chat_after'].get('8081')!=200:
            result.update(chat_health_regression=True,state='HOLD_CALIBRATED_CONTINUATION_CHAT_HEALTH');success=False
            if released:latch_hold(request)
        save();fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        emit('native_calibrated_continuation_receipt',result)
    sealed_context={'request':request,'source_sha':source,'receipt_sha256':digest(proof.read(path))}
    return result,sealed_context,success


def main(context=None):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch('[0-9]{1,24}',request) or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_CALIBRATED_CONTINUATION_OWNER_CONTEXT')
    if context is None:
        try:context=json.loads(os.environ.get('NOX_VERIFIED_CALIBRATION_CONTEXT',''))
        except ValueError:fail('HOLD_CALIBRATED_CONTINUATION_POSITIVE_CONTEXT')
    proof=load('owner_training_calibration_proof');proof.context_value(context)
    helper=load('owner_native_repair');chain=load('owner_training_recovery_chain');chain.GUARD_SHA=PINS['owner_training_calibration_guard']
    installer=load('owner_training_calibration_guard_entry');guard=load('owner_training_calibration_guard')
    path=STATE/('owner_calibrated_continuation_chain_'+request+'.json')
    if path.exists():fail('HOLD_CALIBRATED_CONTINUATION_CHAIN_REQUEST_USED')
    record={'schema':'NOX_OWNER_CALIBRATED_CONTINUATION_CHAIN_V1','request':request,'source_sha':source,
        'started_at':time.time(),'state':'PREFLIGHT','calibration_context':context,'stages':[],
        'trainer_killed':False,'checkpoints_deleted':0,'weights_deleted':0,'initial_admission':None,
        'continuation_started':False,'current_admission_context':None}
    success=False
    def save():helper.atomic(path,json.dumps(record,indent=2).encode())
    try:
        reservation=proof.read(STATE/'train_wants_gpu1',4096);record['teacher_reservation_sha256']=digest(reservation);save()
        native,initial,ok=admit(context,request,source);record['attempt_context']=initial
        current=proof.document(POINTER)
        if (current==native.get('admission') and current.get('request')==initial['request']
                and current.get('source_sha')==initial['source_sha']):record['current_admission_context']=initial
        else:
            prior=(native.get('calibration_evidence') or {}).get('calibration_admission_context')
            if prior and current.get('request')==prior.get('request') and current.get('source_sha')==prior.get('source_sha'):
                record['current_admission_context']=prior
        if native['state']==proof.STATE_STARTED:
            record['initial_admission']=initial;record['continuation_started']=True
            starts=[row['data'].get('process') for row in native.get('steps',[])
                    if row.get('kind')=='single_native_training_started' and isinstance(row.get('data'),dict)]
            if len(starts)!=1 or not isinstance(starts[0],dict):fail('HOLD_CALIBRATED_CONTINUATION_STARTED_PROCESS_PROOF')
            record['continuation_process_started']=starts[0]
        record['stages'].append({'stage':'GENERIC_CALIBRATED_ADMISSION','state':native['state'],
            'optimizer_steps_verified':native['optimizer_steps_verified']})
        if proof.read(STATE/'train_wants_gpu1',4096)!=reservation:
            if native['state']==proof.STATE_STARTED:record['checkpoint_pause']=chain.pause_unprotected(guard,initial)
            fail('HOLD_CALIBRATED_CONTINUATION_RESERVATION_CHANGED')
        if not ok:record['state']='CALIBRATED_CONTINUATION_HELD'
        elif native['state']==proof.STATE_STARTED:
            stage,success=chain.install_guard_or_pause(proof,installer,guard,initial)
            record['stages'].append({'stage':'GENERIC_DISK_GUARD',**stage})
            record['state']='GENERIC_POSITIVE_PROOF_AND_GUARDED_CONTINUATION_VERIFIED' if success else 'CALIBRATED_CONTINUATION_GUARD_PENDING_CHECKPOINT_PAUSE'
        else:record['state']=native['state'];success=True
    except Exception as exc:record.update(state='HOLD_CALIBRATED_CONTINUATION_CHAIN',reason=safe(exc))
    finally:
        record.update(finished_at=time.time(),service_after=helper.service_state(),chat_after=helper.health())
        if record['continuation_started']:
            try:
                current=guard.trainer_process();record['continuation_process_after']=current
                record['continuation_running_at_end']=(current is not None
                    and current==record.get('continuation_process_started')
                    and record['service_after']['state'] in ('RUNNING','STARTING'))
            except Exception as exc:
                record.update(continuation_running_at_end=False,continuation_observation_reason=safe(exc))
            if success and not record['continuation_running_at_end']:
                record['state']='GENERIC_GUARD_VERIFIED_CONTINUATION_NOT_RUNNING';success=False
        save()
        emit('calibrated_continuation_chain',record)
        emit('calibrated_continuation_context',{'request':request,'source_sha':source,'receipt_sha256':digest(proof.read(path)),
            'state':record['state'],'initial_admission':record['initial_admission'],
            'current_admission_context':record['current_admission_context'],'continuation_started':record['continuation_started']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('calibrated_continuation_hold',{'reason':safe(exc)});raise SystemExit(2)
