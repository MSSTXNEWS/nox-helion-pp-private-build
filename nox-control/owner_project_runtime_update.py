#!/usr/bin/env python3
"""Pinned incremental runtime update. No source reseed or direct queue writes.
Only sandbox/model modules, their exact config pins and four retry rows change.
Copied helpers originate from installer SHA256 f8518145ab7ab9685f6f45662684c5475bf3e653929843ac34f4f94ef44198db.
"""

from __future__ import annotations

import ast

import base64

import contextlib
import math
import sqlite3
import urllib.request

import copy

import ctypes

import errno

import fcntl

import hashlib

import importlib.util

import json

import os

from pathlib import Path, PurePosixPath

import re

import stat

import subprocess

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

def package_changes(root, specification, assets):
    base=Path(root)/'state/dispatcher/project_executor/package'
    result={}
    for relative,name in specification.get('package_files',{}).items():
        relative=relpath(relative);pieces=relative.split('/')
        require(len(pieces)==2 and pieces[0] in ('plans','blobs','contracts','manifests')
                and name in assets,'PACKAGE_SCOPE')
        expected=pieces[1][:-5] if pieces[1].endswith('.json') else pieces[1]
        require(SHA.fullmatch(expected) is not None and digest(assets[name])==expected,'PACKAGE_ADDRESS')
        if pieces[0]!='blobs':
            doc=json.loads(assets[name]);require(isinstance(doc,dict),'PACKAGE_DOCUMENT')
        result[str((base/relative).relative_to(root))]=assets[name]
    require(result,'EMPTY_PROJECT_PACKAGE')
    return result

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

