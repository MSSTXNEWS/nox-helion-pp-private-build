#!/usr/bin/env python3
"""Pause-only guard for an explicit Qwen execution revision in the dispatcher.

Historical window1000 verification remains a distinct legacy branch. Metadata can request
a cooperative pause; it does not prove a fresh full checkpoint or model quality.
There is no process start, signal, flag removal, evaluator or background thread.
The hook runs after the existing write_status(), outside the queue lock.
"""
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CONFIG = ROOT / 'config/owner_qwen_training_guard.json'
STATUS = STATE / 'owner_qwen_training_guard.json'
ADMISSION = STATE / 'owner_training_admission.json'
PAUSE = STATE / 'TRAIN_PAUSE_REQUEST.flag'
HOLD = STATE / 'TRAIN_HOLD.flag'
MAINTENANCE = STATE / 'owner_maintenance.lock'
MAINTENANCE_FLAG = STATE / 'OWNER_MAINTENANCE.flag'
SCHEMA = 'NOX_QWEN_TRAINING_GUARD_V1'
CONFIG_SCHEMA = 'NOX_QWEN_TRAINING_GUARD_CONFIG_V1'
REVISION_CONFIG_SCHEMA = 'NOX_QWEN_TRAINING_GUARD_REVISION_CONFIG_V1'
REVISION_VERIFIER_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'  # Renderer replaces this only after shared-verifier review.
REVISION_VERIFIER = SCRIPTS / 'owner_qwen_execution_revision.py'
DEPENDENCIES = {
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
}
INITIAL_RECEIPT_SHA = '2336a33272f75d9fc56efd74172ccf09bba5067cceb1f67b6a966812d9a70262'
ACCEPTED_SIX_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
GIB = 1024 ** 3
MIB = 1024 ** 2
SHA = re.compile('[a-f0-9]{64}')
CHECKPOINT = re.compile('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}')
REQUIRED = {'adapter_model.safetensors', 'adapter_config.json', 'optimizer.pt', 'scheduler.pt',
            'scaler.pt', 'rng_state.pt', 'python_rng.json', 'student_state.json', 'lineage.json'}
REASONS = {'DISK_EARLY_MARGIN', 'EVALUATION_STALE', 'HOLDOUT_REGRESSION'}
DEFAULT_POLICY = {
    'poll_seconds': 5,
    'state_max_age_seconds': 30,
    'stale_successful_updates': 15,
    'regression_patience': 2,
    'regression_absolute_delta': 0.01,
    'regression_relative_delta': 0.01,
    'native_disk_floor_bytes': 10 * GIB,
    'disk_margin_bytes': 256 * MIB,
    'disk_urgent_margin_bytes': 64 * MIB,
    'disk_debounce_seconds': 5,
}
_IO_DEADLINE = threading.local()


class GuardHold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise GuardHold('HOLD_QWEN_GUARD_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def identity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def read(path, maximum=2 * MIB):
    deadline = getattr(_IO_DEADLINE, 'value', None)
    require(deadline is None or time.monotonic() < deadline, 'READ_BUDGET')
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    require(deadline is None or time.monotonic() < deadline, 'READ_BUDGET')
    return raw


def private(path):
    info = plain(path).stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600, 'PRIVATE_FILE_PERMISSIONS')


def pairs(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'JSON_DUPLICATE')
        result[key] = value
    return result


def document(path, maximum=2 * MIB):
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT')
    # This also rejects finite-looking JSON exponents that overflow to infinity.
    encode(value)
    return value, raw


def safe_code(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,100}', value) else type(exc).__name__


def integer(value):
    return type(value) is int and 0 <= value <= 10 ** 15


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def owner_stop():
    return any(p.exists() or p.is_symlink() for p in (
        ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop',
        STATE / 'STOP', ROOT / 'program/STOP', Path('/workspace/NOX_STOP')))


def context_shape(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and re.fullmatch('[0-9]{1,24}', str(value['request']))
            and type(value['request']) is str
            and re.fullmatch('[a-f0-9]{40}', str(value['source_sha']))
            and SHA.fullmatch(str(value['receipt_sha256'])), 'WINDOW_CONTEXT')
    return dict(value)


