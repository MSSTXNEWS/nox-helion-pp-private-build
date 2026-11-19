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

def main():
    readonly_action = os.environ.get('NOX_READONLY_ACTION', '')
    if readonly_action and readonly_action != 'supervisor-config':
        raise SystemExit('HOLD_UNKNOWN_READONLY_ACTION')
    if readonly_action == 'supervisor-config':
        row = supervisor_config_readonly()
        print('NOX_MAINT_SUPERVISOR_CONFIG=' + json.dumps(
            row, ensure_ascii=True, separators=(',', ':'), allow_nan=False), flush=True)
        print('NOX_MAINT_SUPERVISOR_CONFIG_COMPLETE=true', flush=True)
        return
    emit('SNAPSHOT_A',runtime_snapshot())
    worker_status_sample()
    hash_summary()
    project_summary()
    old_claim_comparison()
    configuration()
    leaf_queue_summary()
    emit('LOCKS',locks())
    time.sleep(6)
    worker_status_sample()
    leaf_queue_summary()
    emit('SNAPSHOT_B',runtime_snapshot())
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)


# Compatibility API for unchanged read-only safety and inventory suites.
# The queue/pool inspector above and its default main remain unchanged.
_COMPAT_PUBLIC_SCHEMAS = frozenset((
    'NOX_SAFE', 'S03_STATUS_V1', 'NOX_QWEN_PROGRESS_V1',
    'NOX_QWEN35_9B_SINGLE_TRAINER_V1', 'NOX_QWEN35_9B_CHECKPOINT_V1',
    'NOX_QWEN_STUDENT_PROOF_V1', 'NOX_NATIVE_SUBAGENT_RECEIPT_V1',
    'NOX_OWNER_SAFETY_READONLY_V1', 'NOX_OWNER_MAINTENANCE_V1',
))

_COMPAT_PUBLIC_CODES = frozenset((
    'PASS', 'FAIL', 'FAILED', 'HOLD', 'HOLD_SAFE', 'HOLD_BACKUP', 'HOLD_TRAINING',
    'PENDING', 'RUNNING', 'STOPPED', 'DONE', 'BLOCKED', 'READY', 'LOADING',
    'TRAINING', 'EVALUATING', 'CHECKPOINTING', 'COMPLETED', 'SKIPPED',
    'OBSERVED', 'NOT_OBSERVED', 'UNVERIFIED', 'PREFLIGHT', 'INTEGRATED',
    'PREPARED', 'BLOCKED_PLANNER', 'BLOCKED_SANDBOX', 'FAILED_TESTS',
    'NATIVE_STUDENT_UPDATE_OBSERVED', 'NATIVE_EXECUTION_EVALUATION_CHECKPOINTED',
    'STUDENT_RESTART_AND_UPDATES_VERIFIED', 'EXISTING_TRAINER_HOLD_OR_PAUSE',
    'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED',
    'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
    'pending', 'wait', 'retry', 'running', 'done', 'blocked', 'failed', 'cancelled',
    'event', 'verified_birth', 'checkpoint',
))

def _compat_public_code(key, value):
    # Lexically plausible strings can still be credentials or private prose.
    allowed = _COMPAT_PUBLIC_SCHEMAS if key == 'schema' else _COMPAT_PUBLIC_CODES
    return type(value) is str and value in allowed

def _compat_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_METADATA_KEY')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('NONFINITE_METADATA_NUMBER')
    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('NONFINITE_METADATA_NUMBER')
        return result
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject, parse_float=finite)

