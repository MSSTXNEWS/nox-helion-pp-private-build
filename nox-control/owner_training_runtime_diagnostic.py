#!/usr/bin/env python3
"""Bounded read-only diagnosis of the current native training service.

Only fixed Supervisor status/tail commands and bounded metadata reads occur.
No trainer import, CUDA context, service mutation, checkpoint load, flag write,
or raw log/training content is emitted. Stored counters are not live proof.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SERVICE = 'nox-train-volta-t866u'
CONFIG = Path('/etc/supervisor/conf.d/nox-train-volta-t866u.conf')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
LIMIT = 262144
LOG_LIMIT = 65536
SOURCES = ('run_train_volta_t866u.sh', 'qwen_student_training_entry_revision.py',
           'owner_qwen_execution_revision.py', 'owner_qwen_training_contract.py',
           'owner_qwen_memfd.py', 'qwen35_9b_manifest.json')
MODULES = frozenset(('torch', 'transformers', 'peft', 'accelerate', 'bitsandbytes',
                    'trl', 'datasets', 'safetensors', 'owner_qwen_training_contract',
                    'owner_qwen_memfd', 'owner_qwen_execution_revision'))
EXCEPTIONS = frozenset(('RuntimeError', 'ValueError', 'TypeError', 'ImportError',
                       'ModuleNotFoundError', 'AttributeError', 'KeyError', 'IndexError',
                       'OSError', 'FileNotFoundError', 'MemoryError', 'OutOfMemoryError',
                       'NotImplementedError', 'AssertionError', 'SyntaxError'))
HOLD_CODES = frozenset(('HOLD_QWEN_CGROUP_RESERVE', 'HOLD_QWEN_CHECKPOINT_DISK_RESERVE',
    'HOLD_QWEN_ADMISSION_CHANGED', 'HOLD_EXISTING_TRAINER_POLICY',
    'HOLD_QWEN_EXPLICIT_NATIVE_ADMISSION_REQUIRED', 'HOLD_ACTUAL_EXECUTION_SOURCE_PIN',
    'HOLD_QWEN_UNCHANGED_RUNTIME_SOURCE_PIN', 'HOLD_EXECUTION_VERIFIER_NOT_PREPARED',
    'HOLD_EXECUTION_VERIFIER_SOURCE_CHANGED', 'HOLD_TRAINING_STOP_REQUESTED',
    'HOLD_EXISTING_TRAINER_WRITER_ACTIVE', 'HOLD_MEMFD_PARENT_SCOPE',
    'HOLD_STUDENT_CHECKPOINT_FILE_SHA', 'HOLD_INCOMPLETE_STUDENT_CHECKPOINT',
    'HOLD_NEW_PROCESS_CHECKPOINT_RELOAD_NOT_PROVEN', 'HOLD_NATIVE_RUNTIME_SNAPSHOT_DRIFT',
    'HOLD_ONE_LEASED_CUDA_DEVICE_REQUIRED', 'HOLD_STUDENT_HOLDOUT_REGRESSION',
    'HOLD_REPEATED_AMP_SKIPS', 'HOLD_NONFINITE_STUDENT_MICROBATCH',
    'HOLD_STUDENT_DATASET_SHA_OR_SIZE', 'HOLD_STUDENT_GOAL_ALREADY_COMPLETE'))
STATES = HOLD_CODES | frozenset(('NATIVE_STUDENT_UPDATE_OBSERVED',
    'EXISTING_TRAINER_HOLD_OR_PAUSE', 'STUDENT_RESTART_AND_UPDATES_VERIFIED',
    'TRAINING_RUNNING', 'TRAINING_PAUSED', 'MANUAL_OWNER_STOP',
    'CONTROLLED_PROCESS_YIELD', 'loading_owner_hybrid', 'train_owner_hybrid',
    'moe_failed_no_9b'))
PATTERNS = {
    'CUDA_OUT_OF_MEMORY': r'CUDA out of memory|torch\.OutOfMemoryError',
    'DISK_FULL': r'No space left on device|Disk quota exceeded',
    'CUDA_KERNEL_UNAVAILABLE': r'no kernel image|invalid device function',
    'MISSING_FILE': r'No such file or directory|cannot open file',
    'PERMISSION_DENIED': r'Permission denied|Operation not permitted',
    'MEMFD_UNAVAILABLE': r'HOLD_MEMFD|sealed.memfd.*(?:missing|unavailable)',
    'IMPORT_FAILURE': r'ModuleNotFoundError|ImportError',
    'ARGUMENT_ERROR': r'error: (?:the following arguments|required|unrecognized arguments)',
    'FP16_GRADIENT_UNSCALE': r'Attempting to unscale FP16 gradients',
    'AUTOCAST_DEVICE_ERROR': r'unknown device type for autocast',
    'HOST_PROCESS_KILLED': r'\bKilled\b|SIGKILL|signal 9',
    'NATIVE_ABORT': r'SIGABRT|Fatal Python error|Segmentation fault',
}


class ReadHold(RuntimeError):
    pass


def regular_read(path, limit=LIMIT, *, tail=False):
    """Walk each directory without following symlinks and never read a FIFO."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ReadHold('PATH_SCOPE')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    directory = os.open('/', flags | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        fd = os.open(path.name, flags | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (not tail and before.st_size > limit):
            raise ReadHold('FILE_SCOPE')
        if tail:
            os.lseek(fd, max(0, before.st_size - limit), os.SEEK_SET)
        data = bytearray()
        while len(data) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > limit:
            raise ReadHold('READ_BOUND')
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        stable = all(getattr(before, key) == getattr(after, key) == getattr(named, key) for key in keys)
        if not stable and not tail:
            raise ReadHold('FILE_CHANGED')
        raw = bytes(data)
        return raw, {'bytes': before.st_size, 'read_bytes': len(raw),
                     'mtime_ns': before.st_mtime_ns, 'stable': stable,
                     'sha256': hashlib.sha256(raw).hexdigest(),
                     'hash_scope': 'TAIL_ONLY' if tail else 'WHOLE_FILE'}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def projected_log(raw):
    """Export only finite known diagnostic enums; never arbitrary log strings."""
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw)
    events = []
    for line in text.splitlines()[-1000:]:
        event = {}
        classes = sorted(name for name in EXCEPTIONS if re.search(r'\b' + name + r'\b', line))
        codes = sorted(code for code in HOLD_CODES if re.search(r'\b' + code + r'\b', line))
        kinds = sorted(kind for kind, pattern in PATTERNS.items() if re.search(pattern, line, re.I))
        if classes:
            event['exception_classes'] = classes
        if codes:
            event['hold_codes'] = codes
        if kinds:
            event['patterns'] = kinds
        missing = re.search(r"No module named ['\"]([A-Za-z0-9_.]+)['\"]", line)
        if missing:
            module = missing[1].split('.')[0]
            event['missing_module'] = module if module in MODULES else 'UNLISTED_MODULE'
        if event:
            events.append(event)
    return {'events': events[-32:], 'raw_logs_exported': False}


