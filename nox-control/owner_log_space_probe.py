#!/usr/bin/env python3
"""Bounded log metadata and lossless-size estimate; no cleanup or backup copy.

Unknown paths stay in one private metadata receipt. Log content is read only
for stable, known-name rotations and is fed directly to a count-only gzip
compressor. Partial process visibility permits this read-only estimate, never
deletion. No model, dataset, checkpoint, service, flag or queue is changed.
"""
import base64
from collections import Counter
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types
import zlib

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
PROC = Path('/proc')
ROOTS = (('NOX_LOGS', ROOT / 'logs', 2), ('SUPERVISOR_LOGS', Path('/var/log/supervisor'), 1),
         ('MEDIA_ENGINE_LOGS', ROOT / 'media', 0))
HELPER = 'owner_builder_proc_probe.py'
HELPER_SHA = '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff'
SCHEMA = 'NOX_OWNER_LOG_SPACE_PROBE_V1'
MIB = 1024 ** 2
MAX_ENTRIES, MAX_DIRS, MAX_ROWS = 4096, 64, 128
MAX_METADATA = 2 * MIB
MAX_INPUT, MAX_FILE, MAX_COMPRESSED_FILES = 512 * MIB, 256 * MIB, 32
MIN_AGE = 3600
RATE = 32 * MIB
KNOWN = {
    'train_volta_t866u.log': 'TRAINER_LOG', 'dispatcher_t855u.log': 'DISPATCHER_LOG',
    'agent_integrator_t859u.log': 'INTEGRATOR_LOG', 'autoscale_t877u.log': 'AUTOSCALE_LOG',
    'nox_selfheal.log': 'SELFHEAL_LOG', 'agent_tuner_t858u.log': 'TUNER_LOG',
    'teacher_serve_t811u.log': 'TEACHER_LOG', 'agent_architect_t859u.log': 'ARCHITECT_LOG',
    'nox_priority_scheduler.log': 'PRIORITY_LOG', 'qlora_35b_t848u.log': 'LEGACY_TRAINER_LOG',
    'downloads_t802u.log': 'DOWNLOADS_LOG', 'supervise_chat_8081.log': 'CHAT_BACKEND_LOG',
    'proxy.log': 'CHAT_PROXY_LOG', 'supervisord.log': 'SUPERVISOR_LOG',
    'engine.log': 'MEDIA_ENGINE_LOG', 'engine-error.log': 'MEDIA_ENGINE_ERROR_LOG',
}
ROTATION = re.compile(r'^(?P<base>.+\.log)(?P<suffix>\.[1-9][0-9]{0,7}|\.[0-9]{4}-[0-9]{2}-[0-9]{2})(?P<packed>\.(?:gz|xz|zst|bz2))?$')
PROTECTED = re.compile(r'(?i)(train|owner|journal|audit|memory|s03|dialog|checkpoint|receipt|distill|learn|event|report)')


