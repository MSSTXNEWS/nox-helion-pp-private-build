#!/usr/bin/env python3
"""One read-only observation of an explicitly sealed current Qwen1000 window.

No status/source/configuration writes, service actions, model loads or guard
ticks. Unchanged live checkpoints receive metadata reads only. New checkpoints
or an ended trainer receive at most1GiB of full file hashing within45seconds.
The optional prior pointer is a read-cost hint, never verification evidence.
"""
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
import urllib.request

ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
SCHEMA = 'NOX_QWEN_WINDOW1000_OBSERVATION_V1'
PINS = {
    'owner_training_status.py': '56ac00ee986932524fe61b996b6edde651419dcc0da028d8b6a56f342be58ae8',
    'owner_qwen_training_guard.py': '2a6f6ade1a913bf42bc921d997b83109323adf3227570cf29a0ffc61a7b2614c',
}
SIX_ACCEPTANCE = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
SIX_MANIFEST = 'bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293'
HANDOFF_SHA = '312966b352348f0ae0f403cbe84bbfa2e26f89826f285a0a865965650c7931dc'
MAX_HASH_BYTES = 1024 ** 3
ENDED = {'STOPPED', 'EXITED', 'FATAL', 'BACKOFF'}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_WINDOW_OBSERVER_' + code)


def safe(exc):
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', text) else 'HOLD_QWEN_WINDOW_OBSERVER_UNVERIFIED'


def load(name):
    path = SCRIPTS / name
    require(not any(p.is_symlink() for p in (*path.parents, path)), 'SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 * 1024 ** 2, 'SOURCE_SIZE')
        raw = stream.read(2 * 1024 ** 2 + 1)
        ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and ident(before) == ident(os.fstat(stream.fileno()))
                == ident(path.stat(follow_symlinks=False)) and hashlib.sha256(raw).hexdigest() == PINS[name], 'SOURCE_PIN')
    module = types.ModuleType('_nox_readonly_window_' + name.removesuffix('.py'))
    module.__file__ = str(path); sys.modules[module.__name__] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def previous_hint(value):
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {'directory', 'manifest_sha256'}
            and isinstance(value['directory'], str)
            and re.fullmatch('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}', value['directory'])
            and isinstance(value['manifest_sha256'], str) and re.fullmatch('[a-f0-9]{64}', value['manifest_sha256']),
            'PRIOR_POINTER_HINT')
    return dict(value)


def hash_required(pointer, service_state, prior):
    reference = prior['manifest_sha256'] if prior else SIX_MANIFEST
    return service_state in ENDED or pointer['manifest_sha256'] != reference


def full_checkpoint(status, obs, contract, lineage, pointer, metadata):
    require(0 < metadata['observed_file_bytes'] <= MAX_HASH_BYTES, 'CHECKPOINT_HASH_BUDGET')
    original = obs.read; charged = [0]; payload = [0]; deadline = time.monotonic() + 45
    def bounded(path, maximum=2 * 1024 ** 2, **kwargs):
        maximum = min(maximum, MAX_HASH_BYTES - charged[0])
        require(maximum > 0, 'CHECKPOINT_HASH_BUDGET')
        kwargs['deadline'] = min(kwargs.get('deadline') or deadline, deadline)
        raw, meta = original(path, maximum, **kwargs)
        charged[0] += meta['bytes']
        require(charged[0] <= MAX_HASH_BYTES, 'CHECKPOINT_HASH_BUDGET')
        if kwargs.get('keep') is False:
            payload[0] += meta['bytes']
        return raw, meta
    obs.read = bounded
    try:
        proof, manifest, saved = status.checkpoint(obs, contract, lineage, pointer['directory'],
                                                 pointer['manifest_sha256'], deadline)
    finally:
        obs.read = original
    require(proof['verified_bytes'] == payload[0] <= charged[0] <= MAX_HASH_BYTES, 'CHECKPOINT_HASH_ACCOUNTING')
    proof['observation_checkpoint_bytes_read'] = charged[0]
    return proof, manifest, saved


def progress(obs, process):
    path = OUTPUT / 'owner_progress.json'
    if not path.exists() and not path.is_symlink():
        return {'present': False, 'optimizer_proof': False}
    row, meta = obs.document(path)
    counts = {key: row.get(key) for key in ('successful_optimizer_steps', 'attempted_steps', 'skipped_steps')}
    require(row.get('state') == 'NATIVE_STUDENT_UPDATE_OBSERVED' and all(obs.integer(v) for v in counts.values())
            and counts['attempted_steps'] == counts['successful_optimizer_steps'] + counts['skipped_steps']
            and type(row.get('pid')) is int and row['pid'] > 0 and obs.number(row.get('time')), 'PROGRESS_COUNTERS')
    return {'present': True, **counts, 'pid': row['pid'], 'recorded_at': row['time'],
            'age_seconds': max(0, time.time() - row['time']), 'sha256': meta['sha256'],
            'matches_current_pid': bool(process and row['pid'] == process['pid']),
            'optimizer_proof': False, 'scope': 'PUBLISHED_NATIVE_TELEMETRY_ONLY'}


