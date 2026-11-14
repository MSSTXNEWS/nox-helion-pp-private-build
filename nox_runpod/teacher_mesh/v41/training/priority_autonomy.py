"""NOX V41: source-verified priority planner for the EXISTING OneHost task queue.

The planner schedules no host process and opens no network listener. An installed
OneHost must own authorization, STOP, idempotency, durable receipts and readback.
NOX is one identity; the six lanes are logical work types, not six LLMs.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any

_SHA = re.compile(r'^[0-9a-f]{64}$')
_ID = re.compile(r'^[A-Za-z0-9._:-]{4,120}$')
LANES = frozenset({'CORE', 'MEMORY', 'FORGE', 'SKILLS', 'TEACHERS', 'WEB_QA'})
PENDING = frozenset({'TODO', 'PENDING', 'IN_PROGRESS', 'BLOCKED'})


def _valid_task(row: Any) -> bool:
    """Only trustworthy numeric task receipts; percentages extracted from prose are not proof."""
    return (isinstance(row, Mapping)
        and isinstance(row.get('task_id'), str) and _ID.fullmatch(row['task_id']) is not None
        and row.get('lane') in LANES and row.get('state') in PENDING
        and type(row.get('progress_percent')) in (int, float)
        and 0 <= row['progress_percent'] <= 100
        and row.get('native_verified') is True
        and isinstance(row.get('source_sha256'), str) and _SHA.fullmatch(row['source_sha256']) is not None
        and isinstance(row.get('receipt_sha256'), str) and _SHA.fullmatch(row['receipt_sha256']) is not None
        and row.get('owner_scope_confirmed') is True)


def plan_priorities(rows: Sequence[Mapping], *, existing_job_ids: Sequence[str], limit: int = 6) -> dict:
    """Strictly finish proof-backed >=50% work before new work, no duplicates."""
    if not isinstance(rows, (list, tuple)) or len(rows) > 2000 or not isinstance(existing_job_ids, (list, tuple, set)):
        return {'state': 'HOLD_INVALID_INPUT', 'planned': []}
    if type(limit) is not int or not 1 <= limit <= 6:
        return {'state': 'HOLD_LIMIT', 'planned': []}
    existing = set(existing_job_ids)
    seen = set(); high = []; other = []; omitted = 0
    for row in rows:
        if not _valid_task(row):
            omitted += 1
            continue
        tid = row['task_id']
        if tid in seen or tid in existing:
            omitted += 1
            continue
        seen.add(tid)
        payload = {'task_id': tid, 'lane': row['lane'],
                   'progress_percent': float(row['progress_percent']),
                   'source_sha256': row['source_sha256'],
                   'receipt_sha256': row['receipt_sha256'],
                   'no_new_model_server': True, 'student_protected': True}
        if 50 <= row['progress_percent'] < 100:
            high.append(payload)
        elif row['progress_percent'] < 50:
            other.append(payload)
    high.sort(key=lambda x: (-x['progress_percent'], x['task_id']))
    other.sort(key=lambda x: (-x['progress_percent'], x['task_id']))
    # When eligible verified >=50% work exists, don't enqueue a new-from-zero job.
    selected = (high if high else other)[:limit]
    return {'state': 'PROPOSAL_ONLY_NOT_ENQUEUED', 'planned': selected,
            'ready_over_50_count': len(high), 'other_count': len(other),
            'unverified_or_duplicate_count': omitted,
            'native_job_receipts': [], 'jobs_enqueued': 0,
            'queue_owner': 'EXISTING_NOX_ONEHOST'}


@dataclass(frozen=True)
class SchedulerPorts:
    authorize: Callable[[str], bool]
    stop: Callable[[], bool]
    queue_enqueue: Callable[[dict], Mapping]
    queue_readback: Callable[[str], Mapping]
    s03_audit: Callable[[dict], bool]
    native_duplicate_check: Callable[[str], bool]


def submit_verified_plan(plan: Mapping, host: SchedulerPorts, *, owner_scope: str) -> dict:
    """Real enqueue requires actual native callbacks plus immutable receipts."""
    if plan.get('state') != 'PROPOSAL_ONLY_NOT_ENQUEUED':
        return {'state': 'HOLD_PLAN', 'jobs_enqueued': 0}
    if not isinstance(owner_scope, str) or _ID.fullmatch(owner_scope) is None:
        return {'state': 'HOLD_SCOPE', 'jobs_enqueued': 0}
    for name in ('authorize', 'stop', 'queue_enqueue', 'queue_readback', 's03_audit', 'native_duplicate_check'):
        if not callable(getattr(host, name, None)):
            return {'state': 'HOLD_NATIVE_CALLBACKS', 'jobs_enqueued': 0}
    if host.stop() is not False or host.authorize(owner_scope) is not True:
        return {'state': 'HOLD_STOP_OR_OWNER', 'jobs_enqueued': 0}
    receipts = []
    for job in plan['planned']:
        try:
            if host.stop() is not False or host.authorize(owner_scope) is not True:
                return {'state': 'HOLD_STOP_DURING_QUEUE', 'jobs_enqueued': len(receipts), 'receipts': receipts}
            if host.native_duplicate_check(job['task_id']):
                continue
            data = dict(job, owner_scope=owner_scope, requires_native_worker=True, priority='P0')
            data['manifest_sha256'] = sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            ticket = host.queue_enqueue(data)
            if not isinstance(ticket, Mapping) or ticket.get('accepted') is not True or not _ID.fullmatch(str(ticket.get('job_id', ''))):
                return {'state': 'HOLD_QUEUE_RECEIPT', 'jobs_enqueued': len(receipts), 'receipts': receipts}
            readback = host.queue_readback(ticket['job_id'])
            if not isinstance(readback, Mapping) or readback.get('job_id') != ticket['job_id'] or readback.get('state') not in ('pending', 'running'):
                return {'state': 'HOLD_QUEUE_READBACK', 'jobs_enqueued': len(receipts), 'receipts': receipts}
            audit = {'job_id':ticket['job_id'], 'task_id':job['task_id'], 'manifest_sha256':data['manifest_sha256'],
                     'queue_state':readback['state'], 'performed':True}
            if host.s03_audit(audit) is not True:
                return {'state':'HOLD_AUDIT_NOT_DURABLE','jobs_enqueued':len(receipts)+1,'receipts':receipts+[audit]}
            receipts.append(audit)
        except Exception:
            return {'state':'HOLD_NATIVE_SCHEDULER_ERROR', 'jobs_enqueued':len(receipts), 'receipts':receipts}
    return {'state':'NATIVE_QUEUE_READBACK_VERIFIED', 'jobs_enqueued':len(receipts), 'receipts':receipts,
            'training_started':False, 'source_only':False}
