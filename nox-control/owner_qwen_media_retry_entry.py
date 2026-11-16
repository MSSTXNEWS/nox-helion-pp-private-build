#!/usr/bin/env python3
"""Resubmit exactly two verified blocked jobs through the normal media inbox.

Old jobs, plans, claims and results are retained. A durable link precedes each
new job publication, so an interrupted action cannot blindly create another.
No prompt, owner identifier, raw task or credential is printed.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
JOBS = {
    '5eb826584f059b8dd8eeffe8b4f6cb3a': '1b455a5ea299300e3fb26526229a526a81e9e535c45f6f52ed5031a86ae33b28',
    '72c5ab9b719d0b9a5a191f863db42b1f': 'ea2ef2ad16a4856be34e0fad21305914c49e536da95f7b03da1f950410cc5860',
}
HANDOFF = '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc'
RUNTIME = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
DISPATCHER = 'eeacabfc161d28001396a901c2680f58b71a7fcedd6c46893fc6744144bb6e17'
INSTALL_RECEIPT = '18498798d36bb4cea7ac3f8c274c9cd443f82986eb7c1821d8e0844a9081be35'
CONFIG = '6ecf2239cb300a44c1601063bafe2de855c1c083f44852bb4421910ba304c2f2'
LINK = STATE / 'media/retries/qwen_completed6_6907909296.json'
SCHEMA = 'NOX_QWEN_MEDIA_RETRY_V1'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_MEDIA_RETRY_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def sync_parent(path):
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read(path, limit=2 * 1024 ** 2):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'FILE_BOUND')
        data = stream.read(limit + 1)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'READ_CHANGED')
        return data


def load(name, pin):
    path = ROOT / 'scripts' / name
    raw = read(path)
    require(sha(raw) == pin, 'SOURCE_PIN')
    value = types.ModuleType('_nox_qwen_retry_' + name[:-3]); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def history():
    tasks = json.loads(read(STATE / 'dispatcher/state.json', 16 * 1024 ** 2))['tasks']
    result = {}
    for old_id in JOBS:
        for task_id in ('owner.media.' + old_id, 'owner.plan.media.' + old_id):
            row = tasks.get(task_id)
            require(isinstance(row, dict) and row.get('status') == 'blocked'
                    and isinstance(row.get('owner_claim'), dict), 'OLD_TASK_STATE')
            result[task_id] = sha(encoded(row))
    return result


def submit_linked(runtime, previous, link, save):
    """Observe the normal create_job write; do not alter its request or inbox."""
    old_atomic = runtime.atomic
    expected = runtime.validate_request(previous['request'])
    require(expected == previous['request'], 'NORMALIZED_REQUEST')
    require(isinstance(previous.get('owner'), str) and previous['owner'], 'OWNER_IDENTITY')
    item = {'old_job_id': previous['id'], 'state': 'SUBMITTING', 'new_job_id': None,
            'kind': expected['kind'], 'request_sha256': sha(encoded(expected))}
    link['replacements'].append(item); save()

    def observed_atomic(path, value):
        path = Path(path)
        if path.parent == STATE / 'media/jobs':
            require(item['new_job_id'] is None and isinstance(value, dict)
                    and re.fullmatch('[a-f0-9]{32}', str(value.get('id')))
                    and path == runtime.job_path(value['id']) and not path.exists()
                    and value.get('request') == expected and value.get('owner') == previous['owner']
                    and value.get('state') == 'QUEUED', 'NEW_JOB_PUBLICATION')
            item.update(new_job_id=value['id'], state='PREPARED_BEFORE_JOB_PUBLICATION')
            save()  # The generated ID is durable before the normal job write.
        elif path.parent == STATE / 'media/inbox':
            require(item['new_job_id'] and path.name == item['new_job_id'] + '.json'
                    and value == {'job_id': item['new_job_id']}, 'INBOX_PUBLICATION')
        else:
            require(False, 'UNEXPECTED_CREATE_WRITE')
        old_atomic(path, value)

    runtime.atomic = observed_atomic
    try:
        result = runtime.create_job(dict(expected), previous['owner'])
        require(result.get('id') == item['new_job_id'], 'CREATED_JOB_ID')
    finally:
        runtime.atomic = old_atomic
    item['state'] = 'SUBMITTED_GENERATION_PENDING'; save()
    return item


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', value) else 'HOLD_QWEN_MEDIA_RETRY_UNVERIFIED'


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    adapter, runtime = load('owner_qwen_media_handoff.py', HANDOFF), load('owner_media_runtime.py', RUNTIME)
    require(sha(read(ROOT / 'scripts/nox_dispatcher_t855u.py')) == DISPATCHER, 'DISPATCHER_PIN')
    require(sha(read(STATE / 'owner_qwen_media_handoff_6907909296.json')) == INSTALL_RECEIPT,
            'INSTALL_RECEIPT_PIN')
    require(sha(read(ROOT / 'config/owner_qwen_media_handoff.json')) == CONFIG, 'CONFIG_PIN')
    require(not LINK.exists() and not LINK.is_symlink(), 'PRIOR_ATTEMPT_REQUIRES_INSPECTION')
    actions = adapter.Admission({}, runtime); actions.configuration(HANDOFF)
    lease = os.open(STATE / 'owner_maintenance.lock', os.O_RDWR | os.O_NOFOLLOW)
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'state': 'PREFLIGHT',
              'replacements': [], 'private_prompts_exported': False, 'old_tasks_requeued': 0,
              'old_jobs_modified': False, 'training_control_performed': False}
    original_atomic = runtime.atomic
    def save():
        original_atomic(LINK, result)
        sync_parent(LINK)
    try:
        fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
        require(not runtime.media_stop(), 'OWNER_STOP_OR_MAINTENANCE')
        for path, pin in ((ROOT / 'scripts/nox_dispatcher_t855u.py', DISPATCHER),
                          (ROOT / 'scripts/owner_qwen_media_handoff.py', HANDOFF),
                          (ROOT / 'scripts/owner_media_runtime.py', RUNTIME),
                          (ROOT / 'config/owner_qwen_media_handoff.json', CONFIG)):
            require(sha(read(path)) == pin, 'SOURCE_CHANGED_BEFORE_LEASE')
        result['completed_six'] = adapter.completed_six(actions)
        before = history()
        previous = []
        for job_id, pin in JOBS.items():
            raw = read(runtime.job_path(job_id)); require(sha(raw) == pin, 'OLD_JOB_PIN')
            job = json.loads(raw)
            require(job.get('id') == job_id and job.get('state') == 'BLOCKED'
                    and job.get('reason') == 'HOLD_RESUMABLE_TRAINER_WRAPPER_REQUIRED'
                    and job.get('generation_verified') is False and job.get('outputs') == []
                    and not job.get('cancel_requested') and not job.get('prompt_id'), 'OLD_JOB_SCOPE')
            previous.append(job)
        require(all(runtime.validate_request(job['request']) == job['request'] for job in previous),
                'ORIGINAL_REQUEST_NORMALIZATION')
        require(not any(path.is_symlink() for path in (LINK, *LINK.parents)), 'LINK_SYMLINK')
        LINK.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        sync_parent(LINK.parent)
        fd = os.open(LINK, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(result)); stream.flush(); os.fsync(stream.fileno())
        sync_parent(LINK)
        for job in previous:
            require(not runtime.media_stop(), 'STOP_BEFORE_SUBMIT')
            submit_linked(runtime, job, result, save)
        require(history() == before and all(sha(read(runtime.job_path(jid))) == pin for jid, pin in JOBS.items()),
                'OLD_HISTORY_CHANGED')
        result.update(state='TWO_REPLACEMENT_JOBS_SUBMITTED', old_history_preserved=True,
                      generation_acceptance='PENDING_NATIVE_LIFECYCLE')
        save()
    finally:
        os.close(lease)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_media_retry_submission', 'data': result}), flush=True)
    deadline = time.monotonic() + 240
    observed = []
    while True:
        observed = []
        for item in result['replacements']:
            job = runtime.load_job(item['new_job_id'])
            outputs = [{key: output.get(key) for key in ('filename', 'bytes', 'sha256', 'width', 'height', 'frames', 'media_type')}
                       for output in job.get('outputs', [])]
            observed.append({'old_job_id': item['old_job_id'], 'new_job_id': item['new_job_id'], 'kind': item['kind'],
                             'state': job['state'], 'reason': safe(RuntimeError(job.get('reason', '')))
                             if job.get('reason') else None, 'generation_verified': job.get('generation_verified') is True,
                             'outputs': outputs, 'gpu1_released': job.get('gpu1_released') is True})
        if all(row['state'] in runtime.TERMINAL for row in observed) or time.monotonic() >= deadline:
            break
        time.sleep(2)
    accepted = all(row['state'] == 'COMPLETED' and row['generation_verified'] and row['outputs'] for row in observed)
    result.update(state='REPLACEMENT_MEDIA_GENERATED_VERIFIED' if accepted else 'REPLACEMENT_MEDIA_OBSERVED_NOT_ACCEPTED',
                  observed_jobs=observed, finished_at=time.time())
    save()
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_media_retry_result', 'data': result}), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(accepted).lower(), flush=True)
    return 0 if accepted else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_media_retry_hold', 'data': {'reason': safe(exc)}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
