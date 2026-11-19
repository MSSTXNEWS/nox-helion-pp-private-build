#!/usr/bin/env python3
"""Read-only mapping attribution for one observed anonymous memory inode.

Never reads memory/FD payloads, environment variables or arbitrary files. Maps
paths and command arguments remain private; output is numeric identity, counts,
byte totals, fixed classifications and command hashes only. No release action.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

PROC = Path('/proc')
TARGET = {'device': 1, 'inode': 131095, 'logical_bytes': 75266239716}
KEEPER = {'pid': 498569, 'start_ticks': 168416044, 'ppid': 498567}
CHAT = {'pid': 3266857, 'start_ticks': 172046662}
PID_LIMIT = 512
MAP_LIMIT = 262144
TOTAL_MAP_LIMIT = 16 * 1024 * 1024
APPROVED_SCRIPTS = frozenset(('/root/nox/scripts/owner_qwen_memfd.py',
    '/root/nox/scripts/qwen_student_training_entry_revision.py',
    '/root/nox/scripts/owner_qwen_execution_revision.py',
    '/root/nox/scripts/run_train_volta_t866u.sh',
    '/root/nox/scripts/owner_hermes_hydrate.py'))


class ReadHold(RuntimeError):
    pass


def process_file(pid, name, limit):
    if type(pid) is not int or not 0 < pid < 2 ** 31 or name not in ('stat', 'maps', 'cmdline'):
        raise ReadHold('PROC_FILE_SCOPE')
    directory = os.open(PROC, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    process = fd = None
    try:
        process = os.open(str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=process)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ReadHold('PROC_FILE_BOUND')
        raw = bytearray()
        while len(raw) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        if len(raw) > limit:
            raise ReadHold('PROC_READ_BOUND')
        named = os.stat(name, dir_fd=process, follow_symlinks=False)
        after = os.fstat(fd)
        if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)):
            raise ReadHold('PROC_FILE_CHANGED')
        return bytes(raw)
    finally:
        if fd is not None:
            os.close(fd)
        if process is not None:
            os.close(process)
        os.close(directory)


def identity(pid):
    raw = process_file(pid, 'stat', 4096)
    fields = raw[raw.rindex(b')') + 2:].split()
    if int(raw.split(b' ', 1)[0]) != pid or len(fields) < 20 or int(fields[19]) <= 0:
        raise ReadHold('PROCESS_IDENTITY')
    return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19])}


def command_projection(raw):
    argv = raw.rstrip(b'\0').split(b'\0') if raw else []
    executable = argv[0].rsplit(b'/', 1)[-1] if argv else b''
    kind = ('PYTHON_NAME_ONLY' if executable in (b'python', b'python3', b'python3.10', b'python3.11', b'python3.12')
            else 'SHELL_NAME_ONLY' if executable in (b'sh', b'bash', b'dash') else 'UNCLASSIFIED')
    known = sorted(path for path in APPROVED_SCRIPTS if path.encode() in argv)
    return {'cmdline_sha256': hashlib.sha256(raw).hexdigest(), 'cmdline_bytes': len(raw),
            'argv_count': len(argv), 'invocation_class': kind,
            'inline_command_argument_present': kind != 'UNCLASSIFIED' and b'-c' in argv[1:],
            'approved_script_arguments': known, 'role_established': False,
            'raw_command_exported': False}


def command_facts(expected):
    before = identity(expected['pid'])
    if any(before.get(key) != value for key, value in expected.items()):
        raise ReadHold('COMMAND_PROCESS_CHANGED')
    result = command_projection(process_file(before['pid'], 'cmdline', 65536))
    if identity(before['pid']) != before:
        raise ReadHold('COMMAND_PROCESS_CHANGED')
    return {'identity': before, **result}


def target_fd_metadata(deadline):
    before = identity(KEEPER['pid'])
    if before != KEEPER:
        raise ReadHold('KEEPER_CHANGED')
    directory = os.open(PROC / str(before['pid']) / 'fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    observed = scanned = 0
    complete = True
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not re.fullmatch(r'[0-9]{1,10}', entry.name):
                    continue
                if scanned >= 512 or time.monotonic() >= deadline:
                    complete = False
                    break
                scanned += 1
                try:
                    info = os.stat(entry.name, dir_fd=directory)
                    if (info.st_dev, info.st_ino) != (TARGET['device'], TARGET['inode']):
                        continue
                    link = os.readlink(entry.name, dir_fd=directory)
                    if (not stat.S_ISREG(info.st_mode) or info.st_size != TARGET['logical_bytes']
                            or not link.startswith(('/memfd:', 'memfd:'))):
                        raise ReadHold('TARGET_CHANGED')
                    observed += 1
                except OSError:
                    complete = False
    finally:
        os.close(directory)
    if identity(before['pid']) != before:
        raise ReadHold('KEEPER_CHANGED')
    return {'identity': before, 'target_fd_count': observed, 'scan_complete': complete,
            'target_identity_observed': observed > 0, 'fd_payload_read': False}


def coverage(intervals):
    total = end = 0
    for start, stop in sorted(intervals):
        if stop > max(start, end):
            total += stop - max(start, end)
        end = max(end, stop)
    return total


def project_maps(raw):
    result = {'mapping_count': 0, 'mapped_virtual_bytes': 0, 'malformed_lines': 0}
    intervals = []
    target_device = (os.major(TARGET['device']), os.minor(TARGET['device']))
    for line in raw.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 5:
            result['malformed_lines'] += 1
            continue
        addresses = re.fullmatch(rb'([a-fA-F0-9]{1,16})-([a-fA-F0-9]{1,16})', fields[0])
        device = re.fullmatch(rb'([a-fA-F0-9]{1,8}):([a-fA-F0-9]{1,8})', fields[3])
        if (not addresses or not device or not re.fullmatch(rb'[0-9]{1,20}', fields[4])
                or not re.fullmatch(rb'[a-fA-F0-9]{1,16}', fields[2])
                or not re.fullmatch(rb'[r-][w-][x-][ps]', fields[1])):
            result['malformed_lines'] += 1
            continue
        if (int(device[1], 16), int(device[2], 16)) != target_device or int(fields[4]) != TARGET['inode']:
            continue
        start, stop = int(addresses[1], 16), int(addresses[2], 16)
        if stop <= start:
            result['malformed_lines'] += 1
            continue
        result['mapping_count'] += 1
        result['mapped_virtual_bytes'] += stop - start
        offset = int(fields[2], 16)
        if offset < TARGET['logical_bytes']:
            intervals.append((offset, min(TARGET['logical_bytes'], offset + stop - start)))
    result['unique_file_bytes_mapped'] = coverage(intervals)
    return result, intervals


def mapping_census(deadline, parent):
    result = {'pids_examined': 0, 'map_read_bytes_upper_bound': 0, 'unavailable_processes': 0,
              'unstable_processes': 0, 'census_complete': True,
              'target_mappers': [], 'known_processes': {}}
    known = {CHAT['pid']: ('chat', CHAT), KEEPER['pid']: ('keeper', KEEPER),
             parent['pid']: ('keeper_parent', parent)}
    intervals = []
    seen = set()

    def sample(pid):
        result['pids_examined'] += 1
        try:
            before = identity(pid)
            if pid in known and any(before.get(key) != value for key, value in known[pid][1].items()):
                raise ReadHold('PINNED_PROCESS_CHANGED')
            bound = min(MAP_LIMIT, TOTAL_MAP_LIMIT - result['map_read_bytes_upper_bound'] - 1)
            if bound < 0:
                raise ReadHold('MAP_GLOBAL_READ_BOUND')
            try:
                raw = process_file(pid, 'maps', bound)
            except (OSError, ReadHold):
                result['map_read_bytes_upper_bound'] += bound + 1
                raise
            result['map_read_bytes_upper_bound'] += len(raw)
            projected, ranges = project_maps(raw)
            if identity(pid) != before:
                result['unstable_processes'] += 1
                result['census_complete'] = False
                return
            row = {'identity': before, **projected}
            if pid in known:
                result['known_processes'][known[pid][0]] = row
            if projected['malformed_lines']:
                result['census_complete'] = False
            if projected['mapping_count']:
                result['target_mappers'].append(row)
                intervals.extend(ranges)
        except (OSError, ReadHold, ValueError, IndexError):
            result['unavailable_processes'] += 1
            result['census_complete'] = False
            if pid in known:
                result['known_processes'][known[pid][0]] = {'pid': pid, 'state': 'UNAVAILABLE_SAFE_READ'}

    # Read the protected chat first, even if a later global census hits its bound.
    for pid in known:
        if (time.monotonic() >= deadline or result['pids_examined'] >= PID_LIMIT
                or result['map_read_bytes_upper_bound'] >= TOTAL_MAP_LIMIT - 1):
            result['census_complete'] = False
            break
        seen.add(pid)
        sample(pid)
    try:
        with os.scandir(PROC) as entries:
            for entry in entries:
                if not re.fullmatch(r'[0-9]{1,10}', entry.name) or int(entry.name) in seen:
                    continue
                if (result['pids_examined'] >= PID_LIMIT or time.monotonic() >= deadline
                        or result['map_read_bytes_upper_bound'] >= TOTAL_MAP_LIMIT - 1):
                    result['census_complete'] = False
                    break
                seen.add(int(entry.name))
                sample(int(entry.name))
    except OSError:
        result['census_complete'] = False
    result['mapper_count'] = len(result['target_mappers'])
    result['mapped_virtual_bytes_sum'] = sum(row['mapped_virtual_bytes'] for row in result['target_mappers'])
    result['unique_file_bytes_mapped_all_processes'] = coverage(intervals)
    result['mapped_bytes_are_resident_memory'] = False
    result['sample_is_atomic'] = False
    result['map_paths_and_addresses_exported'] = False
    return result


def observe():
    started = time.monotonic()
    deadline = started + 12
    result = {'schema': 'NOX_TRAINING_INODE_DIAGNOSTIC_V1', 'target': TARGET,
              'files_written': 0, 'service_mutations': 0, 'memory_released': False,
              'weight_payloads_read': False, 'release_authorized': False,
              'raw_cmdline_exported': False, 'environ_read': False}
    try:
        result['target_before'] = target_fd_metadata(deadline)
        if result['target_before']['target_identity_observed'] is not True:
            raise ReadHold('TARGET_NOT_OBSERVED')
        parent = identity(KEEPER['ppid'])
        result['keeper_command'] = command_facts(KEEPER)
        result['parent_command'] = command_facts(parent)
        result['mappings'] = mapping_census(deadline, parent)
        result['target_after'] = target_fd_metadata(deadline)
        result['target_stable'] = result['target_before'] == result['target_after']
        result['state'] = ('READ_ONLY_INODE_DIAGNOSIS_COMPLETE' if result['target_stable']
                           else 'HOLD_INODE_TARGET_CHANGED_OR_UNVERIFIED')
    except (OSError, ReadHold, ValueError, IndexError):
        result['state'] = 'HOLD_INODE_DIAGNOSIS_UNAVAILABLE'
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    if (not re.fullmatch(r'[0-9]{1,24}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))):
        raise ReadHold('OWNER_CONTEXT_REQUIRED')
    result = observe()
    print('NOX_MAINT_TRAINING_INODE_DIAGNOSTIC=' + json.dumps(result, sort_keys=True), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
