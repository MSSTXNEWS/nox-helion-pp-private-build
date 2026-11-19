#!/usr/bin/env python3
"""Read/hash/count gzip bytes for exactly three owner-selected private log IDs.

The immutable private inventory supplies paths; neither names nor log text
leave this process. This is a size estimate, never deletion or backup proof.
No output file, compressed copy, service, queue or training flag is written.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types
import zlib

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
CORE_NAME = 'owner_log_space_probe.py'
CORE_SHA = '92367db1f1f010a5eba2cfd1e69ed34ed5332711b62f60b2b974d60a484c680a'
PROC_NAME = 'owner_builder_proc_probe.py'
PROC_SHA = '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff'
INVENTORY = ROOT / 'state/owner_storage/log_probe_6909108384.json'
INVENTORY_SHA = '9158ef84e21cac2164b277dcfb1b9e2736606a00c7ee2fc4781497be7bfdc683'
INVENTORY_REQUEST = '6909108384'
INVENTORY_SOURCE = '38b09cc43c16660e5de473f5174e78179552b26e'
SELECTED = {
    'f64ef79f91bbda180527ce2c': 89329518,
    '4cbef629438887d4f00787b4': 60374013,
    'b95f06737701308c22e17e64': 59351546,
}
SCHEMA = 'NOX_OWNER_SELECTED_LOG_SIZE_PROBE_V1'
MIB = 1024 ** 2
MAX_RECEIPT = 2 * MIB
MAX_CONTENT = 256 * MIB
MAX_FILE = 128 * MIB
RATE = 32 * MIB
WALL_SECONDS = 28


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_SELECTED_LOG_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def safe(exc):
    value = str(exc)
    if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value):
        return value
    if isinstance(exc, OSError):
        return 'READ_OS_ERROR_' + str(exc.errno or 0)
    return 'READ_UNVERIFIED_' + type(exc).__name__.upper()


def dependencies():
    for name, sha in ((CORE_NAME, CORE_SHA), (PROC_NAME, PROC_SHA)):
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        require(0 < len(raw) <= 65536 and digest(raw) == sha, 'SOURCE_PIN')
    raw = base64.b64decode(BUNDLE[CORE_NAME], validate=True)
    core = types.ModuleType('_nox_selected_log_readonly_core')
    core.__file__ = str(ROOT / 'scripts' / CORE_NAME)
    exec(compile(raw, core.__file__, 'exec'), core.__dict__)
    core.BUNDLE = {PROC_NAME: BUNDLE[PROC_NAME]}
    return core


def inventory_rows(core, deadline):
    core.check_time(deadline)
    fd = core.open_path(INVENTORY)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 < info.st_size <= MAX_RECEIPT, 'INVENTORY_SCOPE')
        raw = os.pread(fd, MAX_RECEIPT + 1, 0)
        require(len(raw) == info.st_size and digest(raw) == INVENTORY_SHA
                and core.identity(os.fstat(fd)) == core.identity(info), 'INVENTORY_SHA_OR_CHANGED')
        again = core.open_path(INVENTORY)
        try:
            require(core.identity(os.fstat(again)) == core.identity(info), 'INVENTORY_PATH_CHANGED')
        finally:
            os.close(again)
    finally:
        os.close(fd)
    value = json.loads(raw)
    require(value.get('schema') == 'NOX_OWNER_LOG_SPACE_PROBE_V1'
            and value.get('request') == INVENTORY_REQUEST
            and value.get('source_sha') == INVENTORY_SOURCE
            and value.get('actual_freed_bytes') == 0
            and value.get('deletion_authorized') is False, 'INVENTORY_CONTEXT')
    rows = value.get('rows')
    require(isinstance(rows, list) and len(rows) <= 128, 'INVENTORY_ROWS')
    selected = []
    for key, size in SELECTED.items():
        matches = [row for row in rows if isinstance(row, dict) and row.get('file_id') == key]
        require(len(matches) == 1, 'INVENTORY_SELECTION')
        row = matches[0]
        path = Path(row.get('_path', ''))
        require(path.is_absolute() and path.parent == ROOT / 'logs' and path.suffix == '.log'
                and '..' not in path.parts and digest(str(path).encode())[:24] == key
                and row.get('root_label') == 'NOX_LOGS'
                and row.get('logical_bytes') == size and 0 < size <= MAX_FILE
                and row.get('uid') == os.geteuid() and row.get('link_count') == 1
                and row.get('historical_diagnostics_protected') is False
                and row.get('already_compressed') is False
                and row.get('duplicate_inode_alias') is False
                and isinstance(row.get('_identity'), list) and len(row['_identity']) == 10,
                'SELECTED_SCOPE')
        selected.append(dict(row))
    require(sum(row['logical_bytes'] for row in selected) <= MAX_CONTENT
            and len({(row['device'], row['inode']) for row in selected}) == len(selected), 'SELECTED_TOTAL')
    return selected


def measure(core, row, deadline, meter):
    result = {'state': 'NOT_ESTIMATED', 'file_id': row['file_id'],
              'deletion_authorized': False, 'compressed_copy_written': False,
              'source_content_exported': False, 'paths_exported': False}
    if row.get('active_reference_before'):
        return {**result, 'reason': 'ACTIVE_REFERENCE_OBSERVED'}
    fd = None
    count = compressed = 0
    start = time.monotonic()
    try:
        core.check_time(deadline)
        fd = core.open_path(row['_path'])
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and core.identity(info) == tuple(row['_identity'])
                and info.st_uid == os.geteuid() and info.st_nlink == 1, 'CURRENT_PREIMAGE_CHANGED')
        require(0 < info.st_size <= MAX_FILE and meter['bytes'] + info.st_size <= MAX_CONTENT, 'CONTENT_BUDGET')
        value = hashlib.sha256()
        compressor = zlib.compressobj(level=1, wbits=31)
        while True:
            core.check_time(deadline)
            raw = os.read(fd, min(256 * 1024, info.st_size + 1 - count))
            if not raw:
                break
            count += len(raw); meter['bytes'] += len(raw)
            require(count <= info.st_size and meter['bytes'] <= MAX_CONTENT, 'CONTENT_GREW')
            value.update(raw); compressed += len(compressor.compress(raw))
            target = start + count / RATE
            while time.monotonic() < target:
                core.check_time(deadline)
                time.sleep(max(0, min(.02, target - time.monotonic())))
        compressed += len(compressor.flush())
        require(count == info.st_size and core.identity(os.fstat(fd)) == core.identity(info), 'CONTENT_CHANGED')
        again = core.open_path(row['_path'])
        try:
            require(core.identity(os.fstat(again)) == core.identity(info), 'CONTENT_PATH_CHANGED')
        finally:
            os.close(again)
        unit = os.fstatvfs(fd).f_frsize
        require(0 < unit <= MIB, 'ALLOCATION_UNIT')
        return {**result, 'state': 'FULL_STABLE_GZIP_SIZE_MEASURED', 'content_bytes_read': count,
            'full_sha256': value.hexdigest(), 'same_fd_and_named_inode_stable': True,
            'gzip_stream_bytes': compressed, 'gzip_level': 1, 'gzip_includes_header_and_trailer': True,
            'allocated_bytes_observed': info.st_blocks * 512, 'allocation_unit_bytes': unit,
            'estimated_allocated_delta_upper_bound': max(0, info.st_blocks * 512 - ((compressed + unit - 1) // unit) * unit),
            'mtime_age_seconds': max(0, int(time.time() - info.st_mtime)),
            'ctime_age_seconds': max(0, int(time.time() - info.st_ctime)),
            'age_proves_inactivity': False, 'shared_extents_verified': False,
            'process_visibility_before': row.get('process_visibility_before'),
            'elapsed_seconds': round(time.monotonic() - start, 3)}
    except (Hold, core.ProbeHold, OSError) as exc:
        return {**result, 'state': 'ESTIMATE_HELD_OR_PARTIAL', 'reason': safe(exc), 'content_bytes_read': count}
    finally:
        if fd is not None:
            os.close(fd)


def analyze(core):
    start = time.monotonic(); end = start + WALL_SECONDS - 2
    free_before = core.disk_free()
    rows = inventory_rows(core, min(end, start + 2))
    metadata = {'bytes': 0}; helper = core.proc_helper(metadata)
    before = core.process_scan(helper, rows, min(end, time.monotonic() + 3))
    meter = {'bytes': 0}
    estimates = []
    compression_end = min(end - 3, time.monotonic() + 18)
    for row in rows:
        row['active_reference_before'] = bool(before['references'].get(row['file_id']))
        row['process_visibility_before'] = 'COMPLETE' if before['complete'] else 'PARTIAL'
        estimates.append(measure(core, row, compression_end, meter))
    after = core.process_scan(helper, rows, min(end, time.monotonic() + 3))
    eligible = []
    for row, value in zip(rows, estimates):
        key = row['file_id']
        value['references_before'] = before['references'].get(key, [])
        value['references_after'] = after['references'].get(key, [])
        value['process_visibility_after'] = 'COMPLETE' if after['complete'] else 'PARTIAL'
        value['fd_maps_absence_verified'] = bool(before['complete'] and after['complete']
            and not value['references_before'] and not value['references_after'])
        value['metadata_stable_after_observation'] = False
        fd = None
        try:
            core.check_time(end)
            fd = core.open_path(row['_path'])
            value['metadata_stable_after_observation'] = core.identity(os.fstat(fd)) == tuple(row['_identity'])
        except (core.ProbeHold, OSError):
            pass
        finally:
            if fd is not None:
                os.close(fd)
        if value['state'] == 'FULL_STABLE_GZIP_SIZE_MEASURED' and value['metadata_stable_after_observation'] and not value['references_after']:
            eligible.append(value)
    result = {'schema': SCHEMA, 'state': 'READ_ONLY_SELECTED_LOG_ESTIMATES', 'inventory_sha256': INVENTORY_SHA,
        'inventory_request': INVENTORY_REQUEST, 'core_source_sha256': CORE_SHA, 'proc_source_sha256': PROC_SHA,
        'selected_count': len(rows), 'full_stable_estimate_count': len(eligible),
        'content_bytes_read': meter['bytes'], 'proc_metadata_bytes_read': metadata['bytes'],
        'allocated_bytes_measured': sum(v['allocated_bytes_observed'] for v in eligible),
        'measured_gzip_stream_bytes': sum(v['gzip_stream_bytes'] for v in eligible),
        'estimated_reclaim_upper_bound_bytes': sum(v['estimated_allocated_delta_upper_bound'] for v in eligible),
        'free_ssd_before_bytes': free_before, 'free_ssd_after_bytes': core.disk_free(),
        'actual_freed_bytes': 0, 'deletion_authorized': False, 'compressed_files_written': 0,
        'metadata_receipts_written': 0, 'full_backup_created': False, 'services_changed': False,
        'training_flags_changed': False, 'raw_log_text_exported': False, 'private_paths_exported': False,
        'partial_proc_visibility_is_not_inactivity_proof': True, 'age_proves_inactivity': False,
        'global_reclaim_is_not_proven': True, 'elapsed_seconds': round(time.monotonic() - start, 3), 'rows': estimates}
    require(len(encoded(result)) <= 32768, 'OUTPUT_BOUND')
    return result


def main():
    code = 0; installed = False
    try:
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
        previous = signal.getsignal(signal.SIGALRM)
        def expired(*_):
            raise Hold('HOLD_SELECTED_LOG_WALL_TIME')
        signal.signal(signal.SIGALRM, expired); installed = True
        signal.setitimer(signal.ITIMER_REAL, WALL_SECONDS)
        result = analyze(dependencies())
    except Exception as exc:
        code = 2
        result = {'schema': SCHEMA, 'state': 'READ_ONLY_OBSERVATION_HELD', 'reason': safe(exc),
            'actual_freed_bytes': 0, 'deletion_authorized': False, 'compressed_files_written': 0,
            'services_changed': False, 'training_flags_changed': False, 'private_paths_exported': False}
    finally:
        if installed:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    print('NOX_MAINT_REPAIR=' + encoded({'kind': 'selected_log_size_probe', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(code == 0).lower(), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
