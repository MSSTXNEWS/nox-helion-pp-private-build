"""Measured resource/quality policy called by the existing owner task pool.

No worker, daemon, model, scheduler or filesystem mutation lives here. Native
callbacks supply observations and execute admitted claims. Source checks are
not evidence of GPU work or an accepted native release.
"""
from __future__ import annotations
from collections.abc import Mapping
import math
import hashlib
import json
import re
import time

HOST_FIELDS = ('cpu_cores', 'ram_bytes', 'io_bytes_per_sec', 'model_slots')
GPU_FIELDS = ('vram_mib', 'compute_fraction')
SHA = re.compile(r'^[a-f0-9]{64}$')
CAP = .85
MAX_AGE_SECONDS = 10


class PolicyHold(ValueError):
    pass


def number(value, code, minimum=0, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise PolicyHold(code)
    return value


def exact_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None and value != '0' * 64


def slot_count(value):
    """Model slots are admitted concurrency counts, not utilization fractions."""
    value = number(value, 'HOLD_POLICY_MODEL_SLOT_COUNT')
    if value != math.floor(value):
        raise PolicyHold('HOLD_POLICY_MODEL_SLOT_COUNT')
    return int(value)


def utility_score(task):
    """Explicit owner priority remains the outer order; this ranks within it."""
    cost = number(task.get('estimated_cost', 1), 'HOLD_POLICY_COST', .000001)
    utility = task.get('utility', {})
    if not isinstance(utility, Mapping) or set(utility) - {'value', 'novelty', 'confidence'}:
        raise PolicyHold('HOLD_POLICY_UTILITY')
    value = number(utility.get('value', .5), 'HOLD_POLICY_VALUE', 0, 1)
    novelty = number(utility.get('novelty', 0), 'HOLD_POLICY_NOVELTY', 0, 1)
    confidence = number(utility.get('confidence', 1), 'HOLD_POLICY_CONFIDENCE', 0, 1)
    return value * (1 + .5 * novelty) * confidence / cost


def promotion_decision(record, *, candidate_sha, criteria=None):
    """Reject mismatched experiments and every required metric regression.

    Native callers must bind the supplied record to their verified evaluation
    receipt. A positive decision only admits an existing reviewed promotion
    handler; it does not publish weights or assert their quality by itself.
    """
    reasons = []
    if not isinstance(criteria, Mapping) or set(criteria) != {'baseline_sha256', 'holdout_sha256', 'metrics'} or not isinstance(criteria['metrics'], Mapping) or not criteria['metrics']:
        return {'eligible': False, 'reasons': ['HOLD_OWNER_QUALITY_CRITERIA']}
    try:
        criteria_sha = hashlib.sha256(json.dumps(criteria, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        return {'eligible': False, 'reasons': ['HOLD_OWNER_QUALITY_CRITERIA']}
    if not isinstance(record, Mapping):
        return {'eligible': False, 'reasons': ['HOLD_QUALITY_RECORD']}
    if (record.get('criteria_sha256') != criteria_sha or record.get('baseline_sha256') != criteria['baseline_sha256']
            or record.get('holdout_sha256') != criteria['holdout_sha256']):
        reasons.append('HOLD_QUALITY_CRITERIA_BINDING')
    if (not exact_sha(candidate_sha) or record.get('candidate_sha256') != candidate_sha
            or not exact_sha(record.get('baseline_sha256'))
            or not exact_sha(record.get('evaluation_receipt_sha256'))
            or record.get('native_receipt_verified') is not True):
        reasons.append('HOLD_QUALITY_ARTIFACT_BINDING')
    if (not exact_sha(record.get('holdout_sha256'))
            or record.get('candidate_holdout_sha256') != record.get('holdout_sha256')
            or record.get('baseline_holdout_sha256') != record.get('holdout_sha256')
            or record.get('unseen_holdout_verified') is not True):
        reasons.append('HOLD_QUALITY_HOLDOUT')
    if record.get('regression_suite_passed') is not True or record.get('rollback_verified') is not True:
        reasons.append('HOLD_QUALITY_REGRESSION_OR_ROLLBACK')
    metrics = record.get('metrics')
    if not isinstance(metrics, list) or not metrics:
        reasons.append('HOLD_QUALITY_METRICS')
        metrics = []
    seen = set(); improved = False
    for metric in metrics:
        try:
            if not isinstance(metric, Mapping) or not isinstance(metric.get('id'), str) or metric['id'] in seen:
                raise PolicyHold('HOLD_QUALITY_METRIC_ID')
            seen.add(metric['id'])
            baseline = number(metric.get('baseline'), 'HOLD_QUALITY_METRIC')
            candidate = number(metric.get('candidate'), 'HOLD_QUALITY_METRIC')
            rule = criteria['metrics'].get(metric['id'])
            if not isinstance(rule, Mapping) or set(rule) != {'direction', 'max_regression', 'min_gain'}:
                raise PolicyHold('HOLD_QUALITY_REQUIRED_METRICS')
            tolerance = number(rule['max_regression'], 'HOLD_QUALITY_TOLERANCE')
            gain = number(rule['min_gain'], 'HOLD_QUALITY_GAIN')
            direction = rule['direction']
            if direction not in ('higher', 'lower'):
                raise PolicyHold('HOLD_QUALITY_DIRECTION')
            delta = candidate - baseline if direction == 'higher' else baseline - candidate
            if delta < -tolerance:
                reasons.append('HOLD_QUALITY_REGRESSION:' + metric['id'])
            improved = improved or delta > 0 and delta >= gain
        except PolicyHold as exc:
            reasons.append(str(exc))
    required = list(criteria['metrics'])
    if (not isinstance(required, list) or not required or any(not isinstance(x, str) for x in required)
            or len(set(required)) != len(required) or set(required) != seen):
        reasons.append('HOLD_QUALITY_REQUIRED_METRICS')
    if not improved:
        reasons.append('HOLD_QUALITY_NO_VERIFIED_GAIN')
    return {'eligible': not reasons, 'reasons': reasons}


class Budget:
    """A single measured tick; selected pending claims reserve incremental cost."""
    def __init__(self, snapshot, now=None):
        now = time.time() if now is None else now
        if not isinstance(snapshot, Mapping) or snapshot.get('schema') != 'NOX_RESOURCE_POLICY_V1':
            raise PolicyHold('HOLD_POLICY_SNAPSHOT')
        if snapshot.get('native_verified') is not True or snapshot.get('instance_id') != 60509551:
            raise PolicyHold('HOLD_POLICY_NATIVE_IDENTITY')
        at = number(snapshot.get('observed_at'), 'HOLD_POLICY_TIMESTAMP')
        if not 0 <= now - at <= MAX_AGE_SECONDS:
            raise PolicyHold('HOLD_POLICY_STALE_OBSERVATION')
        if type(snapshot.get('chat_active')) is not bool:
            raise PolicyHold('HOLD_POLICY_CHAT_STATE')
        if snapshot.get('chat_budget_admitted') is not True:
            raise PolicyHold('HOLD_CHAT_BUDGET_ADMISSION')
        self.chat_active = snapshot['chat_active']
        self.host = self._remaining(snapshot.get('host'), HOST_FIELDS)
        self.gpus = {}
        rows = snapshot.get('gpus')
        if not isinstance(rows, list): raise PolicyHold('HOLD_POLICY_GPU_LIST')
        for gpu in rows:
            if not isinstance(gpu, Mapping) or not isinstance(gpu.get('uuid'), str) or not gpu['uuid'].startswith('GPU-') or gpu['uuid'] in self.gpus:
                raise PolicyHold('HOLD_POLICY_GPU_IDENTITY')
            self.gpus[gpu['uuid']] = self._remaining(gpu, GPU_FIELDS)
        self.original = {'host': dict(self.host), 'gpus': {k:dict(v) for k,v in self.gpus.items()}}

    @staticmethod
    def _remaining(row, fields):
        if not isinstance(row, Mapping): raise PolicyHold('HOLD_POLICY_RESOURCE_DIMENSIONS')
        result = {}
        for group in ('capacity', 'used', 'pending_reserved', 'chat_reserved'):
            if not isinstance(row.get(group), Mapping) or set(row[group]) != set(fields):
                raise PolicyHold('HOLD_POLICY_RESOURCE_DIMENSIONS')
        for field in fields:
            capacity = number(row['capacity'][field], 'HOLD_POLICY_CAPACITY')
            used = number(row['used'][field], 'HOLD_POLICY_USED')
            pending = number(row['pending_reserved'][field], 'HOLD_POLICY_RESERVED')
            chat = number(row['chat_reserved'][field], 'HOLD_POLICY_CHAT_RESERVE')
            if field == 'model_slots':
                # Applying 85% to a single admitted slot left 0.85 slots, so
                # even one job could never run. Compute/VRAM keep their caps.
                capacity, used, pending, chat = map(slot_count, (capacity, used, pending, chat))
                result[field] = max(0, capacity - used - pending - chat)
            else:
                result[field] = max(0, CAP * capacity - used - pending - chat)
        return result

    def reserve(self, task, quality=None, criteria=None):
        demand = task.get('resource_demand')
        if not isinstance(demand, Mapping) or set(demand) != {'host', 'gpus'}:
            return 'HOLD_POLICY_TASK_DEMAND'
        host = demand['host']; gpus = demand['gpus']
        if not isinstance(host, Mapping) or set(host) != set(HOST_FIELDS) or not isinstance(gpus, Mapping):
            return 'HOLD_POLICY_TASK_DEMAND'
        try:
            requested_host = {k:number(host[k], 'HOLD_POLICY_TASK_DEMAND') for k in HOST_FIELDS}
            requested_host['model_slots'] = slot_count(requested_host['model_slots'])
            requested_gpu = {}
            for uid, row in gpus.items():
                if uid not in self.gpus or not isinstance(row, Mapping) or set(row) != set(GPU_FIELDS):
                    return 'HOLD_POLICY_GPU_DEMAND'
                requested_gpu[uid] = {k:number(row[k], 'HOLD_POLICY_GPU_DEMAND') for k in GPU_FIELDS}
            if task.get('resource') == 'GPU_EXCLUSIVE' and not requested_gpu:
                return 'HOLD_POLICY_GPU_DEMAND'
            if self.chat_active and (requested_gpu or requested_host['model_slots']):
                return 'WAIT_CHAT_SOFT_YIELD'
            if task.get('promotion_candidate_sha256') is not None:
                decision = promotion_decision(quality, candidate_sha=task['promotion_candidate_sha256'], criteria=criteria)
                if not decision['eligible']: return decision['reasons'][0]
            if any(value > self.host[k] for k,value in requested_host.items()):
                return 'WAIT_HOST_MEASURED_REMAINDER'
            if any(value > self.gpus[uid][k] for uid,row in requested_gpu.items() for k,value in row.items()):
                return 'WAIT_GPU_MEASURED_REMAINDER'
            for k,value in requested_host.items(): self.host[k] -= value
            for uid,row in requested_gpu.items():
                for k,value in row.items(): self.gpus[uid][k] -= value
            return None
        except PolicyHold as exc:
            return str(exc)


def soft_yield_requests(snapshot):
    """Requests, not SIGSTOP/kill: native handlers acknowledge safe boundaries."""
    if not snapshot.get('chat_active'): return []
    requests = []
    for row in snapshot.get('running_background', []):
        if (isinstance(row, Mapping) and row.get('uses_gpu') is True
                and isinstance(row.get('task_id'), str)
                and row.get('safe_boundary') in ('optimizer_step', 'embedding_batch')
                and exact_sha(row.get('checkpoint_sha256'))
                and type(row.get('cursor')) in (str, int)):
            requests.append({k:row[k] for k in ('task_id', 'safe_boundary', 'checkpoint_sha256', 'cursor')})
    return requests