SPEC = {'schema': 'NOX_PROJECT_RUNTIME_UPDATE_SPEC_V1', 'assets': {'ru_runtime_fcb77cc59eb9a88dde68.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'ru_runtime_84d54c647b0a63447aca.py': '84d54c647b0a63447aca91d34b90372e36dcd59442e3066458a21688fcb5a595', 'ru_runtime_52e62a143d16f387899f.py': '52e62a143d16f387899ff1737ce4eb698dee5ceca510fc6f97f931c11a0aec10', 'ru_runtime_5f3221e2ab59ff2d8c78.py': '5f3221e2ab59ff2d8c787b38661844468c5207805441d3d8b929fbc36c2ef27c', 'ru_plans_a171fa7a94084a1f4b67.data': 'a171fa7a94084a1f4b6751d78097257b9ed0755fc1a46cdfb4d34a27838347dc', 'ru_blobs_fa3d69e506d727295094.data': 'fa3d69e506d72729509455f2c26b5974bb5dbbb10a0baf295c66aca92e46a9f5', 'ru_plans_79b77425ff05d3337c2e.data': '79b77425ff05d3337c2e46653e2e6e0190c2ec59848d617fa2204876fc89eb0d', 'ru_blobs_b980a61884965f4838f8.data': 'b980a61884965f4838f8deafd43dac2ea4642e41dea7870d6a6904ee5a274fc6', 'ru_plans_dd24421576ae4160fa01.data': 'dd24421576ae4160fa01ba529bdcd3fa248e5e0386f7d1b5f7b873476bd272e9', 'ru_blobs_7e625acddd71fe95988e.data': '7e625acddd71fe95988e626de71b17f31f992abbfdb3b006e83d4568ce74a03d', 'ru_blobs_4b06687bbad8fe6ab046.data': '4b06687bbad8fe6ab0466bdaf06ed9239c70da2232bf14e6820eed4919251f5e', 'ru_contracts_eece310e5608fa9c633d.data': 'eece310e5608fa9c633d7c75ce280541d9bec6af8a0c35815465ae82679d4ce4'}, 'runtime_paths': {'ru_runtime_fcb77cc59eb9a88dde68.py': 'scripts/owner_project_executor.py', 'ru_runtime_84d54c647b0a63447aca.py': 'scripts/owner_project_test_runner.py', 'ru_runtime_52e62a143d16f387899f.py': 'scripts/owner_project_model_client.py', 'ru_runtime_5f3221e2ab59ff2d8c78.py': 'scripts/owner_project_planner.py'}, 'package_files': {'plans/a171fa7a94084a1f4b6751d78097257b9ed0755fc1a46cdfb4d34a27838347dc.json': 'ru_plans_a171fa7a94084a1f4b67.data', 'blobs/fa3d69e506d72729509455f2c26b5974bb5dbbb10a0baf295c66aca92e46a9f5': 'ru_blobs_fa3d69e506d727295094.data', 'plans/79b77425ff05d3337c2e46653e2e6e0190c2ec59848d617fa2204876fc89eb0d.json': 'ru_plans_79b77425ff05d3337c2e.data', 'blobs/b980a61884965f4838f8deafd43dac2ea4642e41dea7870d6a6904ee5a274fc6': 'ru_blobs_b980a61884965f4838f8.data', 'plans/dd24421576ae4160fa01ba529bdcd3fa248e5e0386f7d1b5f7b873476bd272e9.json': 'ru_plans_dd24421576ae4160fa01.data', 'blobs/7e625acddd71fe95988e626de71b17f31f992abbfdb3b006e83d4568ce74a03d': 'ru_blobs_7e625acddd71fe95988e.data', 'blobs/4b06687bbad8fe6ab0466bdaf06ed9239c70da2232bf14e6820eed4919251f5e': 'ru_blobs_4b06687bbad8fe6ab046.data', 'contracts/eece310e5608fa9c633d7c75ce280541d9bec6af8a0c35815465ae82679d4ce4.json': 'ru_contracts_eece310e5608fa9c633d.data'}, 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_autonomy_pool.py': '2c4735938dacd2a062ed2ee0b20477a6191d39b0fcf2b6c49686c10133047102', 'scripts/owner_subagent_instruction_truth.py': '485d4a4a571c434afb98512547a7f2a2198606eb1e168b749ae607aaf3c2133f', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'config/owner_native_subagents.json': '6df47b8e65801f1c22af8bf46e3d836b8776b08bf771a54568e2b477d7e8b848', 'scripts/owner_project_executor.py': '687ea3b3548badf9b7babd8c5d420b5270e0fb4d82a72bcaa9a4cee1be44d306', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': '119115603be6dba84121dc2c9c3460482e85fe59f4e5b2598551bcd62ffbdff1', 'scripts/owner_project_native.py': 'd0ff44d4752128c267799202620c34d2503241dad1f7008f8b3539f49efc18b5', 'scripts/owner_project_planner.py': '126c77c1281b7467693063bfe33d17c89eb0d553a1e8ff112ae058994e0a30ba', 'scripts/owner_project_test_runner.py': '35b0e94f9c883da017e444162d1f84b9c0f8ad7bc4c92354bebd12551ae6c3b1'}, 'expected_director': {'pid': 3734446, 'start_ticks': 175943736}, 'expected_workers': [{'pid': 3734568, 'start_ticks': 175944600}, {'pid': 3734569, 'start_ticks': 175944600}, {'pid': 3734570, 'start_ticks': 175944600}], 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}, 'catalog_append': [{'id': '3A02.project.readback_revoke.layout_retry.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'source_sha256': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'priority': 'P1', 'resource': 'CPU_LIGHT', 'deps': [], 'params': {'parent_task_id': '3A02', 'plan_sha256': 'a171fa7a94084a1f4b6751d78097257b9ed0755fc1a46cdfb4d34a27838347dc'}}, {'id': '3B05.project.strict_skill_json.layout_retry.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'source_sha256': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'priority': 'P1', 'resource': 'CPU_LIGHT', 'deps': [], 'params': {'parent_task_id': '3B05', 'plan_sha256': '79b77425ff05d3337c2e46653e2e6e0190c2ec59848d617fa2204876fc89eb0d'}}, {'id': '6V14-04.project.receipt_time_order.fd_retry.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q1_RUNTIME_CHAT', 'source_sha256': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'priority': 'P1', 'resource': 'CPU_LIGHT', 'deps': [], 'params': {'parent_task_id': '6V14-04', 'plan_sha256': 'dd24421576ae4160fa01ba529bdcd3fa248e5e0386f7d1b5f7b873476bd272e9'}}, {'id': '1A03.project.cursor_admission.focus_retry.20261118', 'handler': 'owner_native_project_work', 'queue_id': 'Q1_RUNTIME_CHAT', 'source_sha256': '71dd03dee52f1673c2977fd2abac05c623cea1d1d5049a0645f9eb66314f20e4', 'deps': [], 'priority': 'P1', 'resource': 'CPU_LIGHT', 'estimated_cost': 2, 'title': 'Implement request cursor admission using current focused source and protected tests', 'params': {'parent_task_id': '1A03', 'contract_sha256': 'eece310e5608fa9c633d7c75ce280541d9bec6af8a0c35815465ae82679d4ce4'}}], 'retry_of': {'3A02.project.readback_revoke.layout_retry.20261118': '3A02.project.readback_revoke.20261118', '3B05.project.strict_skill_json.layout_retry.20261118': '3B05.project.strict_skill_json.20261118', '6V14-04.project.receipt_time_order.fd_retry.20261118': '6V14-04.project.receipt_time_order.20261118', '1A03.project.cursor_admission.focus_retry.20261118': '1A03.project.cursor_admission.20261118'}, 'terminal_receipts': {'1A03.project.cursor_admission.20261118': 'cd585f48de5d8947081ebe34982b9ec2be974b97df66e81f073c6c9860267a84', '3A02.project.readback_revoke.20261118': '6b6e7addf886ac52ab6b496d6f1cf3d2097f2eecc765c1667f22281033144970', '3B05.project.strict_skill_json.20261118': '4948d762437c79d9a52dfb26f2f822d1a52bea7bfc07a675604e341fd4240a8e', '6V14-04.project.receipt_time_order.20261118': '6f117bd8ac9f584e5380e4ef494574df19fe2876dfd001e2d18024bb30a31c52'}, 'wait_for_idle_seconds': 40}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

UPDATE_SCHEMA = 'NOX_PROJECT_RUNTIME_UPDATE_SPEC_V1'
SANDBOX_MODULES = frozenset({'owner_project_executor.py','owner_project_test_runner.py'})
MODEL_MODULES = frozenset({'owner_project_planner.py','owner_project_model_client.py','owner_project_model_bridge.py'})
UPDATE_MODULES = SANDBOX_MODULES | MODEL_MODULES
RETRY_PARENTS = frozenset({'1A03','3A02','3B05','6V14-04'})

def decode_update_assets(bundle, specification):
    require(specification.get('schema')==UPDATE_SCHEMA,'UPDATE_SPEC_SCHEMA')
    expected=specification.get('assets')
    require(isinstance(expected,dict) and 1<=len(expected)<=64 and set(bundle)==set(expected),'UPDATE_BUNDLE_FILESET')
    assets={};total=0
    for name,pin in expected.items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name)
                and SHA.fullmatch(str(pin)),'UPDATE_ASSET_NAME_PIN')
        value=bundle[name];require(isinstance(value,str) and len(value)<=4*1024*1024,'UPDATE_ASSET_BOUND')
        raw=base64.b64decode(value,validate=True);total+=len(raw)
        require(len(raw)<=2*1024*1024 and total<=16*1024*1024 and digest(raw)==pin,'UPDATE_ASSET_DIGEST')
        assets[name]=raw
    paths=specification.get('runtime_paths')
    require(isinstance(paths,dict) and 2<=len(paths)<=5,'UPDATE_RUNTIME_SET')
    runtime={}
    for name,relative in paths.items():
        require(name in assets and relative=='scripts/'+Path(relative).name
                and Path(relative).name in UPDATE_MODULES and relative not in runtime,'UPDATE_RUNTIME_PATH')
        compile(assets[name],Path(relative).name,'exec');runtime[relative]=assets[name]
    require({'scripts/'+name for name in SANDBOX_MODULES}<=runtime.keys(),'UPDATE_SANDBOX_REQUIRED')
    return assets,runtime

