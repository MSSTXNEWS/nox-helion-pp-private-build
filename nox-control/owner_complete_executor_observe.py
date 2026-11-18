#!/usr/bin/env python3
"""Fixed read-only NOX queue/pool inspection. No model calls or native writes."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SOURCE_NAMES = (
    'owner_subagent_dispatcher.py', 'owner_subagent_processes.py',
    'owner_autonomy_pool.py', 'owner_task_plans.py',
    'owner_component_tasks.py', 'nox_auto_architect.py', 'owner_dispatcher_mentor.py',
)
FLAGS = (
    ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop',
    ROOT/'program/STOP', ROOT/'state/STOP', ROOT/'state/STOP.flag',
    Path('/workspace/NOX_STOP'), ROOT/'state/OWNER_MAINTENANCE.flag',
    ROOT/'state/TRAIN_HOLD.flag', ROOT/'state/TRAIN_PAUSE_REQUEST.flag',
)
LOCK_PATHS = (ROOT/'state/owner_maintenance.lock', ROOT/'state/dispatcher/native_subagents.lock')
IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:/@ -]{1,250}$')
SHA = re.compile(r'^[0-9a-f]{40,64}$')
PLANNER_MEMORY_TRACE_SHA = 'aa0dd1c8266106b599ce83b64b7af77c7a4f32377fc09cd545e1f9697bda4420'
MAX_SOURCE_FILE = 2 * 1024 * 1024
MAX_SOURCE_TOTAL = 16 * 1024 * 1024


def approved_relative(value):
    if (not isinstance(value,str) or not 1<=len(value)<=240
            or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*',part)
                   or part in ('.','..') for part in value.split('/'))):
        raise ValueError('UNAPPROVED_RELATIVE_PATH')
    return value


def project_observation_scope(config):
    project=config.get('project_executor') or {}
    root=(project.get('roots') or {}).get('NOX_PROJECT_SOURCE') or {}
    expected=ROOT/'projects/owner_executor/source_workspace'
    allowed=root.get('allowed_paths')
    if (config.get('schema')!='NOX_NATIVE_SUBAGENT_BINDING_V1'
            or project.get('schema')!='NOX_PROJECT_EXECUTOR_CONFIG_V1'
            or root.get('path')!=str(expected)
            or root.get('integration_kind')!='SOURCE_WORKSPACE'
            or project.get('package_root')!=str(ROOT/'state/dispatcher/project_executor/package')
            or project.get('state_root')!=str(ROOT/'state/dispatcher/project_executor/run')
            or not isinstance(allowed,list) or not 1<=len(allowed)<=256
            or not all(isinstance(path,str) for path in allowed)
            or len(set(allowed))!=len(allowed) or root.get('deny_paths',[])!=[]):
        raise ValueError('PROJECT_OBSERVATION_SCOPE')
    return project,expected,sorted(approved_relative(path) for path in allowed)

def emit(name, value):
    print('NOX_MAINT_SCOPE_' + name + '=' + json.dumps(value, ensure_ascii=True,
          separators=(',', ':'), allow_nan=False), flush=True)

def safe_read(path, limit):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('ABSOLUTE_PATH_REQUIRED')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError('UNSAFE_TYPE_OR_SIZE')
            chunks = []
            total = 0
            while total <= limit:
                b = os.read(fd, min(65536, limit + 1 - total))
                if not b:
                    break
                chunks.append(b)
                total += len(b)
            after = os.fstat(fd)
            if total > limit or any(getattr(before, k) != getattr(after, k) for k in
                    ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('CHANGED_OR_OVERSIZED')
            return b''.join(chunks), after
        finally:
            os.close(fd)
    finally:
        os.close(parent)

def obj(path, limit=2000000):
    raw, info = safe_read(path, limit)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('OBJECT_REQUIRED')
    return data, raw, info

def redact_source(value):
    out = re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]', value)
    out = re.sub(r'(?i)(https?://)[^/\s@]+:[^/\s@]+@', r'\1[REDACTED]@', out)
    out = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.~+/=-]{12,}', r'\1[REDACTED]', out)
    out = re.sub(r'\b(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}', '[REDACTED_TOKEN]', out)
    out = re.sub(r'''(?i)((?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*["'])([^"'\n]{12,})(["'])''', r'\1[REDACTED]\3', out)
    out = re.sub(r'(?i)([?&](?:token|key|password|signature|secret)=)[^\s&"\']+', r'\1[REDACTED]', out)
    return out

def identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None

def scalar_projection(data, names):
    result = {}
    for name in names:
        value = data.get(name)
        if value is None or isinstance(value, (bool, int)) or isinstance(value, float) and __import__('math').isfinite(value):
            result[name] = value
        elif isinstance(value, str) and len(value) <= 300:
            result[name] = redact_source(value)
    return result

def process(pid):
    try:
        p = Path('/proc')/str(int(pid))
        raw = (p/'stat').read_text()
        fields = raw.rsplit(') ', 1)[1].split()
        result = {'pid':int(pid), 'ppid':int(fields[1]), 'pgrp':int(fields[2]),
                  'start_ticks':int(fields[19]), 'state':fields[0]}
        ns = re.search(r'^NSpid:\s*(.*)$', (p/'status').read_text(), re.M)
        result['namespace_pids'] = [int(x) for x in ns[1].split()] if ns else []
        # Export two non-secret dispatcher controls, never an environment dump.
        result['dispatcher_env'] = {}
        for entry in (p/'environ').read_bytes().split(b'\0'):
            if b'=' not in entry:
                continue
            key, value = entry.split(b'=', 1)
            if key in (b'NOX_DISPATCHER_SAFE', b'NOX_DISPATCHER_WORKERS') and re.fullmatch(rb'[0-9]{1,2}', value):
                result['dispatcher_env'][key.decode()] = value.decode()
        again = (p/'stat').read_text().rsplit(') ', 1)[1].split()
        if int(again[19]) != result['start_ticks']:
            raise ValueError('PID_CHANGED')
        return result
    except (OSError, ValueError, IndexError):
        return {'pid':pid, 'status':'UNKNOWN_OR_CHANGED'}

def runtime_snapshot():
    rows = []
    cp = subprocess.run(['supervisorctl', 'status'], capture_output=True, text=True,
                        timeout=10, check=False)
    keep = {'nox-dispatcher-t855u', 'nox-ds41-8098', 'nox-proxy', 'nox-web29-18775',
            'nox-agent-architect-t859u', 'nox-agent-integrator-t859u', 'nox-agent-tuner-t858u'}
    for line in cp.stdout.splitlines():
        m = re.match(r'^([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+))?', line)
        if m and m[1] in keep:
            rows.append({'service':m[1], 'state':m[2],
                         'identity':process(int(m[3])) if m[3] else None})
    flags = {}
    for path in FLAGS:
        try:
            mode = path.lstat().st_mode
            flags[str(path)] = 'PRESENT' if stat.S_ISREG(mode) else 'UNSAFE_TYPE'
        except FileNotFoundError:
            flags[str(path)] = 'ABSENT'
        except OSError:
            flags[str(path)] = 'UNKNOWN'
    resources = {}
    for name in ('memory.current','memory.max','memory.stat','memory.events',
                 'memory.pressure','cpu.pressure','cpu.stat','cpu.max','io.pressure'):
        try:
            resources[name] = (Path('/sys/fs/cgroup')/name).read_text()[:10000]
        except OSError:
            resources[name] = None
    return {'time_unix':time.time(), 'supervisor_rc':cp.returncode, 'services':rows,
            'flags':flags, 'resources':resources}

def locks():
    try:
        lines = Path('/proc/locks').read_text().splitlines()
    except OSError:
        lines = []
    rows = []
    for path in LOCK_PATHS:
        row = {'path':str(path), 'scope':'PROC_LOCKS_OBSERVATION_NOT_LEASE_ACQUISITION'}
        try:
            s = path.lstat()
            row.update({'present':True, 'inode':s.st_ino, 'device_major':os.major(s.st_dev),
                        'device_minor':os.minor(s.st_dev), 'type_regular':stat.S_ISREG(s.st_mode)})
            matches = []
            for line in lines:
                m = re.search(r'\b([0-9a-f]+):([0-9a-f]+):(\d+)\b', line)
                if m and (int(m[1],16),int(m[2],16),int(m[3])) == (os.major(s.st_dev),os.minor(s.st_dev),s.st_ino):
                    matches.append(line[:250])
            row['matching_kernel_locks'] = matches[:10]
        except FileNotFoundError:
            row['present'] = False
        except OSError:
            row['status'] = 'UNKNOWN'
        rows.append(row)
    return rows


def configuration():
    path = ROOT/'config/owner_native_subagents.json'
    try:
        data, raw, info = obj(path, 1000000)
        row = scalar_projection(data, ('schema','mode','target','owner_authorized','instance_id','policy_id','catalog_sha256'))
        row.update({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),
                    'owner_uid':info.st_uid,'mode_bits':oct(stat.S_IMODE(info.st_mode))})
        row['module_pins'] = {k:v for k,v in data.get('module_pins',{}).items()
                              if identifier(k) and isinstance(v,str) and SHA.fullmatch(v)}
        policy = data.get('policy',{})
        row['policy'] = scalar_projection(policy, ('path','sha256')) if isinstance(policy,dict) else None
        catalog = data.get('catalog')
        row['catalog_shape'] = {'type':type(catalog).__name__}
        if isinstance(catalog,dict):
            pages = catalog.get('pages',[])
            row['catalog_shape']['schema'] = identifier(catalog.get('schema'))
            row['catalog_shape']['pages'] = len(pages) if isinstance(pages,list) else None
            tasks = []
            if isinstance(pages,list):
                for page in pages[:32]:
                    if isinstance(page,dict) and isinstance(page.get('tasks'),list):
                        tasks.extend(page['tasks'][:100])
            if isinstance(catalog.get('tasks'),list):
                tasks.extend(catalog['tasks'][:100])
            row['catalog_shape']['tasks'] = [
                {k:identifier(task.get(k)) for k in ('id','task_id','handler','subagent','status')}
                for task in tasks[:512] if isinstance(task,dict)]
        emit('CONFIG', row)
    except (OSError, ValueError, TypeError) as exc:
        emit('CONFIG', {'path':str(path),'status':'UNKNOWN','error':type(exc).__name__})




def hash_summary():
    names = SOURCE_NAMES + ('nox_dispatcher_t855u.py', 'owner_resource_policy.py',
                            'test_owner_four_queue.py', 'test_owner_normal3_continuity.py',
                            'owner_subagent_instruction_truth.py')
    for name in names:
        try:
            raw, info = safe_read(SCRIPTS/name, 300000)
            emit('INSTALLED_SOURCE', {'path':str(SCRIPTS/name), 'bytes':len(raw),
                'sha256':hashlib.sha256(raw).hexdigest(), 'mtime_ns':info.st_mtime_ns})
        except (OSError, ValueError) as exc:
            emit('INSTALLED_SOURCE', {'path':str(SCRIPTS/name), 'state':'UNAVAILABLE', 'error':type(exc).__name__})

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def s03_receipt_check(receipt):
    import sqlite3
    path = ROOT/'kb/knowledge.sqlite'
    try:
        if any(p.is_symlink() for p in (path, *path.parents)) or not stat.S_ISREG(path.stat().st_mode):
            return {'verified':False, 'state':'UNSAFE_DATABASE_PATH'}
        digest = hashlib.sha256(encoded(receipt)).hexdigest()
        text = 'NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+digest
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.2)) as conn:
            conn.execute('PRAGMA query_only=ON')
            deadline = time.monotonic()+2
            conn.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
            rows = conn.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                                (text, 'owner_native_subagents')).fetchall()
        verified = (len(rows)==1 and rows[0][2]==hashlib.sha256(('M2|'+text).encode()).hexdigest()
                    and json.loads(rows[0][1]).get('receipt') == receipt)
        return {'verified':verified, 's03_item_id':rows[0][0] if verified else None,
                'receipt_sha256':digest, 'scope':'EXACT_READ_ONLY_SQLITE_RECEIPT_MATCH'}
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        return {'verified':False, 'state':'UNAVAILABLE', 'error':type(exc).__name__}

def leaf_queue_summary():
    data, raw, _ = obj(ROOT/'state/dispatcher/state.json',16*1024*1024)
    tasks=data.get('tasks')
    if not isinstance(tasks,dict) or len(tasks)>5000:
        raise ValueError('QUEUE_SHAPE')
    counts={}
    for task in tasks.values():
        if isinstance(task,dict):
            state=identifier(task.get('status')) or 'UNKNOWN'
            counts[state]=counts.get(state,0)+1
    emit('POST_QUEUE', {'task_count':len(tasks), 'counts':counts, 'sha256':hashlib.sha256(raw).hexdigest()})
    for key,task in tasks.items():
        if not isinstance(task,dict) or task.get('handler') not in ('owner_native_typed_leaf','owner_native_subagent_review'):
            continue
        row={k:identifier(task.get(k)) for k in ('id','handler','status','queue_id','parent_task_id','scope')}
        row['key']=identifier(key)
        claim=task.get('owner_claim')
        row['claim']=scalar_projection(claim,('pid','worker','nonce','at')) if isinstance(claim,dict) else None
        row.update(scalar_projection(task,('native_queue_sequence','original_task_accepted','retries','note')))
        result=task.get('result')
        if isinstance(result,dict):
            row['result']=scalar_projection(result,('schema','verified','scope','receipt_sha256','original_task_accepted','check_passed'))
            receipt=result.get('receipt')
            if isinstance(receipt,dict):
                row['receipt']=scalar_projection(receipt,('schema','phase','task_id','job_id','source_sha256','parent_task_id','queue_id','original_task_accepted','training_started','service_or_weights_changed','finished_at'))
                row['receipt_sha_matches']=hashlib.sha256(encoded(receipt)).hexdigest()==result.get('receipt_sha256')
                row['receipt_claim_matches']=receipt.get('claim')==claim
                event=receipt.get('worker_result')
                if isinstance(event,dict):
                    row['worker_result']=scalar_projection(event,('kind','role','pid','id','state','elapsed_ms'))
                    leaf=event.get('leaf_evidence')
                    if isinstance(leaf,dict):
                        row['leaf']=scalar_projection(leaf,('operation','queue_id','parent_task_id','original_task_accepted','scope','check_completed','check_passed','claim','started_at','finished_at','source_sha256','model_called'))
                        row['leaf_sha_matches']=hashlib.sha256(encoded(leaf)).hexdigest()==event.get('leaf_evidence_sha256')
                        row['leaf']['blockers']=[identifier(x) for x in leaf.get('blockers',[])[:20]]
                        worker=leaf.get('worker')
                        row['leaf']['worker']=scalar_projection(worker,('pid','ppid','process_starttime')) if isinstance(worker,dict) else None
                row['s03']=s03_receipt_check(receipt)
        emit('POST_TASK',row)

def worker_status_sample():
    data,raw,_=obj(ROOT/'status/agents_t856u.json',2*1024*1024)
    native=data.get('native_subexecutors')
    if not isinstance(native,dict):
        emit('POST_WORKERS', {'state':'NO_NATIVE_STATUS'})
        return
    director=native.get('director') or {}
    observed_director=process(director.get('pid')) if type(director.get('pid')) is int else None
    row={'time_unix':time.time(), 'observed_at':native.get('observed_at'),
         'claimed_director':scalar_projection(director,('pid','ppid','process_starttime')),
         'observed_director':observed_director,'workers':[]}
    for worker in native.get('workers',[])[:10]:
        if not isinstance(worker,dict):
            continue
        claimed=scalar_projection(worker,('pid','ppid','process_starttime','role','state','heartbeat_at','current_task','native_pid_verified'))
        identity=process(worker['pid']) if type(worker.get('pid')) is int else None
        verified=(isinstance(identity,dict) and identity.get('state') in ('R','S','D','I')
                  and identity.get('start_ticks')==worker.get('process_starttime')
                  and identity.get('ppid')==director.get('pid')
                  and isinstance(observed_director,dict)
                  and observed_director.get('start_ticks')==director.get('process_starttime'))
        row['workers'].append({'claimed':claimed,'observed':identity,'verified':verified})
    project=native.get('project_queues')
    if isinstance(project,dict):
        row['project']=scalar_projection(project,('state','received_unique_tasks','dispatch_cap','bound_leaf_subtasks','original_task_acceptance_added','scope'))
        for name in ('queues','leaf_status'):
            row['project'][name]={k:v for k,v in (project.get(name) or {}).items() if identifier(k) and type(v) is int}
    admission=native.get('last_admission')
    row['admission']=scalar_projection(admission,('state','jobs_started','process_count','process_target')) if isinstance(admission,dict) else None
    resource=native.get('resource_admission')
    if isinstance(resource,dict):
        row['resource_admission']=scalar_projection(resource,('native_verified','instance_id',
            'stop_active','source_sha_verified','owner_scope_verified','cgroup_memory_ratio',
            'raw_cgroup_memory_ratio','effective_cgroup_memory_ratio','projected_cgroup_memory_ratio',
            'cpu_pressure','admission_class'))
        for key in ('bounded_cpu_budget','bounded_cpu_decision'):
            value=resource.get(key)
            if isinstance(value,dict):row['resource_admission'][key]=scalar_projection(value,tuple(value))
    row['pool_lifecycle']=scalar_projection(native.get('pool_lifecycle') or {},
        ('last_started_at','last_closed_at','last_close_reason'))
    emit('POST_WORKERS',row)


INSTALL_REQUEST = '6964933277'
INSTALL_SOURCE = '32546b26b03019169c22f440af5c9f6ed5b0e09c'
PROJECT_PINS = {
    'project_work_tasks.json':'5347258ca08500d61173d9b36f69cc0632eff36d3ea1e10fcbbc420de69be000',
    'project_work_ideas.json':'e1c84397506c6e46fdc3ce71b63cc5eba2f5cc0cd290f8d1e32d4840e25972ae',
    'project_work_receipts_source.json':'b40c012a7280889722f446083c4cbe878db15fd6da34ac19855a99a0a099af71',
    'project_routing_4q.json':'f98ab106e16116a88947f6be207f73ec2bf9215ae107d415077b79479e91c671',
}

def project_summary():
    docs={}
    for name,pin in PROJECT_PINS.items():
        path=ROOT/'state/dispatcher'/name
        try:
            data,raw,_=obj(path,16*1024*1024)
            docs[name]=data
            rows=data.get('ideas') if name=='project_work_ideas.json' else data.get('tasks')
            emit('PROJECT_FILE',{'path':str(path),'bytes':len(raw),
                'sha256':hashlib.sha256(raw).hexdigest(),'matches_expected_source':hashlib.sha256(raw).hexdigest()==pin,
                'row_count':len(rows) if isinstance(rows,(dict,list)) else None})
        except (OSError,ValueError,TypeError) as exc:
            emit('PROJECT_FILE',{'path':str(path),'state':'UNAVAILABLE','error':type(exc).__name__})
    if len(docs)==4:
        try:
            original=[row['id'] for row in docs['project_work_tasks.json']['tasks']]
            original += [row['id'] for row in docs['project_work_ideas.json']['ideas']]
            route=docs['project_routing_4q.json'];routed=[row['task_id'] for row in route['tasks']]
            queues={}
            for row in route['tasks']:
                q=identifier(row.get('queue_id')) or 'UNKNOWN'
                queues[q]=queues.get(q,0)+1
            emit('PROJECT_COVERAGE',{'original_count':len(original),'original_unique':len(set(original)),
                'routed_count':len(routed),'routed_unique':len(set(routed)),
                'missing_count':len(set(original)-set(routed)), 'extra_count':len(set(routed)-set(original)),
                'queues':queues,'dispatch_cap':route.get('dispatch_cap'),
                'source_scope':'MANIFEST_HANDOFF_ONLY_NOT_ORIGINAL_TASK_ACCEPTANCE'})
        except (ValueError,TypeError,KeyError):
            emit('PROJECT_COVERAGE',{'state':'UNKNOWN_SCHEMA'})

def old_claim_comparison():
    backup=ROOT/'state/dispatcher/four_queue_rollback'/INSTALL_REQUEST
    try:
        current,_,_=obj(ROOT/'state/dispatcher/state.json',16*1024*1024)
        original,_,_=obj(backup/'original_queue_snapshot.json',16*1024*1024)
        final,_,_=obj(backup/'final_stopped_queue_snapshot.json',16*1024*1024)
        cur=current['tasks'];old=original['tasks'];last=final['tasks']
        if any(not isinstance(x,dict) for x in (cur,old,last)):
            raise ValueError('QUEUE_SCHEMA')
        emit('ORIGINAL_QUEUE_PRESERVATION',{'original_before_stop_count':len(old),
            'original_after_stop_count':len(last),'current_count':len(cur),
            'missing_before_stop_count':len(set(old)-set(cur)),
            'missing_after_stop_count':len(set(last)-set(cur)),
            'new_id_count':len(set(cur)-set(last))})
        for role in ('runtime','memory','weights'):
            tid='owner.native.v06.'+role+'.84780aaf911a'
            a,b,c=old.get(tid),last.get(tid),cur.get(tid)
            complete=all(isinstance(x,dict) for x in (a,b,c))
            row={'task_id':tid,'present_in_all_three':complete,
                 'current_full_row_equals_before_stop':complete and c==a,
                 'current_full_row_equals_final_stop':complete and c==b}
            if complete:
                row.update({'before_stop_row_sha256':hashlib.sha256(encoded(a)).hexdigest(),
                    'final_stop_row_sha256':hashlib.sha256(encoded(b)).hexdigest(),
                    'current_row_sha256':hashlib.sha256(encoded(c)).hexdigest(),
                    'status_before':identifier(a.get('status')),'status_current':identifier(c.get('status')),
                    'claim_equal':c.get('owner_claim')==a.get('owner_claim')==b.get('owner_claim'),
                    'claim_epoch_equal':c.get('owner_claim_epoch')==a.get('owner_claim_epoch')==b.get('owner_claim_epoch'),
                    'result_equal':c.get('result')==a.get('result')==b.get('result')})
            emit('OLD_REVIEW_PRESERVATION',row)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        emit('OLD_REVIEW_PRESERVATION',{'state':'UNAVAILABLE','error':type(exc).__name__})
    try:
        receipt,raw,_=obj(ROOT/'state/dispatcher'/('four_queue_install_'+INSTALL_REQUEST+'.json'),2*1024*1024)
        row=scalar_projection(receipt,('schema','state','request','source_sha','original_tasks_accepted','training_started','model_restarted','same_worker_identities','finished_at'))
        row.update({'sha256':hashlib.sha256(raw).hexdigest(),
                    'matches_install_request':str(receipt.get('request'))==INSTALL_REQUEST,
                    'matches_install_source':receipt.get('source_sha')==INSTALL_SOURCE})
        emit('INSTALL_RECEIPT',row)
    except (OSError,ValueError,TypeError) as exc:
        emit('INSTALL_RECEIPT',{'state':'UNAVAILABLE','error':type(exc).__name__})


def project_receipt_source(task,receipt,config,current_source):
    source=receipt.get('source_sha256')
    current_pin=(config.get('module_pins') or {}).get('owner_subagent_dispatcher.py')
    historical=config.get('historical_project_source_sha256') or []
    matched=(task.get('params') or {}).get('source_sha256')==source
    scope=('CURRENT' if current_source==current_pin==source else
           'HISTORICAL_VERIFY_ONLY' if source in historical and matched
                and task.get('status') in ('done','blocked','failed','cancelled') else 'UNREVIEWED_OR_CHANGED')
    return {'source_sha256':source,'current_callback_sha256':current_source,
            'matches_config_callback_pin':current_source==current_pin,
            'matches_durable_task_source':matched,'scope':scope,
            'source_authorized':scope in ('CURRENT','HISTORICAL_VERIFY_ONLY')}


def export_model_postimages(tid,plan,project,exported,remaining):
    import base64
    files=plan.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=32:
        return {'complete':False,'state':'PLAN_FILES_INVALID','files':[]},0
    root_spec=project['roots'][plan['root_id']];root=Path(root_spec['path'])
    results=[];used=0
    for changed in files:
        row={'path':changed.get('path'),'sha256':changed.get('after_sha256')}
        try:
            path=changed['path'];p=Path(path);expected=changed['after_sha256']
            if (not isinstance(path,str) or p.is_absolute() or str(p)!=path
                    or any(x in ('','..','.') or x.startswith('.') for x in p.parts)
                    or path not in root_spec.get('allowed_paths',[])
                    or not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected)):
                row['state']='UNAPPROVED_PATH_OR_HASH'
            else:
                source,_=safe_read(root/path,100000);actual=hashlib.sha256(source).hexdigest()
                row.update(bytes=len(source),actual_sha256=actual)
                if actual!=expected:row['state']='POSTIMAGE_CHANGED'
                elif (path,actual) in exported:row['state']='ALREADY_EXPORTED'
                elif used+len(source)>remaining:row['state']='EXPORT_BYTE_LIMIT'
                elif redact_source(source.decode('utf-8'))!=source.decode('utf-8'):
                    row['state']='REDACTION_REQUIRED'
                else:
                    emit('PROJECT_MODEL_POSTIMAGE',{'task_id':tid,'path':path,'bytes':len(source),
                        'sha256':actual,'before_sha256':changed.get('before_sha256'),
                        'base64':base64.b64encode(source).decode()})
                    used+=len(source);exported.add((path,actual));row['state']='EXPORTED'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            row.update(state='UNAVAILABLE',error=type(exc).__name__)
        results.append(row)
    complete=all(row['state'] in ('EXPORTED','ALREADY_EXPORTED') for row in results)
    return {'complete':complete,'state':'COMPLETE' if complete else 'INCOMPLETE',
            'expected_files':len(files),'exported_bytes':used,'files':results},used


def project_plan_reference(task,receipt,event,evidence):
    """Read the actual reviewed-plan binding; worker reference is model-only."""
    params=task.get('params') or {}
    event_ref=event.get('reference') or {}
    if not isinstance(params,dict) or not isinstance(event_ref,dict):
        raise ValueError('PROJECT_REFERENCE_SHAPE')
    if params.get('plan_sha256'):
        reference={key:params[key] for key in ('plan_sha256','contract_sha256') if key in params}
        if event_ref and event_ref!=reference:
            raise ValueError('PROJECT_REFERENCE_CONFLICT')
    else:
        reference=event_ref
        if reference.get('plan_sha256') and (
                reference.get('contract_sha256')!=params.get('contract_sha256')
                or task.get('native_project_generated_reference')!=reference):
            raise ValueError('PROJECT_GENERATED_REFERENCE_CONFLICT')
    if not reference.get('plan_sha256'):
        if receipt.get('plan_sha256') is not None or evidence.get('plan_sha256') is not None:
            raise ValueError('PROJECT_MISSING_DURABLE_REFERENCE')
        return {}
    if (set(reference)-{'plan_sha256','contract_sha256'}
            or any(not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value)
                   for value in reference.values())
            or receipt.get('plan_sha256')!=reference['plan_sha256']
            or evidence.get('plan_sha256')!=reference['plan_sha256']):
        raise ValueError('PROJECT_REFERENCE_PIN_MISMATCH')
    return reference


def project_plan_binding(plan,raw,reference,task,receipt,evidence,project):
    params=task.get('params') or {}
    expected={'task_id':task.get('id'),'parent_task_id':params.get('parent_task_id'),
              'queue_id':task.get('queue_id'),'root_id':'NOX_PROJECT_SOURCE'}
    return (plan.get('schema')=='NOX_PROJECT_WORK_PLAN_V1'
        and plan.get('operation')=='apply_reviewed_files' and encoded(plan)==raw
        and plan.get('acceptance_scope')=='SOURCE_PATCH_TESTED'
        and plan.get('original_task_accepted') is False
        and expected['parent_task_id']==task.get('parent_task_id')
        and all(isinstance(value,str) and plan.get(key)==value and evidence.get(key)==value
                for key,value in expected.items())
        and all(receipt.get(key)==expected[key] for key in ('task_id','parent_task_id','queue_id'))
        and (plan.get('review_origin')=='OWNER_REVIEWED' and params.get('plan_sha256')==reference['plan_sha256']
             or plan.get('review_origin')=='MODEL_CANDIDATE'
             and plan.get('contract_sha256')==reference.get('contract_sha256')==params.get('contract_sha256'))
        and plan.get('root_id') in project.get('roots',{}))


def project_execution_readback():
    import base64
    config, config_raw, _ = obj(ROOT/'config/owner_native_subagents.json')
    emit('PROJECT_EXECUTOR_CONFIG', {'sha256':hashlib.sha256(config_raw).hexdigest(),
        'mode':config.get('execution_mode'),'worker_cap':config.get('global_worker_cap'),
        'source_pins':config.get('project_executor',{}).get('source_pins'),
        'model_pins':config.get('project_executor',{}).get('model',{}).get('source_pins'),
        'historical_project_source_sha256':config.get('historical_project_source_sha256',[]),
        'historical_leaf_source_sha256':config.get('historical_leaf_source_sha256',[])})
    project=config.get('project_executor') or {}
    if not project:
        return
    current_source=hashlib.sha256(safe_read(SCRIPTS/'owner_subagent_dispatcher.py',500000)[0]).hexdigest()
    for name in ('owner_subagent_dispatcher.py','owner_autonomy_pool.py',
                 'owner_subagent_instruction_truth.py','owner_subagent_processes.py',
                 'owner_project_executor.py','owner_project_test_runner.py','owner_project_native.py',
                 'owner_project_planner.py','owner_project_model_client.py','owner_project_model_bridge.py'):
        try:
            raw,_=safe_read(SCRIPTS/name,500000)
            pin=config.get('module_pins',{}).get(name)
            source_row={'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'configured_sha256':pin,'matches_module_pin':hashlib.sha256(raw).hexdigest()==pin if pin else None}
            if name=='owner_subagent_instruction_truth.py':
                match=re.search(rb"^CALLBACK_SHA = '([a-f0-9]{64})'$",raw,re.M)
                source_row['callback_pin']=match[1].decode() if match else None
                source_row['matches_current_callback']=source_row['callback_pin']==current_source
            emit('PROJECT_RUNTIME_SOURCE',source_row)
        except (OSError,ValueError) as exc:
            emit('PROJECT_RUNTIME_SOURCE',{'name':name,'state':'UNAVAILABLE','error':type(exc).__name__})
    state, state_raw, _ = obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
    rows=state.get('tasks',{})
    counts={}
    for task in rows.values():
        key=task.get('status','UNKNOWN');counts[key]=counts.get(key,0)+1
    emit('PROJECT_QUEUE',{'rows':len(rows),'counts':counts,'sha256':hashlib.sha256(state_raw).hexdigest()})
    exported=set();export_bytes=0;verified_postimages={}
    for tid,task in rows.items():
        if not isinstance(task,dict) or task.get('handler')!='owner_native_project_work':continue
        row={key:task.get(key) for key in ('id','parent_task_id','queue_id','status','note','retries',
                                         'native_queue_sequence','original_task_accepted')}
        row['owner_claim']=task.get('owner_claim')
        result=task.get('result') or {};receipt=result.get('receipt') or {}
        row['result']={key:result.get(key) for key in ('verified','scope','receipt_sha256')}
        if receipt:
            row['receipt']={key:receipt.get(key) for key in ('schema','phase','task_id','parent_task_id',
                'queue_id','job_id','plan_sha256','source_sha256','scope','finished_at',
                'project_source_changed','live_service_deployed','original_task_accepted')}
            row['receipt_sha_matches']=hashlib.sha256(encoded(receipt)).hexdigest()==result.get('receipt_sha256')
            row['receipt_claim_matches']=receipt.get('claim')==task.get('owner_claim')
            row['s03']=s03_receipt_check(receipt)
            row['receipt_source']=project_receipt_source(task,receipt,config,current_source)
            event=receipt.get('worker_result') or {};evidence=event.get('project_evidence') or {}
            row['worker_event']={key:event.get(key) for key in ('kind','role','pid','id','state','elapsed_ms','reason')}
            row['project_evidence']={key:evidence.get(key) for key in ('schema','state','task_id','claim',
                'plan_sha256','root_id','acceptance_scope','worker','project_source_changed',
                'integration_verified','postimages','tests_sha256','reason','trusted_tests_unchanged')}
            if evidence:
                row['project_evidence_sha_matches']=hashlib.sha256(encoded(evidence)).hexdigest()==event.get('project_evidence_sha256')
            tests=evidence.get('tests') or {}
            row['tests']={key:tests.get(key) for key in ('schema','completed','passed','modules','tests_run',
                'failures','errors','skipped','sandbox','log_sha256','log_bytes','elapsed_ms')}
            if tests.get('passed') is not True:
                row['tests']['output_tail']=redact_source(str(tests.get('output',''))[-4000:])
            planner=event.get('planner_receipt') or {}
            row['planner_receipt']=planner
            try:
                reference=project_plan_reference(task,receipt,event,evidence)
            except (ValueError,KeyError,TypeError) as exc:
                reference={};row['plan']={'state':'REFERENCE_UNVERIFIED','error':str(exc)}
            if reference.get('plan_sha256'):
                plan_path=Path(project['package_root'])/'plans'/(reference['plan_sha256']+'.json')
                try:
                    plan,raw,_=obj(plan_path)
                    row['plan']={'sha256':hashlib.sha256(raw).hexdigest(),
                        'matches_reference':hashlib.sha256(raw).hexdigest()==reference['plan_sha256'],
                        'files':plan.get('files'), 'review_origin':plan.get('review_origin'),
                        'contract_sha256':plan.get('contract_sha256'),
                        'binding_verified':project_plan_binding(plan,raw,reference,task,receipt,evidence,project),
                        'reference_source':'DURABLE_TASK_PARAMS' if (task.get('params') or {}).get('plan_sha256')
                                           else 'DURABLE_GENERATED_REFERENCE'}
                    proof_verified=(task.get('status')=='done' and result.get('verified') is True
                        and evidence.get('state')=='INTEGRATED' and evidence.get('integration_verified') is True
                        and tests.get('passed') is True and row['plan']['matches_reference'] and row['plan']['binding_verified']
                        and row['receipt_sha_matches'] and row['receipt_claim_matches']
                        and row['s03'].get('verified') is True and row['receipt_source']['source_authorized']
                        and row['receipt_source']['matches_durable_task_source']
                        and row['receipt_source']['matches_config_callback_pin']
                        and row.get('project_evidence_sha_matches') is True
                        and plan.get('task_id')==tid and plan.get('parent_task_id')==task.get('parent_task_id')
                        and plan.get('root_id')=='NOX_PROJECT_SOURCE')
                    files=plan.get('files')
                    if proof_verified and isinstance(files,list) and 1<=len(files)<=32:
                        postimages={approved_relative(f['path']):f['after_sha256'] for f in files}
                        if (len(postimages)==len(files) and postimages==evidence.get('postimages')
                                and set(postimages)<=set(project['roots']['NOX_PROJECT_SOURCE']['allowed_paths'])
                                and all(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v)
                                        for v in postimages.values())):
                            for path,sha in postimages.items():
                                verified_postimages.setdefault(path,[]).append({'task_id':tid,
                                    'receipt_sha256':result['receipt_sha256'],'sha256':sha})
                    if evidence.get('state')=='INTEGRATED' and plan.get('review_origin')=='MODEL_CANDIDATE':
                        verified=proof_verified
                        if verified:
                            row['model_export'],used=export_model_postimages(tid,plan,project,exported,80000-export_bytes)
                            export_bytes+=used
                        else:row['model_export']={'complete':False,'state':'PROOF_UNVERIFIED'}
                        emit('PROJECT_MODEL_EXPORT_SUMMARY',{'task_id':tid,**row['model_export']})
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    row['plan']={'state':'UNAVAILABLE','error':type(exc).__name__}
        # The full receipt remains canonical in native state and S03. This
        # bounded readback retains verification facts and exact source hashes.
        emit('PROJECT_EXECUTION',row)
    config_rows=config.get('catalog',{}).get('tasks',[])
    emit('PROJECT_CATALOG',{'rows':len(config_rows),'new_project_rows':[
        {key:t.get(key) for key in ('id','queue_id','deps','params','priority','resource')}
        for t in config_rows if t.get('handler')=='owner_native_project_work']})
    return {'config_sha256':hashlib.sha256(config_raw).hexdigest(),
            'queue_sha256':hashlib.sha256(state_raw).hexdigest(),'postimages':verified_postimages}


def project_workspace_census(proofs):
    """Per-file stable reads, without locking writers or claiming an atomic tree."""
    started=time.time()
    report={'scope':'CONFIG_ALLOWED_FILES_ONLY_NOT_DIRECTORY_INVENTORY',
        'atomic_snapshot':False,'source_payloads_exported':False,
        'repository_commit_verified':False,'live_deployment_verified':False,
        'original_task_accepted':False,'started_at':started}
    try:
        config,raw,_=obj(ROOT/'config/owner_native_subagents.json')
        _,root,allowed=project_observation_scope(config)
        config_sha=hashlib.sha256(raw).hexdigest()
        report.update(root=str(root),config_sha256=config_sha,allowed_file_count=len(allowed))
        owner,marker,_=obj(root/'NOX_EXECUTOR_BOOTSTRAP.json',65536)
        pins=owner.get('file_pins')
        if (owner.get('schema')!='NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
                or owner.get('root')!=str(root) or not isinstance(pins,dict)
                or set(pins)!=set(allowed) or owner.get('source_file_count')!=len(allowed)
                or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v)
                       for v in pins.values())):
            raise ValueError('BOOTSTRAP_MANIFEST_SCOPE')
        baseline={'schema':'NOX_PROJECT_SOURCE_BASELINE_V1','files':pins,
                  'source_refs':owner.get('source_refs',[])}
        marker_sha=hashlib.sha256(marker).hexdigest()
        manifest_sha=hashlib.sha256(encoded(baseline)).hexdigest()
        baseline_matches=manifest_sha==owner.get('manifest_sha256')
        report['bootstrap']={'sha256':marker_sha,'manifest_sha256':manifest_sha,
            'recorded_manifest_sha256':owner.get('manifest_sha256'),
            'manifest_digest_matches_marker':baseline_matches,'file_count':len(pins),
            'scope':'RECORDED_INSTALL_BASELINE_NOT_CURRENT_ACCEPTANCE'}
        if not baseline_matches:raise ValueError('BOOTSTRAP_MANIFEST_DIGEST')
        proof_config_matches=isinstance(proofs,dict) and proofs.get('config_sha256')==config_sha
        postimages=proofs.get('postimages',{}) if proof_config_matches else {}
        report['receipt_comparison_config_matches']=proof_config_matches
        report['receipt_queue_snapshot_sha256']=proofs.get('queue_sha256') if isinstance(proofs,dict) else None
        files={};details=[];total=0;errors=[]
        for path in allowed:
            row={'path':path,'bootstrap_sha256':pins[path]}
            try:
                source,info=safe_read(root/path,min(MAX_SOURCE_FILE,MAX_SOURCE_TOTAL-total))
                total+=len(source);sha=hashlib.sha256(source).hexdigest()
                files[path]={'sha256':sha,'size':len(source),'mode':stat.S_IMODE(info.st_mode)}
                references=postimages.get(path,[])[:32]
                row.update(**files[path],matches_bootstrap=sha==pins[path],
                    verified_receipt_postimages=[{**item,'matches_current':item['sha256']==sha}
                                                for item in references])
                matches=any(item['sha256']==sha for item in references)
                row['comparison']=('MATCHES_VERIFIED_RECEIPT_POSTIMAGE' if matches else
                    'MATCHES_BOOTSTRAP_BASELINE' if sha==pins[path] else 'CHANGE_WITHOUT_MATCHING_RECEIPT_IN_SNAPSHOT')
            except (OSError,ValueError) as exc:
                row.update(state='UNAVAILABLE',error=type(exc).__name__);errors.append(path)
            details.append(row)
        # Independent second reads detect observed churn; they do not form a lock
        # and cannot prove that no write occurred between two equal observations.
        changed=[];second_total=0
        for path,first in files.items():
            try:
                source,info=safe_read(root/path,min(MAX_SOURCE_FILE,MAX_SOURCE_TOTAL-second_total))
                second_total+=len(source)
                current={'sha256':hashlib.sha256(source).hexdigest(),'size':len(source),
                         'mode':stat.S_IMODE(info.st_mode)}
                if current!=first:changed.append(path)
            except (OSError,ValueError):changed.append(path)
        config_stable=hashlib.sha256(safe_read(ROOT/'config/owner_native_subagents.json',2000000)[0]).hexdigest()==config_sha
        marker_stable=hashlib.sha256(safe_read(root/'NOX_EXECUTOR_BOOTSTRAP.json',65536)[0]).hexdigest()==marker_sha
        complete=not errors and len(files)==len(allowed)
        report.update(state='CENSUS_OBSERVED',files=files,file_comparisons=details,
            count=len(files),total_bytes=total,files_sha256=hashlib.sha256(encoded(files)).hexdigest(),
            complete_allowed_files_read=complete,read_errors=errors,
            changed_between_reads=changed,two_reads_match=complete and not changed,
            config_unchanged_during_census=config_stable,bootstrap_unchanged_during_census=marker_stable,
            current_cas_recheck_required=True,
            unattributed_changed_paths=[r['path'] for r in details
                if r.get('comparison')=='CHANGE_WITHOUT_MATCHING_RECEIPT_IN_SNAPSHOT'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        report.update(state='CENSUS_UNAVAILABLE',error=type(exc).__name__)
    report['finished_at']=time.time()
    emit('PROJECT_SOURCE_WORKSPACE_CENSUS',report)


def project_install_preservation():
    config,_,_=obj(ROOT/'config/owner_native_subagents.json')
    request=str(config.get('owner_request',''))
    if not re.fullmatch(r'[0-9]{1,24}',request):return
    base=ROOT/'state/dispatcher/complete_executor_rollback'/request
    try:
        before,_,_=obj(base/'final_stopped_queue_snapshot.json',32*1024*1024)
        after,_,_=obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
        old=before['tasks'];new=after['tasks']
        historic={key:row for key,row in old.items() if row.get('status') in ('done','blocked','failed')}
        changed=[key for key,row in historic.items() if any(row.get(field)!=new.get(key,{}).get(field)
                                                         for field in ('owner_claim','result'))]
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'old_count':len(old),'current_count':len(new),
            'missing_original_ids':sorted(set(old)-set(new)),'historical_checked':len(historic),
            'changed_claim_or_result':changed,'verified':not(set(old)-set(new)) and not changed})
        receipt,raw,_=obj(ROOT/'state/dispatcher'/('complete_executor_install_'+request+'.json'),4*1024*1024)
        emit('PROJECT_INSTALL_RECEIPT',{'sha256':hashlib.sha256(raw).hexdigest(),
            **{key:receipt.get(key) for key in ('schema','state','request','source_sha','started_at',
                'finished_at','previous_director','new_director','original_tasks_accepted',
                'protected_processes','training_started','model_restarted','preflight',
                'sandbox_preflight','native_sandbox_preflight','source_bootstrap')}})
    except (OSError,ValueError,KeyError) as exc:
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'state':'UNAVAILABLE','error':type(exc).__name__})


def director_child_census():
    data,_,_=obj(ROOT/'status/agents_t856u.json')
    native=data.get('native_subexecutors') or {};pid=(native.get('director') or {}).get('pid')
    result=[]
    if type(pid) is int:
        for child in Path('/proc').iterdir():
            if not child.name.isdigit():continue
            observed=process(int(child.name))
            if observed.get('ppid')!=pid:continue
            try:
                raw=(child/'cmdline').read_bytes()[:4000]
                kind='MP_WORKER' if b'multiprocessing.spawn' in raw else (
                    'MP_RESOURCE_TRACKER' if b'resource_tracker' in raw else 'OTHER_CHILD')
            except OSError:kind='UNKNOWN'
            result.append({**observed,'kind':kind})
    emit('PROJECT_DIRECTOR_CHILDREN',{'director_pid':pid,'children':result,
        'native_fields':sorted(native),'last_admission':native.get('last_admission'),
        'close_reason':native.get('close_reason'),'state':native.get('state')})


def project_active_progress():
    import urllib.request
    try:
        req=urllib.request.Request('http://127.0.0.1:8098/slots',method='GET')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=5) as response:
            raw=response.read(200001)
        if len(raw)>200000:raise ValueError('SLOT_SIZE')
        slots=json.loads(raw)
        if not isinstance(slots,list):raise ValueError('SLOT_SHAPE')
        rows=[]
        keys=('id','id_task','is_processing','n_ctx','n_prompt_tokens','n_decoded','n_predict','n_past','state')
        for slot in slots[:4]:
            row=scalar_projection(slot,keys)
            for field in ('timings','next_token','params'):
                if isinstance(slot.get(field),dict):
                    row[field]=scalar_projection(slot[field],(
                        'n_predict','n_ctx','n_decoded','n_remaining','has_next_token',
                        'prompt_n','prompt_ms','predicted_n','predicted_ms',
                        'predicted_per_token_ms','predicted_per_second'))
            rows.append(row)
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'slots':rows,'scope':'READ_ONLY_NO_PROMPT_OR_COMPLETION_CONTENT'})
    except (OSError,ValueError,TypeError) as exc:
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'state':'UNAVAILABLE','error':type(exc).__name__})
    base=ROOT/'state/dispatcher/project_executor/run/attempts'
    rows=[]
    if base.exists() and not base.is_symlink():
        for path in sorted(base.glob('*/*/*/journal.json'))[-40:]:
            try:
                value,raw,info=obj(path,2000000)
                row=scalar_projection(value,('schema','state','task_id','claim','plan_sha256','reason','started_at','finished_at'))
                row.update({'journal_sha256':hashlib.sha256(raw).hexdigest(),'mtime_ns':info.st_mtime_ns})
                tests=value.get('tests')
                if isinstance(tests,dict):
                    row['tests']=scalar_projection(tests,('schema','completed','passed','tests_run',
                        'failures','errors','skipped','log_sha256','log_bytes','elapsed_ms'))
                    row['tests']['report_sha256']=hashlib.sha256(encoded(tests)).hexdigest()
                    row['tests']['matches_journal_test_pin']=row['tests']['report_sha256']==value.get('tests_sha256')
                rows.append(row)
            except (OSError,ValueError):continue
    try:planner_sha=hashlib.sha256(safe_read(SCRIPTS/'owner_project_planner.py',500000)[0]).hexdigest()
    except (OSError,ValueError):planner_sha=None
    emit('PROJECT_ATTEMPT_PROGRESS',{'attempts':rows,'planner_sha256':planner_sha,
        'interim_trace_unavailable':True,
        'trace_storage':'MEMORY_ONLY_UNTIL_FINAL_RECEIPT' if planner_sha==PLANNER_MEMORY_TRACE_SHA else 'UNREVIEWED_PLANNER_VERSION',
        'scope':'DURABLE_TEST_ATTEMPTS_ONLY_NOT_IN_MEMORY_EDIT_OR_TURN_PROGRESS',
        'absence_of_attempt_does_not_prove_no_source_edits':True})


def main():
    emit('SNAPSHOT_A',runtime_snapshot())
    worker_status_sample()
    director_child_census()
    project_summary()
    project_install_preservation()
    proofs=project_execution_readback()
    project_workspace_census(proofs)
    project_active_progress()
    emit('LOCKS',locks())
    time.sleep(6)
    worker_status_sample()
    director_child_census()
    emit('SNAPSHOT_B',runtime_snapshot())
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
