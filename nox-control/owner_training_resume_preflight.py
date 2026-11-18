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


def main():
    if (not re.fullmatch(r'[0-9]{1,24}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))):
        raise ReadHold('OWNER_CONTEXT_REQUIRED')
    result = observe()
    print('NOX_MAINT_TRAINING_RESUME_PREFLIGHT=' + json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