def metadata(path, *, project=False):
    try:
        raw, result = regular_read(path)
        result['present'] = True
        if project:
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                result['json_state'] = 'INVALID_JSON'
                return result
            if isinstance(value, dict):
                fields = {}
                for name in ('state', 'reason', 'phase'):
                    if isinstance(value.get(name), str) and value[name] in STATES:
                        fields[name] = value[name]
                for name in ('successful_optimizer_steps', 'successful_total', 'attempted_total',
                             'skipped_total', 'step', 'max_steps', 'training_gpu'):
                    number = value.get(name)
                    if type(number) is int and 0 <= number <= 10 ** 12:
                        fields[name] = number
                for name in ('enabled', 'training_allowed', 'native_success_claimed'):
                    if type(value.get(name)) is bool:
                        fields[name] = value[name]
                if value.get('mode') in ('NORMAL', 'TASK_BOOST'):
                    fields['mode'] = value['mode']
                loss = value.get('loss')
                if type(loss) in (int, float) and abs(loss) < 10 ** 15 and math.isfinite(loss):
                    fields['loss'] = loss
                result['fields'] = fields
        return result
    except FileNotFoundError:
        return {'present': False}
    except (OSError, ReadHold):
        return {'present': None, 'state': 'UNAVAILABLE_SAFE_READ'}


