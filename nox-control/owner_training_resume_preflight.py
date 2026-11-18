#!/usr/bin/env python3
"""Bounded read-only current training barriers; no runtime imports or admission."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/root/nox')
CGROUP = Path('/sys/fs/cgroup')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
AREA = ROOT / 'state/owner_qwen_execution_revisions/6916464880'
REFERENCE = {'request': '6916464880', 'source_sha': '7029c77906b512faaa9fd4b8290b122ee8c8f1f6',
    'receipt_sha256': 'ad3a760fac2eb56445a8e60dd19fe842ebc3d17dd26ea105485c0631fdf7ce86'}
SHARED = 'owner_qwen_execution_revision.py'
ENTRY = 'qwen_student_training_entry_revision.py'
GUARD = 'owner_qwen_training_guard.py'
HANDOFF = 'owner_qwen_media_handoff.py'
REQUIREMENT_PINS = {
    SHARED: 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14',
    ENTRY: '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03',
    GUARD: 'd5217f5bdfe21418d6210a18faac8eef422e49009d8abbcd3e71a06988a8b06b',
    HANDOFF: '1afc9705e1b84e0847f9a36d296458eab5098ad2939cbc7f8268a6bf2dfe7ea4',
}
CONSUMERS = frozenset((GUARD, HANDOFF, 'owner_training_status.py',
    'owner_qwen_media_guard.py', 'owner_qwen_handback_retry.py',
    'owner_hermes_hydrate.py', 'nox_dispatcher_t855u.py'))
CP55 = 'checkpoint-u00000055-a00000055-g01794833901774705882'
CP55_POINTER = '192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0'
CP55_MANIFEST = '458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65'
SHA = re.compile(r'[a-f0-9]{64}')
GIB = 1024 ** 3
REASONS = frozenset(('DISK_EARLY_MARGIN', 'EVALUATION_STALE', 'HOLDOUT_REGRESSION'))


class ReadHold(RuntimeError):
    pass


def read(path, limit=262144):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ReadHold('PATH_SCOPE')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = os.open('/', flags | os.O_DIRECTORY)
    fd = None
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, flags | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, flags | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ReadHold('FILE_BOUND')
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        if len(raw) > limit:
            raise ReadHold('READ_BOUND')
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if any(getattr(before, key) != getattr(after, key) or getattr(after, key) != getattr(named, key)
               for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            raise ReadHold('FILE_CHANGED')
        return bytes(raw)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def document(path, expected=None, limit=65536):
    raw = read(path, limit)
    pin = digest(raw)
    if expected is not None and (not SHA.fullmatch(str(expected)) or pin != expected):
        raise ReadHold('DOCUMENT_PIN')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ReadHold('DUPLICATE_KEY')
            value[key] = item
        return value
    def constant(_):
        raise ReadHold('NONFINITE_JSON')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ReadHold('DOCUMENT_SCHEMA')
    return value, pin


def numbers(value, names):
    return {name: value[name] for name in names if type(value.get(name)) in (int, float)
            and 0 <= value[name] < 10 ** 15 and math.isfinite(value[name])
            and (name in ('best_holdout_loss', 'holdout_loss', 'latched_at') or type(value[name]) is int)}


def guard_projection(value, now):
    policy = value.get('policy_state')
    checkpoint = value.get('checkpoint')
    bindings = value.get('bindings')
    policy = policy if isinstance(policy, dict) else {}
    checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
    bindings = bindings if isinstance(bindings, dict) else {}
    projected = numbers(policy, ('last_successful_updates', 'last_evaluation_update',
        'evaluation_age_updates', 'best_holdout_loss', 'regression_streak',
        'observed_distinct_evaluations', 'latched_at', 'disk_early_threshold_bytes',
        'disk_floor_bytes', 'checkpoint_budget_bytes'))
    projected.update({key: policy[key] for key in ('inhibit', 'complete') if type(policy.get(key)) is bool})
    reason = policy.get('reason')
    projected['reason'] = reason if reason is None or isinstance(reason, str) and reason in REASONS else 'UNRECOGNIZED_ENUM'
    state = value.get('state')
    state = state if isinstance(state, str) and state in ('INHIBITED', 'MONITORING') else 'UNRECOGNIZED_ENUM'
    sampled = value.get('sampled_at')
    age = now - sampled if type(sampled) in (int, float) and 0 <= sampled < 10 ** 15 and math.isfinite(sampled) else None
    return {'state': state, 'policy_state': projected,
            'checkpoint': numbers(checkpoint, ('successful_updates', 'attempted_updates',
                'skipped_updates', 'evaluated_at_update', 'holdout_loss', 'observed_file_bytes')),
            'execution_reference_matches': bindings.get('execution_revision') == REFERENCE,
            'sample_age_seconds': round(age, 3) if age is not None else None,
            'sample_is_fresh': age is not None and 0 <= age <= 30,
            'saved_state_is_live_optimizer_permission': False}


def source_fact(name, expected=None):
    if name not in CONSUMERS | {SHARED, ENTRY}:
        raise ReadHold('SOURCE_NAME_SCOPE')
    result = {'expected_sha256': expected if isinstance(expected, str) and SHA.fullmatch(expected) else None}
    try:
        result['actual_sha256'] = digest(read(ROOT / 'scripts' / name, 524288))
        result['matches'] = result['expected_sha256'] is not None and result['actual_sha256'] == expected
    except (OSError, ReadHold):
        result.update(state='UNAVAILABLE_SAFE_READ', matches=False)
    return result


def context_projection():
    result = {'expected_reference': dict(REFERENCE), 'sealed_metadata_chain_verified': False,
              'full_historical_context_verified': False, 'source_comparisons': {}}
    try:
        config, config_pin = document(ROOT / 'config/owner_qwen_execution_revision.json')
        result['config_sha256'] = config_pin
        if (config.get('schema') != 'NOX_QWEN_EXECUTION_REVISION_CONFIG_V1'
                or config.get('enabled') is not True or config.get('execution_revision') != REFERENCE
                or config.get('source_sha256') != REQUIREMENT_PINS[SHARED]):
            raise ReadHold('CURRENT_CONFIG_SCOPE')
        receipt, receipt_pin = document(AREA / 'admission_receipt.json', REFERENCE['receipt_sha256'])
        result['receipt_sha256'] = receipt_pin
        if (receipt.get('schema') != 'NOX_QWEN_EXECUTION_SUCCESSOR_ADMISSION_V1'
                or receipt.get('request') != REFERENCE['request'] or receipt.get('source_sha') != REFERENCE['source_sha']
                or receipt.get('state') != 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED'):
            raise ReadHold('RECEIPT_SCOPE')
        if not isinstance(receipt.get('descriptor_sha256'), str) or not SHA.fullmatch(receipt['descriptor_sha256']):
            raise ReadHold('DESCRIPTOR_PIN')
        descriptor, descriptor_pin = document(AREA / 'descriptor.json', receipt.get('descriptor_sha256'))
        result['descriptor_sha256'] = descriptor_pin
        if (descriptor.get('schema') != 'NOX_QWEN_EXECUTION_SUCCESSOR_DESCRIPTOR_V1'
                or descriptor.get('request') != REFERENCE['request'] or descriptor.get('source_sha') != REFERENCE['source_sha']):
            raise ReadHold('DESCRIPTOR_SCOPE')
        consumers, runtime = descriptor.get('consumer_sources'), descriptor.get('runtime_sources')
        if (not isinstance(consumers, dict) or set(consumers) != CONSUMERS
                or not isinstance(runtime, dict) or set(runtime) != {SHARED, ENTRY}
                or not all(isinstance(pin, str) and SHA.fullmatch(pin) for pin in (*consumers.values(), *runtime.values()))):
            raise ReadHold('DESCRIPTOR_SOURCE_SET')
        if receipt.get('runtime_sources') != runtime or runtime[SHARED] != config['source_sha256']:
            raise ReadHold('SEALED_SOURCE_BINDING')
        for name, pin in sorted({**consumers, **runtime}.items()):
            result['source_comparisons'][name] = source_fact(name, pin)
        result['admission_sha256'] = digest(read(ROOT / 'state/owner_training_admission.json', 65536))
        result['wrapper_sha256'] = digest(read(ROOT / 'scripts/run_train_volta_t866u.sh', 65536))
        result['admission_matches_seal'] = result['admission_sha256'] == receipt.get('new_admission_sha256')
        result['wrapper_matches_seal'] = result['wrapper_sha256'] == receipt.get('wrapper_sha256')
        result['sealed_metadata_chain_verified'] = result['admission_matches_seal'] and result['wrapper_matches_seal']
        result['all_declared_sources_match'] = all(row['matches'] for row in result['source_comparisons'].values())
        result['state'] = 'CURRENT_SEAL_OBSERVED'
    except (OSError, ReadHold, ValueError, UnicodeError):
        result['state'] = 'CURRENT_SEAL_UNVERIFIED'
    return result


def checkpoint_projection():
    result = {'payload_files_read': 0, 'full_payload_hashes_verified': False}
    try:
        pointer, pin = document(OUTPUT / 'latest_checkpoint.json')
        result['latest_pointer_sha256'] = pin
        result['matches_known_cp55_pointer'] = pin == CP55_POINTER
        if (pin != CP55_POINTER or pointer.get('directory') != CP55
                or pointer.get('manifest_sha256') != CP55_MANIFEST):
            raise ReadHold('CHECKPOINT_POINTER_SCOPE')
        manifest, pin = document(OUTPUT / CP55 / 'checkpoint_manifest.json', CP55_MANIFEST)
        result.update(state='CP55_METADATA_SHA_VERIFIED', manifest_sha256=pin,
            counters=numbers(manifest, ('successful_total', 'attempted_total', 'skipped_total',
                'holdout_evaluated_successful_total', 'holdout_loss')))
    except (OSError, ReadHold, ValueError, UnicodeError):
        result['state'] = 'CHECKPOINT_METADATA_UNVERIFIED'
    return result


def resources():
    result = {'raw_cgroup_headroom_bytes': None, 'disk_free_bytes': None, 'gpu1_free_mib': None}
    try:
        current, maximum = (read(CGROUP / name, 128).strip() for name in ('memory.current', 'memory.max'))
        if current.isdigit() and maximum.isdigit() and 0 <= int(current) <= int(maximum):
            result['raw_cgroup_headroom_bytes'] = int(maximum) - int(current)
        fs = os.statvfs(ROOT)
        result['disk_free_bytes'] = fs.f_bavail * fs.f_frsize
    except (OSError, ReadHold, ValueError):
        pass
    try:
        child = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'],
                               capture_output=True, timeout=4)
        if child.returncode == 0 and len(child.stdout) <= 4096:
            matches = [re.fullmatch(rb'1\s*,\s*([0-9]{1,9})\s*', line.strip()) for line in child.stdout.splitlines()]
            matches = [match for match in matches if match]
            if len(matches) == 1:
                result['gpu1_free_mib'] = int(matches[0][1])
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def barriers(result):
    found = []
    guard = result['guard']
    policy = guard.get('policy_state') or {}
    if guard.get('state') == 'INHIBITED' and policy.get('inhibit') is True:
        reason = policy.get('reason')
        found.append('STORED_GUARD_INHIBITED_' + reason if reason in REASONS else 'STORED_GUARD_INHIBITED')
    if not guard.get('sample_is_fresh'):
        found.append('GUARD_SAMPLE_NOT_FRESH')
    if guard.get('execution_reference_matches') is not True:
        found.append('GUARD_EXECUTION_BINDING_UNVERIFIED')
    if policy.get('complete') is True:
        found.append('TRAINING_GOAL_ALREADY_COMPLETE')
    ctx = result['context']
    if not ctx.get('sealed_metadata_chain_verified'):
        found.append('SEALED_CONTEXT_METADATA_UNVERIFIED')
    if not ctx.get('all_declared_sources_match'):
        found.append('SEALED_RUNTIME_OR_CONSUMER_SOURCES_UNVERIFIED')
    if not result['requirements']['source_pins_verified']:
        found.append('RESOURCE_REQUIREMENT_SOURCE_UNVERIFIED')
    values = result['resources']
    for name, floor, code in (
            ('raw_cgroup_headroom_bytes', 48 * GIB + 19329393661, 'RAW_CGROUP_HEADROOM'),
            ('disk_free_bytes', max(10 * GIB, policy.get('disk_early_threshold_bytes', 0)), 'CHECKPOINT_DISK_HEADROOM'),
            ('gpu1_free_mib', 30000, 'GPU1_HEADROOM')):
        value = values.get(name)
        if type(value) is not int or value < floor:
            found.append(code + '_INSUFFICIENT_OR_UNKNOWN')
    if result['checkpoint'].get('state') != 'CP55_METADATA_SHA_VERIFIED':
        found.append('CHECKPOINT_METADATA_UNVERIFIED')
    return found


def observe():
    started = time.monotonic()
    result = {'schema': 'NOX_TRAINING_RESUME_PREFLIGHT_V1', 'files_written': 0,
        'service_mutations': 0, 'flags_changed': False, 'training_admitted': False,
        'optimizer_permission_issued': False, 'checkpoint_payloads_read': False,
        'training_modules_imported': False, 'raw_private_records_exported': False}
    try:
        guard, pin = document(ROOT / 'state/owner_qwen_training_guard.json')
        result['guard'] = {'sha256': pin, **guard_projection(guard, time.time())}
    except (OSError, ReadHold, ValueError, UnicodeError):
        result['guard'] = {'state': 'UNAVAILABLE_SAFE_READ', 'sample_is_fresh': False}
    result['context'] = context_projection()
    result['checkpoint'] = checkpoint_projection()
    verified = {name: source_fact(name, pin) for name, pin in REQUIREMENT_PINS.items()}
    result['requirements'] = {'source_pins': verified, 'source_pins_verified': all(row['matches'] for row in verified.values()),
        'entry_start_raw_headroom_bytes': 32 * GIB, 'entry_memfd_stage_raw_base_headroom_bytes': 48 * GIB,
        'handoff_restaging_raw_headroom_bytes': 48 * GIB + 19329393661,
        'handoff_disk_floor_bytes': 10 * GIB, 'handoff_gpu1_free_mib': 30000,
        'inactive_file_counted_as_headroom': False, 'thresholds_changed': False}
    result['resources'] = resources()
    result['barriers'] = barriers(result)
    result['state'] = 'READ_ONLY_RESUME_PREFLIGHT_COMPLETE'
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result



ADMISSION_SCHEMA = 'NOX_TRAINING_ADMISSION_PREFLIGHT_V1'
CHECKPOINT_FILES = (
    'trainer_state.json', 'optimizer.pt', 'scheduler.pt', 'rng_state.pth',
    'scaler.pt', 'adapter_config.json', 'adapter_model.safetensors',
)
CHECKPOINT_BUDGET_BYTES = 826_671_104
TRAIN_START_BYTES = 32 * GIB
MEMFD_STAGE_BYTES = 48 * GIB
FULL_RESTAGE_BYTES = 48 * GIB + 19_329_393_661
DISK_FLOOR_BYTES = 10 * GIB
GPU1_FLOOR_MIB = 30_000
FRESH_SECONDS = 30
ADMISSION_STATE = ROOT / 'state/training_admissions'
CHAT_SIGNAL = ROOT / 'state/owner_chat_inflight.json'
LEASE_EVIDENCE = ROOT / 'state/owner_training_lease.json'
ROLLBACK_EVIDENCE = ROOT / 'state/training_rollback_evidence.json'
STOP_FLAGS = (
    ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop',
    ROOT / 'program/STOP', ROOT / 'state/STOP', ROOT / 'state/TRAIN_PAUSE_REQUEST.flag',
    ROOT / 'state/TRAIN_HOLD.flag', Path('/workspace/NOX_STOP'),
)


def _sha256(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value < 10 ** 15


def _fresh(sampled_at, now):
    return _timestamp(sampled_at) and 0 <= now - sampled_at <= FRESH_SECONDS


def file_digest(path, limit=CHECKPOINT_BUDGET_BYTES):
    """Hash one bounded regular file without following links or loading it into memory."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or type(limit) is not int or limit <= 0:
        raise ReadHold('HASH_PATH_SCOPE')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_DIRECTORY
    parent = os.open('/', flags)
    fd = None
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > limit:
            raise ReadHold('HASH_FILE_BOUND')
        digestor = hashlib.sha256()
        total = 0
        while True:
            part = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not part:
                break
            total += len(part)
            if total > limit:
                raise ReadHold('HASH_READ_BOUND')
            digestor.update(part)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if total != before.st_size or any(
                getattr(before, key) != getattr(after, key)
                or getattr(after, key) != getattr(named, key)
                for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            raise ReadHold('HASH_FILE_CHANGED')
        return {'bytes': total, 'sha256': digestor.hexdigest()}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _checkpoint_payloads(now):
    result = {'state': 'CHECKPOINT_PAYLOADS_UNVERIFIED', 'pointer_sha256': None,
              'manifest_sha256': None, 'payload_files': [], 'payload_hashes_verified': False,
              'optimizer_scaler_rng_verified': False, 'bundle_sha256': None}
    try:
        pointer, pointer_sha = document(OUTPUT / 'latest_checkpoint.json')
        result['pointer_sha256'] = pointer_sha
        if (pointer_sha != CP55_POINTER or pointer.get('directory') != CP55
                or pointer.get('manifest_sha256') != CP55_MANIFEST):
            raise ReadHold('CHECKPOINT_POINTER_SCOPE')
        manifest, manifest_sha = document(OUTPUT / CP55 / 'checkpoint_manifest.json', CP55_MANIFEST)
        result['manifest_sha256'] = manifest_sha
        expected = manifest.get('files_sha256')
        if not isinstance(expected, dict) or set(expected) != set(CHECKPOINT_FILES):
            raise ReadHold('CHECKPOINT_FILE_SET')
        rows = []
        total = 0
        for name in CHECKPOINT_FILES:
            if not _sha256(expected.get(name)):
                raise ReadHold('CHECKPOINT_FILE_SHA')
            observed = file_digest(OUTPUT / CP55 / name, CHECKPOINT_BUDGET_BYTES)
            if observed['sha256'] != expected[name]:
                raise ReadHold('CHECKPOINT_FILE_HASH')
            total += observed['bytes']
            if total > CHECKPOINT_BUDGET_BYTES:
                raise ReadHold('CHECKPOINT_TOTAL_BUDGET')
            rows.append({'name': name, **observed})
        result.update(state='CHECKPOINT_FULL_HASHES_VERIFIED', payload_files=rows,
            payload_hashes_verified=True, optimizer_scaler_rng_verified=True,
            bundle_sha256=digest(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()))
    except (OSError, ReadHold, ValueError, UnicodeError):
        pass
    return result


def _holdout_projection(now):
    result = {'dataset_sha256': None, 'sample_sha256': None, 'sampled_at_unix': None,
              'sample_age_seconds': None, 'fresh': False, 'best_loss': None,
              'candidate_loss': None, 'regression_streak': None, 'guard_state': 'UNKNOWN'}
    try:
        guard, _ = document(ROOT / 'state/owner_qwen_training_guard.json')
        policy = guard.get('policy_state') if isinstance(guard.get('policy_state'), dict) else {}
        checkpoint = guard.get('checkpoint') if isinstance(guard.get('checkpoint'), dict) else {}
        sampled = policy.get('holdout_sampled_at')
        result.update(
            dataset_sha256=policy.get('holdout_dataset_sha256') if _sha256(policy.get('holdout_dataset_sha256')) else None,
            sample_sha256=policy.get('holdout_sample_sha256') if _sha256(policy.get('holdout_sample_sha256')) else None,
            sampled_at_unix=sampled if _timestamp(sampled) else None,
            sample_age_seconds=round(now - sampled, 3) if _timestamp(sampled) else None,
            fresh=_fresh(sampled, now),
            best_loss=policy.get('best_holdout_loss') if type(policy.get('best_holdout_loss')) in (int, float)
                and math.isfinite(policy.get('best_holdout_loss')) else None,
            candidate_loss=checkpoint.get('holdout_loss') if type(checkpoint.get('holdout_loss')) in (int, float)
                and math.isfinite(checkpoint.get('holdout_loss')) else None,
            regression_streak=policy.get('regression_streak') if type(policy.get('regression_streak')) is int else None,
            guard_state=guard.get('state') if guard.get('state') in ('MONITORING', 'INHIBITED') else 'UNKNOWN',
        )
        result['inhibit'] = policy.get('inhibit') if type(policy.get('inhibit')) is bool else None
    except (OSError, ReadHold, ValueError, UnicodeError):
        result['inhibit'] = None
    return result


def _chat_projection(owner_request_id, now):
    result = {'observed': False, 'inflight': None, 'sampled_at_unix': None, 'fresh': False}
    try:
        value, _ = document(CHAT_SIGNAL)
        sampled = value.get('sampled_at_unix')
        if (value.get('schema') != 'NOX_OWNER_CHAT_INFLIGHT_V1'
                or value.get('owner_request_id') != owner_request_id
                or type(value.get('inflight')) is not bool):
            raise ReadHold('CHAT_SIGNAL_SCHEMA')
        result.update(observed=True, inflight=value['inflight'],
                      sampled_at_unix=sampled if _timestamp(sampled) else None,
                      fresh=_fresh(sampled, now))
    except (OSError, ReadHold, ValueError, UnicodeError):
        pass
    return result


def _stop_projection():
    present = []
    complete = True
    for path in STOP_FLAGS:
        try:
            os.lstat(path)
            present.append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))
        except FileNotFoundError:
            continue
        except OSError:
            complete = False
    return {'stop_state_verified': complete, 'active_stop_flags': present,
            'stop_clear': complete and not present}


