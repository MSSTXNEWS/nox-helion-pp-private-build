#!/usr/bin/env python3
"""Bounded, idle-gated NOX inference capacity measurement; no service mutations.

This measures useful concurrent requests to the existing model, not the number
of sleeping agents, CPU jobs, or a sustained maximum for every future workload.
Only public fixture prompts are submitted. Nothing from live chat is exported.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path('/root/nox')
CGROUP = Path('/sys/fs/cgroup')
BASE = 'http://127.0.0.1:8081'
MODEL_PORTS = (8081, 8098)
STOP_PATHS = tuple(map(Path, ('/root/nox/STOP', '/root/nox/STOP.flag',
    '/root/nox/stop.flag', '/root/nox/.stop', '/root/nox/program/STOP', '/workspace/NOX_STOP')))
HEAVY_SERVICES = ('nox-train-volta-t866u', 'nox-teacher-serve-t811u',
    'nox-distill-worm-t811u', 'nox-self-improve-t846u', 'nox-self-learning-loop',
    'nox-autoscale-t877u')
TRAIN_SCRIPT_NAMES = {'train_qlora_35b_t866u.py', 'hybrid_training_entry.py',
                      'owner_hybrid_training_entry.py'}
FIXTURES = (
    ('ports', 'Return only a JSON object with these exact fields: chat=8080, engine=8081, embeddings=8082.',
     {'chat': 8080, 'engine': 8081, 'embeddings': 8082}),
    ('sort', 'Return only the JSON array containing these numbers sorted in ascending order: 9, 1, 4, 1, 7, 3.',
     [1, 1, 3, 4, 7, 9]),
    ('budget', 'GPU memory budget is 32 GiB. The model uses 21 GiB and 3 GiB must remain reserved. Return only the integer available for other work.', 8),
    ('code', 'Fix this Python function to add its arguments. Return only the corrected code on one line: def add(a, b): return a - b',
     'def add(a,b): return a+b'),
    ('slots', 'A model has 6 parallel slots. Reserve 1 slot for foreground chat. Return only the maximum integer count of background requests in service.', 5),
    ('status', 'Extract fields from this public sample. Return only JSON with exactly the keys service, port, state. Sample: service=chat port=8080 state=ready.',
     {'service': 'chat', 'port': 8080, 'state': 'ready'}),
)


class Hold(RuntimeError):
    pass


def read_text(path, limit=65536):
    try:
        with Path(path).open('rb') as handle:
            data = handle.read(limit + 1)
        return data.decode('utf-8', 'strict') if len(data) <= limit else None
    except (OSError, UnicodeError):
        return None


def read_json(path):
    try:
        return json.loads(read_text(path) or 'null')
    except ValueError:
        return None


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=4)
        return result.returncode, result.stdout[:30000]
    except (OSError, subprocess.TimeoutExpired):
        return 99, ''


def model_base(port):
    """An explicit local model target; never discover or probe unrelated ports."""
    if type(port) is not int or port not in MODEL_PORTS:
        raise Hold('MODEL_PORT_SCOPE')
    return 'http://127.0.0.1:' + str(port)


def get(path, base=BASE):
    try:
        with urllib.request.urlopen(base + path, timeout=2) as response:
            data = response.read(262145)
        if len(data) > 262144:
            raise Hold('HTTP_RESPONSE_TOO_LARGE')
        return json.loads(data)
    except (OSError, ValueError) as exc:
        raise Hold('READ_ONLY_HTTP_' + type(exc).__name__) from None


def stop_active():
    return any(path.exists() or path.is_symlink() for path in STOP_PATHS)


def slot_summary(items):
    """Never copy a slot's prompt, tokens, history, or other chat content."""
    if not isinstance(items, list) or not items or len(items) > 128:
        raise Hold('SLOTS_UNVERIFIED')
    busy = 0
    for item in items:
        if not isinstance(item, dict):
            raise Hold('SLOTS_UNVERIFIED')
        states = [item[key] for key in ('is_processing', 'processing') if key in item]
        if not states or any(type(value) is not bool for value in states) or len(set(states)) != 1:
            raise Hold('SLOTS_UNVERIFIED')
        busy += states[0]
    return {'slots': len(items), 'busy': busy}


