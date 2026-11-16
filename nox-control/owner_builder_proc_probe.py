#!/usr/bin/env python3
"""15-second metadata diagnosis for two known builder copies; no mutations.

Process identity and access failures are observations, never exclusions or an
unlink admission. Only matching builder inode references are retained. No
unknown pathname, argv, environment, maps text or weight content is emitted.
"""
from __future__ import annotations

from collections import Counter
import errno
import json
import os
from pathlib import Path
import re
import signal
import stat
import time

ROOT = Path('/root/nox')
PROC = Path('/proc')
BUILDERS = (
    ('BUILDER_ARCHIVE', ROOT/'progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_model.safetensors'),
    ('BUILDER_KEPT', ROOT/'progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors'),
)
EXPECTED_BYTES = 306787336
MAX_PIDS, MAX_FDS, MAX_ROWS, MAX_ERRORS = 512, 20000, 24, 8
NAMESPACES = ('pid', 'mnt', 'user')
SCHEMA = 'NOX_OWNER_BUILDER_PROC_DIAGNOSTIC_V1'


class ProbeBudget(RuntimeError):
    pass


def tick(deadline):
    if time.monotonic() >= deadline:
        raise ProbeBudget()


def issue(stage, exc):
    number = exc.errno if isinstance(exc, OSError) else None
    return {'stage': stage, 'errno': number,
            'error': errno.errorcode.get(number, 'OS_ERROR') if number is not None else 'INVALID_METADATA'}


def read_at(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('type')
        chunks, count = [], 0
        while count <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - count))
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk); count += len(chunk)
        raise ValueError('limit')
    finally:
        os.close(fd)


def stat_fields(raw, pid):
    closing = raw.rfind(b')')
    if closing < 0 or raw.split(b' ', 1)[0] != str(pid).encode():
        raise ValueError('stat')
    fields = raw[closing + 2:].split()
    if len(fields) < 20 or fields[0] not in (b'R', b'S', b'D', b'Z', b'T', b't', b'X', b'x', b'K', b'W', b'P', b'I'):
        raise ValueError('stat')
    return {'state': fields[0].decode(), 'ppid': int(fields[1]), 'flags': int(fields[6]),
            'threads': int(fields[17]), 'starttime': int(fields[19])}


def status_fields(raw):
    values = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(b':')
        if not separator or key not in (b'Uid', b'Gid', b'Tgid', b'Threads', b'NSpid', b'Kthread'):
            continue
        fields = value.split()
        if not 1 <= len(fields) <= 32 or not all(part.isdigit() for part in fields):
            raise ValueError('status')
        numbers = list(map(int, fields))
        if key in (b'Uid', b'Gid') and len(numbers) != 4:
            raise ValueError('status')
        values[key.decode().lower()] = numbers if key in (b'Uid', b'Gid', b'NSpid') else numbers[0]
    return values


def builder_metadata(label, path, expected_uid):
    row = {'label': label, 'expected_bytes': EXPECTED_BYTES, 'expected_uid': expected_uid,
           'metadata_only': True, 'content_read_bytes': 0}
    try:
        for depth, parent in enumerate(reversed(path.parents)):
            if stat.S_ISLNK(parent.lstat().st_mode):
                row.update(path_scope='SYMLINK_PARENT', symlink_parent_depth=depth)
                return row
        info = path.lstat()
        row.update(path_scope='EXACT_KNOWN_PATH', regular=stat.S_ISREG(info.st_mode),
            symlink=stat.S_ISLNK(info.st_mode), size=info.st_size, size_matches=info.st_size == EXPECTED_BYTES,
            uid=info.st_uid, uid_matches=info.st_uid == expected_uid, gid=info.st_gid,
            mode_decimal=stat.S_IMODE(info.st_mode), mode_octal=format(stat.S_IMODE(info.st_mode), '04o'),
            group_or_other_writable=bool(info.st_mode & 0o022), device=info.st_dev, inode=info.st_ino,
            mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns, nlink=info.st_nlink)
        row['identity_predicate_passes'] = (row['regular'] and row['size_matches'] and row['uid_matches']
                                             and not row['group_or_other_writable'])
    except OSError as exc:
        row['error'] = issue('builder_lstat', exc)
    return row