def _proc_start_ticks(pid):
    if type(pid) is not int or pid <= 0:
        raise ReadHold('LEASE_PID')
    raw = read(Path('/proc') / str(pid) / 'stat', 4096).decode('ascii')
    close = raw.rfind(')')
    if close < 0:
        raise ReadHold('LEASE_PID_STAT')
    fields = raw[close + 2:].split()
    if len(fields) <= 19 or not fields[19].isdigit():
        raise ReadHold('LEASE_PID_TICKS')
    return int(fields[19])


def _owner_control_projection(owner_request_id, source_sha, now):
    result = _stop_projection()
    result.update({'lease_id': None, 'fencing_token': None, 'lease_fresh': False,
        'single_fenced_lease': False, 'handoff_verified': False,
        'pid_start_ticks': [], 'trainer_state': 'UNKNOWN',
        'training_process_count': None, 'lease_evidence_sha256': None})
    try:
        lease, pin = document(LEASE_EVIDENCE)
        result['lease_evidence_sha256'] = pin
        required = (
            lease.get('schema') == 'NOX_OWNER_TRAINING_LEASE_V1'
            and lease.get('owner_request_id') == owner_request_id
            and lease.get('source_sha256') == source_sha
            and lease.get('state') == 'ACTIVE'
            and lease.get('fenced') is True
            and type(lease.get('fencing_token')) is int and lease['fencing_token'] > 0
            and type(lease.get('active_lease_count')) is int and lease['active_lease_count'] == 1
            and isinstance(lease.get('lease_id'), str)
            and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', lease['lease_id']) is not None
            and _fresh(lease.get('sampled_at_unix'), now)
        )
        if not required:
            raise ReadHold('LEASE_EVIDENCE_SCHEMA')
        pid = lease.get('owner_pid')
        expected_ticks = lease.get('owner_pid_start_ticks')
        actual_ticks = _proc_start_ticks(pid)
        if type(expected_ticks) is not int or expected_ticks != actual_ticks:
            raise ReadHold('LEASE_PID_TICKS_MISMATCH')
        result.update(lease_id=lease['lease_id'], fencing_token=lease['fencing_token'],
            lease_fresh=True, single_fenced_lease=True, handoff_verified=lease.get('handoff_verified') is True,
            pid_start_ticks=[{'role': 'lease_owner', 'pid': pid, 'start_ticks': actual_ticks, 'verified': True}],
            trainer_state=lease.get('trainer_state') if lease.get('trainer_state') in ('STOPPED', 'EXITED') else 'UNKNOWN',
            training_process_count=lease.get('training_process_count')
                if type(lease.get('training_process_count')) is int else None)
    except (OSError, ReadHold, ValueError, UnicodeError):
        pass
    result['trainer_stopped'] = result['trainer_state'] in ('STOPPED', 'EXITED') and result['training_process_count'] == 0
    return result


