#!/usr/bin/env python3
"""Explicit owner recovery in the existing NOX controller and trainer service.

halt_main preserves the verified emergency halt implementation. The current
pinned repair action optimizes the stopped service, verifies five real optimizer
steps, then admits continuation. It never replaces the active chat or S03.
"""
from __future__ import annotations
import base64
import configparser
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import types
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
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
HALT_REQUEST='6902883046'
HALT_SOURCE='df3a6005ca711ce44b606b864db154c396cbeb92'
DISPATCHER=ROOT/'scripts/nox_dispatcher_t855u.py'
AUTOSCALE=ROOT/'scripts/nox_autoscale_t877u.py'
SELFHEAL=Path('/root/nox_selfheal.py')
SCHEDULER=ROOT/'scripts/nox_priority_scheduler.py'
CONTROL_PINS={
    'nox_dispatcher_t855u.py':'e372e46108ff15b08833bb1b0abad4ca12f19a6c033f16e3bf68f4bf79e2cd77',
    'nox_autoscale_t877u.py':'4e74f35d9e773592db62a6bbc7a2b8bccbe7797b630b4f6f48843e4c460fd59e',
    'nox_selfheal.py':'6d8e0849c40c316e5cb41fa248a4cace95f8d08cd88d057fcf340c02d1ff88fb',
    'nox_priority_scheduler.py':'eeccb80b896f7e642d77ed1fea3573872863d56ccbc6812d5eae9fc5ad1285ed',
}
OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
OPERATION_MODE='TASK_BOOST'
BOOST_FLAG=ROOT/'state/task_boost_mode.json'
HEAVY_SERVICES={
    'nox-distill-worm-t811u':ROOT/'scripts/distill_worm_t811u.py',
    'nox-self-improve-t846u':ROOT/'scripts/self_improve_worm_t846u.py',
    'nox-self-learning-loop':ROOT/'scripts/self_learning_loop.py',
    'nox-teacher-serve-t811u':ROOT/'scripts/teacher_serve_t811u.sh',
    'nox-offload-t850u':ROOT/'scripts/offload_worm_t850u.py',
    'nox-downloads-t802u':ROOT/'scripts/download_t802u.sh',
    'nox-watch-swap-t845u':ROOT/'scripts/watch_swap_35b_t845u.sh',
    'nox-agent-architect-t859u':ROOT/'scripts/nox_agent_architect_t859u.py',
    'nox-agent-tuner-t858u':ROOT/'scripts/nox_agent_tuner_t858u.py',
}
CHECKPOINT_NAMES=('trainer_state.json','optimizer.pt','scheduler.pt','rng_state.pth',
                  'scaler.pt','adapter_config.json','adapter_model.safetensors')

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

def service_state(name=SERVICE):
    rc,out=command(['supervisorctl','status',name])
    m=re.match(r'^'+re.escape(name)+r'\s+(\w+)(?:\s+pid\s+(\d+))?',out.strip())
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

def halt_main():
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


OWNER_GUARD = '''
# NOX_OWNER_ADMISSION_GUARD_V1: invoked by the existing controller only.
def _nox_owner_maintenance_busy():
    import fcntl as _f, os as _o
    _p=ROOT / "state" / "owner_maintenance.lock"
    try: _fd=_o.open(_p,_o.O_RDONLY|_o.O_NOFOLLOW)
    except FileNotFoundError: return False
    except OSError: return True
    try:
        try: _f.flock(_fd,_f.LOCK_SH|_f.LOCK_NB)
        except BlockingIOError: return True
        return False
    finally: _o.close(_fd)

def _nox_owner_boost_active():
    import json as _json
    _p=ROOT/"state/task_boost_mode.json"
    if not _p.exists(): return False
    try: return _json.loads(_p.read_text()).get("enabled") is True
    except (ValueError,OSError,AttributeError): return True

def _nox_owner_task_admitted(task):
    if _nox_owner_maintenance_busy(): return False
    if not _nox_owner_boost_active(): return True
    if task.get("class") in ("training","agent_distill","gguf_identity"): return False
    if any(_name in ("gpu0","gpu1","chat_swap") for _name in (task.get("locks") or [])): return False
    if task.get("handler") in ("start_qlora","merge_gated","new_gguf","hot_swap","exec_plan"): return False
    return True

def _nox_owner_admission_reason(name):
    if _nox_owner_maintenance_busy(): return "owner maintenance holds admissions"
    if _nox_owner_boost_active() and name in ("nox-train-volta-t866u","nox-train-worm-t811u",
            "nox-distill-worm-t811u","nox-self-improve-t846u","nox-self-learning-loop","nox-teacher-serve-t811u",
            "nox-offload-t850u","nox-downloads-t802u","nox-watch-swap-t845u","nox-agent-architect-t859u","nox-agent-tuner-t858u"):
        return "TASK_BOOST reserves resources for owner tasks"
    if name in ("nox-train-volta-t866u","nox-train-worm-t811u"):
        if name=="nox-train-worm-t811u": return "superseded trainer stays disabled"
        _flags=(ROOT/"STOP",ROOT/"STOP.flag",ROOT/"stop.flag",ROOT/"state/STOP",
                ROOT/"state/TRAIN_HOLD.flag",ROOT/"state/TRAIN_PAUSE_REQUEST.flag")
        if any(_p.exists() for _p in _flags): return "owner training hold or pause"
    if name=="nox-teacher-serve-t811u" and (ROOT/"state/train_wants_gpu1").exists():
        return "training resource reservation"
    return None

def _nox_owner_start_service(name, **kwargs):
    _reason=_nox_owner_admission_reason(name)
    if _reason:
        return subprocess.CompletedProcess(["supervisorctl","start",name],125,_reason,"")
    return subprocess.run(["supervisorctl","start",name],**kwargs)

'''

