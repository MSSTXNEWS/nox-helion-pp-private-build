#!/usr/bin/env python3
"""One bounded, read-only inspection of the fixed Qwen media retry.

No queue changes, claim acquisition, retries, model imports or output payload
reads. Only categorical state, identifiers, hashes and numeric telemetry leave
this process. A completed job record is not a new verification of its output.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
LINK = STATE / 'media/retries/qwen_completed6_6907909296.json'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
OLD = {'5eb826584f059b8dd8eeffe8b4f6cb3a', '72c5ab9b719d0b9a5a191f863db42b1f'}
NAMED = {'943c960553eb5f6cf13702455d06a5d8', '25333223e1a7d6e1bedf92c38a7eaebd'}
SERVICES = ('nox-dispatcher-t855u', 'nox-train-volta-t866u', 'nox-media-comfyui')
TASK_STATES = {'pending', 'wait', 'retry', 'running', 'done', 'blocked', 'failed', 'cancelled'}
JOB_STATES = {'QUEUED', 'YIELDING_TRAINING', 'WAITING_RESOURCES', 'RUNNING', 'SUBMITTING',
              'CANCEL_REQUESTED', 'COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED'}
JOB = re.compile('[a-f0-9]{32}')
PLAN = re.compile('[a-f0-9]{24}')
SHA = re.compile('[a-f0-9]{64}')
TASK = re.compile(r'owner\.(?:media\.[a-f0-9]{32}|plan\.media\.[a-f0-9]{32}|branch\.[a-f0-9]{24}\.[a-z_]{1,40})')
CATEGORIES = JOB_STATES | {'SUBMITTING', 'PREPARED_BEFORE_JOB_PUBLICATION', 'SUBMITTED_GENERATION_PENDING',
    'TWO_REPLACEMENT_JOBS_SUBMITTED', 'REPLACEMENT_MEDIA_GENERATED_VERIFIED', 'REPLACEMENT_MEDIA_OBSERVED_NOT_ACCEPTED',
    'PLANNED_WAITING_FOR_VERIFIED_BRANCHES', 'PLAN_QUEUED_NOT_COMPLETED', 'WAITING_READY_TASK', 'NOT_YET_ADMITTED',
    'ADMITTED_NOT_EXECUTED', 'OBSERVED_RESOURCE_BUDGET', 'MEDIA_ENGINE_AND_ASSET_READINESS_ONLY',
    'VERIFIED_MEDIA_OUTPUT', 'ACTUAL_MEDIA_OUTPUT_REQUIRED'}
DEADLINE = None


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_MEDIA_RETRY_OBSERVER_' + code)


def budget():
    require(DEADLINE is None or time.monotonic() < DEADLINE, 'DEADLINE')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT|NEEDS)_[A-Z0-9_]{1,120}', value) else 'HOLD_MEDIA_RETRY_OBSERVER_' + type(exc).__name__.upper()


def category(value):
    return value if isinstance(value, str) and (value in CATEGORIES
        or re.fullmatch('(HOLD|WAIT|NEEDS)_[A-Z0-9_]{1,110}', value)) else None


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def sha_field(value):
    return value if isinstance(value, str) and SHA.fullmatch(value) else None


def read(path, maximum=262144):
    budget(); path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
        raw = stream.read(maximum + 1)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    budget()
    return raw, {'sha256': digest(raw), 'bytes': len(raw), 'mtime_ns': before.st_mtime_ns,
                 'age_seconds': max(0, round(time.time() - before.st_mtime, 3))}


def pairs(rows):
    value = {}
    for key, item in rows:
        require(key not in value, 'DUPLICATE_JSON_KEY'); value[key] = item
    return value


def document(path, maximum=262144):
    raw, meta = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT'); encoded(value)
    return value, meta


def attempt(function, *args):
    try:
        return function(*args)
    except Exception as exc:
        return {'observation': 'HELD', 'reason': safe(exc)}


def retry_map():
    row, meta = document(LINK)
    require(row.get('schema') == 'NOX_QWEN_MEDIA_RETRY_V1'
            and isinstance(row.get('request'), str) and re.fullmatch('[0-9]{1,24}', row['request'])
            and isinstance(row.get('source_sha'), str) and re.fullmatch('[a-f0-9]{40}', row['source_sha']), 'RETRY_SCHEMA')
    items = row.get('replacements')
    require(isinstance(items, list) and 1 <= len(items) <= 2, 'RETRY_COUNT')
    projected, seen_old, seen_new = [], set(), set()
    for item in items:
        require(isinstance(item, dict) and item.get('old_job_id') in OLD
                and item['old_job_id'] not in seen_old and item.get('kind') in ('image', 'video'), 'RETRY_OLD')
        new = item.get('new_job_id')
        require(new is None or isinstance(new, str) and JOB.fullmatch(new)
                and new not in OLD and new not in seen_new, 'RETRY_NEW')
        seen_old.add(item['old_job_id'])
        if new:
            seen_new.add(new)
        projected.append({'old_job_id': item['old_job_id'], 'new_job_id': new,
                          'kind': item['kind'], 'state': category(item.get('state')),
                          'request_sha256': sha_field(item.get('request_sha256'))})
    return {'observation': 'READ', 'file': meta, 'request': row['request'], 'source_sha': row['source_sha'],
            'state': category(row.get('state')), 'replacements': projected}, seen_new


def job_record(job_id):
    require(JOB.fullmatch(job_id), 'JOB_SCOPE')
    row, meta = document(STATE / 'media/jobs' / (job_id + '.json'))
    require(row.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1' and row.get('id') == job_id
            and row.get('state') in JOB_STATES and isinstance(row.get('request'), dict), 'JOB_SCHEMA')
    request = row['request']; require(request.get('kind') in ('image', 'video'), 'JOB_KIND')
    outputs = row.get('outputs', [])
    require(isinstance(outputs, list) and len(outputs) <= 8 and all(isinstance(v, dict) for v in outputs), 'OUTPUT_BOUND')
    result = {'job_id': job_id, 'file': meta, 'state': row['state'], 'kind': request['kind'],
              'request_sha256': digest((json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()),
              'generation_verified_recorded': row.get('generation_verified') is True,
              'gpu1_released_recorded': row.get('gpu1_released') is True,
              'cancel_requested': row.get('cancel_requested') is True,
              'reason': category(row.get('reason')), 'reason_present': bool(row.get('reason')),
              'created_at': number(row.get('created_at')), 'updated_at': number(row.get('updated_at')),
              'outputs': [{**{key: number(item.get(key)) for key in ('bytes', 'width', 'height', 'frames')},
                           'sha256': sha_field(item.get('sha256'))} for item in outputs],
              'output_payload_read': False, 'output_sha256_reverified': False}
    inbox = STATE / 'media/inbox' / (job_id + '.json')
    result['inbox_present'] = inbox.exists() or inbox.is_symlink()
    if result['inbox_present']:
        queued, imeta = document(inbox, 4096)
        require(queued == {'job_id': job_id}, 'INBOX_IDENTITY')
        result['inbox'] = imeta
    prompt_id = row.get('prompt_id')
    if prompt_id is not None:
        require(isinstance(prompt_id, str) and re.fullmatch('[a-f0-9-]{16,64}', prompt_id), 'COMFY_ID')
    return result, prompt_id


def task_record(task_id, row, tasks):
    require(TASK.fullmatch(task_id) and isinstance(row, dict) and row.get('id') == task_id, 'TASK_IDENTITY')
    claim = row.get('owner_claim'); result = row.get('result'); result = result if isinstance(result, dict) else {}
    evidence = result.get('receipt'); evidence = evidence if isinstance(evidence, dict) else {}
    dependencies = row.get('deps') or []
    require(isinstance(dependencies, list) and len(dependencies) <= 12
            and all(isinstance(v, str) and TASK.fullmatch(v) for v in dependencies), 'DEPENDENCY_SCOPE')
    worker = claim.get('worker') if isinstance(claim, dict) else None
    return {'task_id': task_id, 'task_sha256': digest(encoded(row)),
            'status': row.get('status') if row.get('status') in TASK_STATES else 'UNKNOWN',
            'handler': row.get('handler') if row.get('handler') in ('owner_media', 'owner_plan_step', 'owner_plan_join') else None,
            'plan_id': row.get('owner_plan_id') if isinstance(row.get('owner_plan_id'), str) and PLAN.fullmatch(row['owner_plan_id']) else None,
            'parent_id': row.get('owner_parent_id') if isinstance(row.get('owner_parent_id'), str) and TASK.fullmatch(row['owner_parent_id']) else None,
            'dependencies': [{'task_id': key, 'status': tasks.get(key, {}).get('status')
                              if tasks.get(key, {}).get('status') in TASK_STATES else 'UNKNOWN'} for key in dependencies],
            'claim': {'present': isinstance(claim, dict), 'sha256': digest(encoded(claim)) if isinstance(claim, dict) else None,
                      'worker': worker if isinstance(worker, str) and re.fullmatch('nox-agent-[0-9]{2}', worker) else None,
                      'pid': claim.get('pid') if isinstance(claim, dict) and type(claim.get('pid')) is int else None},
            'retries': number(row.get('retries')), 'max_retries': number(row.get('max_retries')),
            'note_code': category(row.get('note')), 'note_present': bool(row.get('note')),
            'plan_wait': category(row.get('owner_plan_wait')), 'plan_state': category(row.get('owner_plan_state')),
            'result': {'sha256': digest(encoded(result)), 'state': category(result.get('state')),
                       'reason': category(result.get('reason')), 'verified': result.get('verified') is True,
                       'generation_verified': result.get('generation_verified') is True,
                       'receipt_sha256': sha_field(result.get('receipt_sha256')),
                       'receipt_state': category(evidence.get('state')),
                       'receipt_claim_matches': bool(claim) and evidence.get('claim') == claim},
            'saved_plan_receipt': attempt(plan_receipt, task_id, row)}


def plan_receipt(task_id, task):
    result = task.get('result')
    if not isinstance(result, dict) or not result.get('receipt_path'):
        return {'present_in_task_result': False}
    plan, claim = task.get('owner_plan_id'), task.get('owner_claim')
    require(isinstance(plan, str) and PLAN.fullmatch(plan) and isinstance(claim, dict)
            and isinstance(claim.get('nonce'), str) and PLAN.fullmatch(claim['nonce']), 'PLAN_RECEIPT_SCOPE')
    expected = STATE / 'owner_plans' / plan / (digest(encoded(task_id))[:24] + '.' + claim['nonce'] + '.json')
    require(result['receipt_path'] == str(expected) and sha_field(result.get('receipt_sha256')), 'PLAN_RECEIPT_PATH')
    row, meta = document(expected, 131072)
    require(meta['sha256'] == result['receipt_sha256'] and row.get('schema') == 'NOX_OWNER_PLAN_RECEIPT_V1'
            and row.get('plan_id') == plan and row.get('task_id') == task_id and row.get('claim') == claim,
            'PLAN_RECEIPT_BINDING')
    blockers = row.get('blockers', [])
    require(isinstance(blockers, list) and len(blockers) <= 32, 'PLAN_BLOCKER_BOUND')
    return {'present_in_task_result': True, 'file': meta, 'claim_matches': True,
            'verified_recorded': row.get('verified') is True, 'scope': category(row.get('scope')),
            'source_sha256': sha_field(row.get('source_sha256')), 'manifest_sha256': sha_field(row.get('manifest_sha256')),
            'blocker_codes': [category(item) for item in blockers if category(item)],
            'native_evidence_sha256': sha_field(row.get('native_evidence_sha256'))}


def task_graph(job_ids):
    state, meta = document(STATE / 'dispatcher/state.json', 16 * 1024 ** 2)
    tasks = state.get('tasks'); require(isinstance(tasks, dict) and len(tasks) <= 20000
                                       and all(isinstance(v, dict) for v in tasks.values()), 'TASKS_BOUND')
    selected = {prefix + job for job in job_ids for prefix in ('owner.media.', 'owner.plan.media.')}
    selected &= tasks.keys()
    plans = {tasks[key].get('owner_plan_id') for key in selected if isinstance(tasks[key].get('owner_plan_id'), str)
             and PLAN.fullmatch(tasks[key]['owner_plan_id'])}
    selected |= {key for key, row in tasks.items() if row.get('owner_plan_id') in plans}
    require(len(selected) <= 48, 'RELATED_TASK_BOUND')
    counts = {status: sum(row.get('status') == status for row in tasks.values()) for status in sorted(TASK_STATES)}
    return {'file': meta, 'total_tasks': len(tasks), 'counts': counts,
            'relevant_tasks': [task_record(key, tasks[key], tasks) for key in sorted(selected)],
            'no_tasks_requeued': True}


def workers():
    row, meta = document(ROOT / 'status/agents_t856u.json', 750000)
    workers = row.get('workers'); require(isinstance(workers, list) and len(workers) <= 16, 'WORKERS_BOUND')
    native = row.get('native_subexecutors') or {}; admission = native.get('last_admission') or {}
    return {'file': meta, 'reported_thread_count': number(row.get('n')),
            'workers': [{'id': item.get('id') if re.fullmatch('nox-agent-[0-9]{2}', str(item.get('id'))) else None,
                         'status': item.get('status') if item.get('status') in ('idle', 'busy', 'waiting') else None,
                         'has_current_task': bool(item.get('current_task'))} for item in workers if isinstance(item, dict)],
            'native_reviewers': {'target': number(native.get('target')), 'state': category(admission.get('state')),
                                 'jobs_started': number(admission.get('jobs_started')),
                                 'physical_pool_count': len(native['workers']) if isinstance(native.get('workers'), list) else None}}


def services():
    budget()
    proc = subprocess.run(['supervisorctl', 'status', *SERVICES], capture_output=True, timeout=5)
    require(len(proc.stdout) <= 8192, 'SERVICE_OUTPUT_BOUND')
    result = {}
    for name in SERVICES:
        match = re.search(rb'^' + name.encode() + rb'\s+(RUNNING|STARTING|STOPPED|EXITED|FATAL|BACKOFF|STOPPING|UNKNOWN)\b(?:\s+pid\s+([0-9]+))?', proc.stdout, re.M)
        result[name] = {'state': match[1].decode() if match else 'UNKNOWN', 'pid': int(match[2]) if match and match[2] else None}
    budget(); return result


def runtime():
    path = ROOT / 'scripts/owner_media_runtime.py'; raw, _ = read(path, 2 * 1024 ** 2)
    require(digest(raw) == RUNTIME_SHA, 'RUNTIME_PIN')
    value = types.ModuleType('_nox_media_retry_observer_runtime'); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    value.read_json = lambda p, limit=262144: document(p, limit)[0]
    return value


def dispatcher_source():
    _, meta = read(ROOT / 'scripts/nox_dispatcher_t855u.py', 2 * 1024 ** 2)
    profiles = {'eeacabfc161d28001396a901c2680f58b71a7fcedd6c46893fc6744144bb6e17': 'QWEN_MEDIA_HANDOFF',
                '439f669487e965b3a9709078674c1fbff6ceff332b0ad2089dad1f218c2e57cf': 'QWEN_INACTIVE_GUARD_INSTALLED'}
    return {'file': meta, 'known_source_profile': profiles.get(meta['sha256']),
            'source_imported': False, 'unknown_source_is_observation_only': meta['sha256'] not in profiles}


def media_gates(rt):
    config = rt.configuration()
    results = {}
    for kind in ('image', 'video'):
        budget()
        try:
            result = rt.resource_gate(config, kind)
            results[kind] = {'state': 'CURRENT_RESOURCE_GATE_PASSED', 'memory_current': result['memory_current'],
                             'memory_max': result['memory_max'], 'gpu1': result['gpu1']}
        except Exception as exc:
            results[kind] = {'state': 'CURRENT_RESOURCE_GATE_HELD', 'reason': safe(exc)}
    return {'scope': 'CURRENT_READ_ONLY_MEDIA_RESOURCE_GATE_NOT_GENERATION_ACCEPTANCE', 'kinds': results}


def comfy(rt, prompts):
    budget(); rows = rt.queue_ids(); budget()
    require(set(rows) == {'queue_running', 'queue_pending'} and all(isinstance(v, list) and len(v) <= 200 for v in rows.values()), 'COMFY_BOUND')
    return {'running_count': len(rows['queue_running']), 'pending_count': len(rows['queue_pending']),
            'target_jobs': {job: {'prompt_id_present': prompt is not None,
                                 'running': prompt in rows['queue_running'] if prompt else False,
                                 'pending': prompt in rows['queue_pending'] if prompt else False}
                            for job, prompt in prompts.items()}, 'graphs_exported': False}


def snapshot():
    global DEADLINE
    DEADLINE = time.monotonic() + 40
    result = {'schema': 'NOX_QWEN_MEDIA_RETRY_OBSERVATION_V1', 'started_at': time.time(),
              'state': 'READ_ONLY_OBSERVATION', 'mutations_performed': False, 'jobs_submitted': 0,
              'prompts_exported': False, 'owner_identifiers_exported': False, 'output_payloads_read': False}
    target = set(NAMED)
    try:
        result['retry_map'], mapped = retry_map(); target |= mapped
    except Exception as exc:
        result['retry_map'] = {'observation': 'HELD', 'reason': safe(exc)}
    require(len(target) <= 4, 'TARGET_COUNT')
    results, prompts = [], {}
    for job in sorted(target):
        try:
            row, prompt = job_record(job); results.append(row); prompts[job] = prompt
        except Exception as exc:
            results.append({'job_id': job, 'observation': 'HELD', 'reason': safe(exc)})
    result['jobs'] = results
    result['dispatcher_tasks'] = attempt(task_graph, target | OLD)
    result['dispatcher_source'] = attempt(dispatcher_source)
    result['workers'] = attempt(workers)
    result['services'] = attempt(services)
    try:
        rt = runtime()
        result['media_resource_gate'] = attempt(media_gates, rt)
        result['comfy_queue'] = attempt(comfy, rt, prompts)
    except Exception as exc:
        result['runtime'] = {'observation': 'HELD', 'reason': safe(exc)}
    if result['retry_map'].get('file'):
        try:
            _, after = read(LINK)
            result['retry_map_unchanged_during_observation'] = after['sha256'] == result['retry_map']['file']['sha256']
        except Exception:
            result['retry_map_unchanged_during_observation'] = False
    result['finished_at'] = time.time()
    result['all_media_complete_proven'] = False
    require(len(encoded(result)) <= 192000, 'OUTPUT_BOUND')
    return result


def main():
    try:
        result = snapshot()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_media_retry_observation', 'data': result}, allow_nan=False), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_media_retry_observation',
              'data': {'state': 'HELD', 'reason': safe(exc), 'mutations_performed': False}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