def idle_gate(base=BASE):
    if stop_active():
        raise Hold('OWNER_STOP')
    result = slot_summary(get('/slots', base))
    if result['busy']:
        raise Hold('CHAT_BUSY')
    return result


def numbers(path):
    result = {}
    for line in (read_text(path, 4096) or '').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            result[parts[0]] = int(parts[1])
    return result


def finite_limit(name):
    value = (read_text(CGROUP / name, 100) or '').strip()
    return int(value) if value.isdigit() else None


def resources():
    quota = (read_text(CGROUP / 'cpu.max', 100) or '').split()
    cpu = int(quota[0]) / int(quota[1]) if len(quota) == 2 and quota[0].isdigit() and quota[1].isdigit() and int(quota[1]) else None
    return {'at_monotonic': time.monotonic(), 'cpu_quota_cores': cpu,
            'memory_current': finite_limit('memory.current'), 'memory_max': finite_limit('memory.max'),
            'memory_high': finite_limit('memory.high'), 'memory_events': numbers(CGROUP / 'memory.events'),
            'cpu_stat': numbers(CGROUP / 'cpu.stat')}


def resource_gate(current, baseline=None):
    limits = [current.get(key) for key in ('memory_max', 'memory_high') if current.get(key)]
    used = current.get('memory_current')
    if not limits or used is None or not current.get('cpu_quota_cores'):
        raise Hold('CGROUP_BUDGET_UNVERIFIED')
    if used >= min(limits) * 0.92:
        raise Hold('MEMORY_HEADROOM_BELOW_8_PERCENT')
    if baseline:
        for key in ('oom', 'oom_kill', 'max'):
            if current['memory_events'].get(key, 0) > baseline['memory_events'].get(key, 0):
                raise Hold('MEMORY_PRESSURE_' + key.upper())


def gpu_snapshot():
    rc, output = run(['nvidia-smi', '--query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'])
    rows = []
    if rc == 0:
        for line in output.splitlines():
            fields = [part.strip() for part in line.split(',')]
            if len(fields) == 5 and all(value.isdigit() for value in fields):
                rows.append(dict(zip(('index', 'total_mib', 'used_mib', 'free_mib', 'utilization_percent'), map(int, fields))))
    return {'query_rc': rc, 'gpus': rows, 'sampling': 'boundary_snapshots_only'}


def process_evidence():
    """Read argument identity only, never process environments or arbitrary args."""
    rows = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().decode('utf-8', 'replace').strip('\0').split('\0')
            if not argv or not argv[0]:
                continue
            script_names = {Path(value).name for value in argv[1:4] if value.endswith('.py')}
            stat = (entry / 'stat').read_text().split(') ', 1)[1].split()
            if stat[0] in ('Z', 'X'):
                continue
            if script_names & TRAIN_SCRIPT_NAMES:
                rows.append({'pid': int(entry.name), 'kind': 'trainer', 'identity': sorted(script_names & TRAIN_SCRIPT_NAMES), 'start_ticks': stat[19]})
            if Path(argv[0]).name != 'llama-server':
                continue
            options = {key: argv[i + 1] for i, key in enumerate(argv[:-1]) if key in ('-m', '--model', '--port', '-np', '--parallel')}
            model = options.get('-m', options.get('--model', ''))
            if not model.startswith('/root/nox/models/'):
                continue
            kind = 'teacher_or_judge' if ('/teachers/' in model or '/judge/' in model) else 'model_service'
            rows.append({'pid': int(entry.name), 'kind': kind, 'model_basename': Path(model).name,
                         'model_path': model,
                         'port': options.get('--port'), 'parallel': options.get('-np', options.get('--parallel')), 'start_ticks': stat[19]})
        except (OSError, ValueError, IndexError):
            continue
    return rows


def native_model_identity(model, port, processes):
    """Bind a model API ID to the one observed native process on that port."""
    model_base(port)
    rows = [row for row in processes if row.get('port') == str(port)]
    if len(rows) != 1:
        raise Hold('MODEL_PROCESS_UNVERIFIED')
    row = rows[0]
    path = row.get('model_path')
    if (row.get('kind') != 'model_service' or type(row.get('pid')) is not int
            or row['pid'] <= 0 or not str(row.get('start_ticks', '')).isdigit()
            or int(row['start_ticks']) <= 0 or not isinstance(path, str)
            or not path.startswith('/root/nox/models/') or '..' in Path(path).parts
            or not path.endswith('.gguf') or model != path):
        raise Hold('CURRENT_NOX_MODEL_UNVERIFIED')
    return {key: row[key] for key in ('pid', 'start_ticks', 'port', 'model_path')}


