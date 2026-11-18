"""NOX B5/5B01 source candidate: durable deduplication in existing media/jobs store.

Not installed. The live owner_media_runtime.py must wire this under its existing
state/media/jobs.lock and use its own authenticated owner, atomic(), read_json(),
MediaHold, and quota/STOP admission. No independent backend or ledger.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

REQUEST_ID = re.compile(r'^[0-9a-f]{32}$')
ALLOWED = {'kind', 'prompt', 'negative_prompt', 'width', 'height', 'frames', 'fps', 'seed'}

class IdempotencyHold(RuntimeError):
    pass


def request_identity(body):
    """Hash the submitted request, before server adds a random default seed."""
    if not isinstance(body, dict) or set(body) - (ALLOWED | {'client_request_id'}):
        raise IdempotencyHold('INVALID_MEDIA_REQUEST')
    key = body.get('client_request_id')
    if type(key) is not str or not REQUEST_ID.fullmatch(key):
        raise IdempotencyHold('INVALID_MEDIA_CLIENT_REQUEST_ID')
    payload = {k: v for k, v in body.items() if k != 'client_request_id'}
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise IdempotencyHold('INVALID_MEDIA_REQUEST') from None
    return key, payload, hashlib.sha256(encoded).hexdigest()


def find_existing(jobs_dir, owner, key, digest, read_json, repair_inbox=None):
    """Must be called under existing jobs.lock. Fail closed on malformed state."""
    if type(owner) is not str or not owner or len(owner) > 256:
        raise IdempotencyHold('HOLD_MEDIA_OWNER_ID')
    found = None
    for path in sorted(Path(jobs_dir).glob('*.json')):
        item = read_json(path)
        if (path.is_symlink() or not isinstance(item, dict)
                or item.get('id') != path.stem or not REQUEST_ID.fullmatch(path.stem)):
            raise IdempotencyHold('HOLD_MEDIA_JOB_INDEX_UNREADABLE')
        if item.get('owner') == owner and item.get('client_request_id') == key:
            if item.get('payload_sha256') != digest:
                raise IdempotencyHold('HOLD_MEDIA_IDEMPOTENCY_CONFLICT')
            if found is not None:
                raise IdempotencyHold('HOLD_MEDIA_DUPLICATE_REQUEST_ID')
            found = item
    if found and repair_inbox and found.get('state') == 'QUEUED':
        repair_inbox(found['id'])
    return found


def repair_queued_inbox(inbox_dir, job_id, read_json, atomic):
    """Repair a crash between atomic(job) and atomic(inbox) only under jobs.lock."""
    if not REQUEST_ID.fullmatch(job_id):
        raise IdempotencyHold('HOLD_MEDIA_JOB_ID')
    target = Path(inbox_dir) / (job_id + '.json')
    if target.is_symlink():
        raise IdempotencyHold('HOLD_MEDIA_INBOX_CHANGED')
    if target.exists():
        recorded = read_json(target)
        if recorded != {'job_id': job_id}:
            raise IdempotencyHold('HOLD_MEDIA_INBOX_CHANGED')
    else:
        atomic(target, {'job_id': job_id})


def create_or_resume(body, owner, *, lock, jobs_dir, inbox_dir, read_json,
                     atomic, preflight, new_job):
    """A source-ready create path; supply existing jobs.lock and quota callbacks.

    The owner-authenticated FastAPI route must use the same lock as legacy
    create_job. `new_job` performs quota/STOP checks and returns a job record;
    the caller may then serialize its existing public_job() result.
    Rechecking after preflight closes races across processes and threads.
    """
    key, payload, digest = request_identity(body)
    def repair(job_id):
        repair_queued_inbox(inbox_dir, job_id, read_json, atomic)
    with lock():
        existing = find_existing(jobs_dir, owner, key, digest, read_json, repair)
        if existing is not None:
            return existing
    preflight(payload)
    with lock():
        existing = find_existing(jobs_dir, owner, key, digest, read_json, repair)
        if existing is not None:
            return existing
        record = new_job(payload)
        if (not isinstance(record, dict) or
                not isinstance(record.get('id'), str) or
                not REQUEST_ID.fullmatch(record['id'])):
            raise IdempotencyHold('HOLD_MEDIA_NEW_JOB_SCHEMA')
        if record.get('owner') != owner or record.get('state') != 'QUEUED':
            raise IdempotencyHold('HOLD_MEDIA_NEW_JOB_OWNER_OR_STATE')
        record.update(client_request_id=key, payload_sha256=digest)
        atomic(Path(jobs_dir) / (record['id'] + '.json'), record)
        repair(record['id'])
        return record
