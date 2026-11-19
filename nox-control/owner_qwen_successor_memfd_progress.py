#!/usr/bin/env python3
"""Two current-process public memfd metadata samples; no payload or keeper.

The pinned student writes each public inode sequentially without preallocation.
Logical extent is therefore written-byte evidence, not resident RAM, a complete
SHA proof, network traffic, model readiness or optimizer progress.
"""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types

ROOT = Path('/root/nox')
PROC = Path('/proc')
INSTALLER = ROOT / 'scripts/owner_qwen_revision_install.py'
INSTALLER_SHA = 'd562ff23fcf21fb0873a93e6e68b23f0dffa87db07e3fe309bed3e750d0080e6'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
STUDENT_SHA = '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03'
MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
REFERENCE = {'request': '6916464880', 'source_sha': '7029c77906b512faaa9fd4b8290b122ee8c8f1f6',
             'receipt_sha256': 'ad3a760fac2eb56445a8e60dd19fe842ebc3d17dd26ea105485c0631fdf7ce86'}
PROCESS = {'pid': 1091069, 'start_ticks': 162502565, 'boot_id': '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'}
START_SHA = '1bc85f8b30c393698b5fa0ca0a4d7d2cec6c304fbfdd987899c0e9e5488f4db6'
READY_SHA = 'b02d6e1e1d88d1d95d052613fde264cf97f44e02d8c84b59244bf40ea9d2c023'
TOTAL_PUBLIC_BYTES = 19_329_393_661
OWNER_UID = 0
GET_SEALS = getattr(fcntl, 'F_GET_SEALS', 1034)
FULL_SEALS = 15
SCHEMA = 'NOX_QWEN_SUCCESSOR_PUBLIC_MEMFD_PROGRESS_V1'
KIND = 'qwen_successor_public_memfd_progress'
MAX_FDS = 512
MAX_SECONDS = 20.0
SAMPLE_GAP = 1.0
MAX_OUTPUT = 65536
STOPS = tuple(ROOT / p for p in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP', 'program/STOP')) + (Path('/workspace/NOX_STOP'),)
GOOD_STATES = {'UNSEALED_PUBLIC_METADATA_ONLY', 'SEALED_PUBLIC_METADATA_ONLY'}


class Hold(RuntimeError):
    pass


class Deadline(BaseException):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_SUCCESSOR_MEMFD_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(s):
    return (s.st_dev, s.st_ino, s.st_uid, s.st_gid, stat.S_IFMT(s.st_mode))


def safe(exc):
    if isinstance(exc, Deadline):
        return 'HOLD_SUCCESSOR_MEMFD_DEADLINE'
    text = str(exc)
    return text if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', text) else 'HOLD_SUCCESSOR_MEMFD_METADATA_UNAVAILABLE'


def stop_check():
    require(not any(p.exists() or p.is_symlink() for p in STOPS), 'OWNER_STOP')


def core_module():
    require(not any(p.is_symlink() for p in (INSTALLER, *INSTALLER.parents)), 'ISSUER_PATH')
    fd = os.open(INSTALLER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID and before.st_nlink == 1
                and not before.st_mode & 0o022 and 0 < before.st_size <= 131072, 'ISSUER_METADATA')
        raw = stream.read(131073)
        key = lambda s: identity(s) + (s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
        require(len(raw) == before.st_size and key(before) == key(os.fstat(stream.fileno()))
                == key(INSTALLER.stat(follow_symlinks=False)) and digest(raw) == INSTALLER_SHA, 'ISSUER_PIN')
    module = types.ModuleType('_nox_successor_memfd_readonly_issuer')
    module.__file__ = str(INSTALLER)
    exec(compile(raw, str(INSTALLER), 'exec'), module.__dict__)
    return module


def fdinfo(pid, number):
    path = PROC / str(pid) / 'fdinfo' / number
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'FDINFO_TYPE')
        raw = stream.read(4097)
    require(len(raw) <= 4096, 'FDINFO_BOUND')
    result = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(b':')
        if key not in (b'pos', b'flags', b'mnt_id', b'ino'):
            continue
        require(sep and key not in result, 'FDINFO_DUPLICATE')
        value = value.strip()
        require(re.fullmatch(b'[0-7]{1,24}' if key == b'flags' else b'[0-9]{1,20}', value), 'FDINFO_NUMBER')
        number_value = int(value, 8 if key == b'flags' else 10)
        require(number_value < 2 ** 64, 'FDINFO_NUMBER_BOUND')
        result[key] = number_value
    require(b'pos' in result and b'flags' in result, 'FDINFO_FIELDS')
    return {key.decode(): value for key, value in result.items()}


def access_error(exc):
    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EPERM):
            return 'ACCESS_DENIED'
        if exc.errno in (errno.ENOENT, errno.ESRCH, errno.EBADF):
            return 'CHANGED_DURING_SCAN'
        return 'ACCESS_METADATA_ERROR'
    if isinstance(exc, Hold) and str(exc).endswith('_AMBIGUOUS_PUBLIC_INODE'):
        return 'AMBIGUOUS_PUBLIC_INODE'
    return 'PUBLIC_METADATA_REJECTED'


