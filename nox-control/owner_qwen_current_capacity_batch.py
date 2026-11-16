#!/usr/bin/env python3
"""Read current Qwen/media evidence, then bounded1/3/6 inference if idle.

No native installation, launch, queue edit or flag write. Frozen d7/3955/fce
remain unchanged. Only this private process replaces d7's maintenance EX lease
with SH so the existing live1000 guard can keep sampling under its own SH lease.
"""
import base64
from contextlib import contextmanager
import fcntl
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

PINS = {
    'owner_qwen_current_observe.py': '8496d3ace03e1e5e08f2f185145dcd1257095038d67060a115ec3a115b523040',
    'owner_qwen_window_observe_entry.py': '3955572f13d6c53727b85a6ca41287b3648cb21332268bbd783e3629c390e32d',
    'owner_qwen_media_retry_observe.py': 'fce01bca74751ee01a993eba7aa8874b4fc58cb2a8b9656212d0d17923ad4018',
    'owner_capacity_current_load_entry.py': 'd7e2dc220af614cf1cfe5f8341a469e0d17e615d40c7165fc53f712c931ce6c3',
    'owner_capacity_measure_entry.py': '6fafe435ac6d93417fbce76ec38c74c65e016d38e223d7e8ec5084444f9592e3',
    'owner_capacity_probe.py': '36e18d2f37dc8eb39195659e3a1082711bead921eb15150158ef883928a6c4f0',
}
ROOT = Path('/root/nox')
DISPATCHER = ROOT / 'scripts/nox_dispatcher_t855u.py'
DISPATCHER_SHA = '89b359b49fe37e219629574eed5ae7ee3d8e756fa5feb64f5274d68b1eccb2bb'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
GUARD_SHA = '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c'
WINDOW_CONTEXT = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
                  'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
PRIOR_CHECKPOINT = {'directory': 'checkpoint-u00000006-a00000006-g01794804416868029665',
                    'manifest_sha256': 'bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293'}
FAIR_CONTEXT = {'request': '6908510964',
                'source_sha': 'acf229e494d41a9e9cac646b0a0887bbb2deb81c',
                'receipt_sha256': 'be8bc8eda89ffc1790fc22ea360f06a56b4530682d869812623b4f5009d61b1e'}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(exc):
    reason = str(exc)
    return reason if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', reason) else 'HOLD_CURRENT_CAPACITY_UNVERIFIED'


def emit(kind, row):
    raw = json.dumps({'kind': kind, 'data': row}, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    require(len(raw.encode()) <= 160000, 'HOLD_CURRENT_CAPACITY_OUTPUT_BOUND')
    print('NOX_MAINT_REPAIR=' + raw, flush=True)


def prepared():
    modules = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and len(value) <= 400000, 'HOLD_CURRENT_CAPACITY_BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 262144 and digest(raw) == pin, 'HOLD_CURRENT_CAPACITY_BUNDLE_PIN')
        module = types.ModuleType('_nox_capacity_batch_' + name.removesuffix('.py'))
        module.__file__ = '/root/nox/scripts/' + name
        sys.modules[module.__name__] = module
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        module.BUNDLE = BUNDLE
        modules[name] = module
    alias = modules['owner_qwen_current_observe.py']
    training = modules['owner_qwen_window_observe_entry.py']
    media = modules['owner_qwen_media_retry_observe.py']
    capacity = modules['owner_capacity_current_load_entry.py']
    require(alias.ENTRY == 'owner_qwen_window_observe_entry.py'
            and alias.ENTRY_SHA == PINS[alias.ENTRY] and alias.WINDOW_CONTEXT == WINDOW_CONTEXT
            and training.PINS['owner_qwen_training_guard.py'] == GUARD_SHA
            and media.RUNTIME_SHA == RUNTIME_SHA and tuple(capacity.REQUESTED) == (1, 3, 6),
            'HOLD_CURRENT_CAPACITY_FROZEN_CONTRACT')
    # Resolves nested definition-only pins before any model request.
    capacity.helpers()
    return training, media, capacity


@contextmanager
def shared_existing_lease(core):
    path = core.checked(core.STATE / 'owner_maintenance.lock')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022, 'HOLD_CURRENT_CAPACITY_LEASE_FILE')
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('WAIT_CURRENT_CAPACITY_OWNER_MAINTENANCE') from None
        named = path.stat(follow_symlinks=False)
        require((named.st_dev, named.st_ino) == (info.st_dev, info.st_ino), 'HOLD_CURRENT_CAPACITY_LEASE_CHANGED')
        yield
    finally:
        os.close(fd)


