#!/usr/bin/env python3
"""Bounded CPU policy update through the existing owner maintenance route.
No source tree writes, task reset, model restart, or new dispatcher is introduced.
Common helpers are frozen from 2be2752f4e784e94db08159e39b852ec2f22a513f080247740eaf6bdc625c640.
"""

from __future__ import annotations
import base64
import contextlib
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path('/root/nox')

SERVICE = 'nox-dispatcher-t855u'

CONFIG = 'config/owner_native_subagents.json'

STATE = 'state/dispatcher/state.json'

STATUS = 'status/agents_t856u.json'

MAX_BYTES = 32*1024*1024

SHA = re.compile(r'^[a-f0-9]{64}$')

IDENT = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')

QUEUE_IDS = ('Q1_RUNTIME_CHAT','Q2_MEMORY_KNOWLEDGE','Q3_TRAINING_WEIGHTS','Q4_INTEGRATION_ACCEPTANCE')

PROJECT_HANDLER = 'owner_native_project_work'

class Hold(RuntimeError):
    pass

def require(condition, code):
    if not condition:
        raise Hold('HOLD_COMPLETE_EXECUTOR_' + code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()

def read_regular(path, maximum=MAX_BYTES):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in
            (path, *path.parents)), 'PATH_SCOPE')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                'FILE_BOUND')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and (before.st_dev, before.st_ino,
            before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino,
            after.st_size, after.st_mtime_ns), 'FILE_CHANGED')
    return raw

def atomic(path, raw, mode=0o600):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'PATH_SCOPE')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.nox-project-executor-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def preimages(root, expected):
    result = {}
    for relative, pin in expected.items():
        require(SHA.fullmatch(pin) is not None, 'EXPECTED_SOURCE_PIN')
        raw = read_regular(Path(root) / relative)
        require(digest(raw) == pin, 'PREIMAGE_' + Path(relative).name)
        result[relative] = raw
    return result

def apply_transaction(root, changes, before):
    """Compare immediately before each write; roll back only our own bytes."""
    applied = []
    try:
        for relative, raw in changes.items():
            path = Path(root) / relative
            previous = before.get(relative)
            try:
                current = read_regular(path)
            except FileNotFoundError:
                current = None
            require(current == previous, 'CONCURRENT_FILE_CHANGE_' + Path(relative).name)
            applied.append(relative)
            atomic(path, raw, 0o644 if relative.endswith('.py') else 0o600)
            require(read_regular(path) == raw, 'WRITE_READBACK_' + Path(relative).name)
        return applied
    except BaseException:
        rollback_transaction(root, changes, before, applied)
        raise

def rollback_transaction(root, changes, before, applied):
    outcomes = {}
    for relative in reversed(applied):
        path = Path(root) / relative
        try:
            if read_regular(path) != changes[relative]:
                outcomes[relative] = 'FOREIGN_CHANGE_PRESERVED'
            elif before.get(relative) is None:
                # Unreferenced additive files are retained. No existing data is deleted.
                outcomes[relative] = 'ADDITIVE_FILE_RETAINED_UNREFERENCED'
            else:
                atomic(path, before[relative], 0o644 if relative.endswith('.py') else 0o600)
                outcomes[relative] = 'PREIMAGE_RESTORED'
        except (OSError, Hold):
            outcomes[relative] = 'ROLLBACK_IO_FAILED'
    return outcomes

def supervisor(action, name=SERVICE):
    require(name == SERVICE and action in ('status', 'stop', 'start'), 'SUPERVISOR_SCOPE')
    result = subprocess.run(['supervisorctl', action, name], capture_output=True,
                            text=True, timeout=25)
    if action == 'status':
        match = re.fullmatch(re.escape(name) + r'\s+(RUNNING|STOPPED|STARTING|STOPPING|BACKOFF|FATAL|EXITED)\b(?:\s+pid\s+(\d+))?.*',
                             result.stdout.strip())
        require(match is not None, 'SERVICE_STATUS')
        return {'state': match[1], 'pid': int(match[2]) if match[2] else None}
    require(result.returncode == 0, 'SERVICE_' + action.upper())
    return {'action': action, 'rc': result.returncode}

def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    try:
        tail = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        if tail[0] not in ('R', 'S', 'D', 'I'):
            return None
        return {'pid': pid, 'start_ticks': int(tail[19]),
                'ppid': int(tail[1]), 'pgrp': int(tail[2])}
    except (OSError, ValueError, IndexError):
        return None

def stop_clear(root):
    names = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
             'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    return not any(path.exists() or path.is_symlink() for path in
                   [*(Path(root) / name for name in names), Path('/workspace/NOX_STOP')])

def queue_idle(root):
    value = json.loads(read_regular(Path(root) / STATE))
    require(isinstance(value.get('tasks'), dict), 'QUEUE_SCHEMA')
    active = [key for key, row in value['tasks'].items()
              if isinstance(row, dict) and row.get('status') == 'running']
    return value, active

