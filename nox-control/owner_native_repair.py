#!/usr/bin/env python3
"""Explicit owner's immediate training halt on the existing NOX host.

This repair action only halts the original supervised trainer. It never starts
training, installs a replacement scheduler, touches model files, or restarts chat.
"""
from __future__ import annotations
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path('/root/nox')
PROC=Path('/proc')
SERVICE='nox-train-volta-t866u'
WRAPPER=ROOT/'scripts/run_train_volta_t866u.sh'
TRAINER=ROOT/'scripts/train_qlora_35b_t866u.py'
CONFIG=Path('/etc/supervisor/conf.d/nox-train-volta-t866u.conf')
# Both hashes independently read back from the native host on 2026-11-16.
SOURCE_PINS={
    'run_train_volta_t866u.sh':'daeb0b2b90d8a3717ecb8e78c2481697b5f209ce18646ae893e377c0de538b99',
    'train_qlora_35b_t866u.py':'703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a',
}

def emit(kind,data):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)

def atomic(path,data):
    path=Path(path)
    if path.is_symlink():raise RuntimeError('HOLD_TARGET_SYMLINK')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.owner-halt-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def command(args,timeout=12):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return r.returncode,r.stdout
    except subprocess.TimeoutExpired:return 124,''
    except OSError:return 127,''

def service_state():
    rc,out=command(['supervisorctl','status',SERVICE])
    m=re.match(r'^'+re.escape(SERVICE)+r'\s+(\w+)(?:\s+pid\s+(\d+))?',out.strip())
    return {'rc':rc,'state':m[1] if m else 'UNKNOWN','pid':int(m[2]) if m and m[2] else None}

def process(pid):
    p=PROC/str(pid)
    try:
        stat=(p/'stat').read_text().split(') ',1)[1].split()
        argv=[s.decode(errors='replace') for s in (p/'cmdline').read_bytes().split(b'\0') if s]
        env=dict(s.split('=',1) for s in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in s)
        return {'pid':int(pid),'ppid':int(stat[1]),'pgrp':int(stat[2]),'state':stat[0],
                'starttime':stat[19],'argv':argv,'cuda':env.get('CUDA_VISIBLE_DEVICES'),
                'service':env.get('PROC_NAME') or env.get('SUPERVISOR_PROCESS_NAME')}
    except (OSError,ValueError,IndexError):return None

def process_table():
    return {int(p.name):row for p in PROC.iterdir()
            if p.name.isdigit() and (row:=process(int(p.name))) is not None}

def owns_training(row):
    return bool(row and row.get('cuda')=='1' and row.get('service')==SERVICE
                and any(s in row.get('argv',[]) for s in (str(WRAPPER),str(TRAINER))))

def same_process(before,after):
    return bool(owns_training(before) and owns_training(after)
                and all(before.get(k)==after.get(k) for k in ('pid','starttime','argv','cuda','service')))

def public_process(row):
    return {k:row[k] for k in ('pid','ppid','pgrp','state','starttime','cuda','service')}

def signal_owned(before,sig):
    """Pin the local PID with pidfd, then recheck its exact identity before signal."""
    if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise RuntimeError('HOLD_PIDFD_UNAVAILABLE')
    try:fd=os.pidfd_open(before['pid'],0)
    except ProcessLookupError:return False
    try:
        current=process(before['pid'])
        if not current or current.get('state')=='Z':return False
        if not same_process(before,current):raise RuntimeError('HOLD_PID_IDENTITY_CHANGED')
        signal.pidfd_send_signal(fd,sig,None,0)
        return True
    finally:os.close(fd)

def health():
    result={}
    for port in (8080,8081,8082):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/health'%port,timeout=4) as r:result[str(port)]=r.status
        except Exception as exc:result[str(port)]=type(exc).__name__
    return result