def dispatcher_scope(core):
    require(digest(core.read(DISPATCHER, 262144)) == DISPATCHER_SHA, 'HOLD_CURRENT_CAPACITY_DISPATCHER_CHANGED')
    require(digest(core.read(ROOT / 'scripts/owner_media_runtime.py', 262144)) == RUNTIME_SHA,
            'HOLD_CURRENT_CAPACITY_MEDIA_RUNTIME_CHANGED')
    path = core.STATE / ('owner_media_inbox_fair_' + FAIR_CONTEXT['request'] + '.json')
    raw = core.read(path, 262144)
    require(digest(raw) == FAIR_CONTEXT['receipt_sha256'], 'HOLD_CURRENT_CAPACITY_FAIR_RECEIPT')
    row = json.loads(raw)
    require(row.get('schema') == 'NOX_MEDIA_INBOX_FAIR_INSTALL_V1'
            and row.get('request') == FAIR_CONTEXT['request']
            and row.get('source_sha') == FAIR_CONTEXT['source_sha']
            and row.get('dispatcher_after_sha256') == DISPATCHER_SHA
            and row.get('state') == 'MEDIA_INBOX_FAIR_AND_REVIEWER_TRUTH_BOUND'
            and row.get('training_identity_preserved') is True
            and row.get('current_student_process_preserved') is True,
            'HOLD_CURRENT_CAPACITY_FAIR_SOURCE_PROOF')
    return {'dispatcher_sha256': DISPATCHER_SHA, 'runtime_sha256': RUNTIME_SHA,
            'fair_receipt_sha256': FAIR_CONTEXT['receipt_sha256']}


def fresh_guard(guard, service_state, *, expected=None):
    """Read only: no tick, pause, config write, or nested maintenance flock."""
    old_deadline = getattr(guard._IO_DEADLINE, 'value', None)
    guard._IO_DEADLINE.value = time.monotonic() + 4
    try:
        context = None
        if expected is None:
            config, config_sha = guard.checked_config(WINDOW_CONTEXT, GUARD_SHA)
            context = guard.context_evidence(config)
            expected = guard.bindings(config, config_sha, context)
            max_age = config['policy']['state_max_age_seconds']
        else:
            max_age = 30
        row, state_sha = guard.previous_state(expected)
        require(row is not None, 'WAIT_CURRENT_CAPACITY_GUARD_STATE_MISSING')
        sampled = row.get('sampled_at')
        require(type(sampled) in (int, float) and math.isfinite(sampled)
                and 0 <= time.time() - sampled <= min(30, max_age), 'WAIT_CURRENT_CAPACITY_GUARD_STALE')
        policy = row.get('policy_state') or {}
        require(row.get('state') in ('MONITORING', 'INHIBITED') and type(policy.get('inhibit')) is bool,
                'HOLD_CURRENT_CAPACITY_GUARD_STATE')
        if context is not None:
            require(guard.checkpoint_metadata(context) == row.get('checkpoint'),
                    'WAIT_CURRENT_CAPACITY_GUARD_CHECKPOINT_PENDING')
        if service_state in ('RUNNING', 'STARTING'):
            require(row['state'] == 'MONITORING' and policy['inhibit'] is False,
                    'WAIT_CURRENT_CAPACITY_GUARD_INHIBITED')
        return expected, {'state_sha256': state_sha, 'state': row['state'], 'inhibit': policy['inhibit'],
                          'sample_age_seconds': round(time.time() - sampled, 3), 'guard_tick_called': False}
    finally:
        guard._IO_DEADLINE.value = old_deadline