def protected_snapshot(specification):
    result = {}
    for label, expected in specification['protected_processes'].items():
        identity = process_identity(expected['pid'])
        require(identity and identity['start_ticks'] == expected['start_ticks'],
                'PROTECTED_PROCESS_' + label)
        result[label] = identity
    return result

def descendant_snapshot(director_pid, proc_root=Path('/proc')):
    """Bounded exact process census; it authorizes no signals or child kills."""
    require(type(director_pid) is int and director_pid>1,'CHILD_CENSUS_DIRECTOR')
    pending=[director_pid];seen=set();result={}
    while pending:
        parent=pending.pop(0)
        if parent in seen:continue
        seen.add(parent);require(len(seen)<=64,'CHILD_CENSUS_BOUND')
        try:threads=list((Path(proc_root)/str(parent)/'task').iterdir())
        except FileNotFoundError:continue
        require(len(threads)<=128,'CHILD_CENSUS_THREAD_BOUND')
        for thread in threads:
            if not thread.name.isdigit():continue
            try:text=(thread/'children').read_text()
            except FileNotFoundError:continue
            require(len(text)<=4096,'CHILD_CENSUS_OUTPUT_BOUND')
            children=text.split();require(all(x.isdigit() for x in children),'CHILD_CENSUS_SCHEMA')
            for child in map(int,children):
                identity=process_identity(child)
                if identity is None:continue
                require(identity['ppid']==parent,'CHILD_CENSUS_PARENT_CHANGED')
                if child!=director_pid:
                    result[child]=identity;pending.append(child)
    return [result[pid] for pid in sorted(result)]

def live_previous_descendants(previous):
    result=[]
    for old in previous:
        current=process_identity(old['pid'])
        # Reparented old workers still count; a reused PID with new start ticks does not.
        if current and current['start_ticks']==old['start_ticks']:result.append(current)
    return result

def wait_previous_descendants_stopped(previous, timeout=8):
    deadline=time.monotonic()+timeout
    while True:
        remaining=live_previous_descendants(previous)
        if not remaining:return {'observed':len(previous),'all_exact_processes_exited':True}
        require(time.monotonic()<deadline,'OLD_CHILDREN_ALIVE_NO_NATIVE_RESTART')
        time.sleep(.25)

def stop_checked():
    observed = supervisor('status')
    previous = process_identity(observed.get('pid'))
    if observed['state'] not in ('STOPPED', 'FATAL', 'EXITED'):
        try:
            supervisor('stop')
        except (OSError, subprocess.SubprocessError, Hold):
            pass  # The control response is not authoritative; reconcile the actual service.
    deadline = time.monotonic() + 15
    while True:
        current = supervisor('status')
        old_alive = process_identity(previous['pid']) if previous else None
        if (current['state'] in ('STOPPED', 'FATAL', 'EXITED')
                and (old_alive is None or old_alive != previous)):
            return current
        require(time.monotonic() < deadline, 'STOP_NOT_VERIFIED_NO_FILE_ROLLBACK')
        time.sleep(.5)

def start_checked(root, require_native_status=True):
    try:
        supervisor('start')
    except (OSError, subprocess.SubprocessError, Hold):
        pass
    deadline = time.monotonic() + 20
    stable = None
    stable_since = None
    while time.monotonic() < deadline:
        observed = supervisor('status')
        identity = process_identity(observed.get('pid'))
        if observed['state'] == 'RUNNING' and identity:
            loaded = not require_native_status
            try:
                status_doc = json.loads(read_regular(Path(root) / STATUS, 2 * 1024 * 1024))
                native = status_doc.get('native_subexecutors') or {}
                director = native.get('director') or {}
                loaded = (director.get('pid') == identity['pid']
                    and director.get('process_starttime') == identity['start_ticks']
                    and 0 <= time.time() - native.get('observed_at', 0) <= 15)
            except (OSError, ValueError, TypeError, Hold):
                pass
            if loaded:
                if identity != stable:
                    stable, stable_since = identity, time.monotonic()
                elif time.monotonic() - stable_since >= 2:
                    return identity
        elif observed['state'] in ('FATAL', 'EXITED'):
            break
        time.sleep(.5)
    raise Hold('HOLD_COMPLETE_EXECUTOR_STARTUP_NOT_VERIFIED')

def relpath(value):
    require(isinstance(value,str) and 1<=len(value)<=240 and not value.startswith('/')
            and '\\' not in value and '\x00' not in value, 'RELATIVE_PATH')
    pieces=value.split('/')
    require(all(piece not in ('','.','..') and not piece.startswith('.') for piece in pieces), 'RELATIVE_PATH')
    return value

def acceptance_snapshot(root, task_ids):
    status=json.loads(read_regular(Path(root)/STATUS,2*1024*1024));native=status.get('native_subexecutors') or {}
    director=supervisor('status');observed=process_identity(director.get('pid'))
    workers=[]
    for row in native.get('workers',[])[:10]:
        identity=process_identity(row.get('pid'))
        if (observed and identity and identity['ppid']==observed['pid']
                and identity['start_ticks']==row.get('process_starttime')
                and type(row.get('heartbeat_at')) in (int,float)
                and 0<=time.time()-row['heartbeat_at']<=30):
            workers.append({**identity,'role':row.get('role'),'current_task':row.get('current_task'),
                            'heartbeat_at':row.get('heartbeat_at')})
    state,_=queue_idle(root)
    tasks=[{'id':tid,'status':state['tasks'].get(tid,{}).get('status','not_admitted'),
            'claim_present':bool(state['tasks'].get(tid,{}).get('owner_claim'))} for tid in task_ids]
    return {'director':observed,'workers':workers,'tasks':tasks,'observed_at':time.time(),
            'native_last_admission':native.get('last_admission')}