def validate_policy(value):
    require(isinstance(value, dict) and set(value) == set(DEFAULT_POLICY), 'POLICY_FIELDS')
    # These reviewed bounds cannot turn the guard into an unbounded controller.
    require(value['poll_seconds'] == 5 and type(value['poll_seconds']) is int
            and value['disk_debounce_seconds'] == 5 and type(value['disk_debounce_seconds']) is int
            and type(value['state_max_age_seconds']) is int and 10 <= value['state_max_age_seconds'] <= 30
            and type(value['stale_successful_updates']) is int and 1 <= value['stale_successful_updates'] <= 15
            and type(value['regression_patience']) is int and 1 <= value['regression_patience'] <= 2
            and value['native_disk_floor_bytes'] == 10 * GIB
            and type(value['native_disk_floor_bytes']) is int, 'POLICY_SCOPE')
    require(all(finite(value[k]) and 0 <= value[k] <= 0.05 for k in
                ('regression_absolute_delta', 'regression_relative_delta'))
            and integer(value['disk_margin_bytes']) and 256 * MIB <= value['disk_margin_bytes'] <= GIB
            and integer(value['disk_urgent_margin_bytes']) and 64 * MIB <= value['disk_urgent_margin_bytes']
            < value['disk_margin_bytes'], 'POLICY_MARGIN')
    return dict(value)


def configuration(window_context, source_sha256, *, enabled=True):
    require(SHA.fullmatch(str(source_sha256)) and type(enabled) is bool, 'CONFIG_ARGUMENTS')
    return {'schema': CONFIG_SCHEMA, 'enabled': enabled, 'source_sha256': source_sha256,
            'dependencies': dict(DEPENDENCIES),
            'window_admission': context_shape(window_context) if enabled else None,
            'policy': dict(DEFAULT_POLICY)}


def make_revision_guard_config(previous, revision_ref, guard_sha):
    """Pure rendering; no policy changes and no reinterpretation of the old window."""
    require(isinstance(previous, dict) and previous.get('schema') == CONFIG_SCHEMA
            and set(previous) == {'schema', 'enabled', 'source_sha256', 'dependencies', 'window_admission', 'policy'}
            and previous.get('enabled') is True and previous.get('dependencies') == DEPENDENCIES,
            'REVISION_CONFIG_PREIMAGE')
    require(SHA.fullmatch(str(guard_sha)) and SHA.fullmatch(str(REVISION_VERIFIER_SHA)), 'REVISION_CONFIG_PINS')
    value = copy.deepcopy(previous)
    value.update(schema=REVISION_CONFIG_SCHEMA, source_sha256=guard_sha,
                 window_admission=context_shape(previous['window_admission']),
                 execution_revision=context_shape(revision_ref), execution_verifier_sha256=REVISION_VERIFIER_SHA)
    value['policy'] = validate_policy(previous['policy'])
    return value


def make_successor_guard_config(previous, revision_ref, guard_sha):
    """Rebind the exact predecessor revision; origin and every policy value stay fixed."""
    predecessor = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
                   'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
    origin = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
              'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
    keys = {'schema', 'enabled', 'source_sha256', 'dependencies', 'window_admission', 'policy',
            'execution_revision', 'execution_verifier_sha256'}
    require(isinstance(previous, dict) and set(previous) == keys and previous['schema'] == REVISION_CONFIG_SCHEMA
            and previous['enabled'] is True and previous['dependencies'] == DEPENDENCIES
            and previous['source_sha256'] == '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656'
            and previous['execution_verifier_sha256'] == '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
            and previous['execution_revision'] == predecessor and previous['window_admission'] == origin
            and previous['policy'] == DEFAULT_POLICY, 'SUCCESSOR_CONFIG_PREIMAGE')
    policy = validate_policy(previous['policy']); current = context_shape(revision_ref)
    require(current['request'] != predecessor['request'] and SHA.fullmatch(str(guard_sha))
            and SHA.fullmatch(str(REVISION_VERIFIER_SHA)), 'SUCCESSOR_CONFIG_PINS')
    value = copy.deepcopy(previous)
    value.update(source_sha256=guard_sha, execution_revision=current,
                 execution_verifier_sha256=REVISION_VERIFIER_SHA, policy=policy)
    return value


def revision_module():
    raw = read(REVISION_VERIFIER)
    require(SHA.fullmatch(str(REVISION_VERIFIER_SHA)) and digest(raw) == REVISION_VERIFIER_SHA,
            'EXECUTION_VERIFIER_PIN')
    value = types.ModuleType('_nox_revision_guard_verifier')
    value.__file__ = str(REVISION_VERIFIER)
    exec(compile(raw, str(REVISION_VERIFIER), 'exec'), value.__dict__)
    return value


