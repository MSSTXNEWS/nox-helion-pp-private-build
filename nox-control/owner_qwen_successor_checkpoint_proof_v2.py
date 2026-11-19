#!/usr/bin/env python3
"""One bounded, read-only proof of exact CP55 after its admitted writer exited.

The current sealed execution reference is selected by the pinned shared verifier.
Only the exact native issuer's read-only definitions are used. No issuer main,
finalizer, guard tick, model import, service control, lock or file write occurs.
The quality HOLD and PAUSE remain present and byte/identity stable. The retained
checkpoint25 is metadata evidence, not a second full payload read. Historical
optimizer admission is never a current permission to resume the stopped trainer.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types


ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
INSTALLER = SCRIPTS / 'owner_qwen_revision_install.py'
INSTALLER_SHA = 'd562ff23fcf21fb0873a93e6e68b23f0dffa87db07e3fe309bed3e750d0080e6'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
STUDENT_SHA = '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03'
ANCHOR_SHA = 'c206cd9e7a1bacdc5d6dae261d7d775f41bd8f8d2a4986c7464a1b60cacdbf49'
SCHEMA = 'NOX_QWEN_SUCCESSOR_CHECKPOINT_AFTER_EXIT_PROOF_V2'
KIND = 'qwen_successor_checkpoint_after_exit_proof'
PREFIX = 'NOX_MAINT_REPAIR='
OWNER_UID = 0
BYTE_BOUND = 1024 ** 3
OUTER_SECONDS = 75
PROC = Path('/proc')
STATE = ROOT / 'state'
GUARD_NAME = 'owner_qwen_training_guard.py'
GUARD_SHA = 'd5217f5bdfe21418d6210a18faac8eef422e49009d8abbcd3e71a06988a8b06b'
WATCHER_SHA = '1012f4d17d61eff0e42d18e96b9b3211cd133a31e235ca062c7e18fcaa090f02'
EXPECTED_REFERENCE = {
    'request': '6916464880', 'source_sha': '7029c77906b512faaa9fd4b8290b122ee8c8f1f6',
    'receipt_sha256': 'ad3a760fac2eb56445a8e60dd19fe842ebc3d17dd26ea105485c0631fdf7ce86',
}
EXPECTED_PROCESS = {'pid': 1091069, 'start_ticks': 162502565,
    'boot_id': '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'}
EXPECTED_CHECKPOINT = {
    'directory': 'checkpoint-u00000055-a00000055-g01794833901774705882',
    'pointer_sha256': '192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0',
    'manifest_sha256': '458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65',
    'student_state_sha256': 'ca349563443f14cf02e6333cf7a593bf59b68a20ba1160e5388edb130f3fb2f8',
    'successful_total': 55, 'attempted_total': 55, 'skipped_total': 0,
    'evaluated_successful_total': 55, 'verified_bytes': 519936310,
}
FLAG_PINS = {
    'TRAIN_HOLD.flag': ('f5a62613348f1e4516a45dee4ee5eeb791fa9e6ca0c36f10be4414f3f5079866', 54),
    'TRAIN_PAUSE_REQUEST.flag': ('8316e6c12b6a8f53c60d3126fcc421542110e0e9e48848df205ac2c7eaff5aec', 195),
}
JOURNAL_PINS = {
    'watcher_ready.json': 'b02d6e1e1d88d1d95d052613fde264cf97f44e02d8c84b59244bf40ea9d2c023',
    'start_receipt.json': '1bc85f8b30c393698b5fa0ca0a4d7d2cec6c304fbfdd987899c0e9e5488f4db6',
    'watcher_result.json': 'ebe521becaa6d7da9a05d4482003233f762469674b873e428b96f2eb80664efb',
    'activation.json': '33a5789e7e32822e1653ce7973e32dc1c690bd64fc3bfb96e1b357f2a09d3dce',
}
EXPECTED_QUALITY = {
    'inhibit': True, 'reason': 'HOLDOUT_REGRESSION', 'complete': False,
    'last_successful_updates': 55, 'last_evaluation_update': 55,
    'evaluation_age_updates': 0, 'best_holdout_loss': 1.2216252349317074,
    'regression_streak': 2, 'observed_distinct_evaluations': 4,
    'latched_at': 1794833906.8669827,
}


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_QWEN_SUCCESSOR_PROOF_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def source(path, pin):
    path = Path(path)
    require(isinstance(pin, str) and re.fullmatch('[a-f0-9]{64}', pin), 'SOURCE_PIN')
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'SOURCE_PATH')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == OWNER_UID and first.st_nlink == 1
                and not first.st_mode & 0o022 and 0 < first.st_size <= 262144, 'SOURCE_METADATA')
        raw = stream.read(262145)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)) and digest(raw) == pin, 'SOURCE_CHANGED')
    return raw


def load(name, raw):
    module = types.ModuleType('_nox_successor_checkpoint_proof_' + name.removesuffix('.py'))
    module.__file__ = str(SCRIPTS / name)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def native_modules():
    core = load(INSTALLER.name, source(INSTALLER, INSTALLER_SHA))
    shared = load(core.SHARED, source(SCRIPTS / core.SHARED, SHARED_SHA))
    require(core.GIB == BYTE_BOUND and core.PINS[core.SHARED_ASSET] == SHARED_SHA
            and core.PINS[core.STUDENT_ASSET] == STUDENT_SHA, 'SOURCE_GRAPH')
    return core, shared


def checked_context(core, shared, reference=None):
    require(reference is None or reference == EXPECTED_REFERENCE, 'REFERENCE_SCOPE')
    ctx = shared.current_context(EXPECTED_REFERENCE)
    execution = ctx['execution']
    require(ctx['context'] == EXPECTED_REFERENCE and execution['reference'] == EXPECTED_REFERENCE
            and execution['verifier_sha256'] == SHARED_SHA
            and execution['runtime_entry_sha256'] == STUDENT_SHA
            and execution['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA
            and execution['descriptor']['activation_watcher_sha256'] == WATCHER_SHA
            and execution['descriptor']['consumer_sources'][GUARD_NAME] == GUARD_SHA
            and execution['descriptor']['anchor']['manifest_sha256'] == ANCHOR_SHA, 'CURRENT_GRAPH')
    core.protected()
    core.global_stop()
    return ctx


def exited(core, shared, ctx):
    """No admitted child and no PID reuse; do not signal or open its descriptors."""
    core.global_stop()
    row = core.trainer(ctx, required=False)
    require(row.get('process_identity') is None and row.get('service') == {'state': 'FATAL', 'pid': None},
            'TRAINER_NOT_STABLY_EXITED')
    require(shared.process_identity_valid(EXPECTED_PROCESS), 'EXPECTED_WRITER')
    boot = (PROC / 'sys/kernel/random/boot_id').read_bytes()
    require(len(boot) <= 128 and boot.strip() == EXPECTED_PROCESS['boot_id'].encode(), 'BOOT_CHANGED')
    try:
        (PROC / str(EXPECTED_PROCESS['pid'])).stat(follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        # Even a different start time is a reuse collision, never absence proof.
        require(False, 'WRITER_PID_PRESENT_OR_REUSED')
    return row


def active(shared, ctx):
    value = shared.activation_status(ctx)
    require(value.get('active') is True and value.get('bootstrap_pending') is False
            and value.get('permit_sha256') == JOURNAL_PINS['activation.json']
            and value.get('initial_process_identity') == EXPECTED_PROCESS
            and value.get('baseline_successful_total') == 25,
            'ACTIVATION_REQUIRED')
    return value


def private_snapshot(shared, path, maximum, expected):
    """Small fixed private records only; retain raw bytes solely for comparison."""
    path = shared.plain(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID
                and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                and 0 < before.st_size <= maximum, 'PRIVATE_RECORD_METADATA')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)) and digest(raw) == expected,
                'PRIVATE_RECORD_CHANGED')
    return {'raw': raw, 'identity': identity(before), 'sha256': expected, 'bytes': len(raw)}


def flag_snapshot(core, shared):
    core.global_stop()
    rows = {}
    for name, (pin, size) in FLAG_PINS.items():
        rows[name] = private_snapshot(shared, STATE / name, 4096, pin)
        require(rows[name]['bytes'] == size, 'FLAG_SIZE')
    require(rows['TRAIN_HOLD.flag']['raw'] == ('OWNER_QWEN_WINDOW_FAILED request='
            + EXPECTED_REFERENCE['request'] + ' goal=1000\n').encode(), 'HOLD_CURRENT_REQUEST')
    return rows


def stable_flags(core, shared, before):
    require(flag_snapshot(core, shared) == before, 'FLAGS_CHANGED')


def historical_records(shared, ctx, permission):
    rows = {name: private_snapshot(shared, ctx['execution']['directory'] / name, 131072, pin)
            for name, pin in JOURNAL_PINS.items()}
    ready, start, result = (shared.parse(rows[name]['raw']) for name in
                           ('watcher_ready.json', 'start_receipt.json', 'watcher_result.json'))
    require(all(row.get('execution_revision') == ctx['context'] for row in (ready, start, result)),
            'HISTORICAL_REFERENCE')
    require(ready.get('schema') == 'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1'
            and ready.get('watcher_source_sha256') == WATCHER_SHA
            and ready.get('issuer_source_sha256') == INSTALLER_SHA
            and ready.get('verifier_sha256') == SHARED_SHA and ready.get('start_capability') is False
            and shared.process_identity_valid(ready.get('process_identity')), 'READY_BINDING')
    started = start.get('trainer') or {}
    require(start.get('schema') == 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1'
            and start.get('start_command_issued') is True and type(start.get('start_command_returncode')) is int
            and start['start_command_returncode'] == 0
            and started.get('process_identity') == EXPECTED_PROCESS
            and started.get('service', {}).get('state') == 'RUNNING'
            and shared.integer(started.get('service', {}).get('pid')) and started['service']['pid'] > 1
            and start.get('watcher_ready_sha256') == rows['watcher_ready.json']['sha256'], 'START_BINDING')
    require(result.get('schema') == 'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1'
            and result.get('state') == 'EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED'
            and result.get('active') is True and result.get('optimizer_permission_issued') is True
            and result.get('ordinary_guard_verified') is True and result.get('finalizer_called_once') is True
            and result.get('watcher_source_sha256') == WATCHER_SHA
            and result.get('process_identity') == ready['process_identity']
            and result.get('start_receipt_sha256') == rows['start_receipt.json']['sha256'], 'RESULT_BINDING')
    times = (ctx['execution']['descriptor']['created_at'], ready.get('armed_at'), start.get('started_at'),
             start.get('sampled_at'), permission['permit'].get('issued_at'), result.get('finished_at'), time.time())
    require(all(shared.finite(t) for t in times) and all(a <= b for a, b in zip(times, times[1:])),
            'HISTORICAL_TIMES')
    require(shared.parse(rows['activation.json']['raw']) == permission['permit'], 'ACTIVATION_RECORD')
    return rows


def quality_hold(shared, guard, ctx, snapshot, flags):
    """Allow heartbeat time/disk telemetry to change; never alter quality policy."""
    config, config_sha = guard.checked_config(expected_source=GUARD_SHA)
    require(config.get('execution_revision') == ctx['context'] and config.get('policy') == shared.GUARD_POLICY,
            'GUARD_CONFIG')
    expected = guard.bindings(config, config_sha, ctx)
    for attempt in range(3):
        try:
            row, raw_sha = guard.previous_state(expected)
            break
        except guard.GuardHold as exc:
            if str(exc) != 'HOLD_QWEN_GUARD_FILE_CHANGED' or attempt == 2:
                raise
    require(isinstance(row, dict) and row.get('state') == 'INHIBITED', 'QUALITY_HOLD_REQUIRED')
    policy = row.get('policy_state') or {}
    require(all(type(policy.get(k)) is type(v) and policy[k] == v for k, v in EXPECTED_QUALITY.items()),
            'QUALITY_POLICY_CHANGED')
    now = time.time()
    require(shared.finite(row.get('sampled_at')) and 0 <= now - row['sampled_at'] <= 30, 'GUARD_STALE')
    cp = row.get('checkpoint') or {}
    require(cp.get('manifest_sha256') == digest(snapshot['manifest_raw'])
            and cp.get('student_state_sha256') == digest(snapshot['state_raw'])
            and cp.get('pointer_sha256') == digest(snapshot['pointer_raw'])
            and cp.get('successful_updates') == 55 and cp.get('attempted_updates') == 55
            and cp.get('skipped_updates') == 0 and cp.get('evaluated_at_update') == 55
            and cp.get('holdout_loss') == snapshot['saved']['last_holdout_loss'], 'GUARD_CHECKPOINT')
    require(guard.pause_token(row) == flags['TRAIN_PAUSE_REQUEST.flag']['raw'], 'GUARD_PAUSE_BINDING')
    return {'semantic': {'bindings': expected, 'quality': {k: policy[k] for k in EXPECTED_QUALITY},
                         'checkpoint_manifest_sha256': cp['manifest_sha256'], 'state': row['state']},
            'row_sha256': raw_sha, 'sampled_at': row['sampled_at']}


def checkpoint_snapshot(core, shared, ctx):
    pointer, pointer_raw = shared.document(ctx['output'] / 'latest_checkpoint.json', 16384)
    name = pointer.get('directory'); pin = pointer.get('manifest_sha256')
    require(isinstance(name, str) and shared.NAME.fullmatch(name) and shared.sha(pin), 'POINTER')
    folder = shared.plain(ctx['output'] / name)
    manifest, manifest_raw = shared.document(folder / 'checkpoint_manifest.json', 65536, expected=pin)
    require(manifest.get('directory') == name, 'POINTER_DIRECTORY')
    files = manifest.get('files_sha256')
    require(isinstance(files, dict) and len(files) == 10 and shared.REQUIRED <= set(files)
            and all(isinstance(k, str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', k)
                    and k != 'checkpoint_manifest.json' and shared.sha(v) for k, v in files.items()), 'FILE_SET')
    require(set(p.name for p in folder.iterdir()) == set(files) | {'checkpoint_manifest.json'}, 'FOLDER_CONTENTS')
    identities = {}; total = 0
    for filename in sorted(files):
        info = shared.plain(folder / filename).stat(follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER_UID and info.st_nlink == 1
                and not info.st_mode & 0o022 and 0 <= info.st_size <= BYTE_BOUND, 'PAYLOAD_METADATA')
        total += info.st_size; identities[filename] = identity(info)
    require(0 < total <= BYTE_BOUND, 'BYTE_BOUND')
    saved, state_raw = shared.document(folder / 'student_state.json', expected=files['student_state.json'])
    binding = shared.checkpoint_binding(ctx, manifest, saved, allow_initial_anchor=False)
    require(binding.get('current_execution') is True and binding.get('initial_anchor') is False
            and 25 < saved['successful_total'] <= 1000, 'NEW_CURRENT_CHECKPOINT_REQUIRED')
    return {'folder': folder, 'pointer_raw': pointer_raw, 'manifest_raw': manifest_raw,
        'state_raw': state_raw, 'manifest': manifest, 'saved': saved, 'binding': binding,
        'identities': identities, 'total': total}


def continuation_proof(shared, ctx, snapshot, anchor_manifest, anchor_state, process):
    manifest, saved, binding = (snapshot[key] for key in ('manifest', 'saved', 'binding'))
    witness = binding['witness']
    require(manifest.get('process_identity') == process == witness['process_identity']
            and witness['started_at'] >= ctx['execution']['descriptor']['created_at'], 'CHECKPOINT_PROCESS')
    require(anchor_state['successful_total'] == 25
            and saved['update_evidence'][:25] == anchor_state['update_evidence']
            and saved['update_evidence'][:6] == ctx['certificate']['update_evidence'], 'PREFIX_CHANGED')
    chain = ctx['observer'].update_chain(saved, ctx['contract'])
    require(chain.get('successful_optimizer_steps') == saved['successful_total']
            and chain.get('finite_gradient_and_tensor_delta_chain_verified') is True
            and chain.get('adapter_tensor_sha256') == manifest['adapter_tensor_sha256'], 'UPDATE_CHAIN')
    require(manifest['adapter_tensor_sha256'] != anchor_manifest['adapter_tensor_sha256']
            and manifest['files_sha256']['adapter_model.safetensors']
                != anchor_manifest['files_sha256']['adapter_model.safetensors'], 'ADAPTER_UNCHANGED')
    return chain


def final_snapshot(shared, ctx, snapshot):
    require(shared.read(ctx['output'] / 'latest_checkpoint.json', 16384) == snapshot['pointer_raw']
            and shared.read(snapshot['folder'] / 'checkpoint_manifest.json', 65536) == snapshot['manifest_raw']
            and shared.read(snapshot['folder'] / 'student_state.json') == snapshot['state_raw']
            and set(p.name for p in snapshot['folder'].iterdir())
                == set(snapshot['identities']) | {'checkpoint_manifest.json'}
            and all(identity(shared.plain(snapshot['folder'] / name).stat(follow_symlinks=False)) == before
                    for name, before in snapshot['identities'].items()), 'FINAL_CHECKPOINT_CHANGED')


def observe(reference=None):
    started = time.monotonic()
    core, shared = native_modules()
    ctx = checked_context(core, shared, reference)
    permission = active(shared, ctx)
    before = exited(core, shared, ctx)
    historical = historical_records(shared, ctx, permission)
    flags = flag_snapshot(core, shared)
    anchor_manifest, anchor_state = shared.anchor_metadata(ctx)
    snapshot = checkpoint_snapshot(core, shared, ctx)
    require(snapshot['manifest']['directory'] == EXPECTED_CHECKPOINT['directory']
            and digest(snapshot['pointer_raw']) == EXPECTED_CHECKPOINT['pointer_sha256']
            and digest(snapshot['manifest_raw']) == EXPECTED_CHECKPOINT['manifest_sha256']
            and digest(snapshot['state_raw']) == EXPECTED_CHECKPOINT['student_state_sha256']
            and snapshot['saved']['successful_total'] == EXPECTED_CHECKPOINT['successful_total'] == 55
            and snapshot['saved']['attempted_total'] == EXPECTED_CHECKPOINT['attempted_total'] == 55
            and snapshot['saved']['skipped_total'] == EXPECTED_CHECKPOINT['skipped_total'] == 0
            and snapshot['saved']['holdout_evaluated_successful_total']
                == EXPECTED_CHECKPOINT['evaluated_successful_total'] == 55
            and snapshot['total'] == EXPECTED_CHECKPOINT['verified_bytes'], 'EXACT_CP55_REQUIRED')
    chain = continuation_proof(shared, ctx, snapshot, anchor_manifest, anchor_state, EXPECTED_PROCESS)
    require(snapshot['binding']['witness']['kind'] == 'PERIODIC'
            and snapshot['binding']['witness']['started_at'] >= permission['permit']['issued_at'],
            'PERIODIC_EVALUATION_BEFORE_ADMISSION')
    guard = load(GUARD_NAME, source(SCRIPTS / GUARD_NAME, GUARD_SHA))
    quality_before = quality_hold(shared, guard, ctx, snapshot, flags)
    # The frozen finite reader already accepts an explicit callback. Its
    # training no_flags function remains unchanged and is never overridden.
    full, manifest, saved = core.full_checkpoint(ctx,
        flags_check=lambda: stable_flags(core, shared, flags), expected=EXPECTED_CHECKPOINT)
    require(manifest == snapshot['manifest'] and saved == snapshot['saved']
            and full['verified_files'] == 10 and full['verified_bytes'] == snapshot['total']
            and full['full_files_sha256_verified'] is True, 'FULL_PROOF_CHANGED')
    after_ctx = checked_context(core, shared, ctx['context'])
    require(after_ctx['raw'] == ctx['raw'] and after_ctx['wrapper'] == ctx['wrapper']
            and after_ctx['execution'] == ctx['execution'] and after_ctx['config_sha256'] == ctx['config_sha256'],
            'CONTEXT_CHANGED')
    after_permission = active(shared, after_ctx)
    require(after_permission['permit_sha256'] == permission['permit_sha256'], 'PERMISSION_CHANGED')
    after = exited(core, shared, after_ctx)
    require(after == before, 'PROCESS_CHANGED')
    require(historical_records(shared, after_ctx, after_permission) == historical, 'HISTORICAL_RECORDS_CHANGED')
    final_anchor_manifest, final_anchor_state = shared.anchor_metadata(after_ctx)
    require(final_anchor_manifest == anchor_manifest and final_anchor_state == anchor_state, 'ANCHOR_CHANGED')
    stable_flags(core, shared, flags)
    final_snapshot(shared, after_ctx, snapshot)
    quality_after = quality_hold(shared, guard, after_ctx, snapshot, flags)
    require(quality_after['semantic'] == quality_before['semantic'], 'QUALITY_HOLD_CHANGED')
    # A last check follows guard I/O as well; no inference about live memory.
    require(exited(core, shared, after_ctx) == before, 'PROCESS_CHANGED')
    stable_flags(core, shared, flags)
    witness = snapshot['binding']['witness']
    return {'schema': SCHEMA, 'state': 'AFTER_PROCESS_EXIT_CP55_FULLY_VERIFIED_QUALITY_HOLD_PRESERVED',
        'observed_at': time.time(), 'elapsed_seconds': round(time.monotonic() - started, 6), 'read_only': True,
        'execution_revision': ctx['context'], 'execution_binding': shared.execution_binding(ctx),
        'source_pins': {'issuer': INSTALLER_SHA, 'shared': SHARED_SHA, 'student': STUDENT_SHA,
                        'guard': GUARD_SHA, 'watcher': WATCHER_SHA},
        'trainer': {'service_state': after['service']['state'], 'process_identity': after['process_identity']},
        'process_observation_scope': 'AFTER_PROCESS_EXIT', 'same_live_admitted_process_before_after': False,
        'admitted_child_absent_before_after': True, 'recorded_writer_pid_absent_before_after': True,
        'recorded_writer_process_identity': EXPECTED_PROCESS,
        'historical_activation_permit_sha256': permission['permit_sha256'],
        'historical_writer_matches_initial_activation': True,
        'current_process_present': False, 'current_optimizer_permission_verified': False,
        'permission_to_resume': False, 'training_continuation_authorized': False,
        'historical_journals': {name: {'sha256': row['sha256'], 'bytes': row['bytes']}
                               for name, row in historical.items()},
        'preserved_flags': {name: {'sha256': row['sha256'], 'bytes': row['bytes'],
                                  'raw_and_identity_unchanged': True} for name, row in flags.items()},
        'quality_guard': {'state': 'INHIBITED', 'reason': 'HOLDOUT_REGRESSION',
            'policy_state': quality_after['semantic']['quality'], 'fresh_before_after': True,
            'semantic_state_preserved': True, 'heartbeat_may_advance': True,
            'before_sha256': quality_before['row_sha256'], 'after_sha256': quality_after['row_sha256'],
            'sampled_at_before': quality_before['sampled_at'], 'sampled_at_after': quality_after['sampled_at']},
        'checkpoint': {**full, 'files_sha256': manifest['files_sha256'],
            'adapter_tensor_sha256': manifest['adapter_tensor_sha256'], 'current_execution': True,
            'initial_anchor': False, 'latest_pointer_unchanged': True},
        'anchor': {'manifest_sha256': ANCHOR_SHA, 'student_state_sha256': shared.ANCHOR['student_state_sha256'],
            'successful_total': 25, 'metadata_verified': True, 'payload_rehashed_this_observation': False},
        'new_execution_optimizer_updates_verified': saved['successful_total'] - 25,
        'update_prefix_25_preserved': True, 'accepted_six_prefix_preserved': True,
        'finite_gradient_and_tensor_delta_chain_verified': True,
        'adapter_payload_sha256_changed_from_anchor': True, 'recorded_tensor_sha256_changed_from_anchor': True,
        'tensor_hashes_recomputed_by_observer': False,
        'evaluation': {'kind': witness['kind'], 'process_identity': witness['process_identity'],
            'evaluated_successful_total': witness['evaluated_successful_total'],
            'holdout_examples': witness['holdout_examples'], 'holdout_loss': witness['holdout_loss'],
            'started_at': witness['started_at'], 'finished_at': witness['finished_at'],
            'state_unchanged_during_evaluation': witness['before'] == witness['after'],
            'witness_sha256': digest(shared.encode(witness)), 'current_at_checkpoint': chain['holdout_current'],
            'periodic_evaluation_after25_verified': witness['kind'] in ('PERIODIC', 'GOAL')
                and witness['evaluated_successful_total'] > 25},
        'full_checkpoint_files_verified': True, 'new_optimizer_updates_full_verified': True,
        'evidence_scope': 'HISTORICAL_ADMITTED_WRITER_SAVED_UPDATES_AND_FULL_CHECKPOINT_FILE_SHA_AFTER_EXIT',
        'files_or_flags_modified': False, 'service_actions_performed': False,
        'public_base_ram_retention_observed': False, 'persistent_memfd_keeper_verified': False,
        'general_intelligence_improvement_proven': False}


def safe(exc):
    if isinstance(exc, Deadline):
        return 'HOLD_QWEN_SUCCESSOR_PROOF_DEADLINE'
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value) else 'HOLD_QWEN_SUCCESSOR_PROOF_UNVERIFIED'


def deadline(*_):
    raise Deadline()


def main():
    previous = signal.signal(signal.SIGALRM, deadline)
    timer = signal.setitimer(signal.ITIMER_REAL, OUTER_SECONDS)
    try:
        result = observe()
        encoded = json.dumps({'kind': KIND, 'verification': result}, sort_keys=True, allow_nan=False)
        require(len(encoded.encode()) <= 65536, 'OUTPUT_BOUND')
        print(PREFIX + encoded, flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    except BaseException as exc:
        result = {'schema': SCHEMA, 'state': 'HOLD', 'reason': safe(exc), 'read_only': True,
            'full_checkpoint_files_verified': False, 'new_optimizer_updates_full_verified': False,
            'files_or_flags_modified': False, 'service_actions_performed': False,
            'permission_to_resume': False, 'training_continuation_authorized': False}
        print(PREFIX + json.dumps({'kind': KIND, 'verification': result}, sort_keys=True), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            signal.setitimer(signal.ITIMER_REAL, *timer)


if __name__ == '__main__':
    raise SystemExit(main())
