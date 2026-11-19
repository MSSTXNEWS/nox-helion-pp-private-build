#!/usr/bin/env python3
"""Inline preflight, verified result links and proactive reporting for NOX.

The existing dispatcher owns workers, claims, DAG ordering and native actions.
This module attaches bounded recall/consultation metadata and reports evidence;
it does not execute advice, start a scheduler, load a model or invent authority.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

import owner_event_outbox as outbox

ROOT = Path('/root/nox')
PATCH_MARKER = 'NOX_OWNER_TASK_LIFECYCLE_BIND_V1'
SHA = re.compile(r'^[0-9a-f]{64}$')
MEMORY_METHODS = {'semantic', 'hybrid', 'fts', 'like', 'pin', 'recent'}
MEMORY_KINDS = {'LEXICAL_WITH_PINS', 'LEXICAL_BOUNDED_PINS', 'SEMANTIC_LEXICAL_BOUNDED_PINS'}
_LOCAL = threading.local()
_CONTEXT_SLOT = threading.Lock()
_CACHE_LOCK = threading.Lock()
_CACHE = {}
CACHE_SECONDS = 300
LIFECYCLE_SCHEMA = 'NOX_OWNER_TASK_LIFECYCLE_V1'


class LifecycleHold(RuntimeError):
    pass


def file_sha(path, maximum=1024 * 1024):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise LifecycleHold('HOLD_LIFECYCLE_SOURCE_SCOPE')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise LifecycleHold('HOLD_LIFECYCLE_SOURCE_SCOPE')
    return hashlib.sha256(raw).hexdigest()


def bounded_json(path, maximum=262144):
    try:
        return outbox.read_json(Path(path), maximum)
    except (OSError, ValueError, outbox.OutboxHold):
        return None


def journal_recall(task):
    """Read only bounded technical metadata from the existing shared journal."""
    path = ROOT / 'memory/dispatcher_mentor/events.jsonl'
    result = {'state': 'JOURNAL_UNAVAILABLE', 'verified': 0, 'errors': 0,
              'quarantined': 0, 'references_sha256': [], 'error_categories': []}
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return result
            size = info.st_size
            stream.seek(max(0, size - 65536))
            if size > 65536:
                stream.readline(65537)
            lines = stream.read(65536).splitlines()
        categories = set()
        verified_receipts = set()
        for line in lines[-100:]:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(row, dict) or row.get('schema') != 'NOX_DISPATCHER_MENTOR_V1':
                continue
            if row.get('task_id') != task.get('id') and row.get('handler') != task.get('handler'):
                continue
            kind = row.get('kind')
            if kind == 'experience_verified':
                # A verified holdout is not an accepted reusable repair.
                # Native mentor receipts record the handler only in the
                # underlying experience row, so bind reusable success to
                # this exact TaskID rather than another task's handler.
                proof = row.get('verification')
                if (row.get('task_id') != task.get('id')
                        or row.get('accepted') is not True
                        or row.get('partition') != 'train'
                        or not isinstance(proof, dict)
                        or proof.get('kind') not in (
                            'bounded_native_component_check',
                            'native_supervisor_running',
                            'native_gguf_header')
                        or not isinstance(row.get('dedup_sha256'), str)
                        or not SHA.fullmatch(row['dedup_sha256'])):
                    continue
                # Journal replay or repeated reporting of the same native
                # evidence is not another successful skill application.
                if row['dedup_sha256'] in verified_receipts:
                    continue
                verified_receipts.add(row['dedup_sha256'])
                result['verified'] += 1
            elif kind == 'error_observed':
                result['errors'] += 1
                if row.get('category') in ('out_of_memory', 'missing_file', 'permission', 'timeout', 'service_unavailable', 'validation', 'unknown'):
                    categories.add(row['category'])
            elif kind == 'experience_quarantined':
                result['quarantined'] += 1
            else:
                continue
            result['references_sha256'].append(hashlib.sha256(line).hexdigest())
        result.update(state='JOURNAL_RECALLED', references_sha256=result['references_sha256'][-8:], error_categories=sorted(categories))
    except OSError:
        pass
    return result


# Fixed child code, not a model-generated program. It emits metadata only and
# suppresses module prints, so private S03 text cannot enter logs or API calls.
# It remains disabled until the exact native module has been inspected/pinned.
_RECALL_CHILD = r'''
import contextlib, hashlib, importlib.util, json, os, pathlib, sys
p=pathlib.Path('/root/nox/scripts/s03_memory.py')
raw=p.read_bytes()
if p.is_symlink() or hashlib.sha256(raw).hexdigest()!=sys.argv[1]:
    raise SystemExit(2)
sys.path.insert(0,str(p.parent))
gateway_sha=sys.argv[3] if len(sys.argv)>3 else '-'
gateway_raw=None;gateway_path=p.parent/'owner_s03_gateway.py'
if gateway_sha!='-':
    gateway_raw=gateway_path.read_bytes()
    if gateway_path.is_symlink() or hashlib.sha256(gateway_raw).hexdigest()!=gateway_sha:
        raise SystemExit(2)
elif b'owner_s03_gateway' in raw:
    raise SystemExit(2)
with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
    if gateway_raw is not None:
        spec=importlib.util.spec_from_file_location('owner_s03_gateway',str(gateway_path))
        gateway=importlib.util.module_from_spec(spec);sys.modules['owner_s03_gateway']=gateway
        exec(compile(gateway_raw,str(gateway_path),'exec'),gateway.__dict__)
    spec=importlib.util.spec_from_file_location('s03_memory',str(p))
    module=importlib.util.module_from_spec(spec);sys.modules['s03_memory']=module
    exec(compile(raw,str(p),'exec'),module.__dict__)
    rows=module.recall(sys.argv[2],k=16)
if not isinstance(rows,list): raise SystemExit(3)
result=[]
rows=rows[:20]
ranked=sorted(rows,key=lambda row:0 if isinstance(row,dict) and row.get('how') in ('semantic','hybrid','fts','like') else 1)
for row in ranked[:8]:
    if not isinstance(row,dict): continue
    encoded=json.dumps(row,sort_keys=True,ensure_ascii=False,default=str).encode()
    result.append({'reference_sha256':hashlib.sha256(encoded).hexdigest(),
                   'method':row.get('how') if row.get('how') in ('semantic','hybrid','fts','like','pin','recent') else 'unknown'})
semantic=sum(isinstance(row,dict) and row.get('how') in ('semantic','hybrid') for row in rows)
if semantic and gateway_raw is None:raise SystemExit(3)
kind=('SEMANTIC_LEXICAL_BOUNDED_PINS' if semantic else 'LEXICAL_BOUNDED_PINS') if gateway_raw is not None else 'LEXICAL_WITH_PINS'
print(json.dumps({'state':'S03_RECALLED','retrieval_kind':kind,
                  'lexical_matches':sum(isinstance(row,dict) and row.get('how') in ('fts','like','hybrid') for row in rows),
                  'semantic_matches':semantic,'gateway_source_verified':gateway_raw is not None,
                  'references':result,'content_exported':False}))
'''


def semantic_recall(task):
    config = bounded_json(ROOT / 'config/owner_task_lifecycle.json', 16000)
    if not isinstance(config, dict) or config.get('schema') != LIFECYCLE_SCHEMA:
        return {'state': 'MISSING_S03_SOURCE_PIN', 'content_exported': False}
    expected = config.get('s03_source_sha256')
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        return {'state': 'MISSING_S03_SOURCE_PIN', 'content_exported': False}
    gateway_sha = config.get('s03_gateway_source_sha256')
    gateway_enabled = config.get('shared_memory_retrieval') in ('LEXICAL_BOUNDED_PINS', 'SEMANTIC_LEXICAL_BOUNDED_PINS')
    if gateway_enabled and (not isinstance(gateway_sha, str) or not SHA.fullmatch(gateway_sha)):
        return {'state': 'MISSING_S03_GATEWAY_SOURCE_PIN', 'content_exported': False}
    source = ROOT / 'scripts/s03_memory.py'
    try:
        if file_sha(source) != expected:
            return {'state': 'S03_SOURCE_CHANGED', 'content_exported': False}
        if gateway_enabled and file_sha(ROOT / 'scripts/owner_s03_gateway.py') != gateway_sha:
            return {'state': 'S03_GATEWAY_SOURCE_CHANGED', 'content_exported': False}
        # No arbitrary task text is interpolated into code or an external call.
        query = 'NOX technical verified decisions prior errors ' + outbox.safe_id(task.get('handler'))
        child = subprocess.run(['/root/venv_volta/bin/python', '-I', '-c', _RECALL_CHILD, expected, query,
                                gateway_sha if gateway_enabled else '-'],
                               capture_output=True, timeout=1.25, check=False)
        if child.returncode or len(child.stdout) > 12000:
            return {'state': 'S03_RECALL_UNAVAILABLE', 'content_exported': False}
        value = json.loads(child.stdout)
        refs = value.get('references') if isinstance(value, dict) else None
        if (not isinstance(value, dict) or value.get('state') != 'S03_RECALLED' or value.get('retrieval_kind') not in MEMORY_KINDS
                or (value['retrieval_kind'] != 'LEXICAL_WITH_PINS' and not gateway_enabled)
                or (gateway_enabled and value.get('gateway_source_verified') is not True)
                or not isinstance(refs, list) or len(refs) > 8
                or any(not isinstance(row, dict) or not SHA.fullmatch(str(row.get('reference_sha256', ''))) for row in refs)):
            return {'state': 'S03_RECALL_UNVERIFIED', 'content_exported': False}
        matches = value.get('lexical_matches')
        semantic = value.get('semantic_matches')
        if value['retrieval_kind'] == 'SEMANTIC_LEXICAL_BOUNDED_PINS' and (type(semantic) is not int or not 1 <= semantic <= 20):
            return {'state': 'S03_RECALL_UNVERIFIED', 'content_exported': False}
        return {'state': 'S03_RECALLED', 'retrieval_kind': value['retrieval_kind'],
                'lexical_matches': matches if type(matches) is int and 0 <= matches <= 20 else None,
                'semantic_matches': semantic if type(semantic) is int and 0 <= semantic <= 20 else None,
                'references': [{'reference_sha256': row['reference_sha256'], 'method': row.get('method') if row.get('method') in MEMORY_METHODS else 'unknown'} for row in refs],
                'source_sha256': expected, 'gateway_source_sha256': gateway_sha if gateway_enabled else None,
                'content_exported': False}
    except subprocess.TimeoutExpired:
        return {'state': 'S03_RECALL_BUDGET_EXHAUSTED', 'content_exported': False}
    except (OSError, ValueError, LifecycleHold):
        return {'state': 'S03_RECALL_UNAVAILABLE', 'content_exported': False}


def configure_shared_recall(config, s03_source_sha256, gateway_source_sha256):
    """Derive only the reviewed S03 config delta; caller pins and writes it."""
    if not isinstance(config, dict) or config.get('schema') != LIFECYCLE_SCHEMA:
        raise LifecycleHold('HOLD_LIFECYCLE_RECALL_CONFIG_SCHEMA')
    if any(not isinstance(value, str) or not SHA.fullmatch(value)
           for value in (s03_source_sha256, gateway_source_sha256)):
        raise LifecycleHold('HOLD_LIFECYCLE_RECALL_CONFIG_PINS')
    result = copy.deepcopy(config)
    result.update(s03_source_sha256=s03_source_sha256,
                  s03_gateway_source_sha256=gateway_source_sha256,
                  shared_memory_retrieval='SEMANTIC_LEXICAL_BOUNDED_PINS')
    return result


def _gateway_result(value):
    if not isinstance(value, dict):
        return {'state': 'SENIOR_RESPONSE_UNVERIFIED', 'research_state': 'INTERNET_RESEARCH_NOT_VERIFIED'}
    result = {'state': outbox.safe_code(value.get('state'), 'SENIOR_RESPONSE_UNVERIFIED'),
              'research_state': outbox.safe_code(value.get('research_state'), 'INTERNET_RESEARCH_NOT_VERIFIED')}
    for key in ('consultation_sha256', 'config_sha256'):
        if isinstance(value.get(key), str) and SHA.fullmatch(value[key]):
            result[key] = value[key]
    count = value.get('models_consulted')
    result['models_consulted'] = count if type(count) is int and 0 <= count <= 3 else 0
    result['advisory_mode'] = 'COUNCIL' if result['models_consulted'] >= 2 else 'SINGLE_ADVISER' if result['models_consulted'] == 1 else 'NONE'
    result['advice_scope'] = outbox.safe_code(value.get('advice_scope'), 'NOT_AVAILABLE')
    # Suggestions are candidate data. No action string, code or shell is used.
    result['candidate_state'] = 'EVALUATION_REQUIRED' if value.get('candidate') else 'NO_NEW_CANDIDATE'
    return result


def technical_details(task, local_recall, plan, memory):
    """Actual bounded observations plus fixed public intent/error descriptions."""
    params = task.get('params') if isinstance(task.get('params'), dict) else {}
    intent_map = {'audit': 'audit_components', 'optimize_workers': 'optimize_resources',
                  'training_status': 'review_checkpoint', 'training_resume': 'optimize_training',
                  'downloads': 'refresh_dependencies'}
    requested = params.get('plan') if isinstance(params.get('plan'), dict) else {}
    intent = intent_map.get(task.get('owner_plan_intent') or requested.get('intent'))
    operation = params.get('operation')
    operation_map = {'component:chat': 'improve_chat_latency', 'component:memory': 'review_shared_memory',
        'component:training_stack': 'optimize_training', 'component:downloads': 'refresh_dependencies',
        'component:dispatcher': 'optimize_resources', 'component:storage': 'optimize_resources',
        'worker_config': 'optimize_resources', 'worker_verify': 'optimize_resources',
        'resource_budget': 'optimize_resources', 'training_inventory': 'review_checkpoint',
        'training_admission': 'optimize_training', 'training_progress': 'optimize_training',
        'download_admission': 'refresh_dependencies'}
    intent = intent or operation_map.get(operation)
    handler_map = {'start_qlora': 'optimize_training', 'merge_gated': 'review_checkpoint',
                  'identity': 'improve_model_quality', 'holdout_gate': 'improve_model_quality',
                  'ensure_downloads': 'refresh_dependencies', 'wait_q4': 'verify_native_result',
                  'verify_q4': 'verify_native_result', 'owner_component': 'audit_components',
                  'owner_plan_join': 'verify_native_result'}
    intent = intent or handler_map.get(task.get('handler'), 'review_authorized_task')
    job_id = params.get('job_id')
    if task.get('handler') == 'owner_media' and isinstance(job_id, str) and re.fullmatch(r'[0-9a-f]{32}', job_id):
        job = bounded_json(ROOT / 'state/media/jobs' / (job_id + '.json')) or {}
        kind = (job.get('request') or {}).get('kind')
        if kind in ('image', 'video'):
            intent = 'generate_' + kind
    measurements = {}
    for key in ('running', 'queued'):
        if type(plan.get(key)) is int and 0 <= plan[key] <= (6 if key == 'running' else 100000):
            measurements['active_workers' if key == 'running' else 'queued_tasks'] = plan[key]
    if type(memory.get('lexical_matches')) is int:
        measurements['retrieved_lexical_matches'] = memory['lexical_matches']
    try:
        quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota.isdigit() and period.isdigit() and int(period) > 0:
            measurements['cpu_quota_cores'] = int(quota) / int(period)
        for key, filename in (('memory_current_bytes', 'memory.current'), ('memory_max_bytes', 'memory.max')):
            text = (Path('/sys/fs/cgroup') / filename).read_text().strip()
            if text.isdigit():
                measurements[key] = int(text)
        measurements['shm_free_bytes'] = shutil.disk_usage('/dev/shm').free
    except (OSError, ValueError):
        pass
    heartbeat = ROOT / 'status/train_volta_t866u.json'
    hb = bounded_json(heartbeat, 16000)
    try:
        if (isinstance(hb, dict) and -5 <= time.time() - heartbeat.stat().st_mtime <= 90
                and type(hb.get('step')) is int and 0 <= hb['step'] <= 10**9):
            measurements['training_global_step'] = hb['step']
    except OSError:
        pass
    # The latest exact deployment receipt, only when accepted and recent. A
    # subsequent failed deployment prevents reuse of an older success timing.
    candidates = []
    try:
        for index, path in enumerate((ROOT / 'state').glob('owner_chat_upgrade_*.json')):
            if index >= 64:
                candidates = []; break
            if re.fullmatch(r'owner_chat_upgrade_[0-9]+\.json', path.name) and not path.is_symlink():
                candidates.append((path.stat().st_mtime, path))
        if candidates:
            stamp, path = max(candidates, key=lambda item: item[0])
            receipt = bounded_json(path, 1024 * 1024)
            accepted = {'LIVE_RESONANCE_REAL_STREAM_S03_HISTORY_ACCEPTED', 'LIVE_RESONANCE_FUNCTIONAL_PERFORMANCE_PENDING'}
            if isinstance(receipt, dict) and receipt.get('schema') == 'NOX_OWNER_CHAT_UPGRADE_V1' and receipt.get('state') in accepted and -5 <= time.time() - stamp <= 3600:
                for row in (receipt.get('acceptance') or [])[:100]:
                    if not isinstance(row, dict) or not isinstance(row.get('data'), dict):
                        continue
                    data = row['data']
                    mappings = ({'first_meaningful_delta_ms': 'chat_ttft_ms', 'total_ms': 'chat_total_ms'}
                                if row.get('kind') == 'chat_synthetic_latency' else
                                {'first_meaningful_delta_ms': 'chat_followup_ttft_ms'} if row.get('kind') == 'chat_history_followup' else {})
                    for field, key in mappings.items():
                        value = data.get(field)
                        if type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 3600000:
                            measurements[key] = value
    except OSError:
        pass
    targets = {'chat_ttft_ms': 8000, 'chat_followup_ttft_ms': 5000, 'chat_total_ms': 25000, 'global_worker_cap': 6}
    codes = set()
    error = str(task.get('note') or '')[:2000].lower()
    if 'bf16' in error and 'unscale' in error:
        codes.add('BF16_AMP_UNSCALE_UNSUPPORTED')
    if 'cuda' in error and 'out of memory' in error:
        codes.add('CUDA_OUT_OF_MEMORY')
    if any(measurements.get(key, 0) > targets[key] for key in ('chat_ttft_ms', 'chat_followup_ttft_ms')):
        codes.add('MODEL_TTFT_OVER_TARGET')
    if isinstance(task.get('result'), dict) and task['result'].get('accepted') is True and task['result'].get('verified') is not True:
        codes.add('ACCEPTED_WITHOUT_EXECUTION')
    return {'task_intent': intent, 'measurements': measurements, 'targets': targets,
            'public_error_codes': sorted(codes)}


def shared_context(task, local_recall, plan, gateway=None):
    parent = task.get('owner_parent_id')
    group = {'parent': parent, 'plan': task.get('owner_plan_id')} if parent else {
        'task': task.get('id'), 'handler': task.get('handler'), 'params_sha256': outbox.digest(task.get('params') or {})}
    # A new observed failure invalidates earlier advice for this plan. Sibling
    # checks still share their initial context instead of consulting per thread.
    # Siblings may reuse advice only for the SAME technical question. A shared
    # parent/plan alone previously leaked a sibling's handler, parameters or
    # failure note into another task's optimisation candidate.
    group['handler'] = outbox.safe_id(task.get('handler'))
    group['params_sha256'] = outbox.digest(task.get('params') or {})
    group['plan_intent'] = outbox.safe_code(task.get('owner_plan_intent'), 'NONE')
    group['note_sha256'] = hashlib.sha256(str(task.get('note') or '')[:2000].encode('utf-8')).hexdigest()
    group['retries'] = task.get('retries') if type(task.get('retries')) is int else 0
    group['incident'] = task.get('mentor_incident') if SHA.fullmatch(str(task.get('mentor_incident', ''))) else None
    key = outbox.digest(group)
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        transient = {'PENDING', 'RATE_LIMITED', 'SENIOR_CONSULTATION_UNAVAILABLE'}
        missing = {'MISSING_SENIOR_GATEWAY', 'MISSING_CREDENTIALS', 'UNVERIFIED_ACCESS', 'DISABLED'}
        senior_state = cached['value']['senior'].get('state') if cached else None
        ttl = 2 if senior_state in transient else (15 if senior_state in missing else CACHE_SECONDS)
        if cached and now - cached['at'] < ttl:
            return {**cached['value'], 'cache_reused': True, 'context_sha256': key}
    if not _CONTEXT_SLOT.acquire(blocking=False):
        return {'memory': {'state': 'S03_RECALL_BUSY'}, 'senior': {'state': 'SENIOR_CONTEXT_BUSY',
                'research_state': 'INTERNET_RESEARCH_NOT_VERIFIED'}, 'cache_reused': False, 'context_sha256': key}
    try:
        memory = semantic_recall(task)
        details = technical_details(task, local_recall, plan, memory)
        technical = {'schema': 'NOX_TASK_TECHNICAL_CONTEXT_V2',
                     'handler': outbox.safe_id(task.get('handler')),
                     'task_evidence_sha256': key,
                     'prior_verified_count': local_recall['verified'], 'prior_error_count': local_recall['errors'],
                     'error_categories': local_recall['error_categories'],
                     'mode': plan.get('mode', 'UNKNOWN'), 'global_worker_cap': 6,
                     'plan_policy': 'EXISTING_AUTHORIZED_NATIVE_HANDLER_WITH_RESOURCE_LOCKS',
                     'memory_text_included': False, **details}
        if cached and senior_state == 'PENDING' and isinstance(cached.get('technical'), dict):
            # Poll the same distinct provider work, not a new context made by
            # normal memory-usage changes during a two-second pending interval.
            technical = cached['technical']
        if gateway is None:
            senior = {'state': 'MISSING_SENIOR_GATEWAY', 'research_state': 'MISSING_INTERNET_RESEARCH_GATEWAY', 'models_consulted': 0}
        else:
            try:
                senior = _gateway_result(gateway.consult_plan(technical, deadline_seconds=2.0))
            except Exception:
                senior = {'state': 'SENIOR_CONSULTATION_UNAVAILABLE', 'research_state': 'INTERNET_RESEARCH_NOT_VERIFIED', 'models_consulted': 0}
        value = {'memory': memory, 'senior': senior, 'cache_reused': False, 'context_sha256': key,
                 'context_observed_at': now, 'technical_context': technical}
        with _CACHE_LOCK:
            if len(_CACHE) >= 128:
                oldest = min(_CACHE, key=lambda item: _CACHE[item]['at'])
                _CACHE.pop(oldest)
            _CACHE[key] = {'at': now, 'value': value, 'technical': technical}
        return value
    finally:
        _CONTEXT_SLOT.release()


def default_plan_metadata(task, state):
    mode = bounded_json(ROOT / 'state/task_boost_mode.json', 16000) or {}
    tasks = state.get('tasks') or {}
    running = sum(row.get('status') == 'running' for row in tasks.values() if isinstance(row, dict))
    return {'mode': 'TASK_BOOST' if mode.get('enabled') is True else 'NORMAL',
            'planned_branches': 1, 'admitted_width': 1, 'global_cap': 6,
            'running': running, 'queued': sum(row.get('status') in ('pending', 'wait', 'retry') for row in tasks.values() if isinstance(row, dict)),
            'reason': 'SINGLE_NATIVE_HANDLER_NO_REVIEWED_DECOMPOSITION', 'recursive_expansion': False}


def _plan_projection(value):
    value = value if isinstance(value, dict) else {}
    result = {'mode': outbox.safe_code(value.get('mode')), 'reason': outbox.safe_code(value.get('reason')),
              'global_cap': 6, 'recursive_expansion': False}
    for key in ('planned_branches', 'admitted_width', 'running', 'queued', 'new_admission_cap'):
        count = value.get(key)
        result[key] = count if type(count) is int and 0 <= count <= (100000 if key == 'queued' else 6) else None
    for key in ('plan_id', 'parent_id'):
        if value.get(key) is not None:
            result[key] = outbox.safe_id(value[key])
    if value.get('load_reason') is not None:
        result['load_reason'] = outbox.safe_code(value['load_reason'])
    return result


def preflight(task, state, mentor, plans=None, gateway=None):
    stopped = mentor.stop_active()
    plan = _plan_projection(plans.plan_metadata(task, state) if plans is not None else default_plan_metadata(task, state))
    local = journal_recall(task)
    context = ({'memory': {'state': 'NOT_CALLED_OWNER_STOP'}, 'senior': {'state': 'NOT_CALLED_OWNER_STOP',
                'research_state': 'NOT_CALLED_OWNER_STOP'}, 'cache_reused': False} if stopped else
               shared_context(task, local, plan, gateway))
    return {'schema': LIFECYCLE_SCHEMA, 'phase': 'PREFLIGHT', 'task_id': outbox.safe_id(task.get('id')),
            'handler': outbox.safe_id(task.get('handler')), 'claim': (task.get('owner_claim') or {}).get('nonce'),
            'at': time.time(), 'execution': 'BLOCKED_OWNER_STOP' if stopped else 'EXISTING_ADMISSION_REQUIRED',
            'journal_recall': local, 'shared_context': context, 'parallel_plan': plan,
            'optimization': {'state': 'APPROVED_NATIVE_PLAN_RETAINED', 'new_candidates': 'EVALUATION_REQUIRED',
                             'executes_advice': False, 'preserves_owner_constraints': True}}


def _lifecycle_summary(value):
    context = value.get('shared_context') or {}
    senior = context.get('senior') or {}
    return {'memory': (context.get('memory') or {}).get('state'), 'senior': senior.get('state'),
            'memory_retrieval': (context.get('memory') or {}).get('retrieval_kind'),
            'research': senior.get('research_state'), 'optimization': (value.get('optimization') or {}).get('state')}


def verify_media(runtime, task, evidence):
    """Recheck actual scoped files once at completion, never a heartbeat claim."""
    if not isinstance(evidence, dict) or evidence.get('generation_verified') is not True or evidence.get('state') != 'COMPLETED':
        return None
    job_id = (task.get('params') or {}).get('job_id')
    if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id) or evidence.get('id') != job_id:
        return None
    path = ROOT / 'state/media/jobs' / (job_id + '.json')
    job = bounded_json(path)
    if (not isinstance(job, dict) or job.get('schema') != 'NOX_OWNER_MEDIA_JOB_V1' or job.get('id') != job_id
            or job.get('state') != 'COMPLETED' or job.get('generation_verified') is not True):
        return None
    rows = job.get('outputs')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4:
        return None
    try:
        config = runtime.configuration()
        deadline = time.monotonic() + 2.0
        outputs = []
        for item in rows:
            candidate = runtime.output_path(config, job_id, item)
            before = candidate.stat()
            if before.st_size != item.get('bytes') or not SHA.fullmatch(str(item.get('sha256', ''))):
                return None
            h = hashlib.sha256()
            with candidate.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    if time.monotonic() > deadline:
                        return None
                    h.update(chunk)
            after = candidate.stat()
            if h.hexdigest() != item['sha256'] or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                return None
            outputs.append({key: item.get(key) for key in ('sha256', 'bytes', 'width', 'height', 'frames')})
        proof = {'kind': 'native_media_output', 'job_sha256': outbox.digest(job),
                 'media_kind': (job.get('request') or {}).get('kind'), 'outputs': outputs,
                 'gpu1_released': job.get('gpu1_released') is True, 'training_resume': job.get('training_resume')}
        return outbox.proof_projection(proof)
    except (OSError, ValueError, RuntimeError):
        return None


class Coordinator:
    def __init__(self, namespace, mentor, plans=None, gateway=None, media=None):
        self.namespace, self.mentor, self.plans, self.gateway, self.media = namespace, mentor, plans, gateway, media
        self._drain_lock = threading.Lock()
        self._last_drain = 0.0
        self._source = ROOT / 'memory/dispatcher_mentor/events.jsonl'
        self._cursor = ROOT / 'state/owner_events/journal_cursor.json'
        self._initialize_cursor()

    def _initialize_cursor(self):
        with outbox.locked():
            if self._cursor.exists():
                return
            try:
                if self._source.is_symlink():
                    raise LifecycleHold('HOLD_MENTOR_JOURNAL_SYMLINK')
                info = self._source.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise LifecycleHold('HOLD_MENTOR_JOURNAL_NOT_REGULAR')
                value = {'inode': info.st_ino, 'device': info.st_dev, 'offset': info.st_size}
            except FileNotFoundError:
                value = {'inode': None, 'device': None, 'offset': 0}
            # Activation does not replay old status checks as new work.
            outbox.atomic_json(self._cursor, {'schema': 'NOX_OWNER_JOURNAL_CURSOR_V1', **value})

    def _native_state_matches(self, task):
        current = bounded_json(self.namespace['STATE'], 16 * 1024 * 1024)
        row = (current.get('tasks') or {}).get(task.get('id')) if isinstance(current, dict) else None
        claim = task.get('owner_claim') or {}
        return (isinstance(row, dict) and row.get('status') == task.get('status')
                and isinstance(claim.get('nonce'), str) and re.fullmatch(r'[0-9a-f]{24}', claim['nonce'])
                and (row.get('owner_claim') or {}).get('nonce') == claim['nonce'])

    def _abandon_before_action(self, state, task, reason):
        # The task was already claimed by the native dispatcher; release exactly
        # those native locks if STOP/admission changed during bounded preflight.
        self.namespace['release_locks'](task)
        with self.namespace['_qlock']:
            task['status'] = 'blocked'
            task['note'] = reason
            self.namespace['save_state'](state)

    def _report(self, task, pre, row, raised=False):
        if not self._native_state_matches(task):
            self.mentor.journal('owner_task_report', report={'schema': outbox.REPORT_SCHEMA,
                'kind': 'verification_pending', 'persisted': True, 'queue_state_verified': False,
                'state': 'DISPATCHER_STATE_NOT_VERIFIED', 'verification': None,
                'task': {'id': task.get('id'), 'handler': task.get('handler'), 'claim': (task.get('owner_claim') or {}).get('nonce')},
                'lifecycle': _lifecycle_summary(pre), 'learning': 'QUARANTINED_OR_UNAVAILABLE'}, accepted=False)
            return
        proof = outbox.proof_projection((row or {}).get('verification'))
        final_status = task.get('status')
        resolution = task.get('mentor') if isinstance(task.get('mentor'), dict) else {}
        if final_status == 'done':
            kind = 'task_verified' if proof else 'verification_pending'
            result = 'VERIFIED_WITHIN_SCOPE' if proof else 'DONE_REPORTED_VERIFICATION_MISSING'
        elif final_status in ('blocked', 'failed') or raised or resolution:
            kind, result = 'task_failed', resolution.get('state') or 'NATIVE_TASK_FAILED'
        else:
            # A resource wait or idle duty cycle is not progress or completion.
            self.mentor.journal('owner_task_waiting', task_id=outbox.safe_id(task.get('id')),
                                state='WAITING_WITHOUT_COMPLETION_CLAIM', accepted=False)
            return
        learning = ('VERIFIED_TRAIN' if row.get('partition') == 'train' else 'VERIFIED_HOLDOUT') if proof and row else 'QUARANTINED_OR_UNAVAILABLE'
        report = {'schema': outbox.REPORT_SCHEMA, 'kind': kind, 'persisted': True,
                  'task': {'id': task.get('id'), 'handler': task.get('handler'), 'claim': (task.get('owner_claim') or {}).get('nonce')},
                  'state': outbox.safe_code(result), 'verification': proof,
                  'learning': learning, 'lifecycle': _lifecycle_summary(pre)}
        self.mentor.journal('owner_task_report', report=report, accepted=False)
        if resolution.get('verified_fix') is True:
            self.mentor.journal('owner_task_report', report={**report, 'kind': 'repair_verified',
                'state': 'REPAIR_VERIFIED_ORIGINAL_TASK_PENDING', 'repair': resolution.get('verification')}, accepted=False)

    def run(self, original, state, task):
        try:
            with self.namespace['_qlock']:
                snapshot = {'tasks': {key: copy.deepcopy({name: value for name, value in row.items() if not name.startswith('_')})
                                      for key, row in (state.get('tasks') or {}).items()}}
            pre = preflight(task, snapshot, self.mentor, self.plans, self.gateway)
            self.mentor.journal('owner_task_preflight', lifecycle=pre, task_id=pre['task_id'],
                                handler=pre['handler'], accepted=False)
        except Exception:
            self._abandon_before_action(state, task, 'HOLD_DURABLE_PREFLIGHT_UNAVAILABLE')
            return None
        if self.mentor.stop_active() or not self.namespace['_nox_owner_task_admitted'](task):
            self._abandon_before_action(state, task, 'HOLD_OWNER_STOP_OR_NATIVE_ADMISSION')
            self.mentor.journal('owner_task_report', report={'schema': outbox.REPORT_SCHEMA,
                'kind': 'task_blocked', 'persisted': self._native_state_matches(task), 'state': 'OWNER_STOP_OR_NATIVE_ADMISSION',
                'task': {'id': task.get('id'), 'handler': task.get('handler'), 'claim': (task.get('owner_claim') or {}).get('nonce')},
                'lifecycle': _lifecycle_summary(pre)}, accepted=False)
            self.drain(force=True)
            return None
        previous = getattr(_LOCAL, 'context', None)
        context = {'task_id': task.get('id'), 'claim': (task.get('owner_claim') or {}).get('nonce'), 'experience': None,
                   'task': {'id': task.get('id'), 'handler': task.get('handler'), 'claim': (task.get('owner_claim') or {}).get('nonce')},
                   'lifecycle': _lifecycle_summary(pre)}
        _LOCAL.context = context
        raised = False
        try:
            return original(state, task)
        except BaseException:
            raised = True
            raise
        finally:
            _LOCAL.context = previous
            try:
                self._report(task, pre, context['experience'] or {}, raised)
                self.drain(force=True)
            except Exception as exc:
                # Reporting failure cannot replay, cancel or mark work complete.
                self.namespace['ev']('owner_report_deferred', task=outbox.safe_id(task.get('id')), error=type(exc).__name__)

    def drain(self, force=False):
        now = time.monotonic()
        if (not force and now - self._last_drain < 5) or not self._drain_lock.acquire(blocking=False):
            return
        try:
            self._last_drain = now
            cursor = bounded_json(self._cursor, 16000)
            if not isinstance(cursor, dict) or cursor.get('schema') != 'NOX_OWNER_JOURNAL_CURSOR_V1':
                raise LifecycleHold('HOLD_JOURNAL_CURSOR')
            fd = os.open(self._source, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise LifecycleHold('HOLD_MENTOR_JOURNAL_NOT_REGULAR')
                offset = cursor.get('offset')
                if type(offset) is not int or offset < 0:
                    raise LifecycleHold('HOLD_JOURNAL_OFFSET')
                discarding = cursor.get('discarding') is True
                if cursor.get('inode') not in (None, info.st_ino) or cursor.get('device') not in (None, info.st_dev) or offset > info.st_size:
                    offset = 0
                    discarding = False
                stream.seek(offset)
                remaining = 262144
                for _ in range(64):
                    before = stream.tell()
                    line = stream.readline(min(32769, remaining + 1))
                    if not line:
                        break
                    remaining -= len(line)
                    if remaining < 0:
                        break
                    if discarding:
                        offset = stream.tell()
                        discarding = not line.endswith(b'\n')
                        continue
                    if not line.endswith(b'\n'):
                        if len(line) >= 32769:
                            # Skip an oversized unrelated native record in
                            # bounded chunks; it must not starve later reports.
                            discarding = True
                            offset = stream.tell()
                            continue
                        break  # A short unfinished append may finish next tick.
                    try:
                        record = json.loads(line)
                    except (ValueError, UnicodeError):
                        offset = stream.tell(); continue
                    if isinstance(record, dict) and record.get('schema') == 'NOX_DISPATCHER_MENTOR_V1' and record.get('kind') == 'owner_task_report':
                        report = record.get('report')
                        if isinstance(report, dict):
                            report = {**report, 'journal_sha256': hashlib.sha256(line).hexdigest()}
                            try:
                                outbox.publish(report)
                            except outbox.OutboxHold:
                                # Malformed proof remains in the source journal.
                                pass
                            except (OSError, ValueError):
                                offset = before
                                break
                    offset = stream.tell()
                updated = {'schema': 'NOX_OWNER_JOURNAL_CURSOR_V1', 'inode': info.st_ino,
                           'device': info.st_dev, 'offset': offset, 'discarding': discarding}
            outbox.atomic_json(self._cursor, updated)
        except FileNotFoundError:
            return
        finally:
            self._drain_lock.release()


def _checked_module(namespace, name, expected, required=False):
    module = namespace.get(name)
    if module is None and name == 'owner_mentor':
        raise LifecycleHold('HOLD_EXISTING_MENTOR_REQUIRED')
    if module is None:
        if required:
            path = ROOT / 'scripts' / (name + '.py')
            if not isinstance(expected, str) or not SHA.fullmatch(expected) or file_sha(path) != expected:
                raise LifecycleHold('HOLD_LIFECYCLE_MODULE_SOURCE_' + name)
            # Execute the exact checked bytes, not a search-path import that
            # could run an unrelated module before the hash check.
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                    raise LifecycleHold('HOLD_LIFECYCLE_MODULE_SOURCE_' + name)
                source = stream.read(1024 * 1024 + 1)
            if hashlib.sha256(source).hexdigest() != expected:
                raise LifecycleHold('HOLD_LIFECYCLE_MODULE_SOURCE_' + name)
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            previous = sys.modules.get(name)
            try:
                sys.modules[name] = module
                exec(compile(source, str(path), 'exec'), module.__dict__)
                if Path(module.__file__) != path or file_sha(path) != expected:
                    raise LifecycleHold('HOLD_LIFECYCLE_MODULE_SOURCE_' + name)
            except BaseException:
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
                raise
            namespace[name] = module
        else:
            return None
    path = getattr(module, '__file__', None)
    if not isinstance(expected, str) or not SHA.fullmatch(expected) or not path or file_sha(path) != expected:
        raise LifecycleHold('HOLD_LIFECYCLE_MODULE_SOURCE_' + name)
    return module


def bind_dispatcher(namespace, source_pins):
    if namespace.get('_owner_lifecycle_bound'):
        return
    required = ('run_one', 'write_status', 'save_state', 'release_locks', '_nox_owner_task_admitted', 'ev')
    if any(not callable(namespace.get(name)) for name in required) or '_qlock' not in namespace or 'STATE' not in namespace or namespace.get('WORKERS') != 6:
        raise LifecycleHold('HOLD_LIFECYCLE_NATIVE_CALLBACKS')
    if file_sha(outbox.__file__) != source_pins.get('owner_event_outbox'):
        raise LifecycleHold('HOLD_LIFECYCLE_OUTBOX_SOURCE')
    mentor = _checked_module(namespace, 'owner_mentor', source_pins.get('owner_mentor'))
    for name in ('owner_task_plans', 'owner_media_runtime', 'owner_s03_gateway'):
        if name in source_pins and namespace.get(name) is None:
            raise LifecycleHold('HOLD_EXISTING_BINDING_REQUIRED_' + name)
    plans = _checked_module(namespace, 'owner_task_plans', source_pins.get('owner_task_plans'))
    media = _checked_module(namespace, 'owner_media_runtime', source_pins.get('owner_media_runtime'))
    memory = _checked_module(namespace, 'owner_s03_gateway', source_pins.get('owner_s03_gateway'))
    gateway = _checked_module(namespace, 'owner_senior_gateway', source_pins.get('owner_senior_gateway'),
                              required='owner_senior_gateway' in source_pins)
    if plans is not None and not callable(getattr(plans, 'plan_metadata', None)):
        raise LifecycleHold('HOLD_LIFECYCLE_PLAN_INTERFACE')
    if gateway is not None and not callable(getattr(gateway, 'consult_plan', None)):
        raise LifecycleHold('HOLD_LIFECYCLE_SENIOR_INTERFACE')
    if memory is not None and not callable(getattr(memory, 'verify_success', None)):
        raise LifecycleHold('HOLD_LIFECYCLE_S03_INDEX_INTERFACE')
    coordinator = Coordinator(namespace, mentor, plans, gateway, media)
    original_experience = mentor.record_experience
    original_verify = mentor.verify_success
    def verify(task, evidence=None):
        value = original_verify(task, evidence)
        if value is None and plans is not None and callable(getattr(plans, 'verify_success', None)):
            value = plans.verify_success(task, evidence)
        if value is None and media is not None and task.get('handler') == 'owner_media':
            return verify_media(media, task, evidence)
        if value is None and memory is not None and task.get('handler') == 'owner_memory_sync':
            return memory.verify_success(task, evidence)
        return value
    def experience(*args, **kwargs):
        value = original_experience(*args, **kwargs)
        context = getattr(_LOCAL, 'context', None)
        task = args[1] if len(args) > 1 else kwargs.get('task')
        if context and isinstance(task, dict) and task.get('id') == context['task_id'] and (task.get('owner_claim') or {}).get('nonce') == context['claim']:
            context['experience'] = value
        return value
    mentor.verify_success = verify
    mentor.record_experience = experience
    if media is not None:
        original_update = media.update_job
        def update_job(job, **fields):
            previous_state = job.get('state')
            result = original_update(job, **fields)
            context = getattr(_LOCAL, 'context', None)
            if (context and context['task'].get('handler') == 'owner_media' and previous_state != 'RUNNING'
                    and job.get('state') == 'RUNNING' and context['task_id'] == 'owner.media.' + str(job.get('id'))
                    and isinstance(job.get('prompt_id'), str) and re.fullmatch(r'[A-Za-z0-9-]{16,80}', job['prompt_id'])):
                # Actual persisted prompt acceptance is useful progress, but is
                # not a claim that generation or output verification finished.
                try:
                    persisted = bounded_json(ROOT / 'state/media/jobs' / (job['id'] + '.json'))
                    if isinstance(persisted, dict) and persisted.get('prompt_id') == job['prompt_id'] and persisted.get('state') == 'RUNNING':
                        mentor.journal('owner_task_report', report={'schema': outbox.REPORT_SCHEMA,
                            'kind': 'task_progress', 'persisted': True, 'state': 'GENERATION_SUBMITTED',
                            'task': context['task'], 'lifecycle': context['lifecycle'],
                            'progress': {'metric': 'generation_submitted', 'current': 1, 'total': 1,
                                         'evidence_sha256': outbox.digest(persisted)}}, accepted=False)
                        coordinator.drain(force=True)
                except Exception as exc:
                    namespace['ev']('owner_progress_deferred', error=type(exc).__name__)
            return result
        media.update_job = update_job
    original_run, original_status = namespace['run_one'], namespace['write_status']
    def run(state, task):
        return coordinator.run(original_run, state, task)
    def status(state):
        value = original_status(state)
        try:
            coordinator.drain()
        except Exception as exc:
            namespace['ev']('owner_event_drain_deferred', error=type(exc).__name__)
        return value
    namespace['run_one'], namespace['write_status'] = run, status
    namespace['_owner_lifecycle_coordinator'] = coordinator
    namespace['_owner_lifecycle_bound'] = True


def patch_dispatcher(source, expected_sha256, source_pins):
    if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256) or hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise LifecycleHold('HOLD_NATIVE_DISPATCHER_SOURCE_CHANGED')
    if not isinstance(source_pins, dict) or any(not isinstance(value, str) or not SHA.fullmatch(value) for value in source_pins.values()):
        raise LifecycleHold('HOLD_LIFECYCLE_ASSET_PINS')
    if not {'owner_mentor', 'owner_event_outbox'} <= set(source_pins):
        raise LifecycleHold('HOLD_LIFECYCLE_REQUIRED_PINS')
    if PATCH_MARKER in source:
        calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'owner_task_lifecycle' and node.func.attr == 'bind_dispatcher']
        if len(calls) != 1 or len(calls[0].args) != 2 or ast.literal_eval(calls[0].args[1]) != source_pins:
            raise LifecycleHold('HOLD_LIFECYCLE_BOUND_PINS_CHANGED')
        compile(source, '<dispatcher-owner-lifecycle>', 'exec')
        return source
    tree = ast.parse(source)
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not {'run_one', 'write_status', 'owner_claim_ready', '_nox_owner_task_admitted'} <= functions:
        raise LifecycleHold('HOLD_LIFECYCLE_NATIVE_CONTRACT')
    anchor = 'if __name__ == "__main__":'
    if source.count(anchor) != 1:
        raise LifecycleHold('HOLD_LIFECYCLE_MAIN_ANCHOR')
    addition = ('# ' + PATCH_MARKER + '\nimport owner_task_lifecycle\n'
                'owner_task_lifecycle.bind_dispatcher(globals(), ' + repr(source_pins) + ')\n\n')
    updated = source.replace(anchor, addition + anchor, 1)
    compile(updated, '<dispatcher-owner-lifecycle>', 'exec')
    return updated