def checked_config(expected_context=None, expected_source=None):
    value, raw = document(CONFIG, 32768); private(CONFIG)
    revision = value.get('schema') == REVISION_CONFIG_SCHEMA
    keys = {'schema', 'enabled', 'source_sha256', 'dependencies', 'window_admission', 'policy'}
    if revision:
        keys |= {'execution_revision', 'execution_verifier_sha256'}
    require(set(value) == keys and value.get('schema') in {CONFIG_SCHEMA, REVISION_CONFIG_SCHEMA}
            and type(value.get('enabled')) is bool
            and value.get('dependencies') == DEPENDENCIES, 'CONFIG_SCOPE')
    actual_source = digest(read(Path(__file__)))
    require(value.get('source_sha256') == actual_source
            and (expected_source is None or expected_source == actual_source), 'SOURCE_PIN')
    value['policy'] = validate_policy(value['policy'])
    require(value['enabled'] is True, 'NOT_ENABLED')
    value['window_admission'] = context_shape(value['window_admission'])
    current = value['window_admission']
    if revision:
        current = context_shape(value['execution_revision'])
        require(value['execution_verifier_sha256'] == REVISION_VERIFIER_SHA
                and SHA.fullmatch(str(REVISION_VERIFIER_SHA)), 'EXECUTION_VERIFIER_PIN')
    require(expected_context is None or context_shape(expected_context) == current, 'CONTEXT_MISMATCH')
    return value, digest(raw)


def module(name):
    path = SCRIPTS / name; raw = read(path)
    require(digest(raw) == DEPENDENCIES[name], 'DEPENDENCY_PIN')
    value = types.ModuleType('_nox_guard_' + name.removesuffix('.py'))
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def context_evidence(config):
    """Reuse the exact window verifier, with stronger bounded read primitives."""
    if config.get('schema') == REVISION_CONFIG_SCHEMA:
        verifier = revision_module()
        ctx = verifier.current_context(config['execution_revision'])
        require(ctx['origin']['window_reference'] == config['window_admission']
                and ctx['context'] == config['execution_revision']
                and ctx['profile']['successful_updates_goal'] == 1000
                and ctx['output'] == OUTPUT, 'EXECUTION_CONTEXT')
        ctx.update(admission_sha256=ctx['execution']['admission_sha256'],
                   wrapper_sha256=ctx['execution']['wrapper_sha256'],
                   lineage_sha256=ctx['contract'].canonical_sha(ctx['lineage']), _revision_verifier=verifier)
        return ctx
    window = module('owner_qwen_window_entry.py')
    helper = module('owner_qwen_install_entry.py')
    observer = module('owner_qwen_training_observe.py')
    helper.read = read
    window.document = lambda h, path, maximum=2 * MIB: document(path, maximum)
    original_contract = window.source_contract

    def bounded_contract(h):
        contract = original_contract(h)
        corpus = STATE / 'qwen_corpus/6907283384'
        allowed = {corpus / name for name in ('train.jsonl', 'holdout.jsonl', 'corpus_manifest.json')}
        def corpus_sha(path, chunk=MIB):
            require(Path(path) in allowed, 'CORPUS_SCOPE')
            return digest(read(path, 32 * MIB))
        # Only the read implementation changes; the expected hashes and all
        # profile/source/wrapper/provenance comparisons remain the pinned ones.
        contract.sha256_file = corpus_sha
        return contract
    window.source_contract = bounded_contract
    initial = STATE / 'owner_qwen_install_6907283384.json'
    require(digest(read(initial)) == INITIAL_RECEIPT_SHA, 'INITIAL_RECEIPT_PIN')
    ctx = window.context(helper)
    require(ctx['profile']['successful_updates_goal'] == 1000 and ctx['output'] == OUTPUT, 'WINDOW1000_REQUIRED')
    admitted = config['window_admission']
    receipt, raw = document(STATE / ('owner_qwen_window_' + admitted['request'] + '.json'))
    acceptance = receipt.get('acceptance') or {}
    require(digest(raw) == admitted['receipt_sha256']
            and receipt.get('schema') == 'NOX_QWEN_WINDOW_ADVANCE_V1'
            and receipt.get('state') == 'WINDOW_STARTED_ACCEPTANCE_PENDING'
            and receipt.get('request') == admitted['request'] == ctx['admission'].get('request')
            and receipt.get('source_sha') == admitted['source_sha'] == ctx['admission'].get('source_sha')
            and receipt.get('target_goal') == 1000
            and acceptance.get('previous_goal') == 6 and acceptance.get('target_goal') == 1000
            and receipt.get('new_admission_sha256') == digest(ctx['raw'])
            and receipt.get('wrapper_sha256') == digest(ctx['wrapper']), 'SEALED_WINDOW1000')
    lineage, _ = document(OUTPUT / 'owner_lineage.json')
    observer.lineage_proof(lineage, ctx['contract'], ctx['profile'])
    lineage_sha = ctx['contract'].canonical_sha(lineage)
    certificate, certificate_raw = document(OUTPUT / 'owner_acceptance.json')
    require(digest(certificate_raw) == ACCEPTED_SIX_SHA == acceptance.get('acceptance_sha256')
            == acceptance.get('terminal_receipt_sha256')
            and certificate.get('successful_optimizer_steps') == 6
            and certificate.get('new_successful_optimizer_steps') == 1
            and certificate.get('state') == 'STUDENT_RESTART_AND_UPDATES_VERIFIED'
            and acceptance.get('lineage_sha256') == lineage_sha, 'ACCEPTED_SIX_ANCHOR')
    ctx['contract'].verify_proof(certificate, lineage=lineage, minimum_updates=6)
    cp = acceptance.get('checkpoint') or {}
    require(certificate.get('checkpoint') == str(OUTPUT / str(cp.get('directory')))
            and certificate.get('checkpoint_manifest_sha256') == cp.get('manifest_sha256')
            and cp.get('all_checkpoint_file_sha256_verified') is True, 'SIX_CHECKPOINT_ANCHOR')
    require(read(ADMISSION, 64000) == ctx['raw'] and read(helper.WRAPPER) == ctx['wrapper'], 'ADMISSION_CHANGED')
    ctx.update(observer=observer, lineage=lineage, lineage_sha256=lineage_sha, certificate=certificate,
               context=admitted, admission_sha256=digest(ctx['raw']), wrapper_sha256=digest(ctx['wrapper']))
    return ctx