def probe_process(pid, targets, self_ns, deadline, counters, progress):
    row = {'pid': pid, 'errors': [], 'references': [], 'fd_complete': False, 'maps_complete': False,
           'identity_stable': False, 'excluded_from_file_use_proof': False}
    def error(stage, exc):
        counters['errors_' + stage] += 1
        if len(row['errors']) < MAX_ERRORS:
            row['errors'].append(issue(stage, exc))
        else:
            row['errors_truncated'] = True
    def stage(value):
        tick(deadline); progress.update(pid=pid, stage=value)
    directory = None
    try:
        stage('pid_open')
        directory = os.open(PROC/str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for name, maximum in (('stat', 8192), ('status', 65536), ('cmdline', 8192)):
            stage(name)
            try:
                raw = read_at(directory, name, maximum)
                if name == 'stat': row['stat_before'] = stat_fields(raw, pid)
                elif name == 'status': row['status'] = status_fields(raw)
                else: row.update(cmdline_bytes=len(raw), cmdline_empty=not bool(raw))
            except (OSError, ValueError) as exc:
                error(name, exc)
        row['namespaces'] = {}
        for name in NAMESPACES:
            stage('namespace_' + name)
            try:
                info = os.stat('ns/' + name, dir_fd=directory)
                pair = [info.st_dev, info.st_ino]
                row['namespaces'][name] = {'identity': pair, 'same_as_probe': pair == self_ns.get(name)}
            except OSError as exc:
                error('namespace_' + name, exc)
        # Classification failures above never prevent either candidate check.
        stage('fd_open')
        descriptors = None
        try:
            descriptors = os.open('fd', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            row['fd_complete'] = True
            with os.scandir(descriptors) as items:
                for item in items:
                    stage('fd_stat'); counters['fd_entries'] += 1
                    if counters['fd_entries'] > MAX_FDS:
                        raise ProbeBudget()
                    if not item.name.isdigit():
                        row['fd_complete'] = False; error('fd_name', ValueError()); continue
                    try:
                        info = os.stat(item.name, dir_fd=descriptors)
                        labels = targets.get((info.st_dev, info.st_ino), [])
                        if not labels:
                            continue
                        reference = {'kind': 'FD', 'fd': int(item.name), 'builders': labels, 'access': 'UNKNOWN'}
                        try:
                            stage('fdinfo')
                            raw = read_at(directory, 'fdinfo/' + item.name, 16384)
                            match = re.search(rb'^flags:\s*([0-7]+)\s*$', raw, re.MULTILINE)
                            if match is None: raise ValueError('flags')
                            flags = int(match[1], 8)
                            reference.update(flags_decimal=flags,
                                access='PATH_ONLY' if flags & getattr(os, 'O_PATH', 0) else
                                {os.O_RDONLY: 'READ_ONLY', os.O_WRONLY: 'WRITE_ONLY', os.O_RDWR: 'READ_WRITE'}.get(flags & os.O_ACCMODE, 'UNKNOWN'))
                        except (OSError, ValueError) as exc:
                            error('fdinfo', exc)
                        if len(row['references']) < 32: row['references'].append(reference)
                        else: row['references_truncated'] = True
                    except (FileNotFoundError, ProcessLookupError):
                        counters['disappeared_descriptors'] += 1
                    except OSError as exc:
                        row['fd_complete'] = False; error('fd_stat', exc)
        except (OSError, ValueError) as exc:
            row['fd_complete'] = False; error('fd_enumeration', exc)
        finally:
            if descriptors is not None: os.close(descriptors)
        stage('maps')
        try:
            raw = read_at(directory, 'maps', 2 * 1024**2)
            counters['map_bytes'] += len(raw)
            if counters['map_bytes'] > 64 * 1024**2: raise ProbeBudget()
            for line in raw.splitlines():
                tick(deadline)
                fields = line.split(None, 5)
                if len(fields) < 5 or not fields[4].isdigit() or not re.fullmatch(rb'[0-9a-fA-F]+:[0-9a-fA-F]+', fields[3]):
                    raise ValueError('map')
                major, minor = (int(part, 16) for part in fields[3].split(b':'))
                labels = targets.get((os.makedev(major, minor), int(fields[4])), [])
                if not labels: continue
                if not re.fullmatch(rb'[r-][w-][x-][sp]', fields[1]): raise ValueError('map')
                if len(row['references']) < 32:
                    row['references'].append({'kind': 'MMAP', 'builders': labels,
                        'permissions': fields[1].decode(), 'shared_writable': fields[1][1:2] == b'w' and fields[1][3:4] == b's'})
                else: row['references_truncated'] = True
            row['maps_complete'] = True
        except (OSError, ValueError) as exc:
            error('maps', exc)
        stage('stat_after')
        try:
            row['stat_after'] = stat_fields(read_at(directory, 'stat', 8192), pid)
            row['identity_stable'] = row.get('stat_before', {}).get('starttime') == row['stat_after']['starttime']
        except (OSError, ValueError) as exc:
            error('stat_after', exc)
    except OSError as exc:
        error('pid_open', exc)
    finally:
        if directory is not None: os.close(directory)
    row['candidate_fd_maps_complete'] = row['fd_complete'] and row['maps_complete'] and row['identity_stable']
    return row


def run(request, source, seconds=14.0):
    started = time.monotonic(); deadline = started + min(14.0, max(0, seconds))
    counters = Counter(); progress = {'stage': 'start', 'pid': None}
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'state': 'OBSERVED_METADATA',
        'instance_id': 60509551, 'scope': 'CURRENT_PROC_MOUNT_VISIBLE_PROCESSES', 'builders': [],
        'probe_uid': os.geteuid(), 'probe_namespaces': {}, 'processes': [], 'process_rows_truncated': False,
        'files_deleted': 0, 'metadata_changed': False, 'weight_content_read_bytes': 0,
        'private_text_or_unknown_paths_exported': False, 'deletion_admission_evaluated': False,
        'process_identity_alone_authorizes_exclusion': False, 'pid_snapshot_complete': False}
    try:
        for label, path in BUILDERS:
            tick(deadline); result['builders'].append(builder_metadata(label, path, result['probe_uid']))
        targets = {}
        for row in result['builders']:
            if row.get('regular'):
                targets.setdefault((row['device'], row['inode']), []).append(row['label'])
        for name in NAMESPACES:
            tick(deadline)
            try:
                info = (PROC/'self/ns'/name).stat(); result['probe_namespaces'][name] = [info.st_dev, info.st_ino]
            except OSError:
                result['probe_namespaces'][name] = None
        tick(deadline)
        pids = sorted(int(item.name) for item in PROC.iterdir() if item.name.isdigit())
        result['pid_snapshot_count'] = len(pids)
        for pid in pids[:MAX_PIDS]:
            row = probe_process(pid, targets, result['probe_namespaces'], deadline, counters, progress)
            counters['processes_inspected'] += 1
            counters['candidate_fd_maps_complete'] += int(row['candidate_fd_maps_complete'])
            if row['errors'] or row['references'] or not row['candidate_fd_maps_complete']:
                if len(result['processes']) < MAX_ROWS: result['processes'].append(row)
                else: result['process_rows_truncated'] = True
        result['pid_snapshot_complete'] = len(pids) <= MAX_PIDS
    except ProbeBudget:
        result['state'] = 'PARTIAL_BUDGET_REACHED'; result['interrupted_stage'] = dict(progress)
    except (OSError, ValueError) as exc:
        result['state'] = 'PARTIAL_DIAGNOSTIC_READ'; result['diagnostic_error'] = issue(progress['stage'], exc)
    result['counts'] = dict(counters); result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['budget_seconds'] = 15
    return result


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_BUILDER_PROC_OWNER_CONTEXT')
    previous = signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError('HOLD_BUILDER_PROC_EXISTING_TIMER')
    def expired(*_): raise ProbeBudget()
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, 14.0)
    try:
        result = run(request, source)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_proc_diagnostic', 'data': result}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = str(exc)
        safe = message if re.fullmatch(r'HOLD_[A-Z0-9_]+', message) else 'HOLD_BUILDER_PROC_' + type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_proc_diagnostic_failure', 'data': safe}), flush=True)
        raise SystemExit(2)