def _rollback_projection(owner_request_id, checkpoint, now):
    result = {'immutable_pre_run_checkpoint_sha256': None, 'independent_backup_sha256': None,
              'backup_bytes': None, 'restore_probe_sha256': None, 'restore_probe_passed': False,
              'fresh': False, 'backup_verified': False}
    try:
        value, _ = document(ROLLBACK_EVIDENCE)
        sampled = value.get('sampled_at_unix')
        relative = value.get('independent_backup_path')
        if (value.get('schema') != 'NOX_TRAINING_ROLLBACK_EVIDENCE_V1'
                or value.get('owner_request_id') != owner_request_id
                or value.get('immutable_pre_run_checkpoint_sha256') != checkpoint.get('bundle_sha256')
                or not isinstance(relative, str) or not relative.startswith('state/training_backups/' + owner_request_id + '/')
                or Path(relative).is_absolute() or '..' in Path(relative).parts):
            raise ReadHold('ROLLBACK_EVIDENCE_SCOPE')
        observed = file_digest(ROOT / relative, CHECKPOINT_BUDGET_BYTES)
        expected = value.get('independent_backup_sha256')
        if not _sha256(expected) or observed['sha256'] != expected:
            raise ReadHold('ROLLBACK_BACKUP_HASH')
        probe_pin = value.get('restore_probe_sha256')
        passed = value.get('restore_probe_passed') is True and _sha256(probe_pin)
        result.update(immutable_pre_run_checkpoint_sha256=value['immutable_pre_run_checkpoint_sha256'],
            independent_backup_sha256=observed['sha256'], backup_bytes=observed['bytes'],
            restore_probe_sha256=probe_pin if _sha256(probe_pin) else None,
            restore_probe_passed=bool(passed), fresh=_fresh(sampled, now), backup_verified=True)
    except (OSError, ReadHold, ValueError, UnicodeError):
        pass
    return result


