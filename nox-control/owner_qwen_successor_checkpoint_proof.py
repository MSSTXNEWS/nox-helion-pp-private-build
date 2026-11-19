#!/usr/bin/env python3
"""One bounded, read-only proof of new successor checkpoint payloads.

The current sealed execution reference is selected by the pinned shared verifier.
Only the exact native issuer's read-only definitions are used. No issuer main,
finalizer, guard tick, model import, service control, lock or file write occurs.
The retained checkpoint25 is metadata evidence, not a second full payload read.
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
SCHEMA = 'NOX_QWEN_SUCCESSOR_CHECKPOINT_PROOF_V1'
KIND = 'qwen_successor_checkpoint_proof'
PREFIX = 'NOX_MAINT_REPAIR='
OWNER_UID = 0
BYTE_BOUND = 1024 ** 3
OUTER_SECONDS = 75


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
    ctx = shared.current_context(reference)
    execution = ctx['execution']
    require(execution['verifier_sha256'] == SHARED_SHA
            and execution['runtime_entry_sha256'] == STUDENT_SHA
            and execution['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA
            and execution['descriptor']['anchor']['manifest_sha256'] == ANCHOR_SHA, 'CURRENT_GRAPH')
    core.protected()
    core.no_flags()
    return ctx


def live(core, shared, ctx):
    row = core.trainer(ctx, required=True)
    require(row['service']['state'] == 'RUNNING'
            and shared.process_identity_valid(row.get('process_identity')), 'LIVE_PROCESS')
    return row


def active(shared, ctx):
    value = shared.activation_status(ctx)
    require(value.get('active') is True and value.get('bootstrap_pending') is False
            and shared.sha(value.get('permit_sha256')) and value.get('baseline_successful_total') == 25,
            'ACTIVATION_REQUIRED')
    return value


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
    before = live(core, shared, ctx)
    anchor_manifest, anchor_state = shared.anchor_metadata(ctx)
    snapshot = checkpoint_snapshot(core, shared, ctx)
    chain = continuation_proof(shared, ctx, snapshot, anchor_manifest, anchor_state, before['process_identity'])
    full, manifest, saved = core.full_checkpoint(ctx, flags_check=core.no_flags, expected={
        'directory': snapshot['manifest']['directory'], 'pointer_sha256': digest(snapshot['pointer_raw']),
        'manifest_sha256': digest(snapshot['manifest_raw']), 'student_state_sha256': digest(snapshot['state_raw'])})
    require(manifest == snapshot['manifest'] and saved == snapshot['saved']
            and full['verified_files'] == 10 and full['verified_bytes'] == snapshot['total']
            and full['full_files_sha256_verified'] is True, 'FULL_PROOF_CHANGED')
    after_ctx = checked_context(core, shared, ctx['context'])
    require(after_ctx['raw'] == ctx['raw'] and after_ctx['wrapper'] == ctx['wrapper']
            and after_ctx['execution'] == ctx['execution'] and after_ctx['config_sha256'] == ctx['config_sha256'],
            'CONTEXT_CHANGED')
    after_permission = active(shared, after_ctx)
    require(after_permission['permit_sha256'] == permission['permit_sha256'], 'PERMISSION_CHANGED')
    after = live(core, shared, after_ctx)
    require(after == before, 'PROCESS_CHANGED')
    final_anchor_manifest, final_anchor_state = shared.anchor_metadata(after_ctx)
    require(final_anchor_manifest == anchor_manifest and final_anchor_state == anchor_state, 'ANCHOR_CHANGED')
    core.no_flags()
    final_snapshot(shared, after_ctx, snapshot)
    witness = snapshot['binding']['witness']
    return {'schema': SCHEMA, 'state': 'CURRENT_EXECUTION_NEW_CHECKPOINT_FULLY_VERIFIED',
        'observed_at': time.time(), 'elapsed_seconds': round(time.monotonic() - started, 6), 'read_only': True,
        'execution_revision': ctx['context'], 'execution_binding': shared.execution_binding(ctx),
        'source_pins': {'issuer': INSTALLER_SHA, 'shared': SHARED_SHA, 'student': STUDENT_SHA},
        'trainer': {'service_state': after['service']['state'], 'process_identity': after['process_identity']},
        'same_live_admitted_process_before_after': True, 'activation_permit_sha256': permission['permit_sha256'],
        'activation_initial_process_is_current': permission['initial_process_identity'] == after['process_identity'],
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
        'evidence_scope': 'CURRENT_EXECUTION_SAVED_UPDATES_AND_FULL_CHECKPOINT_FILE_SHA',
        'files_or_flags_modified': False, 'service_actions_performed': False,
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
        print(PREFIX + json.dumps({'kind': KIND, 'verification': result}, sort_keys=True, allow_nan=False), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    except BaseException as exc:
        result = {'schema': SCHEMA, 'state': 'HOLD', 'reason': safe(exc), 'read_only': True,
            'full_checkpoint_files_verified': False, 'new_optimizer_updates_full_verified': False,
            'files_or_flags_modified': False, 'service_actions_performed': False}
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