def _compat_safetensors_header(path, limit):
    """Read only a bounded header through pinned nonblocking directory FDs."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('HOLD_SHARD_UNSAFE')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('HOLD_SHARD_UNSAFE')
            def exact(count):
                chunks, remaining = [], count
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        raise ValueError('HOLD_SAFETENSORS_HEADER_SIZE')
                    chunks.append(chunk); remaining -= len(chunk)
                return b''.join(chunks)
            n = int.from_bytes(exact(8), 'little')
            if not 2 <= n <= limit or before.st_size < 8 + n:
                raise ValueError('HOLD_SAFETENSORS_HEADER_SIZE')
            raw = exact(n)
            after = os.fstat(fd)
            if any(getattr(before, key) != getattr(after, key) for key in
                   ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
                raise ValueError('HOLD_SHARD_CHANGED')
            return _compat_json(raw), n, before.st_size
        finally:
            os.close(fd)
    finally:
        os.close(parent)

def _compat_file_metadata(path, limit):
    try:
        raw, _ = safe_read(path, limit)
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'scope': 'BOUNDED_FILE_METADATA_ONLY'}
    except (OSError, ValueError):
        return {'path': str(path), 'state': 'HOLD_FILE_NOT_READ'}

import configparser, math, shlex, shutil, urllib.request

PROC = Path('/proc')

SECRET = re.compile(r'(?i)(?:Bearer\s+\S+|(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}|(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*[\"\'][^\"\']{12,})')

SENSITIVE_NAME = r'(?:password|secret|api[_-]?key|access[_-]?key|authorization|(?:hf|github|gh|api|auth|access|refresh|bearer|nox)[_-]?token|token|NOX2)'

SENSITIVE_ASSIGNMENT = re.compile(r'(?i)\b'+SENSITIVE_NAME+r'[\"\']?\s*[:=]\s*(?:[\"\'][^\"\'\n]*[\"\']|[^\s,;\n]+)')

SERVICES = ('nox-train-volta-t866u', 'nox-teacher-serve-t811u',
            'nox-train-worm-t811u', 'nox-autoscale-t877u', 'nox-dispatcher-t855u',
            'nox-gpu-watchdog-t865u', 'nox-vram-guard-t829u', 'nox-priority-scheduler',
            'nox-selfheal', 'nox-distill-worm-t811u', 'nox-self-improve-t846u',
            'nox-self-learning-loop', 'nox-agent-tuner-t858u', 'nox-agent-architect-t859u',
            'nox-agent-integrator-t859u', 'nox-chat-8081', 'nox-proxy', 'nox-downloads-t802u',
            'nox-checklist-worker', 'nox-dialog-miner', 'nox-offload-t850u', 'nox-watch-swap-t845u')

def redact(value):
    value=re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]', value)
    value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    value=re.sub(r'(?i)--'+SENSITIVE_NAME+r'(?:=|\s+)(?:[\"\'][^\"\'\n]*[\"\']|[^\s,;\n]+)', '[REDACTED_ARGUMENT]',value)
    return SENSITIVE_ASSIGNMENT.sub('[REDACTED_ASSIGNMENT]', SECRET.sub('[REDACTED]',value))

def gpu_apps(output):
    rows=[]
    for line in output.splitlines()[:80]:
        cols=[x.strip() for x in line.split(',')]
        if len(cols)!=3 or not cols[0].isdigit() or not re.fullmatch(r'GPU-[A-Fa-f0-9-]+',cols[1]):continue
        rows.append({'reported_pid':int(cols[0]),'gpu_uuid':cols[1],
                     'used_mib':int(cols[2]) if cols[2].isdigit() else None})
    return rows

def map_gpu_processes(rows, apps):
    """A namespace PID match is evidence only when it identifies one local PID."""
    aliases={}
    for row in rows:
        for pid in {row['pid'], *row.get('namespace_pids',[])}:
            aliases.setdefault(pid,set()).add(row['pid'])
    by_pid={row['pid']:row for row in rows}; unresolved=[]
    for app in apps:
        candidates=aliases.get(app['reported_pid'],set())
        if len(candidates)!=1:
            unresolved.append({**app,'mapping':'UNMAPPED' if not candidates else 'AMBIGUOUS',
                               'candidate_local_pids':sorted(candidates)})
            continue
        pid=next(iter(candidates))
        by_pid[pid].setdefault('gpu_compute_apps',[]).append({**app,
            'mapping':'LOCAL_PID' if app['reported_pid']==pid else 'NSPID'})
    return unresolved

def run(args, timeout=12):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout[:100000]
    except Exception as e:
        return 99, type(e).__name__

def storage_mount_metadata(mountinfo=None, statvfs=None):
    """Bounded, read-only mount inventory; not a seek/write/owner-lease proof."""
    if statvfs is None:
        statvfs = os.statvfs
    if mountinfo is None:
        try:
            mountinfo = Path('/proc/self/mountinfo').read_text(encoding='utf-8')[:500000]
        except OSError:
            return {'status':'UNKNOWN_MOUNTINFO','scope':'ALLOWLISTED_ONLY','mounts':[]}
    roots = ('/', '/data', '/workspace', '/mnt', '/models', '/root/nox')
    candidates = []
    for line in mountinfo.splitlines()[:1024]:
        if ' - ' not in line:
            continue
        left, right = line.split(' - ', 1)
        fields, suffix = left.split(), right.split()
        if len(fields) < 5 or not suffix:
            continue
        mount = re.sub(r'\\([0-7]{3})', lambda m:chr(int(m.group(1),8)), fields[4])
        if mount not in roots and not any(mount.startswith(root + '/') for root in roots[1:]):
            continue
        fstype = suffix[0]
        if fstype in ('proc','sysfs','tmpfs','devtmpfs','devpts','cgroup','cgroup2','mqueue','securityfs'):
            continue
        try:
            v = statvfs(mount)
            if v.f_blocks <= 0:
                continue
            candidates.append({'path':mount,'filesystem':fstype,'total_bytes':v.f_blocks*v.f_frsize,
                               'free_bytes':v.f_bavail*v.f_frsize})
        except (OSError, ValueError):
            candidates.append({'path':mount,'filesystem':fstype,'status':'UNKNOWN_STATVFS'})
        if len(candidates) >= 24:
            break
    return {'status':'READ_ONLY_MOUNT_METADATA','scope':'ALLOWLISTED_ONLY_NOT_EXHAUSTIVE',
            'seekability':'NOT_TESTED','write_access':'NOT_TESTED','mounts':candidates}

def processes():
    rows, snapshots = [], []
    # Pin identities before the GPU/Supervisor query and before argv reads.
    for index, path in enumerate(PROC.iterdir()):
        if index >= 4096:
            break
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
            fields = raw.rsplit(') ', 1)[1].split()
            if raw.split(' (', 1)[0] == path.name and fields[19].isdigit():
                snapshots.append((path, fields))
        except (OSError, ValueError, IndexError):
            pass
    gpu_rc, gpu_out = run(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory', '--format=csv,noheader,nounits'])
    apps = gpu_apps(gpu_out) if gpu_rc == 0 else []
    supervisor_rc, supervisor_out = run(['supervisorctl', 'status'])
    owners = {int(match[2]): match[1] for line in supervisor_out.splitlines()
              if supervisor_rc == 0 and (match := re.match(r'^([A-Za-z0-9_.:-]+)\s+RUNNING\s+pid\s+(\d+)', line))}
    for path, fields in snapshots:
        try:
            argv = (path / 'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not argv[0]:
                continue
            env = dict(item.split('=', 1) for item in (path / 'environ').read_bytes().decode(errors='replace').split('\0') if '=' in item)
            status = (path / 'status').read_text()
            post_raw = (path / 'stat').read_text()
            post = post_raw.rsplit(') ', 1)[1].split()
            if post_raw.split(' (', 1)[0] != path.name or post[19] != fields[19]:
                continue
            row = {'pid': int(path.name), 'ppid': int(fields[1]), 'state': fields[0], 'starttime': fields[19],
                   'exe': os.path.basename(argv[0]), 'cuda': redact(env.get('CUDA_VISIBLE_DEVICES', ''))[:150],
                   'proc_name': redact(env.get('PROC_NAME', ''))[:150],
                   '_relevant': any(name in ' '.join(argv[:3]) for name in ('nox', 'llama', 'train', 'supervisor'))}
            row['scripts'] = [redact(value) for value in argv[1:4] if value.endswith(('.py', '.sh')) and len(value) < 250 and '\n' not in value]
            row['args'] = {key: redact(argv[index+1]) for index, key in enumerate(argv[:-1]) if key in ('-m', '--model', '--port', '-t', '-np', '--max-steps', '--n-gpu-layers', '-ngl') and len(argv[index+1]) < 250}
            for key in ('NSpid', 'VmRSS', 'Threads'):
                match = re.search(r'^' + key + r':\s*(.+)$', status, re.M)
                if match:
                    row[key] = match[1]
            row['namespace_pids'] = [int(value) for value in row.get('NSpid', '').split() if value.isdigit()]
            rows.append(row)
        except (OSError, ValueError, IndexError):
            pass
    unresolved = map_gpu_processes(rows, apps)
    by_pid = {row['pid']: row for row in rows}
    for row in rows:
        chain, pid, seen = [], row['pid'], set()
        for _ in range(12):
            if pid in seen or pid < 2:
                break
            seen.add(pid)
            if pid in owners:
                row['supervisor_owner'], row['supervisor_pid'] = owners[pid], pid
                break
            parent = by_pid.get(pid)
            if not parent:
                break
            pid = parent['ppid']; chain.append(pid)
        row['ancestor_pids'] = chain
    selected = [row for row in rows if row.pop('_relevant') or row.get('gpu_compute_apps')]
    selected.sort(key=lambda row: (not bool(row.get('gpu_compute_apps')), row['pid']))
    return selected[:120] + [{'record': 'gpu_pid_mapping', 'gpu_query_rc': gpu_rc, 'unresolved': unresolved,
        'process_rows_truncated': len(selected) > 120 or len(snapshots) >= 4096,
        'note': 'Namespace ambiguity is unresolved; CUDA_VISIBLE_DEVICES alone is not GPU ownership.'}]

def hf_metadata_probe(base):
    """Bounded read-only HF metadata: never treats tensor headers as weight payload SHA."""
    out = {'record':'trainable_hf_lineage_metadata','scope':'READ_ONLY',
           'weight_payload_sha256_verified':False,'immutable_hf_revision_verified':False,
           'adapter_merge_authorized':False}
    base = Path(base)
    MAX_JSON=16*1024*1024
    # The index and tensor headers do not prove a SHA256 of the weight payload.
    DTYPE_BYTES = {
        'BOOL': 1, 'U8': 1, 'I8': 1, 'F8_E4M3': 1, 'F8_E5M2': 1, 'F8_E8M0': 1,
        'U16': 2, 'I16': 2, 'F16': 2, 'BF16': 2,
        'U32': 4, 'I32': 4, 'F32': 4, 'U64': 8, 'I64': 8, 'F64': 8,
    }
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('DUPLICATE_JSON_KEY')
            obj[key]=value
        return obj
    try:
        files={}
        for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json',
                     'added_tokens.json','chat_template.jinja','generation_config.json'):
            p=base/name
            if not p.exists():continue
            if p.is_symlink() or not p.is_file() or p.stat().st_size>32*1024*1024:
                raise ValueError('HOLD_TOKENIZER_FILE_UNSAFE')
            raw, metadata = safe_read(p, 32*1024*1024)
            files[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':metadata.st_size}
        out['tokenizer_file_digests']=files
        if 'tokenizer.json' not in files or 'tokenizer_config.json' not in files:
            raise ValueError('HOLD_TOKENIZER_REQUIRED_FILES')
        idx=base/'model.safetensors.index.json'
        if idx.is_symlink() or not idx.is_file() or idx.stat().st_size>MAX_JSON:
            raise ValueError('HOLD_SHARD_INDEX_MISSING_OR_UNSAFE')
        idxbytes, _ = safe_read(idx, MAX_JSON)
        index = _compat_json(idxbytes)
        if not isinstance(index, dict):
            raise ValueError('HOLD_SHARD_INDEX_MAP')
        mapping=index.get('weight_map')
        if not isinstance(mapping,dict) or not mapping or len(mapping)>100000:
            raise ValueError('HOLD_SHARD_INDEX_MAP')
        if any(not isinstance(k,str) or not k or not isinstance(v,str) or
               not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.safetensors',v)
               for k,v in mapping.items()):
            raise ValueError('HOLD_SHARD_NAME_UNSAFE')
        names=set(mapping.values())
        actual={p.name for p in base.glob('*.safetensors')}
        if actual!=names or len(names)>50:
            raise ValueError('HOLD_SHARD_INDEX_FILESET_MISMATCH')
        tensors=[]; total_bytes=0
        for name in sorted(names):
            p=base/name
            if p.is_symlink() or not p.is_file():raise ValueError('HOLD_SHARD_UNSAFE')
            header, n, nbytes = _compat_safetensors_header(p, MAX_JSON)
            total_bytes += nbytes
            if not isinstance(header,dict) or len(header)>100000:
                raise ValueError('HOLD_SAFETENSORS_HEADER_OBJECT')
            payload_bytes=nbytes-8-n
            ranges=[]
            entries=[(k,v) for k,v in header.items() if k!='__metadata__']
            from_index={k for k,v in mapping.items() if v==name}
            if {k for k,_ in entries}!=from_index:
                raise ValueError('HOLD_TENSOR_INDEX_HEADER_MISMATCH')
            for key,desc in entries:
                if not isinstance(desc,dict):raise ValueError('HOLD_TENSOR_DESCRIPTOR')
                shape=desc.get('shape'); dtype=desc.get('dtype');offsets=desc.get('data_offsets')
                if (not isinstance(shape,list) or len(shape)>16 or
                    any(type(v)!=int or v<0 for v in shape) or
                    not isinstance(dtype,str) or not re.fullmatch(r'[A-Z0-9_]{2,16}',dtype) or
                    not isinstance(offsets,list) or len(offsets)!=2 or
                    any(type(v)!=int or v<0 for v in offsets) or
                    offsets[0]>offsets[1] or offsets[1]>nbytes-8-n):
                    raise ValueError('HOLD_TENSOR_HEADER_INVALID')
                width=DTYPE_BYTES.get(dtype)
                if width is None:
                    raise ValueError('HOLD_TENSOR_DTYPE_UNSUPPORTED')
                if offsets[1]-offsets[0] != math.prod(shape)*width:
                    raise ValueError('HOLD_TENSOR_BYTE_SIZE')
                ranges.append((offsets[0],offsets[1]))
                tensors.append((key,name,dtype,shape))
            cursor=0
            for first,last in sorted(ranges):
                if first!=cursor:
                    raise ValueError('HOLD_TENSOR_LAYOUT')
                cursor=last
            if cursor!=payload_bytes:
                raise ValueError('HOLD_TENSOR_LAYOUT')
        out['shard_index_sha256']=hashlib.sha256(idxbytes).hexdigest()
        out['tensor_metadata_sha256']=hashlib.sha256(json.dumps(
            sorted(tensors),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        out['tensor_count']=len(tensors);out['shards_count']=len(names)
        out['shards_total_bytes']=total_bytes
        out['status']='HEADER_INDEX_MATCH_ONLY_CONTENT_SHA_PENDING'
    except (OSError,UnicodeError,ValueError,TypeError,OverflowError) as e:
        code=str(e)
        out['status']=code if code.startswith('HOLD_') else 'HOLD_METADATA_'+type(e).__name__.upper()
    return out

def qwen_training_readback():
    base = ROOT / 'lora/qwen35_9b'
    if any(path.is_symlink() or not path.is_dir() for path in (ROOT, ROOT / 'lora', base)):
        return [{'record': 'qwen35_student', 'state': 'RUN_DIRECTORY_NOT_OBSERVED'}]
    runs = []
    for index, path in enumerate(base.iterdir()):
        if index >= 1024:
            return [{'record': 'qwen35_student', 'state': 'RUN_DIRECTORY_BOUND'}]
        if re.fullmatch(r'[0-9][0-9A-Za-z_-]{0,63}', path.name) and path.is_dir() and not path.is_symlink():
            runs.append(path)
    rows = []
    for directory in sorted(runs)[-3:]:
        for name in ('owner_progress.json', 'owner_last_result.json', 'owner_acceptance.json'):
            path = directory / name
            row = {'record': 'qwen35_student', 'run': directory.name, 'receipt': name}
            if path.is_symlink() or not path.is_file():
                row['state'] = 'NOT_OBSERVED'; rows.append(row); continue
            try:
                if path.stat().st_size > 200000:
                    row['state'] = 'SIZE_HOLD'; rows.append(row); continue
                raw, info = safe_read(path, 200000)
                data = _compat_json(raw)
                if not isinstance(data, dict):
                    row['state'] = 'UNEXPECTED_FORMAT'; rows.append(row); continue
                row.update(bytes=len(raw), mtime=info.st_mtime, sha256=hashlib.sha256(raw).hexdigest(),
                           state='METADATA_READ_ONLY', scope='SELF_REPORTED_NOT_LIVE_PROOF',
                           fields=safe_qwen_receipt_fields(data))
            except (OSError, ValueError, TypeError):
                row['state'] = 'READ_OR_PARSE_HOLD'
            rows.append(row)
    return rows or [{'record': 'qwen35_student', 'state': 'NO_RUN_RECEIPTS_OBSERVED'}]

SUPERVISOR_CONFIG_PATH = Path('/etc/supervisor/conf.d/nox-dispatcher-t855u.conf')
SUPERVISOR_CONFIG_DIR = Path('/etc/supervisor/conf.d')
SUPERVISOR_TARGET_SERVICE = 'nox-dispatcher-t855u'
SUPERVISOR_EXPECTED_SCRIPT = '/root/nox/scripts/nox_dispatcher_t855u.py'


def supervisor_config_readonly(config_path=SUPERVISOR_CONFIG_PATH,
                               conf_dir=SUPERVISOR_CONFIG_DIR, now=time.time):
    """Read one known dispatcher config and fail closed on ambiguity.

    Only a canonical interpreter + dispatcher script command is emitted. Other
    command text is replaced with a marker; its digest and token count remain.
    """
    config_path = Path(config_path)
    conf_dir = Path(conf_dir)
    if (config_path.name != 'nox-dispatcher-t855u.conf'
            or config_path.parent != conf_dir or not conf_dir.is_dir()
            or conf_dir.is_symlink()):
        raise ValueError('HOLD_SUPERVISOR_CONFIG_PATH')
    names = sorted(path for path in conf_dir.iterdir() if path.name.endswith('.conf'))
    if len(names) > 128 or config_path not in names:
        raise ValueError('HOLD_SUPERVISOR_CONFIG_MISSING_OR_UNBOUNDED')
    sections = []
    selected = None
    for path in names:
        raw, _ = safe_read(path, 250000)
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(raw.decode('utf-8'))
        section = 'program:' + SUPERVISOR_TARGET_SERVICE
        if parser.has_section(section):
            sections.append(path)
            if path == config_path:
                selected = (raw, parser)
    if len(sections) != 1 or sections[0] != config_path or selected is None:
        raise ValueError('HOLD_SUPERVISOR_CONFIG_DUPLICATE_OR_WRONG_PATH')
    raw, parser = selected
    section = 'program:' + SUPERVISOR_TARGET_SERVICE
    command_raw = parser.get(section, 'command', fallback='').strip()
    if not command_raw or len(command_raw) > 4096:
        raise ValueError('HOLD_SUPERVISOR_COMMAND_MISSING_OR_OVERSIZED')
    try:
        tokens = shlex.split(command_raw, posix=True)
    except ValueError as exc:
        raise ValueError('HOLD_SUPERVISOR_COMMAND_PARSE') from exc
    if not tokens or len(tokens) > 64:
        raise ValueError('HOLD_SUPERVISOR_COMMAND_SCHEMA')
    executable = Path(tokens[0]).name
    interpreter_ok = (Path(tokens[0]).is_absolute()
                      and re.fullmatch(r'python(?:3(?:\.[0-9]{1,2})?)?', executable) is not None)
    command_matches = interpreter_ok and len(tokens) >= 2 and tokens[1] == SUPERVISOR_EXPECTED_SCRIPT
    command_public = (' '.join(tokens[:2]) if command_matches
                      else '[REDACTED_UNRECOGNIZED_COMMAND]')
    restart = parser.get(section, 'autorestart', fallback='unexpected').strip().lower()
    if restart not in ('true', 'false', 'unexpected'):
        raise ValueError('HOLD_SUPERVISOR_AUTORESTART')
    stop_signal = parser.get(section, 'stopsignal', fallback='TERM').strip().upper()
    if not re.fullmatch(r'(?:TERM|INT|QUIT|HUP|USR1|USR2|KILL|[0-9]{1,3})', stop_signal):
        stop_signal = 'UNRECOGNIZED'
    try:
        stop_as_group = parser.getboolean(section, 'stopasgroup', fallback=False)
        kill_as_group = parser.getboolean(section, 'killasgroup', fallback=False)
    except ValueError as exc:
        raise ValueError('HOLD_SUPERVISOR_GROUP_FLAGS') from exc
    return {
        'schema': 'NOX_SUPERVISOR_CONFIG_READONLY_V1',
        'state': 'VERIFIED',
        'observed_at': float(now()),
        'path': str(config_path),
        'service': SUPERVISOR_TARGET_SERVICE,
        'config_sha256': hashlib.sha256(raw).hexdigest(),
        'command': command_public,
        'command_sha256': hashlib.sha256(command_raw.encode('utf-8')).hexdigest(),
        'command_matches_expected': bool(command_matches),
        'command_token_count': len(tokens),
        'command_extra_args_redacted': max(0, len(tokens) - 2),
        'stopsignal': stop_signal,
        'stopasgroup': bool(stop_as_group),
        'killasgroup': bool(kill_as_group),
        'autorestart': restart,
        'duplicates_found': 0,
        'scope': 'ONE_FIXED_SERVICE_CONFIG_COMMAND_REDACTED_UNLESS_CANONICAL',
    }


def supervisor_config():
    """Return recognized service settings; command, environment and text withheld."""
    directory = Path('/etc/supervisor/conf.d')
    names = {'nox.conf', 'nox-runtime.conf'}
    for service in SERVICES:
        names.update((service + '.conf', service.replace('-', '_') + '.conf'))
    rows = []
    for name in sorted(names):
        path = directory / name
        try:
            raw, _ = safe_read(path, 250000)
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.read_string(raw.decode())
            for service in SERVICES:
                section = 'program:' + service
                if not parser.has_section(section):
                    continue
                fields = {}
                for key in ('autostart','stopasgroup','killasgroup'):
                    value = parser.get(section, key, fallback='').lower()
                    if value in ('true','false'):
                        fields[key] = value == 'true'
                restart = parser.get(section, 'autorestart', fallback='').lower()
                if restart in ('true','false','unexpected'):
                    fields['autorestart'] = restart
                for key in ('startsecs','startretries','stopwaitsecs','priority'):
                    value = parser.get(section, key, fallback='')
                    if re.fullmatch(r'[0-9]{1,6}', value):
                        fields[key] = int(value)
                rows.append({'path': str(path), 'service': service, 'settings': fields,
                             'scope': 'OPERATIONAL_SCALARS_ONLY_COMMAND_ENV_WITHHELD'})
        except (OSError, ValueError, UnicodeError, configparser.Error):
            continue
    return rows

SFTCONFIG_REQUIRED = (
    'output_dir', 'per_device_train_batch_size', 'gradient_accumulation_steps',
    'max_length', 'max_steps', 'fp16', 'bf16', 'packing',
    'gradient_checkpointing', 'gradient_checkpointing_kwargs',
    'dataloader_num_workers', 'logging_steps', 'save_steps',
    'save_total_limit', 'warmup_steps', 'learning_rate', 'optim',
    'lr_scheduler_type', 'report_to',
)

def parse_sftconfig_signature_probe(rc, output):
    """Fail closed on the installed TRL signature; never report training."""
    result = {'record': 'pinned_trl_sftconfig_signature',
              'scope': 'READ_ONLY_SIGNATURE_NO_TRAINER',
              'constructor_executed': False, 'optimizer_updates': 0}
    if rc != 0:
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_IMPORT')
    matches = [line[len('NOX_SFTCONFIG_SIGNATURE='):]
               for line in output.splitlines()
               if line.startswith('NOX_SFTCONFIG_SIGNATURE=')]
    if len(matches) != 1 or len(matches[0]) > 4096:
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_OUTPUT')
    try:
        # GitHub/owner-native receipts are evidence, not trusted constructor
        # capabilities. Duplicate keys can silently replace a safe capability
        # with its opposite in Python's permissive json.loads().
        def reject_duplicate_fields(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError('SFTCONFIG_DUPLICATE_SIGNATURE_FIELD')
                out[key] = value
            return out
        def reject_nonfinite(_value):
            raise ValueError('SFTCONFIG_NONFINITE_SIGNATURE_FIELD')
        data = json.loads(matches[0], object_pairs_hook=reject_duplicate_fields,
                          parse_constant=reject_nonfinite)
        if (not isinstance(data, dict) or
                set(data) != {'schema', 'trl_version', 'missing_required_kwargs',
                              'save_safetensors_parameter'} or
                data.get('schema') != 'NOX_SFTCONFIG_NATIVE_SIGNATURE_V1' or
                type(data.get('trl_version')) is not str or
                not re.fullmatch(r'[0-9A-Za-z.+_-]{1,64}', data['trl_version']) or
                type(data.get('save_safetensors_parameter')) is not bool or
                not isinstance(data.get('missing_required_kwargs'), list) or
                len(set(map(str, data['missing_required_kwargs']))) != len(data['missing_required_kwargs']) or
                any(type(k) is not str or k not in SFTCONFIG_REQUIRED
                    for k in data['missing_required_kwargs'])):
            raise ValueError('INVALID_SIGNATURE_RECORD')
    except (ValueError, TypeError, UnicodeError):
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_SCHEMA')
    result.update(trl_version=data['trl_version'],
                  save_safetensors_parameter=data['save_safetensors_parameter'],
                  missing_required_kwargs=data['missing_required_kwargs'])
    if data['missing_required_kwargs']:
        result['status'] = 'HOLD_REQUIRED_SFTCONFIG_KWARGS_UNSUPPORTED'
    elif data['save_safetensors_parameter']:
        result['status'] = 'SIGNATURE_ACCEPTS_LEGACY_SAVE_SAFETENSORS'
    else:
        result['status'] = 'LEGACY_TRUE_REQUIRES_SAFE_OMISSION'
    return result

def pinned_python_path_status(py, venv_root=Path('/root/venv_volta'),
                              trusted_uid=0,
                              system_dirs=(Path('/usr/bin'), Path('/usr/local/bin'))):
    """Validate a pinned venv Python, including normal root-owned venv symlinks.

    Only the known venv path and root-controlled executable targets are allowed.
    Do not run a path that escaped into a writable directory. This is a
    read-only metadata gate, not a writer lease or a CUDA/ABI acceptance.
    """
    if py != venv_root / 'bin' / 'python':
        return 'HOLD_PINNED_NATIVE_PYTHON_PATH'
    try:
        for directory in (venv_root, venv_root / 'bin'):
            metadata = directory.lstat()
            if (not stat.S_ISDIR(metadata.st_mode) or
                    metadata.st_uid != trusted_uid or metadata.st_mode & 0o022):
                return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        config = venv_root / 'pyvenv.cfg'
        config_stat = config.lstat()
        if (not stat.S_ISREG(config_stat.st_mode) or
                config_stat.st_uid != trusted_uid or
                config_stat.st_mode & 0o022 or
                config_stat.st_size > 65536):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        entry_stat = py.lstat()
        if (entry_stat.st_uid != trusted_uid or
                not (stat.S_ISLNK(entry_stat.st_mode) or
                     stat.S_ISREG(entry_stat.st_mode))):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        resolved = py.resolve(strict=True)
        target_stat = resolved.stat()
        approved_local = (
            resolved.parent == venv_root / 'bin' and
            re.fullmatch(r'python(?:3(?:\.[0-9]{1,2})?)?', resolved.name) is not None)
        approved_system = (
            resolved.parent in system_dirs and
            re.fullmatch(r'python3(?:\.[0-9]{1,2})?', resolved.name) is not None)
        if (not (approved_local or approved_system) or
                not stat.S_ISREG(target_stat.st_mode) or
                not target_stat.st_mode & 0o111 or
                target_stat.st_uid != trusted_uid or
                target_stat.st_mode & 0o022):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
    except (OSError, RuntimeError):
        return 'HOLD_PINNED_NATIVE_PYTHON_MISSING'
    return 'PINNED_NATIVE_PYTHON_TRUSTED'

def pinned_sftconfig_signature_probe(py):
    """Inspect the vetted venv interpreter, not its symlink spelling."""
    admission = pinned_python_path_status(py)
    if admission != 'PINNED_NATIVE_PYTHON_TRUSTED':
        return {'record': 'pinned_trl_sftconfig_signature',
                'scope': 'READ_ONLY_SIGNATURE_NO_TRAINER',
                'status': admission,
                'constructor_executed': False, 'optimizer_updates': 0}
    # Constructing SFTConfig() may initialise devices; inspect only its real
    # installed signature. A passed signature is not a live training test.
    code = """
