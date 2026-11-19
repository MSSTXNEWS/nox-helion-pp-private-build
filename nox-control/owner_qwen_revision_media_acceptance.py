#!/usr/bin/env python3
"""One owner image through the ordinary queue, then observe its trainer handback.

This finite entry submits once through the authenticated API. It never starts a
service, changes a training flag, acquires a controller/maintenance lease, or
retries generation. A separate read-only observe_existing call can continue
watching the same sealed submission. A saved post-resume update, not a process
start or a generated image, establishes optimizer continuity.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
AREA = STATE / 'media/revision_acceptance'
SCHEMA = 'NOX_QWEN_REVISION_MEDIA_ACCEPTANCE_V1'
SUBMISSION_SCHEMA = 'NOX_QWEN_REVISION_MEDIA_SUBMISSION_V1'
HELPER = 'owner_media_acceptance_entry.py'
HELPER_SHA = '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'
PINS = {
    'owner_qwen_execution_revision.py': '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e',
    'owner_training_status.py': 'c643fe595e09036302818da8e780269ab2e1b48451025b33cb9b491a911eb879',
    'owner_qwen_training_guard.py': '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656',
    'owner_qwen_media_handoff.py': 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce',
    'owner_qwen_media_guard.py': 'c0feb873174e776285563fdb0290a4b1064402d33c3c05c58d847531690d7723',
    'owner_qwen_handback_retry.py': '70784355b8458d67f5de0a15b2cce4aaf225fa2522fe90b09f359372ee95fc39',
    'owner_hermes_hydrate.py': '65daf1acd5dd937e23b9f960dedb720b8259793729115bab153993a282e735a3',
    'owner_media_runtime.py': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5',
}
FIXTURE = {'kind': 'image', 'prompt': 'An abstract NOX study: a red cube and a blue sphere on a pale background, soft studio light, no lettering.',
           'negative_prompt': 'text, watermark', 'width': 256, 'height': 256,
           'frames': 1, 'fps': 8, 'seed': 160116}
HANDOFF_SCOPE = 'QWEN_CHECKPOINT_RESTORED_TRAINER_ADMISSION_ONLY'
HANDOFF_BLOCKERS = ['OPTIMIZER_PROGRESS_AFTER_RESUME_NOT_PROVEN', 'MODEL_PROMOTION_NOT_AUTHORIZED']
JOB = re.compile('[a-f0-9]{32}')
SHA = re.compile('[a-f0-9]{64}')
TASK_STATES = {'pending', 'wait', 'retry', 'running', 'done', 'blocked', 'failed', 'cancelled'}
PENDING_STATES = {'MEDIA_GENERATION_PENDING', 'MEDIA_COMPLETE_RESUME_PENDING'}
TRANSIENT_GUARD = {'HOLD_QWEN_GUARD_STATE_STALE', 'HOLD_QWEN_GUARD_STATE_CHECKPOINT_PENDING',
                   'HOLD_QWEN_GUARD_STATE_MISSING'}
GIB = 1024 ** 3


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_MEDIA_ACCEPTANCE_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def integer(value):
    return type(value) is int and 0 <= value <= 10 ** 15


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else 'HOLD_QWEN_MEDIA_ACCEPTANCE_' + type(exc).__name__.upper()


def reference(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and isinstance(value['request'], str) and re.fullmatch('[0-9]{1,24}', value['request'])
            and isinstance(value['source_sha'], str) and re.fullmatch('[a-f0-9]{40}', value['source_sha'])
            and isinstance(value['receipt_sha256'], str) and SHA.fullmatch(value['receipt_sha256']), 'REFERENCE')
    return dict(value)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def read(path, maximum=2 * 1024 ** 2, *, expected=None):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum, 'FILE_SCOPE')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    require(expected is None or digest(raw) == expected, 'FILE_SHA')
    return raw


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'DUPLICATE_JSON_KEY'); value[key] = item
    return value


def document(path, maximum=2 * 1024 ** 2, *, expected=None, changing=False):
    for attempt in range(3):
        try:
            raw = read(path, maximum, expected=expected)
            value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
            require(isinstance(value, dict), 'JSON_OBJECT')
            return value, digest(raw)
        except RuntimeError as exc:
            if not changing or str(exc) != 'HOLD_QWEN_MEDIA_ACCEPTANCE_FILE_CHANGED' or attempt == 2:
                raise
            time.sleep(.05)


def fsync_directory(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_create(path, value):
    """No replacement; an uncertain prior submission remains visible forever."""
    path = plain(path); raw = encoded(value) + b'\n'
    require(len(raw) <= 131072, 'PRIVATE_RECEIPT_BOUND')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        created = os.fstat(stream.fileno())
    fsync_directory(path.parent)
    require(read(path, 131072) == raw and identity(path.stat(follow_symlinks=False)) == identity(created)
            and stat.S_IMODE(created.st_mode) == 0o600 and created.st_nlink == 1, 'PRIVATE_RECEIPT_READBACK')
    return digest(raw)


def module(raw, name, pin):
    require(0 < len(raw) <= 262144 and digest(raw) == pin, 'SOURCE_PIN')
    value = types.ModuleType('_nox_revision_media_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name)
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def dependencies():
    helper = module(base64.b64decode(BUNDLE.get(HELPER, ''), validate=True), HELPER, HELPER_SHA)
    # Definitions only. The historical helper main/guards/unload are never used.
    loaded = {name: module(read(SCRIPTS / name, 262144), name, PINS[name]) for name in (
        'owner_qwen_execution_revision.py', 'owner_training_status.py', 'owner_qwen_training_guard.py',
        'owner_media_runtime.py')}
    return helper, loaded


def context(loaded, ref):
    shared = loaded['owner_qwen_execution_revision.py']
    ctx = shared.current_context(ref)
    require(ctx['context'] == ref and shared.activation_status(ctx)['active'] is True, 'EXECUTION_NOT_ACTIVE')
    for name, pin in PINS.items():
        read(SCRIPTS / name, 262144, expected=pin)
        if name in ctx['execution']['descriptor']['consumer_sources']:
            require(ctx['execution']['descriptor']['consumer_sources'][name] == pin, 'CONSUMER_GRAPH')
    return ctx


def handoff_config(ctx):
    row, pin = document(ROOT / 'config/owner_qwen_media_handoff.json', 32768)
    require(row.get('schema') == 'NOX_QWEN_MEDIA_HANDOFF_REVISION_CONFIG_V1'
            and row.get('enabled') is True and row.get('resume_training_after_media') is True
            and row.get('source_sha256') == PINS['owner_qwen_media_handoff.py']
            and row.get('runtime_sha256') == PINS['owner_media_runtime.py']
            and row.get('execution_verifier_sha256') == PINS['owner_qwen_execution_revision.py']
            and row.get('execution_revision') == ctx['context']
            and row.get('window_admission') == ctx['origin']['window_reference'], 'HANDOFF_CONFIG')
    return row, pin


def live(ctx):
    obs = ctx['observer']; service = obs.service(); rows = obs.trainers(ctx['argv'], service)
    process = rows[0] if len(rows) == 1 else None
    if not (service.get('state') == 'RUNNING' and process and all(process.get(key) is True for key in (
            'exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified'))):
        return service, None
    again = obs.process(process['pid'])
    require(again and again['start_ticks'] == process['start_ticks'] and obs.service() == service, 'LIVE_IDENTITY_CHANGED')
    boot = obs.proc_bytes(Path('/proc/sys/kernel/random/boot_id'), 64).decode('ascii').strip()
    require(re.fullmatch('[a-f0-9-]{36}', boot), 'BOOT_ID')
    return service, {**{key: process[key] for key in ('pid', 'ppid', 'start_ticks')}, 'boot_id': boot}


def latest(ctx):
    return document(ctx['output'] / 'latest_checkpoint.json', 16384, changing=True)


def checkpoint(loaded, ctx, pointer, budget, deadline):
    reader = loaded['owner_training_status.py']; obs = reader.observer()
    _, _, argv, gate = reader.admitted(ctx['context'], obs)
    require(argv == ctx['argv'] and gate.get('execution_active') is True, 'STATUS_CURRENT_CONTEXT')
    original = obs.read; per_checkpoint = 0
    def bounded(*args, **kwargs):
        nonlocal per_checkpoint
        if kwargs.get('keep', True) is False:
            args = list(args)
            require(len(args) == 2 and per_checkpoint < GIB and budget['bytes'] < 2 * GIB, 'CHECKPOINT_BYTE_BUDGET')
            args[1] = min(args[1], GIB - per_checkpoint, 2 * GIB - budget['bytes'])
            kwargs['deadline'] = min(deadline, kwargs.get('deadline', deadline))
            raw, meta = original(*args, **kwargs)
            per_checkpoint += meta['bytes']; budget['bytes'] += meta['bytes']
            return raw, meta
        return original(*args, **kwargs)
    obs.read = bounded
    proof, manifest, saved = reader.checkpoint(obs, ctx['contract'], ctx['lineage'], pointer.get('directory'),
                                              pointer.get('manifest_sha256'), min(deadline, time.monotonic() + 45))
    require(proof.get('current_checkpoint_files_verified') is True and proof['checkpoint_file_count'] == 10
            and proof.get('execution_revision_checkpoint_verified') is True
            and proof.get('evaluation_witness_verified') is True, 'CHECKPOINT_CURRENT_EXECUTION')
    return proof, manifest, saved, obs


def checkpoint_summary(proof, manifest, saved):
    return {'directory': manifest['directory'], 'manifest_sha256': proof['manifest_sha256'],
            'successful_total': saved['successful_total'], 'attempted_total': saved['attempted_total'],
            'skipped_total': saved['skipped_total'], 'data_cursor': saved['data_cursor'],
            'student_state_sha256': manifest['files_sha256']['student_state.json'],
            'adapter_tensor_sha256': proof['adapter_tensor_sha256'],
            'update_prefix_sha256': digest(encoded(saved['update_evidence'])),
            'verified_files': proof['checkpoint_file_count'], 'verified_bytes': proof['verified_bytes'],
            'full_checkpoint_files_verified': True, 'execution_evaluation_witness_verified': True,
            'process_identity': {key: manifest['process_identity'][key] for key in ('pid', 'start_ticks', 'boot_id')}}


def guard_gate(guard, ref):
    reason = guard.resume_block_reason(ref)
    if reason is not None:
        require(isinstance(reason, str) and re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', reason), 'GUARD_REASON')
        raise RuntimeError(reason)


def idle_training_controls(guard):
    # The handback's guard reader intentionally leaves flag ownership to its
    # caller. A new smoke must not take over an already requested pause.
    require(not guard.owner_stop(), 'OWNER_STOP')
    require(not any((STATE / name).exists() or (STATE / name).is_symlink() for name in (
        'TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag', 'OWNER_MAINTENANCE.flag')), 'TRAINING_CONTROL_PRESENT')
    path = STATE / 'media/training_yield.json'
    if path.exists() or path.is_symlink():
        value, _ = document(path, 131072, changing=True)
        require(value.get('active') is False, 'PREVIOUS_MEDIA_YIELD_NOT_VERIFIED_IDLE')


def preconditions(helper, loaded, ref, deadline):
    ctx = context(loaded, ref); guard = loaded['owner_qwen_training_guard.py']
    require(not guard.owner_stop(), 'OWNER_STOP')
    guard_gate(guard, ref)
    idle_training_controls(guard)
    config, config_sha = handoff_config(ctx)
    service, process = live(ctx)
    require(process is not None, 'CURRENT_TRAINER_NOT_RUNNING')
    pointer, pointer_sha = latest(ctx); budget = {'bytes': 0}
    proof, manifest, saved, _ = checkpoint(loaded, ctx, pointer, budget, deadline)
    require(manifest.get('process_identity', {}).get('pid') == process['pid']
            and manifest['process_identity'].get('start_ticks') == process['start_ticks']
            and manifest['process_identity'].get('boot_id') == process['boot_id'], 'CURRENT_PROCESS_CHECKPOINT')
    require(latest(ctx) == (pointer, pointer_sha) and live(ctx) == (service, process), 'PRE_SUBMISSION_CHANGED')
    guard_gate(guard, ref)
    helper.no_other_jobs(loaded['owner_media_runtime.py'])
    caps = loaded['owner_media_runtime.py'].capabilities()
    require(caps.get('image') is True, 'IMAGE_NOT_READY')
    queue = loaded['owner_media_runtime.py'].queue_ids()
    require(set(queue) == {'queue_running', 'queue_pending'} and not any(queue.values()), 'ENGINE_QUEUE_NOT_EMPTY')
    return ctx, {'trainer': process, 'service': service, 'dispatcher': helper.dispatcher_identity(),
        'checkpoint': checkpoint_summary(proof, manifest, saved), 'handoff_config_sha256': config_sha,
        'handoff_config_canonical_sha256': digest(encoded(config)),
        'admission_sha256': ctx['execution']['admission_sha256'], 'wrapper_sha256': ctx['execution']['wrapper_sha256']}, budget


def prepare_directory(ref):
    plain(AREA); AREA.mkdir(mode=0o700, exist_ok=True)
    info = AREA.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077, 'PRIVATE_PARENT')
    fsync_directory(AREA.parent)
    directory = AREA / ref['request']
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        require(False, 'PRIOR_INTENT_REQUIRES_OBSERVATION')
    fsync_directory(AREA)
    return directory


def submit_once(client, directory, ref, owner_request, owner_source, before, activity=None):
    intent = {'schema': SUBMISSION_SCHEMA, 'stage': 'PREPARED_SINGLE_POST', 'execution_revision': ref,
              'request': owner_request, 'source_sha': owner_source, 'fixture_sha256': digest(encoded(FIXTURE)),
              'created_at': time.time(), 'before': before, 'generation_retry_authorized': False}
    intent_sha = private_create(directory / 'intent.json', intent)
    # A timeout can mean the API created the job. Never issue a second POST.
    if activity is not None:
        activity['generation_post_attempts'] = 1
    value = client.json('/api/ui/media/jobs', method='POST', data=dict(FIXTURE), status=202)
    jid = value.get('id')
    require(isinstance(jid, str) and JOB.fullmatch(jid) and value.get('request') == FIXTURE
            and value.get('state') == 'QUEUED', 'POST_RESPONSE')
    submitted = {**intent, 'stage': 'SINGLE_JOB_SUBMITTED', 'intent_sha256': intent_sha,
                 'job_id': jid, 'submitted_at': time.time()}
    pin = private_create(directory / 'submission.json', submitted)
    return submitted, {'request': owner_request, 'source_sha': owner_source, 'receipt_sha256': pin}


def read_submission(ref, submission_context):
    submission_context = reference(submission_context)
    directory = AREA / ref['request']
    row, _ = document(directory / 'submission.json', 131072, expected=submission_context['receipt_sha256'])
    require(row.get('schema') == SUBMISSION_SCHEMA and row.get('stage') == 'SINGLE_JOB_SUBMITTED'
            and row.get('execution_revision') == ref and row.get('request') == submission_context['request']
            and row.get('source_sha') == submission_context['source_sha']
            and row.get('fixture_sha256') == digest(encoded(FIXTURE)) and row.get('generation_retry_authorized') is False
            and isinstance(row.get('job_id'), str) and JOB.fullmatch(row['job_id'])
            and isinstance(row.get('intent_sha256'), str) and SHA.fullmatch(row['intent_sha256']), 'SEALED_SUBMISSION')
    intent, _ = document(directory / 'intent.json', 131072, expected=row.get('intent_sha256'))
    expected = dict(row)
    for key in ('intent_sha256', 'job_id', 'submitted_at'):
        expected.pop(key)
    expected['stage'] = 'PREPARED_SINGLE_POST'
    require(intent == expected, 'INTENT_BINDING')
    return row


def task_projection(task):
    if task is None:
        return {'present': False}
    require(isinstance(task, dict) and task.get('status') in TASK_STATES, 'TASK_STATE')
    result = task.get('result') if isinstance(task.get('result'), dict) else {}
    reason = result.get('state')
    return {'present': True, 'state': task['status'], 'retries': task.get('retries') if integer(task.get('retries')) else None,
            'result_state': reason if isinstance(reason, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,120}', reason) else None,
            'claim_present': bool(task.get('owner_claim'))}


def queue_rows(jid):
    row, _ = document(STATE / 'dispatcher/state.json', 16 * 1024 ** 2, changing=True)
    tasks = row.get('tasks'); require(isinstance(tasks, dict) and len(tasks) <= 20000, 'QUEUE_BOUND')
    return {key: tasks.get(prefix + jid) for key, prefix in (
        ('media', 'owner.media.'), ('parent', 'owner.plan.media.'), ('handback', 'owner.media.resume.'))}


def valid_claim(task, dispatcher_pid):
    claim = task.get('owner_claim') or {}
    require(set(claim) == {'worker', 'pid', 'nonce', 'at'} and type(claim['pid']) is int
            and claim['pid'] == dispatcher_pid and isinstance(claim['worker'], str)
            and re.fullmatch('nox-agent-0[1-6]', claim['worker']) and isinstance(claim['nonce'], str)
            and re.fullmatch('[a-f0-9]{24}', claim['nonce']) and isinstance(claim['at'], str)
            and 1 <= len(claim['at']) <= 64 and finite(task.get('owner_claim_epoch'))
            and task.get('claimed_by') == claim['worker'], 'NATIVE_CLAIM')
    return claim


def handback_record(ctx, submission, task, dispatcher_pid):
    jid = submission['job_id']; directory = STATE / 'media/training_handback' / jid
    if task is None or task.get('status') != 'done':
        return None
    require(task.get('id') == 'owner.media.resume.' + jid and task.get('handler') == 'owner_media_resume'
            and task.get('source') == 'owner_qwen_media_handoff' and task.get('class') == 'training'
            and task.get('locks') == ['gpu1'] and task.get('deps') == [] and task.get('params') == {'job_id': jid}, 'HANDBACK_TASK')
    claim = valid_claim(task, dispatcher_pid)
    expected_path = directory / ('claim-' + claim['nonce'] + '.json')
    evidence = task.get('result')
    require(isinstance(evidence, dict) and evidence.get('receipt_path') == str(expected_path)
            and evidence.get('source_sha256') == PINS['owner_qwen_media_handoff.py']
            and isinstance(evidence.get('receipt_sha256'), str) and SHA.fullmatch(evidence['receipt_sha256']), 'HANDBACK_RESULT')
    receipt, _ = document(expected_path, 131072, expected=evidence['receipt_sha256'])
    request, _ = document(directory / 'request.json', 131072, changing=True)
    yielded, _ = document(STATE / 'media/training_yield.json', 131072, changing=True)
    require(request.get('schema') == receipt.get('schema') == 'NOX_QWEN_MEDIA_HANDBACK_V1'
            and request.get('stage') == 'RESUMED' and request.get('start_command_issued') is True
            and request.get('job_id') == receipt.get('job_id') == yielded.get('job_id') == jid
            and request.get('initial_admission') == receipt.get('initial_admission') == ctx['context']
            and request.get('source_sha256') == receipt.get('source_sha256') == PINS['owner_qwen_media_handoff.py']
            and request.get('config_sha256') == submission['before']['handoff_config_canonical_sha256'], 'HANDBACK_BINDING')
    require(receipt.get('state') == evidence.get('state') == 'ADMITTED_EXISTING_TRAINER_RESUMED'
            and receipt.get('verified') is evidence.get('verified') is True
            and receipt.get('scope') == evidence.get('scope') == HANDOFF_SCOPE
            and receipt.get('blockers') == evidence.get('blockers') == HANDOFF_BLOCKERS
            and receipt.get('task_id') == task['id'] and receipt.get('claim') == claim
            and receipt.get('claim_epoch') == task['owner_claim_epoch']
            and receipt.get('optimizer_progress_since_resume_verified') is False
            and receipt.get('weights_promoted') is False, 'HANDBACK_CLAIM_RECEIPT')
    yield_binding = {key: yielded[key] for key in ('job_id', 'requested_at', 'pause_token', 'wrapper_sha256',
                                                 'trainer_before', 'qwen_student', 'qwen_admission_sha256')}
    old = submission['before']['trainer']; qwen = yielded.get('qwen_student') or {}
    require(yielded.get('active') is False and yielded.get('resume') is False
            and yielded.get('resume_state') == 'ADMITTED_EXISTING_TRAINER_RESUMED'
            and yielded.get('handback_source_sha256') == PINS['owner_qwen_media_handoff.py']
            and yielded.get('pause_token') == 'NOX_MEDIA_CHECKPOINT_YIELD ' + jid + '\n'
            and yielded.get('wrapper_sha256') == ctx['execution']['wrapper_sha256']
            and yielded.get('qwen_admission_sha256') == ctx['execution']['admission_sha256']
            and qwen.get('pid') == old['pid'] and qwen.get('starttime') == old['start_ticks']
            and yielded.get('trainer_before', {}).get('pid') == submission['before']['service']['pid']
            and receipt.get('yield_sha256') == request.get('yield_sha256') == digest(encoded(yield_binding)), 'YIELD_CHAIN')
    process = receipt.get('process') or {}
    require(process == request.get('process') and integer(process.get('pid')) and process['pid'] != old['pid']
            and integer(process.get('starttime')) and process['starttime'] > old['start_ticks']
            and process.get('cuda') == '1' and process.get('service') == 'nox-train-volta-t866u'
            and receipt.get('baseline_step') == request.get('baseline_step')
            and receipt.get('baseline_receipt_sha256') == request.get('baseline_receipt_sha256')
            and request.get('boot_id') == old['boot_id']
            and receipt.get('lineage_sha256') == ctx['lineage_sha256'], 'RESUMED_PROCESS_CHAIN')
    for name, expected in {'TRAIN_PAUSE_REQUEST.flag': yielded['pause_token'].encode(),
            'TRAIN_HOLD.flag': ('OWNER_QWEN_WINDOW_FAILED request=' + ctx['context']['request'] + ' goal=1000\n').encode()}.items():
        require(read(directory / ('released-' + name), 4096) == expected, 'OWNED_FLAG_ARCHIVE')
    return {'receipt': receipt, 'request': request, 'yielded': yielded, 'receipt_sha256': evidence['receipt_sha256']}


def paused_checkpoint(loaded, ctx, submission, handback, budget, deadline):
    item = handback['yielded'].get('checkpoint') or {}
    named = Path(item.get('checkpoint', ''))
    require(named.parent == ctx['output'] and ctx['observer'].NAME.fullmatch(named.name)
            and item.get('receipt_sha256') == handback['receipt']['baseline_receipt_sha256'], 'PAUSE_CHECKPOINT_REFERENCE')
    proof, manifest, saved, obs = checkpoint(loaded, ctx,
        {'directory': named.name, 'manifest_sha256': item.get('manifest_sha256')}, budget, deadline)
    terminal = loaded['owner_training_status.py'].terminal(obs, ctx['contract'], ctx['lineage'], manifest, saved, deadline)
    raw_terminal, _ = document(ctx['output'] / 'owner_last_result.json', expected=item['receipt_sha256'])
    old = submission['before']['trainer']; pid = raw_terminal.get('process_identity') or {}
    require(terminal.get('current_execution_terminal_verified') is True and terminal.get('reload_verified') is True
            and terminal.get('state') in {'EXISTING_TRAINER_HOLD_OR_PAUSE', 'HOLD_TRAINING_STOP_REQUESTED'}
            and terminal['receipt_sha256'] == handback['receipt']['baseline_receipt_sha256']
            and saved['successful_total'] == handback['receipt']['baseline_step'] >= submission['before']['checkpoint']['successful_total']
            and pid.get('pid') == old['pid'] and pid.get('start_ticks') == old['start_ticks']
            and pid.get('boot_id') == old['boot_id'], 'CONTROLLED_PAUSE_PROOF')
    original = submission['before']['checkpoint']
    require(digest(encoded(saved['update_evidence'][:original['successful_total']])) == original['update_prefix_sha256'], 'BEFORE_PAUSE_PREFIX')
    return proof, manifest, saved, terminal


def resumed_update(ctx, before, handback, pause_anchor, proof, manifest, saved, process):
    pid = handback['receipt']['process']; witness = saved['last_evaluation_witness']
    require(process and process['pid'] == pid['pid'] and process['start_ticks'] == pid['starttime']
            and process['pid'] != before['trainer']['pid']
            and manifest.get('process_identity', {}).get('pid') == process['pid']
            and manifest['process_identity'].get('start_ticks') == process['start_ticks']
            and manifest['process_identity'].get('boot_id') == process['boot_id'] == before['trainer']['boot_id']
            and witness['process_identity'] == manifest['process_identity'], 'CURRENT_RESUMED_CHECKPOINT')
    restored = witness['restored_checkpoint']; checkpoint_at_pause = handback['yielded']['checkpoint']
    require(witness['kind'] in {'RESUME_RESTORE', 'PERIODIC', 'GOAL'}
            and restored['manifest_sha256'] == checkpoint_at_pause['manifest_sha256']
            and str(ctx['output'] / restored['directory']) == checkpoint_at_pause['checkpoint']
            and restored['student_state_sha256'] == pause_anchor['student_state_sha256']
            and restored['successful_total'] == pause_anchor['successful_total']
            and digest(encoded(saved['update_evidence'][:pause_anchor['successful_total']])) == pause_anchor['update_prefix_sha256'],
            'RESTORE_WITNESS_PREFIX')
    if witness['kind'] == 'RESUME_RESTORE':
        require(all(witness['before'][key] == pause_anchor[key] for key in (
            'successful_total', 'attempted_total', 'skipped_total', 'data_cursor', 'adapter_tensor_sha256')),
            'SAME_COUNTER_RESUME_EVALUATION')
    delta = saved['successful_total'] - pause_anchor['successful_total']
    require(delta > 0 and proof.get('positive_optimizer_updates_verified') is True
            and proof['adapter_tensor_sha256'] != pause_anchor['adapter_tensor_sha256'], 'NEW_OPTIMIZER_UPDATE_REQUIRED')
    return {'successful_updates_after_media_resume': delta, 'baseline_successful_total': pause_anchor['successful_total'],
            'current_successful_total': saved['successful_total'], 'process': process,
            'restored_checkpoint_manifest_sha256': restored['manifest_sha256'],
            'current_evaluation_witness_kind': witness['kind'], 'current_evaluation_witness_verified': True,
            'same_counter_resume_evaluation_witness_present': witness['kind'] == 'RESUME_RESTORE',
            'new_optimizer_checkpoint_verified': True}


def prior_pause(ref, submission_context, submission, previous_observation):
    """Explicit sealed evidence survives normal pruning; it is not a fresh read."""
    pin = reference(previous_observation)
    require(pin['request'] == submission_context['request'] and pin['source_sha'] == submission_context['source_sha'],
            'PRIOR_OBSERVATION_OWNER')
    value, _ = document(AREA / ref['request'] / 'result.json', 131072, expected=pin['receipt_sha256'])
    anchor = value.get('controlled_pause')
    require(value.get('schema') == SCHEMA and value.get('execution_revision') == ref
            and value.get('submission_context') == submission_context and value.get('job_id') == submission['job_id']
            and value.get('before') == submission['before'] and value.get('artifact_verified') is True
            and value.get('handback_claim_verified') is True and isinstance(anchor, dict)
            and isinstance(value.get('handback_receipt_sha256'), str) and SHA.fullmatch(value['handback_receipt_sha256'])
            and anchor.get('full_checkpoint_files_verified') is True and anchor.get('verified_files') == 10
            and integer(anchor.get('verified_bytes')) and 0 < anchor['verified_bytes'] <= GIB
            and all(isinstance(anchor.get(key), str) and SHA.fullmatch(anchor[key]) for key in (
                'manifest_sha256', 'student_state_sha256', 'adapter_tensor_sha256', 'update_prefix_sha256', 'terminal_receipt_sha256'))
            and all(integer(anchor.get(key)) for key in ('successful_total', 'attempted_total', 'skipped_total', 'data_cursor'))
            and anchor['attempted_total'] == anchor['successful_total'] + anchor['skipped_total'], 'PRIOR_FULL_PAUSE_PROOF')
    fields = ('directory', 'manifest_sha256', 'successful_total', 'attempted_total', 'skipped_total', 'data_cursor',
              'student_state_sha256', 'adapter_tensor_sha256', 'update_prefix_sha256', 'verified_files', 'verified_bytes',
              'full_checkpoint_files_verified', 'execution_evaluation_witness_verified', 'process_identity',
              'terminal_receipt_sha256')
    return {**{key: anchor[key] for key in fields if key in anchor},
            'payload_read_scope': 'HISTORICAL_FULL_SHA_IN_EXPLICIT_SEALED_OBSERVATION',
            'previous_observation': pin}, value['handback_receipt_sha256']


def artifact_projection(value):
    return {key: value[key] for key in ('kind', 'job_id', 'bytes', 'sha256', 'media_type', 'decode',
        'decode_verified', 'authenticated_http_verified', 'pixels_exported', 'scope')}


def observe(helper, loaded, ref, submission, submission_context, client, budget, deadline, result=None, previous_pause=None):
    jid = submission['job_id']; before = submission['before']; guard = loaded['owner_qwen_training_guard.py']
    runtime = loaded['owner_media_runtime.py']
    if result is None:
        result = {}
    posts = result.get('generation_post_attempts', 0)
    result.update({'schema': SCHEMA, 'state': 'MEDIA_GENERATION_PENDING',
        'execution_revision': ref, 'submission_context': submission_context, 'job_id': jid,
        'acceptance_verified': False, 'artifact_verified': False, 'handback_claim_verified': False,
        'optimizer_progress_after_resume_verified': False, 'generation_post_attempts': posts,
        'training_service_actions': 0, 'training_flags_written': False, 'controller_sources_modified': False,
        'private_prompts_exported': False, 'urls_or_credentials_exported': False, 'before': before})
    pause_anchor = previous_pause[0] if previous_pause is not None else None
    post_checkpoint = None
    while time.monotonic() < deadline - 90:
        ctx = context(loaded, ref)
        require(not guard.owner_stop(), 'OWNER_STOP')
        _, config_sha = handoff_config(ctx)
        require(config_sha == before['handoff_config_sha256'], 'HANDOFF_CONFIG_CHANGED')
        require(helper.dispatcher_identity() == before['dispatcher'], 'DISPATCHER_CHANGED')
        remote = client.json('/api/ui/media/jobs/' + jid)
        job, _ = document(runtime.job_path(jid), 262144, changing=True)
        require(job.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1' and job.get('id') == remote.get('id') == jid
                and job.get('request') == remote.get('request') == FIXTURE
                and job.get('state') in runtime.ACTIVE | runtime.TERMINAL, 'JOB_IDENTITY')
        tasks = queue_rows(jid)
        reason = job.get('reason')
        result.update(job_state=job['state'],
            job_reason=reason if isinstance(reason, str) and re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', reason) else None,
            tasks={key: task_projection(value) for key, value in tasks.items()})
        if job['state'] in {'BLOCKED', 'FAILED', 'CANCELLED'}:
            require(False, 'GENERATION_' + job['state'])
        if job['state'] == 'COMPLETED' and job.get('generation_verified') is True and job.get('gpu1_released') is True:
            claim = helper.claim_projection(tasks['media'], jid, before['dispatcher']['pid'], require_done=True)
            if claim is not None:
                valid_claim(tasks['media'], before['dispatcher']['pid'])
                if not result['artifact_verified']:
                    checked = helper.verify_artifact(runtime, runtime.configuration(), job, client)
                    result.update(artifact=artifact_projection(checked), artifact_verified=True,
                                  state='MEDIA_COMPLETE_RESUME_PENDING')
                require(tasks['handback'] is None or tasks['handback'].get('status') not in {'blocked', 'failed', 'cancelled'},
                        'HANDBACK_TERMINAL_FAILURE')
                handback = handback_record(ctx, submission, tasks['handback'], before['dispatcher']['pid'])
                if handback is not None:
                    result.update(handback_claim_verified=True, handback_receipt_sha256=handback['receipt_sha256'],
                                  resumed_process_recorded={key: handback['receipt']['process'][key] for key in ('pid', 'ppid', 'starttime')})
                    if pause_anchor is None:
                        paused = paused_checkpoint(loaded, ctx, submission, handback, budget, deadline)
                        pause_anchor = {**checkpoint_summary(*paused[:3]),
                            'terminal_receipt_sha256': paused[3]['receipt_sha256'],
                            'payload_read_scope': 'FULL_SHA_IN_THIS_OBSERVATION'}
                    else:
                        if previous_pause is not None:
                            require(handback['receipt_sha256'] == previous_pause[1], 'PRIOR_HANDOFF_CLAIM_CHANGED')
                    require(pause_anchor['terminal_receipt_sha256'] == handback['receipt']['baseline_receipt_sha256']
                            and pause_anchor['manifest_sha256'] == handback['yielded']['checkpoint']['manifest_sha256']
                            and pause_anchor['successful_total'] == handback['receipt']['baseline_step'], 'PAUSE_ANCHOR_CHANGED')
                    result['controlled_pause'] = pause_anchor
                    service, process = live(ctx); result['service'] = service; result['live_process'] = process
                    pointer, pointer_sha = latest(ctx)
                    manifest, _ = document(ctx['output'] / pointer['directory'] / 'checkpoint_manifest.json', 65536,
                                           expected=pointer['manifest_sha256'])
                    actual = handback['receipt']['process']
                    if (process and process['pid'] == actual['pid'] and process['start_ticks'] == actual['starttime']
                            and manifest.get('process_identity', {}).get('pid') == process['pid']
                            and manifest.get('process_identity', {}).get('start_ticks') == process['start_ticks']
                            and integer(manifest.get('successful_total')) and manifest['successful_total'] > pause_anchor['successful_total']):
                        if post_checkpoint is None or post_checkpoint[0] != pointer_sha:
                            proof, manifest, saved, _ = checkpoint(loaded, ctx, pointer, budget, deadline)
                            post_checkpoint = (pointer_sha, proof, manifest, saved)
                        else:
                            _, proof, manifest, saved = post_checkpoint
                        continuation = resumed_update(ctx, before, handback, pause_anchor, proof, manifest, saved, process)
                        reason = guard.resume_block_reason(ref)
                        result['guard_reason'] = reason
                        if reason in TRANSIENT_GUARD:
                            result['guard_wait_reason'] = reason
                        else:
                            if reason is not None:
                                raise RuntimeError(reason)
                            idle_training_controls(guard)
                            require(latest(ctx) == (pointer, pointer_sha) and live(ctx) == (service, process)
                                    and context(loaded, ref)['raw'] == ctx['raw'], 'FINAL_CONTEXT_CHANGED')
                            result.update(state='MEDIA_AND_RESUMED_OPTIMIZER_VERIFIED', acceptance_verified=True,
                                optimizer_progress_after_resume_verified=True, continuation=continuation,
                                checkpoint=checkpoint_summary(proof, manifest, saved))
                            break
                    elif service.get('state') in {'FATAL', 'BACKOFF', 'EXITED', 'STOPPED'}:
                        require(False, 'RESUMED_TRAINER_NOT_RUNNING')
        time.sleep(min(3.0, max(0.0, deadline - 90 - time.monotonic())))
    result['checkpoint_payload_bytes_verified'] = budget['bytes']
    result['observed_at'] = time.time()
    result['deadline_is_an_observation_bound_not_a_generation_cancel'] = True
    return result


def observe_existing(revision_reference, submission_context, *, previous_observation=None, timeout=360):
    """Read the same explicit job. This function contains no submission path."""
    require(type(timeout) in (int, float) and 120 <= timeout <= 420, 'TIMEOUT_BOUND')
    ref = reference(revision_reference); row = read_submission(ref, submission_context)
    previous = prior_pause(ref, reference(submission_context), row, previous_observation) if previous_observation is not None else None
    helper, loaded = dependencies(); context(loaded, ref)
    client = helper.OwnerClient.authenticate(); result = {}
    try:
        observe(helper, loaded, ref, row, reference(submission_context), client, {'bytes': 0},
                time.monotonic() + timeout, result, previous)
    except Exception as exc:
        result.update(state='HOLD', reason=safe(exc), acceptance_verified=False,
                      optimizer_progress_after_resume_verified=False)
    finally:
        try:
            client.close()
        except Exception as exc:
            result['session_close_reason'] = safe(exc)
    return result


def main(revision_reference=None):
    started = time.monotonic(); client = None; directory = None
    result = {'schema': SCHEMA, 'state': 'HOLD', 'acceptance_verified': False,
              'artifact_verified': False, 'optimizer_progress_after_resume_verified': False,
              'generation_post_attempts': 0, 'training_service_actions': 0, 'training_flags_written': False}
    try:
        # Caller supplies the sealed current revision explicitly. There is no
        # latest-receipt search and no historical-window fallback.
        ref = reference(revision_reference)
        request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
        source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
        require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_ACTION_IDENTITY')
        helper, loaded = dependencies(); deadline = started + 420
        _, before, budget = preconditions(helper, loaded, ref, deadline - 90)
        client = helper.OwnerClient.authenticate()
        # Repeat fresh current gates after credential acquisition, before any
        # durable submission intent or HTTP mutation.
        ctx = context(loaded, ref)
        require(live(ctx)[1] == before['trainer'], 'POST_ADMISSION_CHANGED')
        guard_gate(loaded['owner_qwen_training_guard.py'], ref)
        idle_training_controls(loaded['owner_qwen_training_guard.py'])
        directory = prepare_directory(ref)
        result['execution_revision'] = ref
        submitted, submission_context = submit_once(client, directory, ref, request, source, before, result)
        observe(helper, loaded, ref, submitted, submission_context, client, budget, deadline, result)
    except Exception as exc:
        result.update(state='HOLD', reason=safe(exc), acceptance_verified=False,
                      optimizer_progress_after_resume_verified=False)
        if result['generation_post_attempts'] and 'submission_context' not in result:
            result['submission_outcome'] = 'UNKNOWN_DO_NOT_REPOST'
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                result['session_close_reason'] = safe(exc)
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if directory is not None:
            try:
                pin = private_create(directory / 'result.json', result)
                result['result_sha256'] = pin
                if 'submission_context' in result:
                    result['observation_context'] = {key: result['submission_context'][key] for key in ('request', 'source_sha')}
                    result['observation_context']['receipt_sha256'] = pin
            except Exception as exc:
                result.update(state='HOLD', reason=safe(exc), acceptance_verified=False,
                              optimizer_progress_after_resume_verified=False)
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_revision_media_acceptance', 'data': result},
              sort_keys=True, allow_nan=False), flush=True)
    if result['acceptance_verified']:
        print('NOX_MAINT_REPAIR_COMPLETE', flush=True)
        return 0
    if result['state'] in PENDING_STATES:
        print('NOX_MAINT_REPAIR_PENDING', flush=True)
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