class ProbeHold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise ProbeHold('HOLD_LOG_PROBE_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, info.st_nlink, stat.S_IMODE(info.st_mode), info.st_blocks)


def open_path(path, directory=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for index, part in enumerate(path.parts[1:]):
            is_dir = index < len(path.parts) - 2 or directory
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            if is_dir:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def stopped():
    return any(p.exists() or p.is_symlink() for p in
        (ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'state/STOP', Path('/workspace/NOX_STOP')))


def check_time(deadline):
    require(time.monotonic() < deadline, 'TIME_BUDGET')
    require(not stopped(), 'OWNER_STOP')


def error(exc):
    if isinstance(exc, ProbeHold):
        return str(exc)
    if isinstance(exc, OSError):
        return 'READ_' + errno.errorcode.get(exc.errno, 'OS_ERROR')
    return 'READ_UNVERIFIED'


def metadata(label, path, info, now):
    match = ROTATION.fullmatch(path.name)
    base = match['base'] if match else path.name
    root = next((root for name, root, _ in ROOTS if name == label), None)
    known = KNOWN.get(base) if path.parent == root else None
    if label == 'SUPERVISOR_LOGS' and base != 'supervisord.log':
        known = None
    if label == 'NOX_LOGS' and base in ('supervisord.log', 'engine.log', 'engine-error.log'):
        known = None
    # The media root is never traversed: only its two explicit engine logs.
    if label == 'MEDIA_ENGINE_LOGS' and base not in ('engine.log', 'engine-error.log'):
        return None
    if not match and not path.name.endswith('.log'):
        return None
    return {'file_id': digest(str(path).encode())[:24], 'root_label': label,
            'known_label': known, 'rotation': bool(match), 'already_compressed': bool(match and match['packed']),
            'historical_diagnostics_protected': bool(PROTECTED.search(base)),
            'logical_bytes': info.st_size, 'allocated_bytes': info.st_blocks * 512,
            'uid': info.st_uid, 'gid': info.st_gid, 'mode_octal': format(stat.S_IMODE(info.st_mode), '04o'),
            'link_count': info.st_nlink, 'device': info.st_dev, 'inode': info.st_ino,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
            'mtime_age_seconds': max(0, int(now - info.st_mtime)),
            'ctime_age_seconds': max(0, int(now - info.st_ctime)),
            'old_rotation_for_estimation': bool(match and now - info.st_mtime >= MIN_AGE),
            'deletion_authorized': False, '_path': str(path), '_identity': identity(info)}


def inventory(deadline):
    records, coverage, counts = [], [], Counter()
    now = time.time()
    for label, root, depth_limit in ROOTS:
        row = {'root_label': label, 'complete': True, 'entries': 0, 'errors': Counter()}
        stack = [(root, 0)]
        while stack:
            path, depth = stack.pop()
            directory = None
            try:
                check_time(deadline)
                require(counts['directories'] < MAX_DIRS, 'DIRECTORY_BUDGET')
                directory = open_path(path, directory=True); counts['directories'] += 1
                with os.scandir(directory) as entries:
                    for entry in entries:
                        check_time(deadline)
                        require(counts['entries'] < MAX_ENTRIES, 'ENTRY_BUDGET')
                        counts['entries'] += 1; row['entries'] += 1
                        info = entry.stat(follow_symlinks=False)
                        named = path / entry.name
                        if stat.S_ISLNK(info.st_mode):
                            counts['symlinks_skipped'] += 1
                        elif stat.S_ISDIR(info.st_mode) and depth < depth_limit:
                            stack.append((named, depth + 1))
                        elif stat.S_ISREG(info.st_mode):
                            item = metadata(label, named, info, now)
                            if item is not None:
                                records.append(item)
            except (OSError, ProbeHold) as exc:
                row['complete'] = False; row['errors'][error(exc)] += 1
                if isinstance(exc, ProbeHold):
                    stack.clear()
            finally:
                if directory is not None:
                    os.close(directory)
        row['errors'] = dict(row['errors']); coverage.append(row)
    seen, groups = {}, {}
    for item in records:
        key = item['device'], item['inode']
        previous = seen.get(key)
        item['duplicate_inode_alias'] = previous is not None
        if previous is None:
            seen[key] = item['file_id']
            group = groups.setdefault(item['root_label'], {'unique_inodes': 0, 'allocated_bytes': 0, 'logical_bytes': 0})
            group['unique_inodes'] += 1
            group['allocated_bytes'] += item['allocated_bytes']; group['logical_bytes'] += item['logical_bytes']
    ordered = sorted(records, key=lambda r: (not r['old_rotation_for_estimation'], -r['allocated_bytes'], r['file_id']))
    return ordered[:MAX_ROWS], {'coverage': coverage, 'counts': dict(counts), 'groups': groups,
        'log_records_seen': len(records), 'rows_truncated': len(records) > MAX_ROWS,
        'allocation_basis': 'ST_BLOCKS_PER_DISTINCT_INODE_NOT_SHARED_EXTENT_PROOF'}


def proc_helper(meter):
    raw = base64.b64decode(BUNDLE.get(HELPER, ''), validate=True)
    require(0 < len(raw) <= 65536 and digest(raw) == HELPER_SHA, 'PROC_HELPER_PIN')
    module = types.ModuleType('_nox_log_space_proc_metadata')
    module.__file__ = str(ROOT / 'scripts' / HELPER)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    module.PROC = PROC
    def read_at(directory, name, maximum):
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('type')
            pieces, count = [], 0
            while count <= maximum:
                remaining = MAX_METADATA - meter['bytes']
                if remaining <= 0:
                    raise module.ProbeBudget()
                data = os.read(fd, min(65536, maximum + 1 - count, remaining))
                meter['bytes'] += len(data)
                if not data:
                    return b''.join(pieces)
                pieces.append(data); count += len(data)
            raise ValueError('limit')
        finally:
            os.close(fd)
    module.read_at = read_at
    return module


def process_scan(helper, records, deadline):
    targets = {}
    for row in records:
        targets.setdefault((row['device'], row['inode']), []).append(row['file_id'])
    ns = {}
    for name in helper.NAMESPACES:
        try:
            info = (PROC / 'self/ns' / name).stat(); ns[name] = [info.st_dev, info.st_ino]
        except OSError:
            ns[name] = None
    counts, references, errors = Counter(), {}, []
    complete, total = True, 0
    try:
        pids = sorted(int(p.name) for p in PROC.iterdir() if p.name.isdigit())
        total = len(pids); complete = total <= helper.MAX_PIDS
        for pid in pids[:helper.MAX_PIDS]:
            check_time(deadline)
            item = helper.probe_process(pid, targets, ns, deadline, counts, {})
            counts['processes_inspected'] += 1
            complete &= item['candidate_fd_maps_complete'] and not item.get('references_truncated', False)
            counts['reference_truncations'] += int(item.get('references_truncated', False))
            uid = (item.get('status') or {}).get('uid')
            if item['errors'] and len(errors) < 24:
                errors.append({'pid': pid, 'uid': uid, 'errors': item['errors'],
                    'fd_complete': item['fd_complete'], 'maps_complete': item['maps_complete']})
            for reference in item['references']:
                for file_id in reference['builders']:
                    current = references.setdefault(file_id, [])
                    if len(current) < 8:
                        current.append({'pid': pid, 'uid': uid, 'kind': reference['kind'],
                            'access': reference.get('access'), 'shared_writable': reference.get('shared_writable')})
    except (OSError, ProbeHold, helper.ProbeBudget):
        complete = False; counts['scan_incomplete'] += 1
    return {'complete': complete, 'scope': 'CURRENT_PROC_MOUNT_VISIBLE_PROCESSES', 'pids_seen': total,
            'counts': dict(counts), 'errors': errors, 'references': references,
            'uid_or_namespace_exclusions_applied': False}


def estimate(row, deadline, total_meter):
    result = {'state': 'NOT_ESTIMATED', 'source_content_exported': False,
              'compressed_copy_written': False, 'deletion_authorized': False}
    if not (row['known_label'] and row['old_rotation_for_estimation'] and not row['already_compressed']
            and row['uid'] == os.geteuid() and row['link_count'] == 1 and not row['duplicate_inode_alias']):
        return {**result, 'reason': 'SCOPE_OR_AGE_OR_LINKS'}
    if row.get('active_reference_before'):
        return {**result, 'reason': 'ACTIVE_REFERENCE_OBSERVED'}
    if not (0 < row['logical_bytes'] <= MAX_FILE) or total_meter['bytes'] + row['logical_bytes'] > MAX_INPUT:
        return {**result, 'reason': 'CONTENT_BYTE_BUDGET'}
    fd = None
    count, compressed = 0, 0
    started = time.monotonic()
    try:
        check_time(deadline)
        fd = open_path(row['_path']); before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and identity(before) == tuple(row['_identity']), 'ESTIMATE_PREIMAGE_CHANGED')
        compressor = zlib.compressobj(level=1, wbits=31)
        sha = hashlib.sha256()
        while True:
            check_time(deadline)
            data = os.read(fd, min(256 * 1024, before.st_size + 1 - count))
            if not data:
                break
            count += len(data); total_meter['bytes'] += len(data)
            require(count <= before.st_size and total_meter['bytes'] <= MAX_INPUT, 'ESTIMATE_GREW')
            sha.update(data); compressed += len(compressor.compress(data))
            target_time = started + count / RATE
            while time.monotonic() < target_time:
                check_time(deadline); time.sleep(max(0, min(.02, target_time - time.monotonic())))
        compressed += len(compressor.flush())
        require(count == before.st_size and identity(os.fstat(fd)) == identity(before), 'ESTIMATE_FILE_CHANGED')
        named = open_path(row['_path'])
        try:
            require(identity(os.fstat(named)) == identity(before), 'ESTIMATE_PATH_CHANGED')
        finally:
            os.close(named)
        return {**result, 'state': 'FULL_STABLE_GZIP_SIZE_MEASURED', 'content_bytes_read': count,
                'full_sha256': sha.hexdigest(), 'source_stable': True, 'gzip_level': 1,
                'gzip_stream_bytes': compressed, 'gzip_includes_header_and_trailer': True,
                'estimated_allocated_delta_upper_bound': max(0, row['allocated_bytes'] - ((compressed + 4095) // 4096) * 4096),
                'global_ssd_reclaim_proven': False, 'shared_extents_verified': False,
                'process_visibility': row.get('process_visibility_before'),
                'elapsed_seconds': round(time.monotonic() - started, 3)}
    except (OSError, ProbeHold) as exc:
        return {**result, 'state': 'ESTIMATE_HELD_OR_PARTIAL', 'reason': error(exc), 'content_bytes_read': count}
    finally:
        if fd is not None:
            os.close(fd)


def disk_free():
    info = os.statvfs(ROOT)
    return info.f_bavail * info.f_frsize


def analyze():
    started = time.monotonic(); end = started + 34
    free_before = disk_free()
    rows, report = inventory(min(end, started + 4))
    metadata_meter = {'bytes': 0}; helper = proc_helper(metadata_meter)
    before = process_scan(helper, rows, min(end, time.monotonic() + 4))
    content_meter = {'bytes': 0}
    compress_end = min(end - 4, time.monotonic() + 18)
    attempts = 0
    for row in rows:
        row['active_reference_before'] = bool(before['references'].get(row['file_id']))
        row['process_visibility_before'] = 'COMPLETE' if before['complete'] else 'PARTIAL'
        if attempts >= MAX_COMPRESSED_FILES or time.monotonic() >= compress_end:
            row['compression'] = {'state': 'NOT_ESTIMATED', 'reason': 'ESTIMATE_TOTAL_BUDGET', 'deletion_authorized': False}
            continue
        row['compression'] = estimate(row, compress_end, content_meter)
        attempts += int(row['compression'].get('content_bytes_read', 0) > 0)
    after = process_scan(helper, rows, min(end, time.monotonic() + 4))
    stable_allocated, gzip_bytes, upper = 0, 0, 0
    for row in rows:
        row['references_before'] = before['references'].get(row['file_id'], [])
        row['references_after'] = after['references'].get(row['file_id'], [])
        row['fd_maps_absence_verified'] = before['complete'] and after['complete'] and not row['references_before'] and not row['references_after']
        proof = row['compression']
        row['metadata_stable_after_observation'] = False
        if time.monotonic() < end:
            try:
                fd = open_path(row['_path'])
                try:
                    row['metadata_stable_after_observation'] = identity(os.fstat(fd)) == tuple(row['_identity'])
                finally:
                    os.close(fd)
            except OSError:
                pass
        if (proof.get('state') == 'FULL_STABLE_GZIP_SIZE_MEASURED' and not row['references_after']
                and row['metadata_stable_after_observation']):
            stable_allocated += row['allocated_bytes']; gzip_bytes += proof['gzip_stream_bytes']
            upper += proof['estimated_allocated_delta_upper_bound']
        proof['deletion_authorized'] = False
    report.update(schema=SCHEMA, state='READ_ONLY_LOG_ESTIMATES', started_at=time.time() - (time.monotonic() - started),
        finished_at=time.time(), elapsed_seconds=round(time.monotonic() - started, 3),
        free_ssd_before_bytes=free_before, free_ssd_after_bytes=disk_free(),
        process_before={k:v for k,v in before.items() if k != 'references'},
        process_after={k:v for k,v in after.items() if k != 'references'},
        proc_metadata_bytes_read=metadata_meter['bytes'], content_bytes_read=content_meter['bytes'],
        known_rotation_allocated_bytes_measured=stable_allocated, measured_gzip_stream_bytes=gzip_bytes,
        estimated_reclaim_upper_bound_bytes=upper, actual_freed_bytes=0,
        deletion_authorized=False, compressed_files_written=0, services_changed=False, training_flags_changed=False,
        full_backup_created=False, unknown_names_exported=False, raw_log_text_exported=False,
        rows=rows, dependency_sha256=HELPER_SHA)
    private = json.loads(encoded(report))
    report['rows'] = [{k:v for k,v in row.items() if not k.startswith('_')} for row in rows]
    require(len(encoded(report)) <= MAX_METADATA and len(encoded(private)) <= MAX_METADATA, 'OUTPUT_BOUND')
    return report, private


def private_receipt(value, request, source):
    require(re.fullmatch('[0-9]{6,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    directory = ROOT / 'state/owner_storage'
    parent = open_path(directory, directory=True)
    try:
        info = os.fstat(parent)
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o077, 'RECEIPT_DIRECTORY')
        raw = encoded({**value, 'request': request, 'source_sha': source})
        require(len(raw) <= MAX_METADATA, 'RECEIPT_BOUND')
        name = 'log_probe_' + request + '.json'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:]); require(count > 0, 'RECEIPT_WRITE'); offset += count
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
        verify = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        try:
            info = os.fstat(verify)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == len(raw), 'RECEIPT_READBACK_TYPE')
            parts, count = [], 0
            while count <= len(raw):
                data = os.read(verify, min(65536, len(raw) + 1 - count))
                if not data:
                    break
                parts.append(data); count += len(data)
            require(b''.join(parts) == raw and identity(os.fstat(verify)) == identity(info), 'RECEIPT_READBACK')
        finally:
            os.close(verify)
        return str(directory / name), digest(raw)
    finally:
        os.close(parent)


def main():
    code = 0
    try:
        result, private = analyze()
        path, sha = private_receipt(private, os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
        result.update(private_metadata_receipt=path, private_metadata_receipt_sha256=sha,
                      metadata_receipts_written=1, private_metadata_receipt_verified=True)
    except Exception as exc:
        code = 2
        result = {'schema': SCHEMA, 'state': 'OBSERVATION_HELD', 'reason': error(exc),
                  'actual_freed_bytes': 0, 'deletion_authorized': False, 'services_changed': False}
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'log_space_probe', 'data': result}).decode().strip(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if code == 0 else 'false'), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