def stable_three(snapshots):
    if len(snapshots)!=2:return False
    a,b=snapshots
    identity=lambda row:(row['pid'],row['start_ticks'],row['ppid'])
    if (len(a.get('workers',[]))!=3 or len(b.get('workers',[]))!=3
            or not a.get('director') or a['director']!=b.get('director')):return False
    old={identity(row):row for row in a['workers']};new={identity(row):row for row in b['workers']}
    if len(old)!=3 or set(old)!=set(new):return False
    return (b['observed_at']-a['observed_at']>=1
            and all(new[key]['heartbeat_at']>old[key]['heartbeat_at'] for key in old))

def exact_s03(root,receipt):
    path=Path(root)/'kb/knowledge.sqlite'
    require(not any(p.is_symlink() for p in (path,*path.parents)) and stat.S_ISREG(path.stat().st_mode),'UPDATE_S03_PATH')
    pin=digest(encoded(receipt));text='NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+pin
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)) as connection:
        connection.execute('PRAGMA query_only=ON');deadline=time.monotonic()+2
        connection.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        rows=connection.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                                (text,'owner_native_subagents')).fetchall()
    require(len(rows)==1 and rows[0][2]==digest(('M2|'+text).encode())
            and json.loads(rows[0][1]).get('receipt')==receipt,'UPDATE_S03_EXACT')
    return {'verified':True,'receipt_sha256':pin,'s03_item_id':rows[0][0]}

def source_snapshot(root,config):
    source=Path(root)/'projects/owner_executor/source_workspace'
    require(source.is_dir() and not any(p.is_symlink() for p in (source,*source.parents)),'UPDATE_SOURCE_ROOT')
    allowed=config['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths']
    require(isinstance(allowed,list) and 1<=len(allowed)<=256 and len(set(allowed))==len(allowed),'UPDATE_SOURCE_ALLOWED')
    allowed=set(relpath(p) for p in allowed)
    marker=read_regular(source/'NOX_EXECUTOR_BOOTSTRAP.json',65536);owner=json.loads(marker)
    require(owner.get('schema')=='NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
            and owner.get('root')==str(source) and set(owner.get('file_pins',{}))==allowed,'UPDATE_SOURCE_OWNER')
    seen={};total=0;directories=0
    for directory,names,files in os.walk(source,followlinks=False):
        directories+=1;require(directories<=128,'UPDATE_SOURCE_DIRECTORY_BOUND')
        here=Path(directory)
        for name in list(names):
            child=here/name;require(not child.is_symlink(),'UPDATE_SOURCE_SYMLINK')
            if here==source and name=='.git':names.remove(name)
            else:relpath(str(child.relative_to(source)))
        for name in files:
            relative=str((here/name).relative_to(source))
            if relative=='NOX_EXECUTOR_BOOTSTRAP.json':continue
            require(relative in allowed,'UPDATE_UNKNOWN_SOURCE_FILE')
            raw=read_regular(here/name,2*1024*1024);info=(here/name).stat();total+=len(raw)
            require(total<=16*1024*1024,'UPDATE_SOURCE_BYTES')
            seen[relative]={'sha256':digest(raw),'mode':stat.S_IMODE(info.st_mode),'size':len(raw)}
    require(set(seen)==allowed,'UPDATE_SOURCE_FILESET')
    git=source/'.git';require(git.is_dir() and not git.is_symlink(),'UPDATE_GIT_ROOT')
    head=read_regular(git/'HEAD',4096);git_pins={'HEAD':digest(head)}
    if head.startswith(b'ref: '):
        reference=head[5:].decode('ascii').strip();require(reference.startswith('refs/heads/'),'UPDATE_GIT_HEAD')
        relpath(reference);git_pins[reference]=digest(read_regular(git/reference,4096))
    else:require(re.fullmatch(rb'[a-f0-9]{40}\n?',head),'UPDATE_GIT_HEAD')
    if (git/'index').exists():git_pins['index']=digest(read_regular(git/'index',2*1024*1024))
    return {'files':seen,'files_sha256':digest(encoded(seen)),'count':len(seen),'total_bytes':total,
            'bootstrap_sha256':digest(marker),'git_pins':git_pins,'root':str(source)}