def gpu():
    rc,out=command(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'])
    rows=[]
    if rc==0:
        for line in out.splitlines():
            c=[s.strip() for s in line.split(',')]
            if len(c)==4 and all(s.isdigit() for s in c):
                rows.append(dict(zip(('index','used_mib','free_mib','utilization'),map(int,c))))
    return {'rc':rc,'gpus':rows}

def progress():
    p=ROOT/'status/train_volta_t866u.json'
    try:
        if p.is_symlink() or p.stat().st_size>200000:return {'readable':False}
        d=json.loads(p.read_text())
        return {k:d[k] for k in ('phase','step','global_step','loss','max_steps')
                if k in d and isinstance(d[k],(str,int,float,bool,type(None)))}
    except (OSError,ValueError,TypeError):return {'readable':False}

def verify_sources():
    for p in (WRAPPER,TRAINER):
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=SOURCE_PINS[p.name]:
            raise RuntimeError('HOLD_NATIVE_TRAIN_SOURCE_CHANGED')
    if CONFIG.is_symlink() or not CONFIG.is_file():raise RuntimeError('HOLD_TRAIN_SUPERVISOR_CONFIG')
    config=configparser.ConfigParser(interpolation=None)
    config.read(CONFIG);section='program:'+SERVICE
    if not config.has_section(section):raise RuntimeError('HOLD_TRAIN_SUPERVISOR_CONFIG')
    if shlex.split(config.get(section,'command',fallback=''))!=['/bin/bash',str(WRAPPER)]:
        raise RuntimeError('HOLD_TRAIN_SUPERVISOR_COMMAND')
    return {k:config.get(section,k,fallback='') for k in
            ('autostart','autorestart','stopsignal','stopwaitsecs','stopasgroup','killasgroup')}

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');sha=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch(r'[0-9a-f]{40}',sha):raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    state=ROOT/'state';state.mkdir(parents=True,exist_ok=True)
    fd=os.open(state/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    receipt=state/('owner_maintenance_'+request+'.json')
    if receipt.exists():raise RuntimeError('HOLD_REQUEST_ALREADY_STARTED_INSPECT_RECEIPT')
    result={'schema':'NOX_OWNER_TRAINING_HALT_V1','request':request,'source_sha':sha,'action':'halt_training_only',
            'started':time.time(),'steps':[],'training_started':False,'weights_deleted':0,'s03_modified':False,
            'scripts_modified':False,'chat_before':health(),'gpu_before':gpu(),'progress_before':progress()}
    latched=False;success=False
    def step(kind,data):
        result['steps'].append({'kind':kind,'data':data,'time':time.time()})
        atomic(receipt,json.dumps(result,indent=2).encode());emit(kind,data)
    atomic(receipt,json.dumps(result,indent=2).encode())
    try:
        if result['chat_before'].get('8081')!=200:raise RuntimeError('HOLD_CHAT_UNHEALTHY_BEFORE_HALT')
        settings=verify_sources();result['supervisor_settings']=settings
        service=service_state();result['service_before']=service
        if service['state']=='UNKNOWN':raise RuntimeError('HOLD_TRAIN_SUPERVISOR_STATUS')
        table=process_table();owned=[row for row in table.values() if owns_training(row) and row['state']!='Z']
        if service['pid'] is not None:
            parent=table.get(service['pid'])
            if not owns_training(parent) or str(WRAPPER) not in parent['argv']:raise RuntimeError('HOLD_SUPERVISOR_PID_NOT_OWNED_WRAPPER')
            # Supervisor's configured group stop must not include an unrelated role.
            if settings.get('stopasgroup','').lower()=='true' or settings.get('killasgroup','').lower()=='true':
                if any(p['pgrp']==parent['pgrp'] and p['state']!='Z'
                       and (p['service']!=SERVICE or p['cuda']!='1') for p in table.values()):
                    raise RuntimeError('HOLD_TRAIN_PROCESS_GROUP_HAS_OTHER_ROLE')
        result['owned_processes_before']=[public_process(row) for row in owned]
        backups=ROOT/'backup/owner_maintenance'/request
        for name in ('TRAIN_HOLD.flag','TRAIN_PAUSE_REQUEST.flag'):
            p=state/name
            if p.is_symlink():raise RuntimeError('HOLD_EXISTING_STOP_FLAG_SYMLINK')
            if p.exists():atomic(backups/name,p.read_bytes())
        note=('OWNER_REQUESTED_TRAINING_HALT request='+request+' source='+sha+'\n').encode()
        atomic(state/'TRAIN_HOLD.flag',note);latched=True
        atomic(state/'TRAIN_PAUSE_REQUEST.flag',note)
        if not (state/'train_wants_gpu1').exists():atomic(state/'train_wants_gpu1',note)
        step('training_hold_latched',{'hold':True,'pause_requested':True,'teacher_reservation_retained':True})
        if service['state'] in ('RUNNING','STARTING','BACKOFF','STOPPING'):
            # stopasgroup/killasgroup are existing native service settings. The
            # complete current process group was checked above before calling it.
            rc,_=command(['supervisorctl','stop',SERVICE],75)
            step('owned_supervisor_stop',{'service':SERVICE,'rc':rc})
        for sig,wait_seconds in ((signal.SIGTERM,10),(signal.SIGKILL,5)):
            survivors=[]
            for row in owned:
                current=process(row['pid'])
                if same_process(row,current) and current['state']!='Z':survivors.append(row)
            if not survivors:break
            signalled=[]
            for row in survivors:
                if signal_owned(row,sig):signalled.append(row['pid'])
            step('owned_process_signal',{'signal':sig.name,'local_pids':signalled,
                 'uncheckpointed_work_loss_possible':True})
            deadline=time.monotonic()+wait_seconds
            while time.monotonic()<deadline and any(same_process(row,process(row['pid'])) for row in survivors):time.sleep(1)
        # The existing wrapper reads HOLD before loading CUDA. Repeated dispatcher
        # start requests therefore cannot relaunch training while the flag remains.
        deadline=time.monotonic()+30
        while True:
            remaining=[row for row in process_table().values() if owns_training(row) and row['state']!='Z'
                       and str(TRAINER) in row['argv']]
            if not remaining or time.monotonic()>=deadline:break
            time.sleep(2)
        if remaining:raise RuntimeError('HOLD_OWNED_TRAINER_STILL_RUNNING')
        deadline=time.monotonic()+30
        while True:
            measured=gpu();gpu1=next((g for g in measured['gpus'] if g['index']==1),None)
            if gpu1 and gpu1['free_mib']>=27000:break
            if time.monotonic()>=deadline:raise RuntimeError('HOLD_GPU1_MEMORY_NOT_RELEASED')
            time.sleep(2)
        result['gpu1_release_verified']=gpu1
        result['halt_verified']=True;result['state']='TRAINING_HALTED_OWNER_HOLD_RETAINED'
        step('training_halt_verified',{'trainer_processes':0,'training_started':False,'hold_retained':True})
        success=True
    except Exception as exc:
        code=str(exc);result['state']='HOLD_PARTIAL_HALT' if latched else 'HOLD_BEFORE_MUTATION'
        result['error']=code if re.fullmatch(r'HOLD_[A-Z0-9_]+',code) else type(exc).__name__
    finally:
        result.update(finished=time.time(),hold_retained=(state/'TRAIN_HOLD.flag').is_file(),
                      service_after=service_state(),chat_after=health(),gpu_after=gpu(),progress_after=progress())
        if result['chat_after'].get('8081')!=200:
            result['chat_health_regression']=True;success=False
        atomic(receipt,json.dumps(result,indent=2).encode());emit('native_halt_receipt',result)
        os.close(fd)
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        code=str(exc);emit('failure',code if re.fullmatch(r'HOLD_[A-Z0-9_]+',code) else type(exc).__name__)
        raise SystemExit(2)