def policy_projection(value):
    numbers = ('last_successful_updates', 'last_evaluation_update', 'best_holdout_loss', 'regression_streak',
               'observed_distinct_evaluations', 'low_since', 'last_sample_at', 'last_free_bytes', 'latched_at',
               'checkpoint_budget_bytes', 'disk_early_threshold_bytes', 'disk_urgent_threshold_bytes',
               'disk_floor_bytes', 'evaluation_age_updates')
    result = {key: value[key] for key in numbers if key in value and (value[key] is None or
              type(value[key]) in (int, float) and math.isfinite(value[key]))}
    result.update({key: value[key] for key in ('inhibit', 'complete', 'floor_already_crossed') if type(value.get(key)) is bool})
    result['reason'] = value.get('reason') if value.get('reason') in (None, 'DISK_EARLY_MARGIN', 'EVALUATION_STALE', 'HOLDOUT_REGRESSION') else 'UNKNOWN'
    return result


def guard_projection(guard, context):
    result = {'configuration_verified': False, 'resume_admitted_now': False, 'guard_tick_called': False}
    try:
        cfg, config_sha = guard.checked_config(context, PINS['owner_qwen_training_guard.py'])
        result.update(configuration_verified=True, config_sha256=config_sha, enabled=cfg['enabled'],
                      window_admission=cfg['window_admission'])
        ctx = guard.context_evidence(cfg)
        value, state_sha = guard.previous_state(guard.bindings(cfg, config_sha, ctx))
        require(value is not None, 'GUARD_STATE_MISSING')
        sampled = value.get('sampled_at'); require(type(sampled) in (int, float) and math.isfinite(sampled), 'GUARD_TIMESTAMP')
        age = time.time() - sampled
        reason = guard.resume_block_reason(context)
        result.update(state_sha256=state_sha, state=value['state'] if value.get('state') in ('MONITORING', 'INHIBITED') else 'UNKNOWN', age_seconds=age,
                      fresh=0 <= age <= cfg['policy']['state_max_age_seconds'],
                      inhibit=value['policy_state'].get('inhibit') is True, policy_state=policy_projection(value['policy_state']),
                      resume_admitted_now=reason is None, resume_block_reason=reason)
    except Exception as exc:
        result['reason'] = safe(exc)
    return result


def handoff_projection(guard, context):
    path = ROOT / 'config/owner_qwen_media_handoff.json'
    try:
        row, raw = guard.document(path, 32768); guard.private(path)
        require(row.get('schema') == 'NOX_QWEN_MEDIA_HANDOFF_CONFIG_V1'
                and row.get('source_sha256') == HANDOFF_SHA
                and type(row.get('enabled')) is bool and type(row.get('resume_training_after_media')) is bool
                and guard.digest(guard.read(SCRIPTS / 'owner_qwen_media_handoff.py')) == HANDOFF_SHA, 'HANDOFF_CONFIG')
        return {'config_sha256': guard.digest(raw), 'enabled': row['enabled'],
                'resume_training_after_media': row['resume_training_after_media'],
                'window_admission': guard.context_shape(row['window_admission']) if row['enabled'] else None,
                'matches_current_window': row.get('window_admission') == context,
                'source_verified': True, 'full_handback_admission_executed': False}
    except Exception as exc:
        return {'source_verified': False, 'reason': safe(exc), 'full_handback_admission_executed': False}


def categorical_flags(status, obs, context):
    row = status.flags(obs, context['request'], 1000)
    path = STATE / 'TRAIN_PAUSE_REQUEST.flag'
    if path.exists() and not path.is_symlink():
        raw, _ = obs.read(path, 4096)
        allowed = ((b'NOX_QWEN_GUARD_PAUSE_V1 ', 'QWEN_GUARD'),
                   (b'NOX_QWEN_ACTIVATION_PAUSE_V1 ', 'QWEN_ACTIVATION'),
                   (b'NOX_MEDIA_CHECKPOINT_YIELD ', 'MEDIA_CHECKPOINT_YIELD'))
        row['TRAIN_PAUSE_REQUEST.flag']['category'] = next((name for prefix,name in allowed if raw.startswith(prefix)), 'OTHER_OWNER_PAUSE')
    return row


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    result = {}
    for port in (8080, 8081, 8082):
        try:
            with opener.open('http://127.0.0.1:' + str(port) + '/health', timeout=2) as response:
                result[str(port)] = response.status
        except Exception:
            result[str(port)] = None
    return result