def replace_once(source,old,new):
    if source.count(old)!=1:raise RuntimeError('HOLD_NATIVE_CONTROL_ANCHOR_CHANGED')
    return source.replace(old,new,1)

def patch_dispatcher(source):
    if 'NOX_OWNER_ADMISSION_GUARD_V1' in source:raise RuntimeError('HOLD_CONTROL_ALREADY_PATCHED_INSPECT_FIRST')
    source=replace_once(source,'def h_start_qlora(task):\n',OWNER_GUARD+
        'def h_start_qlora(task):\n    _owner_block=_nox_owner_admission_reason("nox-train-volta-t866u")\n'
        '    if _owner_block: return "wait",_owner_block\n')
    source=replace_once(source,'def h_ensure_program(task):\n',
        'def h_ensure_program(task):\n    _owner_block=_nox_owner_admission_reason(task.get("note") or "")\n'
        '    if _owner_block: return "wait",_owner_block\n')
    source=source.replace('subprocess.run(["supervisorctl", "start", "nox-teacher-serve-t811u"],',
                          '_nox_owner_start_service("nox-teacher-serve-t811u",')
    for handler,name in (('h_ensure_downloads','nox-downloads-t802u'),('h_ensure_offload','nox-offload-t850u')):
        source=replace_once(source,'def '+handler+'(task):\n','def '+handler+'(task):\n'
            '    _owner_block=_nox_owner_admission_reason('+repr(name)+')\n'
            '    if _owner_block: return "wait",_owner_block\n')
    compile(source,str(DISPATCHER),'exec');return source

def patch_autoscale(source):
    if 'NOX_OWNER_ADMISSION_GUARD_V1' in source:raise RuntimeError('HOLD_CONTROL_ALREADY_PATCHED_INSPECT_FIRST')
    source=replace_once(source,'def resume_svc(name, reason):\n',OWNER_GUARD+
        'def resume_svc(name, reason):\n    if _nox_owner_admission_reason(name): return False\n')
    source=replace_once(source,'    if "RUNNING" in st:\n        return False\n',
                                '    if "RUNNING" in st:\n        return True\n')
    source=replace_once(source,'    """Called from the priority scheduler each loop."""\n',
        '    """Called from the priority scheduler each loop."""\n'
        '    if _nox_owner_maintenance_busy(): return {"owner_maintenance":True,"admissions_paused":True}\n')
    compile(source,str(AUTOSCALE),'exec');return source

def patch_selfheal(source):
    source=replace_once(source,'def sv_start(name: str) -> str:\n',OWNER_GUARD+
        'def sv_start(name: str) -> str:\n    _owner_block=_nox_owner_admission_reason(name)\n'
        '    if _owner_block: return "owner_hold: "+_owner_block\n')
    for signature,name in (('fix_training(st: dict, why: str)','nox-train-volta-t866u'),
                           ('fix_teachers(st: dict)','nox-teacher-serve-t811u'),
                           ('fix_distill(st: dict)','nox-distill-worm-t811u')):
        source=replace_once(source,'def '+signature+' -> dict:\n','def '+signature+' -> dict:\n'
            '    _owner_block=_nox_owner_admission_reason('+repr(name)+')\n'
            '    if _owner_block: return {"result":"owner_hold","fix":_owner_block}\n')
    for signature in ('fix_shm(st: dict)','fix_idle_gpu(st: dict, gs: list[dict], work: dict)'):
        source=replace_once(source,'def '+signature+' -> dict:\n','def '+signature+' -> dict:\n'
            '    if _nox_owner_boost_active() or _nox_owner_maintenance_busy(): return {"result":"owner_hold","fix":"TASK_BOOST"}\n')
    source=replace_once(source,'    # teacher row (open models only, no vendor names)\n',
        '    if _nox_owner_boost_active(): return rec  # Operational journal only; no unverified training lessons.\n'
        '    # teacher row (open models only, no vendor names)\n')
    source=replace_once(source,'def ensure_rule_lesson():\n','def ensure_rule_lesson():\n'
                       '    if _nox_owner_boost_active(): return\n')
    source=replace_once(source,'    append_jsonl(OWNER_ORDERS, rec)\n',
        '    append_jsonl(OWNER_ORDERS, rec)\n    if _nox_owner_boost_active(): return rec  # Dispatcher is the sole task-state writer.\n')
    source=replace_once(source,'    def fault(item, diagnosis, playbook=None, unknown=False, evidence=None):\n',
        '    def fault(item, diagnosis, playbook=None, unknown=False, evidence=None):\n'
        '        if _nox_owner_boost_active() and item in ("teachers_down","distill_down","distill_rate_zero","idle_gpu1","shm_high","queue_dry"): return\n')
    compile(source,str(SELFHEAL),'exec');return source