def sample(pid, files, result):
    require(type(pid) is int and pid > 1 and 0 < len(files) <= 16, 'SAMPLE_SCOPE')
    allowed = {'/memfd:nox-qwen-' + row['path'] + ' (deleted)': row for row in files}
    require(len(allowed) == len(files), 'MANIFEST_DUPLICATE')
    rows = {row['path']: {'member': row['path'], 'expected_bytes': row['bytes'], 'state': 'NOT_OBSERVED',
                        'descriptor_count': 0, 'readonly_access_verified': False} for row in files}
    result.update(started_at=time.time(), members=list(rows.values()), descriptors_scanned=0,
                  readlink_unavailable_count=0, readonly_open_count=0, readonly_closed_count=0,
                  public_payload_bytes_read=0, unknown_fd_payload_bytes_read=0, retained_fds=0,
                  descriptor_scan_complete=False)
    seen = {}
    with os.scandir(PROC / str(pid) / 'fd') as entries:
        for entry in entries:
            stop_check()
            result['descriptors_scanned'] += 1
            require(result['descriptors_scanned'] <= MAX_FDS and entry.name.isdecimal(), 'FD_SCAN_BOUND')
            try:
                link = os.readlink(entry.path)
            except FileNotFoundError:
                continue
            except OSError:
                result['readlink_unavailable_count'] += 1
                continue
            if link not in allowed:
                continue  # Unknown target strings are discarded, never opened or exported.
            expected = allowed[link]; row = rows[expected['path']]
            row['descriptor_count'] += 1
            fd = None
            try:
                before = os.stat(entry.path)
                require(stat.S_ISREG(before.st_mode) and before.st_uid == OWNER_UID, 'PUBLIC_TYPE')
                # Following this already matched proc magic link is intentional.
                fd = os.open(entry.path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                result['readonly_open_count'] += 1
                opened = os.fstat(fd)
                require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, 'READONLY_OPEN')
                info = fdinfo(pid, entry.name)
                seals = fcntl.fcntl(fd, GET_SEALS)
                after = os.fstat(fd); named = os.stat(entry.path)
                require(identity(before) == identity(opened) == identity(after) == identity(named)
                        and os.readlink(entry.path) == link, 'PUBLIC_IDENTITY')
                require(0 <= before.st_size <= opened.st_size <= after.st_size <= named.st_size <= expected['bytes']
                        and 0 <= info['pos'] <= expected['bytes']
                        and info.get('ino', after.st_ino) == after.st_ino, 'PUBLIC_SIZE_OR_POSITION')
                inode = (after.st_dev, after.st_ino)
                require(expected['path'] not in seen or seen[expected['path']] == inode, 'AMBIGUOUS_PUBLIC_INODE')
                seen[expected['path']] = inode
                sealed = seals & FULL_SEALS == FULL_SEALS
                require(not sealed or named.st_size == expected['bytes'], 'SEALED_SIZE')
                if row['state'] not in GOOD_STATES | {'NOT_OBSERVED'}:
                    continue  # A prior raced/ambiguous descriptor cannot become an accepted member.
                row.update(device=after.st_dev, inode=after.st_ino, uid=after.st_uid,
                           written_bytes_lower=min(row.get('written_bytes_lower', before.st_size), before.st_size),
                           observed_written_bytes=max(row.get('observed_written_bytes', 0), named.st_size),
                           fdinfo_pos_min=min(row.get('fdinfo_pos_min', info['pos']), info['pos']),
                           fdinfo_pos_max=max(row.get('fdinfo_pos_max', info['pos']), info['pos']),
                           fdinfo_flags=info['flags'], fdinfo_mnt_id=info.get('mnt_id'),
                           position_within_size_bracket=bool(row.get('position_within_size_bracket', True)
                               and before.st_size <= info['pos'] <= named.st_size),
                           seals=seals, fully_sealed=sealed, readonly_access_verified=True,
                           state='SEALED_PUBLIC_METADATA_ONLY' if sealed else 'UNSEALED_PUBLIC_METADATA_ONLY')
            except Exception as exc:
                row.update(state=access_error(exc), readonly_access_verified=False)
            finally:
                if fd is not None:
                    os.close(fd)
                    result['readonly_closed_count'] += 1
    valid = [row for row in rows.values() if row['state'] in GOOD_STATES and row['readonly_access_verified']]
    result.update(finished_at=time.time(), descriptor_scan_complete=result['readlink_unavailable_count'] == 0,
                  observed_unique_public_members=len(valid), observed_unique_written_bytes=sum(row['observed_written_bytes'] for row in valid),
                  fully_sealed_members=sum(row['fully_sealed'] for row in valid),
                  all_manifest_members_observed=len(valid) == len(files),
                  owned_fd_cleanup_complete=result['readonly_open_count'] == result['readonly_closed_count'])