def classify_window_state(*, live, complete, service_state, hold, cooperative_pause_verified):
    """A failure latch or FATAL Supervisor must never be disguised as a benign pause."""
    if (hold.get('owned_failure') or hold.get('owned_advance_failure')
            or service_state in ('FATAL', 'BACKOFF')):
        return 'HELD_AFTER_FAILURE'
    if live:
        return 'RUNNING_CURRENT_WINDOW1000'
    if complete:
        return 'WINDOW1000_COMPLETE_VERIFIED'
    if service_state in ENDED and cooperative_pause_verified:
        return 'CHECKPOINTED_OR_PAUSED'
    return 'ADMITTED_WINDOW1000_NOT_RUNNING'


def observe(window_context, previous_checkpoint=None):
    require(isinstance(window_context, dict), 'EXPLICIT_WINDOW_CONTEXT_REQUIRED')
    prior = previous_hint(previous_checkpoint)
    result = {'schema': SCHEMA, 'started_at': time.time(), 'read_only': True,
              'observation_completed': False, 'service_actions': 0, 'files_written': 0,
              'private_training_text_exported': False, 'base_tensor_bytes_read': 0,
              'new_window_optimizer_updates_verified': False, 'requested_window_complete': False}
    try:
        status, guard = load('owner_training_status.py'), load('owner_qwen_training_guard.py')
        context = status.context_value(window_context)
        obs = guard.module('owner_qwen_training_observe.py')
        window, helper = guard.module('owner_qwen_window_entry.py'), guard.module('owner_qwen_install_entry.py')
        sealed, pointer, argv, admitted = status.admitted(context, obs)
        require(admitted['current_context'] == context and admitted['goal'] == 1000
                and sealed.get('state') == 'WINDOW_STARTED_ACCEPTANCE_PENDING', 'CURRENT_WINDOW1000_REQUIRED')
        anchor = admitted['continuation_acceptance_anchor']
        require(anchor['acceptance_sha256'] == SIX_ACCEPTANCE and anchor['checkpoint']['manifest_sha256'] == SIX_MANIFEST,
                'ACCEPTED_SIX_ANCHOR')
        result.update(window_admission=context, admission_sha256=admitted['pointer_sha256'],
                      wrapper_sha256=admitted['wrapper_sha256'], target_successful_updates=1000,
                      historical_restart_accepted_updates=6, counter_reference_hint=prior)
        contract = obs.load_contract()
        lineage, lineage_meta = obs.document(OUTPUT / 'owner_lineage.json', status.BASELINE['lineage_file_sha256'])
        obs.lineage_proof(lineage, contract, pointer['student_profile'])
        certificate, _ = obs.document(OUTPUT / 'owner_acceptance.json', SIX_ACCEPTANCE)
        contract.verify_proof(certificate, lineage=lineage, minimum_updates=6)
        ctx = {'output': OUTPUT, 'observer': obs, 'contract': contract, 'lineage': lineage,
               'lineage_sha256': contract.canonical_sha(lineage), 'certificate': certificate}
        service = obs.service(); children = obs.trainers(argv, service)
        require(len(children) <= 1, 'MULTIPLE_TRAINERS')
        process = children[0] if len(children) == 1 and all(children[0].get(key) is True for key in
                  ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')) else None
        result.update(training_service=service, trainer_candidates=children, admitted_process=process,
                      process_identity_verified=process is not None)
        result['base_stage'] = window.process_chain(helper, service.get('pid'))
        result['base_stage']['scope'] = 'PROCESS_FD_METADATA_NOT_FULL_MODEL_OR_OPTIMIZER_PROOF'
        cp, cpraw = guard.document(OUTPUT / 'latest_checkpoint.json', 16384)
        metadata = guard.checkpoint_metadata(ctx)
        require(metadata['manifest_sha256'] == cp.get('manifest_sha256'), 'CHECKPOINT_METADATA_RACE')
        proof = manifest = saved = None
        verify = hash_required(cp, service['state'], prior)
        if verify:
            proof, manifest, saved = full_checkpoint(status, obs, contract, lineage, cp, metadata)
        result['progress'] = progress(obs, process)
        result['flags'] = categorical_flags(status, obs, context)
        result['guard'] = guard_projection(guard, context)
        result['handoff_configuration'] = handoff_projection(guard, context)
        try:
            identity = helper.model_identity()
            result['chat_identity'] = {**identity, 'matches_original': identity.get('pid') == 7637
                                      and str(identity.get('start_ticks')) == '149189867'}
        except Exception as exc:
            result['chat_identity'] = {'verified': False, 'reason': safe(exc)}
        result['chat_health'] = health()
        after_service = obs.service()
        if proof is None and after_service['state'] in ENDED:
            cp, cpraw = guard.document(OUTPUT / 'latest_checkpoint.json', 16384)
            metadata = guard.checkpoint_metadata(ctx)
            require(metadata['manifest_sha256'] == cp.get('manifest_sha256'), 'CHECKPOINT_METADATA_RACE')
            proof, manifest, saved = full_checkpoint(status, obs, contract, lineage, cp, metadata)
            verify = True
        if proof is not None:
            require(proof['successful_optimizer_steps'] == metadata['successful_updates'], 'FULL_METADATA_COUNTERS')
            result['checkpoint'] = {**metadata, 'full_files_sha256_verified': True,
                'all_checkpoint_file_hashes_verified': True,
                'verified_bytes': proof['verified_bytes'], 'verified_file_count': proof['checkpoint_file_count'],
                'observation_checkpoint_bytes_read': proof['observation_checkpoint_bytes_read'],
                'new_window_successful_updates': proof['successful_optimizer_steps'] - 6}
            result['new_window_optimizer_updates_verified'] = proof['successful_optimizer_steps'] > 6
            terminal, _ = obs.document(OUTPUT / 'owner_last_result.json')
            if terminal.get('checkpoint') == str(OUTPUT / cp['directory']):
                result['terminal'] = status.terminal(obs, contract, lineage, manifest, saved,
                                                     time.monotonic() + 5, acceptance=False)
            else:
                result['terminal'] = {'state': 'HISTORICAL_TERMINAL_NOT_LATEST_CHECKPOINT'}
        else:
            result['checkpoint'] = {**metadata, 'full_files_sha256_verified': False, 'verified_bytes': 0,
                                    'payload_verification_skipped': 'UNCHANGED_LIVE_CHECKPOINT'}
        result['checkpoint']['full_hash_trigger'] = 'ENDED_TRAINER_OR_CHANGED_POINTER' if verify else 'NONE'
        result['next_observation_hint'] = {'directory': cp['directory'], 'manifest_sha256': cp['manifest_sha256']}
        require(guard.read(OUTPUT / 'latest_checkpoint.json', 16384) == cpraw, 'LATEST_CHECKPOINT_CHANGED')
        _, _, after_argv, after_admitted = status.admitted(context, obs)
        require(after_admitted == admitted and after_argv == argv, 'ADMISSION_CHANGED')
        obs.read(OUTPUT / 'owner_lineage.json', expected=lineage_meta['sha256'])
        after_process = obs.process(process['pid']) if process else None
        live = bool(process and service == after_service and after_service['state'] == 'RUNNING'
                    and after_process and after_process.get('state') != 'Z'
                    and after_process.get('start_ticks') == process['start_ticks'])
        result.update(training_service=after_service, live_admitted_process_verified=live,
                      current_checkpoint_belongs_to_live_process=bool(proof and live
                          and (proof.get('process_identity') or {}).get('pid') == process['pid']
                          and (proof.get('process_identity') or {}).get('start_ticks') == process['start_ticks']))
        terminal = result.get('terminal', {}); hold = result['flags']['TRAIN_HOLD.flag']
        complete = bool(not live and proof and proof['successful_optimizer_steps'] == 1000
                        and terminal.get('state') == 'STUDENT_RESTART_AND_UPDATES_VERIFIED'
                        and terminal.get('independent_holdout_accepted') is True and hold.get('owned_complete'))
        result['requested_window_complete'] = complete
        result['state'] = classify_window_state(
            live=live, complete=complete, service_state=after_service['state'],
            hold=hold, cooperative_pause_verified=(
                after_service['state'] in ENDED and status.cooperative_pause(
                    terminal, result['flags'], admitted['admission_started_at'])))
        result['observation_completed'] = True
    except Exception as exc:
        result.update(state='HOLD_QWEN_WINDOW_OBSERVATION', reason=safe(exc), observation_completed=False,
                      new_window_optimizer_updates_verified=False, requested_window_complete=False)
    result['finished_at'] = time.time()
    require(len(json.dumps(result, allow_nan=False).encode()) <= 64000, 'OUTPUT_BOUND')
    return result


def main(window_context=None, previous_checkpoint=None):
    try:
        result = observe(window_context, previous_checkpoint)
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_window1000_observation', 'data': result}, allow_nan=False), flush=True)
        ok = result['observation_completed']
        print('NOX_MAINT_REPAIR_COMPLETE=' + str(ok).lower(), flush=True)
        return 0 if ok else 2
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_window1000_observation',
              'data': {'state': 'HOLD', 'reason': safe(exc), 'read_only': True, 'files_written': 0}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
