#!/usr/bin/env python3
"""Remove only the exact redundant historical 3030 builder archive.

The canonical SSD file, RAM file, every sidecar, trainer, flags and services
remain untouched. A private, fsynced restore map precedes a reversible rename;
only the rehashed, same-inode quarantine file can then be unlinked. The Drive
proof is an explicit external owner readback, not a native Drive API claim.
"""
from __future__ import annotations

import base64
from collections import Counter
import ctypes
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

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
ARCHIVE = ROOT / 'progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_model.safetensors'
CANONICAL = ROOT / 'progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors'
RAM = Path('/dev/shm/nox_drive/3t724u/t724u_builder_best_holdout.safetensors')
SIZE = 306787336
SHA = '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'
CONFIG_SHA = 'f63032e755ec1f439411b3438b245eec2b420aedd18efc16487d8c9f7bc3dee2'
PROC_NAME = 'owner_builder_proc_probe.py'
PROC_SHA = '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff'
PROOF_NAME = 'owner_builder_drive_public_proof.json'
PROOF_SHA = '51099ab51197ef614141eed6256737a04289e45a252b7d32f5130d8b3a55965c'
ID_HASHES = ('b97211f238e78dcd2338558da5d5ede26547bab124d35db0c4a3c197cb6fc6c2',
             'f53eab6f9020b1e40bc4f59b3b66b86564325428da98b4a41254da216953e4f1',
             'bb7fdeb71daf89e246f0e21d9f712cb50a8414200bf7ecd41dbf9047c81e8f3c',
             '376807b6c539f18d8d37e947c10c6346f64e36763897cf011408dbedb81d46ac')
SCHEMA = 'NOX_BUILDER_ARCHIVE_RECLAIM_V1'
RATE = 32 * 1024 ** 2
CHUNK = 1024 ** 2
SECONDS = 110
FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


class Hold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_BUILDER_ARCHIVE_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def safe(exc):
    value = str(exc)
    return value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', value) else 'HOLD_BUILDER_ARCHIVE_' + type(exc).__name__.upper()


def identity(info):
    return {key: getattr(info, key) for key in FIELDS}


def stop():
    return any(p.exists() or p.is_symlink() for p in (
        ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop',
        ROOT / 'program/STOP', STATE / 'STOP', Path('/workspace/NOX_STOP')))


def tick(deadline):
    require(time.monotonic() < deadline, 'DEADLINE')
    require(not stop(), 'OWNER_STOP')