def checkpoint_metadata(ctx):
    """Hash small committed records only; never claim all tensor files verified."""
    output = ctx['output']; observer = ctx['observer']
    pointer, pointer_raw = document(output / 'latest_checkpoint.json', 16384)
    name = pointer.get('directory')
    require(isinstance(name, str) and CHECKPOINT.fullmatch(name) and SHA.fullmatch(str(pointer.get('manifest_sha256'))),
            'CHECKPOINT_POINTER')
    directory = plain(output / name)
    manifest, manifest_raw = document(directory / 'checkpoint_manifest.json', 65536)
    files = manifest.get('files_sha256')
    require(digest(manifest_raw) == pointer['manifest_sha256']
            and manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1' and manifest.get('directory') == name
            and manifest.get('lineage_sha256') == ctx['lineage_sha256']
            and isinstance(files, dict) and REQUIRED <= files.keys() and len(files) <= 32
            and all(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', key) and key != 'checkpoint_manifest.json'
                    and SHA.fullmatch(str(pin)) for key, pin in files.items()), 'CHECKPOINT_MANIFEST')
    require(set(p.name for p in directory.iterdir()) == set(files) | {'checkpoint_manifest.json'}, 'CHECKPOINT_FILES')
    sizes = []
    for name in files:
        info = plain(directory / name).stat(follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_size >= 0, 'CHECKPOINT_FILE_TYPE')
        sizes.append(info.st_size)
    require(0 < sum(sizes) <= 2 * GIB, 'CHECKPOINT_BYTES')
    saved_lineage, lineage_raw = document(directory / 'lineage.json')
    saved, saved_raw = document(directory / 'student_state.json')
    require(digest(lineage_raw) == files['lineage.json'] and saved_lineage == ctx['lineage']
            and digest(saved_raw) == files['student_state.json'], 'CHECKPOINT_METADATA_SHA')
    proof = observer.update_chain(saved, ctx['contract'])
    require(6 <= proof['successful_optimizer_steps'] <= 1000
            and saved['update_evidence'][:6] == ctx['certificate']['update_evidence']
            and manifest.get('successful_total') == proof['successful_optimizer_steps']
            and manifest.get('attempted_total') == proof['attempted_steps']
            and manifest.get('adapter_tensor_sha256') == proof['adapter_tensor_sha256']
            and manifest.get('holdout_loss') == saved['last_holdout_loss']
            and manifest.get('holdout_evaluated_successful_total') == saved['holdout_evaluated_successful_total']
            and read(output / 'latest_checkpoint.json', 16384) == pointer_raw
            and read(directory / 'checkpoint_manifest.json', 65536) == manifest_raw, 'CHECKPOINT_METADATA_CHANGED')
    result = {'pointer_sha256': digest(pointer_raw), 'manifest_sha256': digest(manifest_raw),
            'student_state_sha256': digest(saved_raw), 'successful_updates': proof['successful_optimizer_steps'],
            'attempted_updates': proof['attempted_steps'], 'skipped_updates': proof['skipped_steps'],
            'evaluated_at_update': saved['holdout_evaluated_successful_total'], 'holdout_loss': saved['last_holdout_loss'],
            'observed_file_bytes': sum(sizes), 'recorded_files': len(files),
            'metadata_hashes_verified': True, 'all_checkpoint_file_hashes_verified': False}
    if 'execution' in ctx:
        verifier = ctx['_revision_verifier']
        active = verifier.activation_status(ctx)['active']
        result['execution_binding'] = verifier.checkpoint_binding(
            ctx, manifest, saved, allow_initial_anchor=not active)
    return result