def assess_admission(evidence, now):
    """Pure fail-closed gate assessment. It can never issue training permission."""
    blockers = []
    resources = evidence.get('resources') if isinstance(evidence.get('resources'), dict) else {}
    if not _fresh(resources.get('sampled_at_unix'), now):
        blockers.append('RESOURCE_SAMPLE_STALE_OR_UNKNOWN')
    if resources.get('telemetry_complete') is not True:
        blockers.append('RESOURCE_TELEMETRY_INCOMPLETE')
    if resources.get('chat_inflight_observed') is not True or resources.get('chat_inflight') is not False:
        blockers.append('CHAT_INFLIGHT_NOT_CLEARED')
    for name, floor, code in (
        ('raw_cgroup_headroom_bytes', FULL_RESTAGE_BYTES, 'RAW_RAM'),
        ('disk_free_bytes', max(DISK_FLOOR_BYTES, resources.get('required_disk_bytes', DISK_FLOOR_BYTES))
            if type(resources.get('required_disk_bytes', DISK_FLOOR_BYTES)) is int else DISK_FLOOR_BYTES, 'DISK'),
        ('gpu1_free_mib', GPU1_FLOOR_MIB, 'GPU1'),
    ):
        value = resources.get(name)
        if type(value) is not int or value < floor:
            blockers.append(code + '_INSUFFICIENT_OR_UNKNOWN')

    checkpoint = evidence.get('checkpoint') if isinstance(evidence.get('checkpoint'), dict) else {}
    rows = checkpoint.get('payload_files')
    if (checkpoint.get('payload_hashes_verified') is not True
            or checkpoint.get('optimizer_scaler_rng_verified') is not True
            or not _sha256(checkpoint.get('pointer_sha256'))
            or not _sha256(checkpoint.get('manifest_sha256'))
            or not _sha256(checkpoint.get('bundle_sha256'))
            or not isinstance(rows, list) or len(rows) != len(CHECKPOINT_FILES)):
        blockers.append('CHECKPOINT_FULL_HASH_CHAIN_UNVERIFIED')
    else:
        by_name = {row.get('name'): row for row in rows if isinstance(row, dict)}
        if set(by_name) != set(CHECKPOINT_FILES) or any(
            type(by_name[name].get('bytes')) is not int or by_name[name]['bytes'] <= 0
            or not _sha256(by_name[name].get('sha256')) for name in CHECKPOINT_FILES
        ):
            blockers.append('CHECKPOINT_PAYLOAD_SET_INVALID')

    holdout = evidence.get('holdout') if isinstance(evidence.get('holdout'), dict) else {}
    if (not _sha256(holdout.get('dataset_sha256')) or not _sha256(holdout.get('sample_sha256'))
            or not _fresh(holdout.get('sampled_at_unix'), now) or holdout.get('fresh') is not True
            or type(holdout.get('best_loss')) not in (int, float)
            or type(holdout.get('candidate_loss')) not in (int, float)
            or not math.isfinite(holdout.get('best_loss', float('nan')))
            or not math.isfinite(holdout.get('candidate_loss', float('nan')))
            or type(holdout.get('regression_streak')) is not int or holdout['regression_streak'] != 0
            or holdout.get('guard_state') != 'MONITORING' or holdout.get('inhibit') is not False
            or holdout.get('candidate_loss') > holdout.get('best_loss')):
        blockers.append('HOLDOUT_STALE_OR_REGRESSED')

    seal = evidence.get('source_seal') if isinstance(evidence.get('source_seal'), dict) else {}
    if seal.get('all_pins_match') is not True:
        blockers.append('SOURCE_SEAL_MISMATCH_OR_UNKNOWN')

    owner = evidence.get('owner_control') if isinstance(evidence.get('owner_control'), dict) else {}
    if owner.get('stop_state_verified') is not True or owner.get('stop_clear') is not True:
        blockers.append('STOP_PRESENT_OR_UNVERIFIED')
    if (owner.get('single_fenced_lease') is not True or owner.get('lease_fresh') is not True
            or owner.get('handoff_verified') is not True):
        blockers.append('FENCED_LEASE_OR_HANDOFF_UNVERIFIED')
    ticks = owner.get('pid_start_ticks')
    if (not isinstance(ticks, list) or not ticks
            or any(not isinstance(row, dict) or row.get('verified') is not True
                   or type(row.get('pid')) is not int or row['pid'] <= 0
                   or type(row.get('start_ticks')) is not int or row['start_ticks'] <= 0
                   for row in ticks)):
        blockers.append('PID_START_TICKS_UNVERIFIED')
    if owner.get('trainer_stopped') is not True:
        blockers.append('TRAINER_NOT_TERMINAL')

    rollback = evidence.get('rollback') if isinstance(evidence.get('rollback'), dict) else {}
    if (rollback.get('backup_verified') is not True or not _sha256(rollback.get('immutable_pre_run_checkpoint_sha256'))
            or not _sha256(rollback.get('independent_backup_sha256'))
            or rollback.get('restore_probe_passed') is not True or not rollback.get('fresh')):
        blockers.append('ROLLBACK_BACKUP_OR_PROBE_UNVERIFIED')

    unique_blockers = list(dict.fromkeys(blockers))
    ready = not unique_blockers
    return {'state': 'OWNER_GATE_REQUIRED' if ready else 'HOLD', 'blockers': unique_blockers,
            'all_gates_pass': ready, 'owner_gate_required': True,
            'training_permission_issued': False}


