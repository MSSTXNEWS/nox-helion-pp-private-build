#!/usr/bin/env python3
"""Disk reserve for the admitted hybrid trainer inside the existing poller.

Only a checkpoint-aware pause flag can be created. This module never deletes
checkpoints, stops a process, resumes training or changes a source/admission.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

ROOT=Path('/root/nox');STATE=ROOT/'state';OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
SERVICE='nox-train-volta-t866u';HYBRID=ROOT/'scripts/hybrid_training_entry.py'
HYBRID_SHA='f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af'
NATIVE_SHA='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
SCHEMA='NOX_OWNER_TRAINING_DISK_GUARD_V1';MARKER='NOX_OWNER_TRAINING_DISK_GUARD_BIND_V1'
NAMES=('adapter_model.safetensors','adapter_config.json','optimizer.pt','scheduler.pt','rng_state.pth','scaler.pt','trainer_state.json')
# Owner-approved floor for the paused-writer BOOST profile: retain4GiB for
# chat/S03/logs and control receipts in addition to two whole checkpoint budgets.
RESERVE_BYTES=4*1024**3
STATUS=STATE/'owner_training_disk_guard.json'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def json_sha(value):return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def plain(path):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_DISK_GUARD_SYMLINK')
    return path
def read(path,limit=262144):
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:fail('HOLD_DISK_GUARD_FILE_SCOPE')
        raw=stream.read(limit+1)
        if len(raw)!=info.st_size:fail('HOLD_DISK_GUARD_FILE_RACE')
        return raw
def document(path,limit=262144):
    value=json.loads(read(path,limit))
    if not isinstance(value,dict):fail('HOLD_DISK_GUARD_JSON')
    return value
def atomic(path,value):
    path=plain(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.disk-guard-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode());stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def validate_context(context):
    if (not isinstance(context,dict) or set(context)!={'request','source_sha','receipt_sha256'}
            or not str(context.get('request','')).isdigit()
            or not re.fullmatch('[a-f0-9]{40}',str(context.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(context.get('receipt_sha256','')))):
        fail('HOLD_DISK_GUARD_ADMISSION_CONTEXT')


def admission(context):
    validate_context(context)
    raw=read(STATE/('owner_maintenance_'+context['request']+'.json'),2*1024*1024)
    if digest(raw)!=context['receipt_sha256']:fail('HOLD_DISK_GUARD_ADMISSION_RECEIPT')
    sealed=json.loads(raw);pointer=document(STATE/'owner_training_admission.json')
    if (sealed.get('schema')!='NOX_OWNER_TRAINING_RESUME_V1' or sealed.get('request')!=context['request']
            or sealed.get('source_sha')!=context['source_sha']
            or sealed.get('state')!='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED'
            or sealed.get('optimizer_steps_verified') is not True or pointer!=sealed.get('admission')
            or pointer.get('schema')!='NOX_OWNER_TRAINING_ADMISSION_V1'
            or pointer.get('request')!=context['request'] or pointer.get('source_sha')!=context['source_sha']
            or pointer.get('max_steps')!=1000 or pointer.get('resume') is not True):
        fail('HOLD_DISK_GUARD_INITIAL_CONTINUATION_REQUIRED')
    for path in (HYBRID,ROOT/'scripts/run_train_volta_t866u.sh',STATE/'train_cpu_max.env'):
        if digest(read(path))!=(pointer.get('sources') or {}).get(str(path)):fail('HOLD_DISK_GUARD_TRAINER_SOURCE')
    if digest(read(HYBRID))!=HYBRID_SHA:fail('HOLD_DISK_GUARD_HYBRID_SOURCE')
    policy=document(STATE/'task_boost_mode.json',16000)
    if policy.get('training_allowed') is not True or policy.get('training_service')!=SERVICE:
        fail('HOLD_DISK_GUARD_TRAINING_NOT_ADMITTED')
    first=sealed.get('five_step_receipt') or {}
    lineage=document(OUTPUT/'owner_lineage.json')
    if (first.get('schema')!='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1' or first.get('global_step')!=5
            or first.get('adapter_delta_verified') is not True
            or json_sha(lineage)!=first.get('lineage_sha256') or lineage.get('native_sha256')!=NATIVE_SHA
            or (lineage.get('training_config') or {}).get('optimizer')!='paged_adamw_8bit'):
        fail('HOLD_DISK_GUARD_LINEAGE_CHANGED')
    return pointer,lineage,first


def checkpoint_budget(lineage,first):
    targets=lineage.get('targets') or {};parameters=targets.get('trainable_parameters')
    if type(parameters) is not int or not 1<=parameters<=2_000_000_000 or targets.get('trainable_dtype')!='float32':
        fail('HOLD_DISK_GUARD_PARAMETER_COUNT')
    checkpoint=first.get('checkpoint') or {};path=OUTPUT/'checkpoint-5';observed=0
    if checkpoint.get('path')!=str(path) or set(checkpoint.get('files_sha256') or {})!=set(NAMES):
        fail('HOLD_DISK_GUARD_CHECKPOINT_SCOPE')
    for name in NAMES:
        file=plain(path/name);fd=os.open(file,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8*1024**3:fail('HOLD_DISK_GUARD_CHECKPOINT_SIZE')
            observed+=info.st_size
        finally:os.close(fd)
    # FP32 adapters + two FP32 moment tensors + a master copy is deliberately
    # above the normal paged8bit state. It also covers previously idle experts.
    upper=max(parameters*16+128*1024**2,(observed*3+1)//2)
    return {'trainable_parameters':parameters,'observed_checkpoint_bytes':observed,
            'checkpoint_budget_bytes':upper,'disk_reserve_bytes':RESERVE_BYTES,
            'required_free_bytes':RESERVE_BYTES+2*upper+256*1024**2}


def trainer_process():
    matches=[]
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:
            argv=(directory/'cmdline').read_bytes().split(b'\0')
            if str(HYBRID).encode() not in argv:continue
            args=[v.decode() for v in argv if v]
            options={key:args[i+1] for i,key in enumerate(args[:-1]) if key in ('--max-steps','--planned-steps','--native-sha')}
            if options!={'--max-steps':'1000','--planned-steps':'1000','--native-sha':NATIVE_SHA} or '--resume' not in args:
                fail('HOLD_DISK_GUARD_PROCESS_SCOPE')
            environment=(directory/'environ').read_bytes().split(b'\0')
            selected={item.partition(b'=')[0]:item.partition(b'=')[2] for item in environment
                      if item.startswith((b'CUDA_VISIBLE_DEVICES=',b'SUPERVISOR_PROCESS_NAME='))}
            if selected!={b'CUDA_VISIBLE_DEVICES':b'1',b'SUPERVISOR_PROCESS_NAME':SERVICE.encode()}:
                fail('HOLD_DISK_GUARD_PROCESS_ROLE')
            tail=(directory/'stat').read_text().rsplit(')',1)[1].split()
            if tail[0]!='Z':matches.append({'pid':int(directory.name),'starttime':int(tail[19])})
        except (OSError,ValueError,IndexError):continue
    if len(matches)>1:fail('HOLD_DISK_GUARD_DUPLICATE_TRAINER')
    return matches[0] if matches else None


def latch_pause(context,budget,process):
    path=plain(STATE/'TRAIN_PAUSE_REQUEST.flag')
    payload=('OWNER_DISK_RESERVE_PAUSE request='+context['request']+' source='+context['source_sha']+'\n').encode()
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:return False
    with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return True


def tick(context):
    validate_context(context)
    result={'schema':SCHEMA,'checked_at':time.time(),'initial_admission':context,
            'checkpoints_deleted':0,'trainer_signalled':False,'training_resumed':False}
    fd=os.open(plain(STATE/'owner_maintenance.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:return {**result,'state':'OWNER_MAINTENANCE_ACTIVE'}
        pointer,lineage,first=admission(context);budget=checkpoint_budget(lineage,first)
        process=trainer_process();space=os.statvfs(plain(OUTPUT));free=space.f_bavail*space.f_frsize
        result.update(budget,free_bytes=free,trainer_process=process)
        if process is None:result['state']='TRAINER_NOT_RUNNING'
        elif (STATE/'TRAIN_PAUSE_REQUEST.flag').exists() or (STATE/'TRAIN_HOLD.flag').exists():
            result['state']='EXISTING_TRAINING_PAUSE_RETAINED'
        elif free<budget['required_free_bytes']:
            if trainer_process()!=process:fail('HOLD_DISK_GUARD_PROCESS_CHANGED')
            result['pause_created']=latch_pause(context,budget,process)
            result['state']='CHECKPOINT_PAUSE_REQUESTED' if result['pause_created'] else 'EXISTING_TRAINING_PAUSE_RETAINED'
        else:result['state']='CHECKPOINT_DISK_HEADROOM_ADMITTED'
        atomic(STATUS,result);return result
    finally:os.close(fd)


def binding_text(context):
    validate_context(context)
    return ('# '+MARKER+'\nimport owner_training_disk_guard\n'
            'owner_training_disk_guard.bind_scheduler(globals(), '+repr(dict(sorted(context.items())))+')\n\n')


def patch_scheduler(source,expected_sha,context):
    if digest(source.encode())!=expected_sha:fail('HOLD_DISK_GUARD_SCHEDULER_PREIMAGE')
    addition=binding_text(context)
    if MARKER in source:fail('HOLD_DISK_GUARD_ALREADY_BOUND')
    anchor='if __name__ == "__main__":\n    main()\n'
    if source.count(anchor)!=1:fail('HOLD_DISK_GUARD_SCHEDULER_ANCHOR')
    updated=source.replace(anchor,addition+anchor,1);compile(updated,'nox_priority_scheduler.py','exec');return updated


def bind_scheduler(namespace,context):
    validate_context(context)
    if namespace.get('_owner_training_disk_guard_bound'):return
    original=namespace.get('apply_protect_and_preempt')
    if not callable(original):fail('HOLD_DISK_GUARD_SCHEDULER_CALLBACK')
    last=[0.0];observation=[None]
    def guarded(*args,**kwargs):
        if time.monotonic()-last[0]>=2:
            last[0]=time.monotonic()
            try:observation[0]=tick(context)
            except Exception as exc:
                reason=str(exc);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
                observation[0]={'schema':SCHEMA,'checked_at':time.time(),'state':'GUARD_OBSERVATION_BLOCKED','reason':reason}
                try:atomic(STATUS,observation[0])
                except OSError:pass
        actions=list(original(*args,**kwargs) or [])
        if observation[0]:actions.append({'training_disk_guard':observation[0]})
        return actions
    namespace['apply_protect_and_preempt']=guarded
    namespace['_owner_training_disk_guard_bound']=True