def supervisor(command, channel=None):
    if command == 'status' and channel is None:
        args = ['supervisorctl', 'status', SERVICE]
    elif command == 'tail' and channel in ('stdout', 'stderr'):
        args = ['supervisorctl', 'tail', SERVICE, channel]
    else:
        raise ReadHold('COMMAND_SCOPE')
    try:
        child = subprocess.run(args, capture_output=True, timeout=6)
        raw = child.stdout[-LOG_LIMIT:]
        result = {'return_code': child.returncode}
        if command == 'status':
            match = re.match(rb'nox-train-volta-t866u\s+(RUNNING|STARTING|STOPPED|EXITED|FATAL|BACKOFF|STOPPING|UNKNOWN)\b(?:\s+pid\s+(\d+))?', raw)
            result['state'] = match[1].decode() if match else 'UNKNOWN'
            result['pid'] = int(match[2]) if match and match[2] else None
        else:
            result.update(projected_log(raw + b'\n' + child.stderr[-LOG_LIMIT:]))
        return result
    except (OSError, subprocess.TimeoutExpired):
        return {'state': 'COMMAND_UNAVAILABLE'}


def log_paths():
    paths = {ROOT / 'logs/train_volta_t866u.log', ROOT / 'logs/train_volta_t866u.supervisor.err'}
    try:
        raw, _ = regular_read(CONFIG, 65536)
        config = configparser.RawConfigParser(interpolation=None)
        config.read_string(raw.decode('utf-8'))
        for key in ('stdout_logfile', 'stderr_logfile'):
            path = Path(config.get('program:' + SERVICE, key, fallback=''))
            if path.parent == ROOT / 'logs' and re.fullmatch(r'[A-Za-z0-9_.-]*t866u[A-Za-z0-9_.-]*', path.name):
                paths.add(path)
    except (OSError, ReadHold, configparser.Error, UnicodeError):
        pass
    return sorted(paths)


def observe():
    started = time.time()
    result = {'schema': 'NOX_TRAINING_RUNTIME_DIAGNOSTIC_V1', 'observed_at': started,
              'service': SERVICE, 'scope': 'CURRENT_SERVICE_AND_BOUNDED_METADATA_ONLY',
              'files_written': 0, 'service_mutations': 0, 'trainer_imported': False,
              'checkpoint_payloads_verified': False, 'live_optimizer_steps_verified': False,
              'raw_logs_exported': False, 'supervisor_before': supervisor('status'),
              'config': metadata(CONFIG), 'sources': {}, 'metadata': {}, 'logs': []}
    for name in SOURCES:
        result['sources'][name] = metadata(ROOT / 'scripts' / name)
    records = {'admission': ROOT / 'state/owner_training_admission.json',
               'policy': ROOT / 'state/task_boost_mode.json',
               'execution_config': ROOT / 'config/owner_qwen_execution_revision.json',
               'guard': ROOT / 'state/owner_qwen_training_guard.json',
               'legacy_heartbeat': ROOT / 'status/train_volta_t866u.json',
               'student_progress': OUTPUT / 'owner_progress.json',
               'student_result': OUTPUT / 'owner_last_result.json',
               'checkpoint_pointer': OUTPUT / 'latest_checkpoint.json'}
    for label, path in records.items():
        result['metadata'][label] = metadata(path, project=True)
    for channel in ('stdout', 'stderr'):
        result['logs'].append({'source': 'supervisorctl:' + channel, **supervisor('tail', channel)})
    for path in log_paths():
        try:
            raw, info = regular_read(path, LOG_LIMIT, tail=True)
            result['logs'].append({'source': path.name, **info, **projected_log(raw)})
        except FileNotFoundError:
            result['logs'].append({'source': path.name, 'present': False})
        except (OSError, ReadHold):
            result['logs'].append({'source': path.name, 'state': 'UNAVAILABLE_SAFE_READ'})
    result['supervisor_after'] = supervisor('status')
    result['service_sample_stable'] = result['supervisor_before'] == result['supervisor_after']
    result['elapsed_seconds'] = round(time.time() - started, 3)
    result['state'] = 'READ_ONLY_DIAGNOSIS_COMPLETE'
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        raise ReadHold('OWNER_CONTEXT_REQUIRED')
    result = observe()
    print('NOX_MAINT_TRAINING_RUNTIME_DIAGNOSTIC=' + json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    print('NOX_MAINT_TRAINING_RUNTIME_DIAGNOSTIC_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
