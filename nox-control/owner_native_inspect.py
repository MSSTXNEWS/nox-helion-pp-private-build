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

if __name__ == '__main__':
    main()