def profile_evidence(mode):
    rc, output = run(['supervisorctl', 'status'])
    services = {}
    for line in output.splitlines():
        match = re.match(r'^([A-Za-z0-9_.:-]+)\s+([A-Z]+)(?:\s+pid\s+(\d+))?', line)
        if match:
            services[match[1]] = {'state': match[2], 'pid': int(match[3]) if match[3] else None}
    heartbeats = []
    for name in ('train_volta_t866u.json', 'train_heartbeat_t811u.json'):
        path = ROOT / 'status' / name
        value = read_json(path)
        if isinstance(value, dict):
            heartbeats.append({'path': str(path), 'age_sec': round(time.time() - path.stat().st_mtime, 2),
                               **{key: value.get(key) for key in ('phase', 'step', 'loss', 'successful_optimizer_steps')}})
    processes = process_evidence()
    reasons = []
    if not services or rc not in (0, 3):
        reasons.append('SUPERVISOR_UNVERIFIED')
    trainers = [row for row in processes if row['kind'] == 'trainer']
    if mode == 'NORMAL':
        if services.get('nox-train-volta-t866u', {}).get('state') != 'RUNNING' or not trainers:
            reasons.append('TRAINER_NOT_RUNNING')
        if not any(row.get('phase') == 'train_owner_hybrid' and type(row.get('step')) is int and row['step'] > 0 and row['age_sec'] < 600 for row in heartbeats):
            reasons.append('NO_FRESH_POSITIVE_STEP_HEARTBEAT')
    else:
        active = [name for name in HEAVY_SERVICES if services.get(name, {}).get('state') not in (None, 'STOPPED', 'EXITED', 'FATAL')]
        if active:
            reasons.append('HEAVY_SERVICES_ACTIVE:' + ','.join(active))
        if trainers or any(row['kind'] == 'teacher_or_judge' for row in processes):
            reasons.append('HEAVY_MODEL_PROCESSES_REMAIN')
        if not (ROOT / 'state/TRAIN_HOLD.flag').exists():
            reasons.append('TRAINING_HOLD_NOT_PRESENT')
    return {'requested_mode': mode, 'verified': not reasons, 'reasons': reasons,
            'services': services, 'processes': processes, 'heartbeats': heartbeats,
            'scope': 'known NOX trainer, improvement services and teacher/judge model processes'}