def start_update_checked(root,owned):
    require(supervisor('status')['state'] in ('STOPPED','FATAL','EXITED'),'UPDATE_START_REQUIRES_STOPPED')
    try:supervisor('start')
    except (OSError,subprocess.SubprocessError,Hold):pass
    deadline=time.monotonic()+20;stable_since=None
    while time.monotonic()<deadline:
        observed=supervisor('status');identity=process_identity(observed.get('pid'))
        if observed['state']=='RUNNING' and identity:
            if not owned:owned.append(identity)
            require(identity==owned[0],'UPDATE_STARTED_DIRECTOR_REPLACED')
            try:
                doc=json.loads(read_regular(Path(root)/STATUS,2*1024*1024));native=doc.get('native_subexecutors') or {}
                director=native.get('director') or {};at=native.get('observed_at')
                loaded=(director.get('pid')==identity['pid'] and director.get('process_starttime')==identity['start_ticks']
                    and type(at) in (int,float) and 0<=time.time()-at<=15)
            except (OSError,ValueError,TypeError,Hold):loaded=False
            if loaded:
                if stable_since is None:stable_since=time.monotonic()
                elif time.monotonic()-stable_since>=2:return identity
        elif observed['state'] in ('FATAL','EXITED'):break
        time.sleep(.5)
    raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_STARTUP_NOT_VERIFIED')

SPEC = {'schema': 'NOX_BOUNDED_CPU_POLICY_INSTALL_SPEC_V1', 'assets': {'bc_runtime_d5fb476f53e64d2014f2.py': 'd5fb476f53e64d2014f27465c7bd64192158b5bcdd79a72ff7c962d853602339', 'bc_runtime_6c67e567e669b993d016.py': '6c67e567e669b993d016ea1d6137a03f3567e564d2b35696edf665a27e0f4756', 'bc_runtime_2c83ec53f7ee7c2d76bc.py': '2c83ec53f7ee7c2d76bc1fac21c80adf76c58f83c5a219ba0294f9b3f713d707', 'bc_runtime_294473d35d4870f50467.py': '294473d35d4870f50467d843c551c9b9fd7c4644e4b615e92403dc916ed109e4'}, 'runtime_paths': {'bc_runtime_d5fb476f53e64d2014f2.py': 'scripts/owner_autonomy_pool.py', 'bc_runtime_6c67e567e669b993d016.py': 'scripts/owner_subagent_dispatcher.py', 'bc_runtime_2c83ec53f7ee7c2d76bc.py': 'scripts/owner_project_native.py', 'bc_runtime_294473d35d4870f50467.py': 'scripts/owner_subagent_instruction_truth.py'}, 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_autonomy_pool.py': '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102', 'scripts/owner_subagent_instruction_truth.py': '485d4a4a571c434afb98512547a7f2a2198606eb1e168b749ae607aaf3c2133f', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'config/owner_native_subagents.json': 'db6a773a09af6de6a1c4d01a188a08c845f1874f3198ea2fd50a2877048d60aa', 'scripts/owner_project_executor.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': '52e62a143d16f387899ff1737ce4eb698dee5ceca510fc6f97f931c11a0aec10', 'scripts/owner_project_native.py': 'd0ff44d4752128c267799202620c34d2503241dad1f7008f8b3539f49efc18b5', 'scripts/owner_project_planner.py': 'aa0dd1c8266106b599ce83b64b7af77c7a4f32377fc09cd545e1f9697bda4420', 'scripts/owner_project_test_runner.py': '84d54c647b0a63447aca91d34b90372e36dcd59442e3066458a21688fcb5a595'}, 'expected_director': {'pid': 3748557, 'start_ticks': 176081802}, 'expected_no_children': True, 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}, 'rebind_task_ids': ['3A02.project.readback_revoke.layout_retry.20261118', '3B05.project.strict_skill_json.layout_retry.20261118', '6V14-04.project.receipt_time_order.fd_retry.20261118', '1A03.project.cursor_admission.focus_retry.20261118']}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BUDGET_UPDATE_SCHEMA='NOX_BOUNDED_CPU_POLICY_INSTALL_SPEC_V1'
BUDGET_MODULES=frozenset({'owner_subagent_dispatcher.py','owner_autonomy_pool.py',
    'owner_project_native.py','owner_subagent_instruction_truth.py'})
MIB=1024*1024
GIB=1024*MIB

def budget_assets(bundle,specification):
    require(specification.get('schema')==BUDGET_UPDATE_SCHEMA,'BUDGET_SPEC_SCHEMA')
    pins=specification.get('assets');paths=specification.get('runtime_paths')
    require(isinstance(pins,dict) and isinstance(paths,dict) and set(pins)==set(bundle)==set(paths)
            and len(pins)==4 and set(paths.values())=={'scripts/'+name for name in BUDGET_MODULES},'BUDGET_MODULE_SET')
    result={}
    for name,pin in pins.items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name)
                and SHA.fullmatch(str(pin)) and isinstance(bundle[name],str) and len(bundle[name])<=512*1024,'BUDGET_ASSET_PIN')
        raw=base64.b64decode(bundle[name],validate=True)
        require(len(raw)<=256*1024 and digest(raw)==pin,'BUDGET_ASSET_HASH')
        compile(raw,paths[name],'exec');result[paths[name]]=raw
    return result

