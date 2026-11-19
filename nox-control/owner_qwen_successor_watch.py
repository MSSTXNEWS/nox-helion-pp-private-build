#!/usr/bin/env python3
"""Finite, single-claim activation watcher for the explicit Qwen successor.

This process is armed before the parent starts the one admitted trainer. It has
no service-start path. After the parent seals a pending result it delegates one
same-process finalization to the pinned native issuer. Owner STOP, source drift,
expiry and failure leave service state and existing flags untouched.
"""
from __future__ import annotations

import argparse
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

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
SELF = 'owner_qwen_successor_watch.py'
SHARED = 'owner_qwen_execution_revision.py'
ISSUER = 'owner_qwen_revision_install.py'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
READY_SCHEMA = 'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1'
CLAIM_SCHEMA = 'NOX_QWEN_SUCCESSOR_WATCHER_CLAIM_V1'
START_SCHEMA = 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1'
RESULT_SCHEMA = 'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1'
PARENT_PROGRESS_STATES = frozenset(('REVISION_INSTALLED_BOOTSTRAP_REQUIRED', 'SINGLE_TRAINER_START_INTENT',
    'SAME_COUNTER_EVALUATION_PENDING', 'REAL_EVALUATION_SAME_COUNTER_CHECKPOINT_VERIFIED'))
