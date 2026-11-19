#!/usr/bin/env python3
"""Restore the second unactivated revision after its failed initial operation.

Source-only until an owner-reviewed primary diagnostic is supplied. This is a
separate post-start rollback, not the initial installer's exception handler.
No trainer start, checkpoint edit, model restart, evaluator, or flag-free
training interval is authorized. Failed-attempt evidence remains immutable.
"""
from __future__ import annotations

import base64
import copy
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
AREA = STATE / 'owner_qwen_execution_retry_rollbacks'
FAILED_AREA = STATE / 'owner_qwen_execution_revisions/6912442714'
REFERENCE = {'request': '6912442714', 'source_sha': '7e27ab2ce0673205701727f4d3ef3f4a59b3d096',
             'receipt_sha256': 'c7304317a76fe08869eec9b6127ffd51107d69698e8b0ea678ae7c0f8d1e2858'}
DESCRIPTOR_SHA = '87bba8dde971ac6d3f80c1658fc0c4117f7623329d5131acc711d1775aebaca2'
OPERATION_SHA = '77dc5780f32f5ea6095151c6718a062f873e0c7d6ce9e6bbe022b32c7b4b3230'
DIAGNOSTIC_SOURCE_SHA = 'fba9af47f00030789a783ff1f62496868eb9452f1c0cbc6397053c2657f3da9a'
DIAGNOSTIC_SHA = '1f1e0554cb45ae1b17d6b433e8c450f51e67032c65814a9c93390239c452d696'
BOOTSTRAP_DEADLINE = 1794822837.278083
OPERATION_REASON = 'HOLD_QWEN_REVISION_INSTALL_NEW_HOLD_OR_PAUSE'
PRIMARY_DIAGNOSIS = 'HOLD_MEMFD_PUBLIC_DOWNLOAD_INTERRUPTED'
DIAGNOSTIC_ASSET = 'owner_qwen_retry_failed_diagnostic.json'
SCHEMA = 'NOX_QWEN_RETRY_HELD_ROLLBACK_V1'
REVIEW_SCHEMA = 'NOX_QWEN_RETRY_ROLLBACK_REVIEW_V1'
PINS = {
    'owner_qwen_revision_install.py': '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468',
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_qwen_disk_rearm_entry.py': 'd7017fecab20dab1dc833b2509b14850d4a65151682031143c23e5596c9b8f38',
}
CURRENT_SOURCES = {
    'nox_dispatcher_t855u.py': '9d331c825a36fa2933d4515b73615763247b28d2b4704fd412ed56d1557deb5d',
    'owner_hermes_hydrate.py': '65daf1acd5dd937e23b9f960dedb720b8259793729115bab153993a282e735a3',
    'owner_qwen_execution_revision.py': '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e',
    'owner_qwen_handback_retry.py': '70784355b8458d67f5de0a15b2cce4aaf225fa2522fe90b09f359372ee95fc39',
    'owner_qwen_media_guard.py': 'c0feb873174e776285563fdb0290a4b1064402d33c3c05c58d847531690d7723',
    'owner_qwen_media_handoff.py': 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce',
    'owner_qwen_training_guard.py': '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656',
    'owner_training_status.py': 'c643fe595e09036302818da8e780269ab2e1b48451025b33cb9b491a911eb879',
    'qwen_student_training_entry_revision.py': '530b59ee1723c5d6279dd8523d3f090c07e984561103d567b2de2b552d1108a9',
    'owner_qwen_revision_install.py': PINS['owner_qwen_revision_install.py'],
}
CURRENT_FLAGS = {
    'TRAIN_HOLD.flag': '4242ff43f2d536740d4793fd832dca5ea7a89b18b50c5352ebe659c4bc36a16b',
    'TRAIN_PAUSE_REQUEST.flag': '1f9d55be4763f92cc603c44c80ff50be4fa311d1b30d2b046ba03bea7eff25c5',
}
MODEL = {'pid': 7637, 'starttime': '149189867', 'pgrp': 7059}
MIB = 1024 ** 2
PRIMARY_SECONDS = 360
RECOVERY_SECONDS = 180
SHA = re.compile('[a-f0-9]{64}')
CODE = re.compile('(HOLD|WAIT)_[A-Z0-9_]{1,150}')


class RollbackHold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise RollbackHold('HOLD_QWEN_REVISION_ROLLBACK_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def safe(exc):
    value = str(exc)
    return value if CODE.fullmatch(value) else 'HOLD_QWEN_REVISION_ROLLBACK_' + type(exc).__name__.upper()


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'PATH')
    return path


def identity(info, moved=False):
    keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns')
    if not moved:
        keys += ('st_ctime_ns',)
    return tuple(getattr(info, key) for key in keys)


def read(path, maximum=2 * MIB, *, expected=None, private=False):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and not stat.S_IMODE(before.st_mode) & 0o022
                and 0 <= before.st_size <= maximum, 'FILE_SCOPE')
        if private:
            require(stat.S_IMODE(before.st_mode) == 0o600, 'PRIVATE_MODE')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    require(expected is None or digest(raw) == expected, 'FILE_SHA')
    return raw


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'JSON_DUPLICATE'); value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT'); encode(value)
    return value


def document(path, maximum=2 * MIB, **kwargs):
    raw = read(path, maximum, **kwargs)
    return parse(raw), raw


def sync_dir(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_dir(path):
    path = plain(path)
    if not path.exists():
        path.mkdir(mode=0o700); sync_dir(path.parent)
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')


def create(path, raw, mode=0o600):
    fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), mode); stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        saved = identity(os.fstat(stream.fileno()))
    sync_dir(path.parent)
    require(read(path, max(len(raw), 1), private=mode == 0o600) == raw
            and identity(path.stat(follow_symlinks=False)) == saved, 'CREATE_READBACK')