def compose_budget_config(raw,runtime,specification):
    config=json.loads(raw);catalog=config.get('catalog') or {};old=catalog.get('tasks')
    require(config.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and config.get('instance_id')==60509551
            and config.get('owner_authorized') is True and config.get('mode')=='NORMAL' and config.get('target')==3
            and config.get('global_worker_cap')==3 and config.get('execution_mode')=='NATIVE_PROJECT_V1','BUDGET_CONFIG_SCOPE')
    require(catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1' and isinstance(old,list) and len(old)==19
            and digest(encoded(catalog))==config.get('catalog_sha256'),'BUDGET_CATALOG_PREIMAGE')
    previous=config.get('module_pins',{}).get('owner_subagent_dispatcher.py')
    require(SHA.fullmatch(str(previous)) and previous==specification['expected_native'].get('scripts/owner_subagent_dispatcher.py'),
            'BUDGET_PREVIOUS_CALLBACK')
    ids=specification.get('rebind_task_ids');require(isinstance(ids,list) and len(ids)==len(set(ids))==4,'BUDGET_REBIND_COUNT')
    require(set(ids)=={row['id'] for row in old[15:]},'BUDGET_REBIND_EXACT_LAST_FOUR')
    require({row.get('params',{}).get('parent_task_id') for row in old[15:]}=={'1A03','3A02','3B05','6V14-04'},'BUDGET_REBIND_PARENTS')
    for row in old[15:]:
        require(row.get('handler')==PROJECT_HANDLER and row.get('source_sha256')==previous
                and row.get('resource')=='CPU_LIGHT' and row.get('queue_id') in QUEUE_IDS,'BUDGET_REBIND_SCOPE')
    result=copy.deepcopy(config);callback=digest(runtime['scripts/owner_subagent_dispatcher.py'])
    require(callback!=previous,'BUDGET_CALLBACK_UNCHANGED')
    for name in BUDGET_MODULES:
        require(name in config['module_pins'],'BUDGET_EXISTING_MODULE')
        result['module_pins'][name]=digest(runtime['scripts/'+name])
    for row in result['catalog']['tasks'][15:]:row['source_sha256']=callback
    result['catalog_sha256']=digest(encoded(result['catalog']))
    for key in ('historical_project_source_sha256','historical_leaf_source_sha256'):
        values=config.get(key,[])
        require(isinstance(values,list) and len(values)<=16 and all(SHA.fullmatch(str(v)) for v in values),'BUDGET_HISTORICAL_PINS')
        result[key]=sorted(set(values)|{previous})
    check=copy.deepcopy(result);check['catalog']=config['catalog'];check['catalog_sha256']=config['catalog_sha256']
    for name in BUDGET_MODULES:check['module_pins'][name]=config['module_pins'][name]
    for key in ('historical_project_source_sha256','historical_leaf_source_sha256'):
        if key in config:check[key]=config[key]
        else:check.pop(key,None)
    require(check==config and result['catalog']['tasks'][:15]==old[:15],'BUDGET_UNRELATED_CONFIG_CHANGE')
    return config,result

def absent_retry_rows(state,ids):
    require(all(tid not in state['tasks'] for tid in ids),'BUDGET_RETRY_ALREADY_ADMITTED')

def project_history_proofs(root,state,config):
    rows={tid:row for tid,row in state['tasks'].items() if row.get('handler')==PROJECT_HANDLER}
    require(len(rows)==7,'BUDGET_EXISTING_PROJECT_COUNT')
    allowed={config['module_pins']['owner_subagent_dispatcher.py'],*config.get('historical_project_source_sha256',[])}
    proofs={}
    for tid,row in rows.items():
        result=row.get('result') or {};receipt=result.get('receipt') or {}
        phase='PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED' if row.get('status')=='done' else 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
        require(row.get('status') in ('done','blocked') and result.get('verified') is True
                and receipt.get('task_id')==tid and receipt.get('claim')==row.get('owner_claim')
                and receipt.get('original_task_accepted') is False and receipt.get('source_sha256') in allowed
                and receipt.get('phase')==phase and result.get('receipt_sha256')==digest(encoded(receipt)),
                'BUDGET_EXISTING_PROJECT_RECEIPT')
        proofs[tid]=exact_s03(root,receipt)
    return proofs

def preserve_terminal_history(before,after):
    old=before['tasks'];new=after['tasks'];missing=sorted(set(old)-set(new))
    terminal={tid:row for tid,row in old.items() if row.get('status') in ('done','completed','failed','blocked','cancelled','canceled')
        or row.get('native_project_terminal')}
    changed=[];resumed=[]
    for tid,row in old.items():
        different=any(row.get(field)!=new.get(tid,{}).get(field) for field in ('owner_claim','result','native_project_terminal'))
        if different:
            if tid in terminal:changed.append(tid)
            else:resumed.append({'id':tid,'old_status':row.get('status'),'new_status':new.get(tid,{}).get('status'),
                'old_claim_sha256':digest(encoded(row.get('owner_claim'))),
                'new_claim_sha256':digest(encoded(new.get(tid,{}).get('owner_claim'))),
                'same_result':row.get('result')==new.get(tid,{}).get('result')})
    return {'old_count':len(old),'missing_old_ids':missing,'terminal_rows_checked':len(terminal),
        'changed_terminal_claim_result_ids':changed,'nonterminal_claim_changes':resumed[:100],
        'nonterminal_claim_changes_count':len(resumed),'verified':not missing and not changed}

