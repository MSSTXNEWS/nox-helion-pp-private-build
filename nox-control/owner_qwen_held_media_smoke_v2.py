#!/usr/bin/env python3
"""One image through the existing queue after the explicit second rollback.

The sealed rollback is a prerequisite, not a request to perform a rollback.
Only an owned private journal and the normal authenticated media job are
written. No trainer, flag, service, source, GPU or engine control is invoked.
An uncertain POST is never repeated. observe_existing reads one sealed job.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
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
AREA = STATE / 'media/held_rollback_smoke'
ROLLBACK_AREA = STATE / 'owner_qwen_execution_retry_rollbacks'
FAILED_AREA = STATE / 'owner_qwen_execution_revisions/6912442714'
MAINTENANCE = STATE / 'owner_maintenance.lock'
SCHEMA = 'NOX_QWEN_HELD_MEDIA_SMOKE_V1'
SUBMISSION_SCHEMA = 'NOX_QWEN_HELD_MEDIA_SUBMISSION_V1'
ROLLBACK_SCHEMA = 'NOX_QWEN_RETRY_HELD_ROLLBACK_V1'
ACCEPTED = 'HELD_TRAINER_IMAGE_AND_OWNER_DELIVERY_VERIFIED'
MAX_SECONDS = 180
VERIFY_RESERVE = 90
MODEL = {'pid': 7637, 'starttime': '149189867', 'pgrp': 7059}
FAILED_REF = {'request': '6912442714', 'source_sha': '7e27ab2ce0673205701727f4d3ef3f4a59b3d096',
              'receipt_sha256': 'c7304317a76fe08869eec9b6127ffd51107d69698e8b0ea678ae7c0f8d1e2858'}
PINS = {
    'owner_media_acceptance_entry.py': '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60',
    'owner_qwen_revision_install.py': '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
}
FIXTURE = {'kind': 'image', 'prompt': 'A red ceramic cup on a pale blue table, soft studio light, simple composition, no lettering.',
           'negative_prompt': 'text, watermark', 'width': 256, 'height': 256, 'frames': 1, 'fps': 8, 'seed': 161125}
SHA = re.compile('[a-f0-9]{64}')
JOB = re.compile('[a-f0-9]{32}')
TASK_STATES = {'pending', 'wait', 'retry', 'running', 'done', 'blocked', 'failed', 'cancelled'}


class SmokeHold(RuntimeError):
    pass


class Deadline(SmokeHold):
    pass


def require(ok, code):
    if not ok:
        raise SmokeHold('HOLD_QWEN_HELD_MEDIA_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,140}', value) else 'HOLD_QWEN_HELD_MEDIA_' + type(exc).__name__.upper()


def reference(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and type(value['request']) is str and re.fullmatch('[0-9]{1,24}', value['request'])
            and type(value['source_sha']) is str and re.fullmatch('[a-f0-9]{40}', value['source_sha'])
            and type(value['receipt_sha256']) is str and SHA.fullmatch(value['receipt_sha256']), 'REFERENCE')
    return dict(value)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def read(path, maximum=262144, *, expected=None, private=False):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not stat.S_IMODE(before.st_mode) & 0o022 and 0 <= before.st_size <= maximum, 'FILE_SCOPE')
        require(not private or stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1, 'PRIVATE_FILE')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    require(expected is None or digest(raw) == expected, 'FILE_SHA')
    return raw


def unique(pairs):
    row = {}
    for key, value in pairs:
        require(key not in row, 'DUPLICATE_JSON'); row[key] = value
    return row


def document(path, maximum=262144, *, expected=None, private=False, changing=False):
    for attempt in range(3):
        try:
            raw = read(path, maximum, expected=expected, private=private)
            row = json.loads(raw, object_pairs_hook=unique,
                             parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
            require(isinstance(row, dict), 'JSON_OBJECT'); encode(row)
            return row, digest(raw)
        except SmokeHold as exc:
            if not changing or str(exc) != 'HOLD_QWEN_HELD_MEDIA_FILE_CHANGED' or attempt == 2:
                raise
            time.sleep(.02)


def sync_directory(path):
    fd = os.open(plain(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_create(path, row):
    path = plain(path); raw = encode(row) + b'\n'
    require(len(raw) <= 131072, 'RECEIPT_BOUND')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        created = identity(os.fstat(stream.fileno()))
    sync_directory(path.parent)
    require(read(path, 131072, private=True) == raw and identity(path.stat(follow_symlinks=False)) == created,
            'RECEIPT_READBACK')
    return digest(raw)


def prepare_directory(ref):
    plain(AREA); AREA.mkdir(mode=0o700, exist_ok=True)
    info = AREA.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'JOURNAL_PARENT')
    sync_directory(AREA.parent)
    directory = AREA / ref['request']
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        require(False, 'PRIOR_INTENT_REQUIRES_EXPLICIT_OBSERVATION')
    sync_directory(AREA)
    return directory


def module(raw, name, pin):
    require(0 < len(raw) <= 262144 and digest(raw) == pin, 'SOURCE_PIN')
    value = types.ModuleType('_nox_held_smoke_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name)
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def dependencies():
    # Definition-only loads; none of these historical entries' main functions
    # or their control/cleanup methods are called.
    loaded = {}
    for name, pin in PINS.items():
        encoded = BUNDLE.get(name, '')
        require(isinstance(encoded, str) and len(encoded) <= 350000, 'BUNDLE_BOUND')
        loaded[name] = module(base64.b64decode(encoded, validate=True), name, pin)
    helper = loaded['owner_media_acceptance_entry.py']; core = loaded['owner_qwen_revision_install.py']
    guard = module(read(SCRIPTS / core.GUARD), core.GUARD, core.OLD_SOURCES[core.GUARD])
    runtime = helper.load_runtime(read(SCRIPTS / 'owner_media_runtime.py'))
    return {'helper': helper, 'core': core, 'guard': guard, 'runtime': runtime,
            'native': loaded['owner_native_repair.py'], 'deploy': loaded['owner_download_status_entry.py']}


def maintenance_shared():
    """Existing SH lock blocks EX mutations and permits guard/media SH reads."""
    fd = os.open(plain(MAINTENANCE), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and not stat.S_IMODE(info.st_mode) & 0o022, 'MAINTENANCE_SCOPE')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            require(False, 'MAINTENANCE_EXCLUSIVE')
        require(identity(os.fstat(fd)) == identity(MAINTENANCE.stat(follow_symlinks=False)), 'MAINTENANCE_CHANGED')
        return fd
    except BaseException:
        os.close(fd); raise


def rollback_receipt(core, ref):
    row, pin = document(ROLLBACK_AREA / ref['request'] / 'result.json', 131072,
                        expected=ref['receipt_sha256'], private=True)
    cp = row.get('checkpoint') or {}; guard = row.get('ordinary_guard') or {}
    require(row.get('schema') == ROLLBACK_SCHEMA and row.get('state') == 'ORIGINAL_CHECKPOINT25_HELD_STATE_RESTORED'
            and row.get('request') == ref['request'] and row.get('source_sha') == ref['source_sha']
            and row.get('failed_execution_revision') == FAILED_REF and row.get('failed_attempt_preserved') is True
            and row.get('training_flags_present') is True and row.get('learning_rearm_performed') is False
            and row.get('initial_installer_reentry_not_executed') is True and row.get('trainer_start_calls') == 0
            and type(row.get('trainer_start_calls')) is int and row.get('optimizer_permission_issued') is False
            and row.get('checkpoints_modified') is False and row.get('main_chat_model_restarted') is False
            and row.get('active_chat') == MODEL and row.get('chat_health') == {'8080': 200, '8081': 200, '8082': 200},
            'ROLLBACK_ACCEPTANCE')
    require(cp.get('full_files_sha256_verified') is True and all(cp.get(k) == v for k, v in core.ANCHOR.items())
            and (row.get('checkpoint_inventory') or {}).get('no_new_revision_checkpoint_metadata_observed') is True
            and guard.get('state') == 'INHIBITED' and guard.get('reason') == 'EVALUATION_STALE'
            and guard.get('successful_updates') == 25 and guard.get('evaluated_at_update') == 10, 'ROLLBACK_CHECKPOINT_PROOF')
    return {'reference': ref, 'schema': ROLLBACK_SCHEMA, 'receipt_sha256': pin,
            'historical_full_checkpoint_sha256_verified': True, 'successful_updates': 25}


def held_sources(core):
    core.protected()
    for name, pin in core.OLD_SOURCES.items():
        read(SCRIPTS / name, expected=pin)
    for name, pin in core.CONFIG_PINS.items():
        read(ROOT / 'config' / name, expected=pin, private=True)
    read(STATE / 'owner_training_admission.json', expected=core.OLD_ADMISSION, private=True)
    read(SCRIPTS / 'run_train_volta_t866u.sh', expected=core.OLD_WRAPPER)
    for path in (SCRIPTS / core.SHARED, SCRIPTS / core.STUDENT, SCRIPTS / core.SELF,
                 ROOT / 'config/owner_qwen_execution_revision.json', FAILED_AREA / 'activation.json'):
        plain(path)
        require(not path.exists() and not path.is_symlink(), 'REVISION_OR_ACTIVATION_PRESENT')


def inactive_yield():
    path = STATE / 'media/training_yield.json'; plain(path)
    if not path.exists():
        return
    row, _ = document(path, changing=True)
    require(row.get('active') is False, 'ACTIVE_OR_UNKNOWN_YIELD')


def held_context(d):
    core, guard = d['core'], d['guard']; held_sources(core); core.exact_flags(); inactive_yield()
    config, config_sha = guard.checked_config(core.ORIGIN, core.OLD_SOURCES[core.GUARD])
    ctx = guard.context_evidence(config)
    window = guard.module('owner_qwen_window_entry.py'); helper = guard.module('owner_qwen_install_entry.py')
    ctx['argv'] = window.arguments(helper, ctx['profile'], core.ORIGIN['request'], core.OLD_ADMISSION, 1000, resume=True)
    return ctx, config, config_sha


def held_snapshot(d, ctx, config, config_sha, before=None):
    core, guard = d['core'], d['guard']; held_sources(core); core.exact_flags(); inactive_yield()
    cp = guard.checkpoint_metadata(ctx)
    require(cp['pointer_sha256'] == core.ANCHOR['pointer_sha256']
            and cp['manifest_sha256'] == core.ANCHOR['manifest_sha256']
            and cp['student_state_sha256'] == core.ANCHOR['student_state_sha256']
            and cp['recorded_files'] == core.ANCHOR['verified_files']
            and cp['observed_file_bytes'] == core.ANCHOR['verified_bytes'], 'CHECKPOINT25_CHANGED')
    row, guard_sha = document(guard.STATUS, 65536, private=True, changing=True)
    require(row.get('bindings') == guard.bindings(config, config_sha, ctx), 'GUARD_BINDING')
    core.migration_policy(guard, row, cp)
    require(finite(row.get('sampled_at')) and 0 <= time.time() - row['sampled_at'] <= 30, 'GUARD_SAMPLE_STALE')
    trainer = core.trainer(ctx)
    require(trainer == {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}, 'TRAINER_NOT_HELD')
    chat = d['deploy'].model_identity(d['native']); require(chat == MODEL, 'CHAT_IDENTITY')
    dispatcher = d['helper'].dispatcher_identity()
    require(before is None or dispatcher == before['dispatcher'], 'DISPATCHER_CHANGED')
    return {'checkpoint': cp, 'checkpoint_payloads_hashed_in_this_smoke': False,
            'accepted_six_sha256': core.ACCEPTANCE, 'lineage_sha256': core.ORIGIN_LINEAGE,
            'guard_state': 'INHIBITED', 'guard_reason': 'EVALUATION_STALE', 'guard_sha256': guard_sha,
            'guard_sampled_at': row['sampled_at'], 'trainer': trainer, 'flags': dict(core.FLAGS),
            'chat': chat, 'dispatcher': dispatcher, 'yield_active': False}


def no_other_jobs(runtime, own=None):
    directory = plain(STATE / 'media/jobs')
    with os.scandir(directory) as items:
        for count, item in enumerate(items, 1):
            require(count <= 450, 'JOB_INVENTORY')
            path = plain(Path(item.path))
            if re.fullmatch(r'[a-f0-9]{32}\.lock', item.name):
                # ca8.update_job retains this per-job empty lock. It is not a
                # job record. Skip it only after same-FD private/zero-byte
                # validation AND validation of its corresponding job below.
                read(path, 0, private=True)
                path = plain(path.with_suffix('.json'))
                require(path.exists(), 'JOB_LOCK_WITHOUT_RECORD')
            elif re.fullmatch(r'\.media-[A-Za-z0-9_-]{6,64}', item.name):
                # ca8.atomic has not yet published a stable record. Do not
                # admit a generation while an in-flight record is unknown.
                raise SmokeHold('WAIT_QWEN_HELD_MEDIA_ATOMIC_JOB_WRITE')
            else:
                require(item.is_file(follow_symlinks=False) and item.name.endswith('.json')
                        and JOB.fullmatch(item.name[:-5]), 'JOB_INVENTORY')
            row, _ = document(path, changing=True)
            require(row.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1' and row.get('id') == path.stem
                    and row.get('state') in runtime.ACTIVE | runtime.TERMINAL, 'JOB_INVENTORY_STATE')
            require(row['id'] == own or row['state'] not in runtime.ACTIVE, 'OTHER_OWNER_JOB')


def ready_to_submit(d):
    no_other_jobs(d['runtime'])
    config = d['runtime'].configuration(); engine = d['runtime'].engine_identity(config)
    queues = d['runtime'].queue_ids()
    require(queues == {'queue_running': [], 'queue_pending': []}, 'ENGINE_NOT_IDLE')
    return engine


def submit_once(client, directory, ref, request, source, before, result):
    intent = {'schema': SUBMISSION_SCHEMA, 'stage': 'PREPARED_SINGLE_POST', 'rollback_reference': ref,
              'request': request, 'source_sha': source, 'fixture_sha256': digest(encode(FIXTURE)),
              'created_at': time.time(), 'before': before, 'generation_retry_authorized': False}
    intent_sha = private_create(directory / 'intent.json', intent)
    result['generation_post_attempts'] = 1
    # No retry, including on timeout, invalid response, or failed journal write.
    row = client.json('/api/ui/media/jobs', method='POST', data=dict(FIXTURE), status=202)
    require(isinstance(row, dict) and isinstance(row.get('id'), str) and JOB.fullmatch(row['id'])
            and row.get('request') == FIXTURE and row.get('state') == 'QUEUED', 'POST_RESPONSE')
    submitted = {**intent, 'stage': 'SINGLE_JOB_SUBMITTED', 'intent_sha256': intent_sha,
                 'job_id': row['id'], 'submitted_at': time.time()}
    pin = private_create(directory / 'submission.json', submitted)
    return submitted, {'request': request, 'source_sha': source, 'receipt_sha256': pin}


def read_submission(ref, sealed):
    sealed = reference(sealed)
    row, _ = document(AREA / ref['request'] / 'submission.json', 131072, expected=sealed['receipt_sha256'], private=True)
    require(row.get('schema') == SUBMISSION_SCHEMA and row.get('stage') == 'SINGLE_JOB_SUBMITTED'
            and row.get('rollback_reference') == ref and row.get('request') == sealed['request']
            and row.get('source_sha') == sealed['source_sha'] and row.get('fixture_sha256') == digest(encode(FIXTURE))
            and row.get('generation_retry_authorized') is False and isinstance(row.get('job_id'), str)
            and JOB.fullmatch(row['job_id']) and isinstance(row.get('intent_sha256'), str)
            and SHA.fullmatch(row['intent_sha256']), 'SEALED_SUBMISSION')
    intent, _ = document(AREA / ref['request'] / 'intent.json', 131072, expected=row['intent_sha256'], private=True)
    expected = {k: v for k, v in row.items() if k not in ('intent_sha256', 'job_id', 'submitted_at')}
    expected['stage'] = 'PREPARED_SINGLE_POST'; require(intent == expected, 'INTENT_BINDING')
    return row


def queue_task(jid):
    row, _ = document(STATE / 'dispatcher/state.json', 16 * 1024 ** 2, changing=True)
    tasks = row.get('tasks'); require(isinstance(tasks, dict) and len(tasks) <= 20000, 'QUEUE_BOUND')
    task = tasks.get('owner.media.' + jid)
    require(task is None or isinstance(task, dict) and task.get('status') in TASK_STATES, 'TASK_STATE')
    return task


def artifact_projection(row):
    return {key: row[key] for key in ('kind', 'job_id', 'bytes', 'sha256', 'media_type', 'decode',
                                    'decode_verified', 'authenticated_http_verified', 'pixels_exported', 'scope')}


def observe(d, ctx, config, config_sha, submitted, client, deadline, result):
    jid = submitted['job_id']; before = submitted['before']; runtime = d['runtime']; helper = d['helper']
    result.update(state='MEDIA_GENERATION_PENDING', job_id=jid)
    while time.monotonic() < deadline - VERIFY_RESERVE:
        held_snapshot(d, ctx, config, config_sha, before); no_other_jobs(runtime, jid)
        remote = client.json('/api/ui/media/jobs/' + jid)
        job, _ = document(runtime.job_path(jid), changing=True)
        require(job.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1' and job.get('id') == remote.get('id') == jid
                and job.get('request') == remote.get('request') == FIXTURE
                and job.get('state') in runtime.ACTIVE | runtime.TERMINAL, 'JOB_IDENTITY')
        result['job_state'] = job['state']; reason = job.get('reason')
        result['job_reason'] = reason if isinstance(reason, str) and re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', reason) else None
        task = queue_task(jid); result['task_state'] = task.get('status') if task else None
        require(job['state'] not in {'FAILED', 'BLOCKED', 'CANCELLED'}, 'GENERATION_' + job['state'])
        if job['state'] == 'COMPLETED' and job.get('generation_verified') is True and job.get('gpu1_released') is True:
            claim = helper.claim_projection(task, jid, before['dispatcher']['pid'], require_done=True)
            if claim is not None:
                require(job.get('training_resume') == 'TRAINING_PREVIOUSLY_HELD', 'TRAINER_RESUME_NOT_HELD')
                result['native_claim'] = claim
                checked = helper.verify_artifact(runtime, runtime.configuration(), job, client)
                result.update(artifact=artifact_projection(checked), artifact_verified=True)
                after = held_snapshot(d, ctx, config, config_sha, before)
                no_other_jobs(runtime, jid)
                result.update(state=ACCEPTED, acceptance_verified=True, after=after,
                              native_generation_claim_verified=True, training_still_held=True,
                              main_chat_identity_preserved=True)
                return
        time.sleep(min(2.0, max(0.0, deadline - VERIFY_RESERVE - time.monotonic())))


def execute(rollback_reference, submission_context=None, *, timeout=MAX_SECONDS):
    require(type(timeout) in (int, float) and 100 <= timeout <= MAX_SECONDS, 'TIMEOUT_SCOPE')
    started = time.monotonic(); deadline = started + timeout; client = None; lease = None; directory = None
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    result = {'schema': SCHEMA, 'state': 'HOLD', 'request': request, 'source_sha': source,
              'acceptance_verified': False, 'artifact_verified': False, 'generation_post_attempts': 0,
              'trainer_start_calls': 0, 'training_flags_written': False, 'sources_modified': False,
              'direct_engine_control_calls': 0, 'private_content_exported': False,
              'deadline_seconds': timeout, 'deadline_does_not_cancel_native_job': True}
    old_handlers = {}; old_timer = signal.getitimer(signal.ITIMER_REAL)
    def interrupted(signum, _frame):
        if signum == signal.SIGALRM:
            raise Deadline('WAIT_QWEN_HELD_MEDIA_OBSERVATION_BUDGET')
        raise SmokeHold('HOLD_QWEN_HELD_MEDIA_INTERRUPTED')
    try:
        require(old_timer[0] == 0 and old_timer[1] == 0, 'PARENT_TIMER_PRESENT')
        for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT):
            old_handlers[signum] = signal.signal(signum, interrupted)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        ref = reference(rollback_reference); result['rollback_reference'] = ref
        require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_ACTION')
        d = dependencies(); lease = maintenance_shared()
        result['rollback_proof'] = rollback_receipt(d['core'], ref)
        ctx, config, config_sha = held_context(d)
        before = held_snapshot(d, ctx, config, config_sha)
        if submission_context is None:
            result['engine_before'] = ready_to_submit(d)
            client = d['helper'].OwnerClient.authenticate()
            # Authentication may take time. Repeat every pre-submit condition.
            before = held_snapshot(d, ctx, config, config_sha, before); ready_to_submit(d)
            require(time.monotonic() < deadline - VERIFY_RESERVE - 8, 'SUBMISSION_BUDGET')
            directory = prepare_directory(ref)
            submitted, sealed = submit_once(client, directory, ref, request, source, before, result)
        else:
            sealed = reference(submission_context); submitted = read_submission(ref, sealed)
            directory = AREA / ref['request']
            require(before['dispatcher'] == submitted['before']['dispatcher'], 'SUBMISSION_DISPATCHER_CHANGED')
            no_other_jobs(d['runtime'], submitted['job_id'])
            client = d['helper'].OwnerClient.authenticate()
        result['submission_context'] = sealed; result['before'] = submitted['before']
        observe(d, ctx, config, config_sha, submitted, client, deadline, result)
    except Exception as exc:
        reason = safe(exc)
        if result['generation_post_attempts'] and 'submission_context' not in result:
            result.update(state='MEDIA_SUBMISSION_UNRESOLVED', reason=reason)
        elif isinstance(exc, Deadline):
            result.update(state='MEDIA_GENERATION_PENDING', reason=reason)
        else:
            result.update(state='HOLD', reason=reason)
        result['acceptance_verified'] = False
    finally:
        if client is not None:
            if time.monotonic() + 9 < deadline:
                try:
                    client.close()
                    result['owner_session_closed'] = True
                except Exception as exc:
                    result['owner_session_closed'] = False; result['session_close_reason'] = safe(exc)
            else:
                client.cookie = None
                result['owner_session_closed'] = False
                result['session_close_reason'] = 'WAIT_QWEN_HELD_MEDIA_CLOSE_BUDGET'
        if lease is not None:
            os.close(lease)
        result['finished_at'] = time.time(); result['duration_seconds'] = round(time.monotonic() - started, 3)
        try:
            if directory is not None:
                name = 'result.json' if submission_context is None else 'observation-' + request + '.json'
                pin = private_create(directory / name, result)
                result['result_context'] = {'request': request, 'source_sha': source, 'receipt_sha256': pin}
                result['result_record'] = name
        except Exception as exc:
            result.update(state='HOLD', reason=safe(exc), acceptance_verified=False, result_record_verified=False)
        finally:
            if old_handlers:
                signal.setitimer(signal.ITIMER_REAL, 0)
                for signum, handler in old_handlers.items():
                    signal.signal(signum, handler)
    return result


def observe_existing(rollback_reference, submission_context, *, timeout=MAX_SECONDS):
    """Read one exact sealed job; the submission branch is unreachable."""
    reference(submission_context)
    return execute(rollback_reference, submission_context, timeout=timeout)


def main(rollback_reference=None):
    result = execute(rollback_reference)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_held_media_smoke', 'data': result},
                                         sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    accepted = result.get('state') == ACCEPTED and result.get('acceptance_verified') is True
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if accepted else 'false'), flush=True)
    return 0 if accepted else 2


if __name__ == '__main__':
    sys.exit(main())