def replace(path, before, after, mode, *, expected_identity=None, prepared=None):
    require(read(path, max(len(before), 1)) == before, 'REPLACE_PREIMAGE')
    observed_identity = identity(path.stat(follow_symlinks=False), moved=True)
    require(expected_identity is None or observed_identity == expected_identity, 'REPLACE_IDENTITY')
    fd, temporary = tempfile.mkstemp(prefix='.qwen-held-restore-', dir=plain(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode); stream.write(after); stream.flush(); os.fsync(stream.fileno())
            after_identity = identity(os.fstat(stream.fileno()), moved=True)
        if prepared:
            prepared(after_identity)  # durable postimage inode before the atomic replacement
        require(read(path, max(len(before), 1)) == before
                and identity(path.stat(follow_symlinks=False), moved=True) == observed_identity, 'REPLACE_CHANGED')
        os.replace(temporary, plain(path)); sync_dir(path.parent)
        require(read(path, max(len(after), 1)) == after
                and identity(path.stat(follow_symlinks=False), moved=True) == after_identity, 'REPLACE_READBACK')
        return after_identity
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def rename_noreplace(source, destination):
    """One exact same-filesystem move; no overwrite or copy/unlink fallback."""
    source, destination = plain(source), plain(destination)
    first = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    second = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(os.fstat(first).st_dev == os.fstat(second).st_dev, 'ARCHIVE_FILESYSTEM')
        libc = ctypes.CDLL(None, use_errno=True)
        function = getattr(libc, 'renameat2', None)
        require(function is not None, 'NOREPLACE_UNAVAILABLE')
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        if function(first, os.fsencode(source.name), second, os.fsencode(destination.name), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(second); os.close(first)


def loaded(name, raw):
    value = types.ModuleType('_nox_held_rollback_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name); sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def bundle(name, expected, maximum=131072):
    text = BUNDLE.get(name)
    require(isinstance(text, str) and len(text) <= (maximum * 4 // 3 + 8), 'BUNDLE_BOUND')
    raw = base64.b64decode(text, validate=True)
    require(0 < len(raw) <= maximum and digest(raw) == expected, 'BUNDLE_PIN')
    return raw


def review_gate(value):
    keys = {'schema', 'execution_revision', 'diagnostic_sha256', 'diagnostic_source_sha256',
            'operation_receipt_sha256', 'finalize_receipt_absent', 'expected_operation_reason', 'primary_diagnosis_reviewed',
            'primary_diagnosis_code'}
    require(isinstance(value, dict) and set(value) == keys and value['schema'] == REVIEW_SCHEMA
            and value['execution_revision'] == REFERENCE and value['primary_diagnosis_reviewed'] is True
            and value['diagnostic_source_sha256'] == DIAGNOSTIC_SOURCE_SHA
            and value['diagnostic_sha256'] == DIAGNOSTIC_SHA
            and value['operation_receipt_sha256'] == OPERATION_SHA and value['finalize_receipt_absent'] is True
            and value['expected_operation_reason'] == OPERATION_REASON
            and value['primary_diagnosis_code'] == PRIMARY_DIAGNOSIS, 'PRIMARY_DIAGNOSIS_REVIEW_REQUIRED')
    raw = bundle(DIAGNOSTIC_ASSET, value['diagnostic_sha256'], 131072)
    diagnostic = parse(raw)
    operation = diagnostic.get('operation_result') or {}
    require(diagnostic.get('schema') == 'NOX_QWEN_EXECUTION_REVISION_DIAGNOSTIC_V1'
            and diagnostic.get('state') == 'DIAGNOSTIC_OBSERVED'
            and diagnostic.get('observation_complete') is True and diagnostic.get('read_only') is True
            and diagnostic.get('execution_revision') == REFERENCE
            and diagnostic.get('source_and_origin_pins_verified') is True
            and diagnostic.get('files_written') == diagnostic.get('service_actions') == 0
            and diagnostic.get('finalize_receipt') == {'present': False}
            and operation.get('present') is True and operation.get('sha256') == OPERATION_SHA
            and operation.get('state') == 'HOLD_QWEN_EXECUTION_REVISION_INSTALL'
            and operation.get('reason') == value['expected_operation_reason']
            and operation.get('optimizer_permission_issued') is False, 'DIAGNOSTIC_SCOPE')
    require(diagnostic.get('activation', {}).get('active') is False
            and diagnostic.get('activation', {}).get('deadline') == BOOTSTRAP_DEADLINE
            and diagnostic.get('trainer', {}).get('service') == {'state': 'FATAL', 'pid': None}
            and diagnostic.get('trainer', {}).get('process_identity') is None, 'DIAGNOSTIC_TRAINER_NOT_DEAD')
    for name, pin in CURRENT_FLAGS.items():
        row = diagnostic.get('flags', {}).get(name) or {}
        require(row.get('present') is True and row.get('sha256') == pin
                and row.get('ownership') == ('OWNED_CURRENT_WINDOW_FAILURE' if name == 'TRAIN_HOLD.flag'
                                             else 'OWNED_CURRENT_REVISION_PAUSE'), 'DIAGNOSTIC_FLAG_SCOPE')
    stdout = [row for row in diagnostic.get('log_diagnostics', [])
              if isinstance(row, dict) and row.get('stream') == 'stdout']
    started = diagnostic.get('operation_result', {}).get('started_at')
    finished = operation.get('finished_at')
    require(len(stdout) == 1 and type(started) in (int, float) and math.isfinite(started)
            and type(finished) in (int, float) and math.isfinite(finished) and 0 < started <= finished,
            'DIAGNOSTIC_CURRENT_ATTEMPT_TIMING')
    events = stdout[0].get('safe_events'); modified = stdout[0].get('mtime_ns')
    require(type(modified) is int and int(started * 1_000_000_000) <= modified <= int(finished * 1_000_000_000)
            and isinstance(events, list) and events and events[-1] == {'state': PRIMARY_DIAGNOSIS}
            and PRIMARY_DIAGNOSIS in stdout[0].get('hold_codes', []), 'DIAGNOSTIC_CURRENT_DOWNLOAD_FAILURE')
    return copy.deepcopy(value), diagnostic, raw


def current_flags(core, expected_reason):
    core.global_stop()
    result = {name: read(STATE / name, 4096, expected=pin, private=True) for name, pin in CURRENT_FLAGS.items()}
    require(result['TRAIN_HOLD.flag'] == ('OWNER_QWEN_WINDOW_FAILED request=' + REFERENCE['request'] + ' goal=1000\n').encode(), 'CURRENT_HOLD_OWNER')
    require(result['TRAIN_PAUSE_REQUEST.flag'] == ('NOX_QWEN_EXECUTION_REVISION_PAUSE request=' + REFERENCE['request']
            + ' reason=' + expected_reason + '\n').encode(), 'CURRENT_PAUSE_OWNER')
    return result


def no_trainer(core, ctx):
    seen = core.trainer(ctx)
    require(seen == {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}, 'EXACT_DEAD_TRAINER')
    return seen


def media_idle(runtime, core):
    value = runtime.queue_ids()
    require(isinstance(value, dict) and set(value) == {'queue_running', 'queue_pending'}
            and all(type(v) is list and len(v) == 0 for v in value.values()), 'MEDIA_ENGINE_NOT_IDLE')
    core.queue_idle()
    queue, _ = core.document(STATE / 'dispatcher/state.json', 16 * MIB)
    for row in queue['tasks'].values():
        if row.get('status') in ('pending', 'running'):
            require(row.get('handler') not in ('owner_media', 'owner_media_resume')
                    and not any(str(item).lower() == 'gpu1' for item in row.get('locks', [])), 'PENDING_MEDIA_OR_GPU1')
    yielded = STATE / 'media/training_yield.json'
    if yielded.exists() or yielded.is_symlink():
        record, _ = document(yielded, 65536)
        require(record.get('active') is False, 'ACTIVE_MEDIA_YIELD')


def absent_finalizer_and_activation():
    """Absence is an explicit branch, never a fabricated finalizer receipt."""
    with os.scandir(plain(FAILED_AREA)) as entries:
        for index, row in enumerate(entries):
            require(index < 64, 'FAILED_AREA_BOUND')
            require(not row.name.startswith('finalize-'), 'UNREVIEWED_FINALIZER_PRESENT')
            require(row.name != 'activation.json', 'ACTIVATION_EXISTS')


def native_diagnosis(core, ctx, approved, diagnostic):
    require(approved['finalize_receipt_absent'] is True
            and diagnostic.get('finalize_receipt') == {'present': False}, 'NO_FINALIZER_BRANCH')
    absent_finalizer_and_activation()
    operation, operation_raw = document(FAILED_AREA / 'operation_result.json', expected=OPERATION_SHA, private=True)
    require(operation.get('schema') == core.SCHEMA and operation.get('execution_revision') == REFERENCE
            and operation.get('request') == REFERENCE['request'] and operation.get('source_sha') == REFERENCE['source_sha']
            and operation.get('descriptor_sha256') == DESCRIPTOR_SHA
            and operation.get('state') == 'HOLD_QWEN_EXECUTION_REVISION_INSTALL'
            and operation.get('reason') == approved['expected_operation_reason']
            and operation.get('start_command_issued') is True and operation.get('start_command_returncode') == 0
            and operation.get('optimizer_permission_issued') is False, 'NATIVE_FAILED_OPERATION_SCOPE')
    pause = operation.get('checkpoint_pause') or {}
    require(pause.get('state') == 'CHECKPOINT_PAUSE_REQUESTED'
            and pause.get('sha256') == CURRENT_FLAGS['TRAIN_PAUSE_REQUEST.flag'], 'OPERATION_FLAG_PROOF')
    observed = diagnostic['operation_result']
    require(operation.get('started_at') == observed.get('started_at')
            and operation.get('finished_at') == observed.get('finished_at'), 'OPERATION_TIMING_CHANGED')
    absent_finalizer_and_activation()
    return {'operation_result.json': operation_raw}


def checkpoint_inventory(core, ctx):
    """Bounded metadata proof of no saved/orphan revision state; no payload edits.

    A latest pointer alone cannot rule out a save that failed before pointer or
    ledger publication. Inspect both the finite ledger and checkpoint folders,
    and refuse even an incomplete .checkpoint-* folder. Historical payload
    hashes are not re-claimed as verified by this metadata-only inventory.
    """
    deadline = time.monotonic() + 10
    consumed = 0
    def metadata(path, maximum):
        nonlocal consumed
        core.global_stop(); require(time.monotonic() < deadline, 'CHECKPOINT_INVENTORY_TIME')
        raw = read(path, maximum); consumed += len(raw)
        require(consumed <= 4 * MIB, 'CHECKPOINT_INVENTORY_BYTES')
        return parse(raw), raw
    def folders():
        result = {}
        with os.scandir(plain(OUTPUT)) as entries:
            for index, row in enumerate(entries):
                require(index < 256 and time.monotonic() < deadline, 'CHECKPOINT_INVENTORY_BOUND')
                require(not row.name.startswith('.checkpoint-'), 'INCOMPLETE_CHECKPOINT_PRESENT')
                if not row.name.startswith('checkpoint-'):
                    continue
                require(re.fullmatch('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}', row.name), 'CHECKPOINT_INVENTORY_NAME')
                info = row.stat(follow_symlinks=False)
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                        and not stat.S_IMODE(info.st_mode) & 0o022, 'CHECKPOINT_INVENTORY_DIRECTORY')
                result[row.name] = identity(info)
        return result
    before = folders()
    ledger, ledger_raw = metadata(OUTPUT / 'owner_checkpoints.json', 2 * MIB)
    rows = ledger.get('checkpoints')
    require(ledger.get('schema') == 'NOX_QWEN_OWNED_CHECKPOINTS_V1'
            and ledger.get('lineage_sha256') == core.ORIGIN_LINEAGE
            and isinstance(rows, list) and 0 < len(rows) <= 2000, 'CHECKPOINT_LEDGER_SCOPE')
    names = set(); retained = {}; snapshots = []
    for row in rows:
        require(isinstance(row, dict) and re.fullmatch('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}', str(row.get('directory')))
                and SHA.fullmatch(str(row.get('manifest_sha256'))) and type(row.get('retained')) is bool,
                'CHECKPOINT_LEDGER_ROW')
        name = row['directory']; good, attempted = row.get('successful_total'), row.get('attempted_total')
        require(name not in names and type(good) is int and type(attempted) is int
                and 0 <= good <= attempted <= 25 and int(name[12:20]) == good and int(name[22:30]) == attempted
                and 'execution_binding' not in row, 'NEW_CHECKPOINT_LEDGER_EVIDENCE')
        require(good < 25 or name == core.ANCHOR['directory']
                and row['manifest_sha256'] == core.ANCHOR['manifest_sha256'], 'NEW_SAME_COUNTER_CHECKPOINT')
        names.add(name)
        if row['retained']:
            retained[name] = row
    require(set(before) == set(retained) and core.ANCHOR['directory'] in retained, 'ORPHAN_OR_MISSING_CHECKPOINT')
    certificate = ctx['certificate']; accepted = Path(certificate['checkpoint'])
    require(accepted.parent == OUTPUT and accepted.name in retained
            and retained[accepted.name]['manifest_sha256'] == certificate['checkpoint_manifest_sha256'], 'ACCEPTED_SIX_DIRECTORY')
    for name, row in sorted(retained.items()):
        manifest, manifest_raw = metadata(OUTPUT / name / 'checkpoint_manifest.json', 65536)
        require(digest(manifest_raw) == row['manifest_sha256']
                and manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1'
                and manifest.get('directory') == name and manifest.get('lineage_sha256') == core.ORIGIN_LINEAGE
                and manifest.get('successful_total') == row['successful_total']
                and manifest.get('attempted_total') == row['attempted_total']
                and 'execution_binding' not in manifest, 'REVISION_CHECKPOINT_OR_FOREIGN_MANIFEST')
        saved, saved_raw = metadata(OUTPUT / name / 'student_state.json', 2 * MIB)
        require(digest(saved_raw) == (manifest.get('files_sha256') or {}).get('student_state.json')
                and saved.get('successful_total') == row['successful_total']
                and saved.get('attempted_total') == row['attempted_total']
                and saved.get('holdout_evaluated_successful_total') <= row['successful_total']
                and 'execution_binding' not in saved and 'last_evaluation_witness' not in saved,
                'REVISION_CHECKPOINT_OR_FOREIGN_STATE')
        snapshots.append({'directory': name, 'manifest_sha256': digest(manifest_raw),
                          'state_sha256': digest(saved_raw), 'successful_total': row['successful_total']})
    require(read(OUTPUT / 'owner_checkpoints.json', 2 * MIB) == ledger_raw
            and folders() == before, 'CHECKPOINT_INVENTORY_CHANGED')
    snapshot = encode({'ledger_sha256': digest(ledger_raw), 'folders': before, 'metadata': snapshots})
    return {'summary': {'metadata_only': True, 'ledger_entries': len(rows), 'retained_checkpoints': len(before),
                        'no_new_revision_checkpoint_metadata_observed': True, 'incomplete_checkpoint_folders': 0,
                        'inventory_sha256': digest(snapshot)}, 'snapshot': snapshot, 'ledger_raw': ledger_raw}


def policy_same(value, original):
    keys = ('inhibit', 'reason', 'latched_at', 'last_successful_updates', 'last_evaluation_update',
            'best_holdout_loss', 'regression_streak', 'observed_distinct_evaluations')
    return all(value.get(key) == original.get(key) for key in keys)


def plan_restore(core, shared, ctx, prepared):
    """Exact fixed-path beforeimages; bytes and declared modes are distinct."""
    before_sources = {name: read(FAILED_AREA / 'source_before' / name, expected=pin, private=True)
                      for name, pin in core.OLD_SOURCES.items()}
    before_configs = {name: read(FAILED_AREA / 'config_before' / name, 32768, expected=pin, private=True)
                      for name, pin in core.CONFIG_PINS.items()}
    historical_admission = read(FAILED_AREA / 'previous_admission.json', 64000, expected=core.OLD_ADMISSION, private=True)
    historical_wrapper = read(FAILED_AREA / 'previous_wrapper.sh', expected=core.OLD_WRAPPER, private=True)
    read(FAILED_AREA / 'previous_entry.py', expected=core.OLD_ENTRY, private=True)
    guard_before, guard_before_raw = document(FAILED_AREA / 'guard_before.json', 65536, private=True)
    original_policy, policy_raw = document(FAILED_AREA / 'guard_policy_before.json', 65536, private=True)
    old_guard = loaded(core.GUARD, before_sources[core.GUARD])
    old_config = parse(before_configs['owner_qwen_training_guard.json'])
    origin_ctx = shared.historical_context(FAILED_AREA)
    origin_ctx.update(lineage_sha256=core.ORIGIN_LINEAGE, admission_sha256=core.OLD_ADMISSION,
                      wrapper_sha256=core.OLD_WRAPPER, context=core.ORIGIN)
    require(guard_before.get('bindings') == old_guard.bindings(old_config, digest(before_configs['owner_qwen_training_guard.json']), origin_ctx), 'ORIGIN_GUARD_BINDING')
    old_cp = old_guard.checkpoint_metadata(origin_ctx)
    require(core.migration_policy(old_guard, guard_before, old_cp) == original_policy, 'ORIGIN_POLICY_ARCHIVE')
    require(digest(policy_raw) == prepared['operation']['original_guard_policy_sha256'], 'ORIGIN_POLICY_SHA')
    target_flags = {name: read(FAILED_AREA / ('before-' + name), 4096, expected=pin, private=True)
                    for name, pin in core.FLAGS.items()}
    require(target_flags['TRAIN_PAUSE_REQUEST.flag'] == old_guard.pause_token(guard_before), 'ORIGIN_FLAG_BINDING')
    new_guard = loaded(core.GUARD, read(SCRIPTS / core.GUARD, expected=CURRENT_SOURCES[core.GUARD]))
    config, config_sha = new_guard.checked_config(REFERENCE, CURRENT_SOURCES[core.GUARD])
    guard_ctx = new_guard.context_evidence(config)
    current_guard, current_guard_raw = document(new_guard.STATUS, 65536, private=True)
    require(current_guard.get('bindings') == new_guard.bindings(config, config_sha, guard_ctx)
            and current_guard.get('state') in ('BOOTSTRAP_EVALUATION', 'INHIBITED')
            and policy_same(current_guard.get('policy_state') or {}, original_policy)
            and current_guard.get('checkpoint') == new_guard.checkpoint_metadata(guard_ctx), 'CURRENT_GUARD_POLICY')
    # Reconstruct only the actual initial revision's deterministic postimages.
    media = loaded('owner_qwen_media_handoff.py', read(SCRIPTS / 'owner_qwen_media_handoff.py', expected=CURRENT_SOURCES['owner_qwen_media_handoff.py']))
    status = loaded('owner_training_status.py', read(SCRIPTS / 'owner_training_status.py', expected=CURRENT_SOURCES['owner_training_status.py']))
    hydrate = loaded('owner_hermes_hydrate.py', read(SCRIPTS / 'owner_hermes_hydrate.py', expected=CURRENT_SOURCES['owner_hermes_hydrate.py']))
    rendered = {
        'owner_qwen_training_guard.json': new_guard.make_revision_guard_config(old_config, REFERENCE, CURRENT_SOURCES[core.GUARD]),
        'owner_qwen_media_handoff.json': media.make_revision_media_config(parse(before_configs['owner_qwen_media_handoff.json']), REFERENCE, source_sha256=CURRENT_SOURCES['owner_qwen_media_handoff.py']),
        'owner_training_status.json': status.make_revision_status_config(parse(before_configs['owner_training_status.json']), REFERENCE),
        'owner_hermes_warm.json': hydrate.make_revision_hydrate_manifest(parse(before_configs['owner_hermes_warm.json']), REFERENCE,
            source_sha256=CURRENT_SOURCES['owner_hermes_hydrate.py'], runtime_entry_sha256=CURRENT_SOURCES[core.STUDENT]),
    }
    rows = []
    def add(label, path, current, restored, mode):
        require(read(path, max(len(current), 1)) == current, 'PLAN_PREIMAGE')
        rows.append({'label': label, 'path': path, 'before': current, 'after': restored,
                     'declared_mode': mode, 'before_mode': stat.S_IMODE(path.stat().st_mode),
                     'before_identity': identity(path.stat(), moved=True), 'intent': False, 'applied': False})
    for name, restored in before_sources.items():
        add('source-' + name, SCRIPTS / name, read(SCRIPTS / name, expected=CURRENT_SOURCES[name]), restored, 0o644)
    for name, value in rendered.items():
        add('config-' + name, ROOT / 'config' / name, core.encode(value), before_configs[name], 0o600)
    read(ROOT / 'config/owner_media_runtime.json', expected=core.CONFIG_PINS['owner_media_runtime.json'])
    add('training-admission.json', shared.ADMISSION, ctx['raw'], historical_admission, 0o600)
    add('training-wrapper.sh', shared.WRAPPER, ctx['wrapper'], historical_wrapper, 0o700)
    add('guard-state.json', new_guard.STATUS, current_guard_raw, guard_before_raw, 0o600)
    for name, restored in target_flags.items():
        add(name, STATE / name, prepared['flags'][name], restored, 0o600)
    for name in (core.SHARED, core.STUDENT, core.SELF):
        add('retired-' + name, SCRIPTS / name, read(SCRIPTS / name, expected=CURRENT_SOURCES[name]), None, None)
    execution_cfg = {'schema': shared.CONFIG_SCHEMA, 'enabled': True, 'source_sha256': CURRENT_SOURCES[core.SHARED], 'execution_revision': REFERENCE}
    add('retired-execution-config.json', shared.CONFIG, shared.encode(execution_cfg), None, None)
    return rows, old_guard, original_policy, origin_ctx


def plan_projection(rows):
    return [{'label': row['label'], 'before_sha256': digest(row['before']),
             'after_sha256': digest(row['after']) if row['after'] is not None else None,
             'before_observed_mode': row['before_mode'], 'declared_restored_mode': row['declared_mode'],
             'before_identity': row['before_identity'],
             'mode_is_historical_metadata_proof': False, 'move_to_private_archive': row['after'] is None}
            for row in rows]


def precheck_rows(rows, *, original_only=False):
    for row in rows:
        path = row['path']; current = read(path, max(len(row['before']), len(row['after'] or b''), 1)) if path.exists() or path.is_symlink() else None
        allowed = (row['before'],) if original_only else (row['before'], row['after'])
        require(current in allowed, 'FOREIGN_TARGET_CHANGED')
        if current is not None:
            actual_identity = identity(path.stat(follow_symlinks=False), moved=True)
            if current == row['before']:
                require(actual_identity == row['before_identity'] or not original_only
                        and actual_identity == row.get('compensated_identity'), 'FOREIGN_TARGET_IDENTITY')
            else:
                require(actual_identity == row.get('after_identity'), 'FOREIGN_POSTIMAGE_IDENTITY')
        if row['after'] is None and current is None:
            archive = row['archive']
            require(read(archive, max(len(row['before']), 1)) == row['before']
                    and identity(archive.stat(), moved=True) == row['before_identity'], 'MOVED_ARCHIVE_CHANGED')


def apply_row(row, save):
    row['intent'] = True; save()
    if row['after'] is None:
        require(read(row['path'], max(len(row['before']), 1)) == row['before']
                and identity(row['path'].stat(), moved=True) == row['before_identity'], 'RETIRE_PREIMAGE')
        rename_noreplace(row['path'], row['archive'])
        row['applied'] = True  # latch before fsync/readback, which may fail
        sync_dir(row['path'].parent); sync_dir(row['archive'].parent)
        require(read(row['archive'], max(len(row['before']), 1)) == row['before']
                and identity(row['archive'].stat(), moved=True) == row['before_identity'], 'RETIRE_READBACK')
    else:
        def prepared(new_identity):
            row['after_identity'] = new_identity; save()
        replace(row['path'], row['before'], row['after'], row['declared_mode'],
                expected_identity=row['before_identity'], prepared=prepared)
        row['applied'] = True
    save()


def compensate_rows(rows, save=lambda: None):
    precheck_rows(rows)
    for row in reversed(rows):
        path = row['path']
        if path.exists() or path.is_symlink():
            current = read(path, max(len(row['before']), len(row['after'] or b''), 1))
            if current == row['before']:
                continue
            require(row['after'] is not None and current == row['after'], 'COMPENSATION_FOREIGN_TARGET')
            def prepared(new_identity):
                row['compensated_identity'] = new_identity; save()
            replace(path, row['after'], row['before'], row['before_mode'],
                    expected_identity=row['after_identity'], prepared=prepared)
        else:
            require(row['after'] is None and read(row['archive'], max(len(row['before']), 1)) == row['before'], 'COMPENSATION_ARCHIVE')
            require(identity(row['archive'].stat(), moved=True) == row['before_identity'], 'COMPENSATION_INODE')
            rename_noreplace(row['archive'], path)
            sync_dir(path.parent); sync_dir(row['archive'].parent)
            require(read(path, max(len(row['before']), 1)) == row['before'], 'COMPENSATION_READBACK')


def stop_owned_services(core, deploy, helper, identities, result, save):
    result['dispatcher_stop_attempted'] = True; save()
    core.stop_dispatcher(helper, identities['dispatcher'])
    result['proxy_stop_attempted'] = True; save()
    deploy.stop_proxy(helper, identities['proxy'])


def restart_owned_services(core, deploy, helper, result, save):
    result['dispatcher_start_attempted'] = True; save()
    result['dispatcher_after'] = core.start_dispatcher(helper); save()
    result['proxy_start_attempted'] = True; save()
    result['proxy_after'] = deploy.start_proxy(helper); save()


def stop_settled_for_compensation(core, deploy, helper, identities, result):
    stop_plan = []
    for name, key in ((core.DISPATCHER_SERVICE, 'dispatcher'), (core.PROXY_SERVICE, 'proxy')):
        if not result.get(key + '_stop_attempted'):
            continue
        state = helper.service_state(name)['state']
        require(state in ('RUNNING', 'STOPPED', 'EXITED')
                or state == 'FATAL' and result.get(key + '_start_attempted') is True, 'UNSETTLED_CONTROLLER')
        if state == 'RUNNING':
            current = core.service_identity(helper, name, core.DISPATCHER) if key == 'dispatcher' else deploy.proxy_identity(helper)
            require(current == identities[key] or current == result.get(key + '_after'), 'FOREIGN_CONTROLLER')
            stop_plan.append((key, current))
    # Classify both services before stopping either healthy controller.
    for key, current in stop_plan:
        if key == 'dispatcher':
            core.stop_dispatcher(helper, current)
        else:
            deploy.stop_proxy(helper, current)


def held_postcondition(core, guard, policy, rows, *, fresh_after=None):
    for row in rows:
        if row['after'] is None:
            require(not row['path'].exists() and not row['path'].is_symlink(), 'RETIRED_SOURCE_REAPPEARED')
        else:
            # The ordinary guard legitimately resamples only this one record.
            if fresh_after is None or row['label'] != 'guard-state.json':
                require(read(row['path'], max(len(row['after']), 1)) == row['after'], 'RESTORED_BYTES_CHANGED')
            require(stat.S_IMODE(row['path'].stat().st_mode) == row['declared_mode'], 'DECLARED_MODE_CHANGED')
    config, config_sha = guard.checked_config(core.ORIGIN, core.OLD_SOURCES[core.GUARD])
    ctx = guard.context_evidence(config)
    row, raw = document(guard.STATUS, 65536, private=True)
    checkpoint = guard.checkpoint_metadata(ctx)
    require(row.get('bindings') == guard.bindings(config, config_sha, ctx)
            and row.get('state') == 'INHIBITED' and policy_same(row.get('policy_state') or {}, policy)
            and row.get('checkpoint') == checkpoint, 'RESTORED_HELD_GUARD')
    core.migration_policy(guard, row, checkpoint)
    require(core.exact_flags() and ctx['observer'].service() == {'state': 'FATAL', 'pid': None}, 'RESTORED_TRAINER_CHANGED')
    window = guard.module('owner_qwen_window_entry.py'); helper = guard.module('owner_qwen_install_entry.py')
    argv = window.arguments(helper, ctx['profile'], core.ORIGIN['request'], core.OLD_ADMISSION, 1000, resume=True)
    require(not ctx['observer'].trainers(argv, ctx['observer'].service()), 'RESTORED_TRAINER_PRESENT')
    if fresh_after is not None:
        sampled = row.get('sampled_at')
        require(type(sampled) in (int, float) and fresh_after <= sampled <= time.time()
                and time.time() - sampled <= 30, 'ORDINARY_GUARD_SAMPLE_PENDING')
    return {'state': row['state'], 'reason': row['policy_state']['reason'], 'sha256': digest(raw),
            'successful_updates': checkpoint['successful_updates'], 'evaluated_at_update': checkpoint['evaluated_at_update']}


def main(reviewed_failure=None):
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    result = {'schema': SCHEMA, 'state': 'PREFLIGHT', 'request': request, 'source_sha': source,
              'failed_execution_revision': REFERENCE, 'trainer_start_calls': 0, 'optimizer_permission_issued': False,
              'evidence_branch': 'FAILED_INITIAL_OPERATION_WITHOUT_FINALIZER', 'finalizer_receipt_present': None,
              'checkpoints_modified': False, 'failed_attempt_receipt_modified': False,
              'declared_modes_are_original_metadata': False, 'main_chat_model_restarted': False,
              'private_content_exported': False, 'started_at': time.time()}
    controller = maintenance = forge = None; rows = []; ready = False; live_restored = False; success = False
    result_raw = None; archive = None; core = deploy = helper = shared = ctx = None
    identities = {}; evidence_snapshots = {}; original_signal = {}
    previous_timer = None; timer_started = None

    def save():
        nonlocal result_raw
        if not ready:
            return
        result['write_intents'] = [{'label': row['label'], 'intent': row['intent'], 'applied': row['applied'],
                                  'owned_postimage_identity': row.get('after_identity'),
                                  'compensated_identity': row.get('compensated_identity')} for row in rows]
        raw = encode(result); path = archive / 'result.json'
        if result_raw is None:
            create(path, raw)
        else:
            replace(path, result_raw, raw, 0o600)
        result_raw = raw

    def interrupted(_signum, _frame):
        raise RollbackHold('HOLD_QWEN_REVISION_ROLLBACK_BOUNDED_INTERRUPTION')

    def set_budget(seconds):
        remaining = previous_timer[0] - (time.monotonic() - timer_started) if previous_timer and previous_timer[0] else seconds
        require(remaining > 0, 'PARENT_DEADLINE_EXPIRED')
        signal.setitimer(signal.ITIMER_REAL, min(seconds, remaining))

    try:
        require(re.fullmatch('[0-9]{1,24}', request) and request != REFERENCE['request']
                and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_REQUEST')
        approved, diagnostic, diagnostic_raw = review_gate(reviewed_failure)
        previous_timer = signal.getitimer(signal.ITIMER_REAL); timer_started = time.monotonic()
        for sig in (signal.SIGTERM, signal.SIGALRM):
            original_signal[sig] = signal.getsignal(sig); signal.signal(sig, interrupted)
        set_budget(PRIMARY_SECONDS)
        modules = {name: loaded(name, bundle(name, pin)) for name, pin in PINS.items()}
        core, deploy, helper, rearm = (modules[name] for name in PINS)
        for name, pin in CURRENT_SOURCES.items():
            read(SCRIPTS / name, expected=pin)
        shared = loaded(core.SHARED, read(SCRIPTS / core.SHARED, expected=CURRENT_SOURCES[core.SHARED]))
        ctx = shared.current_context(REFERENCE)
        require(ctx['execution']['descriptor_sha256'] == DESCRIPTOR_SHA
                and ctx['execution']['directory'] == FAILED_AREA
                and ctx['execution']['descriptor']['bootstrap']['expires_at'] == BOOTSTRAP_DEADLINE, 'FAILED_CONTEXT')
        runtime = loaded('owner_media_runtime.py', read(SCRIPTS / 'owner_media_runtime.py', expected=core.PROTECTED['owner_media_runtime.py']))
        controller = core.acquire(STATE / 'media/controller.lock', 6)
        maintenance = core.acquire(STATE / 'owner_maintenance.lock', 6)
        forge = core.acquire(STATE / 'forge_training.lock', 6)
        core.global_stop(); core.protected(); no_trainer(core, ctx); media_idle(runtime, core)
        stopped_heavy = rearm.heavy_stopped(ctx['helper'])
        flags = current_flags(core, approved['expected_operation_reason'])
        evidence_snapshots = native_diagnosis(core, ctx, approved, diagnostic)
        result['finalizer_receipt_present'] = False
        require(shared.activation_status(ctx)['active'] is False, 'ACTIVATION_PRESENT')
        full, manifest, state = core.full_checkpoint(ctx, expected=core.ANCHOR,
            flags_check=lambda: current_flags(core, approved['expected_operation_reason']))
        binding = shared.checkpoint_binding(ctx, manifest, state, allow_initial_anchor=True)
        require(binding['legacy_anchor'] is True and full['successful_total'] == 25, 'ORIGINAL_ANCHOR_REQUIRED')
        inventory = checkpoint_inventory(core, ctx)
        require(deploy.model_identity(helper) == MODEL and deploy.slots_idle(), 'CHAT_IDENTITY_OR_BUSY')
        identities = {'dispatcher': core.service_identity(helper, core.DISPATCHER_SERVICE, core.DISPATCHER),
                      'proxy': deploy.proxy_identity(helper)}
        operation = parse(evidence_snapshots['operation_result.json'])
        rows, old_guard, original_policy, origin_ctx = plan_restore(core, shared, ctx, {'flags': flags, 'operation': operation})
        archive = AREA / request
        require(not archive.exists() and not archive.is_symlink(), 'ROLLBACK_REQUEST_REUSED')
        private_dir(AREA); private_dir(archive)
        private_dir(archive / 'failed_current'); private_dir(archive / 'retired')
        create(archive / 'reviewed_failure.json', encode(approved))
        create(archive / 'diagnostic.json', diagnostic_raw)
        create(archive / 'checkpoint_inventory.json', inventory['snapshot'])
        create(archive / 'checkpoint_ledger.json', inventory['ledger_raw'])
        for name, raw in evidence_snapshots.items():
            create(archive / name, raw)
        # Immutable attempt proofs are copied, never moved or overwritten.
        for name, pin in (('descriptor.json', DESCRIPTOR_SHA), ('admission_receipt.json', REFERENCE['receipt_sha256'])):
            raw = read(FAILED_AREA / name, expected=pin, private=True)
            create(archive / name, raw); evidence_snapshots[name] = raw
        for row in rows:
            create(archive / 'failed_current' / row['label'], row['before'])
            row['archive'] = archive / 'retired' / row['label']
        for name in ('owner_last_result.json', 'owner_progress.json'):
            path = OUTPUT / name
            if path.exists() or path.is_symlink():
                create(archive / ('observed-' + name), read(path))
        plan = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'failed_execution_revision': REFERENCE,
                'primary_diagnosis_code': approved['primary_diagnosis_code'], 'writes': plan_projection(rows),
                'evidence_branch': 'FAILED_INITIAL_OPERATION_WITHOUT_FINALIZER',
                'finalizer_receipt_present': False, 'failed_operation_sha256': OPERATION_SHA,
                'restore_semantics': 'EXPLICIT_ORIGINAL_HELD_STATE_NOT_LEARNING_REARM', 'full_original_checkpoint': full,
                'checkpoint_inventory': inventory['summary'],
                'declared_modes': {'sources': '0644', 'config_and_state': '0600', 'wrapper': '0700'},
                'historical_mode_metadata_preserved': False, 'failed_attempt_kept_immutable': True}
        create(archive / 'plan.json', encode(plan)); ready = True
        result.update(state='ARCHIVED_AND_PLAN_VERIFIED', plan_sha256=digest(encode(plan)),
                      primary_diagnosis_code=approved['primary_diagnosis_code'], checkpoint=full,
                      checkpoint_inventory=inventory['summary'], heavy_services=stopped_heavy)
        save()
        precheck_rows(rows, original_only=True); current_flags(core, approved['expected_operation_reason'])
        require(shared.current_context(REFERENCE)['raw'] == ctx['raw'], 'PRECOMMIT_CONTEXT_CHANGED')
        absent_finalizer_and_activation()
        no_trainer(core, ctx); media_idle(runtime, core); core.protected()
        require(checkpoint_inventory(core, ctx) == inventory, 'PRECOMMIT_CHECKPOINT_INVENTORY_CHANGED')
        stop_owned_services(core, deploy, helper, identities, result, save)
        # The existing held flags are atomically replaced with the archived
        # origin held tokens, never removed to admit training.
        for row in rows:
            core.global_stop(); apply_row(row, save)
        core.protected()
        absent_finalizer_and_activation()
        require(checkpoint_inventory(core, ctx) == inventory, 'RESTORED_CHECKPOINT_INVENTORY_CHANGED')
        held_postcondition(core, old_guard, original_policy, rows)
        result.update(state='ORIGINAL_HELD_FILES_RESTORED'); save()
        restart_owned_services(core, deploy, helper, result, save)
        require(deploy.model_identity(helper) == MODEL, 'MODEL_CHANGED_AFTER_RELOAD')
        health = helper.health(); require(all(health.get(str(port)) == 200 for port in (8080, 8081, 8082)), 'CORE_HEALTH')
        for name, raw in evidence_snapshots.items():
            require(read(FAILED_AREA / name, max(len(raw), 1)) == raw, 'FAILED_EVIDENCE_CHANGED')
        absent_finalizer_and_activation()
        live_restored = True
        released_at = time.time(); os.close(maintenance); maintenance = None
        deadline = time.monotonic() + 25
        while True:
            try:
                proof = held_postcondition(core, old_guard, original_policy, rows, fresh_after=released_at)
                break
            except RollbackHold as exc:
                if str(exc) != 'HOLD_QWEN_REVISION_ROLLBACK_ORDINARY_GUARD_SAMPLE_PENDING':
                    raise
                require(time.monotonic() < deadline, 'ORDINARY_GUARD_SAMPLE_PENDING'); time.sleep(.5)
        require(deploy.model_identity(helper) == MODEL, 'FINAL_MODEL_CHANGED')
        result.update(state='ORIGINAL_CHECKPOINT25_HELD_STATE_RESTORED', ordinary_guard=proof,
                      chat_health=health, active_chat=MODEL, failed_attempt_preserved=True,
                      training_flags_present=True, learning_rearm_performed=False,
                      initial_installer_reentry_not_executed=True)
        success = True
    except BaseException as exc:
        result.update(state='HOLD_QWEN_REVISION_ROLLBACK', reason=safe(exc))
        if ready and not live_restored and (result.get('dispatcher_stop_attempted') or any(row['intent'] for row in rows)):
            try:
                set_budget(RECOVERY_SECONDS)
                # All-file preflight precedes any recovery service action.
                precheck_rows(rows)
                no_trainer(core, ctx)
                stop_settled_for_compensation(core, deploy, helper, identities, result)
                compensate_rows(rows, save)
                require(shared.current_context(REFERENCE)['raw'] == ctx['raw'], 'COMPENSATED_CONTEXT')
                current_flags(core, reviewed_failure['expected_operation_reason'])
                if result.get('dispatcher_stop_attempted'):
                    result['dispatcher_after'] = core.start_dispatcher(helper)
                if result.get('proxy_stop_attempted'):
                    result['proxy_after'] = deploy.start_proxy(helper)
                require(deploy.model_identity(helper) == MODEL, 'COMPENSATED_MODEL_CHANGED')
                result['compensation'] = {'state': 'FAILED_ATTEMPT_HELD_STATE_RESTORED', 'trainer_started': False}
            except BaseException as failure:
                result['compensation'] = {'state': 'NOT_CONFIRMED', 'reason': safe(failure), 'trainer_started': False}
        elif live_restored:
            result['restored_files_retained'] = True
            result['ordinary_guard_acceptance_pending'] = True
    finally:
        if original_signal:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig, previous in original_signal.items():
                signal.signal(sig, previous)
            remaining = max(.001, previous_timer[0] - (time.monotonic() - timer_started)) if previous_timer[0] else 0
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])
        for fd in (forge, maintenance, controller):
            if fd is not None:
                os.close(fd)
        result['finished_at'] = time.time()
        if ready:
            try:
                save(); result['receipt_sha256'] = digest(result_raw)
            except BaseException as exc:
                success = False; result.update(state='HOLD_QWEN_REVISION_ROLLBACK_RECEIPT', reason=safe(exc))
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_retry_held_rollback', 'data': result},
              sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