def checkpoint_budget(parameters, observed_bytes):
    require(integer(parameters) and 0 < parameters <= 100_000_000
            and integer(observed_bytes) and 0 < observed_bytes <= 2 * GIB, 'BUDGET_INPUT')
    value = max(16 * parameters + 128 * MIB, (3 * observed_bytes + 1) // 2)
    require(value <= 2 * GIB, 'BUDGET_EXCEEDS_NATIVE_CAP')
    return value


def policy_step(previous, checkpoint, free_bytes, parameters, now, policy, initial_loss):
    """Pure policy: debounce only while room for a checkpoint remains."""
    require(integer(free_bytes) and finite(now), 'POLICY_TELEMETRY')
    p = validate_policy(policy)
    good, evaluated, loss = (checkpoint[k] for k in ('successful_updates', 'evaluated_at_update', 'holdout_loss'))
    require(integer(good) and 6 <= good <= 1000 and integer(evaluated) and 0 <= evaluated <= good
            and finite(loss) and loss >= 0 and finite(initial_loss) and initial_loss >= 0, 'POLICY_CHECKPOINT')
    value = copy.deepcopy(previous) if previous else {
        'last_successful_updates': 6, 'last_evaluation_update': 6, 'best_holdout_loss': initial_loss,
        'regression_streak': 0, 'observed_distinct_evaluations': 0,
        'low_since': None, 'last_sample_at': None, 'last_free_bytes': None,
        'inhibit': False, 'reason': None, 'latched_at': None,
    }
    require(good >= value['last_successful_updates'] and evaluated >= value['last_evaluation_update'], 'CHECKPOINT_REGRESSION')
    if evaluated > value['last_evaluation_update']:
        threshold = value['best_holdout_loss'] + max(p['regression_absolute_delta'],
                                                    abs(value['best_holdout_loss']) * p['regression_relative_delta'])
        # A copied old loss cannot become a second evaluation. If a current
        # evaluated checkpoint was missed, reset the observed streak rather
        # than infer its chronology from directory times or ledger labels.
        current = evaluated == good
        value['regression_streak'] = value['regression_streak'] + 1 if current and loss > threshold else 0
        value['observed_distinct_evaluations'] += int(current)
        value['best_holdout_loss'] = min(value['best_holdout_loss'], loss)
        value['last_evaluation_update'] = evaluated
    budget = checkpoint_budget(parameters, checkpoint['observed_file_bytes'])
    floor = p['native_disk_floor_bytes']
    early, urgent = floor + budget + p['disk_margin_bytes'], floor + budget + p['disk_urgent_margin_bytes']
    previous_time, previous_free = value['last_sample_at'], value['last_free_bytes']
    interval = now - previous_time if previous_time is not None else None
    require(interval is None or interval >= 0, 'CLOCK_REGRESSION')
    disk_reason = False
    if free_bytes >= early:
        value['low_since'] = None
    elif free_bytes <= urgent:
        disk_reason = True
    else:
        if value['low_since'] is None or interval is None or interval > 2 * p['poll_seconds']:
            value['low_since'] = now
        disk_reason = now - value['low_since'] >= p['disk_debounce_seconds']
    reason = None
    if good < 1000:
        if disk_reason:
            reason = 'DISK_EARLY_MARGIN'
        elif good - evaluated >= p['stale_successful_updates']:
            reason = 'EVALUATION_STALE'
        elif value['regression_streak'] >= p['regression_patience']:
            reason = 'HOLDOUT_REGRESSION'
    if reason and not value['inhibit']:
        value.update(inhibit=True, reason=reason, latched_at=now)
    value.update(last_successful_updates=good, last_sample_at=now, last_free_bytes=free_bytes,
                 checkpoint_budget_bytes=budget, disk_early_threshold_bytes=early,
                 disk_urgent_threshold_bytes=urgent, disk_floor_bytes=floor,
                 floor_already_crossed=free_bytes < floor, complete=good == 1000,
                 evaluation_age_updates=good - evaluated)
    return value


def bindings(config, config_sha, ctx):
    value = {'source_sha256': config['source_sha256'], 'config_sha256': config_sha,
            'window_admission': dict(config['window_admission']), 'admission_sha256': ctx['admission_sha256'],
            'wrapper_sha256': ctx['wrapper_sha256'], 'lineage_sha256': ctx['lineage_sha256']}
    if 'execution' in ctx:
        value.update(execution_revision=dict(ctx['execution']['reference']),
                     execution_descriptor_sha256=ctx['execution']['descriptor_sha256'],
                     execution_verifier_sha256=ctx['execution']['verifier_sha256'])
    return value


def bootstrap_decision(previous, checkpoint, free_bytes, parameters, now, policy, initial_loss, activation):
    """Preserve quality history until the finite issuer accepts full checkpoint bytes.

The only suppression is reissuing the original stale-evaluation pause during
the bounded evaluation phase. Fresh disk or quality hazards still request pause.
This routine neither clears the latch nor grants optimizer/resume permission.
"""
    require(isinstance(previous, dict) and previous.get('inhibit') is True
            and previous.get('reason') == 'EVALUATION_STALE', 'BOOTSTRAP_PRIOR_POLICY')
    require(activation.get('active') is False, 'BOOTSTRAP_ALREADY_ACTIVE')
    preview = policy_step(previous, checkpoint, free_bytes, parameters, now, policy, initial_loss)
    decision = copy.deepcopy(previous)
    for key in ('low_since', 'last_sample_at', 'last_free_bytes', 'checkpoint_budget_bytes',
                'disk_early_threshold_bytes', 'disk_urgent_threshold_bytes', 'disk_floor_bytes',
                'floor_already_crossed', 'complete', 'evaluation_age_updates'):
        decision[key] = preview[key]
    baseline = activation.get('baseline_successful_total')
    deadline = activation.get('deadline')
    blocked = None
    if not (activation.get('bootstrap_pending') is True and finite(deadline) and now <= deadline):
        blocked = 'BOOTSTRAP_DEADLINE_OR_SCOPE'
    elif not (integer(baseline) and checkpoint['successful_updates'] == baseline == previous['last_successful_updates']):
        blocked = 'BOOTSTRAP_UNEXPECTED_OPTIMIZER_UPDATE'
    elif free_bytes < preview['disk_early_threshold_bytes']:
        blocked = 'DISK_EARLY_MARGIN'
    elif preview['regression_streak'] >= policy['regression_patience']:
        blocked = 'HOLDOUT_REGRESSION'
    return decision, {'state': 'INHIBITED' if blocked else 'BOOTSTRAP_EVALUATION',
                      'pause_required': blocked is not None, 'blocked_reason': blocked,
                      'quality_history_preserved': True, 'optimizer_permission': False,
                      'deadline': deadline, 'baseline_successful_total': baseline}


def previous_state(expected):
    if not STATUS.exists() and not STATUS.is_symlink():
        return None, None
    row, raw = document(STATUS, 65536); private(STATUS)
    require(row.get('schema') == SCHEMA and row.get('bindings') == expected
            and isinstance(row.get('policy_state'), dict), 'STATE_SCOPE')
    return row, digest(raw)


def atomic_state(row, previous_sha):
    plain(STATUS)
    if previous_sha is None:
        require(not STATUS.exists() and not STATUS.is_symlink(), 'STATE_COLLISION')
    else:
        require(digest(read(STATUS, 65536)) == previous_sha, 'STATE_CHANGED')
    raw = encode(row); require(len(raw) <= 65536, 'STATE_BOUND')
    fd, name = tempfile.mkstemp(prefix='.qwen-guard-', dir=plain(STATE))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, STATUS)
        directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    require(read(STATUS, 65536) == raw, 'STATE_READBACK')
    return digest(raw)


