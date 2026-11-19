"""NOT WIRED / NOT PRODUCTION: pure NOX chat resource admission contract.

This standalone review candidate accepts only a fresh owner-collected snapshot
for the existing shared model; it performs no reads, allocations, cache drops,
process control, or inference. It is not wired into the production chat route.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping


SCHEMA = 'NOX_CHAT_RESOURCE_ADMISSION_V1'
SAMPLE_SCHEMA = 'NOX_CHAT_RESOURCE_SAMPLE_V1'
CALIBRATION_SCHEMA = 'NOX_CHAT_RESOURCE_CALIBRATION_V1'
SHA = re.compile(r'^[a-f0-9]{64}$')
MAX_CURRENT_AGE_SECONDS = 5
MAX_BASELINE_AGE_SECONDS = 15
MAX_CALIBRATION_AGE_SECONDS = 7 * 24 * 60 * 60
MAX_RESERVATION_TTL_SECONDS = 30
MIB = 1024 * 1024
GIB = 1024 * MIB


class ChatResourceHold(ValueError):
    """A missing, stale, inconsistent, or unsafe measurement must HOLD."""


def _hold(code: str) -> None:
    raise ChatResourceHold('HOLD_CHAT_RESOURCE_' + code)


def _integer(value, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value >= 2**63:
        _hold(code)
    return value


def _finite(value, code: str, *, minimum: float = 0.0) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        _hold(code)
    return float(value)


def _mapping(value, code: str) -> Mapping:
    if not isinstance(value, Mapping):
        _hold(code)
    return value


def _validate_sample(sample, *, model, now: float, baseline: bool) -> dict:
    sample = _mapping(sample, 'SAMPLE_MISSING')
    required = {'schema', 'observed_at', 'instance_id', 'model', 'cgroup', 'process', 'gpus'}
    if set(sample) != required or sample.get('schema') != SAMPLE_SCHEMA:
        _hold('SAMPLE_SCHEMA')
    if sample.get('instance_id') != 60509551:
        _hold('INSTANCE_ID')
    observed = _finite(sample.get('observed_at'), 'SAMPLE_TIME')
    age = now - observed
    limit = MAX_BASELINE_AGE_SECONDS if baseline else MAX_CURRENT_AGE_SECONDS
    if age < 0 or age > limit:
        _hold('BASELINE_STALE' if baseline else 'CURRENT_STALE')

    identity = _mapping(sample.get('model'), 'MODEL_IDENTITY')
    if set(identity) != {'model_id', 'weights_sha256', 'runtime_sha256', 'pid', 'start_ticks'}:
        _hold('MODEL_IDENTITY')
    if (not isinstance(identity.get('model_id'), str) or not 1 <= len(identity['model_id']) <= 200
            or not isinstance(identity.get('weights_sha256'), str)
            or SHA.fullmatch(identity['weights_sha256']) is None
            or not isinstance(identity.get('runtime_sha256'), str)
            or SHA.fullmatch(identity['runtime_sha256']) is None
            or identity.get('weights_sha256') != model.get('weights_sha256')
            or identity.get('runtime_sha256') != model.get('runtime_sha256')
            or identity.get('model_id') != model.get('model_id')):
        _hold('MODEL_IDENTITY')
    pid = _integer(identity.get('pid'), 'MODEL_PID', minimum=2)
    start_ticks = _integer(identity.get('start_ticks'), 'MODEL_START_TICKS', minimum=1)

    cgroup = _mapping(sample.get('cgroup'), 'CGROUP_MISSING')
    cgroup_fields = {'memory_current_bytes', 'memory_max_bytes', 'file_bytes',
                     'inactive_file_bytes', 'shmem_bytes', 'memory_psi_some_avg10',
                     'memory_psi_full_avg10', 'cpu_psi_some_avg10'}
    if set(cgroup) != cgroup_fields:
        _hold('CGROUP_FIELDS')
    current = _integer(cgroup['memory_current_bytes'], 'CGROUP_CURRENT')
    maximum = _integer(cgroup['memory_max_bytes'], 'CGROUP_MAX', minimum=1)
    if current > maximum:
        _hold('CGROUP_OVER_LIMIT')
    file_bytes = _integer(cgroup['file_bytes'], 'CGROUP_FILE')
    inactive_file = _integer(cgroup['inactive_file_bytes'], 'CGROUP_INACTIVE_FILE')
    shmem = _integer(cgroup['shmem_bytes'], 'CGROUP_SHMEM')
    if shmem > file_bytes or inactive_file > current:
        _hold('CGROUP_COUNTERS')
    pressure = {key: _finite(cgroup[key], 'CGROUP_PRESSURE') for key in
                ('memory_psi_some_avg10', 'memory_psi_full_avg10', 'cpu_psi_some_avg10')}

    process = _mapping(sample.get('process'), 'PROCESS_MISSING')
    if set(process) != {'pid', 'start_ticks', 'rss_bytes', 'pss_bytes'}:
        _hold('PROCESS_FIELDS')
    if (process.get('pid') != pid or process.get('start_ticks') != start_ticks
            or type(process.get('pid')) is not int or type(process.get('start_ticks')) is not int):
        _hold('PROCESS_IDENTITY')
    rss = _integer(process['rss_bytes'], 'PROCESS_RSS')
    pss = _integer(process['pss_bytes'], 'PROCESS_PSS')
    if pss > rss:
        _hold('PROCESS_MEMORY_COUNTERS')

    gpus = sample.get('gpus')
    if not isinstance(gpus, list) or not 1 <= len(gpus) <= 8:
        _hold('GPU_LIST')
    gpu_map = {}
    for row in gpus:
        row = _mapping(row, 'GPU_ROW')
        if set(row) != {'uuid', 'total_bytes', 'used_bytes', 'model_process_bytes', 'process_pid'}:
            _hold('GPU_FIELDS')
        uuid = row.get('uuid')
        if not isinstance(uuid, str) or not 1 <= len(uuid) <= 128 or uuid in gpu_map:
            _hold('GPU_IDENTITY')
        if row.get('process_pid') != pid or type(row.get('process_pid')) is not int:
            _hold('GPU_PROCESS_IDENTITY')
        total = _integer(row['total_bytes'], 'GPU_TOTAL', minimum=1)
        used = _integer(row['used_bytes'], 'GPU_USED')
        model_used = _integer(row['model_process_bytes'], 'GPU_MODEL_USED')
        if used > total or model_used > used:
            _hold('GPU_COUNTERS')
        gpu_map[uuid] = {'total_bytes': total, 'used_bytes': used,
                         'model_process_bytes': model_used}
    return {'observed_at': observed, 'model': dict(identity), 'cgroup': {
        'current_bytes': current, 'max_bytes': maximum, 'file_bytes': file_bytes,
        'inactive_file_bytes': inactive_file, 'shmem_bytes': shmem, **pressure},
        'process': {'rss_bytes': rss, 'pss_bytes': pss}, 'gpus': gpu_map}


def evaluate_chat_admission(snapshot, *, policy, now: float) -> dict:
    """Validate measured chat budget and report HOLD or a measured projection.

    Raw free bytes remain visible. Inactive file cache is only included in a
    projection; this function never asks the OS to reclaim or drop it. A low
    raw margin can pass only when a fresh, matching calibration plus current
    PSI and per-process VRAM measurements show the request fits. A caller may
    act on an eligible result only while holding the matching exclusive
    resource lease across this decision and inference; this pure function
    validates the lease evidence but cannot acquire or enforce that lock.
    """
    snapshot = _mapping(snapshot, 'SNAPSHOT_MISSING')
    if set(snapshot) != {'schema', 'instance_id', 'model', 'request', 'reservation',
                         'baseline', 'current', 'calibration'}:
        _hold('SNAPSHOT_FIELDS')
    if snapshot.get('schema') != SCHEMA or snapshot.get('instance_id') != 60509551:
        _hold('SNAPSHOT_SCHEMA')
    now = _finite(now, 'CLOCK')
    model = _mapping(snapshot.get('model'), 'MODEL_IDENTITY')
    if (set(model) != {'model_id', 'weights_sha256', 'runtime_sha256'}
            or not isinstance(model.get('model_id'), str)
            or SHA.fullmatch(str(model.get('weights_sha256'))) is None
            or SHA.fullmatch(str(model.get('runtime_sha256'))) is None):
        _hold('MODEL_IDENTITY')
    request = _mapping(snapshot.get('request'), 'REQUEST_MISSING')
    if set(request) != {'input_tokens', 'output_tokens', 'reservation_lease_id'}:
        _hold('REQUEST_FIELDS')
    input_tokens = _integer(request['input_tokens'], 'REQUEST_INPUT_TOKENS', minimum=1)
    output_tokens = _integer(request['output_tokens'], 'REQUEST_OUTPUT_TOKENS', minimum=1)
    reservation = _mapping(snapshot.get('reservation'), 'RESERVATION_MISSING')
    if set(reservation) != {'lease_id', 'exclusive', 'acquired_at', 'expires_at', 'active_inferences'}:
        _hold('RESERVATION_FIELDS')
    lease_id = reservation.get('lease_id')
    if not isinstance(lease_id, str) or not 1 <= len(lease_id) <= 128:
        _hold('RESERVATION_IDENTITY')
    if request.get('reservation_lease_id') != lease_id:
        _hold('RESERVATION_IDENTITY')
    if reservation.get('exclusive') is not True:
        _hold('RESERVATION_NOT_EXCLUSIVE')
    if _integer(reservation.get('active_inferences'), 'RESERVATION_ACTIVE_INFERENCES') != 0:
        _hold('RESERVATION_BUSY')
    acquired_at = _finite(reservation.get('acquired_at'), 'RESERVATION_TIME')
    expires_at = _finite(reservation.get('expires_at'), 'RESERVATION_TIME')
    if (acquired_at > now or expires_at <= now
            or expires_at <= acquired_at
            or expires_at - acquired_at > MAX_RESERVATION_TTL_SECONDS):
        _hold('RESERVATION_EXPIRED_OR_UNBOUNDED')
    baseline = _validate_sample(snapshot.get('baseline'), model=model, now=now, baseline=True)
    current = _validate_sample(snapshot.get('current'), model=model, now=now, baseline=False)
    if acquired_at > baseline['observed_at'] or current['observed_at'] > expires_at:
        _hold('RESERVATION_SAMPLE_WINDOW')
    if current['observed_at'] < baseline['observed_at']:
        _hold('SAMPLE_ORDER')
    if current['model'] != baseline['model'] or current['gpus'].keys() != baseline['gpus'].keys():
        _hold('BASELINE_IDENTITY')
    if current['cgroup']['max_bytes'] != baseline['cgroup']['max_bytes']:
        _hold('CGROUP_LIMIT_CHANGED')

    calibration = _mapping(snapshot.get('calibration'), 'CALIBRATION_MISSING')
    required = {'schema', 'model_id', 'weights_sha256', 'runtime_sha256', 'measured_at', 'sample_count',
                'max_input_tokens', 'max_output_tokens', 'peak_cgroup_delta_bytes',
                'peak_pss_delta_bytes', 'peak_gpu_delta_bytes_by_uuid'}
    if set(calibration) != required or calibration.get('schema') != CALIBRATION_SCHEMA:
        _hold('CALIBRATION_SCHEMA')
    measured_at = _finite(calibration.get('measured_at'), 'CALIBRATION_TIME')
    if not 0 <= now - measured_at <= MAX_CALIBRATION_AGE_SECONDS:
        _hold('CALIBRATION_STALE')
    if (calibration.get('model_id') != model['model_id']
            or calibration.get('weights_sha256') != model['weights_sha256']
            or calibration.get('runtime_sha256') != model['runtime_sha256']
            or type(calibration.get('sample_count')) is not int
            or calibration['sample_count'] < 3):
        _hold('CALIBRATION_IDENTITY_OR_COUNT')
    if (input_tokens > _integer(calibration.get('max_input_tokens'), 'CALIBRATION_INPUT_TOKENS', minimum=1)
            or output_tokens > _integer(calibration.get('max_output_tokens'), 'CALIBRATION_OUTPUT_TOKENS', minimum=1)):
        _hold('REQUEST_EXCEEDS_CALIBRATED_TOKENS')
    peak_cgroup = _integer(calibration.get('peak_cgroup_delta_bytes'), 'CALIBRATION_CGROUP_PEAK')
    peak_pss = _integer(calibration.get('peak_pss_delta_bytes'), 'CALIBRATION_PSS_PEAK')
    gpu_peaks = _mapping(calibration.get('peak_gpu_delta_bytes_by_uuid'), 'CALIBRATION_GPU_PEAKS')
    if set(gpu_peaks) != set(current['gpus']):
        _hold('CALIBRATION_GPU_SET')
    gpu_peaks = {uuid: _integer(value, 'CALIBRATION_GPU_PEAK') for uuid, value in gpu_peaks.items()}

    cgroup = current['cgroup']
    reclaimable = min(cgroup['inactive_file_bytes'],
                      cgroup['file_bytes'] - cgroup['shmem_bytes'],
                      cgroup['current_bytes'])
    raw_headroom = cgroup['max_bytes'] - cgroup['current_bytes']
    effective_current = cgroup['current_bytes'] - reclaimable
    ram_peak = max(peak_cgroup, peak_pss)
    projected_headroom = cgroup['max_bytes'] - effective_current - ram_peak

    policy = _mapping(policy, 'POLICY_FIELDS')
    if set(policy) != {'minimum_projected_headroom_bytes', 'minimum_gpu_free_bytes',
                       'maximum_memory_psi_avg10', 'maximum_cpu_psi_avg10'}:
        _hold('POLICY_FIELDS')
    projected_floor = _integer(policy['minimum_projected_headroom_bytes'], 'POLICY_HEADROOM', minimum=1)
    gpu_floor = _integer(policy['minimum_gpu_free_bytes'], 'POLICY_GPU_FREE', minimum=1)
    memory_psi_limit = _finite(policy['maximum_memory_psi_avg10'], 'POLICY_MEMORY_PSI')
    cpu_psi_limit = _finite(policy['maximum_cpu_psi_avg10'], 'POLICY_CPU_PSI')
    if current['cgroup']['memory_psi_some_avg10'] > memory_psi_limit or current['cgroup']['memory_psi_full_avg10'] > memory_psi_limit:
        _hold('MEMORY_PRESSURE')
    if current['cgroup']['cpu_psi_some_avg10'] > cpu_psi_limit:
        _hold('CPU_PRESSURE')
    if projected_headroom < projected_floor:
        _hold('PROJECTED_HEADROOM')

    gpu_results = {}
    for uuid, gpu in current['gpus'].items():
        free_after = gpu['total_bytes'] - gpu['used_bytes'] - gpu_peaks[uuid]
        gpu_results[uuid] = {'free_bytes': gpu['total_bytes'] - gpu['used_bytes'],
                             'measured_request_peak_bytes': gpu_peaks[uuid],
                             'projected_free_bytes': free_after}
        if free_after < gpu_floor:
            _hold('GPU_HEADROOM')

    state = 'ELIGIBLE_PROJECTED_CACHE_RECLAIM' if raw_headroom < projected_floor else 'ELIGIBLE_RAW_HEADROOM'
    return {'schema': 'NOX_CHAT_RESOURCE_DECISION_V1', 'state': state,
            'request_tokens': {'input': input_tokens, 'output': output_tokens},
            'raw_headroom_bytes': raw_headroom, 'reclaimable_file_bytes': reclaimable,
            'measured_ram_request_peak_bytes': ram_peak,
            'projected_headroom_bytes': projected_headroom,
            'minimum_projected_headroom_bytes': projected_floor,
            'baseline_to_current': {
                'cgroup_current_delta_bytes': current['cgroup']['current_bytes'] - baseline['cgroup']['current_bytes'],
                'model_pss_delta_bytes': current['process']['pss_bytes'] - baseline['process']['pss_bytes'],
                'gpu_model_process_delta_bytes': {
                    uuid: current['gpus'][uuid]['model_process_bytes'] - baseline['gpus'][uuid]['model_process_bytes']
                    for uuid in current['gpus']},
            },
            'memory_psi_some_avg10': cgroup['memory_psi_some_avg10'],
            'memory_psi_full_avg10': cgroup['memory_psi_full_avg10'],
            'reservation_expires_at': expires_at,
            'gpu': gpu_results, 'memory_reclaim_invoked': False}