def zero_children_guard(specification):
    require(specification.get('expected_no_children') is True,'BUDGET_ZERO_CHILDREN_CONTRACT')
    expected=specification['expected_director'];identity=process_identity(expected['pid'])
    require(identity and identity['start_ticks']==expected['start_ticks'],'BUDGET_DIRECTOR_CHANGED')
    status=supervisor('status');require(status['state']=='RUNNING' and status.get('pid')==identity['pid'],'BUDGET_SUPERVISOR_IDENTITY')
    children=descendant_snapshot(identity['pid']);require(not children,'BUDGET_UNEXPECTED_DIRECTOR_CHILDREN')
    return {'director':identity,'children':children,'observed_at':time.time()}

def wait_idle_zero_children(root,specification,timeout=40):
    deadline=time.monotonic()+timeout
    while True:
        require(stop_clear(root),'BUDGET_OWNER_STOP_DURING_DRAIN')
        state,active=queue_idle(root);absent_retry_rows(state,specification['rebind_task_ids'])
        try:observed=zero_children_guard(specification)
        except Hold as exc:
            if str(exc)!='HOLD_COMPLETE_EXECUTOR_BUDGET_UNEXPECTED_DIRECTOR_CHILDREN':raise
            observed=None
        if not active and observed:return state,observed
        require(time.monotonic()<deadline,'BUDGET_ACTIVE_CLAIMS_OR_CHILDREN_NOT_DRAINED')
        time.sleep(.5)

def read_budget_snapshot(config,cgroup=Path('/sys/fs/cgroup')):
    def raw(name):return read_regular(Path(cgroup)/name,65536).decode('ascii')
    def integer(name):
        text=raw(name).strip();require(re.fullmatch(r'[0-9]{1,20}',text),'BUDGET_CGROUP_INTEGER');return int(text)
    stats={}
    for line in raw('memory.stat').splitlines():
        key,value=line.split();require(key not in stats and re.fullmatch(r'[0-9]{1,20}',value),'BUDGET_MEMORY_STAT');stats[key]=int(value)
    def psi(text,kind):
        for line in text.splitlines():
            if line.startswith(kind+' '):
                fields=dict(part.split('=',1) for part in line.split()[1:]);value=float(fields['avg10'])
                require(math.isfinite(value) and value>=0,'BUDGET_PSI');return value
        raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_PSI_MISSING')
    pressure=raw('memory.pressure');cpu=psi(raw('cpu.pressure'),'some')
    sandbox=config['project_executor']['sandbox'].get('memory_mb')
    require(type(sandbox) is int and 96<=sandbox<=512,'BUDGET_SANDBOX_LIMIT')
    return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2','instance_id':60509551,'observed_at':time.time(),
        'worker_slots':3,'current_bytes':integer('memory.current'),'max_bytes':integer('memory.max'),
        'inactive_file_bytes':stats['inactive_file'],'file_bytes':stats['file'],'shmem_bytes':stats['shmem'],
        'sandbox_limit_bytes':sandbox*MIB,'planner_reserve_bytes':128*MIB,'minimum_headroom_bytes':2*GIB,
        'memory_psi_some_avg10':psi(pressure,'some'),'memory_psi_full_avg10':psi(pressure,'full'),'cpu_pressure':cpu}

def load_budget_module(root,runtime,expected,request):
    stage=Path(root)/'state/dispatcher/bounded_cpu_preflight'/request
    require(not stage.exists() and not stage.is_symlink(),'BUDGET_PREFLIGHT_ALREADY_EXISTS')
    stage.mkdir(parents=True,mode=0o700)
    policy=read_regular(Path(root)/'scripts/owner_resource_policy.py')
    require(digest(policy)==expected.get('scripts/owner_resource_policy.py'),'BUDGET_RESOURCE_POLICY_PIN')
    sources={'owner_resource_policy':policy,'owner_autonomy_pool':runtime['scripts/owner_autonomy_pool.py']}
    previous={name:sys.modules.get(name) for name in sources};loaded={}
    try:
        for name,source in sources.items():
            path=stage/(name+'.py');atomic(path,source,0o644)
            loader=importlib.util.spec_from_file_location(name,path);require(loader and loader.loader,'BUDGET_MODULE_LOADER')
            module=importlib.util.module_from_spec(loader);sys.modules[name]=module;loader.loader.exec_module(module);loaded[name]=module
        module=loaded['owner_autonomy_pool'];require(callable(getattr(module,'bounded_cpu_decision',None)),'BUDGET_VALIDATOR_REQUIRED')
        return module,stage
    finally:
        for name,value in previous.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value

