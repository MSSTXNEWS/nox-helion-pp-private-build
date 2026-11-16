#!/usr/bin/env python3
"""Bounded, read-only failure diagnosis for the explicit installed revision.

Reuse the frozen technical-log sanitizer. No training/control calls, writes,
checkpoint payload hashes, model imports, raw logs, prompts or credentials.
"""
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
INSTALLER_SHA = '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468'
SHARED_SHA = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
REFERENCE = {'request': '6912442714', 'source_sha': '7e27ab2ce0673205701727f4d3ef3f4a59b3d096',
             'receipt_sha256': 'c7304317a76fe08869eec9b6127ffd51107d69698e8b0ea678ae7c0f8d1e2858'}
FINALIZE = 'finalize-6912442714.json'
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
    raw = core.read(path, 4096)
    result = {'present': True, 'bytes': len(raw), 'sha256': core.digest(raw), 'ownership': 'OTHER_OR_UNRECOGNIZED'}
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


def snapshot():
    core = core_module(); raw = core.read(core.SCRIPTS / core.SHARED)
    require(core.digest(raw) == SHARED_SHA == core.PINS[core.SHARED], 'SHARED_PIN')
    shared = core.module(core.SHARED, raw); ctx = shared.current_context(REFERENCE); core.protected()
    require(ctx['context'] == REFERENCE and ctx['execution']['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA,
            'EXPLICIT_CURRENT_CONTEXT')
    area = core.STATE / 'owner_qwen_execution_revisions' / REFERENCE['request']
    require(ctx['execution']['directory'] == area, 'AREA_SCOPE')
    binding = shared.execution_binding(ctx)
    result = {'schema': 'NOX_QWEN_EXECUTION_REVISION_DIAGNOSTIC_V1', 'state': 'DIAGNOSTIC_OBSERVED',
        'observed_at': time.time(), 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'boot_seconds': time.clock_gettime(time.CLOCK_BOOTTIME), 'read_only': True,
        'execution_revision': REFERENCE, 'source_and_origin_pins_verified': True,
        'files_written': 0, 'service_actions': 0, 'checkpoint_payload_bytes_read': 0,
        'raw_logs_exported': False, 'private_training_text_exported': False}
    result['boot_id'] = section(lambda: process({'boot_id': ctx['observer'].proc_bytes(
        Path('/proc/sys/kernel/random/boot_id'), 64).decode('ascii').strip()})['boot_id'])
    result['trainer'] = section(lambda: trainer(core.trainer(ctx)))
    result['log_diagnostics'] = section(lambda: ctx['window'].log_diagnostics(ctx['helper']))
    result['finalize_receipt'] = section(lambda: json_record(core, area / FINALIZE, record))
    result['operation_result'] = section(lambda: json_record(core, area / 'operation_result.json', record))
    for name, key in (('owner_last_result.json', 'last_result'), ('owner_progress.json', 'progress')):
        result[key] = section(lambda name=name: json_record(core, ctx['output'] / name,
                                                           lambda value: progress(value, binding)))
    result['flags'] = {name: section(lambda name=name: flag(core, name, REFERENCE['request']))
                      for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag', 'OWNER_MAINTENANCE.flag')}
    def activation():
        value = shared.activation_status(ctx)
        return {key: value[key] for key in ('active', 'bootstrap_pending', 'deadline', 'permit_sha256', 'reason')}
    result['activation'] = section(activation)
    result['chat_model_identity'] = section(lambda: process(ctx['helper'].model_identity()))
    result['chat_health'] = health()
    require(shared.current_context(REFERENCE)['raw'] == ctx['raw'], 'CONTEXT_CHANGED_DURING_OBSERVATION')
    core.protected()
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
    signal.signal(signal.SIGALRM, timed_out); signal.alarm(45)
    try:
        value = snapshot(); rc = 0 if value['observation_complete'] else 2
    except (Exception, DiagnosticDeadline) as exc:
        value = {'schema': 'NOX_QWEN_EXECUTION_REVISION_DIAGNOSTIC_V1', 'state': 'HOLD',
                 'reason': safe(exc), 'read_only': True, 'files_written': 0, 'service_actions': 0,
                 'checkpoint_payload_bytes_read': 0, 'raw_logs_exported': False}
        rc = 2
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old)
    value['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_execution_revision_diagnostic', 'data': value},
          sort_keys=True, allow_nan=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
