#!/usr/bin/env python3
"""Bounded, read-only failure diagnosis for the explicit installed revision.

Reuse the frozen technical-log sanitizer. No training/control calls, writes,
checkpoint payload hashes, model imports, raw logs, prompts or credentials.
"""
import ast
import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import time
import types
import urllib.request

INSTALLER = Path('/root/nox/scripts/owner_qwen_revision_install.py')
INSTALLER_SHA = '711912d596ce6c8e806d4ee16d9d5a1fae41c89b527825b13cf2c6788a17975a'
SHARED_SHA = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
REFERENCE = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
             'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
OPERATION_SHA = '2955b5de09412fa919d0f025a62078bc4cf1ff7f3ef14e6adaf8db065c87a5f3'
STUDENT_SHA = 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c'
DESCRIPTOR_SHA = '9d3c9ce7bc612d5c9fc5db361ee36248bb50a6f1d6935702fdc80c244bc72470'
HOLD_SHA = '536ba522ae83bfb052998a175993e94701c1cbc24d93a92f0107377858644d38'
LOG_LIMIT = 65536
DIRECTORY_LIMIT = 64
TERMINAL_FIELDS = ('state', 'successful_optimizer_steps', 'new_successful_optimizer_steps',
                   'attempted_steps', 'skipped_steps', 'reload_verified', 'independent_holdout_accepted')
FRESH_CHECKPOINT = {
    'directory': 'checkpoint-u00000025-a00000025-g01794828669565488412',
    'manifest_sha256': 'c206cd9e7a1bacdc5d6dae261d7d775f41bd8f8d2a4986c7464a1b60cacdbf49',
    'student_state_sha256': 'f5c1a30c1afe092a01d46c533692968efc54f38ce96dda4a956c48074ee55f7a',
    'prior_full_file_verification_observation_request': '6915435324',
}
STATES = {'RUNNING', 'STARTING', 'STOPPING', 'STOPPED', 'EXITED', 'FATAL', 'BACKOFF', 'UNKNOWN',
    'FINALIZE_PREFLIGHT', 'BOOTSTRAP_LOADING_PENDING', 'REAL_EVALUATION_SAME_COUNTER_CHECKPOINT_VERIFIED',
    'EVALUATION_ACCEPTED_ORDINARY_GUARD_PENDING', 'EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED',
    'CHECKPOINT_PAUSE_REQUESTED', 'EXISTING_FLAG_PRESERVED', 'NOT_CONFIRMED', 'NO_BOUND_CONTEXT',
    'NATIVE_STUDENT_UPDATE_OBSERVED', 'NATIVE_EXECUTION_EVALUATION_CHECKPOINTED',
    'EXISTING_TRAINER_HOLD_OR_PAUSE', 'MANUAL_OWNER_STOP', 'CONTROLLED_PROCESS_YIELD',
    'STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED', 'STUDENT_RESTART_AND_UPDATES_VERIFIED'}
EXCEPTIONS = {'RuntimeError', 'ValueError', 'TypeError', 'KeyError', 'OSError', 'FileNotFoundError',
              'PermissionError', 'TimeoutError', 'BlockingIOError', 'AttributeError', 'Hold',
              'MemoryError', 'JSONDecodeError', 'ImportError', 'ModuleNotFoundError'}


class DiagnosticDeadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_REVISION_DIAGNOSTIC_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and abs(value) <= 10 ** 20 else None