import sys
sys.dont_write_bytecode = True
import inspect, importlib.metadata, json, os
if sys.version_info[:2] != (3, 12) or os.path.realpath(sys.prefix) != '/root/venv_volta':
    raise RuntimeError('PINNED_VENV_INTERPRETER_IDENTITY_HOLD')
from trl import SFTConfig
required = %r
parameters = inspect.signature(SFTConfig).parameters
accepted = {key for key, value in parameters.items()
            if value.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                              inspect.Parameter.KEYWORD_ONLY)}
print('NOX_SFTCONFIG_SIGNATURE=' + json.dumps({
  'schema': 'NOX_SFTCONFIG_NATIVE_SIGNATURE_V1',
  'trl_version': importlib.metadata.version('trl'),
  'missing_required_kwargs': [key for key in required if key not in accepted],
  'save_safetensors_parameter': 'save_safetensors' in accepted,
}, separators=(',', ':')))
""" % (SFTCONFIG_REQUIRED,)
    rc, output = run([str(py), '-I', '-c', code], timeout=30)
    return parse_sftconfig_signature_probe(rc, output)

def installed_package_versions_readback(py):
    """Inspect metadata only in a trusted, isolated pinned venv; never import torch."""
    status = pinned_python_path_status(py)
    result = {'record': 'installed_package_versions', 'python': str(py),
              'status': status, 'rc': None, 'versions': {},
              'cuda_context_created': False, 'trainer_started': False}
    if status != 'PINNED_NATIVE_PYTHON_TRUSTED':
        return result
    # The child checks actual version and sys.prefix, not only symlink ownership.
    code = """