def budget_preflight(config,module,stage,phase,cgroup=Path('/sys/fs/cgroup')):
    snapshot=read_budget_snapshot(config,cgroup)
    reclaim=min(snapshot['inactive_file_bytes'],snapshot['file_bytes']-snapshot['shmem_bytes'],snapshot['current_bytes'])
    reserve=3*(max(256*MIB,snapshot['sandbox_limit_bytes'])+128*MIB)
    projected=snapshot['current_bytes']-reclaim+reserve
    decision=module.bounded_cpu_decision(snapshot,memory_ratio=projected/snapshot['max_bytes'],
        cpu_pressure=snapshot['cpu_pressure'],now=time.time())
    require(decision.get('reclaimable_bytes')==reclaim and decision.get('reserved_bytes')==reserve
            and decision.get('projected_bytes')==projected and decision.get('headroom_bytes')==snapshot['max_bytes']-projected,
            'BUDGET_INDEPENDENT_ARITHMETIC')
    result={'schema':'NOX_BOUNDED_CPU_NATIVE_PREFLIGHT_V1','phase':phase,'snapshot':snapshot,'decision':decision,
        'model_inference_called':False,'workers_started':0,'source_tree_writes':0}
    atomic(Path(stage)/(phase+'.json'),encoded(result));print('NOX_MAINT_BOUNDED_CPU_PREFLIGHT='+encoded(result).decode(),flush=True)
    require(decision.get('eligible') is True and decision['headroom_bytes']>=2*GIB,'BUDGET_NATIVE_ADMISSION_HOLD')
    return result

def budget_receipt(root,request,receipt):
    path=Path(root)/'state/dispatcher'/('bounded_cpu_install_'+request+'.json');raw=encoded(receipt)
    atomic(path,raw);require(read_regular(path)==raw,'BUDGET_RECEIPT_READBACK')
    print('NOX_MAINT_BOUNDED_CPU_INSTALL='+raw.decode(),flush=True)