def _evidence_receipt(owner_request_id, source_sha, now):
    prior = observe()
    resources_now = dict(prior.get('resources', {}))
    resources_now.update(sampled_at_unix=now, telemetry_complete=all(
        type(resources_now.get(name)) is int for name in
        ('raw_cgroup_headroom_bytes', 'disk_free_bytes', 'gpu1_free_mib')))
    chat = _chat_projection(owner_request_id, now)
    resources_now.update(chat_inflight_observed=chat['observed'], chat_inflight=chat['inflight'],
        chat_signal_fresh=chat['fresh'])
    guard = prior.get('guard', {})
    required_disk = guard.get('policy_state', {}).get('disk_early_threshold_bytes', DISK_FLOOR_BYTES)
    resources_now['required_disk_bytes'] = required_disk if type(required_disk) is int else None
    resources_now.update(required_start_bytes=TRAIN_START_BYTES,
        required_memfd_stage_bytes=MEMFD_STAGE_BYTES, required_full_restaging_bytes=FULL_RESTAGE_BYTES,
        disk_floor_bytes=DISK_FLOOR_BYTES, gpu1_required_mib=GPU1_FLOOR_MIB,
        checkpoint_budget_bytes=CHECKPOINT_BUDGET_BYTES)
    checkpoint = _checkpoint_payloads(now)
    holdout = _holdout_projection(now)
    source = {'all_pins_match': prior.get('requirements', {}).get('source_pins_verified') is True
        and prior.get('context', {}).get('all_declared_sources_match') is True,
        'requirement_pins': prior.get('requirements', {}).get('source_pins', {}),
        'context_state': prior.get('context', {}).get('state', 'UNKNOWN')}
    owner = _owner_control_projection(owner_request_id, source_sha, now)
    rollback = _rollback_projection(owner_request_id, checkpoint, now)
    evidence = {'resources': resources_now, 'checkpoint': checkpoint, 'holdout': holdout,
        'source_seal': source, 'owner_control': owner, 'rollback': rollback}
    decision = assess_admission(evidence, now)
    return {'schema': ADMISSION_SCHEMA, 'captured_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
        'owner_request_id': owner_request_id, 'source_sha256': source_sha,
        **evidence, 'decision': decision, 'state': decision['state'],
        'training_permission_issued': False, 'service_mutations': 0,
        'training_modules_imported': False, 'raw_private_records_exported': False}


