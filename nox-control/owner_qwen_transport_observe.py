#!/usr/bin/env python3
"""Finite read-only observation of the explicit current execution revision."""
import hashlib
import json
import configparser
import math
import os
from pathlib import Path
import re
import stat
import time
import types
import urllib.request

INSTALLER = Path('/root/nox/scripts/owner_qwen_revision_install.py')
INSTALLER_SHA = '4be67c1d30d9513c96a3164c02e70056c47004922bbd3398cbc5e463f820f25d'


def transport_events(raw):
    """Project bounded public transport fields; never associate logs with a PID."""
    events = []
    allowed_types = {'TimeoutError', 'ConnectionResetError', 'URLError', 'HTTPError',
                     'IncompleteRead', 'RemoteDisconnected', 'SSLEOFError', 'SSLZeroReturnError',
                     'SSLCertVerificationError', 'gaierror', 'OSError', 'BrokenPipeError',
                     'ConnectionAbortedError', 'ConnectionRefusedError', 'BlockingIOError',
                     'InterruptedError', 'SSLError', 'OTHER_EXCEPTION'}
    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError('duplicate')
            row[key] = value
        return row
    for line in raw[-65536:].split(b'\n'):
        if not 1 <= len(line) <= 4096:
            continue
        try:
            row = json.loads(line, object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        except (ValueError, UnicodeError):
            continue
        if (not isinstance(row, dict) or row.get('state') != 'PINNED_PUBLIC_BASE_STAGING'
                or row.get('transport_version') != 'NOX_QWEN_PUBLIC_TRANSPORT_V1'):
            continue
        stage = row.get('stage', 'PROGRESS')
        offset, total = row.get('bytes'), row.get('total')
        committed = row.get('committed_offset', offset)
        if (not isinstance(stage, str) or stage not in {'OPEN', 'READ', 'WRITE', 'CLOSE', 'VERIFIED', 'PROGRESS'}
                or type(offset) is not int or type(total) is not int
                or not 0 <= offset <= total <= 20 * 1024 ** 3
                or type(committed) is not int or committed != offset):
            continue
        attempt = row.get('attempt')
        if stage != 'PROGRESS' and (type(attempt) is not int or not 1 <= attempt <= 6):
            continue
        event = {'stage': stage, 'attempt': attempt if type(attempt) is int and 1 <= attempt <= 6 else None,
                 'committed_offset': offset, 'total_bytes': total}
        for key, low, high in (('http_status', 100, 599), ('errno', -65535, 65535)):
            value = row.get(key)
            event[key] = value if type(value) is int and low <= value <= high else None
        for key in ('staging_elapsed_seconds', 'io_elapsed_seconds'):
            value = row.get(key)
            event[key] = value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 7200 else None
        value = row.get('exception_type')
        event['exception_type'] = value if isinstance(value, str) and value in allowed_types else ('OTHER_EXCEPTION' if value is not None else None)
        events.append(event)
    return events[-24:]


def transport_telemetry(core, ctx):
    """Use the exact pinned window's supervisor/stdout scope, at most 64KiB."""
    result = {'transport_version': 'NOX_QWEN_PUBLIC_TRANSPORT_V1', 'may_include_prior_runs': True,
              'current_process_bound': False, 'full_weights_integrity_proven': False,
              'raw_text_exported': False, 'events': []}
    try:
        helper = ctx['helper']
        raw_config = helper.read(helper.SUPERVISOR)
        core.require(helper.digest(raw_config) == helper.SUPERVISOR_SHA, 'TRANSPORT_SUPERVISOR_PIN')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(raw_config.decode())
        name = config.get('program:' + helper.SERVICE, 'stdout_logfile', fallback='')
        core.require(name and name.upper() not in {'AUTO', 'NONE'}, 'TRANSPORT_NO_EXPLICIT_LOG_PATH')
        path = Path(name)
        core.require(path.is_absolute() and path.resolve() == path
                     and path.is_relative_to(helper.ROOT / 'logs'), 'TRANSPORT_LOG_SCOPE')
        fd = os.open(helper.plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            core.require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid(), 'TRANSPORT_LOG_TYPE')
            offset = max(0, before.st_size - 65536)
            stream.seek(offset); raw = stream.read(min(65536, before.st_size))
            after, named = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
            core.require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                         == (named.st_dev, named.st_ino) and after.st_size >= before.st_size
                         and named.st_size >= before.st_size and len(raw) == before.st_size - offset,
                         'TRANSPORT_LOG_CHANGED')
        result.update(status='BOUNDED_LOG_TELEMETRY', log_bytes=before.st_size, mtime_ns=before.st_mtime_ns,
                      tail_bytes_read=len(raw), events=transport_events(raw))
    except Exception as exc:
        value = str(exc)
        result.update(status='UNAVAILABLE', reason=value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value)
                      else 'HOLD_TRANSPORT_LOG_' + type(exc).__name__.upper())
    return result


