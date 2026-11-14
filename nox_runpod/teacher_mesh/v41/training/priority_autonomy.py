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

from nox_runpod.teacher_mesh.v71.disk_budget import SAFETY_FLOOR_BYTES, verify_new_write_space

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
            data = dict(job, owner_scope=owner_scope, requires_native_worker=True,
                        priority='P1', chat_priority='P0',
                        requires_native_chat_recheck=True)
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


@dataclass(frozen=True)
class ChatFirstBudget:
    """Admission policy for existing OneHost; never starts a process."""
    quiet_seconds: int = 20
    chat_recent_seconds: int = 45
    # Minimum filesystem rollback headroom for NEW WRITES, not a chat threshold.
    disk_checkpoint_reserve_bytes: int = 10_000_000_000
    min_gpu_free_mib: int = 3072
    max_gpu_temp_c: int = 80
    target_idle_compute_pct: int = 85


def chat_first_admission(status: Mapping, *, budget: ChatFirstBudget = ChatFirstBudget()) -> dict:
    """Turn live OneHost observations into an *advisory* background-work decision.

    A chat request is a preemption signal, not permission to kill a trainer in
    mid-step. OneHost must pause at a verified optimizer/checkpoint boundary.
    No disk/backup proof -> allow nonmutating preparation, not training/weights.
    Missing telemetry, heartbeat or chat state -> fail closed.
    """
    result = {'schema': 'NOX_CHAT_FIRST_ADMISSION_V1', 'queue_owner': 'EXISTING_NOX_ONEHOST',
              'new_scheduler': False, 'launch': False, 'training_launch': False,
              'target_compute_pct_idle': budget.target_idle_compute_pct,
              'chat_reserved': True, 'actions': [], 'reasons': []}
    if not isinstance(status, Mapping) or status.get('owner_authorized') is not True:
        result['reasons'].append('HOLD_NO_OWNER_HEARTBEAT')
        return result
    if status.get('stop_active') is not False:
        result['reasons'].append('HOLD_STOP_OR_UNKNOWN')
        return result
    if status.get('chat_state') not in ('idle', 'pending', 'generating'):
        result['reasons'].append('HOLD_CHAT_STATE_UNKNOWN')
        return result
    elapsed = status.get('seconds_since_chat_activity')
    if type(elapsed) not in (int, float) or elapsed < 0:
        result['reasons'].append('HOLD_CHAT_HEARTBEAT_UNKNOWN')
        return result
    if status['chat_state'] in ('pending','generating') or elapsed < budget.chat_recent_seconds:
        result['actions'] = ['CHAT_P0', 'PAUSE_GPU_BACKGROUND_AT_SAFE_BOUNDARY',
                             'PRESERVE_MODEL_AND_S03']
        result['reasons'].append('CHAT_FIRST')
        return result

    result['actions'] = ['KEEP_MAIN_NOX_MODEL_WARM', 'ALLOW_CPU_KNOWLEDGE_PREP',
                         'ALLOW_INDEXED_S03_RETRIEVAL']
    result['launch'] = True
    gpus = status.get('gpus')
    # Chat inference itself is never held for an arbitrary 20 GB disk threshold.
    # A new checkpoint, optimizer/temp write or training cycle requires a real
    # verified per-operation footprint, with a small emergency floor.
    disk_snapshot = dict(status)
    disk_snapshot['min_free_after_bytes'] = budget.disk_checkpoint_reserve_bytes
    disk_gate = verify_new_write_space(disk_snapshot)
    result['disk_gate'] = disk_gate['state']
    if not isinstance(gpus, list) or len(gpus) != 2 or any(
        not isinstance(g, Mapping) or
        type(g.get('vram_free_mib')) is not int or g['vram_free_mib'] < 0 or
        type(g.get('temperature_c')) is not int or
        g['temperature_c'] < 0 for g in gpus):
        result['reasons'].append('HOLD_GPU_TELEMETRY')
        return result
    if any(g['temperature_c'] >= budget.max_gpu_temp_c for g in gpus):
        result['reasons'].append('HOLD_GPU_TEMP')
        return result
    if disk_gate['state'] != 'READY_FOR_OTHER_NATIVE_GATES':
        result['reasons'].append(disk_gate['state'])
        return result
    if status.get('external_restore_verified') is not True:
        result['reasons'].append('HOLD_EXTERNAL_RESTORE')
        return result
    if status.get('checkpoint_resume_verified') is not True:
        result['reasons'].append('HOLD_CHECKPOINT_RESUME')
        return result
    if status.get('runtime_gpu_abi_verified') is not True:
        result['reasons'].append('HOLD_CUDA_RUNTIME')
        return result
    if status.get('training_owner_lease') is not True:
        result['reasons'].append('HOLD_NATIVE_TRAINING_LEASE')
        return result
    available = [i for i,g in enumerate(gpus)
                 if g['vram_free_mib'] >= budget.min_gpu_free_mib]
    # GPU0 should remain dedicated to chat; offloading optimizer to GPU0
    # is not admitted even if telemetry reports spare capacity.
    if 1 not in available:
        result['reasons'].append('HOLD_GPU1_HEADROOM')
        return result
    result['actions'].append('REQUEST_ONEHOST_GPU1_DISTILLATION_ADMISSION')
    result['training_launch'] = False  # lease check is NOT an actual queue receipt
    result['reasons'].append('READY_FOR_NATIVE_QUEUE_AND_PEAK_VRAM_CHECK')
    return result
