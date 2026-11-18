"""Pure relay admission/comparison rules; no I/O, leases or optimizer permission.

The dispatcher remains the authority for current native source/owner/resource
verification. This module can only narrow its admission, never replace it.
"""
from __future__ import annotations

import math
import re
import time

MIB = 1024 ** 2
GIB = 1024 ** 3
INSTANCE = 60509551
SHA = re.compile(r'[a-f0-9]{64}')
TRAINING_REQUIREMENTS = {
    'entry_raw_headroom_bytes': 32 * GIB,
    'memfd_stage_raw_base_headroom_bytes': 48 * GIB,
    'full_restage_raw_headroom_bytes': 70869001213,
    'gpu1_free_mib': 30000,
    'disk_floor_bytes': 10 * GIB,
    'inactive_file_counts_as_training_headroom': False,
}

# Primary sources, retrieved 2026-11-18. These motivate engineering choices;
# their published task-specific gains are not measured gains for NOX.
RESEARCH_BASIS = {
    'incremental_verified_memory': 'https://arxiv.org/abs/2510.04618v3',
    'reflection_with_external_feedback': 'https://arxiv.org/abs/2303.11366',
    'budgeted_prompt_candidates': 'https://arxiv.org/abs/2507.19457v2',
    'harness_candidates_with_prior_artifacts': 'https://arxiv.org/abs/2603.28052',
    'difficulty_aware_compute': 'https://arxiv.org/abs/2408.03314',
    'isolated_artifact_verification': 'https://www.tbench.ai/news/terminal-bench-4-1',
    'same_harness_model_comparison': 'https://www.swebench.com/',
    'real_work_multiple_metrics': 'https://arena.ai/leaderboard/agent',
}


def _integer(value, low=0, high=2 ** 63 - 1):
    return type(value) is int and low <= value <= high


def _number(value, low=0, high=1e15):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _hold(reason, **extra):
    return {'schema': 'NOX_RELAY_RESOURCE_ADMISSION_V1', 'admit': False,
            'reason': reason, 'optimizer_updates_authorized': False,
            'native_writer_lease': False, **extra}