def category(value):
    if isinstance(value, str) and (value in STATES or value in EXCEPTIONS
            or re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', value)):
        return value
    return None


def safe(exc):
    return category(str(exc)) or ('HOLD_QWEN_REVISION_DIAGNOSTIC_' + type(exc).__name__.upper())


def process(value):
    if not isinstance(value, dict):
        return None
    out = {key: value[key] for key in ('pid', 'ppid', 'start_ticks', 'starttime')
           if type(value.get(key)) is int and 0 < value[key] < 10 ** 18}
    if isinstance(value.get('start_ticks'), str) and re.fullmatch('[0-9]{1,20}', value['start_ticks']):
        out['start_ticks'] = value['start_ticks']
    if isinstance(value.get('boot_id'), str) and re.fullmatch('[a-f0-9-]{36}', value['boot_id']):
        out['boot_id'] = value['boot_id']
    return out


def trainer(value):
    if not isinstance(value, dict):
        return None
    service = value.get('service') or {}
    return {'service': {'state': category(service.get('state')), 'pid': number(service.get('pid'))},
            'process_identity': process(value.get('process_identity'))}


def record(value):
    out = {key: category(value.get(key)) for key in ('state', 'reason') if key in value}
    out.update({key: number(value.get(key)) for key in ('started_at', 'finished_at') if key in value})
    if 'trainer' in value:
        out['trainer'] = trainer(value['trainer'])
    if type(value.get('optimizer_permission_issued')) is bool:
        out['optimizer_permission_issued'] = value['optimizer_permission_issued']
    pause = value.get('checkpoint_pause')
    if isinstance(pause, dict):
        out['checkpoint_pause'] = {key: category(pause.get(key)) for key in ('state', 'reason') if key in pause}
        if isinstance(pause.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', pause['sha256']):
            out['checkpoint_pause']['sha256'] = pause['sha256']
    return out


def progress(value, binding):
    out = {'state': category(value.get('state')),
           'execution_binding_matches_current': value.get('execution_binding') == binding}
    out.update({key: number(value.get(key)) for key in ('pid', 'time', 'successful_optimizer_steps',
        'new_successful_optimizer_steps', 'attempted_steps', 'skipped_steps', 'holdout_evaluated_successful_total') if key in value})
    if 'process_identity' in value:
        out['process_identity'] = process(value['process_identity'])
    for key in ('reload_verified', 'independent_holdout_accepted'):
        if type(value.get(key)) is bool:
            out[key] = value[key]
    return out


def section(function):
    try:
        return function()
    except FileNotFoundError:
        return {'present': False}
    except Exception as exc:
        return {'observation': 'HELD', 'reason': safe(exc)}


def json_record(core, path, projector):
    value, raw = core.document(path, 2 * 1024 ** 2)
    return {'present': True, 'sha256': core.digest(raw), **projector(value)}


def flag(core, name, request):
    path = core.STATE / name
    if not path.exists() and not path.is_symlink():
        return {'present': False}
    before = path.stat(follow_symlinks=False)
    raw = core.read(path, 4096)
    require(core.ident(before) == core.ident(path.stat(follow_symlinks=False)), 'FLAG_CHANGED')
    result = {'present': True, 'mtime_ns': before.st_mtime_ns, 'bytes': len(raw), 'sha256': core.digest(raw), 'ownership': 'OTHER_OR_UNRECOGNIZED'}
    if name == 'TRAIN_HOLD.flag':
        for suffix, code in (('FAILED', 'OWNED_CURRENT_WINDOW_FAILURE'), ('COMPLETE', 'OWNED_CURRENT_WINDOW_COMPLETE')):
            expected = ('OWNER_QWEN_WINDOW_' + suffix + ' request=' + request + ' goal=1000\n').encode()
            if raw == expected:
                result['ownership'] = code
    if name == 'TRAIN_PAUSE_REQUEST.flag':
        match = re.fullmatch(rb'NOX_QWEN_EXECUTION_REVISION_PAUSE request=' + request.encode()
                             + rb' reason=((?:HOLD|WAIT)_[A-Z0-9_]{1,150})\n', raw)
        if match:
            result.update(ownership='OWNED_CURRENT_REVISION_PAUSE', reason=match[1].decode('ascii'))
        elif re.fullmatch(rb'NOX_MEDIA_CHECKPOINT_YIELD [a-f0-9]{32}\n', raw):
            result['ownership'] = 'MEDIA_TOKEN_FORMAT_ONLY_OWNERSHIP_NOT_PROVEN'
    return result


def core_module():
    require(not any(p.is_symlink() for p in (*INSTALLER.parents, INSTALLER)), 'INSTALLER_PATH')
    fd = os.open(INSTALLER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 < before.st_size <= 131072, 'INSTALLER_FILE')
        raw = stream.read(131073)
        ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and ident(before) == ident(os.fstat(stream.fileno()))
                == ident(INSTALLER.stat(follow_symlinks=False)) and digest(raw) == INSTALLER_SHA, 'INSTALLER_PIN')
    value = types.ModuleType('_nox_qwen_revision_readonly_diagnostic'); value.__file__ = str(INSTALLER)
    exec(compile(raw, str(INSTALLER), 'exec'), value.__dict__)
    return value


def health():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    result = {}
    for port in (8080, 8081, 8082):
        try:
            with opener.open('http://127.0.0.1:' + str(port) + '/health', timeout=3) as response:
                result[str(port)] = response.status
        except Exception:
            result[str(port)] = None
    return result


def absence_of_finalizer_and_activation(core, area):
    """Two bounded snapshots establish absence; no guessed finalizer receipt."""
    path = core.plain(area)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISDIR(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022, 'ATTEMPT_DIRECTORY')
        count = 0
        with os.scandir(fd) as entries:
            for row in entries:
                count += 1
                require(count <= DIRECTORY_LIMIT, 'ATTEMPT_DIRECTORY_BOUND')
                require(not row.name.startswith('finalize-'), 'UNREVIEWED_FINALIZER_PRESENT')
                require(row.name != 'activation.json', 'ACTIVATION_PRESENT')
        require(core.ident(before) == core.ident(os.fstat(fd))
                == core.ident(path.stat(follow_symlinks=False)), 'ATTEMPT_DIRECTORY_CHANGED')
        return {'finalizer_receipts_absent': True, 'activation_file_absent': True,
                'entries_observed': count, 'directory_identity_sha256': digest(core.encode(core.ident(before)))}
    finally:
        os.close(fd)


def allowed_terminal_codes(student, verifier):
    require(digest(student) == STUDENT_SHA and digest(verifier) == SHARED_SHA, 'LOG_MARKER_SOURCE_PIN')
    student_tree = ast.parse(student); verifier_tree = ast.parse(verifier)
    allowed = {node.value for tree in (student_tree, verifier_tree) for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)
               and re.fullmatch('HOLD_[A-Z0-9_]{1,150}', node.value)}
    # The exact shared require() raises this prefix plus its literal second
    # argument. Its hash is checked before deriving any permitted category.
    require_node = next(node for node in verifier_tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'require')
    prefixes = {node.value for node in ast.walk(require_node)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    require(prefixes == {'HOLD_QWEN_REVISION_'}, 'VERIFIER_REQUIRE_PREFIX')
    allowed.update('HOLD_QWEN_REVISION_' + node.args[1].value for node in ast.walk(verifier_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'require'
        and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str) and re.fullmatch('[A-Z0-9_]{1,100}', node.args[1].value))
    allowed.update(('HOLD_MEMFD_TRANSPORT_OPEN_FAILED', 'HOLD_MEMFD_TRANSPORT_READ_FAILED'))
    return allowed


def terminal_summary(row, allowed):
    if not isinstance(row, dict) or not isinstance(row.get('state'), str) or row['state'] not in allowed:
        return None
    if set(row) == {'state', 'native_success_claimed'} and row['native_success_claimed'] is False:
        return row
    if set(row) != set(TERMINAL_FIELDS):
        return None
    counters = ('successful_optimizer_steps', 'new_successful_optimizer_steps', 'attempted_steps', 'skipped_steps')
    if not all(type(row.get(key)) is int and 0 <= row[key] <= 10**9 for key in counters):
        return None
    if (not all(type(row.get(key)) is bool for key in ('reload_verified', 'independent_holdout_accepted'))
            or row['attempted_steps'] != row['successful_optimizer_steps'] + row['skipped_steps']
            or row['new_successful_optimizer_steps'] > row['successful_optimizer_steps']):
        return None
    return row


def parse_terminal(raw, allowed):
    """Only the two exact terminal shapes emitted by pinned ce7 are accepted."""
    lines = [line for line in raw.split(b'\n') if line.strip()]
    codes = []; last = None
    for index, line in enumerate(lines):
        if len(line) > 4096:
            continue
        try:
            def unique(items):
                value = {}
                for key, item in items:
                    require(key not in value, 'DUPLICATE_LOG_KEY'); value[key] = item
                return value
            row = json.loads(line, object_pairs_hook=unique,
                             parse_constant=lambda _: require(False, 'NONFINITE_LOG'))
        except (ValueError, UnicodeError, RuntimeError):
            continue
        summary = terminal_summary(row, allowed)
        if summary is not None:
            codes.append(summary['state'])
            if index == len(lines) - 1:
                last = summary
    return {'terminal_codes': list(dict.fromkeys(codes))[-8:],
            'last_nonempty_line_terminal_code': last['state'] if last else None,
            'last_nonempty_line_terminal_summary': last}


def terminal_receipt(core, ctx, binding, expected_process, allowed):
    value, raw = core.document(ctx['output'] / 'owner_last_result.json', 2 * 1024**2)
    summary = terminal_summary({key: value.get(key) for key in TERMINAL_FIELDS}, allowed)
    identity = value.get('process_identity')
    bound = bool(summary is not None and value.get('execution_binding') == binding
        and identity == expected_process and process(identity) == identity
        and value.get('checkpoint') == str(ctx['output'] / FRESH_CHECKPOINT['directory'])
        and value.get('checkpoint_manifest_sha256') == FRESH_CHECKPOINT['manifest_sha256']
        and value.get('successful_optimizer_steps') == 25 and value.get('attempted_steps') == 25
        and value.get('skipped_steps') == 0 and value.get('new_successful_optimizer_steps') == 0
        and value.get('reload_verified') is True and value.get('holdout_finite') is True
        and value.get('holdout_evaluated_successful_total') == 25)
    return {'present': True, 'sha256': core.digest(raw), **progress(value, binding),
        'terminal_summary': summary, 'current_process_and_known_checkpoint_bound': bound,
        'known_checkpoint_manifest_sha256': FRESH_CHECKPOINT['manifest_sha256'],
        'checkpoint_payload_read_in_this_diagnostic': False,
        'prior_full_file_verification_observation_request': FRESH_CHECKPOINT['prior_full_file_verification_observation_request']}


def causal_logs(core, ctx, start, allowed):
    helper = ctx['helper']
    raw_config = helper.read(helper.SUPERVISOR)
    require(helper.digest(raw_config) == helper.SUPERVISOR_SHA, 'LOG_SUPERVISOR_PIN')
    config = configparser.ConfigParser(interpolation=None); config.read_string(raw_config.decode())
    rows = []
    for stream in ('stdout', 'stderr'):
        name = config.get('program:' + helper.SERVICE, stream + '_logfile', fallback='')
        require(name and name.upper() not in {'AUTO', 'NONE'}, 'LOG_EXPLICIT_PATH')
        path = Path(name)
        require(path.is_absolute() and path.resolve() == path and path.is_relative_to(helper.ROOT / 'logs'), 'LOG_SCOPE')
        try:
            fd = os.open(helper.plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            rows.append({'stream': stream, 'present': False}); continue
        with os.fdopen(fd, 'rb') as handle:
            before = os.fstat(handle.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid(), 'LOG_TYPE')
            offset = max(0, before.st_size - LOG_LIMIT)
            handle.seek(offset); raw = handle.read(min(LOG_LIMIT, before.st_size))
            require(core.ident(before) == core.ident(os.fstat(handle.fileno()))
                    == core.ident(path.stat(follow_symlinks=False)) and len(raw) == before.st_size - offset, 'LOG_RACE')
        summary = ctx['window'].safe_log_summary(raw)
        summary['hold_codes'] = [code for code in summary['hold_codes'] if code in allowed]
        summary['safe_events'] = [row for row in summary['safe_events']
            if row['state'] == 'PINNED_PUBLIC_BASE_STAGING' or row['state'] in allowed]
        rows.append({'stream': stream, 'present': True, 'log_bytes': before.st_size,
            'mtime_ns': before.st_mtime_ns, 'tail_bytes_read': len(raw), 'tail_sha256': digest(raw),
            'modified_during_current_attempt': start <= before.st_mtime_ns / 1e9 <= time.time(),
            'per_record_process_identity_bound': False, **summary, **parse_terminal(raw, allowed)})
    return rows


def guard_metadata(core, ctx, flags):
    raw = core.read(core.SCRIPTS / core.GUARD)
    require(core.digest(raw) == core.PINS['owner_qwen_revision_guard.py'], 'GUARD_PIN')
    guard = core.module(core.GUARD, raw)
    cfg, cfg_sha = guard.checked_config(REFERENCE, core.digest(raw))
    row, row_raw = core.document(guard.STATUS, 65536)
    expected = guard.bindings(cfg, cfg_sha, ctx)
    require(row.get('bindings') == expected, 'GUARD_CURRENT_BINDINGS')
    policy = row.get('policy_state')
    require(isinstance(policy, dict) and type(policy.get('inhibit')) is bool, 'GUARD_POLICY')
    pause = flags['TRAIN_PAUSE_REQUEST.flag']
    if pause.get('present') is True and policy['inhibit'] is True:
        raw_pause = core.read(core.STATE / 'TRAIN_PAUSE_REQUEST.flag', 4096)
        if raw_pause == guard.pause_token(row) and core.digest(raw_pause) == pause.get('sha256'):
            pause.update(ownership='OWNED_CURRENT_GUARD_PAUSE', reason=policy.get('reason'),
                         bindings_sha256=core.digest(guard.encode(expected)))
    return {'sha256': core.digest(row_raw), 'config_sha256': cfg_sha,
        'state': row.get('state') if row.get('state') in {'BOOTSTRAP_EVALUATION', 'INHIBITED', 'MONITORING'} else None,
        'sampled_at': number(row.get('sampled_at')), 'bindings': expected,
        'bindings_sha256': core.digest(guard.encode(expected)),
        'policy_state': {'inhibit': policy['inhibit'],
            'reason': policy.get('reason') if policy.get('reason') in guard.REASONS else None,
            **{key: number(policy.get(key)) for key in ('latched_at', 'best_holdout_loss',
                'regression_streak', 'last_evaluation_update', 'last_successful_updates', 'evaluation_age_updates')}},
        'guard_tick_called': False}


def primary_failure(logs, flags, start, last_result):
    hold = flags['TRAIN_HOLD.flag']; pause = flags['TRAIN_PAUSE_REQUEST.flag']
    stdout = next((row for row in logs if row['stream'] == 'stdout'), {})
    code = stdout.get('last_nonempty_line_terminal_code')
    later_owned_pause = bool(pause.get('ownership') in {'OWNED_CURRENT_GUARD_PAUSE', 'OWNED_CURRENT_REVISION_PAUSE'}
        and type(pause.get('mtime_ns')) is int and type(hold.get('mtime_ns')) is int
        and pause['mtime_ns'] >= hold['mtime_ns'])
    times_bound = bool(stdout.get('modified_during_current_attempt') is True
        and hold.get('ownership') == 'OWNED_CURRENT_WINDOW_FAILURE' and hold.get('sha256') == HOLD_SHA
        and (pause.get('present') is False or later_owned_pause) and type(hold.get('mtime_ns')) is int
        and start <= stdout['mtime_ns'] / 1e9 <= hold['mtime_ns'] / 1e9 + 1
        and abs(hold['mtime_ns'] - stdout['mtime_ns']) <= 120 * 10 ** 9)
    summary = stdout.get('last_nonempty_line_terminal_summary')
    receipt_bound = bool(last_result.get('current_process_and_known_checkpoint_bound') is True
                         and last_result.get('terminal_summary') == summary and summary is not None)
    record_bound = bool(summary and (set(summary) == {'state', 'native_success_claimed'} or receipt_bound))
    proved = times_bound and record_bound
    return {'code': code if proved else None,
        'terminal_record_observed': code is not None,
        'current_window_time_and_owned_flag_bound': times_bound,
        'terminal_receipt_current_process_bound': receipt_bound,
        'optimizer_permission_wait_timeout_observed': proved and receipt_bound
            and code == 'HOLD_QWEN_REVISION_WAIT_OPTIMIZER_PERMISSION_TIMEOUT',
        'transport_budget_exhaustion_observed': proved and code == 'HOLD_MEMFD_TRANSPORT_DEADLINE',
        'scope': 'EXACT_FINAL_STDOUT_SHAPE_CURRENT_TERMINAL_RECEIPT_AND_OWNED_WINDOW_FAILURE',
        'per_record_process_identity_bound': False,
        'cause_inferred_from_elapsed_time_only': False}


def snapshot():
    core = core_module(); raw = core.read(core.SCRIPTS / core.SHARED)
    require(core.digest(raw) == SHARED_SHA == core.PINS[core.SHARED], 'SHARED_PIN')
    shared = core.module(core.SHARED, raw); ctx = shared.current_context(REFERENCE); core.protected()
    require(ctx['context'] == REFERENCE and ctx['execution']['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA,
            'EXPLICIT_CURRENT_CONTEXT')
    area = core.STATE / 'owner_qwen_execution_revisions' / REFERENCE['request']
    require(ctx['execution']['directory'] == area, 'AREA_SCOPE')
    require(ctx['execution']['runtime_entry_sha256'] == STUDENT_SHA
            and ctx['execution']['descriptor_sha256'] == DESCRIPTOR_SHA, 'ATTEMPT_SOURCE_BINDING')
    live = core.trainer(ctx); activation_value = shared.activation_status(ctx)
    require(live['service']['state'] == 'FATAL' and live['service'].get('pid') is None
            and live['process_identity'] is None and activation_value['active'] is False, 'STOPPED_CURRENT_ATTEMPT')
    binding = shared.execution_binding(ctx)
    result = {'schema': 'NOX_QWEN_BUDGET_FAILURE_DIAGNOSTIC_V1', 'state': 'DIAGNOSTIC_OBSERVED',
        'observed_at': time.time(), 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'boot_seconds': time.clock_gettime(time.CLOCK_BOOTTIME), 'read_only': True,
        'execution_revision': REFERENCE, 'source_and_origin_pins_verified': True,
        'files_written': 0, 'service_actions': 0, 'checkpoint_payload_bytes_read': 0,
        'raw_logs_exported': False, 'private_training_text_exported': False}
    result['boot_id'] = section(lambda: process({'boot_id': ctx['observer'].proc_bytes(
        Path('/proc/sys/kernel/random/boot_id'), 64).decode('ascii').strip()})['boot_id'])
    result['trainer'] = trainer(live)
    operation, operation_raw = core.document(area / 'operation_result.json')
    require(core.digest(operation_raw) == OPERATION_SHA, 'ATTEMPT_RECEIPT')
    require(operation.get('execution_revision') == REFERENCE
            and operation.get('state') == 'BOOTSTRAP_LOADING_PENDING'
            and operation.get('optimizer_permission_issued') is False, 'ATTEMPT_RECEIPT_CONTEXT')
    expected_process = operation['trainer']['process_identity']
    require(process(expected_process) == expected_process and expected_process.get('pid') == 1025702
            and expected_process.get('start_ticks') == 162077108
            and expected_process.get('boot_id') == '9c0ecc02-85c1-452b-b8ae-521e9a11fd03', 'ORIGINAL_PROCESS_BINDING')
    result['finalizer_and_activation_absence_before'] = absence_of_finalizer_and_activation(core, area)
    result['operation_result'] = {'present': True, 'sha256': OPERATION_SHA, **record(operation)}
    result['finalize_receipt'] = {'present': False, 'absence_verified': True}
    log_start = operation['resources_before_start']['sampled_at']
    require(number(log_start) is not None and ctx['execution']['descriptor']['created_at'] <= log_start <= time.time(), 'START_BOUND')
    allowed = allowed_terminal_codes(core.read(core.SCRIPTS / core.STUDENT, 131072), raw)
    result['log_diagnostics'] = causal_logs(core, ctx, log_start, allowed)
    result['last_result'] = section(lambda: terminal_receipt(core, ctx, binding, expected_process, allowed))
    result['progress'] = section(lambda: json_record(core, ctx['output'] / 'owner_progress.json',
                                                    lambda value: progress(value, binding)))
    result['flags'] = {name: section(lambda name=name: flag(core, name, REFERENCE['request']))
                      for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag', 'OWNER_MAINTENANCE.flag')}
    result['guard'] = section(lambda: guard_metadata(core, ctx, result['flags']))
    def activation():
        return {key: activation_value[key] for key in ('active', 'bootstrap_pending', 'deadline', 'permit_sha256', 'reason')}
    result['activation'] = section(activation)
    result['primary_failure'] = primary_failure(result['log_diagnostics'], result['flags'], log_start, result['last_result'])
    result['chat_model_identity'] = section(lambda: process(ctx['helper'].model_identity()))
    result['chat_health'] = health()
    require(shared.current_context(REFERENCE)['raw'] == ctx['raw'], 'CONTEXT_CHANGED_DURING_OBSERVATION')
    core.protected()
    require(core.trainer(ctx) == live and shared.activation_status(ctx)['active'] is False, 'ATTEMPT_CHANGED')
    for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag'):
        again = flag(core, name, REFERENCE['request'])
        require(all(again.get(key) == result['flags'][name].get(key)
                    for key in ('present', 'sha256', 'bytes', 'mtime_ns')), 'FLAG_CHANGED_AT_END')
    result['finalizer_and_activation_absence_after'] = absence_of_finalizer_and_activation(core, area)
    require(result['finalizer_and_activation_absence_after'] == result['finalizer_and_activation_absence_before'],
            'ATTEMPT_DIRECTORY_CHANGED_AT_END')
    require(core.digest(core.read(area / 'operation_result.json')) == OPERATION_SHA, 'OPERATION_CHANGED_AT_END')
    if result['last_result'].get('present') is True:
        require(core.digest(core.read(ctx['output'] / 'owner_last_result.json')) == result['last_result']['sha256'],
                'TERMINAL_CHANGED_AT_END')
    def held(value):
        return (isinstance(value, dict) and (value.get('observation') == 'HELD' or any(held(v) for v in value.values()))
                or isinstance(value, list) and any(held(v) for v in value))
    result['observation_complete'] = not held(result) and result['operation_result'].get('present') is True
    if not result['observation_complete']:
        result['state'] = 'DIAGNOSTIC_PARTIAL'
    return result


def main():
    started = time.monotonic(); old = signal.getsignal(signal.SIGALRM)
    def timed_out(_signum, _frame):
        raise DiagnosticDeadline('HOLD_QWEN_REVISION_DIAGNOSTIC_DEADLINE')
    signal.signal(signal.SIGALRM, timed_out); signal.alarm(20)
    try:
        value = snapshot(); rc = 0 if value['observation_complete'] else 2
    except (Exception, DiagnosticDeadline) as exc:
        value = {'schema': 'NOX_QWEN_BUDGET_FAILURE_DIAGNOSTIC_V1', 'state': 'HOLD',
                 'reason': safe(exc), 'read_only': True, 'files_written': 0, 'service_actions': 0,
                 'checkpoint_payload_bytes_read': 0, 'raw_logs_exported': False}
        rc = 2
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old)
    value['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_budget_failure_diagnostic', 'data': value},
          sort_keys=True, allow_nan=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