def source_proof():
    result = {}
    for label, path in (('probe', Path(__file__)), ('dispatcher', ROOT / 'scripts/nox_dispatcher_t855u.py'),
                        ('dispatcher_config', ROOT / 'config/dispatcher_agents_t868u.json')):
        text = read_text(path, 200000)
        if text is not None:
            result[label] = {'path': str(path), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    current = ROOT / 'models/current.gguf'
    try:
        result['model'] = {'path': str(current), 'resolved_basename': current.resolve().name,
                           'size': current.stat().st_size, 'mtime_ns': current.stat().st_mtime_ns}
    except OSError:
        result['model'] = None
    return result


def validate_content(index, content):
    expected = FIXTURES[index % len(FIXTURES)][2]
    clean = content.strip()
    if clean.startswith('```') and clean.endswith('```'):
        clean = re.sub(r'^```(?:python|json)?\s*', '', clean)[:-3].strip()
    if isinstance(expected, str):
        return re.sub(r'\s+', '', clean) == re.sub(r'\s+', '', expected)
    try:
        actual = json.loads(clean)
        return type(actual) is type(expected) and actual == expected
    except ValueError:
        return False


def infer(model, index, cancel, deadline, usage=True, base=BASE):
    prompt = FIXTURES[index % len(FIXTURES)][1]
    request = {'model': model, 'stream': True, 'temperature': 0, 'max_tokens': 48,
               'cache_prompt': False, 'chat_template_kwargs': {'enable_thinking': False},
               'messages': [{'role': 'user', 'content': prompt}]}
    if usage:
        request['stream_options'] = {'include_usage': True}
    start = time.monotonic()
    first = None
    content = ''
    tokens = None
    finish = None
    done = False
    reasoning = False
    row = {'fixture': FIXTURES[index % len(FIXTURES)][0], 'state': 'INCOMPLETE'}
    try:
        if cancel.is_set() or stop_active() or start >= deadline:
            raise Hold('CANCELLED')
        req = urllib.request.Request(base + '/v1/chat/completions',
            data=json.dumps(request).encode(), headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'}, method='POST')
        with urllib.request.urlopen(req, timeout=min(8, max(0.1, deadline - start))) as response:
            while True:
                if cancel.is_set() or stop_active() or time.monotonic() > deadline or time.monotonic() - start > 12:
                    raise Hold('REQUEST_DEADLINE_OR_STOP')
                raw = response.readline(16001)
                if not raw:
                    break
                if len(raw) > 16000:
                    raise Hold('SSE_OVERSIZE')
                line = raw.decode('utf-8', 'strict').strip()
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    done = True
                    break
                obj = json.loads(payload)
                if not isinstance(obj, dict) or obj.get('error') is not None:
                    raise Hold('SSE_ERROR_OR_NONOBJECT')
                native_usage = obj.get('usage')
                if isinstance(native_usage, dict):
                    count = native_usage.get('completion_tokens')
                    if type(count) is int and 0 < count <= 48:
                        tokens = count
                choices = obj.get('choices', [])
                if not isinstance(choices, list) or len(choices) > 1:
                    raise Hold('SSE_CHOICES')
                for choice in choices:
                    if not isinstance(choice, dict) or not isinstance(choice.get('delta', {}), dict):
                        raise Hold('SSE_DELTA')
                    delta = choice.get('delta', {})
                    chunk = delta.get('content', '')
                    if chunk is not None and not isinstance(chunk, str):
                        raise Hold('SSE_CONTENT')
                    if chunk:
                        first = first or time.monotonic()
                        content += chunk
                        if len(content) > 16000:
                            raise Hold('CONTENT_OVERSIZE')
                    reasoning |= bool(delta.get('reasoning_content') or delta.get('reasoning'))
                    finish = choice.get('finish_reason') or finish
        valid = done and finish in ('stop', 'eos_token') and first is not None and validate_content(index, content)
        row.update(state='PASSED' if valid else 'INVALID_OR_INCOMPLETE', stream_done=done,
                   finish_reason=finish, task_valid=bool(valid), reasoning_observed=reasoning,
                   completion_tokens=tokens, token_source='native_stream_usage' if tokens is not None else 'unavailable',
                   public_fixture_response=content[:500])
    except urllib.error.HTTPError as exc:
        row['state'] = 'HTTP_' + str(exc.code)
    except (Hold, OSError, ValueError, UnicodeError) as exc:
        row['state'] = str(exc) if isinstance(exc, Hold) else type(exc).__name__
    row['ttft_ms'] = round((first - start) * 1000, 3) if first else None
    row['total_ms'] = round((time.monotonic() - start) * 1000, 3)
    return row


def percentile(values, fraction):
    values = sorted(value for value in values if value is not None)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def burst(model, concurrency, samples, deadline, usage, base=BASE):
    idle_gate(base)
    before = resources()
    resource_gate(before)
    sampled = [before]
    cancel = threading.Event()
    rows = []
    failure = None
    start = time.monotonic()
    last_slot_check = start
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = {pool.submit(infer, model, i, cancel, deadline, usage, base) for i in range(samples)}
        while pending:
            finished, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            rows.extend(future.result() for future in finished if not future.cancelled())
            sample = resources()
            sampled.append(sample)
            try:
                resource_gate(sample, before)
                if stop_active() or time.monotonic() >= deadline:
                    raise Hold('OWNER_STOP_OR_PROBE_DEADLINE')
                if pending and time.monotonic() - last_slot_check >= 1:
                    # A spare slot can reveal newly arrived foreground traffic.
                    # This does not pretend to identify requests by private data.
                    last_slot_check = time.monotonic()
                    if slot_summary(get('/slots', base))['busy'] > concurrency:
                        raise Hold('FOREGROUND_TRAFFIC_OBSERVED')
            except Hold as exc:
                failure = str(exc)
                cancel.set()
                for future in pending:
                    future.cancel()
    elapsed = time.monotonic() - start
    after = sampled[-1]
    cpu_seconds = (after['cpu_stat'].get('usage_usec', 0) - before['cpu_stat'].get('usage_usec', 0)) / 1e6
    passed = [row for row in rows if row['state'] == 'PASSED']
    streamed = [row for row in rows if row.get('stream_done') is True
                and row.get('finish_reason') in ('stop', 'eos_token') and row.get('ttft_ms') is not None]
    state = 'PASSED' if len(passed) == samples and not failure else (
        'QUALITY_FAILED' if len(streamed) == samples and not failure else 'FAILED')
    exact_tokens = sum(row['completion_tokens'] for row in rows) if len(rows) == samples and all(type(row.get('completion_tokens')) is int for row in rows) else None
    return {'concurrency': concurrency, 'samples': samples, 'completed_samples': len(rows),
            'passed': len(passed), 'native_streams_completed': len(streamed), 'state': state,
            'hold_reason': failure, 'elapsed_sec': round(elapsed, 4),
            'useful_tasks_per_sec': round(len(passed) / elapsed, 4),
            'completion_tokens_per_sec': round(exact_tokens / elapsed, 3) if exact_tokens is not None else None,
            'completion_tokens': exact_tokens, 'p50_ttft_ms': percentile([row['ttft_ms'] for row in rows], 0.5),
            'p95_ttft_ms': percentile([row['ttft_ms'] for row in rows], 0.95),
            'p95_total_ms': percentile([row['total_ms'] for row in rows], 0.95),
            'cpu_quota_utilization_percent': round(100 * cpu_seconds / elapsed / before['cpu_quota_cores'], 2),
            'peak_sampled_memory_bytes': max(row['memory_current'] for row in sampled),
            'memory_events_delta': {key: after['memory_events'].get(key, 0) - before['memory_events'].get(key, 0) for key in ('high', 'max', 'oom', 'oom_kill')},
            'results': rows}


def recommend(rows, max_ttft_ms, max_total_ms):
    passing = [row for row in rows if row['state'] == 'PASSED'
               and row['p95_ttft_ms'] is not None and row['p95_ttft_ms'] <= max_ttft_ms
               and row['p95_total_ms'] is not None and row['p95_total_ms'] <= max_total_ms]
    if not passing:
        return {'best_measured_concurrency': None, 'largest_passing_tested_concurrency': None}
    best = max(passing, key=lambda row: row['useful_tasks_per_sec'])
    # A smaller configuration within 5% of the best leaves more room for chat.
    efficient = min((row for row in passing if row['useful_tasks_per_sec'] >= 0.95 * best['useful_tasks_per_sec']), key=lambda row: row['concurrency'])
    return {'best_measured_concurrency': best['concurrency'],
            'recommended_concurrency': efficient['concurrency'],
            'largest_passing_tested_concurrency': max(row['concurrency'] for row in passing),
            'best_useful_tasks_per_sec': best['useful_tasks_per_sec']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('NORMAL', 'TASK_BOOST'), required=True)
    parser.add_argument('--reserve-slots', type=int, default=1, choices=(0, 1))
    parser.add_argument('--samples', type=int, default=12, choices=(6, 12))
    parser.add_argument('--deadline-sec', type=int, default=105, choices=range(30, 111))
    parser.add_argument('--max-ttft-ms', type=int, default=3000)
    parser.add_argument('--max-total-ms', type=int, default=12000)
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--model-port', type=int, choices=MODEL_PORTS, default=8081,
                        help='Existing local model service; use 8098 for the current DeepSeek service.')
    args = parser.parse_args(argv)
    base = model_base(args.model_port)
    deadline = time.monotonic() + args.deadline_sec
    result = {'schema': 'NOX_OWNER_CAPACITY_V1', 'requested_mode': args.mode,
              'recorded_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'source': source_proof(),
              'scope': 'short public tasks on the existing model; CPU/IO executor ceiling is not measured',
              'profile_before': profile_evidence(args.mode), 'resources_before': resources(),
              'gpu_before': gpu_snapshot(), 'reserve_foreground_slots': args.reserve_slots,
              'latency_policy': {'p95_ttft_ms': args.max_ttft_ms, 'p95_total_ms': args.max_total_ms},
              'cases': [], 'profile_verified': False, 'global_maximum_proven': False,
              'model_port': args.model_port, 'model_target': base,
              'caveats': ['Idle admission is advisory, not an exclusive lease; foreground traffic can arrive during a burst.',
                          'Short finite task bursts do not establish sustained capacity for long contexts or tools.',
                          'Small-sample p95 is an empirical order statistic, not a confidence bound.']}
    try:
        slots = idle_gate(base)
        result['model_slots'] = slots['slots']
        if args.inventory_only:
            result['state'] = 'INVENTORY_ONLY'
            return result
        if not result['profile_before']['verified']:
            raise Hold('REQUESTED_MODE_NOT_VERIFIED')
        resource_gate(result['resources_before'])
        models = get('/v1/models', base)
        items = models.get('data') if isinstance(models, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise Hold('SINGLE_EXISTING_MODEL_UNVERIFIED')
        model = items[0].get('id')
        native_identity = native_model_identity(model, args.model_port, process_evidence())
        result['native_model_before'] = native_identity
        ceiling = min(slots['slots'] - args.reserve_slots, 6)
        if ceiling < 1:
            raise Hold('NO_BACKGROUND_SLOT_BUDGET')
        result['candidate_concurrency'] = sorted({value for value in (1, 2, 4, ceiling) if value <= ceiling})
        usage = True
        warmup = infer(model, 0, threading.Event(), deadline, usage, base)
        if warmup['state'] == 'HTTP_400':
            idle_gate(base)
            usage = False
            warmup = infer(model, 0, threading.Event(), deadline, usage, base)
        result['warmup_excluded'] = warmup
        if warmup['state'] != 'PASSED':
            raise Hold('WARMUP_TASK_NOT_VALID')
        for concurrency in result['candidate_concurrency']:
            if deadline - time.monotonic() < 15:
                raise Hold('PROBE_TIME_BUDGET_EXHAUSTED')
            if native_model_identity(model, args.model_port, process_evidence()) != native_identity:
                raise Hold('MODEL_PROCESS_CHANGED')
            case = burst(model, concurrency, args.samples, deadline, usage, base)
            result['cases'].append(case)
            print('NOX_MAINT_CAPACITY_CASE=' + json.dumps(case, sort_keys=True, separators=(',', ':')), flush=True)
            if case['state'] == 'FAILED':
                raise Hold('CANDIDATE_FAILED')
        result['state'] = 'BOUNDED_BENCHMARK_COMPLETED'
    except Hold as exc:
        result['state'] = 'HOLD_' + str(exc)
    finally:
        result['profile_after'] = profile_evidence(args.mode)
        if 'native_model_before' in result:
            try:
                result['native_model_after'] = native_model_identity(model, args.model_port, process_evidence())
                result['native_model_stable'] = result['native_model_before'] == result['native_model_after']
            except Hold:
                result['native_model_stable'] = False
            if not result['native_model_stable']:
                result['state'] = 'HOLD_MODEL_PROCESS_CHANGED'
        result['resources_after'] = resources()
        result['gpu_after'] = gpu_snapshot()
        result['profile_verified'] = result['profile_before']['verified'] and result['profile_after']['verified']
        if result['profile_verified'] and args.mode == 'NORMAL':
            before = {row['path']: row.get('step') for row in result['profile_before']['heartbeats']}
            result['training_step_advanced_during_probe'] = any(type(row.get('step')) is int and type(before.get(row['path'])) is int and row['step'] > before[row['path']] for row in result['profile_after']['heartbeats'])
        result['measured'] = recommend(result['cases'], args.max_ttft_ms, args.max_total_ms)
        if not result['profile_verified'] or result.get('native_model_stable') is False:
            result['mode_capacity_usable'] = False
        else:
            result['mode_capacity_usable'] = bool(result['measured'].get('recommended_concurrency'))
        if args.mode == 'NORMAL' and not result.get('training_step_advanced_during_probe'):
            result['mode_capacity_usable'] = False
        print('NOX_MAINT_CAPACITY=' + json.dumps(result, sort_keys=True, separators=(',', ':')), flush=True)
        print('NOX_MAINT_CAPACITY_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