def _private_dirfd(path, create=False):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ReadHold('RECEIPT_DIR_SCOPE')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = os.open('/', flags)
    try:
        for index, component in enumerate(path.parts[1:]):
            final = index == len(path.parts[1:]) - 1
            try:
                child = os.open(component, flags, dir_fd=parent)
            except FileNotFoundError:
                if not create or not final:
                    raise
                os.mkdir(component, 0o700, dir_fd=parent)
                child = os.open(component, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        meta = os.fstat(parent)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) & 0o077:
            raise ReadHold('RECEIPT_DIR_PERMISSIONS')
        return parent
    except BaseException:
        os.close(parent)
        raise


def write_admission_receipt(receipt, directory=ADMISSION_STATE):
    if (not isinstance(receipt, dict) or receipt.get('schema') != ADMISSION_SCHEMA
            or receipt.get('state') not in ('HOLD', 'OWNER_GATE_REQUIRED')
            or receipt.get('training_permission_issued') is not False
            or not isinstance(receipt.get('decision'), dict)
            or receipt['decision'].get('training_permission_issued') is not False
            or not re.fullmatch(r'[0-9]{1,24}', str(receipt.get('owner_request_id', '')))):
        raise ReadHold('RECEIPT_SCHEMA')
    raw = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > 65536:
        raise ReadHold('RECEIPT_SIZE')
    request = receipt['owner_request_id']
    final_name = request + '.json'
    dirfd = _private_dirfd(directory, create=True)
    temp_name = '.tmp.' + request + '.' + str(os.getpid()) + '.' + str(time.time_ns())
    fd = None
    try:
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=dirfd)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.link(temp_name, final_name, src_dir_fd=dirfd, dst_dir_fd=dirfd, follow_symlinks=False)
        os.unlink(temp_name, dir_fd=dirfd)
        os.fsync(dirfd)
        verify_fd = os.open(final_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
        try:
            meta = os.fstat(verify_fd)
            if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size != len(raw):
                raise ReadHold('RECEIPT_READBACK_METADATA')
            digestor = hashlib.sha256()
            observed = bytearray()
            while len(observed) <= 65536:
                part = os.read(verify_fd, min(65536, 65537 - len(observed)))
                if not part:
                    break
                observed.extend(part)
            if bytes(observed) != raw:
                raise ReadHold('RECEIPT_READBACK_CONTENT')
            receipt_sha = digest(bytes(observed))
        finally:
            os.close(verify_fd)
        return {'path': str(Path(directory) / final_name), 'sha256': receipt_sha, 'bytes': len(raw), 'mode': '0600'}
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temp_name, dir_fd=dirfd)
        except OSError:
            pass
        raise
    finally:
        os.close(dirfd)


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if (not re.fullmatch(r'[0-9]{1,24}', request)
            or not re.fullmatch(r'[a-f0-9]{40}', source_sha)):
        raise ReadHold('OWNER_CONTEXT_REQUIRED')
    receipt = _evidence_receipt(request, source_sha, time.time())
    written = write_admission_receipt(receipt)
    receipt['receipt'] = written
    print('NOX_MAINT_TRAINING_ADMISSION_PREFLIGHT=' + json.dumps(receipt, sort_keys=True, allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    main()