def growth(first, second):
    before = {row['member']: row for row in first['members']}
    matched = []; newly_observed = []; uncertain = []
    for row in second['members']:
        old = before[row['member']]
        if row['state'] not in GOOD_STATES:
            uncertain.append(row['member']); continue
        if old['state'] == 'NOT_OBSERVED':
            newly_observed.append(row['member']); continue
        if (old['state'] not in GOOD_STATES or (old['device'], old['inode']) != (row['device'], row['inode'])
                or old['observed_written_bytes'] > row['observed_written_bytes']):
            uncertain.append(row['member']); continue
        matched.append({'member': row['member'], 'written_bytes_delta': row['observed_written_bytes'] - old['observed_written_bytes']})
    return {'same_inode_members': matched, 'newly_observed_members': newly_observed, 'uncertain_members': uncertain,
            'same_inode_written_bytes_delta': sum(row['written_bytes_delta'] for row in matched),
            'atomic_global_snapshot': False, 'network_transfer_bytes_measured': False}


def start_binding(shared, ctx):
    row, _ = shared.document(ctx['execution']['directory'] / 'start_receipt.json', 16384, expected=START_SHA, private=True)
    require(row.get('schema') == 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1'
            and row.get('execution_revision') == REFERENCE and row.get('watcher_ready_sha256') == READY_SHA
            and row.get('start_command_issued') is True and type(row.get('start_command_returncode')) is int
            and row['start_command_returncode'] == 0
            and (row.get('trainer') or {}).get('process_identity') == PROCESS
            and ((row.get('trainer') or {}).get('service') or {}).get('state') == 'RUNNING', 'START_BINDING')
    shared.read(ctx['execution']['directory'] / 'watcher_ready.json', 16384, expected=READY_SHA, private=True)


