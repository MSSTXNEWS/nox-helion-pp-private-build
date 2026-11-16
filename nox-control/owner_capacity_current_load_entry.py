#!/usr/bin/env python3
"""One bounded 1/3/6 request sweep of the existing model under current load.

This is not NORMAL/TASK_BOOST acceptance or a hardware maximum. No service,
model, training flag, queue or persistent measurement file is changed. The
existing maintenance lock is held transiently; public fixtures remain exact.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PINS = {
    'owner_capacity_measure_entry.py': '6fafe435ac6d93417fbce76ec38c74c65e016d38e223d7e8ec5084444f9592e3',
    'owner_capacity_probe.py': '36e18d2f37dc8eb39195659e3a1082711bead921eb15150158ef883928a6c4f0',
}
REQUESTED = (1, 3, 6)
SAMPLES = 6
MAX_SECONDS = 45
EXPECTED_CHAT_PID = 7637
EXPECTED_CHAT_START = 149189867
MAX_TTFT_MS = 3000
MAX_TOTAL_MS = 12000


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def safe_error(exc):
    value = str(exc)
    waits = {'CHAT_BUSY': 'WAIT_CURRENT_LOAD_CHAT_BUSY',
             'OWNER_STOP': 'WAIT_CURRENT_LOAD_OWNER_STOP',
             'FOREGROUND_TRAFFIC_OBSERVED': 'WAIT_CURRENT_LOAD_FOREGROUND_ARRIVED',
             'OWNER_STOP_OR_PROBE_DEADLINE': 'WAIT_CURRENT_LOAD_DEADLINE_OR_STOP'}
    if value in waits:
        return waits[value]
    return value if re.fullmatch(r'(?:HOLD|WAIT)_[A-Z0-9_]{1,100}', value) else 'HOLD_CURRENT_LOAD_' + type(exc).__name__.upper()


def global_stop(core):
    paths = [core.ROOT / name for name in core.STOP_RELATIVE]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def budget_diagnostic(content, oracle_result):
    """Categorical only. Never salvage a wrong answer or copy its text/value."""
    row = {'schema': 'NOX_PUBLIC_BUDGET_VALIDATION_V1', 'oracle_match': bool(oracle_result),
           'raw_response_exported': False, 'actual_value_exported': False}
    if not isinstance(content, str) or len(content) > 16000:
        return dict(row, json_parse='UNAVAILABLE', value_type='UNKNOWN', value_relation='UNKNOWN')
    clean = content.strip()
    if clean.startswith('```') and clean.endswith('```'):
        clean = re.sub(r'^```(?:python|json)?\s*', '', clean)[:-3].strip()
    def invalid_constant(value):
        raise ValueError('nonfinite')
    try:
        actual = json.loads(clean, parse_constant=invalid_constant)
    except ValueError:
        return dict(row, json_parse='INVALID', value_type='UNKNOWN', value_relation='NOT_COMPARABLE')
    names = {int: 'INTEGER', bool: 'BOOLEAN', float: 'FLOAT', str: 'STRING',
             dict: 'OBJECT', list: 'ARRAY', type(None): 'NULL'}
    return dict(row, json_parse='VALID', value_type=names.get(type(actual), 'UNKNOWN'),
                value_relation=('MATCH' if actual == 8 else 'MISMATCH') if type(actual) is int else 'TYPE_MISMATCH')


def helpers():
    for name, pin in PINS.items():
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin,
                'HOLD_CURRENT_LOAD_BUNDLE_PIN')
    raw = base64.b64decode(BUNDLE['owner_capacity_measure_entry.py'], validate=True)
    core = types.ModuleType('_nox_current_load_guard_primitives')
    core.__file__ = '/root/nox/scripts/owner_capacity_measure_entry.py'
    exec(compile(raw, core.__file__, 'exec'), core.__dict__)
    core.BUNDLE = BUNDLE
    # Only pinned read-only primitives and the private inference loader are used.
    # native_profile/main/save_modes are deliberately never called.
    probe = core.load_probe()
    require(len(probe.FIXTURES) == SAMPLES and probe.FIXTURES[2][0] == 'budget'
            and type(probe.FIXTURES[2][2]) is int and probe.FIXTURES[2][2] == 8,
            'HOLD_CURRENT_LOAD_FIXTURE_CONTRACT')
    probe.stop_active = lambda: global_stop(core)
    local = threading.local()
    original_validate, private_infer = probe.validate_content, probe.infer

    def validate(index, content):
        accepted = original_validate(index, content)
        if index % SAMPLES == 2:
            local.budget = budget_diagnostic(content, accepted)
        return accepted

    def infer(*args, **kwargs):
        local.budget = None
        result = private_infer(*args, **kwargs)
        require('public_fixture_response' not in result, 'HOLD_CURRENT_LOAD_RESPONSE_PRIVACY')
        if local.budget is not None:
            result['budget_validation'] = local.budget
        return result

    probe.validate_content, probe.infer = validate, infer
    return core, probe


@contextmanager
def existing_lease(core):
    """No file creation or flags. A busy owner's lease produces WAIT."""
    path = core.checked(core.STATE / 'owner_maintenance.lock')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022, 'HOLD_CURRENT_LOAD_LEASE_FILE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('WAIT_CURRENT_LOAD_OWNER_LEASE_BUSY') from None
        current = path.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino),
                'HOLD_CURRENT_LOAD_LEASE_CHANGED')
        yield
    finally:
        os.close(fd)