def directory(path):
    """Resolve each component with O_NOFOLLOW; no parent symlink traversal."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def regular(parent, name, *, expected_size=None, single_link=True):
    require(Path(name).name == name and name not in ('.', '..'), 'BASENAME')
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOATIME, dir_fd=parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and (not single_link or info.st_nlink == 1)
                and (expected_size is None or info.st_size == expected_size), 'FILE_SCOPE')
        return fd
    except BaseException:
        os.close(fd); raise


def named(parent, name, fd, expected=None):
    current = os.fstat(fd); path = os.stat(name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISREG(path.st_mode) and identity(path) == identity(current)
            and (expected is None or identity(current) == expected), 'FILE_OR_PATH_CHANGED')
    return identity(current)


def full_hash(fd, deadline, expected=None, expected_size=None):
    expected = SHA if expected is None else expected
    expected_size = SIZE if expected_size is None else expected_size
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_size == expected_size, 'HASH_SIZE')
    start = time.monotonic(); value = hashlib.sha256(); offset = 0
    while offset < expected_size:
        tick(deadline)
        raw = os.pread(fd, min(CHUNK, expected_size - offset), offset)
        require(bool(raw), 'HASH_EOF'); offset += len(raw); value.update(raw)
        delay = offset / RATE - (time.monotonic() - start)
        if delay > 0:
            time.sleep(min(delay, .05))
    require(identity(os.fstat(fd)) == identity(before) and value.hexdigest() == expected, 'HASH_OR_METADATA_CHANGED')
    return identity(before)


def stable_small(parent, name, expected=None, maximum=262144):
    fd = regular(parent, name, single_link=False)
    try:
        before = os.fstat(fd); require(0 < before.st_size <= maximum, 'SMALL_FILE_BOUND')
        raw = os.pread(fd, maximum + 1, 0)
        require(len(raw) == before.st_size, 'SMALL_FILE_READ')
        named(parent, name, fd, identity(before))
        require(expected is None or digest(raw) == expected, 'SMALL_FILE_SHA')
        return {'sha256': digest(raw), 'bytes': len(raw), 'identity': identity(before)}
    finally:
        os.close(fd)


def sidecars(parent):
    names = os.listdir(parent)
    require(len(names) <= 64, 'SIDECAR_COUNT')
    result = {}
    for name in names:
        if name == 'adapter_model.safetensors':
            continue
        require(Path(name).name == name, 'SIDECAR_NAME')
        result[name] = identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
    return result


def fsync_dir(fd):
    os.fsync(fd)


def private_json(parent, name, value):
    """Immutable no-replace record: no existing restore map is overwritten."""
    raw = encoded(value)
    require(0 < len(raw) <= 262144, 'PRIVATE_RECORD_BOUND')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        written = identity(os.fstat(stream.fileno()))
    fsync_dir(parent)
    check = regular(parent, name, expected_size=len(raw))
    try:
        require(stat.S_IMODE(os.fstat(check).st_mode) == 0o600, 'PRIVATE_RECORD_MODE')
        named(parent, name, check, written)
        observed = os.pread(check, len(raw) + 1, 0)
        require(observed == raw and digest(observed) == digest(raw), 'PRIVATE_RECORD_READBACK')
        named(parent, name, check, written)
    finally:
        os.close(check)
    return {'sha256': digest(raw), 'bytes': len(raw)}


def rename_noreplace(old_parent, old_name, new_parent, new_name):
    """Namespace operation only; caller latches success before directory fsync."""
    lib = ctypes.CDLL(None, use_errno=True)
    fn = getattr(lib, 'renameat2', None)
    require(fn is not None, 'RENAME_NOREPLACE_UNAVAILABLE')
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    if fn(old_parent, os.fsencode(old_name), new_parent, os.fsencode(new_name), 1):
        raise OSError(ctypes.get_errno(), 'renameat2')


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    require(False, 'ARCHIVE_NAME_REAPPEARED')


def rollback(quarantine, archive_parent, qname, observed):
    current = os.stat(qname, dir_fd=quarantine, follow_symlinks=False)
    require(stat.S_ISREG(current.st_mode) and identity(current) == observed, 'ROLLBACK_QUARANTINE_CHANGED')
    # RENAME_NOREPLACE atomically refuses to clobber a reappeared archive path.
    rename_noreplace(quarantine, qname, archive_parent, ARCHIVE.name)
    require(identity(os.stat(ARCHIVE.name, dir_fd=archive_parent, follow_symlinks=False))['st_ino'] == observed['st_ino'],
            'ROLLBACK_READBACK')


def dependencies():
    raw = base64.b64decode(BUNDLE.get(PROC_NAME, ''), validate=True)
    require(0 < len(raw) < 65536 and digest(raw) == PROC_SHA, 'PROC_SOURCE_PIN')
    proc = types.ModuleType('_nox_builder_archive_proc')
    exec(compile(raw, '<pinned-builder-proc>', 'exec'), proc.__dict__)
    raw = base64.b64decode(BUNDLE.get(PROOF_NAME, ''), validate=True)
    require(0 < len(raw) <= 8192, 'EXTERNAL_PROOF_BOUND')
    proof = json.loads(raw)
    require(digest(encoded(proof)) == PROOF_SHA and proof.get('schema') == 'NOX_BUILDER_DRIVE_REFETCH_PUBLIC_PROOF_V1'
            and proof.get('evidence_origin') == 'OWNER_SESSION_CONNECTED_GOOGLE_DRIVE_FULL_DOWNLOAD_READBACK'
            and proof.get('combined_bytes') == SIZE and proof.get('combined_sha256') == SHA
            and proof.get('complete_drive_download_and_sha_verified') is True, 'EXTERNAL_PROOF_PIN')
    require(len(proof['parts']) == 4 and [r['ordinal'] for r in proof['parts']] == list(range(4))
            and tuple(r['drive_id_sha256'] for r in proof['parts']) == ID_HASHES
            and sum(r['bytes'] for r in proof['parts']) == SIZE, 'EXTERNAL_PARTS')
    return proc, proof


def usage(proc, targets, own_fds, deadline):
    """Partial visibility is evidence only. Any observed foreign ref blocks."""
    counts = Counter(); progress = {}; rows = []; complete = True
    self_ns = {}
    for name in proc.NAMESPACES:
        try:
            info = (proc.PROC / 'self/ns' / name).stat(); self_ns[name] = [info.st_dev, info.st_ino]
        except OSError:
            self_ns[name] = None
    pids = sorted(int(p.name) for p in proc.PROC.iterdir() if p.name.isdigit())
    complete = len(pids) <= proc.MAX_PIDS
    references = []; ignored = 0
    try:
        for pid in pids[:proc.MAX_PIDS]:
            row = proc.probe_process(pid, targets, self_ns, deadline, counts, progress)
            for ref in row['references']:
                if (pid == os.getpid() and ref.get('kind') == 'FD' and ref.get('fd') in own_fds
                        and ref.get('access') == 'READ_ONLY'):
                    ignored += 1
                else:
                    references.append({'pid': pid, **ref})
            valid = row.get('candidate_fd_maps_complete') is True and not row.get('references_truncated')
            complete = complete and valid
            if not valid:
                rows.append({'pid': pid, 'identity_stable': row.get('identity_stable'),
                             'errors': row.get('errors', []), 'references_truncated': row.get('references_truncated', False)})
    except proc.ProbeBudget:
        complete = False; counts['budget_reached'] += 1
    return {'scope': 'CURRENT_PROC_MOUNT_VISIBLE_PROCESSES', 'complete': complete,
            'visibility': 'COMPLETE' if complete else 'PARTIAL', 'pid_count': len(pids),
            'counts': dict(counts), 'unreadable_or_changed': rows[:24], 'rows_truncated': len(rows) > 24,
            'references': references[:64], 'references_truncated': len(references) > 64,
            'known_reference_count': len(references), 'own_exact_readonly_fds_ignored': ignored,
            'partial_visibility_is_not_proof_of_inactivity': True}


def free_bytes(fd):
    value = os.fstatvfs(fd)
    return value.f_bavail * value.f_frsize


def prepare_private(parent, name):
    os.mkdir(name, 0o700, dir_fd=parent)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        require(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700 and os.fstat(fd).st_uid == os.geteuid(), 'PRIVATE_DIRECTORY')
        fsync_dir(parent)
        return fd
    except BaseException:
        os.close(fd)
        raise


def operate(result, proc, proof, deadline):
    handles = []; a = c = r = quarantine = None; archive_fd = canonical_fd = ram_fd = None
    renamed = unlinked = False; renamed_identity = None
    qname = 'archive-adapter_model.safetensors'
    try:
        for path in (ARCHIVE.parent, CANONICAL.parent, RAM.parent):
            handles.append(directory(path))
        a, c, r = handles
        canonical_fd = regular(c, CANONICAL.name, expected_size=SIZE); handles.append(canonical_fd)
        ram_fd = regular(r, RAM.name, expected_size=SIZE); handles.append(ram_fd)
        canonical_before = full_hash(canonical_fd, deadline); named(c, CANONICAL.name, canonical_fd, canonical_before)
        ram_before = full_hash(ram_fd, deadline); named(r, RAM.name, ram_fd, ram_before)
        result.update(canonical_ssd_full_sha_verified=True, native_ram_full_sha_verified=True)
        result['free_bytes_before'] = free_bytes(c)
        try:
            archive_fd = regular(a, ARCHIVE.name, expected_size=SIZE); handles.append(archive_fd)
        except FileNotFoundError:
            result.update(state='ARCHIVE_ALREADY_ABSENT_CANONICAL_AND_RAM_RETAINED', fresh_archive_deleted=False)
            return
        archive_before = full_hash(archive_fd, deadline); named(a, ARCHIVE.name, archive_fd, archive_before)
        require(archive_before['st_dev'] == canonical_before['st_dev']
                and archive_before['st_ino'] != canonical_before['st_ino'], 'SEPARATE_SSD_FILES')
        config_before = [stable_small(parent, 'adapter_config.json', CONFIG_SHA, 16384) for parent in (a, c)]
        sides_before = [sidecars(parent) for parent in (a, c)]
        targets = {(archive_before['st_dev'], archive_before['st_ino']): ['BUILDER_ARCHIVE'],
                   (canonical_before['st_dev'], canonical_before['st_ino']): ['BUILDER_KEPT']}
        result['usage_before'] = usage(proc, targets, {archive_fd, canonical_fd}, min(deadline, time.monotonic() + 10))
        require(result['usage_before'].get('complete') is True, 'PROCESS_INSPECTION_INCOMPLETE')
        require(result['usage_before']['known_reference_count'] == 0, 'KNOWN_PROCESS_REFERENCE')
        tick(deadline)
        backup_parent = directory(ROOT / 'backup'); handles.append(backup_parent)
        name = 'builder-archive-reclaim-' + result['request']
        quarantine = prepare_private(backup_parent, name); handles.append(quarantine)
        require(os.fstat(quarantine).st_dev == archive_before['st_dev'], 'QUARANTINE_FILESYSTEM')
        restore_map = {'schema': 'NOX_BUILDER_ARCHIVE_RESTORE_MAP_V1', 'request': result['request'],
            'source_sha': result['source_sha'], 'original_path': str(ARCHIVE), 'canonical_path': str(CANONICAL),
            'ram_path': str(RAM), 'quarantine_path': str(ROOT / 'backup' / name / qname),
            'file_sha256': SHA, 'file_bytes': SIZE, 'original_metadata': archive_before,
            'original_atime_ns': os.fstat(archive_fd).st_atime_ns,
            'original_allocated_bytes': os.fstat(archive_fd).st_blocks * 512,
            'canonical_metadata': canonical_before, 'ram_metadata': ram_before,
            'sidecar_metadata': sides_before, 'adapter_configs': config_before,
            'external_owner_drive_readback': proof, 'external_proof_canonical_sha256': PROOF_SHA,
            'native_direct_drive_readback': False, 'ram_is_durable_backup': False,
            'restore_order': ['VERIFIED_CANONICAL_SSD', 'APPROVED_DRIVE_PARTS_IN_ORDINAL_ORDER'],
            'restore_rule': 'COPY_TO_PRIVATE_TEMP_FULL_SHA_THEN_NO_REPLACE_ORIGINAL_PATH',
            'merge_or_optimizer_conversion_authorized': False,
            'proc_visibility_before': result['usage_before']}
        result['restore_map'] = private_json(quarantine, 'restore-map.json', restore_map)
        result['restore_map']['path'] = str(ROOT / 'backup' / name / 'restore-map.json')
        named(a, ARCHIVE.name, archive_fd, archive_before); named(c, CANONICAL.name, canonical_fd, canonical_before)
        named(r, RAM.name, ram_fd, ram_before); tick(deadline)
        # The destination directory is new and private; no overwrite is ever used.
        rename_noreplace(a, ARCHIVE.name, quarantine, qname); renamed = True
        renamed_info = os.stat(qname, dir_fd=quarantine, follow_symlinks=False)
        renamed_identity = identity(renamed_info)
        # The namespace change is already tracked even if either fsync fails.
        fsync_dir(a); fsync_dir(quarantine)
        private_json(quarantine, 'renamed.json', {'schema': SCHEMA, 'state': 'QUARANTINED_NO_BYTES_FREED',
                     'identity': renamed_identity, 'original_identity': archive_before})
        # Rename may alter ctime, but never accept a copy-up/replacement inode.
        require(all(renamed_identity[k] == archive_before[k] for k in FIELDS if k != 'st_ctime_ns'), 'RENAMED_INODE_CHANGED')
        named(quarantine, qname, archive_fd, renamed_identity)
        post_rename = full_hash(archive_fd, deadline); named(quarantine, qname, archive_fd, post_rename)
        full_hash(canonical_fd, deadline); named(c, CANONICAL.name, canonical_fd, canonical_before)
        named(r, RAM.name, ram_fd, ram_before)
        result['usage_before_unlink'] = usage(proc, targets, {archive_fd, canonical_fd}, min(deadline, time.monotonic() + 10))
        require(result['usage_before_unlink']['known_reference_count'] == 0, 'KNOWN_PROCESS_REFERENCE')
        require([sidecars(parent) for parent in (a, c)] == sides_before
                and [stable_small(parent, 'adapter_config.json', CONFIG_SHA, 16384) for parent in (a, c)] == config_before,
                'SIDECAR_CHANGED')
        tick(deadline); named(quarantine, qname, archive_fd, post_rename); absent(a, ARCHIVE.name)
        named(c, CANONICAL.name, canonical_fd, canonical_before); named(r, RAM.name, ram_fd, ram_before)
        private_json(quarantine, 'unlink-intent.json', {'schema': SCHEMA, 'state': 'EXACT_ARCHIVE_UNLINK_INTENT',
            'identity': post_rename, 'full_sha256': SHA, 'canonical_ssd_retained': True,
            'external_drive_verified_by_owner': True, 'partial_proc_visibility_accepted_with_reported_limit': True})
        tick(deadline); named(quarantine, qname, archive_fd, post_rename); absent(a, ARCHIVE.name)
        os.unlink(qname, dir_fd=quarantine); unlinked = True
        result['fresh_archive_deleted'] = True
        fsync_dir(quarantine)
        result.update(state='EXACT_ARCHIVE_REMOVED_CANONICAL_RAM_AND_DRIVE_RETAINED', fresh_archive_deleted=True,
            archive_file_bytes_unlinked=SIZE, archive_allocated_bytes_upper_bound=renamed_info.st_blocks * 512,
            restore_map_preserved=True,
            original_mode_not_changed=True, canonical_ssd_not_chmodded_or_hardlinked=True)
        named(c, CANONICAL.name, canonical_fd, canonical_before); named(r, RAM.name, ram_fd, ram_before)
        absent(a, ARCHIVE.name)
        require([sidecars(parent) for parent in (a, c)] == sides_before, 'POST_UNLINK_SIDECAR_CHANGED')
        result['all_sidecars_preserved'] = True
    except BaseException as exc:
        result.update(state='ARCHIVE_REMOVED_POSTCHECK_HELD' if unlinked else 'HOLD_ARCHIVE_NOT_REMOVED', reason=safe(exc))
        if renamed and not unlinked:
            try:
                require(renamed_identity is not None, 'ROLLBACK_IDENTITY_UNKNOWN')
                # A content writer may change ctime: return the same inode without
                # clobbering any new original path; preserve the drift in receipt.
                current = identity(os.stat(qname, dir_fd=quarantine, follow_symlinks=False))
                require(all(current[k] == renamed_identity[k] for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')),
                        'ROLLBACK_FOREIGN_INODE')
                rollback(quarantine, a, qname, current)
                result['archive_name_restored_without_overwrite'] = True
                fsync_dir(a); fsync_dir(quarantine)
            except BaseException as rollback_error:
                result['rollback_reason'] = safe(rollback_error)
                try:
                    os.stat(qname, dir_fd=quarantine, follow_symlinks=False)
                    result['quarantined_file_retained_for_owner'] = True
                except FileNotFoundError:
                    result['quarantined_file_retained_for_owner'] = False
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            result['interrupted'] = True
    finally:
        # Own read FDs must close before free-space evidence, including deleted inode.
        for fd in reversed(handles):
            try: os.close(fd)
            except OSError: pass
        try:
            parent = directory(CANONICAL.parent)
            try:
                result['free_bytes_after_own_fds_closed'] = free_bytes(parent)
            finally:
                os.close(parent)
        except OSError as space_error:
            result['free_space_readback_error'] = safe(space_error)
        if 'free_bytes_before' in result and 'free_bytes_after_own_fds_closed' in result:
            result['global_free_space_delta_bytes'] = result['free_bytes_after_own_fds_closed'] - result['free_bytes_before']
        result['global_free_delta_attributed_exclusively_to_operation'] = False
        result['unlink_may_free_zero_bytes_on_overlay_or_open_references'] = True


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    proc, proof = dependencies()
    result = {'schema': SCHEMA, 'instance_id': 60509551, 'request': request, 'source_sha': source,
        'started_at': time.time(), 'state': 'PREFLIGHT', 'expected_bytes': SIZE, 'expected_sha256': SHA,
        'fresh_archive_deleted': False, 'external_proof_canonical_sha256': PROOF_SHA,
        'external_drive_readback_origin': proof['evidence_origin'], 'native_direct_drive_readback': False,
        'proc_source_sha256': PROC_SHA, 'maintenance_lease': 'SHARED_GUARD_TICKS_ALLOWED',
        'trainer_or_service_actions': 0, 'training_flags_written': False, 'weights_merged': False,
        'canonical_file_modified': False, 'ram_file_modified': False, 'private_urls_or_ids_exported': False}
    state = directory(STATE); maintenance = operation = None
    receipt_name = 'owner_builder_archive_reclaim_' + request + '.json'
    try:
        try:
            os.stat(receipt_name, dir_fd=state, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            require(False, 'REQUEST_ALREADY_RECORDED')
        maintenance = regular(state, 'owner_maintenance.lock', single_link=False)
        fcntl.flock(maintenance, fcntl.LOCK_SH | fcntl.LOCK_NB)
        require(not (STATE / 'OWNER_MAINTENANCE.flag').exists()
                and not (STATE / 'OWNER_MAINTENANCE.flag').is_symlink(), 'MAINTENANCE_ACTIVE')
        operation = os.open('owner_builder_archive_reclaim.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                            0o600, dir_fd=state)
        require(stat.S_ISREG(os.fstat(operation).st_mode) and os.fstat(operation).st_uid == os.geteuid(), 'OPERATION_LOCK')
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
        previous = signal.getsignal(signal.SIGALRM)
        def expired(*_): raise Hold('HOLD_BUILDER_ARCHIVE_WALL_TIME')
        signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, SECONDS)
        try:
            tick(time.monotonic() + 1)
            operate(result, proc, proof, time.monotonic() + SECONDS - 5)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        result['finished_at'] = time.time()
        receipt = private_json(state, receipt_name, result)
    finally:
        for fd in (operation, maintenance, state):
            if fd is not None: os.close(fd)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_archive_reclaim', 'data': result}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_archive_reclaim_context', 'data': {
        'request': request, 'source_sha': source, 'receipt_sha256': receipt['sha256'], 'receipt_bytes': receipt['bytes']}}, separators=(',', ':')), flush=True)
    ok = result['state'] in ('EXACT_ARCHIVE_REMOVED_CANONICAL_RAM_AND_DRIVE_RETAINED', 'ARCHIVE_ALREADY_ABSENT_CANONICAL_AND_RAM_RETAINED')
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(ok).lower(), flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'builder_archive_reclaim_preflight', 'data': {'state': 'HOLD', 'reason': safe(exc)}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