def validate_append_row(row,known,callback):
    required={'id','handler','deps','resource','source_sha256','params','queue_id'}
    require(isinstance(row,dict) and required<=row.keys()
            and not row.keys()-(required|{'priority','title','estimated_cost'}),'UPDATE_ROW_FIELDS')
    tid=row['id'];params=row['params'];deps=row['deps'];cost=row.get('estimated_cost',1)
    require(isinstance(tid,str) and IDENT.fullmatch(tid) and tid not in known
            and row['handler']==PROJECT_HANDLER and row['source_sha256']==callback
            and row['queue_id'] in QUEUE_IDS and row['resource']=='CPU_LIGHT','UPDATE_ROW_SCOPE')
    require(isinstance(params,dict) and params.get('parent_task_id') in RETRY_PARENTS
            and tid.startswith(params['parent_task_id']+'.'),'UPDATE_ROW_PARENT')
    field='contract_sha256' if params['parent_task_id']=='1A03' else 'plan_sha256'
    require(set(params)=={'parent_task_id',field} and SHA.fullmatch(str(params[field])),'UPDATE_ROW_REFERENCE')
    require(isinstance(deps,list) and all(isinstance(x,str) and IDENT.fullmatch(x) for x in deps)
            and len(deps)==len(set(deps)) and tid not in deps,'UPDATE_ROW_DEPS')
    require(row.get('priority','P2') in ('P0','P1','P2','P3') and type(cost) in (int,float)
            and math.isfinite(cost) and 0<cost<=100000 and isinstance(row.get('title',tid),str)
            and 1<=len(row.get('title',tid))<=180,'UPDATE_ROW_PRESENTATION')

