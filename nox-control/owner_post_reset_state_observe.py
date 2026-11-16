#!/usr/bin/env python3
"""Finite metadata observation under owner STOP; never a resume authorization.

Only fixed flags/journals, three checkpoint JSON files, guard metadata, a
read-only Supervisor status command and three localhost health GETs are read.
No tensor, database, corpus, history, credential, or application response body
is read. The alarm bounds this observer only; no existing process is signaled.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CGROUP = Path('/sys/fs/cgroup')
FILESYSTEMS = {'SSD': ROOT, 'SHARED_MEMORY': Path('/dev/shm')}
FLAGS = {'OWNER_STOP': ROOT / 'STOP', 'OWNER_MAINTENANCE': STATE / 'OWNER_MAINTENANCE.flag',
         'TRAIN_HOLD': STATE / 'TRAIN_HOLD.flag', 'TRAIN_PAUSE': STATE / 'TRAIN_PAUSE_REQUEST.flag'}
JOURNALS = {
    '6917926683': '09e6cadfcbc10e6c4fb5abfde5185750f9676f9b',
    '6918022617': 'a923a7d7ccdf46001cc9b7ac6bd08fe0639dc596',
}
SCHEMA = 'NOX_POST_RESET_STATE_OBSERVATION_V1'
SHA = re.compile('[a-f0-9]{64}')
NAME = re.compile('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}')
CODE = re.compile('[A-Z][A-Z0-9_]{0,95}')
SERVICE = re.compile('nox-[A-Za-z0-9_.:-]{1,72}')
SERVICE_STATES = {'RUNNING', 'STARTING', 'STOPPED', 'STOPPING', 'EXITED', 'FATAL', 'BACKOFF', 'UNKNOWN'}
PAYLOADS = {'README.md', 'adapter_config.json', 'adapter_model.safetensors', 'lineage.json',
            'optimizer.pt', 'python_rng.json', 'rng_state.pt', 'scaler.pt', 'scheduler.pt', 'student_state.json'}
META_LIMIT = 256 * 1024
SECONDS = 20.0


class ObservationHold(Exception):
    pass


class Deadline(BaseException):
    pass


def require(ok, reason):
    if not ok:
        raise ObservationHold(reason)


def check(deadline):
    if time.monotonic() >= deadline:
        raise Deadline()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {key: getattr(info, 'st_' + key) for key in
            ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns')}


def open_regular(path, maximum):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= maximum, 'REGULAR_FILE_BOUND')
        except BaseException:
            os.close(fd)
            raise
        return fd, info
    finally:
        os.close(parent)


def read_record(path, maximum, deadline):
    check(deadline)
    fd, before = open_regular(path, maximum)
    try:
        parts, size = [], 0
        while True:
            check(deadline)
            raw = os.read(fd, min(65536, maximum + 1 - size))
            if not raw:
                break
            parts.append(raw)
            size += len(raw)
            require(size <= maximum, 'READ_BOUND')
        raw = b''.join(parts)
        fresh, named = open_regular(path, maximum)
        try:
            require(identity(before) == identity(os.fstat(fd)) == identity(named)
                    and len(raw) == before.st_size, 'FILE_CHANGED')
        finally:
            os.close(fresh)
        return {'raw': raw, 'identity': identity(before), 'sha256': digest(raw), 'bytes': len(raw)}
    finally:
        os.close(fd)


def metadata(row):
    return {'bytes': row['bytes'], 'sha256': row['sha256'], 'identity': row['identity'],
            'mode_octal': format(stat.S_IMODE(row['identity']['mode']), '04o'),
            'same_fd_and_named_identity_verified': True}


def document(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'JSON_DUPLICATE_KEY')
            value[key] = item
        return value
    def constant(_):
        raise ObservationHold('JSON_NONFINITE')
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10 ** 16


def coded(value):
    return value if isinstance(value, str) and CODE.fullmatch(value) else None


def reference(value):
    if not isinstance(value, dict):
        return None
    request, source, receipt = (value.get(k) for k in ('request', 'source_sha', 'receipt_sha256'))
    if (isinstance(request, str) and re.fullmatch('[0-9]{1,24}', request)
            and isinstance(source, str) and re.fullmatch('[a-f0-9]{40}', source)
            and isinstance(receipt, str) and SHA.fullmatch(receipt)):
        return {'request': request, 'source_sha': source, 'receipt_sha256': receipt}
    return None


def scalar_fields(value, keys):
    return {key: value[key] for key in keys if key in value and number(value[key])}


def flag_projection(label, row):
    raw = row['raw']
    request, form = None, 'UNKNOWN_CONTENT_WITHHELD'
    patterns = ((b'OWNER_MODEL_UPDATE ([0-9]{1,24})\n', 'OWNER_MODEL_UPDATE'),
                (b'OWNER_QWEN_WINDOW_FAILED request=([0-9]{1,24}) goal=1000\n', 'QWEN_WINDOW_FAILURE'))
    for pattern, known in patterns:
        match = re.fullmatch(pattern, raw)
        if match:
            request, form = match.group(1).decode('ascii'), known
            break
    if re.fullmatch(b'NOX_QWEN_GUARD_PAUSE_V1 context=[a-f0-9]{64} source=[a-f0-9]{64} reason=[A-Z_]{1,64}\n', raw):
        form = 'QWEN_GUARD_PAUSE'
    return {'state': 'PRESENT', 'label': label, **metadata(row), 'known_format': form,
            'owner_request': request, 'raw_contents_exported': False}


def service_map(value):
    require(isinstance(value, dict) and len(value) <= 64, 'SERVICE_MAP')
    require(all(isinstance(k, str) and SERVICE.fullmatch(k) and v in SERVICE_STATES
                for k, v in value.items()), 'SERVICE_VALUE')
    return dict(value)


def journal_projection(request, row):
    value = document(row['raw'])
    require(value.get('schema') == 'NOX_OWNER_EMERGENCY_RESET_V1'
            and value.get('request') == request and value.get('source_sha') == JOURNALS[request], 'JOURNAL_BINDING')
    result = {'state': 'METADATA_OBSERVED', **metadata(row), 'request': request,
              'source_sha': JOURNALS[request], 'recorded_state': coded(value.get('state')),
              'service_state_scope': 'HISTORICAL_RESET_JOURNAL_NOT_CURRENT_SERVICE_PROOF'}
    for key in ('stop_verified', 'maintenance_flags_active'):
        result[key] = value.get(key) if type(value.get(key)) is bool else None
    result.update(scalar_fields(value, ('bytes_reclaimed_verified', 'free_after_bytes')))
    for key in ('original_services', 'supervisor_after'):
        if key in value:
            result[key] = service_map(value[key])
    backup = value.get('s03_backup')
    if isinstance(backup, dict) and number(backup.get('bytes')) and isinstance(backup.get('sha256'), str) and SHA.fullmatch(backup['sha256']):
        result['s03_backup'] = {'bytes': backup['bytes'], 'sha256': backup['sha256']}
    return result


def checkpoint_projection(read):
    pointer = read('CHECKPOINT_POINTER', OUTPUT / 'latest_checkpoint.json', META_LIMIT)
    value = document(pointer['raw'])
    name, pin = value.get('directory'), value.get('manifest_sha256')
    require(isinstance(name, str) and NAME.fullmatch(name) and isinstance(pin, str) and SHA.fullmatch(pin), 'CHECKPOINT_PATH_SCOPE')
    manifest = read('CHECKPOINT_MANIFEST', OUTPUT / name / 'checkpoint_manifest.json', META_LIMIT)
    saved = read('CHECKPOINT_STATE', OUTPUT / name / 'student_state.json', META_LIMIT)
    m, s = document(manifest['raw']), document(saved['raw'])
    files = m.get('files_sha256')
    require(manifest['sha256'] == pin and m.get('directory') == name
            and isinstance(files, dict) and set(files) == PAYLOADS
            and all(isinstance(p, str) and SHA.fullmatch(p) for p in files.values())
            and files['student_state.json'] == saved['sha256'], 'CHECKPOINT_METADATA_BINDING')
    require(all(type(m.get(k)) is int and m[k] == s.get(k) for k in ('successful_total', 'attempted_total')),
            'CHECKPOINT_COUNTER_BINDING')
    binding, other = m.get('execution_binding'), s.get('execution_binding')
    require(binding == other, 'CHECKPOINT_EXECUTION_BINDING')
    result = {'state': 'HASH_BOUND_METADATA_OBSERVED', 'directory': name,
              'pointer': metadata(pointer), 'manifest': metadata(manifest), 'student_state': metadata(saved),
              'counters': scalar_fields(s, ('successful_total', 'attempted_total', 'skipped_total',
                   'holdout_evaluated_successful_total', 'last_holdout_loss', 'data_cursor')),
              'execution_revision': reference(binding.get('execution_revision')) if isinstance(binding, dict) else None,
              'manifest_payload_hashes': files, 'full_payload_sha256_verified': False,
              'metadata_only_not_new_learning_acceptance': True}
    witness = s.get('last_evaluation_witness')
    if isinstance(witness, dict):
        result['recorded_evaluation'] = {'kind': coded(witness.get('kind')),
            **scalar_fields(witness, ('evaluated_successful_total', 'started_at', 'finished_at', 'holdout_examples', 'holdout_loss'))}
    return result


def guard_projection(row):
    value = document(row['raw'])
    policy, checkpoint, bindings = (value.get(k) for k in ('policy_state', 'checkpoint', 'bindings'))
    require(all(isinstance(v, dict) for v in (policy, checkpoint, bindings)), 'GUARD_OBJECTS')
    sampled = value.get('sampled_at')
    age = time.time() - sampled if number(sampled) else None
    return {'state': 'METADATA_OBSERVED', **metadata(row), 'recorded_state': coded(value.get('state')),
        'sampled_at': sampled if number(sampled) else None, 'age_seconds': round(age, 3) if age is not None else None,
        'fresh_within_30_seconds': age is not None and 0 <= age <= 30,
        'execution_revision': reference(bindings.get('execution_revision')),
        'inhibit': policy.get('inhibit') if type(policy.get('inhibit')) is bool else None,
        'latched_reason': coded(policy.get('reason')),
        'policy': scalar_fields(policy, ('last_successful_updates', 'last_evaluation_update', 'evaluation_age_updates', 'best_holdout_loss',
            'regression_streak', 'observed_distinct_evaluations', 'latched_at', 'last_sample_at')),
        'checkpoint': scalar_fields(checkpoint, ('successful_updates', 'attempted_updates', 'skipped_updates', 'evaluated_at_update', 'holdout_loss')),
        'checkpoint_hashes': {k: checkpoint[k] for k in ('manifest_sha256', 'student_state_sha256', 'pointer_sha256')
                              if isinstance(checkpoint.get(k), str) and SHA.fullmatch(checkpoint[k])},
        'permission_to_resume': False}


def services(deadline):
    check(deadline)
    result = subprocess.run(['supervisorctl', 'status'], capture_output=True, timeout=min(3.0, deadline - time.monotonic()))
    require(result.returncode in (0, 3) and len(result.stdout) <= 65536, 'SUPERVISOR_STATUS')
    rows = {}
    for line in result.stdout.decode('ascii', errors='replace').splitlines():
        match = re.fullmatch(r'(nox-[A-Za-z0-9_.:-]{1,72})\s+([A-Z]+)(?:\s+(.*))?', line)
        if not match:
            continue
        name, state, tail = match.groups()
        require(state in SERVICE_STATES and name not in rows and len(rows) < 64, 'SUPERVISOR_ROW')
        pid = re.match(r'pid ([0-9]{1,10}),', tail or '') if state == 'RUNNING' else None
        rows[name] = {'state': state, 'pid': int(pid.group(1)) if pid else None}
    require('nox-train-volta-t866u' in rows, 'SUPERVISOR_SCOPE')
    return {'state': 'CURRENT_STATUS_OBSERVED', 'services': rows, 'raw_output_exported': False}


def health(port, deadline):
    check(deadline)
    started = time.monotonic()
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=min(1.0, deadline - started))
    try:
        connection.request('GET', '/health')
        response = connection.getresponse()
        return {'port': port, 'status': response.status, 'elapsed_seconds': round(time.monotonic() - started, 4),
                'response_body_bytes_read': 0, 'redirect_followed': False}
    except Exception as exc:
        return {'port': port, 'status': None, 'error_type': type(exc).__name__,
                'elapsed_seconds': round(time.monotonic() - started, 4), 'response_body_bytes_read': 0}
    finally:
        connection.close()


def resource_value(path, deadline):
    """Cgroup pseudo-files can have st_size=0 while returning live numeric data."""
    check(deadline)
    fd, before = open_regular(path, 128)
    try:
        raw = os.read(fd, 129)
        require(0 < len(raw) <= 128 and os.read(fd, 1) == b'', 'RESOURCE_BOUND')
        fresh, named = open_regular(path, 128)
        try:
            require(identity(before) == identity(os.fstat(fd)) == identity(named), 'RESOURCE_IDENTITY_CHANGED')
        finally:
            os.close(fresh)
        value = raw.strip()
        require(value == b'max' or re.fullmatch(b'[0-9]{1,20}', value), 'RESOURCE_VALUE')
        return {'state': 'VALUE_OBSERVED', 'value_bytes': int(value) if value != b'max' else None,
                'unlimited': value == b'max', 'sampled_at': time.time()}
    finally:
        os.close(fd)


def filesystem_value(path, deadline):
    check(deadline)
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        value = os.fstatvfs(fd)
        return {'state': 'VALUE_OBSERVED', 'free_bytes': value.f_bavail * value.f_frsize,
                'total_bytes': value.f_blocks * value.f_frsize, 'sampled_at': time.time(),
                'free_definition': 'f_bavail * f_frsize'}
    finally:
        os.close(fd)


def resources(deadline):
    def sample(function):
        try:
            return function()
        except Exception as exc:
            return {'state': 'UNKNOWN', 'reason': failure(exc)}
    cgroup = {name: sample(lambda name=name: resource_value(CGROUP / name, deadline))
              for name in ('memory.current', 'memory.max', 'memory.swap.current', 'memory.swap.max')}
    current, limit = (cgroup[key].get('value_bytes') for key in ('memory.current', 'memory.max'))
    headroom = limit - current if type(current) is int and type(limit) is int and current <= limit else None
    return {'scope': 'SAMPLED_TELEMETRY_NOT_ADMISSION_OR_RESUME_PERMISSION', 'cgroup': cgroup,
            'memory_headroom_bytes': headroom,
            'filesystems': {label: sample(lambda path=path: filesystem_value(path, deadline))
                            for label, path in FILESYSTEMS.items()}}


def failure(exc):
    return str(exc) if isinstance(exc, ObservationHold) else type(exc).__name__


def observe(deadline, result=None):
    records, absent = {}, {}
    def read(label, path, maximum):
        row = read_record(path, maximum, deadline)
        records[label] = (path, maximum, row)
        return row
    def section(function):
        try:
            return function()
        except FileNotFoundError:
            return {'state': 'ABSENT'}
        except Exception as exc:
            return {'state': 'HOLD_OBSERVATION', 'reason': failure(exc)}
    result = {} if result is None else result
    result.update(flags={}, reset_journals={}, health=[], observation_complete=False)
    for label, path in FLAGS.items():
        result['flags'][label] = section(lambda label=label, path=path: flag_projection(label, read(label, path, 4096)))
        if result['flags'][label]['state'] == 'ABSENT':
            absent[label] = path
    for request in JOURNALS:
        result['reset_journals'][request] = section(lambda request=request: journal_projection(request,
            read('RESET_' + request, STATE / ('owner_emergency_reset_' + request + '.json'), 128 * 1024)))
    result['checkpoint'] = section(lambda: checkpoint_projection(read))
    result['guard'] = section(lambda: guard_projection(read('GUARD', STATE / 'owner_qwen_training_guard.json', META_LIMIT)))
    result['supervisor'] = section(lambda: services(deadline))
    result['resources'] = resources(deadline)
    for port in (8080, 8081, 8082):
        result['health'].append(health(port, deadline))
    changed = []
    for label, (path, maximum, original) in records.items():
        try:
            require(read_record(path, maximum, deadline) == original, 'OBSERVATION_CHANGED')
        except Exception:
            changed.append(label)
    for label, path in absent.items():
        try:
            read_record(path, 4096, deadline)
        except FileNotFoundError:
            continue
        except Exception:
            pass
        changed.append(label)
    result['changed_during_observation'] = changed
    result['all_read_records_stable_through_end'] = not changed
    rows = [*result['flags'].values(), *result['reset_journals'].values(), result['checkpoint'], result['guard'], result['supervisor']]
    result['observation_complete'] = not changed and all(row['state'] != 'HOLD_OBSERVATION' for row in rows)
    return result


def main():
    started = time.time()
    result = {'schema': SCHEMA, 'started_at': started, 'state': 'HOLD_OBSERVATION',
              'observed_under_owner_stop_allowed': True, 'permission_to_resume': False,
              'files_written': 0, 'training_actions': 0, 'service_control_actions': 0,
              'application_posts': 0, 'tensor_payload_bytes_read': 0, 'private_contents_exported': False}
    result['health_does_not_verify_model_identity'] = True
    def alarm(*_):
        raise Deadline()
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, SECONDS)
    try:
        source, request = os.environ.get('NOX_OWNER_SOURCE_SHA', ''), os.environ.get('NOX_OWNER_REQUEST_ID', '')
        require(os.geteuid() == 0 and re.fullmatch('[a-f0-9]{40}', source)
                and re.fullmatch('[0-9]{1,24}', request), 'OWNER_CONTEXT')
        result.update(source_sha=source, request=request)
        observe(time.monotonic() + SECONDS, result)
        result['state'] = 'METADATA_OBSERVATION_COMPLETE' if result['observation_complete'] else 'METADATA_OBSERVATION_PARTIAL'
    except Deadline:
        result.update(state='METADATA_OBSERVATION_PARTIAL', reason='DEADLINE', observation_complete=False)
    except Exception as exc:
        result.update(reason=failure(exc), observation_complete=False)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    result['finished_at'] = time.time()
    result['elapsed_seconds'] = round(result['finished_at'] - started, 4)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'post_reset_state', 'data': result}, sort_keys=True, allow_nan=False), flush=True)
    if result.get('observation_complete'):
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