def configure_private_capacity(capacity, guard):
    """Only this loaded d7 module changes; installed and bundle bytes stay exact."""
    original_helpers, original_gate, original_series = capacity.helpers, capacity.gate, capacity.run_series
    observed = {'expected_guard_bindings': None, 'training_service': None, 'guard_samples': 0,
                'during_burst_guard_samples': 0, 'captured_result': None}

    def helpers():
        core, probe = original_helpers()
        services = core.services()
        engine = (services.get('nox-media-comfyui') or {}).get('state')
        require(engine in ('RUNNING', 'STOPPED', 'EXITED'), 'WAIT_CURRENT_CAPACITY_MEDIA_SERVICE_UNVERIFIED')
        # All job records are monitored; the real queue is also checked when
        # its service is running. Every case rechecks current service states.
        core.monitor_media(probe, {'media_engine_state': engine})
        original_resources, original_resource_gate = probe.resources, probe.resource_gate
        cached = {'until': 0.0, 'reason': None}

        def resources():
            value = original_resources()
            if observed['expected_guard_bindings'] is not None and time.monotonic() >= cached['until']:
                cached['until'] = time.monotonic() + 1
                try:
                    fresh_guard(guard, observed['training_service']['state'], expected=observed['expected_guard_bindings'])
                    observed['during_burst_guard_samples'] += 1
                except Exception as exc:
                    cached['reason'] = safe(exc)
            value['current_qwen_guard_reason'] = cached['reason']
            return value

        def resource_gate(value, baseline=None):
            original_resource_gate(value, baseline)
            if value.get('current_qwen_guard_reason'):
                raise probe.Hold(value['current_qwen_guard_reason'])

        probe.resources, probe.resource_gate = resources, resource_gate
        return core, probe

    def gate(core, probe, baseline=None):
        row = original_gate(core, probe, baseline)
        source = dispatcher_scope(core)
        expected, sampled = fresh_guard(guard, row['training_service']['state'])
        observed.update(expected_guard_bindings=expected, training_service=row['training_service'])
        observed['guard_samples'] += 1
        row.update(qwen_guard=sampled, current_dispatcher=source,
                   maintenance_lease='SHARED_READ_ONLY_GUARD_TICK_COMPATIBLE')
        return row

    def series(core, probe, result):
        result['maintenance_lease_mode'] = 'SHARED_READ_ONLY'
        result['dispatcher_guard_sampling_allowed'] = True
        result['foreground_isolation_proven'] = False
        result['model_slots_are_total_concurrency'] = True
        try:
            return original_series(core, probe, result)
        finally:
            observed['captured_result'] = result

    capacity.helpers, capacity.gate, capacity.run_series = helpers, gate, series
    capacity.existing_lease = shared_existing_lease
    return observed


def main():
    result = {'schema': 'NOX_CURRENT_QWEN_MEDIA_CAPACITY_BATCH_V1', 'started_at': time.time(),
              'state': 'OBSERVATION_PENDING', 'source_pins': PINS, 'window_admission': WINDOW_CONTEXT,
              'service_actions': 0, 'files_written': 0, 'training_flags_written': False,
              'jobs_submitted': 0, 'queue_changes': False, 'capacity_attempted': False,
              'normal_mode_proven': False, 'task_boost_mode_proven': False, 'global_maximum_proven': False}
    code = 2
    try:
        training, media, capacity = prepared()
        observed_training = training.observe(dict(WINDOW_CONTEXT), dict(PRIOR_CHECKPOINT))
        emit('qwen_window1000_observation', observed_training)
        observed_media = media.snapshot()
        source = observed_media.get('dispatcher_source') or {}
        if (source.get('file') or {}).get('sha256') == DISPATCHER_SHA:
            observed_media['batch_known_dispatcher_profile'] = 'QWEN_GUARD_WITH_FAIR_MEDIA_AND_TRUTH_OVERLAY'
        emit('qwen_media_retry_observation', observed_media)
        require(observed_training.get('observation_completed') is True,
                'WAIT_CURRENT_CAPACITY_TRAINING_OBSERVATION_UNVERIFIED')
        # No completion is inferred from media observer.main() returning0.
        # The d7 gate independently requires all jobs and the real Comfy queue idle.
        guard = training.load('owner_qwen_training_guard.py')
        observation = configure_private_capacity(capacity, guard)
        result['capacity_attempted'] = True
        code = capacity.main()
        captured = observation['captured_result'] or {}
        measured = captured.get('measured') or {}
        result.update(state='CURRENT_LOAD_SWEEP_RECORDED' if code == 0 else 'CURRENT_LOAD_PARTIAL_OR_WAITING',
                      capacity_state=captured.get('state'), capacity_reason=captured.get('reason'),
                      guard_samples_before_cases=observation['guard_samples'],
                      guard_samples_during_bursts=observation['during_burst_guard_samples'],
                      tested_concurrencies=[row.get('concurrency') for row in captured.get('cases', [])],
                      sweep_complete=measured.get('sweep_complete') is True,
                      all_fixture_quality_passed=measured.get('all_fixture_quality_passed') is True,
                      measured_scope='CURRENT_LOAD_SHORT_PUBLIC_FIXTURES_ONLY',
                      maintenance_lease='SHARED_READ_ONLY_NO_FLAGS')
    except Exception as exc:
        result.update(state='OBSERVATIONS_PARTIAL_OR_HELD', reason=safe(exc))
    result['finished_at'] = time.time()
    emit('current_qwen_media_capacity_batch', result)
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if code == 0 else 'false'), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