def compose_update(raw,runtime,specification,root):
    current=json.loads(raw)
    require(current.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and current.get('instance_id')==60509551
            and current.get('execution_mode')=='NATIVE_PROJECT_V1' and current.get('owner_authorized') is True
            and current.get('mode')=='NORMAL' and current.get('target')==3 and current.get('global_worker_cap')==3,
            'UPDATE_CURRENT_CONFIG')
    project=current.get('project_executor') or {}
    require(project.get('schema')=='NOX_PROJECT_EXECUTOR_CONFIG_V1' and project.get('enabled') is True
            and project.get('max_workers')==3 and project.get('package_root')==str(Path(root)/'state/dispatcher/project_executor/package')
            and project.get('state_root')==str(Path(root)/'state/dispatcher/project_executor/run')
            and project.get('roots',{}).get('NOX_PROJECT_SOURCE',{}).get('path')==str(Path(root)/'projects/owner_executor/source_workspace'),
            'UPDATE_PROJECT_CONFIG')
    catalog=current.get('catalog') or {};old=catalog.get('tasks')
    require(catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1' and isinstance(old,list)
            and digest(encoded(catalog))==current.get('catalog_sha256'),'UPDATE_CATALOG_HASH')
    known={row['id'] for row in old};require(len(known)==len(old),'UPDATE_OLD_DUPLICATE')
    callback=current.get('module_pins',{}).get('owner_subagent_dispatcher.py')
    require(callback==specification['expected_native'].get('scripts/owner_subagent_dispatcher.py')
            and SHA.fullmatch(str(callback)),'UPDATE_CALLBACK_PIN')
    new=specification.get('catalog_append');retry=specification.get('retry_of')
    require(isinstance(new,list) and len(new)==4 and isinstance(retry,dict),'UPDATE_RETRY_COUNT')
    parents=set();ids=set()
    for row in new:
        validate_append_row(row,known|ids,callback);parents.add(row['params']['parent_task_id']);ids.add(row['id'])
        reference=row['params'].get('plan_sha256') or row['params'].get('contract_sha256')
        directory='plans' if 'plan_sha256' in row['params'] else 'contracts'
        require(directory+'/'+reference+'.json' in specification['package_files'],'UPDATE_REFERENCE_ASSET')
    require(parents==RETRY_PARENTS and set(retry)==ids and len(set(retry.values()))==4
            and all(isinstance(old_id,str) and old_id in known for old_id in retry.values()),'UPDATE_RETRY_MAPPING')
    remaining={row['id']:set(row['deps']) for row in new}
    require(all(deps<=known|ids for deps in remaining.values()),'UPDATE_UNKNOWN_DEPENDENCY')
    remaining={tid:deps-known for tid,deps in remaining.items()}
    while remaining:
        ready={tid for tid,deps in remaining.items() if not deps};require(ready,'UPDATE_DEPENDENCY_CYCLE')
        remaining={tid:deps-ready for tid,deps in remaining.items() if tid not in ready}
    result=copy.deepcopy(current)
    for relative,source in runtime.items():
        name=Path(relative).name;pin=digest(source)
        require(name in UPDATE_MODULES and name in current['module_pins'],'UPDATE_RUNTIME_EXISTING_MODULE')
        result['module_pins'][name]=pin
        if name in SANDBOX_MODULES:result['project_executor']['source_pins'][name]=pin
        else:result['project_executor']['model']['source_pins'][name]=pin
    result['catalog']['tasks'].extend(copy.deepcopy(new));result['catalog_sha256']=digest(encoded(result['catalog']))
    # Reversing exactly the authorized edits must reconstruct the entire old config.
    check=copy.deepcopy(result)
    check['catalog']=current['catalog'];check['catalog_sha256']=current['catalog_sha256']
    for relative in runtime:
        name=Path(relative).name;check['module_pins'][name]=current['module_pins'][name]
        group=check['project_executor']['source_pins'] if name in SANDBOX_MODULES else check['project_executor']['model']['source_pins']
        previous=current['project_executor']['source_pins'] if name in SANDBOX_MODULES else current['project_executor']['model']['source_pins']
        group[name]=previous[name]
    require(check==current and result['catalog']['tasks'][:-4]==old,'UPDATE_UNRELATED_CONFIG_CHANGE')
    return current,result

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