def install_budget(bundle,specification,root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'BUDGET_OWNER_CONTEXT')
    root=Path(root);runtime=budget_assets(bundle,specification);expected=specification['expected_native']
    require(isinstance(expected,dict) and CONFIG in expected and all(path==CONFIG or
        re.fullmatch(r'scripts/(?:owner_[a-z0-9_]+|nox_dispatcher_t855u)\.py',path) for path in expected),'BUDGET_EXPECTED_SCOPE')
    before=preimages(root,expected);old,new=compose_budget_config(before[CONFIG],runtime,specification)
    require(all(expected.get('scripts/'+name)==pin for name,pin in old['module_pins'].items())
        and 'scripts/nox_dispatcher_t855u.py' in expected,'BUDGET_ALL_MODULE_PREIMAGES')
    changes={**runtime,CONFIG:encoded(new)};ids=specification['rebind_task_ids'];protected=protected_snapshot(specification)
    require(stop_clear(root),'BUDGET_OWNER_STOP')
    lockpath=root/'state/owner_maintenance.lock';require(not lockpath.is_symlink(),'BUDGET_LEASE_PATH');fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_BOUNDED_CPU_POLICY_INSTALL_RECEIPT_V1','request':request,'source_sha':source,'state':'PREFLIGHT',
        'started_at':time.time(),'queue_writes':0,'source_tree_writes':0,'source_reseeded':False,
        'model_restarted':False,'training_started':False,'original_tasks_accepted':0}
    applied=[];stop_attempted=False;new_owned=[];source_before=None;final_state=None;original_projects=None
    def lease_guard():
        info=os.fstat(fd);named=lockpath.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and not info.st_mode&0o022
            and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'BUDGET_LEASE_CHANGED')
    def guard():
        lease_guard();require(stop_clear(root),'BUDGET_OWNER_STOP_CHANGED')
        require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED')
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_MAINTENANCE_BUSY') from exc
        guard();preimages(root,expected);baseline,first=wait_idle_zero_children(root,specification)
        absent_retry_rows(baseline,ids);original_projects=project_history_proofs(root,baseline,old)
        receipt['existing_project_receipts']=original_projects
        source_before=source_snapshot(root,old);receipt['source_before']=source_before
        module,stage=load_budget_module(root,runtime,expected,request)
        receipt['budget_before_stop']=budget_preflight(new,module,stage,'before_stop')
        state,second=wait_idle_zero_children(root,specification)
        require(second['director']==first['director'],'BUDGET_DIRECTOR_CHANGED_BEFORE_STOP')
        receipt['zero_children_snapshots']=[first,second]
        guard();preimages(root,expected);require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_PREFLIGHT')
        state,active=queue_idle(root);require(not active,'BUDGET_ACTIVE_BEFORE_STOP');absent_retry_rows(state,ids)
        require(preserve_terminal_history(baseline,state)['verified'],'BUDGET_HISTORY_CHANGED_BEFORE_STOP')
        require(project_history_proofs(root,state,old)==original_projects,'BUDGET_PROJECT_RECEIPTS_CHANGED_BEFORE_STOP')
        backup=root/'state/dispatcher/bounded_cpu_rollback'/request
        require(not backup.exists() and not backup.is_symlink(),'BUDGET_BACKUP_EXISTS');backup.mkdir(parents=True,mode=0o700)
        for relative in changes:atomic(backup/relative,before[relative])
        atomic(backup/'original_queue_snapshot.json',encoded(state));atomic(backup/'source_snapshot.json',encoded(source_before))
        receipt.update(backup_path=str(backup),previous_director=first['director'])
        guard();zero_children_guard(specification);stop_attempted=True;stop_checked()
        require(process_identity(first['director']['pid']) is None,'BUDGET_OLD_DIRECTOR_ALIVE')
        final_state,active=queue_idle(root);require(not active,'BUDGET_ACTIVE_AFTER_STOP');absent_retry_rows(final_state,ids)
        require(preserve_terminal_history(state,final_state)['verified'],'BUDGET_TERMINAL_HISTORY_CHANGED_ON_STOP')
        require(project_history_proofs(root,final_state,old)==original_projects,'BUDGET_PROJECT_RECEIPTS_CHANGED_ON_STOP')
        require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_ON_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_state));receipt['final_stopped_queue_sha256']=digest(encoded(final_state))
        guard();receipt['budget_after_stop']=budget_preflight(new,module,stage,'after_stop')
        applied=apply_transaction(root,changes,before)
        guard();require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_AFTER_APPLY')
        receipt['new_director']=start_update_checked(root,new_owned)
        guard();require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_BEFORE_ADMISSION')
        receipt.update(state='BOUNDED_CPU_INSTALLED_ADMISSION_PENDING',source_preserved_before_admission=True,
            first_fifteen_catalog_rows_preserved=True,old_module_pins=old['module_pins'],
            installed_files={path:digest(raw) for path,raw in changes.items()},protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_BOUNDED_CPU_'+type(exc).__name__
        try:
            lease_guard()
            if applied:
                observed=supervisor('status')
                if observed['state']=='RUNNING':
                    actual=process_identity(observed.get('pid'))
                    require(new_owned and actual==new_owned[0],'BUDGET_FOREIGN_DIRECTOR_NO_ROLLBACK')
                    children=descendant_snapshot(actual['pid']);stop_checked();wait_previous_descendants_stopped(children)
                else:require(observed['state'] in ('STOPPED','FATAL','EXITED'),'BUDGET_UNKNOWN_PROCESS_NO_ROLLBACK')
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stop_attempted and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and stop_clear(root):
                require(all(read_regular(root/path)==before[path] for path in changes),'BUDGET_ROLLBACK_UNVERIFIED')
                require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_NO_RESTART')
                require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED_NO_RESTART')
                receipt['restored_director']=start_checked(root);receipt['restored_original_runtime']=True
        except Exception as recovery:
            receipt['recovery']=str(recovery) if isinstance(recovery,Hold) else 'HOLD_BUDGET_RECOVERY_'+type(recovery).__name__
        receipt['finished_at']=time.time();budget_receipt(root,request,receipt);raise
    finally:os.close(fd)
    last=None;snapshots=[];deadline=time.monotonic()+45
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'BUDGET_OWNER_STOP_AFTER_ADMISSION')
            require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED_AFTER_ADMISSION')
            try:
                last=acceptance_snapshot(root,ids)
                require(last['director']==receipt['new_director'],'BUDGET_NEW_DIRECTOR_CHANGED')
                if len(last['workers'])==len({row['pid'] for row in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if stable_three(snapshots) and any(row['claim_present'] for row in last['tasks']):break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        after,_=queue_idle(root);receipt['history_preservation']=preserve_terminal_history(final_state,after)
        require(receipt['history_preservation']['verified'],'BUDGET_TERMINAL_HISTORY_PRESERVATION_FAILED')
        # New retry rows are valid new work; verify the seven old rows independently.
        old_only={'tasks':{tid:after['tasks'][tid] for tid,row in final_state['tasks'].items() if row.get('handler')==PROJECT_HANDLER}}
        receipt['existing_project_receipts_after_admission']=project_history_proofs(root,old_only,old)
        require(receipt['existing_project_receipts_after_admission']==original_projects,'BUDGET_OLD_PROJECT_RECEIPT_DRIFT')
        receipt.update(readback=last,process_snapshots=snapshots)
        require(last and len(snapshots)==2 and last is snapshots[-1] and stable_three(snapshots),'BUDGET_THREE_NATIVE_WORKERS_NOT_VERIFIED')
        require(any(row['claim_present'] for row in last['tasks']),'BUDGET_NO_RETRY_ADMISSION')
        receipt.update(three_live_workers_verified=True,state='BOUNDED_CPU_THREE_WORKERS_RETRY_RUNNING'
            if any(row['status']=='running' for row in last['tasks']) else 'BOUNDED_CPU_THREE_WORKERS_RETRY_ADMITTED')
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_BUDGET_ADMISSION_READBACK'
        receipt['readback']=last;receipt['process_snapshots']=snapshots
    receipt['finished_at']=time.time();budget_receipt(root,request,receipt);return receipt

def main():
    result=install_budget(BUNDLE,SPEC)
    if result.get('three_live_workers_verified') is True:
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    else:raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_ADMISSION_NOT_VERIFIED')

if __name__=='__main__':main()