STOP_REQUESTED = False


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_QWEN_SUCCESSOR_WATCH_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def identity(info):
    return tuple(getattr(info, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def source(path, expected=None):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and not before.st_mode & 0o022 and 0 < before.st_size <= 131072, 'SOURCE_SCOPE')
        raw = f.read(131073)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(f.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'SOURCE_RACE')
    require(expected is None or digest(raw) == expected, 'SOURCE_SHA')
    return raw


def load(name, raw):
    value = types.ModuleType('_nox_successor_watch_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name)
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def private_directory(path):
    info = plain(path).stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')


def create(shared, path, value):
    """Create this watcher's own immutable receipt; never replace another file."""
    private_directory(path.parent)
    raw = encode(value)
    require(len(raw) <= 16384, 'RECEIPT_BOUND')
    fd = os.open(plain(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(raw); f.flush(); os.fsync(f.fileno())
    dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    require(shared.read(path, 16384, private=True) == raw, 'RECEIPT_READBACK')
    return digest(raw)


def process_identity():
    text = Path('/proc/self/stat').read_text()
    fields = text[text.rfind(')') + 2:].split()
    return {'pid': os.getpid(), 'start_ticks': int(fields[19]),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def stopped(shared):
    return STOP_REQUESTED or shared.stop_active()


def context_unchanged(shared, ctx):
    require(not stopped(shared), 'OWNER_STOP')
    shared.read(shared.CONFIG, 32768, expected=ctx['config_sha256'], private=True)
    shared.read(shared.ADMISSION, 64000, expected=ctx['execution']['admission_sha256'], private=True)
    shared.read(shared.WRAPPER, expected=ctx['execution']['wrapper_sha256'])


def start_receipt(shared, ctx, ready_sha):
    area = ctx['execution']['directory']
    # O_EXCL creation may be visible just before the parent's one small write.
    # Only incomplete JSON/file-change reads get this short retry; identity and
    # semantic mismatches are terminal and never authorize a start or activation.
    end = time.monotonic() + 2
    while True:
        try:
            value, raw = shared.document(area / 'start_receipt.json', 16384, private=True)
            break
        except json.JSONDecodeError:
            require(time.monotonic() < end, 'START_PARTIAL_JSON')
        except shared.Hold as exc:
            if str(exc) != 'HOLD_QWEN_REVISION_FILE_CHANGED':
                raise
            require(time.monotonic() < end, 'START_FILE_UNSTABLE')
        require(not stopped(shared), 'OWNER_STOP')
        time.sleep(0.05)
    require(value.get('schema') == START_SCHEMA
            and value.get('execution_revision') == ctx['execution']['reference']
            and value.get('start_command_issued') is True
            and type(value.get('start_command_returncode')) is int and value['start_command_returncode'] == 0
            and value.get('watcher_ready_sha256') == ready_sha, 'START_RECEIPT')
    trainer = value.get('trainer')
    require(isinstance(trainer, dict) and shared.process_identity_valid(trainer.get('process_identity')), 'START_PROCESS')
    service = trainer.get('service')
    require(isinstance(service, dict) and service.get('state') == 'RUNNING'
            and type(service.get('pid')) is int and service['pid'] > 1, 'START_SERVICE')
    started = value.get('started_at', value.get('sampled_at'))
    require(shared.finite(started) and ctx['execution']['descriptor']['created_at'] <= started <= time.time() + 2,
            'START_TIME')
    return value, digest(raw)


def pending_parent(shared, ctx, start_sha=None):
    path = ctx['execution']['directory'] / 'operation_result.json'
    if not path.exists() and not path.is_symlink():
        return False
    end = time.monotonic() + 2
    while True:
        try:
            value, _ = shared.document(path, 131072, private=True)
            break
        except shared.Hold as exc:
            if str(exc) != 'HOLD_QWEN_REVISION_FILE_CHANGED':
                raise
            require(time.monotonic() < end and not stopped(shared), 'PARENT_FILE_UNSTABLE')
            time.sleep(0.05)
    require(value.get('execution_revision') == ctx['execution']['reference'], 'PARENT_REFERENCE')
    if value.get('state') in PARENT_PROGRESS_STATES and value.get('finished_at') is None:
        require(value.get('optimizer_permission_issued') is False, 'PARENT_PROGRESS_PERMISSION')
        return False
    if value.get('state') == 'BOOTSTRAP_LOADING_PENDING':
        require(shared.sha(start_sha) and value.get('start_receipt_sha256') == start_sha
                and value.get('optimizer_permission_issued') is False, 'PARENT_START_BINDING')
        if value.get('finished_at') is None:
            return False
        require(shared.finite(value['finished_at']), 'PARENT_FINISH_TIME')
        return True
    # A parent may already be completing activation; the next iteration reads
    # the separately verified activation. A terminal failed parent never retries.
    require(value.get('optimizer_permission_issued') is True, 'PARENT_TERMINAL')
    return False


def safe_finalizer_result(value):
    require(isinstance(value, dict), 'FINALIZER_RESULT')
    state = value.get('state')
    require(isinstance(state, str) and re.fullmatch('[A-Z0-9_]{1,160}', state), 'FINALIZER_STATE')
    out = {'state': state}
    for name in ('active', 'optimizer_permission_issued', 'ordinary_guard_verified', 'read_only'):
        if name in value:
            require(type(value[name]) is bool or name in ('active', 'optimizer_permission_issued')
                    and value[name] is None, 'FINALIZER_BOOLEAN')
            out[name] = value[name]
    return out


def monitor(shared, ctx, ready_sha, *, monotonic=time.monotonic, sleep=time.sleep):
    ref = ctx['execution']['reference']
    ttl = ctx['execution']['descriptor']['bootstrap']['expires_at'] - time.time()
    require(math.isfinite(ttl) and 0 < ttl <= 3600, 'TTL')
    end = monotonic() + ttl
    while True:
        context_unchanged(shared, ctx)
        active = shared.activation_status(ctx)
        if active.get('active') is True:
            shared.current_context(ref)
            return {'state': 'ACTIVATION_OBSERVED_READ_ONLY', 'active': True, 'read_only': True,
                    'optimizer_permission_issued': False, 'activation_sha256': active['permit_sha256']}
        require(active.get('bootstrap_pending') is True and monotonic() < end, 'EXPIRED')
        start_path = ctx['execution']['directory'] / 'start_receipt.json'
        if start_path.exists() or start_path.is_symlink():
            start, start_sha = start_receipt(shared, ctx, ready_sha)
            if pending_parent(shared, ctx, start_sha):
                ctx = shared.current_context(ref)
                context_unchanged(shared, ctx)
                if shared.activation_status(ctx).get('active') is True:
                    continue
                issuer = load(ISSUER, source(SCRIPTS / ISSUER,
                    ctx['execution']['descriptor']['activation_issuer_sha256']))
                require(callable(getattr(issuer, 'finalize_same_process', None)), 'ISSUER_API')
                remaining = min(end - monotonic(), ctx['execution']['descriptor']['bootstrap']['expires_at'] - time.time())
                require(0 < remaining <= 3600 and not stopped(shared), 'FINALIZE_BOUND')
                value = issuer.finalize_same_process(ref, start_sha, wait_seconds=remaining,
                                                      stop_check=lambda: stopped(shared))
                result = safe_finalizer_result(value)
                result['start_receipt_sha256'] = start_sha
                result['finalizer_called_once'] = True
                return result
        else:
            pending_parent(shared, ctx)
        sleep(min(0.5, max(0.0, end - monotonic())))


def sanitized_error(exc):
    if isinstance(exc, Deadline):
        return 'HOLD_QWEN_SUCCESSOR_WATCH_DEADLINE'
    code = str(exc)
    return code if re.fullmatch('HOLD_[A-Z0-9_]{1,150}', code) else 'HOLD_QWEN_SUCCESSOR_WATCH_FAILURE'


def run(reference):
    shared = load(SHARED, source(SCRIPTS / SHARED, SHARED_SHA))
    ref = shared.validate_reference(reference)
    ctx = shared.current_context(ref)
    area = ctx['execution']['directory']; private_directory(area)
    desc = ctx['execution']['descriptor']
    watcher_sha = digest(source(SCRIPTS / SELF, desc['activation_watcher_sha256']))
    require(Path(__file__) == SCRIPTS / SELF, 'NATIVE_SOURCE_PATH')
    source(SCRIPTS / ISSUER, desc['activation_issuer_sha256'])
    who = process_identity()
    require(shared.process_identity_valid(who) and not stopped(shared), 'ARM_IDENTITY_OR_STOP')
    now = time.time()
    require(now < desc['bootstrap']['expires_at'] <= now + 3600, 'ARM_TTL')
    claim = {'schema': CLAIM_SCHEMA, 'execution_revision': ref, 'process_identity': who,
             'watcher_source_sha256': watcher_sha, 'claimed_at': now, 'start_capability': False}
    create(shared, area / 'watcher_claim.json', claim)
    result = None
    try:
        ready = {'schema': READY_SCHEMA, 'execution_revision': ref, 'process_identity': who,
                 'watcher_source_sha256': watcher_sha, 'verifier_sha256': SHARED_SHA,
                 'issuer_source_sha256': desc['activation_issuer_sha256'], 'armed_at': time.time(),
                 'start_capability': False}
        ready_sha = create(shared, area / 'watcher_ready.json', ready)
        result = monitor(shared, ctx, ready_sha)
    except BaseException as exc:
        # A failure can arrive after the issuer commits its permit. This path
        # does not reread it and therefore cannot claim either active or inactive.
        result = {'state': sanitized_error(exc), 'active': None, 'optimizer_permission_issued': None,
                  'activation_observation': 'NOT_RECHECKED_AFTER_EXCEPTION',
                  'service_actions': 0, 'flags_changed_by_watcher': False}
    result = {'schema': RESULT_SCHEMA, 'execution_revision': ref, 'process_identity': who,
              'watcher_source_sha256': watcher_sha, 'finished_at': time.time(), **result}
    create(shared, area / 'watcher_result.json', result)
    return result


def stop_signal(*_):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def deadline_signal(*_):
    raise Deadline()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--receipt-sha256', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop_signal); signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGALRM, deadline_signal)
    signal.setitimer(signal.ITIMER_REAL, 3600)
    try:
        result = run({'request': args.request, 'source_sha': args.source_sha, 'receipt_sha256': args.receipt_sha256})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    # Parent routes stdout/stderr to private files, not public workflow output.
    print(json.dumps({'schema': RESULT_SCHEMA, 'state': result['state'],
                      'active': result.get('active')}, separators=(',', ':')), flush=True)
    return 0 if result.get('active') is True or result.get('optimizer_permission_issued') is True else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'schema': RESULT_SCHEMA, 'state': sanitized_error(exc)}, separators=(',', ':')), flush=True)
        raise SystemExit(2)