def pause_token(row):
    p = row['policy_state']; require(p['inhibit'] is True and p['reason'] in REASONS, 'PAUSE_REASON')
    return ('NOX_QWEN_GUARD_PAUSE_V1 context=' + digest(encode(row['bindings'])) + ' source='
            + row['bindings']['source_sha256'] + ' reason=' + p['reason'] + '\n').encode()


def request_pause(row):
    """O_EXCL only; existing manual/media/trainer flags are never changed."""
    if owner_stop() or MAINTENANCE_FLAG.exists() or MAINTENANCE_FLAG.is_symlink():
        return 'OWNER_STOP_OR_MAINTENANCE'
    if HOLD.exists() or HOLD.is_symlink():
        return 'EXISTING_HOLD_PRESERVED'
    token = pause_token(row)
    if PAUSE.exists() or PAUSE.is_symlink():
        return 'OWN_PAUSE_PRESENT' if not PAUSE.is_symlink() and read(PAUSE, 4096) == token else 'EXISTING_PAUSE_PRESERVED'
    try:
        fd = os.open(plain(PAUSE), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except FileExistsError:
        return 'EXISTING_PAUSE_PRESERVED'
    with os.fdopen(fd, 'wb') as stream:
        stream.write(token); stream.flush(); os.fsync(stream.fileno())
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    require(read(PAUSE, 4096) == token, 'PAUSE_READBACK')
    return 'OWN_PAUSE_REQUESTED'


def disk_free():
    info = os.statvfs(plain(OUTPUT))
    return info.f_bavail * info.f_frsize


class Guard:
    def __init__(self, expected_source):
        require(SHA.fullmatch(str(expected_source)) and digest(read(Path(__file__))) == expected_source, 'BIND_SOURCE')
        self.expected_source, self.lock, self.last_poll = expected_source, threading.Lock(), None
        self.last_result = {'state': 'NOT_SAMPLED'}

    def tick(self):
        if not self.lock.acquire(blocking=False):
            return self.last_result
        lease = None
        old_deadline = getattr(_IO_DEADLINE, 'value', None)
        try:
            monotonic = time.monotonic()
            if self.last_poll is not None and monotonic - self.last_poll < 5:
                return self.last_result
            self.last_poll = monotonic
            _IO_DEADLINE.value = monotonic + 4
            # No config, dependency loads, state writes or flags for window5/6.
            pointer, _ = document(ADMISSION, 64000)
            if (pointer.get('student_profile') or {}).get('successful_updates_goal') != 1000:
                self.last_result = {'state': 'NON_TARGET_WINDOW_NO_ACTION'}
                return self.last_result
            lease = os.open(plain(MAINTENANCE), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            require(stat.S_ISREG(os.fstat(lease).st_mode), 'MAINTENANCE_FILE')
            try:
                fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                self.last_result = {'state': 'WAIT_OWNER_MAINTENANCE'}
                return self.last_result
            if owner_stop() or MAINTENANCE_FLAG.exists() or MAINTENANCE_FLAG.is_symlink():
                self.last_result = {'state': 'WAIT_OWNER_STOP_OR_MAINTENANCE'}
                return self.last_result
            config, config_sha = checked_config(expected_source=self.expected_source)
            ctx = context_evidence(config)
            expected = bindings(config, config_sha, ctx)
            prior, prior_sha = previous_state(expected)
            checkpoint = checkpoint_metadata(ctx)
            now = time.time()
            free_bytes = disk_free()
            decision = policy_step(prior['policy_state'] if prior else None, checkpoint, free_bytes,
                                   ctx['lineage']['targets']['parameters'], now, config['policy'],
                                   ctx['certificate']['final_holdout_loss'])
            bootstrap = None
            if 'execution' in ctx:
                activation = ctx['_revision_verifier'].activation_status(ctx)
                if not activation['active']:
                    require(prior is not None, 'BOOTSTRAP_STATE_MISSING')
                    decision, bootstrap = bootstrap_decision(prior['policy_state'], checkpoint, free_bytes,
                        ctx['lineage']['targets']['parameters'], now, config['policy'],
                        ctx['certificate']['final_holdout_loss'], activation)
            row = {'schema': SCHEMA, 'bindings': expected, 'sampled_at': now, 'policy_state': decision,
                   'checkpoint': checkpoint, 'state': 'INHIBITED' if decision['inhibit'] else 'MONITORING',
                   'pause_flag': 'NOT_REQUESTED', 'checkpoint_after_pause_verified': False,
                   'scope': 'HASH_BOUND_CHECKPOINT_METADATA_AND_PAUSE_REQUEST_ONLY'}
            if bootstrap is not None:
                row.update(state=bootstrap['state'], execution_bootstrap=bootstrap)
            # The exact context is still current immediately before either write.
            require(read(ADMISSION, 64000) == ctx['raw'] and digest(read(CONFIG, 32768)) == config_sha
                    and not owner_stop() and not MAINTENANCE_FLAG.exists(), 'PREWRITE_CONTEXT_CHANGED')
            saved_sha = atomic_state(row, prior_sha)
            if decision['inhibit'] and (bootstrap is None or bootstrap['pause_required']):
                row['pause_flag'] = request_pause(row)
                atomic_state(row, saved_sha)
            self.last_result = {'state': row['state'], 'reason': decision['reason'],
                                'inhibit': decision['inhibit'], 'pause_flag': row['pause_flag']}
        except Exception as exc:
            # A broken read cannot create a pause or authorize a handback.
            # The immutable binding and freshness checks in resume_block_reason
            # reject the failure independently; no foreign state is overwritten.
            self.last_result = {'state': 'HELD', 'reason': safe_code(exc)}
        finally:
            if lease is not None:
                os.close(lease)
            _IO_DEADLINE.value = old_deadline
            self.lock.release()
        return self.last_result


def resume_block_reason(context):
    """Read-only; caller already holds maintenance EX. None means guard permits.

This never acquires that lease again, never clears a latch/flag and never starts
a process. Other handback checkpoint/resource/owner-flag gates still apply.
"""
    old_deadline = getattr(_IO_DEADLINE, 'value', None)
    _IO_DEADLINE.value = time.monotonic() + 4
    try:
        require(not owner_stop(), 'OWNER_STOP')
        config, config_sha = checked_config(context)
        ctx = context_evidence(config)
        if 'execution' in ctx and not ctx['_revision_verifier'].activation_status(ctx)['active']:
            return 'WAIT_QWEN_GUARD_EXECUTION_BOOTSTRAP'
        expected = bindings(config, config_sha, ctx)
        previous, _ = previous_state(expected)
        require(previous is not None, 'STATE_MISSING')
        p = previous['policy_state']
        if p.get('inhibit') is True:
            require(p.get('reason') in REASONS, 'STATE_REASON')
            return 'HOLD_QWEN_GUARD_' + p['reason']
        now = time.time(); sampled = previous.get('sampled_at')
        require(finite(sampled) and 0 <= now - sampled <= config['policy']['state_max_age_seconds'], 'STATE_STALE')
        require(previous.get('state') == 'MONITORING' and p.get('inhibit') is False, 'STATE_NOT_PERMISSIVE')
        require(p.get('complete') is False, 'GOAL_ALREADY_COMPLETE')
        checkpoint = checkpoint_metadata(ctx)
        require(checkpoint == previous.get('checkpoint'), 'STATE_CHECKPOINT_PENDING')
        free = disk_free()
        checked = policy_step(p, checkpoint, free, ctx['lineage']['targets']['parameters'], now,
                              config['policy'], ctx['certificate']['final_holdout_loss'])
        require(checked['inhibit'] is False and free >= checked['disk_early_threshold_bytes'], 'RESUME_MARGIN_OR_QUALITY')
        require(read(ADMISSION, 64000) == ctx['raw'] and digest(read(CONFIG, 32768)) == config_sha, 'RESUME_CONTEXT_CHANGED')
        return None
    except Exception as exc:
        value = safe_code(exc)
        return value if value.startswith(('WAIT_', 'HOLD_')) else 'HOLD_QWEN_GUARD_EVIDENCE_UNAVAILABLE'
    finally:
        _IO_DEADLINE.value = old_deadline


def bind_dispatcher(namespace, expected_sha256):
    existing = namespace.get('_owner_qwen_training_guard')
    if existing is not None:
        require(existing.expected_source == expected_sha256, 'ALREADY_BOUND_OTHER_SOURCE')
        return existing
    previous = namespace.get('write_status')
    require(callable(previous), 'WRITE_STATUS_HOOK')
    guard = Guard(expected_sha256)
    def write_status(*args, **kwargs):
        try:
            return previous(*args, **kwargs)
        finally:
            guard.tick()
    namespace['write_status'] = write_status
    namespace['_owner_qwen_training_guard'] = guard
    return guard
