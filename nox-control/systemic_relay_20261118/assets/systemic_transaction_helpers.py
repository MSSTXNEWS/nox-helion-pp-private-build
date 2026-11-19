#!/usr/bin/env python3
"""Runner-only kernel-self-FD update with native preflight before stop.
Common transaction helpers frozen from 2be2752f4e784e94db08159e39b852ec2f22a513f080247740eaf6bdc625c640.
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

PREFLIGHT_BASE = b'def value():\n    return 1\n'

PREFLIGHT_PATCH = b'def value():\n    return 2\n'

PREFLIGHT_TEST = b'import asyncio\nimport sqlite3\nimport threading\nimport unittest\nfrom pathlib import Path\nimport httpx\nfrom fastapi import FastAPI\nimport source\n\nclass NativePreflight(unittest.TestCase):\n    def test_source_patch(self):\n        self.assertEqual(source.value(), 2)\n        self.assertEqual(str(Path(__file__).parent), "/work/project/source")\n        self.assertEqual(str(Path(__file__).parents[3]), "/")\n    def test_asgi_dependencies(self):\n        app = FastAPI()\n        @app.get(\'/probe\')\n        async def probe():\n            return {\'probe\': 2}\n        async def check():\n            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=\'http://fixture.local\') as client:\n                response = await client.get(\'/probe\')\n                self.assertEqual(response.json(), {\'probe\': 2})\n        asyncio.run(check())\n    def test_sqlite_extension(self):\n        with sqlite3.connect(\':memory:\') as connection:\n            self.assertEqual(connection.execute(\'select 2\').fetchone(), (2,))\n    def test_thread_allowed(self):\n        result = []\n        thread = threading.Thread(target=lambda: result.append(2))\n        thread.start()\n        thread.join(2)\n        self.assertFalse(thread.is_alive())\n        self.assertEqual(result, [2])\n'

def sandbox_preflight(root, runtime, package, project, request):
    """Run only a fixed fixture with pinned modules before any live-code write."""
    require(project.get('sandbox',{}).get('backend')=='chroot_seccomp','NATIVE_SANDBOX_BACKEND')
    require(project['sandbox'].get('uid')==65534 and project['sandbox'].get('gid')==65534,
            'NATIVE_SANDBOX_IDENTITY')
    stage=Path(root)/'state/dispatcher/complete_executor_preflight'/request
    require(not stage.exists() and not stage.is_symlink(),'PREFLIGHT_ALREADY_EXISTS')
    require(not any(p.is_symlink() for p in stage.parents),'PREFLIGHT_PATH')
    stage.mkdir(parents=True,mode=0o700)
    module_dir=stage/'modules';module_dir.mkdir(mode=0o700)
    for name in ('owner_project_executor.py','owner_project_test_runner.py'):
        raw=runtime['scripts/'+name]
        require(digest(raw)==project['source_pins'][name],'PREFLIGHT_SOURCE_PIN')
        atomic(module_dir/name,raw,0o644)
    fixture=stage/'source';fixture.mkdir(mode=0o700)
    atomic(fixture/'source.py',PREFLIGHT_BASE,0o644)
    atomic(fixture/'test_source.py',PREFLIGHT_TEST,0o644)
    config=copy.deepcopy(project)
    config.update(package_root=str(stage/'package'),state_root=str(stage/'run'),
                  roots={'PREFLIGHT_SOURCE':{'path':str(fixture),
                    'integration_kind':'SOURCE_WORKSPACE',
                    'allowed_paths':['source.py','test_source.py'],'deny_paths':[]}})
    dependency=config.get('dependency_manifest')
    require(isinstance(dependency,dict) and set(dependency)=={'path','sha256'},'PREFLIGHT_DEPENDENCY_REQUIRED')
    dependency_path=Path(dependency['path'])
    require(dependency_path.is_absolute() and dependency_path.is_relative_to(Path(root)/'state/dispatcher/project_executor/package/manifests'),
            'PREFLIGHT_DEPENDENCY_PATH')
    relative=str(dependency_path.relative_to(root))
    raw=package.get(relative)
    require(isinstance(raw,bytes) and digest(raw)==dependency['sha256'],'PREFLIGHT_DEPENDENCY_PIN')
    manifest_path=stage/'dependency-manifest.json';atomic(manifest_path,raw)
    config['dependency_manifest']={'path':str(manifest_path),'sha256':dependency['sha256']}
    loader=importlib.util.spec_from_file_location('_nox_approved_project_executor_preflight',module_dir/'owner_project_executor.py')
    require(loader is not None and loader.loader is not None,'PREFLIGHT_LOADER')
    executor=importlib.util.module_from_spec(loader);loader.loader.exec_module(executor)
    plan={'schema':'NOX_PROJECT_WORK_PLAN_V1','task_id':'NATIVE-PREFLIGHT.source.1',
          'parent_task_id':'NATIVE-PREFLIGHT','queue_id':'Q4_INTEGRATION_ACCEPTANCE',
          'root_id':'PREFLIGHT_SOURCE','operation':'apply_reviewed_files','review_origin':'OWNER_REVIEWED',
          'context':[{'path':'source.py','sha256':digest(PREFLIGHT_BASE)},
                     {'path':'test_source.py','sha256':digest(PREFLIGHT_TEST)}],
          'files':[{'path':'source.py','before_sha256':digest(PREFLIGHT_BASE),
                    'after_sha256':digest(PREFLIGHT_PATCH),'payload_sha256':digest(PREFLIGHT_PATCH)}],
          'verification':{'kind':'python_unittest','modules':['test_source'],'min_tests':4,'timeout_sec':45},
          'acceptance_scope':'SOURCE_PATCH_TESTED','original_task_accepted':False}
    reference=executor.materialize_plan(plan,{digest(PREFLIGHT_PATCH):PREFLIGHT_PATCH},config)
    result=executor.prepare(reference,config,digest(('preflight:'+request).encode())[:24],
                            stop_check=lambda:not stop_clear(root))
    evidence=result.get('project_evidence') or {};tests=evidence.get('tests') or {};facts=tests.get('sandbox') or {}
    summary={'schema':'NOX_NATIVE_PROJECT_SANDBOX_PREFLIGHT_V1','state':result.get('state'),
             'tests_run':result.get('tests_run'),'sandbox':facts,'reason':evidence.get('reason'),
             'dependency_manifest_sha256':dependency['sha256'],
             'runtime_source_pins':config['source_pins'],'evidence_sha256':result.get('project_evidence_sha256'),
             'source_unchanged':read_regular(fixture/'source.py')==PREFLIGHT_BASE,
             'fixture_only':True,'business_task_completed':False,'model_inference_called':False,
             'original_task_accepted':False,'path':str(stage),'at':time.time()}
    atomic(stage/'preflight_receipt.json',encoded(summary))
    print('NOX_MAINT_COMPLETE_EXECUTOR_PREFLIGHT='+encoded(summary).decode(),flush=True)
    require(result.get('state')=='PREPARED' and result.get('passed') is True
            and result.get('sandbox_verified') is True and result.get('trusted_tests_unchanged') is True
            and result.get('tests_run')==4 and tests.get('passed') is True
            and tests.get('failures')==0 and tests.get('errors')==0 and tests.get('skipped')==0
            and facts.get('uid')==65534 and facts.get('gid')==65534
            and all(facts.get(key) is True for key in ('network_denied','fork_denied','exec_denied',
                'host_path_hidden','no_new_privs','seccomp_filter'))
            and summary['source_unchanged'],'NATIVE_SANDBOX_PREFLIGHT_FAILED')
    return summary

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

def expected_processes(specification):
    expected=specification['expected_director'];director=process_identity(expected['pid'])
    require(director and director['start_ticks']==expected['start_ticks'],'UPDATE_DIRECTOR_CHANGED')
    workers=specification['expected_workers']
    require(isinstance(workers,list) and len(workers)==3 and len({x['pid'] for x in workers})==3,'UPDATE_WORKER_COUNT')
    result=[]
    for row in workers:
        actual=process_identity(row['pid'])
        require(actual and actual['start_ticks']==row['start_ticks'] and actual['ppid']==director['pid'],'UPDATE_WORKER_CHANGED')
        result.append(actual)
    return {'director':director,'workers':result}

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

MIB=1024*1024

GIB=1024*MIB

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

SPEC={'schema': 'NOX_KERNEL_SELF_FD_RUNNER_INSTALL_SPEC_V1', 'assets': {'sf_runtime_192d0c1b7b87447d4f08.py': '192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f', 'sf_plan_457dbaf4484cfb5b7e14.json': '457dbaf4484cfb5b7e14c5308285a42f01714dcec28358a54e6c926adf787e0b', 'sf_payload_5201af0115e1ead68d33.source': '5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926', 'sf_payload_4329f7389b24cfbb1fbb.source': '4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821', 'sf_fd_descriptor_768d28516014a124a380.json': '768d28516014a124a3809ee5af0a410508a621ee95d780ce7b1681fce5da1c58'}, 'runtime_paths': {'sf_runtime_192d0c1b7b87447d4f08.py': 'scripts/owner_project_test_runner.py'}, 'package_paths': {'sf_plan_457dbaf4484cfb5b7e14.json': 'state/dispatcher/project_executor/package/plans/457dbaf4484cfb5b7e14c5308285a42f01714dcec28358a54e6c926adf787e0b.json', 'sf_payload_5201af0115e1ead68d33.source': 'state/dispatcher/project_executor/package/blobs/5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926', 'sf_payload_4329f7389b24cfbb1fbb.source': 'state/dispatcher/project_executor/package/blobs/4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821'}, 'fd_preflight_descriptor_asset': 'sf_fd_descriptor_768d28516014a124a380.json', 'catalog_append': [{'id': '1A03.project.cursor_admission.proc_retry.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q1_RUNTIME_CHAT', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'params': {'parent_task_id': '1A03', 'plan_sha256': '457dbaf4484cfb5b7e14c5308285a42f01714dcec28358a54e6c926adf787e0b'}, 'source_sha256': '6c67e567e669b993d016ea1d6137a03f3567e564d2b35696edf665a27e0f4756'}], 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '6c67e567e669b993d016ea1d6137a03f3567e564d2b35696edf665a27e0f4756', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_autonomy_pool.py': 'd5fb476f53e64d2014f27465c7bd64192158b5bcdd79a72ff7c962d853602339', 'scripts/owner_subagent_instruction_truth.py': '294473d35d4870f50467d843c551c9b9fd7c4644e4b615e92403dc916ed109e4', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'config/owner_native_subagents.json': '085fa4e3c8c96ae4ffb952dee53bb0d8bda0a1c50416a4d8a365017d043e95be', 'scripts/owner_project_executor.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': '52e62a143d16f387899ff1737ce4eb698dee5ceca510fc6f97f931c11a0aec10', 'scripts/owner_project_native.py': '2c83ec53f7ee7c2d76bc1fac21c80adf76c58f83c5a219ba0294f9b3f713d707', 'scripts/owner_project_planner.py': 'aa0dd1c8266106b599ce83b64b7af77c7a4f32377fc09cd545e1f9697bda4420', 'scripts/owner_project_test_runner.py': '84d54c647b0a63447aca91d34b90372e36dcd59442e3066458a21688fcb5a595'}, 'expected_director': {'pid': 3760381, 'start_ticks': 176197984}, 'expected_workers': [{'pid': 3760595, 'start_ticks': 176199997}, {'pid': 3760596, 'start_ticks': 176199997}, {'pid': 3760597, 'start_ticks': 176199997}], 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}}
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

SELF_FD_SCHEMA='NOX_KERNEL_SELF_FD_RUNNER_INSTALL_SPEC_V1'
SELF_FD_RUNNER='scripts/owner_project_test_runner.py'
SELF_FD_RUNNER_PIN='192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f'
SELF_FD_CONFIG_PIN='085fa4e3c8c96ae4ffb952dee53bb0d8bda0a1c50416a4d8a365017d043e95be'
SELF_FD_SOURCE_PIN='f9d914745e8b42bc7d8f45bc5dd0804291a86eacab4edd1cd2dc42d4c17f583f'
SELF_FD_TASK='1A03.project.cursor_admission.proc_retry.20261118'
SELF_FD_PLAN='457dbaf4484cfb5b7e14c5308285a42f01714dcec28358a54e6c926adf787e0b'
SELF_FD_DESCRIPTOR='768d28516014a124a3809ee5af0a410508a621ee95d780ce7b1681fce5da1c58'
SELF_FD_REQUIRED={
    '1A03.project.cursor_admission.focus_retry.20261118':'284d6284b5d088b4dcaa16250f4151ba26cad0b9f20f73bd708e9a60a097b80d',
    '1A03.project.cursor_admission.owner_rescue.20261118':'c3f293373560fcb1950cc1d134ac94b8c7d4fb8ec16045dc95b868bb39d30d32'}

def self_fd_assets(bundle,specification):
    require(specification.get('schema')==SELF_FD_SCHEMA,'SELF_FD_SCHEMA')
    pins=specification.get('assets');runtime_paths=specification.get('runtime_paths');package_paths=specification.get('package_paths')
    descriptor=specification.get('fd_preflight_descriptor_asset')
    require(isinstance(pins,dict) and isinstance(runtime_paths,dict) and isinstance(package_paths,dict)
            and len(runtime_paths)==1 and set(runtime_paths.values())=={SELF_FD_RUNNER}
            and set(pins)==set(bundle)==set(runtime_paths)|set(package_paths)|{descriptor}
            and len(pins)==5 and len(package_paths)==3,'SELF_FD_ASSET_SCOPE')
    assets={};total=0
    for name,pin in pins.items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',name)
                and SHA.fullmatch(str(pin)) and isinstance(bundle[name],str) and len(bundle[name])<=3*1024*1024,'SELF_FD_ASSET_PIN')
        raw=base64.b64decode(bundle[name],validate=True);total+=len(raw)
        require(len(raw)<=2*1024*1024 and total<=8*1024*1024 and digest(raw)==pin,'SELF_FD_ASSET_HASH');assets[name]=raw
    runtime={path:assets[name] for name,path in runtime_paths.items()}
    require(digest(runtime[SELF_FD_RUNNER])==SELF_FD_RUNNER_PIN,'SELF_FD_REVIEWED_RUNNER_PIN');compile(runtime[SELF_FD_RUNNER],SELF_FD_RUNNER,'exec')
    package={}
    for name,path in package_paths.items():
        match=re.fullmatch(r'state/dispatcher/project_executor/package/(plans|blobs)/([a-f0-9]{64})(\.json)?',path)
        require(match and bool(match[3])==(match[1]=='plans') and digest(assets[name])==match[2],'SELF_FD_PACKAGE_PATH')
        require(path not in package,'SELF_FD_PACKAGE_DUPLICATE');package[path]=assets[name]
    require(digest(assets[descriptor])==SELF_FD_DESCRIPTOR,'SELF_FD_DESCRIPTOR_PIN')
    return runtime,package,json.loads(assets[descriptor])

def self_fd_compose(raw,runtime,specification):
    require(digest(raw)==SELF_FD_CONFIG_PIN,'SELF_FD_CONFIG_PREIMAGE');old=json.loads(raw)
    require(old.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and old.get('instance_id')==60509551
        and old.get('owner_authorized') is True and old.get('mode')=='NORMAL' and old.get('target')==3
        and old.get('global_worker_cap')==3 and old.get('execution_mode')=='NATIVE_PROJECT_V1','SELF_FD_CONFIG_SCOPE')
    catalog=old.get('catalog') or {};rows=catalog.get('tasks')
    require(catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1' and isinstance(rows,list) and len(rows)==20
        and digest(encoded(catalog))==old.get('catalog_sha256'),'SELF_FD_CATALOG_PREIMAGE')
    project=old['project_executor'];require(project.get('sandbox',{}).get('backend')=='chroot_seccomp'
        and project['sandbox'].get('uid')==65534 and project['sandbox'].get('gid')==65534
        and project['sandbox'].get('memory_mb')==256,'SELF_FD_BACKEND_SCOPE')
    append=specification.get('catalog_append');require(isinstance(append,list) and len(append)==1,'SELF_FD_APPEND_COUNT')
    row=append[0];known={x['id'] for x in rows};callback=old['module_pins']['owner_subagent_dispatcher.py']
    required={'id','handler','deps','resource','source_sha256','params','queue_id'}
    require(isinstance(row,dict) and required<=set(row)
        and not set(row)-(required|{'priority','title','estimated_cost'}),'SELF_FD_APPEND_FIELDS')
    require(row['id']==SELF_FD_TASK and row['id'] not in known and row['handler']==PROJECT_HANDLER
        and row['source_sha256']==callback and row['queue_id']=='Q1_RUNTIME_CHAT' and row['resource']=='CPU_LIGHT'
        and row['deps']==[] and row['params']=={'parent_task_id':'1A03','plan_sha256':SELF_FD_PLAN},'SELF_FD_APPEND_SCOPE')
    cost=row.get('estimated_cost',1);title=row.get('title',row['id'])
    require(row.get('priority','P2') in ('P0','P1','P2','P3') and type(cost) in (int,float)
        and math.isfinite(cost) and 0<cost<=100000 and isinstance(title,str) and 1<=len(title)<=180,'SELF_FD_APPEND_PRESENTATION')
    require(set(runtime)=={SELF_FD_RUNNER} and digest(runtime[SELF_FD_RUNNER])==SELF_FD_RUNNER_PIN,'SELF_FD_RUNTIME_ONLY')
    new=copy.deepcopy(old);new['module_pins']['owner_project_test_runner.py']=SELF_FD_RUNNER_PIN
    new['project_executor']['source_pins']['owner_project_test_runner.py']=SELF_FD_RUNNER_PIN
    new['catalog']['tasks'].append(copy.deepcopy(row));new['catalog_sha256']=digest(encoded(new['catalog']))
    undo=copy.deepcopy(new);undo['catalog']=old['catalog'];undo['catalog_sha256']=old['catalog_sha256']
    undo['module_pins']['owner_project_test_runner.py']=old['module_pins']['owner_project_test_runner.py']
    undo['project_executor']['source_pins']['owner_project_test_runner.py']=old['project_executor']['source_pins']['owner_project_test_runner.py']
    require(undo==old and new['catalog']['tasks'][:-1]==rows,'SELF_FD_UNRELATED_CONFIG_CHANGE')
    return old,new

def self_fd_history(root,state,config):
    expected={row['id'] for row in config['catalog']['tasks'] if row.get('handler')==PROJECT_HANDLER}
    rows={tid:row for tid,row in state['tasks'].items() if row.get('handler')==PROJECT_HANDLER}
    require(set(rows)==expected and len(rows)==12,'SELF_FD_PROJECT_HISTORY_SET')
    allowed={config['module_pins']['owner_subagent_dispatcher.py'],*config.get('historical_project_source_sha256',[])};proofs={}
    for tid,row in rows.items():
        result=row.get('result') or {};receipt=result.get('receipt') or {}
        phase='PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED' if row.get('status')=='done' else 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
        require(row.get('status') in ('done','blocked') and result.get('verified') is True
            and receipt.get('task_id')==tid and receipt.get('claim')==row.get('owner_claim')
            and receipt.get('original_task_accepted') is False and receipt.get('source_sha256') in allowed
            and receipt.get('phase')==phase and result.get('receipt_sha256')==digest(encoded(receipt)),
            'SELF_FD_OLD_PROJECT_RECEIPT')
        if tid in SELF_FD_REQUIRED:
            require(row['status']=='blocked' and result['receipt_sha256']==SELF_FD_REQUIRED[tid]
                and receipt.get('project_source_changed') is False,'SELF_FD_REQUIRED_FAILURE_CHANGED')
        proofs[tid]=exact_s03(root,receipt)
    require(set(SELF_FD_REQUIRED)<=set(proofs),'SELF_FD_REQUIRED_FAILURE_MISSING')
    return proofs

def self_fd_children(specification):
    owner=expected_processes(specification);status=supervisor('status')
    require(status['state']=='RUNNING' and status.get('pid')==owner['director']['pid'],'SELF_FD_SUPERVISOR_IDENTITY')
    children=descendant_snapshot(owner['director']['pid']);expected={(x['pid'],x['start_ticks']) for x in owner['workers']}
    observed={(x['pid'],x['start_ticks']) for x in children};require(expected<=observed,'SELF_FD_MISSING_WORKER_CHILD')
    auxiliary=[];unknown=[]
    for row in children:
        if (row['pid'],row['start_ticks']) in expected:continue
        try:
            argv=read_regular(Path('/proc')/str(row['pid'])/'cmdline',8192).split(b'\0')
            tracker=(row['ppid']==owner['director']['pid'] and any(re.fullmatch(
                rb'from multiprocessing\.resource_tracker import main; *main\([0-9]{1,8}\)',arg) for arg in argv))
        except (OSError,Hold):tracker=False
        (auxiliary if tracker else unknown).append(row)
    require(len(auxiliary)<=1,'SELF_FD_MULTIPLE_RESOURCE_TRACKERS')
    return {'processes':owner,'children':children,'observed_resource_trackers':auxiliary,'unexpected_children':unknown,'at':time.time()}

def self_fd_drain(root,specification,timeout=40):
    deadline=time.monotonic()+timeout
    while True:
        require(stop_clear(root),'SELF_FD_STOP_DURING_DRAIN')
        state,active=queue_idle(root);require(SELF_FD_TASK not in state['tasks'],'SELF_FD_RETRY_ALREADY_ADMITTED')
        observed=self_fd_children(specification)
        if not active and not observed['unexpected_children']:return state,observed
        require(time.monotonic()<deadline,'SELF_FD_ACTIVE_CLAIMS_OR_UNKNOWN_CHILDREN');time.sleep(.5)

def self_fd_adapter(facts,parent_pid):
    require(facts.get('uid')==65534 and facts.get('gid')==65534 and all(facts.get(key) is True for key in
        ('network_denied','fork_denied','exec_denied','host_path_hidden','no_new_privs','seccomp_filter')),'SELF_FD_CONFINEMENT')
    proof=facts.get('kernel_self_fd_adapter') or {}
    require(proof.get('schema')=='NOX_KERNEL_SELF_FD_TEST_ADAPTER_V1'
        and proof.get('scope')=='SELF_STAT_AND_BOOT_ID_ONLY' and proof.get('mode')=='KERNEL_SELF_FD_TEST_ADAPTER'
        and all(proof.get(key) is True for key in ('kernel_backed','fresh_pread_offset_zero','own_pid_start_verified'))
        and proof.get('full_proc_available') is False and proof.get('foreign_pid_visibility') is False
        and proof.get('reserved_regular_file_descriptors')==2 and proof.get('directory_descriptors_preserved')==0
        and proof.get('procfs_magic')==40864 and type(proof.get('verifier_pid')) is int
        and proof['verifier_pid']>1 and proof['verifier_pid']!=parent_pid and proof.get('verifier_parent_pid')==parent_pid
        and type(proof.get('start_ticks')) is int and proof['start_ticks']>0
        and SHA.fullmatch(str(proof.get('boot_id_sha256')))
        and type(proof.get('stat_reads')) is int and proof['stat_reads']>=4
        and type(proof.get('boot_reads')) is int and proof['boot_reads']>=4,'SELF_FD_KERNEL_PROOF')
    return proof

def self_fd_preflight(root,runtime,package,project,request,descriptor,before,history):
    combined={**runtime,'scripts/owner_project_executor.py':before['scripts/owner_project_executor.py']}
    dep=project['dependency_manifest'];dep_path=Path(dep['path'])
    require(dep_path.is_relative_to(root/'state/dispatcher/project_executor/package/manifests'),'SELF_FD_DEPENDENCY_SCOPE')
    dep_raw=read_regular(dep_path);require(digest(dep_raw)==dep['sha256'],'SELF_FD_DEPENDENCY_PIN')
    generic=sandbox_preflight(root,combined,{str(dep_path.relative_to(root)):dep_raw},project,request)
    self_fd_adapter(generic['sandbox'],os.getpid());stage=Path(generic['path']);modules=stage/'modules'
    cloned=copy.deepcopy(project);cloned.update(package_root=str(stage/'reviewed-package'),state_root=str(stage/'reviewed-run'))
    for path,raw in package.items():atomic(Path(cloned['package_root'])/Path(path).relative_to('state/dispatcher/project_executor/package'),raw)
    loader=importlib.util.spec_from_file_location('_nox_self_fd_executor',modules/'owner_project_executor.py')
    require(loader and loader.loader,'SELF_FD_EXECUTOR_LOADER');executor=importlib.util.module_from_spec(loader);loader.loader.exec_module(executor)
    executor.validate_config(cloned);ref={'plan_sha256':SELF_FD_PLAN};plan=executor.load_plan(ref,cloned)
    require(plan['task_id']==SELF_FD_TASK and plan['parent_task_id']=='1A03' and plan['root_id']=='NOX_PROJECT_SOURCE'
        and plan['review_origin']=='OWNER_REVIEWED' and plan['verification']['min_tests']==30,'SELF_FD_RETRY_PLAN_SCOPE')
    existing_plan_path=root/'state/dispatcher/project_executor/package/plans/379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json'
    existing_raw=read_regular(existing_plan_path);require(digest(existing_raw)==existing_plan_path.stem,'SELF_FD_PREVIOUS_RESCUE_PLAN_PIN')
    prior=json.loads(existing_raw);compare=copy.deepcopy(plan);compare['task_id']=prior['task_id'];require(compare==prior,'SELF_FD_RETRY_ONLY_ID_CHANGE')
    prepared=executor.prepare(ref,cloned,digest(('self-fd-rescue:'+request).encode())[:24],stop_check=lambda:not stop_clear(root))
    ev=prepared.get('project_evidence') or {};tests=ev.get('tests') or {}
    print('NOX_MAINT_SELF_FD_RESCUE_PREFLIGHT='+encoded({'state':prepared.get('state'),'tests':tests,'reason':ev.get('reason'),'shared_source_integrated':False}).decode(),flush=True)
    require(prepared.get('state')=='PREPARED' and prepared.get('passed') is True and prepared.get('trusted_tests_unchanged') is True
        and tests.get('tests_run')==30 and tests.get('passed') is True and all(tests.get(k)==0 for k in ('failures','errors','skipped')),'SELF_FD_RESCUE_NATIVE_TESTS')
    self_fd_adapter(tests.get('sandbox') or {},os.getpid())
    require(descriptor.get('schema')=='NOX_PINNED_CURRENT_SOURCE_TEST_PREFLIGHT_V1'
        and descriptor.get('operation')=='PRIVATE_WORKTREE_TEST_REPORT_ONLY' and descriptor.get('shared_source_writes') is False
        and descriptor.get('queue_claim_or_admission') is False and descriptor.get('reapply_original_before_cas') is False,'SELF_FD_FD_DESCRIPTOR_SCOPE')
    fd_tid=descriptor['task_id_reference_only'];require(history[fd_tid]['receipt_sha256']==descriptor['native_integration_receipt_sha256'],'SELF_FD_FD_PRIOR_RECEIPT')
    fd_pin=descriptor['original_plan_reference']['plan_sha256'];fd_raw=read_regular(root/'state/dispatcher/project_executor/package/plans'/(fd_pin+'.json'))
    require(digest(fd_raw)==fd_pin,'SELF_FD_FD_PLAN_PIN');fd_plan=json.loads(fd_raw)
    context={x['path']:x['sha256'] for x in fd_plan['context']};context.update({x['path']:x['after_sha256'] for x in fd_plan['files']})
    require(context=={x['path']:x['sha256'] for x in descriptor['context']} and fd_plan['verification']==descriptor['verification']
        and descriptor['verification']['min_tests']==36,'SELF_FD_FD_CURRENT_CONTEXT')
    check={'context':descriptor['context'],'files':[]};attempt=stage/'fd-current-preflight';work=attempt/'work';work.mkdir(parents=True,mode=0o700)
    with executor.tree(project['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
        snapshot=executor._check_source(handle,check)
        for path,(raw,_) in snapshot.items():atomic(work/path,raw,0o644)
        report=executor._test_report(attempt,work,fd_plan,cloned,lambda:not stop_clear(root),lambda:None)
        executor._check_source(handle,check)
    print('NOX_MAINT_SELF_FD_FD_REGRESSION_PREFLIGHT='+encoded({'tests':report,'shared_source_integrated':False,'queue_claim':False}).decode(),flush=True)
    require(report.get('completed') is True and report.get('passed') is True and report.get('tests_run')==36
        and all(report.get(k)==0 for k in ('failures','errors','skipped')),'SELF_FD_FD_REGRESSION_NATIVE_TESTS')
    self_fd_adapter(report.get('sandbox') or {},os.getpid())
    return {'state':'NATIVE_PREFLIGHT_70_PASSED','generic':generic,'rescue':{'tests':tests,'plan_sha256':SELF_FD_PLAN},
        'fd_current_regression':{'tests':report,'descriptor_sha256':SELF_FD_DESCRIPTOR},'tests_run':70,
        'shared_source_integrated':False,'queue_claims':0,'model_calls':0,'path':str(stage)}

def self_fd_receipt(root,request,receipt):
    raw=encoded(receipt);path=root/'state/dispatcher'/('kernel_self_fd_install_'+request+'.json')
    atomic(path,raw);require(read_regular(path)==raw,'SELF_FD_RECEIPT_READBACK')
    print('NOX_MAINT_KERNEL_SELF_FD_INSTALL='+raw.decode(),flush=True)

def install_self_fd(bundle,specification,root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'SELF_FD_OWNER_CONTEXT')
    root=Path(root);runtime,package,descriptor=self_fd_assets(bundle,specification);expected=specification['expected_native']
    require(isinstance(expected,dict) and expected.get(CONFIG)==SELF_FD_CONFIG_PIN and all(path==CONFIG or
        re.fullmatch(r'scripts/(?:owner_[a-z0-9_]+|nox_dispatcher_t855u)\.py',path) for path in expected),'SELF_FD_PREIMAGE_SCOPE')
    before=preimages(root,expected);old,new=self_fd_compose(before[CONFIG],runtime,specification)
    require(all(expected.get('scripts/'+name)==pin for name,pin in old['module_pins'].items())
        and 'scripts/nox_dispatcher_t855u.py' in expected,'SELF_FD_ALL_MODULE_PINS')
    changes={**runtime}
    for path,raw in package.items():
        try:current=read_regular(root/path)
        except FileNotFoundError:current=None
        require(current is None or current==raw,'SELF_FD_IMMUTABLE_PACKAGE_COLLISION')
        if current is None:before[path]=None;changes[path]=raw
    changes[CONFIG]=encoded(new);protected=protected_snapshot(specification);require(stop_clear(root),'SELF_FD_OWNER_STOP')
    lock=root/'state/owner_maintenance.lock';require(not lock.is_symlink(),'SELF_FD_LEASE_PATH');fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_KERNEL_SELF_FD_RUNNER_INSTALL_RECEIPT_V1','request':request,'source_sha':source,'state':'PREFLIGHT',
        'started_at':time.time(),'queue_writes':0,'source_tree_writes':0,'source_reseeded':False,'training_started':False,
        'model_restarted':False,'original_tasks_accepted':0,'runtime_changed':['owner_project_test_runner.py']}
    applied=[];stopped=False;owned=[];source_before=None;final_state=None;projects=None
    def guard():
        info=os.fstat(fd);named=lock.stat();require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
            and info.st_nlink==1 and not info.st_mode&0o022 and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'SELF_FD_LEASE_CHANGED')
        require(stop_clear(root),'SELF_FD_OWNER_STOP_CHANGED');require(protected_snapshot(specification)==protected,'SELF_FD_PROTECTED_CHANGED')
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise Hold('HOLD_COMPLETE_EXECUTOR_SELF_FD_LEASE_BUSY') from exc
        guard();preimages(root,expected);baseline,first=self_fd_drain(root,specification)
        projects=self_fd_history(root,baseline,old);receipt['old_project_s03']=projects
        source_before=source_snapshot(root,old);require(source_before['count']==28 and source_before['files_sha256']==SELF_FD_SOURCE_PIN,'SELF_FD_SOURCE_PREIMAGE')
        receipt['source_before']=source_before
        budget_module,budget_stage=load_budget_module(root,{'scripts/owner_autonomy_pool.py':before['scripts/owner_autonomy_pool.py']},expected,request)
        receipt['budget_before_stop']=budget_preflight(new,budget_module,budget_stage,'before_stop')
        receipt['native_preflight']=self_fd_preflight(root,runtime,package,new['project_executor'],request,descriptor,before,projects)
        guard();preimages(root,expected);state,second=self_fd_drain(root,specification)
        require(second['processes']==first['processes'],'SELF_FD_WORKER_GENERATION_CHANGED')
        require(preserve_terminal_history(baseline,state)['verified'] and self_fd_history(root,state,old)==projects,'SELF_FD_HISTORY_CHANGED_PREFLIGHT')
        require(source_snapshot(root,old)==source_before,'SELF_FD_SOURCE_CHANGED_PREFLIGHT')
        backup=root/'state/dispatcher/kernel_self_fd_rollback'/request;require(not backup.exists() and not backup.is_symlink(),'SELF_FD_BACKUP_EXISTS')
        backup.mkdir(parents=True,mode=0o700)
        for path in changes:
            if before.get(path) is not None:atomic(backup/path,before[path])
        atomic(backup/'original_queue_snapshot.json',encoded(state));atomic(backup/'source_snapshot.json',encoded(source_before))
        receipt.update(backup_path=str(backup),old_processes=first['processes'],drain_snapshots=[first,second])
        guard();last=self_fd_children(specification);require(not last['unexpected_children'],'SELF_FD_CHILD_BEFORE_STOP')
        state,active=queue_idle(root);require(not active and SELF_FD_TASK not in state['tasks'],'SELF_FD_ACTIVE_BEFORE_STOP')
        stopped=True;stop_checked();receipt['previous_children_stopped']=wait_previous_descendants_stopped(last['children'])
        require(process_identity(first['processes']['director']['pid']) is None,'SELF_FD_OLD_DIRECTOR_ALIVE')
        final_state,active=queue_idle(root);require(not active and SELF_FD_TASK not in final_state['tasks'],'SELF_FD_ACTIVE_AFTER_STOP')
        require(preserve_terminal_history(state,final_state)['verified'] and self_fd_history(root,final_state,old)==projects,'SELF_FD_HISTORY_CHANGED_ON_STOP')
        require(source_snapshot(root,old)==source_before,'SELF_FD_SOURCE_CHANGED_ON_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_state));receipt['final_stopped_queue_sha256']=digest(encoded(final_state))
        guard();receipt['budget_after_stop']=budget_preflight(new,budget_module,budget_stage,'after_stop')
        applied=apply_transaction(root,changes,before);guard();require(source_snapshot(root,old)==source_before,'SELF_FD_SOURCE_CHANGED_AFTER_APPLY')
        receipt['new_director']=start_update_checked(root,owned);guard()
        require(source_snapshot(root,old)==source_before,'SELF_FD_SOURCE_CHANGED_BEFORE_RELEASE')
        receipt.update(state='RUNNER_INSTALLED_ADMISSION_PENDING',source_preserved_before_admission=True,
            old_catalog_rows_preserved=20,installed_files={path:digest(raw) for path,raw in changes.items()},protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_SELF_FD_'+type(exc).__name__
        try:
            guard()
            if applied:
                observed=supervisor('status')
                if observed['state']=='RUNNING':
                    current=process_identity(observed.get('pid'));require(owned and current==owned[0],'SELF_FD_FOREIGN_DIRECTOR_NO_ROLLBACK')
                    children=descendant_snapshot(current['pid']);stop_checked();wait_previous_descendants_stopped(children)
                else:require(observed['state'] in ('STOPPED','FATAL','EXITED'),'SELF_FD_UNKNOWN_PROCESS_NO_ROLLBACK')
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stopped and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and stop_clear(root):
                require(all(read_regular(root/path)==before[path] for path in expected),'SELF_FD_ROLLBACK_PREIMAGES')
                require(source_snapshot(root,old)==source_before,'SELF_FD_ROLLBACK_SOURCE')
                require(protected_snapshot(specification)==protected,'SELF_FD_ROLLBACK_PROTECTED')
                receipt['restored_director']=start_checked(root);receipt['restored_original_runtime']=True
        except Exception as failure:receipt['recovery']=str(failure) if isinstance(failure,Hold) else 'HOLD_SELF_FD_RECOVERY_'+type(failure).__name__
        receipt['finished_at']=time.time();self_fd_receipt(root,request,receipt);raise
    finally:os.close(fd)
    snapshots=[];last=None;deadline=time.monotonic()+45
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'SELF_FD_STOP_AFTER_ADMISSION');require(protected_snapshot(specification)==protected,'SELF_FD_PROTECTED_AFTER_ADMISSION')
            try:
                last=acceptance_snapshot(root,[SELF_FD_TASK]);require(last['director']==receipt['new_director'],'SELF_FD_NEW_DIRECTOR_CHANGED')
                if len(last['workers'])==len({x['pid'] for x in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if stable_three(snapshots) and last['tasks'][0]['claim_present']:break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        after,_=queue_idle(root);receipt['history_preservation']=preserve_terminal_history(final_state,after)
        require(receipt['history_preservation']['verified'],'SELF_FD_TERMINAL_HISTORY_CHANGED')
        old_only={'tasks':{tid:after['tasks'][tid] for tid in final_state['tasks'] if final_state['tasks'][tid].get('handler')==PROJECT_HANDLER}}
        receipt['old_project_s03_after']=self_fd_history(root,old_only,old);require(receipt['old_project_s03_after']==projects,'SELF_FD_OLD_S03_CHANGED')
        require(last and stable_three(snapshots) and last['tasks'][0]['claim_present'],'SELF_FD_THREE_WORKERS_RETRY_NOT_VERIFIED')
        receipt.update(state='KERNEL_SELF_FD_THREE_WORKERS_RETRY_ADMITTED',three_live_workers_verified=True,
            readback=last,process_snapshots=snapshots)
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt.update(state=str(exc) if isinstance(exc,Hold) else 'HOLD_SELF_FD_ADMISSION_READBACK',readback=last,process_snapshots=snapshots)
    receipt['finished_at']=time.time();self_fd_receipt(root,request,receipt);return receipt

def main():
    result=install_self_fd(BUNDLE,SPEC)
    if result.get('three_live_workers_verified') is True:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    else:raise Hold('HOLD_COMPLETE_EXECUTOR_SELF_FD_ADMISSION_NOT_VERIFIED')

if __name__=='__main__':main()