def terminal_proofs(root,state,specification,config):
    expected=specification.get('terminal_receipts');retry=specification['retry_of']
    require(isinstance(expected,dict) and set(expected)==set(retry.values()),'UPDATE_TERMINAL_PINS')
    tasks=state['tasks'];proofs={};new_by_id={row['id']:row for row in specification['catalog_append']}
    for new_id,old_id in retry.items():
        row=tasks.get(old_id) or {};result=row.get('result') or {};receipt=result.get('receipt') or {}
        require(row.get('status')=='blocked' and row.get('handler')==PROJECT_HANDLER
                and row.get('parent_task_id')==new_by_id[new_id]['params']['parent_task_id']
                and new_id not in tasks,'UPDATE_RETRY_TERMINAL_REQUIRED')
        pin=digest(encoded(receipt));claim=row.get('owner_claim') or {}
        evidence=(receipt.get('worker_result') or {}).get('project_evidence') or {}
        require(SHA.fullmatch(str(expected[old_id])) and pin==expected[old_id] and result.get('receipt_sha256')==pin
                and result.get('verified') is True and receipt.get('claim')==claim
                and claim.get('pid')==specification['expected_director']['pid']
                and re.fullmatch(r'[a-f0-9]{24}',str(claim.get('nonce','')))
                and receipt.get('task_id')==old_id and receipt.get('source_sha256')==config['module_pins']['owner_subagent_dispatcher.py']
                and receipt.get('phase')=='PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                and receipt.get('original_task_accepted') is False and receipt.get('project_source_changed') is False
                and evidence.get('project_source_changed') is False,'UPDATE_TERMINAL_RECEIPT')
        proofs[old_id]=exact_s03(root,receipt)
    for row in specification['catalog_append']:
        require(all(dep in new_by_id or tasks.get(dep,{}).get('status')=='done' for dep in row['deps']),
                'UPDATE_UNSATISFIED_DEPENDENCY')
    return proofs

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

def unchanged_history(before,after):
    old=before['tasks'];new=after['tasks']
    missing=sorted(set(old)-set(new))
    protected={key:row for key,row in old.items() if row.get('owner_claim') or row.get('result') is not None}
    changed=[key for key,row in protected.items() if any(row.get(field)!=new.get(key,{}).get(field)
        for field in ('owner_claim','result','native_project_terminal'))]
    return {'old_count':len(old),'missing_old_ids':missing,'historical_entries':len(protected),
            'changed_claim_or_result_ids':changed,'verified':not missing and not changed}

