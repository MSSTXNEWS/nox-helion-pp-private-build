#!/usr/bin/env python3
"""Install the reviewed checkpoint reserve in the existing priority service."""
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
SCHEMA='NOX_OWNER_TRAINING_DISK_GUARD_INSTALL_V1'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
GUARD_SHA='f2036aa08282d917ea7ad27b533e31f03dd57ade4f49a8ec5b33dfc2f0fc1d58'
INITIAL_REQUEST=''
INITIAL_SOURCE=''
INITIAL_RECEIPT_SHA=''
SERVICE='nox-priority-scheduler';SCHEDULER=SCRIPTS/'nox_priority_scheduler.py'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def load(name,pin):
    raw=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if digest(raw)!=pin:fail('HOLD_DISK_GUARD_INSTALL_BUNDLE_PIN')
    module=types.ModuleType(name);module.__file__=str(SCRIPTS/(name+'.py'))
    sys.modules[name]=module;exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module,raw


def owned_scheduler(helper):
    config=helper.program_config(SERVICE);command=shlex.split(config.get('command',''))
    if str(SCHEDULER) not in command:fail('HOLD_DISK_GUARD_SCHEDULER_COMMAND')
    state=helper.service_state(SERVICE)
    if state['state']!='RUNNING':fail('HOLD_DISK_GUARD_SCHEDULER_NOT_RUNNING')
    process=helper.process(state['pid'])
    if not process or process['service']!=SERVICE or str(SCHEDULER) not in process['argv']:
        fail('HOLD_DISK_GUARD_SCHEDULER_PROCESS')
    if config.get('stopasgroup','').lower()=='true' or config.get('killasgroup','').lower()=='true':
        if any(p['state']!='Z' and p['pgrp']==process['pgrp'] and p['service']!=SERVICE
               for p in helper.process_table().values()):fail('HOLD_DISK_GUARD_FOREIGN_PROCESS_GROUP')
    return state


def main(initial_context=None):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    context=({'request':INITIAL_REQUEST,'source_sha':INITIAL_SOURCE,'receipt_sha256':INITIAL_RECEIPT_SHA}
             if initial_context is None else initial_context)
    if (not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source)
            or not isinstance(context,dict) or set(context)!={'request','source_sha','receipt_sha256'}
            or not str(context.get('request','')).isdigit()
            or not re.fullmatch('[a-f0-9]{40}',str(context.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(context.get('receipt_sha256','')))):
        fail('HOLD_DISK_GUARD_INSTALL_CONTEXT')
    helper,_=load('owner_native_repair',HELPER_SHA);guard,guard_raw=load('owner_training_disk_guard',GUARD_SHA)
    pointer,lineage,first=guard.admission(context);budget=guard.checkpoint_budget(lineage,first)
    before_sha=(pointer.get('sources') or {}).get(str(SCHEDULER));before=guard.read(SCHEDULER)
    if digest(before)!=before_sha:fail('HOLD_DISK_GUARD_INSTALL_PREIMAGE')
    updated=guard.patch_scheduler(before.decode(),before_sha,context).encode()
    guard_path=SCRIPTS/'owner_training_disk_guard.py'
    if guard_path.exists() and digest(guard.read(guard_path))!=GUARD_SHA:fail('HOLD_DISK_GUARD_HELPER_CONFLICT')
    path=STATE/('owner_training_disk_guard_install_'+request+'.json')
    if path.exists():fail('HOLD_DISK_GUARD_INSTALL_REQUEST_REUSED')
    fd=os.open(guard.plain(STATE/'owner_maintenance.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;paused=False;installed=False;success=False
    record={'schema':SCHEMA,'request':request,'source_sha':source,'initial_admission':context,
            'guard_source_sha256':GUARD_SHA,'scheduler_before_sha256':before_sha,
            'scheduler_after_sha256':digest(updated),'budget':budget,'state':'ADMITTING',
            'trainer_source_changed':False,'checkpoints_deleted':0,'trainer_signalled':False,
            'training_restarted':False,'started_at':time.time(),'rollback':False}
    backup=ROOT/'backup/owner_training_disk_guard'/request
    def save():helper.atomic(path,json.dumps(record,indent=2).encode())
    def start():
        rc,_=helper.command(['supervisorctl','start',SERVICE],30)
        end=time.monotonic()+15
        while time.monotonic()<end:
            if helper.service_state(SERVICE)['state']=='RUNNING':return
            time.sleep(.5)
        fail('HOLD_DISK_GUARD_SCHEDULER_START')
    try:
        save();owned_scheduler(helper);guard.admission(context)
        if digest(guard.read(SCHEDULER))!=before_sha:fail('HOLD_DISK_GUARD_INSTALL_SOURCE_RACE')
        record['trainer_before']=guard.trainer_process();record['chat_before']=helper.health()
        helper.atomic(backup/'nox_priority_scheduler.py',before)
        rc,_=helper.command(['supervisorctl','stop',SERVICE],45)
        paused=helper.service_state(SERVICE)['state'] in ('STOPPED','EXITED')
        if rc or not paused:fail('HOLD_DISK_GUARD_SCHEDULER_STOP')
        helper.atomic(guard_path,guard_raw);os.chmod(guard_path,0o644)
        helper.atomic(SCHEDULER,updated);os.chmod(SCHEDULER,0o755);installed=True
        if digest(guard.read(guard_path))!=GUARD_SHA or digest(guard.read(SCHEDULER))!=digest(updated):
            fail('HOLD_DISK_GUARD_INSTALL_READBACK')
        start();paused=False;started=time.time();record['state']='INSTALLED_AWAITING_NATIVE_POLL';save()
        fcntl.flock(fd,fcntl.LOCK_UN);locked=False
        deadline=time.monotonic()+20;observation=None
        while time.monotonic()<deadline:
            try:
                value=guard.document(guard.STATUS)
                if (value.get('schema')==guard.SCHEMA and value.get('checked_at',0)>=started
                        and value.get('initial_admission')==context):observation=value;break
            except FileNotFoundError:pass
            time.sleep(1)
        if not observation or observation.get('state') not in (
                'CHECKPOINT_DISK_HEADROOM_ADMITTED','CHECKPOINT_PAUSE_REQUESTED',
                'EXISTING_TRAINING_PAUSE_RETAINED','TRAINER_NOT_RUNNING'):
            fail('HOLD_DISK_GUARD_NATIVE_POLL_NOT_VERIFIED')
        record['native_observation']=observation;record['state']='EXISTING_PRIORITY_DISK_GUARD_VERIFIED';success=True
    except Exception as exc:
        record.update(reason=safe(exc),state='HOLD_DISK_GUARD_INSTALL')
        if locked:
            if installed and digest(guard.read(SCHEDULER))==digest(updated):
                if helper.service_state(SERVICE)['state'] in ('RUNNING','STARTING'):
                    helper.command(['supervisorctl','stop',SERVICE],45)
                helper.atomic(SCHEDULER,before);record['rollback']=True;paused=True
            if paused:
                try:start()
                except Exception:record['service_restore_failed']=True
    finally:
        if locked:fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
        record.update(finished_at=time.time(),chat_after=helper.health(),scheduler_service=helper.service_state(SERVICE))
        save();emit('training_disk_guard_receipt',record)
        emit('training_disk_guard_receipt_context',{'request':request,'source_sha':source,
             'receipt_sha256':digest(guard.read(path)),'state':record['state']})
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:emit('training_disk_guard_install_hold',{'reason':safe(exc)});raise SystemExit(2)