def snapshot(result):
    stop_check(); core = core_module()
    raw = core.read(core.SCRIPTS / core.SHARED)
    require(digest(raw) == SHARED_SHA == core.PINS[core.SHARED_ASSET], 'SHARED_PIN')
    shared = core.module(core.SHARED, raw); ctx = shared.current_context(REFERENCE)
    require(ctx['context'] == REFERENCE and ctx['execution']['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA
            and ctx['execution']['runtime_entry_sha256'] == STUDENT_SHA, 'CURRENT_EXECUTION')
    core.protected(); start_binding(shared, ctx)
    trainer = core.trainer(ctx, required=True)
    require(trainer['process_identity'] == PROCESS, 'EXPECTED_PROCESS')
    result.update(trainer_before=trainer, source_and_origin_pins_verified=True)
    manifest, raw = core.document(core.SCRIPTS / 'qwen35_9b_manifest.json', 262144)
    require(digest(raw) == MANIFEST_SHA == core.PROTECTED['qwen35_9b_manifest.json'], 'PUBLIC_MANIFEST_PIN')
    files = ctx['contract'].validate_manifest(manifest)
    require(len(files) == 16 and sum(row['bytes'] for row in files) == TOTAL_PUBLIC_BYTES, 'PUBLIC_TOTAL')
    result.update(expected_public_bytes=TOTAL_PUBLIC_BYTES, public_manifest_sha256=MANIFEST_SHA, samples=[])
    for index in range(2):
        stop_check(); value = {}; result['samples'].append(value)
        sample(PROCESS['pid'], files, value)
        if index == 0:
            time.sleep(SAMPLE_GAP)
    stop_check()
    after = core.trainer(ctx, required=True); result['trainer_after'] = after
    require(after == trainer, 'TRAINER_CHANGED')
    current = shared.current_context(REFERENCE)
    require(current['raw'] == ctx['raw'] and current['wrapper'] == ctx['wrapper']
            and current['config_sha256'] == ctx['config_sha256'], 'CONTEXT_CHANGED')
    start_binding(shared, current); core.protected()
    result.update(current_binding_verified=True, state='CURRENT_PUBLIC_MEMFD_METADATA_OBSERVED',
                  comparison=growth(*result['samples']))


def main():
    started = time.monotonic()
    result = {'schema': SCHEMA, 'state': 'HOLD', 'read_only': True, 'observed_at': time.time(),
              'execution_revision': dict(REFERENCE), 'expected_process_identity': dict(PROCESS),
              'source_pins': {'issuer': INSTALLER_SHA, 'shared': SHARED_SHA, 'student': STUDENT_SHA},
              'current_binding_verified': False, 'public_payload_bytes_read': 0, 'unknown_fd_payload_bytes_read': 0,
              'checkpoint_payload_bytes_read': 0, 'full_public_base_payload_sha_verified': False,
              'optimizer_updates_proven': False, 'keeper_started': False, 'files_written': 0,
              'services_or_flags_modified': False, 'unknown_fd_paths_exported': False, 'persistent_fds_retained': 0}
    previous = signal.getsignal(signal.SIGALRM); old_timer = signal.getitimer(signal.ITIMER_REAL)
    def expired(*_):
        raise Deadline()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(MAX_SECONDS, old_timer[0]) if old_timer[0] else MAX_SECONDS)
    try:
        snapshot(result); rc = 0
    except (Exception, Deadline) as exc:
        result.update(state='HOLD', current_binding_verified=False, reason=safe(exc)); rc = 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        remaining = max(.001, old_timer[0] - (time.monotonic() - started)) if old_timer[0] else 0
        signal.setitimer(signal.ITIMER_REAL, remaining, old_timer[1])
    result['owned_fd_cleanup_verified'] = all(row.get('readonly_open_count', 0) == row.get('readonly_closed_count', 0)
                                             for row in result.get('samples', []))
    result['persistent_fds_retained'] = 0 if result['owned_fd_cleanup_verified'] else None
    if not result['owned_fd_cleanup_verified']:
        result.update(state='HOLD', current_binding_verified=False, reason='HOLD_SUCCESSOR_MEMFD_FD_CLEANUP_UNVERIFIED'); rc = 2
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    encoded = json.dumps({'kind': KIND, 'data': result}, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode()) > MAX_OUTPUT:
        encoded = json.dumps({'kind': KIND, 'data': {'schema': SCHEMA, 'state': 'HOLD',
            'reason': 'HOLD_SUCCESSOR_MEMFD_OUTPUT_BOUND', 'read_only': True, 'current_binding_verified': False}}, separators=(',', ':'))
        rc = 2
    print('NOX_MAINT_REPAIR=' + encoded, flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