def patch_scheduler(source):
    source=replace_once(source,'def pause_pausable(reason: str):\n','ROOT = Path("/root/nox")\n'+OWNER_GUARD+
        'def pause_pausable(reason: str):\n    if _nox_owner_boost_active() or _nox_owner_maintenance_busy(): return [],0\n')
    source=replace_once(source,'def resume_paused():\n','def resume_paused():\n'
                       '    if _nox_owner_boost_active() or _nox_owner_maintenance_busy(): return [],0\n')
    source=replace_once(source,'def restore_gpu1_teachers():\n','def restore_gpu1_teachers():\n'
                       '    if _nox_owner_admission_reason("nox-teacher-serve-t811u"): return\n')
    source=replace_once(source,'def apply_protect_and_preempt(disk_gb, vram_info, owner_active, ident):\n',
        'def apply_protect_and_preempt(disk_gb, vram_info, owner_active, ident):\n'
        '    if _nox_owner_boost_active() or _nox_owner_maintenance_busy(): return [{"owner_scoped_control":True}]\n')
    compile(source,str(SCHEDULER),'exec');return source

def bundle_module(name):
    data=base64.b64decode(BUNDLE.get(name+'.py',''),validate=True)
    if not data:raise RuntimeError('HOLD_REQUIRED_OWNER_HELPER_MISSING')
    module=types.ModuleType(name);module.__file__=str(ROOT/'scripts'/(name+'.py'));sys.modules[name]=module
    exec(compile(data,module.__file__,'exec'),module.__dict__)
    return module,data

def program_config(name):
    found=[]
    for path in sorted(Path('/etc/supervisor/conf.d').glob('*.conf'))[:150]:
        if path.is_symlink() or path.stat().st_size>300000:continue
        parser=configparser.ConfigParser(interpolation=None,strict=False)
        try:parser.read(path)
        except (OSError,configparser.Error):continue
        section='program:'+name
        if parser.has_section(section):
            found.append({key:parser.get(section,key,fallback='') for key in
                          ('command','stopasgroup','killasgroup','stopwaitsecs','stopsignal')})
    if len(found)!=1:raise RuntimeError('HOLD_SUPERVISOR_PROGRAM_NOT_UNIQUE')
    return found[0]

TEACHER_ROLES={
    '8087':('/root/nox/models/teachers/vikhr-nemo-12b-instruct-r-21-09-24-q4_k_m.gguf','0'),
    '8088':('/root/nox/models/teachers/saiga_nemo_12b.Q4_K_M.gguf',''),
    '8092':('/root/nox/models/judge/Qwen3Guard-Gen-4B.Q4_K_M.gguf',''),
    '8093':('/root/nox/models/judge/Qwen3Guard-Gen-4B.Q4_K_M.gguf',''),
    '8096':('/root/nox/models/judge/Qwen3Guard-Gen-4B.Q4_K_M.gguf','1'),
}

def teacher_role(row):
    if not row or not row['argv'] or row['argv'][0]!='/root/nox/bin/llama-server':return None
    argv=row['argv']
    def value(flag):return argv[argv.index(flag)+1] if flag in argv and argv.index(flag)+1<len(argv) else None
    port=value('--port');known=TEACHER_ROLES.get(port)
    if (not known or (value('-m') or value('--model'))!=known[0] or row['cuda']!=known[1]
            or row['service'] not in (None,'','nox-selfheal','nox-teacher-serve-t811u')):return None
    return port

def signal_teacher(before,sig):
    fd=os.pidfd_open(before['pid'],0)
    try:
        current=process(before['pid'])
        if not current or current['state']=='Z':return False
        if (not teacher_role(before) or teacher_role(current)!=teacher_role(before)
                or any(before[k]!=current[k] for k in ('pid','starttime','argv','cuda','service'))):
            raise RuntimeError('HOLD_TEACHER_IDENTITY_CHANGED')
        signal.pidfd_send_signal(fd,sig,None,0);return True
    finally:os.close(fd)