import sys
sys.dont_write_bytecode = True
import importlib.metadata as m, json, os
if sys.version_info[:2] != (3, 12) or os.path.realpath(sys.prefix) != '/root/venv_volta':
    raise SystemExit('HOLD_PINNED_VENV_RUNTIME_IDENTITY')
names = ['torch','transformers','accelerate','datasets','safetensors','peft',
         'bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py','sqlite-vec',
         'playwright','pytest','ruff']
versions = {}
for name in names:
    try:
        versions[name] = m.version(name)
    except m.PackageNotFoundError:
        versions[name] = None
print(json.dumps(versions, separators=(',', ':')))
"""
    rc, output = run([str(py), '-I', '-c', code], timeout=20)
    result['rc'] = rc
    if rc != 0 or len(output) > 16384:
        result['status'] = 'HOLD_PACKAGE_METADATA_PROBE_FAILED'
        return result
    try:
        versions = json.loads(output)
    except (TypeError, ValueError):
        result['status'] = 'HOLD_PACKAGE_METADATA_INVALID'
        return result
    names = ('torch','transformers','accelerate','datasets','safetensors',
             'peft','bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py',
             'sqlite-vec','playwright','pytest','ruff')
    if (not isinstance(versions, dict) or set(versions) != set(names) or
            any(v is not None and
                (not isinstance(v, str) or len(v) > 128 or
                 not re.fullmatch(r'[0-9A-Za-z.+_!\\-]+', v))
                for v in versions.values())):
        result['status'] = 'HOLD_PACKAGE_METADATA_INVALID'
        return result
    result['status'] = 'READ_ONLY_VERSION_METADATA'
    result['versions'] = versions
    return result

def controls():
    """Bounded source/config digests and vetted probes; no raw private payloads."""
    rows = []
    names = ('train_qlora_35b_t866u.py','run_train_volta_t866u.sh',
             'nox_autoscale_t877u.py','owner_dispatcher_mentor.py','nox_dispatcher_t855u.py',
             'teacher_serve_t811u.sh','vram_guard_t829u.py','gpu_hang_watchdog_t865u.py',
             'nox_priority_scheduler.py','download_t802u.sh','chat_proxy.py',
             'nox_agent_architect_t859u.py','nox_agent_integrator_t859u.py','nox_agent_tuner_t858u.py')
    for name in names:
        rows.append(_compat_file_metadata(ROOT / 'scripts' / name, 250000))
    rows.append(_compat_file_metadata(Path('/root/nox_selfheal.py'), 110000))
    rows.append({'record': 'supervisor_configuration', 'services': supervisor_config()})
    py = Path('/root/venv_volta/bin/python')
    rows.append(installed_package_versions_readback(py))
    rows.append(pinned_sftconfig_signature_probe(py))
    # Worker configuration can contain prompts/memory under innocuous key names.
    # Preserve content identity without recursively exporting that configuration.
    pool = ROOT / 'config/dispatcher_agents_t868u.json'
    rows.append(dict(_compat_file_metadata(pool, 100000), record='dispatcher_workers',
                     configuration_withheld=True))
    return rows

def memory_metadata_inventory(roots):
    """Bounded nonsecret metadata for DB filenames, never a recall/health PASS.

    Do not follow symlinks, recurse into training data or read private rows.
    Canonical /root/nox/kb/knowledge.sqlite was missed by the older *.db glob.
    """
    files=[];seen=set()
    for root in roots:
        if root.is_symlink() or not root.is_dir(): continue
        # Sort candidate names together before inode deduplication: per-extension
        # traversal once kept c_alias.sqlite instead of canonical c.sqlite3.
        # Preserve the existing 50-per-extension and 100-total bounds.
        candidates=set()
        for pattern in ('*.db','*.sqlite','*.sqlite3'):
            candidates.update(sorted(root.glob(pattern))[:50])
        for p in sorted(candidates):
            if p.is_symlink() or not p.is_file(): continue
            try: st=p.stat()
            except OSError: continue
            key=(st.st_dev,st.st_ino)
            if key in seen: continue
            seen.add(key)
            files.append({'path':str(p),'bytes':st.st_size,'mtime':st.st_mtime})
            if len(files)>=100: return files
    return files

def chat_storage():
    out = {'health': {}, 'storage': {}}
    for port in (8080, 8081, 8082):
        started = time.monotonic()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=5) as response:
                status = response.status
        except Exception as exc:
            status = type(exc).__name__
        out['health'][str(port)] = {'status': status, 'seconds': round(time.monotonic() - started, 3)}
    if shutil.which('rclone'):
        rc, text = run(['rclone', 'listremotes'])
        out['storage'] = {'rclone': True, 'rc': rc, 'remotes': [name for name in text.splitlines()
            if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:', name) and redact(name) == name]}
    else:
        out['storage'] = {'rclone': False}
    out['memory_files'] = memory_metadata_inventory((ROOT / 'memory', ROOT / 'kb'))
    out['memory_files_scope'] = 'LOCAL_METADATA_ONLY'
    out['s03_recall_status'] = 'UNKNOWN_NOT_PROBED'
    out['model_slots_scope'] = 'INFERENCE_CONTEXT_SLOTS_NOT_MODEL_INSTANCES'
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots', timeout=3) as response:
            raw = response.read(100001)
        if len(raw) > 100000:
            raise ValueError('SLOT_RESPONSE_BOUND')
        slots = _compat_json(raw)
        if not isinstance(slots, list):
            raise ValueError('SLOT_RESPONSE_SCHEMA')
        result = []
        for slot in slots[:128]:
            if not isinstance(slot, dict):
                continue
            row = {}
            for key, low, high in (('id', 0, 255), ('n_ctx', 1, 1048576)):
                value = slot.get(key)
                if type(value) is int and low <= value <= high:
                    row[key] = value
            if type(slot.get('is_processing')) is bool:
                row['is_processing'] = slot['is_processing']
            # A backend-specific state object is not a public scalar contract.
            if type(slot.get('state')) is str and slot['state'] in ('idle', 'processing', 'IDLE', 'PROCESSING'):
                row['state'] = slot['state']
            result.append(row)
        out['model_slots'] = result
    except Exception as exc:
        out['model_slots_error'] = type(exc).__name__
    return out

PUBLIC_STATUS_CODE = re.compile(r'^[A-Za-z][A-Za-z0-9_:-]{0,95}$')

PUBLIC_TASK_ID = re.compile(r'^owner\.[A-Za-z0-9_.:-]{1,95}$')

PUBLIC_EVIDENCE_NUMBERS = frozenset((
    'successful_optimizer_steps', 'attempted_steps', 'skipped_steps',
    'verified_files', 'verified_bytes', 'training_started',
    'optimizer_steps_verified', 'native_verified', 'source_sha_verified'))

def safe_qwen_receipt_fields(data):
    """Project recognized public codes and bounded metrics, never arbitrary text."""
    if not isinstance(data, dict):
        return {}
    fields = {}
    for key in ('schema', 'state', 'status', 'phase', 'error', 'reason'):
        value = data.get(key)
        if _compat_public_code(key, value):
            fields[key] = value
    request = data.get('request')
    if type(request) is str and re.fullmatch(r'[0-9]{1,24}', request):
        fields['request'] = request
    for key in ('training_started', 'optimizer_steps_verified', 'checkpoint_verified'):
        if type(data.get(key)) is bool:
            fields[key] = data[key]
    for key in ('successful_optimizer_steps', 'successful_updates', 'global_step', 'step'):
        value = data.get(key)
        if type(value) is int and 0 <= value <= 10**12:
            fields[key] = value
    for key, maximum in (('loss', 10**6), ('finished_at', 10**12), ('updated_at', 10**12)):
        value = data.get(key)
        # Range-check integers before isfinite; enormous ints cannot coerce to float.
        if type(value) in (int, float) and 0 <= value <= maximum and math.isfinite(value):
            fields[key] = value
    return fields

def bounded_receipt_meta(path, limit=100000):
    path = Path(path)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return {'state': 'HOLD_SYMLINK'}
        if not stat.S_ISREG(info.st_mode):
            return {'state': 'HOLD_NONREGULAR'}
        if info.st_size > limit:
            return {'state': 'HOLD_FILE_BOUND'}
        raw, _ = safe_read(path, limit)
        try:
            obj = _compat_json(raw)
        except (ValueError, UnicodeError):
            return {'state': 'HOLD_INVALID_JSON'}
        if not isinstance(obj, dict):
            return {'state': 'HOLD_INVALID_OBJECT'}
        fields = {key: obj[key] for key in ('schema', 'state', 'status', 'kind', 'result_state')
                  if _compat_public_code(key, obj.get(key))}
        booleans = {'training_started', 'optimizer_steps_verified', 'native_verified', 'source_sha_verified'}
        for key in PUBLIC_EVIDENCE_NUMBERS:
            value = obj.get(key)
            if ((key in booleans and type(value) is bool)
                    or (key not in booleans and type(value) is int and 0 <= value <= 10**15)):
                fields[key] = value
        return {'state': 'READ_ONLY_METADATA', 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'fields': fields}
    except (OSError, ValueError):
        return {'state': 'HOLD_READ_FAILED'}

def safe_owner_task(task):
    if not isinstance(task, dict):
        return {'state': 'HOLD_INVALID_TASK'}
    fields = {}
    task_id = task.get('id')
    if (isinstance(task_id, str) and PUBLIC_TASK_ID.fullmatch(task_id)
            and redact(task_id) == task_id):
        fields['id'] = task_id
    for key in ('status', 'result_state'):
        if _compat_public_code(key, task.get(key)):
            fields[key] = task[key]
    for key in ('retries', 'finished_at', 'owner_claim_epoch'):
        value = task.get(key)
        if type(value) is int and 0 <= value <= 10**15:
            fields[key] = value
    fields['result_payload_withheld'] = 'result' in task
    return fields

def receipts():
    rows = []
    for p in sorted((ROOT / 'state').glob('owner_maintenance_*.json'))[-8:]:
        rows.append({'path': str(p), 'evidence': bounded_receipt_meta(p)})
    return rows

def owner_component_readback():
    rows = []
    for name in ('owner.training_stack', 'owner.dispatcher', 'owner.chat',
                 'owner.memory', 'owner.storage', 'owner.downloads'):
        path = ROOT / 'state/owner_components' / (name + '.json')
        if path.exists() or path.is_symlink():
            rows.append({'component': name, 'evidence': bounded_receipt_meta(path)})
    queue = ROOT / 'state/dispatcher/state.json'
    tasks, queue_scope = [], 'HOLD_NOT_READ'
    try:
        raw, _ = safe_read(queue, 3000000)
        state = _compat_json(raw)
        if isinstance(state, dict) and isinstance(state.get('tasks'), dict):
            tasks = [safe_owner_task(dict(task, id=task.get('id', name)))
                     for name, task in state['tasks'].items()
                     if isinstance(name, str) and name.startswith('owner.')
                     and isinstance(task, dict)][:512]
            queue_scope = 'OWNER_TASK_STATUS_ONLY_NO_RESULTS'
        else:
            queue_scope = 'HOLD_INVALID_QUEUE'
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError):
        queue_scope = 'HOLD_INVALID_QUEUE'
    print('NOX_MAINT_COMPONENTS=' + json.dumps(
        {'receipts': rows, 'tasks': tasks, 'queue_scope': queue_scope},
        separators=(',', ':'), allow_nan=False), flush=True)

def owner_safety_snapshot():
    """Read-only owner/8081 admission evidence; NEVER interpret a flag absence as a lease."""
    root = ROOT
    stop_names = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
                  'state/STOP', 'state/STOP.flag')
    paths = [root / name for name in stop_names] + [Path('/workspace/NOX_STOP'),
                                                    root / 'state/TRAIN_HOLD.flag',
                                                    root / 'state/TRAIN_PAUSE_REQUEST.flag']
    def kind(path):
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                return 'HOLD_SYMLINK'
            return 'PRESENT' if stat.S_ISREG(mode) else 'HOLD_NONREGULAR'
        except FileNotFoundError:
            return 'ABSENT'
        except OSError:
            return 'UNKNOWN'
    flags = {str(path): kind(path) for path in paths}
    # Include every canonical STOP alias (including /state/STOP.flag),
    # and the independent /workspace/NOX_STOP path; training flags follow.
    manual_flags = [flags[str(p)] for p in paths[:len(stop_names) + 1]]
    owner_stop = ('PRESENT' if 'PRESENT' in manual_flags
                  else 'HOLD_UNSAFE_FLAG' if any(x != 'ABSENT' for x in manual_flags)
                  else 'NOT_OBSERVED_NOT_AUTHORIZATION')
    maintenance_lock = kind(root / 'state/owner_maintenance.lock')
    # The real owner MODEL_UPDATE uses this separate maintenance flag.
    # Its omission made a stopped server appear to have no known maintenance
    # even when the owner had deliberately fenced it. Never infer a lease.
    owner_maintenance = kind(root / 'state/OWNER_MAINTENANCE.flag')
    # Neither a lock-file's existence nor a STOP absence is an owner writer lease.
    services = {}
    for name in ('nox-chat-8081', 'nox-dispatcher-t855u', 'nox-priority-scheduler',
                 'nox-selfheal', 'nox-gpu-watchdog-t865u'):
        rc, output = run(['supervisorctl', 'status', name], timeout=8)
        lines = output.strip().splitlines()
        match = re.match(r'^' + re.escape(name) + r'\s+([A-Z]+)(?:\s+pid\s+(\d+)\b)?',
                         lines[0]) if len(lines) == 1 else None
        status = match.group(1) if match else 'UNKNOWN'
        pid = int(match.group(2)) if match and match.group(2) else None
        # Nonzero supervisorctl cannot attest a RUNNING PID. A RUNNING row
        # without pid also fails closed; legitimate STOPPED (rc=3) remains visible.
        if status == 'RUNNING' and (rc != 0 or pid is None):
            status = 'UNKNOWN_SUPERVISOR_RUNNING_IDENTITY'
            pid = None
        start_ticks = None
        if pid:
            try:
                start_ticks = int((PROC / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19])
            except (OSError, IndexError, ValueError):
                status = 'UNKNOWN_PID_IDENTITY'
        services[name] = {'supervisor_rc': rc, 'state': status, 'pid': pid,
                          'start_ticks': start_ticks}
    inodes = set()
    net_status = 'OBSERVED'
    for net in (PROC / 'net/tcp', PROC / 'net/tcp6'):
        try:
            for line in net.read_text().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 10 and parts[3] == '0A' and int(parts[1].rsplit(':', 1)[1], 16) == 8081:
                    inodes.add(parts[9])
        except (OSError, IndexError, ValueError):
            net_status = 'UNKNOWN_NETWORK_NAMESPACE'
    owners, matched_inodes = [], set()
    if inodes:
        try:
            for process_index, proc in enumerate(PROC.iterdir()):
                if process_index >= 4096:
                    net_status = 'UNKNOWN_PID_SOCKET_MAPPING'; break
                if not proc.name.isdecimal():
                    continue
                try:
                    initial = (proc / 'stat').read_text()
                    ticks = int(initial.rsplit(') ', 1)[1].split()[19])
                    if initial.split(' (', 1)[0] != proc.name:
                        raise ValueError('PID_IDENTITY')
                    observed = set()
                    for fd_index, fd in enumerate((proc / 'fd').iterdir()):
                        if fd_index >= 4096:
                            net_status = 'UNKNOWN_PID_SOCKET_MAPPING'; break
                        try:
                            target = os.readlink(fd)
                        except OSError:
                            net_status = 'UNKNOWN_PID_SOCKET_MAPPING'; continue
                        if target.startswith('socket:[') and target.endswith(']') and target[8:-1] in inodes:
                            observed.add(target[8:-1])
                    again = (proc / 'stat').read_text()
                    if (again.split(' (', 1)[0] != proc.name
                            or int(again.rsplit(') ', 1)[1].split()[19]) != ticks):
                        raise ValueError('PID_CHANGED')
                    if observed:
                        owners.append({'pid': int(proc.name), 'start_ticks': ticks})
                        matched_inodes.update(observed)
                except (OSError, ValueError, IndexError):
                    net_status = 'UNKNOWN_PID_SOCKET_MAPPING'
        except OSError:
            net_status = 'UNKNOWN_PID_SOCKET_MAPPING'
    if inodes != matched_inodes and net_status == 'OBSERVED':
        net_status = 'UNRESOLVED_LISTENER_OWNER'
    heartbeat = {}
    for name in ('status/dispatcher_t855u.json', 'status/agents_t856u.json'):
        path = root / name
        if kind(path) == 'PRESENT':
            try:
                heartbeat[name] = {'mtime_ns': path.stat().st_mtime_ns,
                                   'scope': 'FILE_MTIME_ONLY_NOT_HEARTBEAT_PROOF'}
            except OSError:
                heartbeat[name] = {'state': 'UNKNOWN'}
        else:
            heartbeat[name] = {'state': kind(path)}
    return {'schema': 'NOX_OWNER_SAFETY_READONLY_V1',
            'stop_flags': flags, 'manual_stop': owner_stop,
            'owner_maintenance_flag': owner_maintenance,
            'maintenance_lock_file': maintenance_lock,
            'writer_lease': 'UNKNOWN_NO_OWNER_CAS_READBACK',
            'supervisor': services,
            'listener_8081': {'status': net_status,
                              'socket_inodes_observed': len(inodes),
                              'matched_pids': owners[:10],
                              'complete_pid_map': len(owners) <= 10 and inodes == matched_inodes and net_status == 'OBSERVED'},
            'dispatcher_heartbeat_files': heartbeat,
            'admission': 'READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER'}

MAYA_P0_BINARY_REL = 'engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4'

MAYA_P0_BINARY_SHA256 = '3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20'

def maya_p0_binary_readback(root=None, expected_sha256=None):
    """Read a bounded SHA/ELF pin; never run or load the model binary."""
    root = ROOT if root is None else Path(root)
    expected = MAYA_P0_BINARY_SHA256 if expected_sha256 is None else expected_sha256
    path = root / MAYA_P0_BINARY_REL
    result = {'schema': 'NOX_MAYA_P0_BINARY_READONLY_V1', 'path': str(path),
              'pinned_sha256': expected, 'observed_sha256': None,
              'state': 'HOLD_UNKNOWN', 'cuda124_runtime': 'NOT_TESTED',
              'sm70_kernel': 'NOT_TESTED', 'model_pack': 'NOT_TESTED',
              'real_inference': 'NOT_TESTED', 'native_model_promotion': False}
    parent_fd = None
    file_fd = None
    deadline = time.monotonic() + 12.0

    def within_deadline():
        if time.monotonic() >= deadline:
            result['state'] = 'HOLD_BINARY_READ_DEADLINE'
            return False
        return True

    try:
        if not path.is_absolute():
            result['state'] = 'HOLD_UNSAFE_PARENT'
            return result
        # Bind each ancestor by directory FD, including ancestors above root.
        # A path-based is_symlink/lstat check followed by open is not sufficient.
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            parent_fd = os.open('/', directory_flags)
            for part in path.parts[1:-1]:
                if not within_deadline():
                    return result
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child_fd
        except FileNotFoundError:
            result['state'] = 'HOLD_BINARY_NOT_PRESENT'
            return result
        except OSError:
            result['state'] = 'HOLD_UNSAFE_PARENT'
            return result

        leaf = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(leaf.st_mode):
            result['state'] = 'HOLD_SYMLINK_BINARY'
            return result
        if not stat.S_ISREG(leaf.st_mode) or not (leaf.st_mode & 0o111):
            result['state'] = 'HOLD_NOT_EXECUTABLE_REGULAR'
            return result
        # O_NONBLOCK prevents a FIFO substituted after the metadata check from
        # blocking before fstat. The FD is rechecked before reading any payload.
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                          os.O_NONBLOCK, dir_fd=parent_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or not (before.st_mode & 0o111):
            result['state'] = 'HOLD_NOT_EXECUTABLE_REGULAR'
            return result
        if not 64 <= before.st_size <= 1024 ** 3:
            result['state'] = 'HOLD_BINARY_SIZE'
            return result

        digest = hashlib.sha256()
        with os.fdopen(file_fd, 'rb', buffering=0, closefd=False) as stream:
            if not within_deadline():
                return result
            first = stream.read(64)
            if len(first) != 64:
                result['state'] = 'HOLD_BINARY_CHANGED_DURING_READ'
                return result
            if (first[:4] != b'\x7fELF' or first[4] != 2 or first[5] != 1
                    or int.from_bytes(first[18:20], 'little') != 62):
                result['state'] = 'HOLD_NOT_LINUX_X86_64_ELF'
                return result
            digest.update(first)
            remaining = before.st_size - len(first)
            while remaining:
                if not within_deadline():
                    return result
                block = stream.read(min(8 * 1024 * 1024, remaining))
                if not block:
                    result['state'] = 'HOLD_BINARY_CHANGED_DURING_READ'
                    return result
                digest.update(block)
                remaining -= len(block)
            if not within_deadline():
                return result
            # Never chase a growing file to EOF: at most original size + 1 byte.
            if stream.read(1):
                result['state'] = 'HOLD_BINARY_CHANGED_DURING_READ'
                return result

        after = os.fstat(file_fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after):
            result['state'] = 'HOLD_BINARY_CHANGED_DURING_READ'
            return result
        result['bytes'] = before.st_size
        result['observed_sha256'] = digest.hexdigest()
        result['state'] = ('SHA_PIN_MATCH_ELF_ONLY' if result['observed_sha256'] == expected
                           else 'HOLD_BINARY_SHA_MISMATCH')
        return result
    except FileNotFoundError:
        result['state'] = 'HOLD_BINARY_NOT_PRESENT'
    except (OSError, ValueError):
        result['state'] = 'HOLD_BINARY_IO_OR_PATH'
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    return result

def maya_elf_linkage_readback(root=None):
    """Read the pinned Maya ELF's dynamic section with readelf; never invoke Maya."""
    root = ROOT if root is None else Path(root)
    result = {'schema':'NOX_MAYA_ELF_LINKAGE_READONLY_V1',
              'path':str(root / MAYA_P0_BINARY_REL),
              'pinned_sha256':MAYA_P0_BINARY_SHA256,
              'observed_sha256':None,'bytes':None,'state':'HOLD_UNKNOWN',
              'needed_sonames':[],'rpath':[],'cuda_driver_direct_needed':False,'cuda_driver_expected_at_runtime':False,
              'cuda_runtime_needed':False,'cublas_needed':False,
              'maya_executable_invoked':False,'cuda_context_created':False,
              'dependency_resolution':'NOT_TESTED'}
    pin = maya_p0_binary_readback(root=root)
    result['observed_sha256'] = pin.get('observed_sha256')
    result['bytes'] = pin.get('bytes')
    if pin.get('state') != 'SHA_PIN_MATCH_ELF_ONLY':
        result['state'] = 'HOLD_BINARY_PIN'
        return result
    readelf = shutil.which('readelf')
    if not readelf:
        result['state'] = 'HOLD_READELF_UNAVAILABLE'
        return result
    try:
        cp = subprocess.run([readelf, '-d', '--wide', result['path']],
                            shell=False, check=False, capture_output=True,
                            text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        result['state'] = 'HOLD_READELF_FAILED'
        return result
    if cp.returncode != 0:
        result['state'] = 'HOLD_READELF_FAILED'
        return result
    needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', cp.stdout)
    paths = re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]*)\]', cp.stdout)
    result['needed_sonames'] = needed[:128]
    result['rpath'] = paths[:8]
    result['cuda_driver_direct_needed'] = any(x.startswith('libcuda.so') for x in needed)
    result['cuda_runtime_needed'] = any(x.startswith('libcudart.so') for x in needed)
    result['cuda_driver_expected_at_runtime'] = result['cuda_runtime_needed']
    result['cublas_needed'] = any(x.startswith(('libcublas.so', 'libcublasLt.so')) for x in needed)
    result['state'] = 'ELF_LINKAGE_READ_ONLY'
    return result