def chat_identity(core):
    path = core.PROC / str(EXPECTED_CHAT_PID)
    fields = core.read(path / 'stat', 8192).decode().rsplit(') ', 1)[1].split()
    argv = core.read(path / 'cmdline', 65536).decode().rstrip('\0').split('\0')
    require(len(fields) > 19 and fields[0] not in ('Z', 'X')
            and int(fields[19]) == EXPECTED_CHAT_START and argv
            and Path(argv[0]).name == 'llama-server', 'HOLD_CURRENT_LOAD_CHAT_IDENTITY')
    options = {key: argv[i + 1] for i, key in enumerate(argv[:-1])
               if key in ('--port', '-np', '--parallel', '-m', '--model')}
    require(options.get('--port') == '8081' and options.get('-np', options.get('--parallel')) == '6'
            and options.get('-m', options.get('--model')) == str(core.ROOT / 'models/current.gguf'),
            'HOLD_CURRENT_LOAD_CHAT_ARGUMENTS')
    return {'pid': EXPECTED_CHAT_PID, 'start_ticks': EXPECTED_CHAT_START, 'model_slots': 6}


def gate(core, probe, baseline=None):
    require(not global_stop(core), 'WAIT_CURRENT_LOAD_OWNER_STOP')
    identity = chat_identity(core)
    slots = probe.idle_gate()
    require(slots['slots'] == 6 and slots['busy'] == 0, 'WAIT_CURRENT_LOAD_CHAT_BUSY')
    resources = probe.resources()
    probe.resource_gate(resources, baseline)
    statuses = core.services()
    core.media_idle(statuses)
    training = statuses.get(core.TRAINER)
    require(isinstance(training, dict) and training.get('state') in
            {'RUNNING', 'STARTING', 'EXITED', 'STOPPED', 'FATAL', 'BACKOFF'},
            'HOLD_CURRENT_LOAD_TRAINING_SERVICE_UNKNOWN')
    # Recheck after read-only media/service inspection; never wait out a user.
    slots = probe.idle_gate()
    require(slots['slots'] == 6, 'HOLD_CURRENT_LOAD_SLOT_COUNT_CHANGED')
    return {'chat_identity': identity, 'training_service': training,
            'resources': resources, 'model_slots': slots['slots']}


def summary(probe, rows, stable):
    complete = ([row.get('concurrency') for row in rows] == list(REQUESTED)
                and all(row.get('native_streams_completed') == SAMPLES
                        and row.get('state') in ('PASSED', 'QUALITY_FAILED')
                        and not row.get('hold_reason') for row in rows))
    all_quality = complete and all(row.get('passed') == SAMPLES and row.get('state') == 'PASSED' for row in rows)
    quality = probe.recommend(rows, MAX_TTFT_MS, MAX_TOTAL_MS)
    latency = [row['concurrency'] for row in rows
               if row.get('native_streams_completed') == SAMPLES and not row.get('hold_reason')
               and row.get('p95_ttft_ms') is not None and row['p95_ttft_ms'] <= MAX_TTFT_MS
               and row.get('p95_total_ms') is not None and row['p95_total_ms'] <= MAX_TOTAL_MS]
    return {'sweep_complete': complete, 'profile_stable': bool(stable),
            'all_fixture_quality_passed': bool(all_quality),
            'quality_passing_cases': [row['concurrency'] for row in rows if row.get('state') == 'PASSED'],
            'largest_latency_passing_tested_concurrency': max(latency, default=None),
            'recommended_tested_total_concurrency': quality.get('recommended_concurrency') if stable and all_quality else None,
            'accepted_background_limit': None, 'normal_mode_proven': False, 'task_boost_mode_proven': False,
            'global_maximum_proven': False, 'sustained_capacity_proven': False,
            'scope': 'OBSERVED_CURRENT_LOAD_SHORT_PUBLIC_FIXTURES_ONLY'}