def postflight_inventory():
    """Bounded readback only; no media download, model load or credential output."""
    out={'chat_sources':[],'media':{'roots':[],'ports':{},'files':[]}}
    inspector,_=bundle_module('owner_native_inspect')
    for p in (ROOT/'scripts/nox_v29_chat_bridge.py',ROOT/'scripts/supervise_chat_8081.sh',Path('/opt/supervisor-scripts/nox-proxy.sh')):
        if not p.is_file() or p.is_symlink() or p.stat().st_size>90000:continue
        data=p.read_bytes();raw=data.decode(errors='replace');safe=inspector.redact(raw)
        safe=re.sub(r'(?im)^.*\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)\s*=.*$', '[REDACTED_SECRET_ASSIGNMENT]',safe)
        row={'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'source_redacted':safe!=raw,'source':safe}
        if len(json.dumps(out['chat_sources']+[row]))>90000:row.pop('source');row['source_omitted']='OUTPUT_BUDGET'
        out['chat_sources'].append(row)
    for base in (Path('/root/ComfyUI'),ROOT/'ComfyUI',Path('/workspace/ComfyUI')):
        out['media']['roots'].append({'path':str(base),'present':base.is_dir()})
        for kind in ('diffusion_models','checkpoints','text_encoders','vae'):
            directory=base/'models'/kind
            if directory.is_dir():
                for p in directory.iterdir():
                    if len(out['media']['files'])>=30:break
                    if p.is_file() and not p.is_symlink():out['media']['files'].append({'path':str(p),'bytes':p.stat().st_size})
    for port in (8188,7860,8000):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/'%port,timeout=2) as r:out['media']['ports'][str(port)]=r.status
        except Exception as exc:out['media']['ports'][str(port)]=type(exc).__name__
    import shutil
    out['media']['shm']=dict(zip(('total','used','free'),shutil.disk_usage('/dev/shm')))
    out['media']['cgroup']={n:Path('/sys/fs/cgroup',n).read_text().strip() for n in ('memory.max','memory.current','cpu.max')}
    return out

def resource_budget(limit,used,quota,affinity):
    if not all(type(x) is int for x in (limit,used,quota,affinity)) or not 0<=used<limit or quota<1 or affinity<1:
        raise RuntimeError('HOLD_NATIVE_CGROUP_BUDGET')
    gib=1024**3;cpu_gib=min(64,(limit-used-16*gib)//gib)
    if cpu_gib<56:raise RuntimeError('HOLD_TRAIN_CPU_RAM_HEADROOM')
    return {'train_cpu_gib':cpu_gib,'omp_threads':min(4,quota,affinity),
            'openblas_threads':1,'gpu_weight_placement_gib':12,'cgroup_memory_limit':limit,
            'cgroup_memory_current':used,'cpu_quota_cores':quota,'chat_reserve_gib':16}

def wrapper_source(request,max_steps=5,resume=False):
    if not request.isdigit() or max_steps not in (5,1000):raise RuntimeError('HOLD_WRAPPER_ARGUMENTS')
    args=' --resume' if resume else ''
    return '''#!/bin/bash
# Existing NOX trainer service: one bounded, checkpointed hybrid run. No port kills.
set -u
export TZ=Europe/Moscow CUDA_VISIBLE_DEVICES=1 TOKENIZERS_PARALLELISM=false
STATE=/root/nox/state
HOLD="$STATE/TRAIN_HOLD.flag"
for flag in "$HOLD" "$STATE/TRAIN_PAUSE_REQUEST.flag" /root/nox/STOP /root/nox/STOP.flag /root/nox/stop.flag "$STATE/STOP"; do
  [ ! -e "$flag" ] || exit 0
done
if [ -f "$STATE/train_cpu_max.env" ]; then set -a; . "$STATE/train_cpu_max.env"; set +a; fi
export TRAIN_GPU_BUDGET=12
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:128
/root/venv_volta/bin/python -u /root/nox/scripts/hybrid_training_entry.py --native-sha '''+SOURCE_PINS[TRAINER.name]+''' --max-steps '''+str(max_steps)+''' --planned-steps 1000'''+args+'''
rc=$?
# Both success and failure stop automatic repeats. Continuation requires verified
# checkpoint evidence and another explicit owner admission by the same operator.
if [ ! -e "$HOLD" ]; then
  if [ "$rc" -eq 0 ]; then state=BOUNDED_COMPLETE; else state=FAILED; fi
  /root/venv_volta/bin/python - "$HOLD" "$state" <<'PY_HOLD'
import os,sys,tempfile
from pathlib import Path
p=Path(sys.argv[1]);fd,tmp=tempfile.mkstemp(prefix='.hybrid-hold-',dir=p.parent)
try:
 with os.fdopen(fd,'w') as f:f.write('OWNER_HYBRID_'+sys.argv[2]+' request='''+request+'''\\n');f.flush();os.fsync(f.fileno())
 if not p.exists():os.link(tmp,p)
except FileExistsError:pass
finally:os.unlink(tmp)
PY_HOLD
fi
exit "$rc"
'''

def verify_five_result(result):
    if (not isinstance(result,dict) or result.get('state')!='VERIFIED_BOUNDED_ADAPTER_UPDATE'
            or result.get('native_sha256')!=SOURCE_PINS[TRAINER.name]
            or type(result.get('global_step')) is not int or result['global_step']!=5
            or type(result.get('successful_optimizer_steps')) is not int or result['successful_optimizer_steps']<1
            or type(result.get('loss')) not in (int,float) or not math.isfinite(result['loss'])
            or result.get('adapter_delta_verified') is not True):raise RuntimeError('HOLD_FIVE_STEP_RECEIPT')
    before=result.get('before_tensor_sha256');after=result.get('after_tensor_sha256')
    if any(not isinstance(s,str) or not re.fullmatch('[a-f0-9]{64}',s) for s in (before,after)) or before==after:
        raise RuntimeError('HOLD_NO_ADAPTER_TENSOR_DELTA')
    cp=result.get('checkpoint',{});path=OUTPUT/'checkpoint-5'
    hashes=cp.get('files_sha256',{})
    if cp.get('path')!=str(path) or cp.get('global_step')!=5 or set(hashes)!=set(CHECKPOINT_NAMES):
        raise RuntimeError('HOLD_CHECKPOINT_RECEIPT_SCOPE')
    for name in CHECKPOINT_NAMES:
        p=path/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size<=0:raise RuntimeError('HOLD_CHECKPOINT_FILE_MISSING')
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
        if h.hexdigest()!=hashes[name]:raise RuntimeError('HOLD_CHECKPOINT_HASH_CHANGED')
    if json.loads((path/'trainer_state.json').read_text()).get('global_step')!=5:
        raise RuntimeError('HOLD_CHECKPOINT_STEP_MISMATCH')
    return True

def main():
    """New explicitly pinned owner action; TASK_BOOST keeps training on HOLD."""
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');sha=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch(r'[0-9a-f]{40}',sha):raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    if OPERATION_MODE not in ('TASK_BOOST','TRAIN_AFTER_OPTIMIZATION'):raise RuntimeError('HOLD_OPERATION_MODE')
    state=ROOT/'state';fd=os.open(state/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    receipt=state/('owner_maintenance_'+request+'.json')
    if receipt.exists():raise RuntimeError('HOLD_REQUEST_ALREADY_STARTED_INSPECT_RECEIPT')
    backups=ROOT/'backup/owner_maintenance'/request
    result={'schema':'NOX_OWNER_OPTIMIZE_HYBRID_V1','request':request,'source_sha':sha,'started':time.time(),
            'steps':[],'training_started':False,'optimizer_steps_verified':False,'weights_deleted':0,
            's03_modified':False,'operation_mode':OPERATION_MODE,'chat_before':health(),'gpu_before':gpu()}
    success=False;controllers={};training_started=False;lock_held=True
    class BoostReady(Exception):pass
    def save():atomic(receipt,json.dumps(result,indent=2).encode())
    def step(kind,data):
        result['steps'].append({'kind':kind,'data':data,'time':time.time()});save();emit(kind,data)
    def backup(p):
        if p.is_symlink():raise RuntimeError('HOLD_SOURCE_SYMLINK')
        if p.exists():
            target=backups/str(p).lstrip('/')
            if target.exists():raise RuntimeError('HOLD_BACKUP_COLLISION')
            atomic(target,p.read_bytes())
    def install(p,data):
        before=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        backup(p);atomic(p,data);os.chmod(p,0o755)
        step('source_installed',{'path':str(p),'before':before,'after':hashlib.sha256(data).hexdigest()})
    def pause_service(name,script,controller=False):
        current=service_state(name);config=program_config(name)
        argv=shlex.split(config.get('command',''));bound=str(script) in argv
        if not bound:
            for arg in argv:
                launcher=Path(arg)
                if (launcher.parent==Path('/opt/supervisor-scripts') and launcher.suffix=='.sh'
                        and launcher.is_file() and not launcher.is_symlink() and launcher.stat().st_size<32000
                        and str(script) in launcher.read_text()):bound=True
        if not bound:raise RuntimeError('HOLD_SERVICE_COMMAND_SCOPE')
        if controller:controllers[name]=current
        if current['state'] in ('STOPPED','EXITED','FATAL'):return
        if current['state']!='RUNNING':raise RuntimeError('HOLD_SERVICE_STATUS')
        p=process(current['pid'])
        if not p or p['service']!=name or str(script) not in p['argv']:raise RuntimeError('HOLD_SERVICE_PROCESS_IDENTITY')
        group=[row for row in process_table().values() if row['pgrp']==p['pgrp'] and row['state']!='Z']
        if (config.get('stopasgroup','').lower()=='true' or config.get('killasgroup','').lower()=='true'):
            if any(row['service']!=name for row in group):raise RuntimeError('HOLD_SERVICE_GROUP_FOREIGN_ROLE')
        rc,_=command(['supervisorctl','stop',name],75)
        step('existing_service_paused',{'service':name,'rc':rc,'controller':controller})
        if service_state(name)['state'] not in ('STOPPED','EXITED'):raise RuntimeError('HOLD_SERVICE_NOT_STOPPED')
    def release_flags(allowed_prefix):
        for name in ('TRAIN_HOLD.flag','TRAIN_PAUSE_REQUEST.flag'):
            p=state/name
            if not p.exists():continue
            if p.is_symlink() or not p.read_text().startswith(allowed_prefix):raise RuntimeError('HOLD_NEW_OWNER_STOP_MUST_REMAIN')
            destination=backups/('released_'+str(time.time_ns())+'_'+name)
            destination.parent.mkdir(parents=True,exist_ok=True);p.rename(destination)
        step('owner_training_hold_released',{'preserved_in_backup':True})
    save()
    try:
        halt=json.loads((state/('owner_maintenance_'+HALT_REQUEST+'.json')).read_text())
        if halt.get('source_sha')!=HALT_SOURCE or halt.get('halt_verified') is not True:
            raise RuntimeError('HOLD_PRIOR_NATIVE_HALT_NOT_VERIFIED')
        current_hold=state/'TRAIN_HOLD.flag'
        if (not current_hold.is_file() or current_hold.is_symlink() or current_hold.stat().st_size>4096
                or not current_hold.read_text().startswith('OWNER_REQUESTED_TRAINING_HALT request='+HALT_REQUEST+' source='+HALT_SOURCE)):
            raise RuntimeError('HOLD_CURRENT_OWNER_TRAINING_STOP_NOT_RETAINED')
        if result['chat_before'].get('8081')!=200:raise RuntimeError('HOLD_CHAT_UNHEALTHY')
        verify_sources()
        if service_state()['state'] not in ('STOPPED','EXITED','FATAL'):raise RuntimeError('HOLD_TRAINER_NOT_STOPPED')
        if any(owns_training(p) and p['state']!='Z' and str(TRAINER) in p['argv'] for p in process_table().values()):
            raise RuntimeError('HOLD_NATIVE_TRAIN_PROCESS_REMAINING')
        g1=next((g for g in result['gpu_before']['gpus'] if g['index']==1),None)
        if not g1 or g1['free_mib']<27000:raise RuntimeError('HOLD_GPU1_HEADROOM')
        if any(p.exists() for p in (ROOT/'STOP',ROOT/'STOP.flag',ROOT/'stop.flag',state/'STOP')):
            raise RuntimeError('HOLD_GLOBAL_STOP_REMAINS')
        if OUTPUT.exists() and any(OUTPUT.iterdir()):raise RuntimeError('HOLD_EXISTING_HYBRID_RUN_INSPECT_RESUME')
        mentor,mentor_asset=bundle_module('owner_dispatcher_mentor')
        components,component_asset=bundle_module('owner_component_tasks')
        changed={}
        for path,transform in ((DISPATCHER,patch_dispatcher),(AUTOSCALE,patch_autoscale),
                               (SELFHEAL,patch_selfheal),(SCHEDULER,patch_scheduler)):
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=CONTROL_PINS[path.name]:
                raise RuntimeError('HOLD_NATIVE_CONTROL_SOURCE_CHANGED')
            transformed=transform(path.read_text())
            if path==DISPATCHER:transformed=mentor.transform_dispatcher(transformed)
            compile(transformed,str(path),'exec');changed[path]=transformed.encode()
        asset=base64.b64decode(BUNDLE.get('hybrid_training_entry.py',''),validate=True)
        if not asset:raise RuntimeError('HOLD_HYBRID_ENTRY_BUNDLE_MISSING')
        compile(asset,'hybrid_training_entry.py','exec')
        limit=int(Path('/sys/fs/cgroup/memory.max').read_text());used=int(Path('/sys/fs/cgroup/memory.current').read_text())
        quota,period=map(int,Path('/sys/fs/cgroup/cpu.max').read_text().split())
        budget=resource_budget(limit,used,max(1,quota//period),len(os.sched_getaffinity(0)))
        result['resource_budget']=budget;step('native_admission_verified',{'gpu1':g1,'budget':budget})
        if OPERATION_MODE=='TASK_BOOST':
            backup(BOOST_FLAG)
            atomic(BOOST_FLAG,json.dumps({'schema':'NOX_OWNER_TASK_BOOST_V1','enabled':True,
                'mode':'TASK_BOOST','request':request,'source_sha':sha,'started':time.time(),
                'training_allowed':False},indent=2).encode())
            step('task_boost_latched',{'training_allowed':False,'training_hold_retained':True})
        for name,script in (('nox-dispatcher-t855u',DISPATCHER),('nox-priority-scheduler',SCHEDULER),('nox-selfheal',SELFHEAL)):
            pause_service(name,script,controller=True)
        if OPERATION_MODE=='TASK_BOOST':
            for name,script in HEAVY_SERVICES.items():pause_service(name,script)
        for path,data in changed.items():install(path,data)
        install(ROOT/'scripts/hybrid_training_entry.py',asset)
        install(ROOT/'scripts/owner_dispatcher_mentor.py',mentor_asset)
        install(ROOT/'scripts/owner_component_tasks.py',component_asset)
        for optional in ('owner_capacity_probe.py',):
            if optional in BUNDLE:
                data=base64.b64decode(BUNDLE[optional],validate=True);compile(data,optional,'exec')
                install(ROOT/'scripts'/optional,data)
        manifest=base64.b64decode(BUNDLE.get('download_manifest.json',''),validate=True)
        if not manifest or not isinstance(json.loads(manifest),dict):raise RuntimeError('HOLD_DOWNLOAD_MANIFEST_MISSING')
        install(ROOT/'config/owner_download_manifest.json',manifest)
        worker_path=ROOT/'config/dispatcher_agents_t868u.json'
        existing=json.loads(worker_path.read_text())
        worker_configuration=mentor.worker_config(existing)
        install(worker_path,json.dumps(worker_configuration,ensure_ascii=False,indent=2).encode())
        result['worker_configuration']=worker_configuration
        env=('TRAIN_CPU_MAX=%dGiB\nOMP_NUM_THREADS=%d\nMKL_NUM_THREADS=%d\nOPENBLAS_NUM_THREADS=1\nTOKENIZERS_PARALLELISM=false\n' %
             (budget['train_cpu_gib'],budget['omp_threads'],budget['omp_threads'])).encode()
        install(state/'train_cpu_max.env',env)
        install(WRAPPER,wrapper_source(request).encode())
        if command(['bash','-n',str(WRAPPER)])[0]:raise RuntimeError('HOLD_WRAPPER_SYNTAX')
        if OPERATION_MODE=='TASK_BOOST':
            teachers=[p for p in process_table().values() if teacher_role(p) and p['state']!='Z']
            for sig,wait in ((signal.SIGTERM,12),(signal.SIGKILL,4)):
                sent=[]
                for p in teachers:
                    try:
                        if signal_teacher(p,sig):sent.append({'pid':p['pid'],'port':teacher_role(p)})
                    except ProcessLookupError:pass
                if sent:
                    step('owned_auxiliary_teachers_yielded',{'signal':sig.name,'processes':sent})
                    deadline=time.monotonic()+wait
                    while time.monotonic()<deadline and any(teacher_role(process(p['pid'])) for p in teachers):time.sleep(1)
            if any(teacher_role(p) and p['state']!='Z' for p in process_table().values()):raise RuntimeError('HOLD_AUXILIARY_TEACHERS_STILL_RUNNING')
        # One registration transaction while the dispatcher and every known
        # direct state writer are paused. Preserve the previous task history.
        tasks=components.queue_tasks()
        if len(tasks)!=6 or len({t['id'] for t in tasks})!=6:raise RuntimeError('HOLD_SIX_COMPONENT_TASK_SCHEMA')
        state_path=ROOT/'state/dispatcher/state.json';queue_path=ROOT/'state/dispatcher/queue.jsonl'
        dispatcher_state=json.loads(state_path.read_text())
        if not isinstance(dispatcher_state.get('tasks'),dict):raise RuntimeError('HOLD_NATIVE_QUEUE_SCHEMA')
        additions=[task for task in tasks if task['id'] not in dispatcher_state['tasks']]
        if additions:
            backup(state_path);backup(queue_path)
            for task in additions:dispatcher_state['tasks'][task['id']]=task
            atomic(state_path,json.dumps(dispatcher_state,ensure_ascii=False,indent=2).encode())
            before=queue_path.read_bytes() if queue_path.exists() else b''
            if before and not before.endswith(b'\n'):before+=b'\n'
            atomic(queue_path,before+b''.join((json.dumps(t,ensure_ascii=False)+'\n').encode() for t in additions))
        step('native_component_jobs_registered',{'task_ids':[t['id'] for t in tasks],
                                               'new_count':len(additions),'old_history_preserved':True})
        restarted_at=time.time()
        for name,old in controllers.items():
            if old['state']=='RUNNING':
                rc,_=command(['supervisorctl','start',name],30)
                step('existing_controller_restarted',{'name':name,'rc':rc})
                if service_state(name)['state'] not in ('RUNNING','STARTING'):raise RuntimeError('HOLD_CONTROLLER_RESTART')
        if health().get('8081')!=200:raise RuntimeError('HOLD_CHAT_HEALTH_BEFORE_TRAINING')
        if OPERATION_MODE=='TASK_BOOST':
            if not (state/'TRAIN_HOLD.flag').is_file() or service_state()['state'] not in ('STOPPED','EXITED','FATAL'):
                raise RuntimeError('HOLD_TASK_BOOST_TRAINING_NOT_PAUSED')
            # Configuration mutations are finished. Release the one writer lock
            # so the six real workers can claim the registered tasks while the
            # rest of this action only reads receipts and status.
            fcntl.flock(fd,fcntl.LOCK_UN);lock_held=False
            deadline=time.monotonic()+35;worker_readback=None
            status_path=ROOT/'status/agents_t856u.json'
            while time.monotonic()<deadline:
                try:
                    observed=json.loads(status_path.read_text())
                    rows=observed.get('workers',[])
                    claimed=[r['current_task']['id'] for r in rows if isinstance(r.get('current_task'),dict)]
                    if status_path.stat().st_mtime>=restarted_at and observed.get('n')==6 and len(rows)==6:
                        if len(claimed)!=len(set(claimed)):raise RuntimeError('HOLD_DUPLICATE_NATIVE_TASK_CLAIM')
                        current=service_state('nox-dispatcher-t855u')
                        if current['state']!='RUNNING':raise RuntimeError('HOLD_DISPATCHER_NOT_RUNNING')
                        st=(PROC/str(current['pid'])/'status').read_text()
                        match=re.search(r'^Threads:\s*(\d+)',st,re.M)
                        worker_readback={'dispatcher_pid':current['pid'],'process_threads':int(match[1]) if match else None,
                            'worker_ids':[r.get('id') for r in rows],'workers':6,'busy_count':len(claimed),
                            'claimed_task_ids':claimed,'native_status_mtime':status_path.stat().st_mtime}
                        break
                except (OSError,ValueError,KeyError,TypeError):pass
                time.sleep(2)
            if worker_readback is None:raise RuntimeError('HOLD_SIX_NATIVE_WORKERS_NOT_VERIFIED')
            result['native_workers']=worker_readback;step('six_native_workers_verified',worker_readback)
            result['state']='TASK_BOOST_SIX_NATIVE_WORKERS_ACTIVE_TRAINING_PAUSED'
            result['hybrid_training_installed']=True
            result['training_started']=False
            step('task_boost_verified',{'training_started':False,'hybrid_entry_installed_disabled':True,
                                       'held_training':True,'chat_healthy':True})
            raise BoostReady()
        release_flags('OWNER_REQUESTED_TRAINING_HALT request='+HALT_REQUEST+' ')
        rc,_=command(['supervisorctl','start',SERVICE],35)
        result['training_started']=training_started=service_state()['state'] in ('RUNNING','STARTING')
        step('bounded_training_started',{'rc':rc,'service':service_state(),'max_steps':5,'planned_steps':1000})
        if not training_started:raise RuntimeError('HOLD_HYBRID_TRAINER_START')
        deadline=time.monotonic()+400;last=None
        while time.monotonic()<deadline:
            result_file=OUTPUT/'owner_last_result.json'
            if result_file.is_file():
                candidate=json.loads(result_file.read_text());verify_five_result(candidate)
                result['five_step_receipt']=candidate;result['optimizer_steps_verified']=True
                step('five_steps_independently_verified',{'global_step':5,'finite_loss':candidate['loss'],
                     'adapter_tensor_changed':True,'seven_checkpoint_hashes_verified':True})
                break
            current=progress()
            if current!=last:step('training_progress',current);last=current
            if service_state()['state'] in ('STOPPED','EXITED','FATAL'):
                raise RuntimeError('HOLD_BOUNDED_TRAINING_EXITED_WITHOUT_RESULT')
            time.sleep(10)
        if not result['optimizer_steps_verified']:
            result['state']='BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING';success=True
        else:
            # Wait for the same supervised wrapper to exit and latch completion.
            deadline=time.monotonic()+35
            while service_state()['state'] in ('RUNNING','STARTING') and time.monotonic()<deadline:time.sleep(2)
            if service_state()['state'] not in ('STOPPED','EXITED'):raise RuntimeError('HOLD_FIRST_RUN_NOT_TERMINAL')
            if health().get('8081')!=200:raise RuntimeError('HOLD_CHAT_HEALTH_BEFORE_CONTINUATION')
            # Preserve the first wrapper in a second named backup before updating
            # the same service to a verified optimizer continuation.
            atomic(backups/'first_five_wrapper.sh',WRAPPER.read_bytes())
            atomic(WRAPPER,wrapper_source(request,1000,True).encode());os.chmod(WRAPPER,0o755)
            release_flags('OWNER_HYBRID_BOUNDED_COMPLETE request='+request)
            rc,_=command(['supervisorctl','start',SERVICE],35)
            if service_state()['state'] not in ('RUNNING','STARTING'):raise RuntimeError('HOLD_CONTINUATION_START_FAILED')
            result['state']='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED';result['continuation_target_steps']=1000
            step('existing_training_continuation_started',{'rc':rc,'resume_checkpoint':5,'target_steps':1000})
            success=True
    except BoostReady:
        success=True
    except Exception as exc:
        code=str(exc);result['state']='HOLD_OPTIMIZATION_OR_TRAINING'
        result['error']=code if re.fullmatch(r'HOLD_[A-Z0-9_]+',code) else type(exc).__name__
        if lock_held and not (state/'TRAIN_HOLD.flag').exists():
            atomic(state/'TRAIN_HOLD.flag',('OWNER_OPTIMIZATION_FAILED request='+request+'\n').encode())
    finally:
        # Restore original controllers only; HOLD blocks training after failures.
        for name,old in controllers.items():
            if lock_held and old['state']=='RUNNING' and service_state(name)['state'] in ('STOPPED','EXITED'):
                rc,_=command(['supervisorctl','start',name],30)
                result['steps'].append({'kind':'controller_restored_in_finalizer','data':{'name':name,'rc':rc},'time':time.time()})
        result.update(finished=time.time(),hold_retained=(state/'TRAIN_HOLD.flag').exists(),service_after=service_state(),
                      chat_after=health(),gpu_after=gpu(),progress_after=progress())
        if success and OPERATION_MODE=='TASK_BOOST':
            try:result['postflight_inventory']=postflight_inventory()
            except Exception as exc:result['postflight_inventory_error']=type(exc).__name__
        if result['chat_after'].get('8081')!=200:result['chat_health_regression']=True;success=False
        save();emit('native_optimization_receipt',result);os.close(fd)
    if success:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if success else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        code=str(exc);emit('failure',code if re.fullmatch(r'HOLD_[A-Z0-9_]+',code) else type(exc).__name__)
        raise SystemExit(2)