def maya_dependency_path_readback(linkage=None):
    """Stat expected CUDA DSOs in ldconfig cache or ELF RPATH; never load a DSO."""
    linkage = maya_elf_linkage_readback() if linkage is None else linkage
    result = {'schema':'NOX_MAYA_DEPENDENCY_PATHS_READONLY_V1',
              'state':'HOLD_UNKNOWN','method':'LDCONFIG_CACHE_AND_ELF_RPATH_STAT_ONLY',
              'libraries':{},'maya_executable_invoked':False,
              'cuda_context_created':False,'runtime_abi':'NOT_TESTED'}
    if linkage.get('state') != 'ELF_LINKAGE_READ_ONLY':
        result['state'] = 'HOLD_ELF_LINKAGE'
        return result
    ldconfig = shutil.which('ldconfig')
    if not ldconfig:
        result['state'] = 'HOLD_LDCONFIG_UNAVAILABLE'
        return result
    try:
        cp = subprocess.run([ldconfig, '-p'], shell=False, check=False,
                            capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        result['state'] = 'HOLD_LDCONFIG_FAILED'
        return result
    if cp.returncode != 0 or len(cp.stdout) > 1024 * 1024:
        result['state'] = 'HOLD_LDCONFIG_FAILED'
        return result
    names = ('libcuda.so.1','libcudart.so.12','libcublas.so.12','libcublasLt.so.12')
    cache = {name:[] for name in names}
    for line in cp.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] in cache and fields[-2] == '=>':
            cache[fields[0]].append(fields[-1])
    rpaths = [x for x in linkage.get('rpath',[]) if isinstance(x,str)]
    for name in names:
        paths = list(dict.fromkeys(cache[name] + [str(Path(base) / name) for base in rpaths]))
        found = []
        for candidate in paths[:32]:
            try:
                p = Path(candidate)
                if p.is_file():
                    found.append({'path':candidate,'resolved_path':str(p.resolve(strict=True))})
            except (OSError, RuntimeError):
                pass
        result['libraries'][name] = {'present':bool(found),'candidates':found[:8]}
    result['state'] = ('AVAILABLE_PATHS_ONLY' if all(result['libraries'][n]['present'] for n in names)
                       else 'HOLD_REQUIRED_LIBRARY_PATH_MISSING')
    cuda_paths = result['libraries']['libcuda.so.1']['candidates']
    rt_paths = result['libraries']['libcudart.so.12']['candidates']
    result['driver_path_hint'] = cuda_paths[0]['resolved_path'] if cuda_paths else None
    result['toolkit_path_hint'] = rt_paths[0]['resolved_path'] if rt_paths else None
    result['cuda_toolkit_path_version_hint'] = (
        '12.4' if any('/cuda-12.4/' in row['resolved_path'] for row in rt_paths) else 'UNKNOWN')
    return result

if __name__ == '__main__':
    main()
