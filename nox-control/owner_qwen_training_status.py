"""Read-only current Qwen evidence for the existing owner chat.

The initial five-update checkpoint and a later six-update restart admission
have distinct sealed contexts. Saved evidence never implies a live process,
and model-load lineage never implies current RAM residency. Large checkpoint
files use a SHA cache bound to their complete filesystem identity. This module
performs no training, network request, model import, flag write or merge.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import threading
import time
import types

ROOT = Path('/root/nox')
PROC = Path('/proc')
SCHEMA = 'NOX_OWNER_CURRENT_TRAINING_EVIDENCE_V1'
CONFIG_SCHEMA = 'NOX_OWNER_TRAINING_STATUS_CONFIG_V1'
OBSERVER_SHA = 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a'
INITIAL = {'request': '6907283384', 'source_sha': '2a0d18d8c4434c4798335868df4b28be0e507ed5',
           'receipt_sha256': '2336a33272f75d9fc56efd74172ccf09bba5067cceb1f67b6a966812d9a70262'}
INITIAL_ADMISSION_SHA = 'c82b6d4eadabf973ad184f87b120243b74acf78c52565b17440a19f5566c3a33'
INITIAL_WRAPPER_SHA = '9bc41d32abbdb245dcc03f1611c28e27f5423d3a59819093c0394c59c56f4da5'
WINDOW_REQUEST = '6907513913'
WINDOW_SOURCE = '4d5f0b065309f3524dc4d5d08d3924a4d0223931'
WINDOW_ENTRY_SHA = 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7'
BASELINE = {
    'checkpoint_directory': 'checkpoint-u00000005-a00000005-g01794803450864100744',
    'manifest_sha256': '96aed3c5512a6d60da0a1370ae086ab248f226a6e68f7ab3f42dc9b15dc838e9',
    'terminal_sha256': '3c305ea42f49a40903aa5bfcfa2131d49a06b085642aac6c559686eb636d9d59',
    'lineage_sha256': '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190',
    'lineage_file_sha256': '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0',
    'successful_optimizer_steps': 5, 'attempted_steps': 5, 'skipped_steps': 0,
    'adapter_tensor_sha256': '7a82a5ffc4cc4520d8e6d0d066a5cfd7657891da6cecf3229f3b8d1f82c30ef3',
}
SHA = re.compile('[a-f0-9]{64}')
HASH_SECONDS = 5.0
_VERIFY_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_HASH_CACHE = {}
_OBSERVER_SOURCE_BYTES = None  # Exact bundle bytes are supplied only during installer preflight.


class StatusHold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise StatusHold('HOLD_QWEN_STATUS_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def valid_sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def read(path, maximum=2 * 1024 ** 2, *, expected=None, keep=True, deadline=None, audit=None):
    """Re-use only a full prior SHA for the same owner-controlled file identity."""
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum, 'FILE')
        key = (str(path), identity(before), expected)
        use_cache = keep is False and valid_sha(expected)
        with _CACHE_LOCK:
            hit = use_cache and _HASH_CACHE.get(key) is True
        h, chunks, total = hashlib.sha256(), [], 0
        if not hit:
            while True:
                require(deadline is None or time.monotonic() < deadline, 'HASH_DEADLINE')
                block = stream.read(min(1024 * 1024, maximum + 1 - total))
                if not block:
                    break
                total += len(block)
                require(total <= maximum, 'FILE_BOUND')
                h.update(block)
                if keep:
                    chunks.append(block)
            require(total == before.st_size, 'FILE_SIZE_CHANGED')
        after, named = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
        require(identity(before) == identity(after) == identity(named), 'FILE_CHANGED')
    value = expected if hit else h.hexdigest()
    require(expected is None or value == expected, 'FILE_SHA')
    if use_cache and not hit:
        with _CACHE_LOCK:
            if len(_HASH_CACHE) >= 128:
                _HASH_CACHE.clear()
            _HASH_CACHE[key] = True
    if audit is not None:
        audit['checkpoint_bytes_hashed'] += 0 if hit else total
        audit['checkpoint_files_from_stat_cache'] += int(bool(hit))
    return b''.join(chunks), {'bytes': before.st_size, 'sha256': value, 'mtime_ns': before.st_mtime_ns}


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def document(path, expected=None, maximum=2 * 1024 ** 2):
    raw, meta = read(path, maximum, expected=expected)
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'DOCUMENT')
    return value, meta


def context_value(context=None):
    if context is None:
        value, _ = document(ROOT / 'config/owner_training_status.json', maximum=16384)
        require(set(value) == {'schema', 'admission'} and value['schema'] == CONFIG_SCHEMA, 'CONFIGURATION')
        context = value['admission']
    require(isinstance(context, dict) and set(context) == {'request', 'source_sha', 'receipt_sha256'}
            and isinstance(context['request'], str) and re.fullmatch('[0-9]{1,24}', context['request'])
            and isinstance(context['source_sha'], str) and re.fullmatch('[a-f0-9]{40}', context['source_sha'])
            and valid_sha(context['receipt_sha256']), 'CONTEXT')
    return dict(context)


def observer(audit=None):
    path = ROOT / 'scripts/owner_qwen_training_observe.py'
    if path.exists() or path.is_symlink():
        raw, _ = read(path, expected=OBSERVER_SHA)
    else:
        raw = _OBSERVER_SOURCE_BYTES
        require(isinstance(raw, bytes) and digest(raw) == OBSERVER_SHA, 'OBSERVER_NOT_INSTALLED')
    value = types.ModuleType('_nox_qwen_status_verified_observer')
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    value.ROOT, value.STATE, value.SCRIPTS, value.PROC = ROOT, ROOT / 'state', ROOT / 'scripts', PROC
    value.OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
    value.CORPUS = ROOT / 'state/qwen_corpus/6907283384'
    value.read = lambda *args, **kwargs: read(*args, **kwargs, audit=audit)
    return value


def previous_acceptance():
    return {'previous_goal': 5, 'target_goal': 6,
            'terminal_receipt_sha256': BASELINE['terminal_sha256'],
            'checkpoint': {'directory': BASELINE['checkpoint_directory'],
                'manifest_sha256': BASELINE['manifest_sha256'], 'verified_files': 10,
                'verified_bytes': 519881851, 'all_checkpoint_file_sha256_verified': True},
            'acceptance_sha256': None, 'lineage_sha256': BASELINE['lineage_sha256']}


def arguments(obs, request, pointer_sha, profile):
    expected = {'--request': request, '--admission-sha256': pointer_sha,
                '--base-directory': profile['base_directory'], '--base-transport': 'sealed-memfd',
                '--manifest': str(obs.SCRIPTS / 'qwen35_9b_manifest.json'),
                '--output-directory': str(obs.OUTPUT),
                '--train-jsonl': str(obs.CORPUS / 'train.jsonl'), '--train-sha256': obs.DATA_PINS['train.jsonl'],
                '--holdout-jsonl': str(obs.CORPUS / 'holdout.jsonl'), '--holdout-sha256': obs.DATA_PINS['holdout.jsonl'],
                '--dataset-manifest': str(obs.CORPUS / 'corpus_manifest.json'),
                '--dataset-manifest-sha256': obs.DATA_PINS['corpus_manifest.json'],
                '--successful-updates': str(profile['successful_updates_goal'])}
    argv = ['/root/venv_volta/bin/python', '-u', str(obs.SCRIPTS / 'qwen_student_training_entry.py')]
    argv.extend(item for pair in expected.items() for item in pair)
    if profile['successful_updates_goal'] != 5:
        argv.append('--resume')
    return argv


def wrapper_bytes(argv, request, goal):
    """Pure template from helper864fe and the exact reviewed4d5 numeric delta."""
    require(goal in (5, 6, 1000) and re.fullmatch('[0-9]{1,24}', request), 'WRAPPER_SCOPE')
    latch = "import os,sys\np=sys.argv[1]\ntry:\n fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)\nexcept FileExistsError:\n raise SystemExit(0)\nwith os.fdopen(fd,'w') as f:\n f.write('OWNER_QWEN_WINDOW_'+('COMPLETE' if sys.argv[2]=='0' else 'FAILED')+' request='+sys.argv[3]+' goal=5\\n');f.flush();os.fsync(f.fileno())\n"
    raw = ('#!/bin/bash\nset -u\nunset BNB_CUDA_VERSION\nexport CUDA_VISIBLE_DEVICES=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false\n'
           'for flag in /root/nox/STOP /root/nox/STOP.flag /root/nox/stop.flag /root/nox/.stop /root/nox/program/STOP /root/nox/state/STOP /workspace/NOX_STOP /root/nox/state/TRAIN_HOLD.flag /root/nox/state/TRAIN_PAUSE_REQUEST.flag; do\n'
           '  [ ! -e "$flag" ] && [ ! -L "$flag" ] || exit 0\ndone\n'
           + 'child_pid=\nforward_stop() { if [ -n "$child_pid" ]; then kill -TERM "$child_pid" 2>/dev/null || true; fi; }\n'
           + 'trap forward_stop TERM INT\n' + shlex.join(argv) + ' &\nchild_pid=$!\n'
           + 'while true; do\n  wait "$child_pid"\n  rc=$?\n  kill -0 "$child_pid" 2>/dev/null || break\ndone\n'
           + '/root/venv_volta/bin/python - /root/nox/state/TRAIN_HOLD.flag "$rc" ' + shlex.quote(request) + " <<'NOX_QWEN_LATCH'\n"
           + latch + 'NOX_QWEN_LATCH\nexit "$rc"\n').encode()
    require(raw.count(br' goal=5\n') == 1, 'WRAPPER_TEMPLATE')
    return raw.replace(br' goal=5\n', (' goal=' + str(goal) + '\\n').encode(), 1)


def admitted(context, obs):
    initial, _ = document(obs.STATE / ('owner_qwen_install_' + INITIAL['request'] + '.json'), INITIAL['receipt_sha256'])
    require(initial.get('schema') == 'NOX_QWEN_INITIAL_OWNER_INSTALL_V1'
            and initial.get('request') == INITIAL['request'] and initial.get('source_sha') == INITIAL['source_sha']
            and initial.get('state') == 'NEW_STUDENT_STARTED_ACCEPTANCE_PENDING'
            and initial.get('source_installed') is True and initial.get('source_pins') == obs.PINS, 'INITIAL_INSTALL')
    pointer, pointer_meta = document(obs.STATE / 'owner_training_admission.json')
    expected_sources = {str(obs.SCRIPTS / name): pin for name, pin in obs.PINS.items() if name.endswith('.py')}
    cursor, cursor_sha = pointer, pointer_meta['sha256']
    anchor_seen = False
    current_record = current_context = current_wrapper_sha = None
    continuation_anchor = None
    for depth in range(3):
        request, source = cursor.get('request'), cursor.get('source_sha')
        require(isinstance(request, str) and re.fullmatch('[0-9]{1,24}', request)
                and isinstance(source, str) and re.fullmatch('[a-f0-9]{40}', source), 'WINDOW_IDENTITY')
        goal = cursor.get('student_profile', {}).get('successful_updates_goal')
        require(type(goal) is int and goal in (5, 6, 1000), 'WINDOW_GOAL')
        profile = dict(initial['student_profile']); profile['successful_updates_goal'] = goal
        require(cursor.get('schema') == 'NOX_OWNER_TRAINING_ADMISSION_V1'
                and cursor.get('initial_request') == INITIAL['request'] and cursor.get('sources') == expected_sources
                and cursor.get('student_profile') == profile, 'ADMISSION_PROFILE')
        argv = arguments(obs, request, cursor_sha, profile)
        expected_wrapper = wrapper_bytes(argv, request, goal)
        if goal == 5:
            require(cursor_sha == INITIAL_ADMISSION_SHA and request == INITIAL['request']
                    and source == INITIAL['source_sha'] and digest(expected_wrapper) == INITIAL_WRAPPER_SHA, 'INITIAL_POINTER')
            sealed, record_context = initial, INITIAL
            wrapper_sha = INITIAL_WRAPPER_SHA
        else:
            sealed, meta = document(obs.STATE / ('owner_qwen_window_' + request + '.json'))
            record_context = {'request': request, 'source_sha': source, 'receipt_sha256': meta['sha256']}
            require(sealed.get('schema') == 'NOX_QWEN_WINDOW_ADVANCE_V1'
                    and sealed.get('request') == request and sealed.get('source_sha') == source
                    and sealed.get('state') in {'WINDOW_STARTED_ACCEPTANCE_PENDING', 'HOLD'}
                    and sealed.get('initial_request') == INITIAL['request'] and sealed.get('target_goal') == goal
                    and sealed.get('new_admission_sha256') == cursor_sha
                    and sealed.get('wrapper_sha256') == digest(expected_wrapper), 'WINDOW_RECEIPT')
            wrapper_sha = sealed['wrapper_sha256']
            accepted = sealed.get('acceptance')
            if goal == 6:
                require(request == WINDOW_REQUEST and source == WINDOW_SOURCE and accepted == previous_acceptance(),
                        'KNOWN_SIX_UPDATE_ADMISSION')
            else:
                require(isinstance(accepted, dict) and set(accepted) == {'previous_goal', 'target_goal',
                    'terminal_receipt_sha256', 'checkpoint', 'acceptance_sha256', 'lineage_sha256'}
                    and accepted['previous_goal'] == 6 and accepted['target_goal'] == 1000
                    and valid_sha(accepted['terminal_receipt_sha256'])
                    and accepted['terminal_receipt_sha256'] == accepted['acceptance_sha256']
                    and accepted['lineage_sha256'] == BASELINE['lineage_sha256'], 'CONTINUATION_ACCEPTANCE')
                certificate, _ = document(obs.OUTPUT / 'owner_acceptance.json', accepted['acceptance_sha256'])
                cp = accepted['checkpoint']
                require(isinstance(cp, dict) and set(cp) == {'directory', 'manifest_sha256', 'verified_files',
                    'verified_bytes', 'all_checkpoint_file_sha256_verified'}
                    and isinstance(cp['directory'], str) and obs.NAME.fullmatch(cp['directory'])
                    and valid_sha(cp['manifest_sha256']) and type(cp['verified_files']) is int and 9 <= cp['verified_files'] <= 32
                    and type(cp['verified_bytes']) is int and 0 < cp['verified_bytes'] <= 2 * 1024 ** 3
                    and cp['all_checkpoint_file_sha256_verified'] is True
                    and certificate.get('checkpoint') == str(obs.OUTPUT / cp['directory'])
                    and certificate.get('checkpoint_manifest_sha256') == cp['manifest_sha256']
                    and certificate.get('successful_optimizer_steps') == 6
                    and certificate.get('new_successful_optimizer_steps') == 1
                    and certificate.get('state') == 'STUDENT_RESTART_AND_UPDATES_VERIFIED'
                    and certificate.get('reload_verified') is True, 'CONTINUATION_CERTIFICATE')
                continuation_anchor = accepted
            archived = ROOT / 'backup/owner_qwen_window' / request
            previous_sha = sealed.get('previous_admission_sha256')
            require(valid_sha(previous_sha), 'PREVIOUS_ADMISSION_SHA')
            previous, _ = document(archived / 'previous_admission.json', previous_sha)
            previous_goal = previous.get('student_profile', {}).get('successful_updates_goal')
            require(previous_goal == {6: 5, 1000: 6}[goal]
                    and sealed.get('previous_request') == previous.get('request'), 'PREVIOUS_WINDOW')
            previous_wrapper, _ = read(archived / 'previous_wrapper.sh')
            require(previous_wrapper == wrapper_bytes(arguments(obs, previous['request'], previous_sha,
                        previous['student_profile']), previous['request'], previous_goal), 'ARCHIVED_WRAPPER')
            created = cursor.get('created_at')
            require(type(created) in (int, float) and math.isfinite(created) and created > 0, 'WINDOW_TIMESTAMP')
            expected_pointer = dict(previous)
            expected_pointer.update(request=request, source_sha=source, student_profile=profile, created_at=created,
                previous_request=previous['request'], previous_admission_sha256=previous_sha,
                accepted_previous_window=accepted['terminal_receipt_sha256'])
            require(cursor == expected_pointer, 'WINDOW_POINTER_CHAIN')
        anchor_seen = anchor_seen or record_context == context
        if depth == 0:
            current_record, current_context, current_wrapper_sha = sealed, record_context, wrapper_sha
        if goal == 5:
            break
        cursor, cursor_sha = previous, previous_sha
    else:
        require(False, 'WINDOW_CHAIN_BOUND')
    require(anchor_seen, 'CONFIGURED_ANCHOR_NOT_IN_CURRENT_CHAIN')
    for name, pin in obs.PINS.items():
        read(obs.SCRIPTS / name, expected=pin)
    profile = pointer['student_profile']; goal = profile['successful_updates_goal']
    argv = arguments(obs, pointer['request'], pointer_meta['sha256'], profile)
    wrapper, _ = read(obs.SCRIPTS / 'run_train_volta_t866u.sh', expected=current_wrapper_sha)
    require(wrapper == wrapper_bytes(argv, pointer['request'], goal), 'CURRENT_WRAPPER_BYTES')
    return current_record, pointer, argv, {'pointer_sha256': pointer_meta['sha256'], 'wrapper_sha256': current_wrapper_sha,
        'resume': goal != 5, 'goal': goal, 'current_context': current_context,
        'configured_anchor': context, 'continuation_acceptance_anchor': continuation_anchor,
        'admission_started_at': current_record.get('started_at')}


def admission(context):
    context = context_value(context)
    sealed, pointer, _, _ = admitted(context, observer())
    return sealed, pointer


def checkpoint(obs, contract, lineage, name, manifest_sha, deadline):
    """Verify any named checkpoint, including an older durable acceptance point."""
    require(isinstance(name, str) and obs.NAME.fullmatch(name) and valid_sha(manifest_sha), 'CHECKPOINT_POINTER')
    directory = obs.OUTPUT / name
    manifest, _ = obs.document(directory / 'checkpoint_manifest.json', manifest_sha)
    files = manifest.get('files_sha256')
    require(isinstance(files, dict) and obs.REQUIRED <= files.keys() and len(files) <= 32
            and all(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', key) and key != 'checkpoint_manifest.json'
                    and valid_sha(pin) for key, pin in files.items()), 'CHECKPOINT_FILES')
    require(manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1' and manifest.get('directory') == name
            and manifest.get('lineage_sha256') == contract.canonical_sha(lineage)
            and not directory.is_symlink()
            and set(p.name for p in directory.iterdir()) == set(files) | {'checkpoint_manifest.json'}, 'CHECKPOINT_LINEAGE')
    total = 0
    for filename, expected in sorted(files.items()):
        _, meta = obs.read(directory / filename, 2 * 1024 ** 3 - total, expected=expected, keep=False, deadline=deadline)
        total += meta['bytes']
    saved_lineage, _ = obs.document(directory / 'lineage.json', files['lineage.json'])
    saved, _ = obs.document(directory / 'student_state.json', files['student_state.json'])
    require(saved_lineage == lineage, 'SAVED_LINEAGE')
    proof = obs.update_chain(saved, contract)
    require(manifest.get('successful_total') == proof['successful_optimizer_steps']
            and manifest.get('attempted_total') == proof['attempted_steps']
            and manifest.get('holdout_evaluated_successful_total') == saved['holdout_evaluated_successful_total']
            and manifest.get('holdout_loss') == saved['last_holdout_loss']
            and (proof['successful_optimizer_steps'] == 0 or manifest.get('adapter_tensor_sha256') == proof['adapter_tensor_sha256']),
            'CHECKPOINT_STATE')
    if proof['successful_optimizer_steps'] >= 5:
        require(saved['update_evidence'][4]['adapter_sha_after'] == BASELINE['adapter_tensor_sha256'], 'BASELINE_PREFIX')
    obs.read(directory / 'checkpoint_manifest.json', expected=manifest_sha)
    proof.update(manifest_sha256=manifest_sha, current_checkpoint_files_verified=True,
                 checkpoint_file_count=len(files), required_checkpoint_files=9, verified_bytes=total,
                 process_identity=manifest.get('process_identity'))
    return proof, manifest, saved


def terminal(obs, contract, lineage, latest_manifest, latest_saved, deadline, acceptance=False):
    path = obs.OUTPUT / ('owner_acceptance.json' if acceptance else 'owner_last_result.json')
    row, meta = obs.document(path)
    named = Path(row.get('checkpoint', ''))
    require(named.parent == obs.OUTPUT and obs.NAME.fullmatch(named.name), 'TERMINAL_CHECKPOINT_SCOPE')
    full = None
    if named.name == latest_manifest['directory'] and not acceptance:
        manifest, saved = latest_manifest, latest_saved
    else:
        full, manifest, saved = checkpoint(obs, contract, lineage, named.name, row.get('checkpoint_manifest_sha256'), deadline)
        require(latest_saved['update_evidence'][:len(saved['update_evidence'])] == saved['update_evidence'], 'TERMINAL_PREFIX')
    try:
        proof = obs.terminal_proof(path, contract, lineage, manifest, saved, acceptance=acceptance)
    except obs.Hold:
        # A resumed process may yield before its first update. When state is
        # unchanged, the pinned trainer retains the previous checkpoint and
        # writes its new process identity only into the terminal receipt.
        require(not acceptance and row.get('state') in {'MANUAL_OWNER_STOP', 'CONTROLLED_PROCESS_YIELD',
                    'EXISTING_TRAINER_HOLD_OR_PAUSE', 'HOLD_TRAINING_STOP_REQUESTED'}
                and type(row.get('new_successful_optimizer_steps')) is int
                and row['new_successful_optimizer_steps'] == 0 and row.get('reload_verified') is True,
                'ZERO_UPDATE_PAUSE_SCOPE')
        current = saved['holdout_evaluated_successful_total'] == saved['successful_total']
        holdout_ok = current and saved['last_holdout_loss'] <= saved['initial_holdout_loss'] * 1.05 + .01
        pid = row.get('process_identity')
        require(row.get('schema') == contract.PROOF_SCHEMA and row.get('lineage_sha256') == contract.canonical_sha(lineage)
                and row.get('base_manifest_sha256') == contract.MANIFEST_SHA
                and row.get('checkpoint_manifest_sha256') == digest(obs.read(named / 'checkpoint_manifest.json')[0])
                and row.get('update_evidence') == saved['update_evidence']
                and row.get('successful_optimizer_steps') == saved['successful_total']
                and row.get('attempted_steps') == saved['attempted_total'] and row.get('skipped_steps') == saved['skipped_total']
                and row.get('final_adapter_tensor_sha256') == manifest['adapter_tensor_sha256']
                and row.get('holdout_finite') is current and row.get('independent_holdout_accepted') is holdout_ok
                and row.get('initial_holdout_loss') == saved['initial_holdout_loss']
                and row.get('final_holdout_loss') == saved['last_holdout_loss']
                and row.get('holdout_evaluated_successful_total') == saved['holdout_evaluated_successful_total']
                and isinstance(pid, dict) and set(pid) == {'pid', 'start_ticks', 'boot_id'}
                and type(pid['pid']) is int and pid['pid'] > 0 and type(pid['start_ticks']) is int and pid['start_ticks'] > 0
                and isinstance(pid['boot_id'], str) and re.fullmatch('[a-f0-9-]{36}', pid['boot_id']), 'ZERO_UPDATE_PAUSE_BINDING')
        proof = {'state': row['state'], 'receipt_sha256': meta['sha256'], 'reload_verified': True,
                 'successful_optimizer_steps': saved['successful_total'], 'holdout_current': current,
                 'independent_holdout_accepted': holdout_ok, 'restart_acceptance_verified': False,
                 'zero_new_update_pause_verified': True, 'quality_scope': 'DISJOINT_NEXT_TOKEN_LOSS_NOT_GENERAL_IQ'}
    require(proof['receipt_sha256'] == meta['sha256'], 'TERMINAL_CHANGED')
    proof['terminal_receipt_mtime_ns'] = meta['mtime_ns']
    if full is not None:
        proof.update(checkpoint_manifest_sha256=full['manifest_sha256'],
                     checkpoint_file_count=full['checkpoint_file_count'], checkpoint_bytes_verified=full['verified_bytes'])
    obs.read(path, expected=meta['sha256'])
    return proof


def flags(obs, request, goal):
    value = obs.flags()
    for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag'):
        row = value[name]
        row.pop('this_qwen_window_complete', None); row.pop('this_qwen_window_failed', None)
        if row.get('present'):
            raw, meta = read(obs.STATE / name, 4096)
            row.update(meta)
            row['owned_complete'] = raw == f'OWNER_QWEN_WINDOW_COMPLETE request={request} goal={goal}\n'.encode()
            row['owned_failure'] = raw == f'OWNER_QWEN_WINDOW_FAILED request={request} goal={goal}\n'.encode()
            row['owned_advance_failure'] = raw == f'OWNER_QWEN_WINDOW_ADVANCE_FAILED request={request}\n'.encode()
    return value


def cooperative_pause(last, flag, admission_started_at):
    """A failed wrapper exit alone is insufficient to distinguish a safe yield."""
    pause = flag.get('TRAIN_PAUSE_REQUEST.flag', {})
    terminal_time, pause_time = last.get('terminal_receipt_mtime_ns'), pause.get('mtime_ns')
    return bool(last.get('state') in {'EXISTING_TRAINER_HOLD_OR_PAUSE', 'HOLD_TRAINING_STOP_REQUESTED',
                                     'CONTROLLED_PROCESS_YIELD'}
                and pause.get('present') is True and type(terminal_time) is int and type(pause_time) is int
                and terminal_time >= pause_time
                and type(admission_started_at) in (int, float) and math.isfinite(admission_started_at)
                and admission_started_at > 0 and terminal_time / 10 ** 9 >= admission_started_at)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else 'HOLD_QWEN_STATUS_UNAVAILABLE'


def snapshot(context=None):
    result = {'schema': SCHEMA, 'student_model': 'Qwen/Qwen3.5-9B', 'observed_at': time.time(),
              'read_only': True, 'state': 'UNVERIFIED_ADMISSION', 'verification_state': 'TRAINING_EVIDENCE_UNVERIFIED',
              'positive_optimizer_steps_verified': False, 'optimizer_steps': None, 'global_step': None,
              'skipped_optimizer_steps': None, 'checkpoint_saved_verified': False, 'checkpoint_restore_verified': False,
              'restart_acceptance_verified': False, 'current_model_merge_inclusion': 'NOT_VERIFIED',
              'current_process_model_loaded_verified': False, 'current_run': None,
              'checkpoint_bytes_hashed': 0, 'checkpoint_files_from_stat_cache': 0,
              'base_weights_hashed': False, 'private_training_text_exported': False}
    acquired = False
    try:
        context = context_value(context)
        obs = observer(result)
        _, pointer, argv, gate = admitted(context, obs)
        result['admission'] = gate['current_context']
        result['configured_anchor'] = context
        result['current_context_is_verified_descendant'] = gate['current_context'] != context
        result['target_successful_optimizer_steps'] = gate['goal']
        acquired = _VERIFY_LOCK.acquire(blocking=False)
        require(acquired, 'VERIFICATION_BUSY')
        deadline = time.monotonic() + HASH_SECONDS
        contract = obs.load_contract()
        service_before = obs.service()
        children = obs.trainers(argv, service_before)
        process = children[0] if len(children) == 1 and all(children[0][key] for key in
                  ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')) else None
        result['flags'] = flags(obs, gate['current_context']['request'], gate['goal'])
        lineage, lm = obs.document(obs.OUTPUT / 'owner_lineage.json', BASELINE['lineage_file_sha256'])
        result['historical_model_load'] = obs.lineage_proof(lineage, contract, pointer['student_profile'])
        require(contract.canonical_sha(lineage) == BASELINE['lineage_sha256'], 'INITIAL_LINEAGE_CHANGED')
        cp, cpmeta = obs.document(obs.OUTPUT / 'latest_checkpoint.json')
        proof, manifest, saved = checkpoint(obs, contract, lineage, cp.get('directory'), cp.get('manifest_sha256'), deadline)
        require(proof['successful_optimizer_steps'] <= gate['goal'], 'CHECKPOINT_BEYOND_ADMITTED_GOAL')
        result.update(latest_verified_checkpoint=proof, checkpoint_saved_verified=True,
                      optimizer_steps=proof['successful_optimizer_steps'], global_step=proof['attempted_steps'],
                      skipped_optimizer_steps=proof['skipped_steps'],
                      positive_optimizer_steps_verified=proof['positive_optimizer_updates_verified'],
                      verification_state='VERIFIED_QWEN_OPTIMIZER_CHECKPOINT')
        result['global_step_meaning'] = 'QWEN_ATTEMPTED_OPTIMIZER_STEPS'
        for accepted, key in ((False, 'last_terminal'), (True, 'restart_acceptance')):
            path = obs.OUTPUT / ('owner_acceptance.json' if accepted else 'owner_last_result.json')
            if path.exists() or path.is_symlink():
                try:
                    result[key] = terminal(obs, contract, lineage, manifest, saved, deadline, accepted)
                    if accepted:
                        result['restart_acceptance_verified'] = True
                        result['checkpoint_restore_verified'] = True
                except (OSError, ValueError, TypeError, KeyError, StatusHold, obs.Hold) as exc:
                    result[key] = {'state': 'UNVERIFIED_OR_STALE_TERMINAL', 'reason': safe(exc)}
        if gate['continuation_acceptance_anchor'] is not None:
            anchor = gate['continuation_acceptance_anchor']; accepted = result.get('restart_acceptance', {})
            require(result['restart_acceptance_verified'] and accepted.get('receipt_sha256') == anchor['acceptance_sha256']
                    and accepted.get('checkpoint_manifest_sha256') == anchor['checkpoint']['manifest_sha256']
                    and accepted.get('checkpoint_file_count') == anchor['checkpoint']['verified_files']
                    and accepted.get('checkpoint_bytes_verified') == anchor['checkpoint']['verified_bytes'],
                    'CONTINUATION_CHECKPOINT_ACCEPTANCE_UNVERIFIED')
        progress_path = obs.OUTPUT / 'owner_progress.json'
        if progress_path.exists() or progress_path.is_symlink():
            progress, _ = obs.document(progress_path)
            result['progress_telemetry'] = {key: progress[key] for key in
                ('successful_optimizer_steps', 'attempted_steps', 'skipped_steps', 'pid') if obs.integer(progress.get(key))}
            result['progress_telemetry']['evidence_scope'] = 'UNVERIFIED_TELEMETRY_NOT_A_CHECKPOINT_PROOF'
            result['progress_telemetry']['pid_matches_observed_child'] = bool(process and progress.get('pid') == process['pid'])
            result['progress_telemetry']['stale_relative_to_observed_child'] = bool(process and progress.get('pid') != process['pid'])
            if obs.number(progress.get('time')):
                result['progress_telemetry']['age_seconds'] = max(0, time.time() - progress['time'])
        after, aftermeta = obs.document(obs.OUTPUT / 'latest_checkpoint.json')
        require(after == cp and aftermeta['sha256'] == cpmeta['sha256'], 'LATEST_CHECKPOINT_CHANGED')
        obs.read(obs.OUTPUT / 'owner_lineage.json', expected=lm['sha256'])
        _, _, after_argv, after_gate = admitted(context, obs)
        require(after_gate == gate and after_argv == argv, 'ADMISSION_CHANGED')
        service_after = obs.service()
        live = bool(process and service_before == service_after and service_after['state'] == 'RUNNING'
                    and (obs.process(process['pid']) or {}).get('start_ticks') == process['start_ticks'])
        result['service'] = service_after
        result['live_admitted_process_verified'] = live
        result['current_run'] = {'process': process, 'phase': 'RUNNING_LOADING_OR_TRAINING'} if live else None
        result['current_process_model_loaded_verified'] = bool(live
            and isinstance(proof['process_identity'], dict)
            and proof['process_identity'].get('pid') == process['pid']
            and proof['process_identity'].get('start_ticks') == process['start_ticks'])
        hold = result['flags']['TRAIN_HOLD.flag']
        last = result.get('last_terminal', {})
        if (hold.get('owned_failure') or hold.get('owned_advance_failure')
                or service_after['state'] in {'FATAL', 'BACKOFF'}):
            result['state'] = 'HELD_AFTER_FAILURE'
        elif live:
            result['state'] = 'RUNNING_CURRENT_QWEN_ADMISSION'
        elif service_after['state'] in {'STOPPED', 'EXITED', 'FATAL', 'BACKOFF'} and cooperative_pause(
                last, result['flags'], gate.get('admission_started_at')):
            result['state'] = 'CHECKPOINTED_OR_PAUSED'
        elif last.get('successful_optimizer_steps') == gate['goal'] and hold.get('owned_complete'):
            result['state'] = last['state']
        elif result['flags']['global_stop_present'] or hold.get('present') or result['flags']['TRAIN_PAUSE_REQUEST.flag']['present']:
            result['state'] = 'CHECKPOINTED_OR_PAUSED'
        else:
            result['state'] = 'ADMITTED_TRAINER_NOT_RUNNING'
    except Exception as exc:
        result.update(state='UNVERIFIED_ADMISSION', verification_state='TRAINING_EVIDENCE_UNVERIFIED', reason=safe(exc),
                      positive_optimizer_steps_verified=False, optimizer_steps=None, global_step=None,
                      skipped_optimizer_steps=None, checkpoint_saved_verified=False, checkpoint_restore_verified=False,
                      restart_acceptance_verified=False, live_admitted_process_verified=False,
                      current_process_model_loaded_verified=False, current_run=None)
        result.pop('latest_verified_checkpoint', None)
        result.pop('historical_model_load', None)
        result.pop('last_terminal', None)
        result.pop('restart_acceptance', None)
    finally:
        if acquired:
            _VERIFY_LOCK.release()
    return result


def model_projection(value):
    require(isinstance(value, dict) and value.get('schema') == SCHEMA, 'PROJECTION')
    fields = ('student_model', 'state', 'verification_state', 'positive_optimizer_steps_verified',
              'optimizer_steps', 'global_step', 'global_step_meaning', 'skipped_optimizer_steps',
              'target_successful_optimizer_steps', 'checkpoint_saved_verified', 'checkpoint_restore_verified',
              'restart_acceptance_verified', 'historical_model_load', 'current_process_model_loaded_verified',
              'live_admitted_process_verified', 'latest_verified_checkpoint', 'last_terminal', 'restart_acceptance',
              'current_run', 'progress_telemetry', 'flags', 'service', 'reason', 'current_model_merge_inclusion',
              'current_context_is_verified_descendant')
    return {key: value[key] for key in fields if key in value}


def bind_self_observation(namespace, context=None):
    if namespace.get('_owner_training_status_bound'):
        return
    original_snapshot, original_model = namespace['snapshot'], namespace['evidence_for_model']
    def observed():
        value = original_snapshot(); training = snapshot(context)
        # Replace the old35B projection; stale keys must not leak into Qwen facts.
        value['training'] = {**model_projection(training), 'observed_at': training['observed_at']}
        return value
    def evidence(observation, verified_memory):
        value = original_model(observation, verified_memory)
        if value.get('state') not in ('HOLD_UNVERIFIED_SELF_OBSERVATION', 'HOLD_NATIVE_SERVICES_UNOBSERVED'):
            value['training'] = model_projection(snapshot(context))
        return value
    namespace.update(snapshot=observed, evidence_for_model=evidence, _owner_training_status_bound=True)