def load(name, raw):
    module = types.ModuleType('_nox_revision_observe_' + name.removesuffix('.py'))
    module.__file__ = '/root/nox/scripts/' + name
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def main():
    if INSTALLER.is_symlink():
        raise RuntimeError('HOLD_REVISION_OBSERVER_PATH')
    raw = INSTALLER.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INSTALLER_SHA:
        raise RuntimeError('HOLD_REVISION_OBSERVER_INSTALLER_PIN')
    core = load(INSTALLER.name, raw)
    shared_raw = core.read(core.SCRIPTS / core.SHARED)
    core.require(core.digest(shared_raw) == core.PINS[core.SHARED], 'OBSERVER_VERIFIER_PIN')
    shared = core.module(core.SHARED, shared_raw)
    ctx = shared.current_context(); core.protected()
    guard_raw = core.read(core.SCRIPTS / core.GUARD)
    core.require(core.digest(guard_raw) == core.PINS['owner_qwen_revision_guard.py'], 'OBSERVER_GUARD_PIN')
    guard = core.module(core.GUARD, guard_raw)
    cfg, cfg_sha = guard.checked_config(ctx['context'], core.digest(guard_raw))
    ctx = guard.context_evidence(cfg)
    live = core.trainer(ctx)
    proof, manifest, saved = core.full_checkpoint(ctx, flags_check=lambda: None)
    binding = shared.checkpoint_binding(ctx, manifest, saved, allow_initial_anchor=True)
    activation = shared.activation_status(ctx)
    row, row_raw = core.document(guard.STATUS, 65536)
    core.require(row.get('bindings') == guard.bindings(cfg, cfg_sha, ctx), 'OBSERVER_GUARD_BINDING')
    flags = {name: {'present': (core.STATE / name).exists() or (core.STATE / name).is_symlink()}
             for name in core.FLAGS}
    for name, value in flags.items():
        if value['present']:
            flag_raw = core.read(core.STATE / name, 4096)
            value.update(bytes=len(flag_raw), sha256=core.digest(flag_raw))
    status_raw = core.read(core.SCRIPTS / 'owner_training_status.py')
    core.require(core.digest(status_raw) == core.PINS['owner_qwen_revision_status.py'], 'OBSERVER_STATUS_PIN')
    status = core.module('owner_training_status.py', status_raw).snapshot()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    health = {}
    for port in (8080, 8081, 8082):
        try:
            with opener.open('http://127.0.0.1:' + str(port) + '/health', timeout=3) as response:
                health[str(port)] = response.status
        except Exception:
            health[str(port)] = None
    witness = binding.get('witness')
    sample_age = time.time() - row['sampled_at']
    new_updates = proof['successful_total'] - 25
    actual_live = live['service']['state'] == 'RUNNING' and live['process_identity'] is not None
    state = ('RUNNING_NEW_OPTIMIZER_UPDATES_VERIFIED' if actual_live and activation['active'] and new_updates > 0
             else 'RUNNING_BOOTSTRAP_OR_FIRST_UPDATE_PENDING' if actual_live
             else 'PAUSED_OR_STOPPED_CHECKPOINT_PRESERVED')
    value = {'schema': 'NOX_QWEN_EXECUTION_REVISION_OBSERVATION_V1', 'state': state,
             'observed_at': time.time(), 'read_only': True, 'execution_revision': ctx['context'],
             'execution_binding': shared.execution_binding(ctx), 'trainer': live,
             'checkpoint': proof, 'new_successful_updates_since_revision': max(0, new_updates),
             'new_optimizer_updates_verified': activation['active'] and new_updates > 0,
             'evaluated_at_update': saved['holdout_evaluated_successful_total'],
             'evaluation_age_updates': saved['successful_total'] - saved['holdout_evaluated_successful_total'],
             'holdout_loss': saved['last_holdout_loss'],
             'evaluation_witness': {'kind': witness['kind'], 'holdout_examples': witness['holdout_examples'],
                 'evaluated_successful_total': witness['evaluated_successful_total'],
                 'state_unchanged_during_evaluation': witness['before'] == witness['after'],
                 'finished_at': witness['finished_at']} if witness else None,
             'activation': {k: activation[k] for k in ('active', 'bootstrap_pending', 'permit_sha256', 'initial_process_identity')},
             'guard': {'state': row['state'], 'sha256': core.digest(row_raw), 'age_seconds': sample_age,
                 'fresh': 0 <= sample_age <= 30, 'policy_state': row['policy_state'], 'checkpoint': row['checkpoint']},
             'flags': flags, 'disk_free_bytes': guard.disk_free(), 'chat_health': health,
             'chat_model_identity': ctx['helper'].model_identity(),
             'chat_status_reader': {k: status.get(k) for k in ('state', 'reason', 'verification_state',
                  'optimizer_steps', 'skipped_optimizer_steps', 'checkpoint_saved_verified',
                  'positive_optimizer_steps_verified', 'current_process_model_loaded_verified',
                  'current_run', 'execution_revision', 'current_execution', 'execution_binding')},
             'original_checkpoint25_retained': (core.OUTPUT / core.ANCHOR['directory']).is_dir(),
             'accepted_six_preserved': True, 'general_intelligence_improvement_proven': False,
             'chat_weights_merged_or_switched': False}
    value['transport_telemetry'] = transport_telemetry(core, ctx)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_execution_revision_observation', 'data': value},
          sort_keys=True, allow_nan=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value) else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_execution_revision_observation',
              'data': {'state': 'UNVERIFIED', 'reason': reason, 'read_only': True}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
