#!/usr/bin/env python3
"""Bound current public memfd access; only sealed config.json payload is read."""
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

INSTALLER = Path('/root/nox/scripts/owner_qwen_revision_install.py')
INSTALLER_SHA = '711912d596ce6c8e806d4ee16d9d5a1fae41c89b527825b13cf2c6788a17975a'
SHARED_SHA = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
STUDENT_SHA = 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c'
MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
REFERENCE = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
             'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
GET_SEALS = getattr(fcntl, 'F_GET_SEALS', 1034)
FULL_SEALS = 15
SCHEMA = 'NOX_QWEN_PUBLIC_MEMFD_ACCESS_PROBE_V1'


class ProbeDeadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_PUBLIC_MEMFD_PROBE_' + code)


def identity(s):
    return (s.st_dev, s.st_ino, s.st_uid, stat.S_IFMT(s.st_mode))


def core_module():
    require(not any(p.is_symlink() for p in (INSTALLER, *INSTALLER.parents)), 'INSTALLER_PATH')
    with os.fdopen(os.open(INSTALLER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as f:
        first = os.fstat(f.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and not first.st_mode & 0o022 and 0 < first.st_size <= 131072, 'INSTALLER_FILE')
        raw = f.read(131073)
        key = lambda s: identity(s) + (s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == first.st_size and key(first) == key(os.fstat(f.fileno()))
                == key(INSTALLER.stat(follow_symlinks=False))
                and hashlib.sha256(raw).hexdigest() == INSTALLER_SHA, 'INSTALLER_PIN')
    value = types.ModuleType('_nox_public_memfd_readonly'); value.__file__ = str(INSTALLER)
    exec(compile(raw, str(INSTALLER), 'exec'), value.__dict__)
    return value


def cgroup_snapshot():
    out = {'available': False}
    try:
        values = {}
        for name in ('memory.current', 'memory.max', 'memory.events'):
            with open('/sys/fs/cgroup/' + name, 'rb') as f:
                raw = f.read(4097)
            require(len(raw) <= 4096, 'CGROUP_BOUND')
            values[name] = raw.decode('ascii').strip()
        current = values['memory.current']; maximum = values['memory.max']
        require(current.isdecimal() and (maximum == 'max' or maximum.isdecimal()), 'CGROUP_NUMBER')
        events = {}
        for line in values['memory.events'].splitlines():
            fields = line.split()
            require(len(fields) == 2 and fields[1].isdecimal(), 'CGROUP_EVENTS')
            if fields[0] in ('low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill'):
                require(fields[0] not in events, 'CGROUP_DUPLICATE')
                events[fields[0]] = int(fields[1])
        limit = None if maximum == 'max' else int(maximum)
        out.update(available=True, current_bytes=int(current), limit_bytes=limit, events=events,
                   headroom_bytes=None if limit is None else max(0, limit - int(current)))
    except Exception:
        out['reason'] = 'CGROUP_METADATA_UNAVAILABLE'
    return out


def safe_access_error(exc):
    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EPERM):
            return 'ACCESS_DENIED'
        if exc.errno in (errno.ENOENT, errno.ESRCH, errno.EBADF):
            return 'CHANGED_DURING_SCAN'
        return 'ACCESS_METADATA_ERROR'
    return 'METADATA_REJECTED'


def memfd_access(pid, files, result):
    allowed = {'/memfd:nox-qwen-' + r['path'] + ' (deleted)': r for r in files}
    require(len(allowed) == len(files) and len(files) <= 16, 'MANIFEST_MEMBERS')
    rows = {r['path']: {'member': r['path'], 'expected_bytes': r['bytes'], 'state': 'PENDING_NOT_OBSERVED'} for r in files}
    result.update(members=list(rows.values()), scanned_descriptors=0, matched_descriptors=0,
                  descriptor_scan_complete=False, readlink_unavailable_count=0,
                  config_payload_bytes_read=0, config_sha_verified=False,
                  public_readonly_open_count=0, public_fds_retained=0,
                  other_member_payload_bytes_read=0, unknown_fd_payload_bytes_read=0,
                  full_public_base_payload_sha_verified=False)
    seen = {}; config_checked = set()
    with os.scandir(Path('/proc') / str(pid) / 'fd') as entries:
        for entry in entries:
            result['scanned_descriptors'] += 1
            require(result['scanned_descriptors'] <= 512 and entry.name.isdecimal(), 'FD_SCAN_BOUND')
            try:
                link = os.readlink(entry.path)
            except FileNotFoundError:
                continue
            except OSError:
                result['readlink_unavailable_count'] += 1
                continue
            if link not in allowed:
                continue
            expected = allowed[link]; row = rows[expected['path']]
            result['matched_descriptors'] += 1
            fd = None
            try:
                before = os.stat(entry.path)
                # This fixed, matched proc magic link intentionally follows to the public inode.
                fd = os.open(entry.path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                result['public_readonly_open_count'] += 1
                opened = os.fstat(fd)
                require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, 'NOT_READONLY')
                seals = fcntl.fcntl(fd, GET_SEALS)
                after = os.fstat(fd); named = os.stat(entry.path)
                require(stat.S_ISREG(after.st_mode) and after.st_uid == os.geteuid()
                        and identity(before) == identity(opened) == identity(after) == identity(named)
                        and os.readlink(entry.path) == link, 'MEMBER_IDENTITY')
                require(0 <= before.st_size <= opened.st_size <= after.st_size <= named.st_size <= expected['bytes'], 'MEMBER_SIZE')
                key = (after.st_dev, after.st_ino)
                if expected['path'] in seen and seen[expected['path']] != key:
                    row.update(state='AMBIGUOUS_PUBLIC_INODE', readonly_access_verified=False)
                    if expected['path'] == 'config.json':
                        result['config_sha_verified'] = False
                    continue
                if row['state'] == 'AMBIGUOUS_PUBLIC_INODE':
                    continue
                seen[expected['path']] = key
                sealed = seals & FULL_SEALS == FULL_SEALS
                require(not sealed or after.st_size == expected['bytes'], 'SEALED_SIZE')
                row.update(device=after.st_dev, inode=after.st_ino, uid=after.st_uid,
                           observed_bytes=after.st_size, seals=seals, fully_sealed=sealed,
                           readonly_access_verified=True,
                           state='SEALED_METADATA_ONLY' if sealed else 'PENDING_UNSEALED')
                if expected['path'] == 'config.json' and sealed:
                    require(0 < expected['bytes'] <= 65536, 'CONFIG_SIZE_BOUND')
                    if key not in config_checked:
                        config_checked.add(key)
                        payload = os.pread(fd, expected['bytes'] + 1, 0)
                        result['config_payload_bytes_read'] += len(payload)
                        require(len(payload) == expected['bytes'], 'CONFIG_LENGTH')
                        require(identity(after) == identity(os.fstat(fd)) == identity(os.stat(entry.path))
                                and os.readlink(entry.path) == link
                                and fcntl.fcntl(fd, GET_SEALS) & FULL_SEALS == FULL_SEALS, 'CONFIG_IDENTITY')
                        row['observed_sha256'] = hashlib.sha256(payload).hexdigest()
                        result['config_sha_verified'] = row['observed_sha256'] == expected['sha256']
                    row['state'] = ('SEALED_PUBLIC_CONFIG_SHA_VERIFIED' if result['config_sha_verified'] else 'CONFIG_SHA_MISMATCH')
            except Exception as exc:
                row.update(state=safe_access_error(exc), readonly_access_verified=False)
                if expected['path'] == 'config.json':
                    result['config_sha_verified'] = False
            finally:
                if fd is not None:
                    os.close(fd)
    result['descriptor_scan_complete'] = result['readlink_unavailable_count'] == 0
    if not result['descriptor_scan_complete']:
        for row in rows.values():
            if row['state'] == 'PENDING_NOT_OBSERVED':
                row['state'] = 'NOT_OBSERVED_SCAN_PARTIAL'
    result['observed_public_members'] = len(seen)
    result['observed_public_bytes'] = sum(r.get('observed_bytes', 0) for r in rows.values())
    result['fully_sealed_members'] = sum(r.get('fully_sealed') is True and r.get('readonly_access_verified') is True for r in rows.values())


def snapshot(result):
    core = core_module(); raw = core.read(core.SCRIPTS / core.SHARED)
    require(core.digest(raw) == SHARED_SHA == core.PINS[core.SHARED], 'SHARED_PIN')
    shared = core.module(core.SHARED, raw); ctx = shared.current_context(REFERENCE); core.protected()
    require(ctx['context'] == REFERENCE and ctx['execution']['descriptor']['activation_issuer_sha256'] == INSTALLER_SHA
            and ctx['execution']['runtime_entry_sha256'] == STUDENT_SHA, 'CURRENT_EXECUTION')
    before = core.trainer(ctx, required=True)
    result.update(execution_revision=dict(REFERENCE), trainer_before=before, current_binding_verified=False,
                  source_and_origin_pins_verified=True, cgroup_before=cgroup_snapshot())
    manifest, raw = core.document(core.SCRIPTS / 'qwen35_9b_manifest.json')
    require(core.digest(raw) == MANIFEST_SHA == core.PROTECTED['qwen35_9b_manifest.json'], 'PUBLIC_MANIFEST_PIN')
    files = ctx['contract'].validate_manifest(manifest)
    require(sum(r['path'] == 'config.json' for r in files) == 1, 'CONFIG_MEMBER')
    result['public_manifest_sha256'] = MANIFEST_SHA
    result['memfd'] = {}
    memfd_access(before['process_identity']['pid'], files, result['memfd'])
    result['cgroup_after'] = cgroup_snapshot()
    result['trainer_after'] = core.trainer(ctx, required=True)
    require(result['trainer_after'] == before, 'TRAINER_CHANGED')
    require(shared.current_context(REFERENCE)['raw'] == ctx['raw'], 'ADMISSION_CHANGED')
    core.protected()
    result['current_binding_verified'] = True
    result['state'] = 'PUBLIC_MEMFD_ACCESS_OBSERVED'


def main():
    result = {'schema': SCHEMA, 'state': 'HOLD', 'read_only': True, 'observed_at': time.time(),
              'files_written': 0, 'service_actions': 0, 'checkpoint_payload_bytes_read': 0,
              'current_binding_verified': False, 'optimizer_updates_proven': False,
              'keeper_started': False, 'unknown_fd_paths_exported': False}
    previous = signal.getsignal(signal.SIGALRM); timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    def expired(_signal, _frame):
        raise ProbeDeadline('HOLD_PUBLIC_MEMFD_PROBE_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(20, timer[0]) if timer[0] else 20)
    try:
        snapshot(result); rc = 0
    except (Exception, ProbeDeadline) as exc:
        reason = str(exc)
        result.update(state='HOLD', current_binding_verified=False,
                      reason=reason if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', reason)
                      else 'HOLD_PUBLIC_MEMFD_PROBE_METADATA_UNAVAILABLE')
        rc = 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        remaining = max(.001, timer[0] - (time.monotonic() - started)) if timer[0] else 0
        signal.setitimer(signal.ITIMER_REAL, remaining, timer[1])
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_public_memfd_access_probe', 'data': result},
          sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