def evaluate_resources(snapshot, demand, *, now=None):
    """Recheck exact existing CPU budget; GPU/weight work never inherits it.

    snapshot is the native callback's raw resource evidence. demand contains
    lane and budget fields from a grounded mission. A true result permits only
    bounded source work; model calls still acquire the existing fair slot lease.
    """
    if not isinstance(snapshot, dict) or not isinstance(demand, dict):
        return _hold('HOLD_RELAY_RESOURCE_SCHEMA')
    if (snapshot.get('instance_id') != INSTANCE or snapshot.get('stop_active') is not False
            or any(snapshot.get(key) is not True for key in
                   ('native_verified', 'owner_scope_verified', 'source_sha_verified'))):
        return _hold('HOLD_RELAY_NATIVE_OWNER_EVIDENCE')
    lane = demand.get('lane', 'cpu')
    if lane == 'optimizer':
        return _hold('HOLD_NEW_TRAINING_CONTEXT_AND_QUALITY_DECISION_REQUIRED',
                     requirements=TRAINING_REQUIREMENTS.copy())
    if lane == 'eval_only':
        # A read-only checkpoint-preparation receipt is not model-eval admission.
        return _hold('HOLD_REVIEWED_EVAL_RUNNER_AND_RESOURCE_HANDOFF_REQUIRED',
                     requirements=TRAINING_REQUIREMENTS.copy())
    if lane not in ('cpu', 'model', 'checkpoint_prepare'):
        return _hold('HOLD_RELAY_UNKNOWN_RESOURCE_LANE')
    limits = demand.get('budget')
    bounds = {'cpu_seconds': (1, 120), 'max_model_turns': (0, 24),
              'max_searches': (0, 4), 'max_output_bytes': (1, 262144)}
    if (not isinstance(limits, dict) or any(key not in limits for key in bounds)
            or any(not _integer(limits[key], *bound) for key, bound in bounds.items())
            or demand.get('paid_api_calls', 0) != 0):
        return _hold('HOLD_RELAY_TASK_BUDGET')
    if lane == 'checkpoint_prepare' and (limits['max_model_turns'] or limits['max_searches']):
        return _hold('HOLD_CHECKPOINT_PREPARE_IS_READ_ONLY')
    budget = snapshot.get('bounded_cpu_budget')
    required = {'schema', 'source', 'instance_id', 'observed_at', 'worker_slots',
                'current_bytes', 'max_bytes', 'inactive_file_bytes', 'file_bytes',
                'shmem_bytes', 'sandbox_limit_bytes', 'planner_reserve_bytes',
                'minimum_headroom_bytes', 'memory_psi_some_avg10',
                'memory_psi_full_avg10', 'cpu_pressure'}
    if (not isinstance(budget, dict) or set(budget) != required
            or budget['schema'] != 'NOX_BOUNDED_CPU_BUDGET_V1'
            or budget['source'] != 'cgroup_v2' or budget['instance_id'] != INSTANCE):
        return _hold('HOLD_RELAY_BOUNDED_CPU_EVIDENCE')
    integer_fields = ('worker_slots', 'current_bytes', 'max_bytes', 'inactive_file_bytes',
                      'file_bytes', 'shmem_bytes', 'sandbox_limit_bytes',
                      'planner_reserve_bytes', 'minimum_headroom_bytes')
    if (any(not _integer(budget[key]) for key in integer_fields)
            or budget['max_bytes'] == 0 or budget['shmem_bytes'] > budget['file_bytes']
            or budget['worker_slots'] != 3 or budget['planner_reserve_bytes'] != 128 * MIB
            or budget['minimum_headroom_bytes'] != 2 * GIB
            or not 96 * MIB <= budget['sandbox_limit_bytes'] <= 512 * MIB
            or budget['sandbox_limit_bytes'] % MIB):
        return _hold('HOLD_RELAY_BOUNDED_CPU_BYTES')
    if any(not _number(budget[key]) for key in
           ('observed_at', 'memory_psi_some_avg10', 'memory_psi_full_avg10', 'cpu_pressure')):
        return _hold('HOLD_RELAY_PRESSURE_TELEMETRY')
    now = time.time() if now is None else now
    if not _number(now) or not 0 <= now - budget['observed_at'] <= 5:
        return _hold('HOLD_RELAY_STALE_CAPACITY')
    if max(budget['memory_psi_some_avg10'], budget['memory_psi_full_avg10']) >= 1:
        return _hold('HOLD_RELAY_MEMORY_PRESSURE')
    if budget['cpu_pressure'] >= 50:
        return _hold('HOLD_RELAY_CPU_PRESSURE')
    reclaim = min(budget['inactive_file_bytes'], budget['file_bytes'] - budget['shmem_bytes'],
                  budget['current_bytes'])
    reserve = 3 * (max(256 * MIB, budget['sandbox_limit_bytes']) + 128 * MIB)
    headroom = budget['max_bytes'] - (budget['current_bytes'] - reclaim + reserve)
    if headroom < 2 * GIB:
        return _hold('HOLD_RELAY_CPU_HEADROOM')
    # Reclaimable page-cache is an estimate, not immediately free allocation.
    # Keep a hard raw cgroup buffer for the interactive chat before new work.
    raw_headroom = budget['max_bytes'] - budget['current_bytes']
    raw_floor = max(512 * MIB, budget['sandbox_limit_bytes'] + budget['planner_reserve_bytes'])
    if raw_headroom < raw_floor:
        return _hold('HOLD_RELAY_RAW_CGROUP_HEADROOM',
                     raw_headroom_bytes=raw_headroom, required_raw_headroom_bytes=raw_floor)
    return {'schema': 'NOX_RELAY_RESOURCE_ADMISSION_V1', 'admit': True, 'reason': None,
            'scope': 'BOUNDED_SOURCE_WORK_NOT_GPU_OR_WEIGHT_ADMISSION',
            'limits': {key: limits[key] for key in bounds}, 'maximum_workers': 3,
            'model_concurrency': 1, 'model_lease_required': lane == 'model',
            'paid_api_calls': 0, 'reserved_bytes': reserve, 'cpu_headroom_bytes': headroom,
            'raw_headroom_bytes': budget['max_bytes'] - budget['current_bytes'],
            'optimizer_updates_authorized': False, 'native_writer_lease': False}


