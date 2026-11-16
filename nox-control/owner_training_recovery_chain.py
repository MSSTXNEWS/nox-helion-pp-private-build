#!/usr/bin/env python3
"""One finite owner action: verified config recovery, then native disk guard.

The initial recovery receipt is sealed before guard installation and is never
rewritten afterwards. If that guard cannot be verified, the exact admitted
continuation receives only a checkpoint-aware pause request.
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
ROOT=Path('/root/nox');STATE=ROOT/'state'
RECOVERY_SHA='7884571d05a9df7d20fb71dfe8e58feabd4941eeec23534f5ec0e2b28c502854'
GUARD_INSTALL_SHA='59ea8ac37bdec4c990950aeef9c4ab7283f633cb300ee6384007111efd06d86c'
GUARD_SHA='f2036aa08282d917ea7ad27b533e31f03dd57ade4f49a8ec5b33dfc2f0fc1d58'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_RECOVERY_CHAIN_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'));sys.modules[name]=module
    exec(compile(raw,module.__file__,'exec'),module.__dict__);module.BUNDLE=BUNDLE
    return module


def sealed_result(recovery,request,source):
    raw=recovery.read(STATE/('owner_maintenance_'+request+'.json'))
    value=json.loads(raw)
    if (value.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or value.get('request')!=request
            or value.get('source_sha')!=source):fail('HOLD_RECOVERY_CHAIN_RESULT_CONTEXT')
    return value,{'request':request,'source_sha':source,'receipt_sha256':digest(raw)}


def pause_unprotected(guard,context):
    """A verified continuation may yield; no uncheckpointed process is killed."""
    fd=os.open(guard.plain(STATE/'owner_maintenance.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        deadline=time.monotonic()+5
        while True:
            try:fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:fail('HOLD_RECOVERY_CHAIN_PAUSE_MAINTENANCE_BUSY')
                time.sleep(.1)
        guard.admission(context);process=guard.trainer_process()
        if process is None:return {'state':'ADMITTED_TRAINER_NOT_RUNNING','pause_created':False}
        path=guard.plain(STATE/'TRAIN_PAUSE_REQUEST.flag')
        if path.exists():return {'state':'EXISTING_PAUSE_RETAINED','pause_created':False,'process':process}
        if guard.trainer_process()!=process:fail('HOLD_RECOVERY_CHAIN_PAUSE_PROCESS_CHANGED')
        payload=('OWNER_DISK_GUARD_UNAVAILABLE request='+context['request']+' source='+context['source_sha']+'\n').encode()
        try:flag=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:return {'state':'EXISTING_PAUSE_RETAINED','pause_created':False,'process':process}
        with os.fdopen(flag,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
        return {'state':'CHECKPOINT_PAUSE_REQUESTED_GUARD_UNVERIFIED','pause_created':True,'process':process,
                'pause_sha256':digest(payload),'checkpoint_completion_verified':False}
    finally:os.close(fd)


def install_guard_or_pause(recovery,installer,guard,context):
    try:
        rc=installer.main(context)
        record=recovery.document(STATE/('owner_training_disk_guard_install_'+os.environ['NOX_OWNER_REQUEST_ID']+'.json'))
        if (rc!=0 or record.get('state')!='EXISTING_PRIORITY_DISK_GUARD_VERIFIED'
                or record.get('initial_admission')!=context or record.get('guard_source_sha256')!=GUARD_SHA):
            fail('HOLD_RECOVERY_CHAIN_NATIVE_GUARD_NOT_VERIFIED')
        return {'state':'NATIVE_DISK_GUARD_VERIFIED','native_state':record['state'],
                'scheduler_after_sha256':record['scheduler_after_sha256'],'native_observation':record['native_observation']},True
    except Exception as exc:
        result={'state':'GUARD_UNVERIFIED','reason':safe(exc)}
        try:result['checkpoint_pause']=pause_unprotected(guard,context)
        except Exception as pause_exc:result['checkpoint_pause']={'state':'PAUSE_NOT_CONFIRMED','reason':safe(pause_exc)}
        return result,False


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_RECOVERY_CHAIN_OWNER_CONTEXT')
    recovery=load('owner_training_recovery_entry',RECOVERY_SHA)
    installer=load('owner_training_disk_guard_entry',GUARD_INSTALL_SHA)
    guard=load('owner_training_disk_guard',GUARD_SHA)
    helper,_=recovery.load('owner_native_repair',recovery.HELPER_SHA)
    receipt=STATE/('owner_training_recovery_chain_'+request+'.json')
    if receipt.exists():fail('HOLD_RECOVERY_CHAIN_REQUEST_USED')
    record={'schema':'NOX_OWNER_TRAINING_RECOVERY_CHAIN_V1','request':request,'source_sha':source,
            'started_at':time.time(),'state':'PREFLIGHT','initial_admission':None,'stages':[],
            'trainer_killed':False,'checkpoints_deleted':0,'weights_deleted':0}
    def save():helper.atomic(receipt,json.dumps(record,indent=2).encode())
    success=False
    try:
        # The original admission reserved GPU1 from legacy teacher restart.
        # It is retained throughout recovery and never recreated from guessing.
        reservation=recovery.read(STATE/'train_wants_gpu1',4096)
        record['teacher_reservation_sha256']=digest(reservation);save()
        rc=recovery.main()
        native,context=sealed_result(recovery,request,source)
        record['initial_admission']=context
        record['stages'].append({'stage':'CONFIG_RECOVERY','returncode':rc,'state':native.get('state'),
            'optimizer_steps_verified':native.get('optimizer_steps_verified')})
        if recovery.read(STATE/'train_wants_gpu1',4096)!=reservation:
            if native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':
                record['checkpoint_pause']=pause_unprotected(guard,context)
            fail('HOLD_RECOVERY_CHAIN_TEACHER_RESERVATION_CHANGED')
        if rc!=0:
            record['state']='RECOVERY_HELD';success=False
        elif native.get('state')=='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED':
            stage,success=install_guard_or_pause(recovery,installer,guard,context);record['stages'].append({'stage':'DISK_GUARD',**stage})
            record['state']='FIVE_STEPS_AND_GUARDED_CONTINUATION_VERIFIED' if success else 'FIVE_STEPS_VERIFIED_GUARD_PENDING_CHECKPOINT_PAUSE'
        elif native.get('state')=='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING':
            record['state']='INITIAL_TRAINING_RUNNING_PROOF_PENDING';record['observation_context']=context;success=True
        elif native.get('state') in ('TRAINING_CHECKPOINTED_BY_NEW_PAUSE','FIVE_STEPS_VERIFIED_OWNER_PAUSE_RETAINED',
                                    'FIVE_STEPS_VERIFIED_DISK_RESERVE_RETAINED'):
            record['state']=native['state'];success=True
        else:fail('HOLD_RECOVERY_CHAIN_UNKNOWN_RESULT')
    except Exception as exc:record.update(state='HOLD_TRAINING_RECOVERY_CHAIN',reason=safe(exc))
    finally:
        record.update(finished_at=time.time(),chat_after=helper.health(),service_after=helper.service_state())
        save();emit('training_recovery_chain_receipt',record)
        emit('training_recovery_chain_context',{'request':request,'source_sha':source,'receipt_sha256':digest(recovery.read(receipt)),
            'state':record['state'],'initial_admission':record['initial_admission']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_recovery_chain_hold',{'reason':safe(exc)});raise SystemExit(2)