def model_prompt_preflight(root,project,contract,snapshot,modules,runtime):
    name='owner_project_planner.py';raw=runtime.get('scripts/'+name)
    if raw is None:raw=read_regular(Path(root)/'scripts'/name)
    require(digest(raw)==project['model']['source_pins'][name],'UPDATE_PROMPT_PLANNER_PIN')
    atomic(modules/name,raw,0o644)
    loader=importlib.util.spec_from_file_location('_nox_approved_prompt_preflight_planner',modules/name)
    require(loader is not None and loader.loader is not None,'UPDATE_PROMPT_LOADER')
    planner=importlib.util.module_from_spec(loader);loader.loader.exec_module(planner)
    captured=[]
    class Captured(Exception):pass
    def capture(messages):captured.append(copy.deepcopy(messages));raise Captured()
    def no_verifier(*args):raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_PROMPT_UNEXPECTED_VERIFIER')
    try:planner.plan_task(contract,snapshot,capture,no_verifier,lambda:not stop_clear(root))
    except Captured:pass
    require(len(captured)==1,'UPDATE_FIRST_PROMPT_CAPTURE')
    messages=captured[0]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_PROMPT_REDIRECT')
    def request(path,payload=None):
        require(path in ('/v1/models','/props','/apply-template','/tokenize'),'UPDATE_PROMPT_ENDPOINT')
        data=None if payload is None else encoded(payload)
        require(data is None or len(data)<=256*1024,'UPDATE_PROMPT_REQUEST_BOUND')
        req=urllib.request.Request('http://127.0.0.1:8098'+path,data=data,
            method='GET' if payload is None else 'POST',headers={'Content-Type':'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=15) as response:
            require(response.status==200,'UPDATE_PROMPT_HTTP_STATUS');reply=response.read(512*1024+1)
        require(len(reply)<=512*1024,'UPDATE_PROMPT_REPLY_BOUND');return json.loads(reply)
    models=request('/v1/models')
    require(isinstance(models,dict) and any(isinstance(row,dict) and row.get('id')==project['model']['expected_model_id']
        for row in models.get('data',[])),'UPDATE_PROMPT_MODEL_ID')
    props=request('/props');context=(props.get('default_generation_settings') or {}).get('n_ctx')
    require(type(context) is int and context==4096,'UPDATE_PROMPT_CONTEXT')
    rendered=request('/apply-template',{'messages':messages})
    require(isinstance(rendered,dict) and isinstance(rendered.get('prompt'),str),'UPDATE_PROMPT_TEMPLATE')
    tokenized=request('/tokenize',{'content':rendered['prompt'],'add_special':False,'parse_special':True,'with_pieces':False})
    tokens=tokenized.get('tokens') if isinstance(tokenized,dict) else None
    require(isinstance(tokens,list) and all(type(x) is int for x in tokens),'UPDATE_PROMPT_TOKENIZER')
    maximum=project['model']['max_tokens'];require(type(maximum) is int and 128<=maximum<=1200,'UPDATE_PROMPT_OUTPUT_BUDGET')
    summary={'schema':'NOX_PROJECT_MODEL_PROMPT_PREFLIGHT_V1','task_id':contract['task_id'],
        'prompt_messages_sha256':digest(encoded(messages)),'rendered_prompt_sha256':digest(rendered['prompt'].encode()),
        'input_tokens':len(tokens),'context_tokens':context,'max_output_tokens':maximum,'reserve_tokens':128,
        'first_prompt_unmodified':True,'model_inference_called':False,'source_tree_changed':False,
        'fits_context':len(tokens)+maximum+128<=context}
    atomic(modules.parent/'model_prompt_preflight.json',encoded(summary))
    print('NOX_MAINT_PROJECT_MODEL_PROMPT_PREFLIGHT='+encoded(summary).decode(),flush=True)
    require(summary['fits_context'],'UPDATE_FIRST_PROMPT_CONTEXT_EXCEEDED')
    return summary

def stage_and_validate_retries(root,project,package,preflight,specification,runtime):
    stage=Path(preflight['path']);modules=stage/'modules';review=stage/'reviewed-package';review.mkdir(mode=0o700)
    base=Path(root)/'state/dispatcher/project_executor/package'
    for relative,raw in package.items():
        target=Path(root)/relative;sub=target.relative_to(base);atomic(review/sub,raw)
    clone=copy.deepcopy(project);clone.update(package_root=str(review),state_root=str(stage/'reviewed-run'))
    loader=importlib.util.spec_from_file_location('_nox_approved_runtime_update_executor',modules/'owner_project_executor.py')
    require(loader is not None and loader.loader is not None,'UPDATE_EXECUTOR_LOADER')
    executor=importlib.util.module_from_spec(loader);loader.loader.exec_module(executor);executor.validate_config(clone)
    result=[]
    with executor.tree(project['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
        for row in specification['catalog_append']:
            reference={key:value for key,value in row['params'].items() if key in ('plan_sha256','contract_sha256')}
            if 'plan_sha256' in reference:
                plan=executor.load_plan(reference,clone)
                require(plan.get('review_origin')=='OWNER_REVIEWED','UPDATE_REVIEWED_RETRY')
                for patch in plan['files']:
                    payload=read_regular(review/'blobs'/patch['payload_sha256'])
                    require(digest(payload)==patch['payload_sha256']==patch['after_sha256'],'UPDATE_RETRY_PAYLOAD')
                source_check=plan
            else:
                plan=executor.load_contract_metadata(reference,clone)
                source_check={'context':plan['context'],'files':[]}
            require(plan['task_id']==row['id'] and plan['parent_task_id']==row['params']['parent_task_id']
                    and plan['queue_id']==row['queue_id'] and plan['root_id']=='NOX_PROJECT_SOURCE','UPDATE_PLAN_IDENTITY')
            snapshot=executor._check_source(handle,source_check)
            item={'task_id':row['id'],'reference':reference,'source_preimages_verified':True}
            if 'plan_sha256' in reference:
                checked=executor.prepare(reference,clone,digest(('update-preflight:'+row['id']).encode())[:24],
                    stop_check=lambda:not stop_clear(root))
                evidence=checked.get('project_evidence') or {};tests=evidence.get('tests') or {};facts=tests.get('sandbox') or {}
                item['native_prepared']={'state':checked.get('state'),'tests':tests,'reason':evidence.get('reason'),
                    'evidence_sha256':checked.get('project_evidence_sha256'),'shared_source_integrated':False}
                print('NOX_MAINT_PROJECT_RETRY_PREFLIGHT='+encoded(item).decode(),flush=True)
                require(checked.get('state')=='PREPARED' and checked.get('passed') is True
                    and checked.get('sandbox_verified') is True and checked.get('trusted_tests_unchanged') is True
                    and tests.get('passed') is True and type(tests.get('tests_run')) is int
                    and tests['tests_run']>=plan['verification']['min_tests']
                    and all(tests.get(key)==0 for key in ('failures','errors','skipped'))
                    and facts.get('uid')==65534 and facts.get('gid')==65534
                    and all(facts.get(key) is True for key in ('network_denied','fork_denied','exec_denied',
                        'host_path_hidden','no_new_privs','seccomp_filter')),'UPDATE_RETRY_NATIVE_PREFLIGHT_FAILED')
                executor._check_source(handle,source_check)
            else:item['prompt_preflight']=model_prompt_preflight(root,project,plan,
                {path:value[0] for path,value in snapshot.items()},modules,runtime)
            result.append(item)
    return result

def update_receipt(root,request,receipt):
    raw=encoded(receipt);path=Path(root)/'state/dispatcher'/('project_runtime_update_'+request+'.json')
    atomic(path,raw);require(read_regular(path)==raw,'UPDATE_RECEIPT_READBACK')
    print('NOX_MAINT_PROJECT_RUNTIME_UPDATE='+raw.decode(),flush=True)

def update(bundle,specification,root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'UPDATE_OWNER_CONTEXT')
    root=Path(root);assets,runtime=decode_update_assets(bundle,specification)
    expected=specification['expected_native']
    require(isinstance(expected,dict) and CONFIG in expected and all(path==CONFIG or
            re.fullmatch(r'scripts/(?:owner_[a-z0-9_]+|nox_dispatcher_t855u)\.py',path) for path in expected),'UPDATE_EXPECTED_NATIVE_SCOPE')
    before=preimages(root,expected);old,proposed=compose_update(before[CONFIG],runtime,specification,root)
    require(all(expected.get('scripts/'+name)==pin for name,pin in old['module_pins'].items())
            and 'scripts/nox_dispatcher_t855u.py' in expected,'UPDATE_ALL_MODULE_PREIMAGES')
    package=package_changes(root,specification,assets)
    dependency=old['project_executor']['dependency_manifest'];dep_relative=str(Path(dependency['path']).relative_to(root))
    dep_raw=read_regular(root/dep_relative);require(digest(dep_raw)==dependency['sha256'],'UPDATE_DEPENDENCY_PIN')
    if dep_relative in package:require(package[dep_relative]==dep_raw,'UPDATE_DEPENDENCY_CHANGED')
    package[dep_relative]=dep_raw
    changes={relative:raw for relative,raw in runtime.items() if raw!=before.get(relative)}
    for relative,raw in package.items():
        try:current=read_regular(root/relative)
        except FileNotFoundError:current=None
        require(current is None or current==raw,'UPDATE_IMMUTABLE_PACKAGE_CONFLICT')
        if current is None:before[relative]=None;changes[relative]=raw
    changes[CONFIG]=encoded(proposed)
    protected=protected_snapshot(specification);expected_processes(specification)
    require(stop_clear(root),'UPDATE_OWNER_STOP')
    lockpath=root/'state/owner_maintenance.lock';require(not lockpath.is_symlink(),'UPDATE_LEASE_PATH')
    fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_PROJECT_RUNTIME_UPDATE_RECEIPT_V1','request':request,'source_sha':source,
        'state':'PREFLIGHT','started_at':time.time(),'source_tree_writes':0,'queue_writes':0,'source_reseeded':False,
        'training_started':False,'model_restarted':False,'original_tasks_accepted':0,'runtime_changed':sorted(runtime)}
    applied=[];old_descendants=[];final_state=None;source_before=None;stop_attempted=False;new_director=None;new_owned=[]
    def lease_guard():
        info=os.fstat(fd);named=lockpath.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and not info.st_mode&0o022
                and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'UPDATE_LEASE_CHANGED')
    def guard():
        lease_guard();require(stop_clear(root),'UPDATE_OWNER_STOP_CHANGED')
        require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED')
    try:
        wait=specification.get('wait_for_idle_seconds',40);require(type(wait) is int and 0<=wait<=120,'UPDATE_WAIT_BOUND')
        deadline=time.monotonic()+wait
        while True:
            require(stop_clear(root),'UPDATE_OWNER_STOP_WHILE_WAITING');expected_processes(specification)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:require(time.monotonic()<deadline,'UPDATE_ACTIVE_PROJECT_LEASE');time.sleep(.5)
        guard();expected_processes(specification);preimages(root,expected)
        deadline=time.monotonic()+40
        while True:
            state,active=queue_idle(root)
            if not active:break
            guard();require(time.monotonic()<deadline,'UPDATE_ACTIVE_CLAIMS');time.sleep(.5)
        receipt['terminal_receipts']=terminal_proofs(root,state,specification,old)
        source_before=source_snapshot(root,old);receipt['source_before']=source_before
        receipt['native_sandbox_preflight']=sandbox_preflight(root,runtime,package,proposed['project_executor'],request)
        receipt['reviewed_retries']=stage_and_validate_retries(root,proposed['project_executor'],package,
            receipt['native_sandbox_preflight'],specification,runtime)
        guard();expected_processes(specification);preimages(root,expected)
        require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_DURING_PREFLIGHT')
        baseline,active=queue_idle(root);require(not active,'UPDATE_ACTIVE_AFTER_PREFLIGHT')
        terminal_proofs(root,baseline,specification,old)
        require(unchanged_history(state,baseline)['verified'],'UPDATE_HISTORY_CHANGED_BEFORE_STOP')
        backup=root/'state/dispatcher/project_runtime_update_rollback'/request
        require(not backup.exists() and not backup.is_symlink(),'UPDATE_BACKUP_EXISTS');backup.mkdir(parents=True,mode=0o700)
        for relative in changes:
            if before.get(relative) is not None:atomic(backup/relative,before[relative])
        atomic(backup/'original_queue_snapshot.json',encoded(baseline));atomic(backup/'source_snapshot.json',encoded(source_before))
        receipt['backup_path']=str(backup);previous=expected_processes(specification)['director']
        require(supervisor('status').get('pid')==previous['pid'],'UPDATE_SUPERVISOR_IDENTITY')
        old_descendants=descendant_snapshot(previous['pid']);receipt['previous_descendants']=old_descendants
        receipt['previous_director']=previous;stop_attempted=True;stop_checked()
        require(process_identity(previous['pid']) is None,'UPDATE_OLD_DIRECTOR_ALIVE')
        receipt['previous_descendants_stopped']=wait_previous_descendants_stopped(old_descendants)
        guard();final_state,active=queue_idle(root);require(not active,'UPDATE_ACTIVE_AFTER_STOP')
        require(unchanged_history(baseline,final_state)['verified'],'UPDATE_HISTORY_CHANGED_ON_STOP')
        terminal_proofs(root,final_state,specification,old)
        require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_ON_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_state))
        receipt['final_stopped_queue_sha256']=digest(encoded(final_state))
        applied=apply_transaction(root,changes,before)
        guard();require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_AFTER_APPLY')
        new_director=start_update_checked(root,new_owned);receipt['new_director']=new_director
        guard();require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_BEFORE_RELEASE')
        receipt.update(state='UPDATED_RETRIES_PENDING',installed_files={path:digest(raw) for path,raw in changes.items()},
            source_preserved_before_admission=True,old_catalog_preserved=True,callback_unchanged=True,protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_COMPLETE_EXECUTOR_UPDATE_'+type(exc).__name__
        try:
            lease_guard()
            if applied:
                current=supervisor('status');pid=current.get('pid')
                if current['state']=='RUNNING':
                    identity=process_identity(pid)
                    require(new_owned and identity==new_owned[0],'UPDATE_FOREIGN_DIRECTOR_NO_ROLLBACK')
                    new_children=descendant_snapshot(pid);stop_checked();wait_previous_descendants_stopped(new_children)
                else:require(current['state'] in ('STOPPED','FATAL','EXITED'),'UPDATE_UNKNOWN_DIRECTOR_NO_ROLLBACK')
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stop_attempted and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and stop_clear(root):
                require(not live_previous_descendants(old_descendants),'UPDATE_OLD_CHILDREN_ALIVE')
                require(all(before.get(path) is None or read_regular(root/path)==before[path] for path in changes),'UPDATE_ROLLBACK_UNVERIFIED')
                require(source_before is None or source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_NO_RESTART')
                require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED_NO_RESTART')
                receipt['restored_director']=start_checked(root);receipt['restored_original_runtime']=True
        except Exception as recovery:
            receipt['recovery']=str(recovery) if isinstance(recovery,Hold) else 'HOLD_UPDATE_RECOVERY_'+type(recovery).__name__
        receipt['finished_at']=time.time();update_receipt(root,request,receipt);raise
    finally:os.close(fd)
    ids=[row['id'] for row in specification['catalog_append']];snapshots=[];last=None
    deadline=time.monotonic()+40
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'UPDATE_OWNER_STOP_DURING_ADMISSION')
            require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED_AFTER_RELEASE')
            try:
                last=acceptance_snapshot(root,ids)
                require(last.get('director')==new_director,'UPDATE_NEW_DIRECTOR_CHANGED')
                if len(last['workers'])==len({row['pid'] for row in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if stable_three(snapshots) and any(row['claim_present'] for row in last['tasks']):break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        after,_=queue_idle(root);receipt['history_preservation']=unchanged_history(final_state,after)
        require(receipt['history_preservation']['verified'],'UPDATE_HISTORY_PRESERVATION_FAILED')
        live=bool(last and stable_three(snapshots) and last is snapshots[-1])
        running=bool(last and any(row['status']=='running' for row in last['tasks']))
        admitted=bool(last and any(row['claim_present'] for row in last['tasks']))
        receipt.update(state='UPDATED_RETRY_WORK_RUNNING' if live and running else
            'UPDATED_RETRY_WORK_ADMITTED' if live and admitted else 'UPDATED_RETRIES_PENDING',
            three_live_workers_verified=live,readback=last,process_snapshots=snapshots)
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_UPDATE_ADMISSION_READBACK'
        receipt['readback']=last;receipt['process_snapshots']=snapshots
    receipt['finished_at']=time.time();update_receipt(root,request,receipt);return receipt

def main():
    update(BUNDLE,SPEC)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':main()