def _wilson_95(passed, total):
    """Descriptive interval for one independent outcome per declared task."""
    z = 1.959963984540054
    proportion = passed / total
    divisor = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / divisor
    radius = z * math.sqrt(proportion * (1 - proportion) / total
                          + z * z / (4 * total * total)) / divisor
    return {'lower': max(0.0, center - radius), 'upper': min(1.0, center + radius),
            'confidence_level': 0.95, 'method': 'WILSON_95_INDEPENDENT_TASKS'}


def comparison_scope(candidate, baseline):
    """Compare fixed task outcomes, never public Arena units or an ordinal rank.

    harness_sha256 pins the *evaluation* harness. The candidate agent/harness
    belongs in artifact_sha256 and may differ. A declared task is counted once;
    all failures, timeouts and exhausted budgets stay in the denominator. The
    caller verifies receipts before setting native_verified. These marginal
    intervals are descriptive, not a paired significance test or promotion gate.
    """
    answer = {'schema': 'NOX_RELAY_COMPARISON_V1', 'comparable': False,
              'reason': 'EVIDENCE_OR_EVALUATION_CONTRACT_MISMATCH',
              'scope': 'PINNED_TASK_DISTRIBUTION_AND_BUDGET_ONLY',
              'rank_claim_authorized': False, 'general_intelligence_claim_authorized': False,
              'significant_improvement_claim_authorized': False, 'automatic_promotion': False}
    if not all(isinstance(row, dict) for row in (candidate, baseline)):
        return {**answer, 'reason': 'MISSING_EVALUATION'}
    same = ('benchmark_id', 'benchmark_revision', 'task_split_sha256',
            'verifier_sha256', 'budget_policy_sha256', 'harness_sha256',
            'denominator_kind', 'trial_count', 'confidence_method', 'confidence_level')
    pins = ('task_split_sha256', 'verifier_sha256', 'budget_policy_sha256',
            'harness_sha256', 'artifact_sha256', 'evaluation_receipt_sha256')
    valid = all(
        row.get('holdout_isolated') is True and row.get('native_verified') is True
        and row.get('all_declared_tasks_accounted') is True
        and row.get('failures_and_timeouts_in_denominator') is True
        and row.get('denominator_kind') == 'ONE_INDEPENDENT_OUTCOME_PER_DECLARED_TASK'
        and row.get('confidence_method') == 'WILSON_95_INDEPENDENT_TASKS'
        and type(row.get('confidence_level')) is float and row['confidence_level'] == 0.95
        and all(type(row.get(key)) is str and 1 <= len(row[key]) <= 160
                for key in ('benchmark_id', 'benchmark_revision'))
        and all(type(row.get(key)) is str and SHA.fullmatch(row[key]) for key in pins)
        and _integer(row.get('trial_count'), 1, 1000000)
        and _integer(row.get('passed_count'), 0, row['trial_count'])
        for row in (candidate, baseline))
    comparable = bool(valid and all(candidate.get(key) == baseline.get(key) and
                                   candidate.get(key) is not None for key in same))
    if not comparable:
        return answer
    return {**answer, 'comparable': True, 'reason': None, 'denominator': candidate['trial_count'],
            'candidate': {'passed_count': candidate['passed_count'],
                          'rate': candidate['passed_count'] / candidate['trial_count'],
                          'ci': _wilson_95(candidate['passed_count'], candidate['trial_count'])},
            'baseline': {'passed_count': baseline['passed_count'],
                         'rate': baseline['passed_count'] / baseline['trial_count'],
                         'ci': _wilson_95(baseline['passed_count'], baseline['trial_count'])},
            'descriptive_rate_delta': (candidate['passed_count'] - baseline['passed_count'])
                                      / candidate['trial_count']}
