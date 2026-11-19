#!/usr/bin/env python3
"""Bounded read-only diagnosis of the current native training service.

Only fixed Supervisor status/tail commands and bounded metadata reads occur.
Memory reads cover pinned identities and a bounded census of anonymous FD owners.
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
PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
FD_LIMIT = 512
PID_LIMIT = 512
CENSUS_FD_LIMIT = 16384
# Chat/proxy/web were preserved by the verified continuous executor deployment.
# The director/worker identities come from its final native acceptance on Nov 18.
# Any reuse or replacement is reported as unavailable; it does not widen this scope.
MEMORY_PROCESSES = {
    'chat': (3266857, 172046662),
    'embedding': (3353067, 172255944),
    'proxy': (3703386, 175609570),
    'web': (3505392, 173653097),
    'director': (27386, 180803640),
    'worker_runtime': (27518, 180804769),
    'worker_memory': (27519, 180804769),
    'worker_weights': (27520, 180804769),
}
SMAPS_FIELDS = frozenset(('Rss', 'Pss', 'Pss_Anon', 'Pss_File', 'Pss_Shmem',
    'Shared_Clean', 'Shared_Dirty', 'Private_Clean', 'Private_Dirty', 'Anonymous',
    'AnonHugePages', 'ShmemPmdMapped', 'FilePmdMapped', 'Swap', 'SwapPss', 'Locked'))
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


def process_identity(pid):
    if type(pid) is not int or not 0 < pid < 2 ** 31:
        raise ReadHold('PID_SCOPE')
    raw, _ = regular_read(PROC / str(pid) / 'stat', 4096)
    # The process name can contain arbitrary text; only numeric fields leave here.
    fields = raw[raw.rindex(b')') + 2:].split()
    if (int(raw.split(b' ', 1)[0]) != pid or len(fields) < 20
            or fields[0] not in (b'R', b'S', b'D', b'I') or int(fields[19]) <= 0):
        raise ReadHold('PROCESS_IDENTITY')
    return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19])}


def memory_cgroup():
    result = {}
    try:
        for name in ('current', 'max'):
            raw, _ = regular_read(CGROUP / ('memory.' + name), 128)
            value = raw.strip()
            result[name + '_bytes'] = int(value) if value.isdigit() else None
        raw, _ = regular_read(CGROUP / 'memory.stat', 16384)
        for line in raw.splitlines():
            pair = line.split()
            if len(pair) == 2 and pair[0] in (b'anon', b'file', b'shmem', b'inactive_file',
                    b'active_file', b'file_mapped', b'kernel', b'sock') and pair[1].isdigit():
                result[pair[0].decode() + '_bytes'] = int(pair[1])
        result['state'] = 'OBSERVED'
    except (OSError, ReadHold, ValueError):
        result['state'] = 'UNAVAILABLE_SAFE_READ'
    return result


def fd_memory(pid, deadline, limit=FD_LIMIT):
    """Read link types and inode sizes only, never the contents of an open FD."""
    counts = {'memfd': 0, 'anonymous_file': 0, 'anonymous_inode': 0}
    # Keep device/inode pairs private, using them only to deduplicate shared FDs.
    unique = {}
    scanned = unavailable = 0
    complete = True
    directory = os.open(PROC / str(pid) / 'fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not re.fullmatch(r'[0-9]{1,10}', entry.name):
                    continue
                if scanned >= min(FD_LIMIT, limit) or time.monotonic() >= deadline:
                    complete = False
                    break
                scanned += 1
                try:
                    target = os.readlink(entry.name, dir_fd=directory)
                    kind = ('memfd' if target.startswith(('/memfd:', 'memfd:')) else
                            'anonymous_inode' if target.startswith('anon_inode:') else
                            'anonymous_file' if target.startswith('/SYSV') or target == '/dev/zero (deleted)' else None)
                    if kind is None:
                        continue
                    info = os.stat(entry.name, dir_fd=directory)
                    if os.readlink(entry.name, dir_fd=directory) != target:
                        unavailable += 1
                        continue
                    counts[kind] += 1
                    if kind != 'anonymous_inode' and stat.S_ISREG(info.st_mode) and info.st_size >= 0:
                        unique[(info.st_dev, info.st_ino)] = (kind, info.st_size)
                except OSError:
                    unavailable += 1
        summary = {'scanned': scanned, 'scan_complete': complete, 'unavailable': unavailable,
                   'fd_counts': counts, 'names_exported': False,
                   'logical_file_bytes_are_resident_memory': False}
        for kind in ('memfd', 'anonymous_file'):
            values = [size for observed_kind, size in unique.values() if observed_kind == kind]
            summary[kind + '_unique_inodes'] = len(values)
            summary[kind + '_logical_bytes'] = sum(values)
        return summary, unique
    finally:
        os.close(directory)


def anonymous_owner_census(deadline):
    """Find detached keepers without reading names, arguments, maps or contents."""
    result = {'scope': 'BOUNDED_NUMERIC_PID_ANONYMOUS_FD_CENSUS',
              'pid_limit': PID_LIMIT, 'fd_limit': CENSUS_FD_LIMIT,
              'pids_examined': 0, 'fds_examined': 0, 'unavailable_processes': 0,
              'partial_fd_scans': 0, 'unstable_processes': 0,
              'census_complete': True, 'owners': [], 'files': [],
              'logical_file_bytes_are_resident_memory': False}
    files = {}
    owners = []
    try:
        with os.scandir(PROC) as entries:
            for entry in entries:
                if not re.fullmatch(r'[0-9]{1,10}', entry.name):
                    continue
                if (result['pids_examined'] >= PID_LIMIT or result['fds_examined'] >= CENSUS_FD_LIMIT
                        or time.monotonic() >= deadline):
                    result['census_complete'] = False
                    break
                result['pids_examined'] += 1
                pid = int(entry.name)
                try:
                    before = process_identity(pid)
                    summary, unique = fd_memory(pid, deadline, CENSUS_FD_LIMIT - result['fds_examined'])
                    result['fds_examined'] += summary['scanned']
                    if not summary['scan_complete'] or summary['unavailable']:
                        result['partial_fd_scans'] += 1
                        result['census_complete'] = False
                    if process_identity(pid) != before:
                        result['unstable_processes'] += 1
                        result['census_complete'] = False
                        continue
                    if not unique:
                        continue
                    owner = {'pid': pid, 'start_ticks': before['start_ticks']}
                    owners.append({**owner, 'unique_inodes': len(unique),
                                   'logical_bytes': sum(size for _, size in unique.values()),
                                   'fd_scan_complete': summary['scan_complete'] and not summary['unavailable']})
                    for identity, (kind, size) in unique.items():
                        if identity not in files:
                            files[identity] = {'kind': kind, 'logical_bytes': size,
                                               'size_changed': False, 'owners': []}
                        item = files[identity]
                        item['size_changed'] |= item['logical_bytes'] != size
                        item['logical_bytes'] = max(item['logical_bytes'], size)
                        item['owners'].append(owner)
                except (OSError, ReadHold, ValueError, IndexError):
                    result['unavailable_processes'] += 1
                    result['census_complete'] = False
    except OSError:
        result['census_complete'] = False
        result['state'] = 'UNAVAILABLE_SAFE_READ'
    ranked = sorted(files.items(), key=lambda item: item[1]['logical_bytes'], reverse=True)
    result['unique_inodes'] = len(files)
    result['unique_logical_bytes'] = sum(item['logical_bytes'] for item in files.values())
    result['per_process_logical_bytes_sum'] = sum(row['logical_bytes'] for row in owners)
    result['shared_inodes'] = sum(len(item['owners']) > 1 for item in files.values())
    result['owners_total'] = len(owners)
    result['owners'] = sorted(owners, key=lambda item: item['logical_bytes'], reverse=True)[:64]
    result['owner_rows_truncated'] = len(owners) > len(result['owners'])
    result['files'] = [{'device': identity[0], 'inode': identity[1], **item,
                       'owners': item['owners'][:64], 'owner_count': len(item['owners'])}
                      for identity, item in ranked[:64]]
    result['file_rows_truncated'] = len(files) > len(result['files'])
    result['sample_is_atomic'] = False
    return result


def process_memory(pid, start_ticks, deadline):
    result = {'pid': pid, 'expected_start_ticks': start_ticks}
    try:
        before = process_identity(pid)
        if before['start_ticks'] != start_ticks:
            return {**result, 'state': 'IDENTITY_CHANGED_NO_MEMORY_READ'}, {}
        result['identity'] = before
        raw, _ = regular_read(PROC / str(pid) / 'smaps_rollup', 65536)
        metrics = {}
        for line in raw.decode('ascii', 'replace').splitlines():
            match = re.fullmatch(r'([A-Za-z_]+):\s+([0-9]{1,18})\s+kB', line.strip())
            if match and match[1] in SMAPS_FIELDS:
                if match[1] in metrics:
                    raise ReadHold('DUPLICATE_SMAPS_FIELD')
                metrics[match[1]] = int(match[2]) * 1024
        if not {'Rss', 'Pss'} <= metrics.keys():
            raise ReadHold('SMAPS_FIELDS')
        raw, _ = regular_read(PROC / str(pid) / 'status', 65536)
        namespace_pids = []
        for line in raw.splitlines():
            if line.startswith(b'NSpid:'):
                fields = line.split()[1:]
                if 0 < len(fields) <= 16 and all(x.isdigit() and 0 < int(x) < 2 ** 31 for x in fields):
                    namespace_pids = [int(x) for x in fields]
        namespaces = {}
        for name in ('pid', 'mnt', 'ipc', 'user'):
            try:
                target = os.readlink(PROC / str(pid) / 'ns' / name)
                match = re.fullmatch(re.escape(name) + r':\[([0-9]{1,20})\]', target)
                if match:
                    namespaces[name] = int(match[1])
            except OSError:
                pass
        try:
            descriptors, unique = fd_memory(pid, deadline)
        except OSError:
            descriptors, unique = {'state': 'UNAVAILABLE_SAFE_READ'}, {}
        if process_identity(pid) != before:
            return {**result, 'state': 'IDENTITY_CHANGED_DURING_READ'}, {}
        result.update(state='OBSERVED_STABLE_IDENTITY', smaps_rollup_bytes=metrics,
                      namespace_pids=namespace_pids, namespace_ids=namespaces,
                      descriptors=descriptors)
        return result, unique
    except (OSError, ReadHold, ValueError, IndexError):
        return {**result, 'state': 'UNAVAILABLE_SAFE_READ'}, {}


def memory_observation():
    """Bounded attribution does not authorize reclaiming or account for all shmem."""
    deadline = time.monotonic() + 12
    result = {'scope': 'PINNED_PROCESS_MEMORY_AND_BOUNDED_ANONYMOUS_FD_CENSUS', 'processes': {},
              'cgroup_before': memory_cgroup(), 'fd_payloads_read': False,
              'cmdline_environ_maps_read': False, 'reclaimable_memory_proven': False,
              'full_cgroup_memory_attribution': False}
    unique = {}
    for label, (pid, ticks) in MEMORY_PROCESSES.items():
        if time.monotonic() >= deadline:
            result['processes'][label] = {'pid': pid, 'state': 'READ_BUDGET_EXHAUSTED'}
            continue
        row, descriptors = process_memory(pid, ticks, deadline)
        result['processes'][label] = row
        unique.update(descriptors)
    rows = [row['smaps_rollup_bytes'] for row in result['processes'].values()
            if row['state'] == 'OBSERVED_STABLE_IDENTITY']
    result['stable_processes_observed'] = len(rows)
    result['smaps_sums_bytes'] = {name: sum(row[name] for row in rows if name in row)
        for name in ('Pss', 'Pss_Anon', 'Pss_File', 'Pss_Shmem', 'Private_Dirty')}
    result['smaps_field_process_counts'] = {name: sum(name in row for row in rows)
        for name in result['smaps_sums_bytes']}
    result['unique_open_anonymous_files'] = {
        'scope': 'EXPLICIT_PROCESS_IDENTITIES_ONLY',
        'inodes': len(unique), 'logical_bytes': sum(size for _, size in unique.values()),
        'resident_bytes_proven': False, 'shared_fds_deduplicated': True}
    census = anonymous_owner_census(deadline)
    result['anonymous_owner_census'] = census
    result['additional_owner_rollups'] = []
    known = set(MEMORY_PROCESSES.values())
    for owner in census['owners'][:8]:
        if (owner['pid'], owner['start_ticks']) in known:
            continue
        if time.monotonic() >= deadline:
            result['additional_owner_rollup_budget_exhausted'] = True
            break
        row, _ = process_memory(owner['pid'], owner['start_ticks'], deadline)
        result['additional_owner_rollups'].append(row)
    result['cgroup_after'] = memory_cgroup()
    return result


def observe():
    started = time.time()
    result = {'schema': 'NOX_TRAINING_RUNTIME_DIAGNOSTIC_V1', 'observed_at': started,
              'service': SERVICE, 'scope': 'CURRENT_SERVICE_AND_BOUNDED_MEMORY_METADATA',
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
    result['memory'] = memory_observation()
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
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
