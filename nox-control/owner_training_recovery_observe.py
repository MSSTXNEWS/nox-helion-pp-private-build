#!/usr/bin/env python3
"""Observe a sealed pending recovery and continue only its verified first five.

Never launches or repeats initial training. A new operator request supplies the
exact immutable pending receipt context, observes that same process, and may
admit continuation of its independently verified seven-file checkpoint.
"""
import base64
import fcntl
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
ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
RECOVERY_SHA='7884571d05a9df7d20fb71dfe8e58feabd4941eeec23534f5ec0e2b28c502854'
SERVICE='nox-train-volta-t866u'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load_recovery():
    raw=base64.b64decode(BUNDLE.get('owner_training_recovery_entry.py',''),validate=True)
    if digest(raw)!=RECOVERY_SHA:fail('HOLD_RECOVERY_OBSERVE_SOURCE')
    module=types.ModuleType('owner_training_recovery_entry');sys.modules[module.__name__]=module
    exec(compile(raw,'<pinned-recovery-entry>','exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module


def pending_evidence(recovery,context):
    if (not isinstance(context,dict) or set(context)!={'request','source_sha','receipt_sha256'}
            or not str(context.get('request','')).isdigit()
            or not re.fullmatch('[a-f0-9]{40}',str(context.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(context.get('receipt_sha256','')))):
        fail('HOLD_RECOVERY_OBSERVE_CONTEXT')
    raw=recovery.read(STATE/('owner_maintenance_'+context['request']+'.json'))
    if digest(raw)!=context['receipt_sha256']:fail('HOLD_RECOVERY_OBSERVE_RECEIPT_PIN')
    previous=json.loads(raw);pointer=recovery.document(STATE/'owner_training_admission.json')
    owned=previous.get('unstarted_recovery') or {};config=owned.get('configuration_preflight') or {}
    if (previous.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1'
            or previous.get('request')!=context['request'] or previous.get('source_sha')!=context['source_sha']
            or previous.get('state')!='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING'
            or previous.get('training_started') is not True or previous.get('optimizer_steps_verified') is not False
            or previous.get('admission')!=pointer or pointer.get('request')!=context['request']
            or pointer.get('source_sha')!=context['source_sha'] or pointer.get('max_steps')!=5 or pointer.get('resume') is not False
            or owned.get('hybrid_before_sha256')!=recovery.HYBRID_BEFORE
            or owned.get('hybrid_after_sha256')!=recovery.HYBRID_AFTER
            or owned.get('preparation_sha256')!=recovery.PREPARATION_SHA
            or owned.get('dataset_bytes')!=recovery.DATASET_BYTES
            or (owned.get('failed_admission') or {}).get('request')!=recovery.FAILED_REQUEST
            or (owned.get('failed_admission') or {}).get('source_sha')!=recovery.FAILED_SOURCE
            or config.get('state')!='INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED'
            or config.get('hybrid_sha256')!=recovery.HYBRID_AFTER):
        fail('HOLD_RECOVERY_OBSERVE_PENDING_REQUIRED')
    sources=pointer.get('sources') or {}
    if not isinstance(sources,dict) or len(sources)!=20 or sources.get(str(recovery.ENTRY))!=recovery.HYBRID_AFTER:
        fail('HOLD_RECOVERY_OBSERVE_SOURCE_SET')
    for path,pin in sources.items():
        if not re.fullmatch('[a-f0-9]{64}',str(pin)) or digest(recovery.read(path))!=pin:
            fail('HOLD_RECOVERY_OBSERVE_SOURCE_CHANGED')
    starts=[row.get('data') or {} for row in previous.get('steps',[]) if row.get('kind')=='single_native_training_started']
    if len(starts)!=1 or starts[0].get('max_steps')!=5 or not isinstance(starts[0].get('process'),dict):
        fail('HOLD_RECOVERY_OBSERVE_PROCESS_PROOF')
    return previous,pointer,starts[0]['process']


def same_initial_process(helper,resume,identity):
    current=resume.prove_training(helper)
    if any(current.get(key)!=identity.get(key) for key in ('pid','starttime','cuda','service')):
        fail('HOLD_RECOVERY_OBSERVE_PROCESS_CHANGED')
    row=helper.process(current['pid']);args=row.get('argv',[]) if row else []
    options={key:args[i+1] for i,key in enumerate(args[:-1]) if key in ('--max-steps','--planned-steps','--native-sha')}
    if options!={'--max-steps':'5','--planned-steps':'1000','--native-sha':resume.NATIVE_SHA} or '--recover-unstarted' not in args or '--resume' in args:
        fail('HOLD_RECOVERY_OBSERVE_PROCESS_ARGUMENTS')
    return current


def main(initial_context=None):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_RECOVERY_OBSERVE_OWNER_CONTEXT')
    if initial_context is None:
        try:initial_context=json.loads(os.environ.get('NOX_TRAINING_RECOVERY_CONTEXT',''))
        except ValueError:fail('HOLD_RECOVERY_OBSERVE_CONTEXT')
    recovery=load_recovery();helper,_=recovery.load('owner_native_repair',recovery.HELPER_SHA)
    resume,_=recovery.load('owner_training_resume',recovery.RESUME_SHA)
    disk,_=recovery.load('owner_training_disk_guard',recovery.DISK_GUARD_SHA)
    path=STATE/('owner_maintenance_'+request+'.json')
    if path.exists():fail('HOLD_RECOVERY_OBSERVE_REQUEST_USED')
    fd=os.open(STATE/'owner_maintenance.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;success=False
    result={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':request,'source_sha':source,
            'started':time.time(),'steps':[],'training_started':False,'optimizer_steps_verified':False,
            'weights_deleted':0,'s03_modified':False,'observed_initial_admission':initial_context}
    def save():helper.atomic(path,json.dumps(result,indent=2).encode())
    def event(kind,data):result['steps'].append({'kind':kind,'data':data,'time':time.time()});save();emit(kind,data)
    try:
        previous,pointer,identity=pending_evidence(recovery,initial_context)
        for key in ('boost_request','dispatcher_upgrade','s03_activation','media_acceptance','unstarted_recovery','admission'):
            result[key]=previous[key]
        result['admitted_sources']=pointer['sources'];result['chat_before']=helper.health()
        policy=recovery.document(STATE/'task_boost_mode.json');resume.verify_policy(policy)
        if policy.get('training_allowed') is not True or policy.get('training_service')!=SERVICE:
            fail('HOLD_RECOVERY_OBSERVE_PERMISSION')
        if any(helper.service_state(name)['state'] not in resume.STOPPED for name in helper.HEAVY_SERVICES):
            fail('HOLD_RECOVERY_OBSERVE_LEGACY_SERVICE')
        terminal=OUTPUT/'owner_last_result.json'
        if not terminal.exists():same_initial_process(helper,resume,identity)
        fcntl.flock(fd,fcntl.LOCK_UN);locked=False
        result['state']='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING';save()
        deadline=time.monotonic()+430;candidate=None;last=None
        while time.monotonic()<deadline:
            if terminal.exists():
                candidate=recovery.document(terminal)
                if candidate.get('state')=='CHECKPOINTED_OWNER_STOP':
                    resume.verify_paused_result(helper,candidate)
                    result.update(state='TRAINING_CHECKPOINTED_BY_NEW_PAUSE',checkpointed_result=candidate);success=True;break
                helper.verify_five_result(candidate)
                result.update(five_step_receipt=candidate,optimizer_steps_verified=True)
                event('five_steps_independently_verified',{'global_step':5,'loss':candidate['loss'],
                    'successful_optimizer_steps':candidate['successful_optimizer_steps'],
                    'skipped_optimizer_steps':candidate['skipped_optimizer_steps'],'seven_checkpoint_hashes_verified':True});break
            same_initial_process(helper,resume,identity)
            current=helper.progress()
            if current!=last:event('native_training_progress',current);last=current
            time.sleep(8)
        if candidate is None:
            same_initial_process(helper,resume,identity);success=True
        elif result['optimizer_steps_verified']:
            deadline=time.monotonic()+40
            while helper.service_state()['state'] in ('RUNNING','STARTING') and time.monotonic()<deadline:time.sleep(1)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
            pending_evidence(recovery,initial_context);resume.resource_admission(helper)
            if (STATE/'TRAIN_PAUSE_REQUEST.flag').exists():
                result['state']='FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED';success=True
            else:
                complete=('OWNER_HYBRID_BOUNDED_COMPLETE request='+initial_context['request']+'\n').encode()
                if recovery.read(STATE/'TRAIN_HOLD.flag',4096)!=complete:fail('HOLD_RECOVERY_OBSERVE_COMPLETION_FLAG')
                budget=disk.checkpoint_budget(recovery.document(OUTPUT/'owner_lineage.json'),candidate)
                space=os.statvfs(OUTPUT);free=space.f_bavail*space.f_frsize
                event('continuation_checkpoint_disk_admission',{**budget,'free_bytes':free})
                if free<budget['required_free_bytes']:
                    result['state']='FIVE_STEPS_VERIFIED_DISK_RESERVE_RETAINED';success=True
                else:
                    backup=ROOT/'backup/owner_training_recovery_observe'/request
                    helper.atomic(backup/'first_five_wrapper.sh',recovery.read(recovery.WRAPPER))
                    helper.atomic(backup/'first_five_admission.json',recovery.read(recovery.POINTER))
                    data=helper.wrapper_source(request,1000,True).encode()
                    helper.atomic(recovery.WRAPPER,data);os.chmod(recovery.WRAPPER,0o755)
                    if digest(recovery.read(recovery.WRAPPER))!=digest(data) or helper.command(['bash','-n',str(recovery.WRAPPER)],10)[0]:
                        fail('HOLD_RECOVERY_OBSERVE_WRAPPER_READBACK')
                    pointer={**pointer,'request':request,'source_sha':source,'wrapper_request':request,'max_steps':1000,'resume':True,
                        'observed_initial_admission':initial_context,'sources':{**pointer['sources'],str(recovery.WRAPPER):digest(data)}}
                    result['admission']=pointer;result['admitted_sources']=pointer['sources'];save()
                    helper.atomic(recovery.POINTER,json.dumps(pointer,indent=2).encode())
                    (STATE/'TRAIN_HOLD.flag').rename(backup/'released_five_step_complete_hold')
                    rc,_=helper.command(['supervisorctl','start',SERVICE],35)
                    deadline=time.monotonic()+10;started=None
                    while time.monotonic()<deadline:
                        try:started=resume.prove_training(helper);break
                        except RuntimeError:time.sleep(.25)
                    if started is None or helper.service_state()['state'] not in ('RUNNING','STARTING'):
                        fail('HOLD_RECOVERY_OBSERVE_CONTINUATION_START')
                    event('single_native_training_started',{'max_steps':1000,'process':started,'rc':rc})
                    result.update(state='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED',continuation_target_steps=1000,training_started=True);success=True
            fcntl.flock(fd,fcntl.LOCK_UN);locked=False
    except Exception as exc:
        result.update(state='HOLD_TRAINING_RECOVERY_OBSERVATION',error=safe(exc))
        if locked and not (STATE/'TRAIN_HOLD.flag').exists() and result.get('optimizer_steps_verified'):
            helper.atomic(STATE/'TRAIN_HOLD.flag',('OWNER_TRAINING_RECOVERY_OBSERVATION_FAILED request='+request+'\n').encode())
    finally:
        if locked:fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
        result.update(finished=time.time(),service_after=helper.service_state(),chat_after=helper.health(),gpu_after=helper.gpu(),
                      progress_after=helper.progress(),hold_retained=(STATE/'TRAIN_HOLD.flag').exists(),
                      pause_retained=(STATE/'TRAIN_PAUSE_REQUEST.flag').exists())
        if result['chat_after'].get('8081')!=200:result['chat_health_regression']=True;success=False
        save();emit('native_training_resume_receipt',result)
        emit('initial_training_context',{'request':request,'source_sha':source,'receipt_sha256':digest(recovery.read(path)),
            'state':result['state'],'optimizer_steps_verified':result['optimizer_steps_verified']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_recovery_observation_hold',{'reason':safe(exc)});raise SystemExit(2)