def run_series(core, probe, result):
    before = gate(core, probe)
    result['before'] = before
    data = core.http_json(8081, '/v1/models', 16384)
    entries = data.get('data') if isinstance(data, dict) else None
    model = str(core.ROOT / 'models/current.gguf')
    require(isinstance(entries, list) and len(entries) == 1
            and isinstance(entries[0], dict) and entries[0].get('id') == model,
            'HOLD_CURRENT_LOAD_EXISTING_MODEL')
    deadline = time.monotonic() + MAX_SECONDS
    usage = True
    gate(core, probe, before['resources'])
    warmup = probe.infer(model, 0, threading.Event(), deadline, usage)
    result['warmup_excluded'] = warmup
    require(warmup.get('stream_done') is True and warmup.get('finish_reason') in ('stop', 'eos_token')
            and warmup.get('ttft_ms') is not None, 'HOLD_CURRENT_LOAD_WARMUP_TRANSPORT')
    for concurrency in REQUESTED:
        require(deadline - time.monotonic() >= 15, 'WAIT_CURRENT_LOAD_DEADLINE')
        current = gate(core, probe, before['resources'])
        require(current['chat_identity'] == before['chat_identity']
                and current['training_service'] == before['training_service'],
                'WAIT_CURRENT_LOAD_PROFILE_CHANGED')
        require(deadline - time.monotonic() >= 12, 'WAIT_CURRENT_LOAD_DEADLINE')
        case = probe.burst(model, concurrency, SAMPLES, deadline, usage)
        case['foreground_spare_slots_during_case'] = 6 - concurrency
        result['cases'].append(case)
        if case['state'] == 'FAILED':
            raise RuntimeError('HOLD_CURRENT_LOAD_TRANSPORT_OR_RESOURCE')
    after = gate(core, probe, before['resources'])
    result['after'] = after
    stable = (before['chat_identity'] == after['chat_identity']
              and before['training_service'] == after['training_service'])
    require(stable, 'WAIT_CURRENT_LOAD_PROFILE_CHANGED')
    result['measured'] = summary(probe, result['cases'], stable)
    result['state'] = ('CURRENT_LOAD_MEASURED_ALL_FIXTURES_PASSED' if result['measured']['all_fixture_quality_passed']
                       else 'CURRENT_LOAD_MEASURED_WITH_QUALITY_FAILURES')


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'\d{6,20}', request) and re.fullmatch(r'[a-f0-9]{40}', source),
            'HOLD_CURRENT_LOAD_CONTEXT')
    result = {'schema': 'NOX_OWNER_CURRENT_LOAD_CAPACITY_V1', 'request': request, 'source_sha': source,
              'started_at': time.time(), 'state': 'CURRENT_LOAD_PENDING', 'cases': [],
              'mode': 'CURRENT_LOAD_ONLY', 'candidate_total_concurrency': list(REQUESTED), 'samples_per_case': SAMPLES,
              'pinned_sources': PINS, 'service_controls_performed': False, 'model_changes': False,
              'training_flags_written': False, 'queue_changes': False, 'measurement_files_written': False,
              'raw_response_exported': False, 'private_content_exported': False,
              'full_process_inventory_performed': False, 'all_heavy_processes_paused_proven': False,
              'global_maximum_proven': False, 'maintenance_lease_is_full_pause_proof': False,
              'caveats': ['Six is TOTAL inference concurrency on one existing model, with zero extra foreground slot in that case.',
                          'Admission checks idle slots before each case; arriving user work can interrupt the bounded sweep.',
                          'Slots cannot identify a queued foreground request when all six are busy; six requests are finite and never retried.',
                          'Process visibility is incomplete; no NORMAL/TASK_BOOST or hardware maximum is claimed.',
                          'Six samples give empirical latency order statistics, not population confidence bounds.']}
    probe = None
    try:
        core, probe = helpers()
        with existing_lease(core):
            run_series(core, probe, result)
    except Exception as exc:
        result.update(state='CURRENT_LOAD_PARTIAL_OR_HELD', reason=safe_error(exc))
        if probe is not None:
            result['measured'] = summary(probe, result['cases'], False)
    result['finished_at'] = time.time()
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'current_load_capacity', 'data': result},
          ensure_ascii=False, allow_nan=False, separators=(',', ':')), flush=True)
    complete = result.get('measured', {}).get('sweep_complete') and result.get('measured', {}).get('profile_stable')
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if complete else 'false'), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'current_load_capacity',
              'data': {'state': 'CURRENT_LOAD_HELD', 'reason': safe_error(exc)}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
