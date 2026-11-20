#!/usr/bin/env python3
"""NOX cold storage: copy, streaming SHA readback, receipt, optional exact eviction.
Uses only an existing rclone remote. No daemon, credentials, GPU or trainer changes.
Batch transfers use at most six OS processes. Deletion is serial and opt-in.
"""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path, PureWindowsPath
import re
import selectors
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time

GIB = 1024 ** 3
MIB = 1024 ** 2
PRIORITY_STATE = Path('/root/nox/state/priority')
NATIVE_CGROUP = Path('/sys/fs/cgroup')
BACKGROUND_RAM_FLOOR = 512 * MIB
BACKGROUND_HASH_RATE = 32 * MIB
BACKGROUND_RCLONE_LIMITS = ('--bwlimit', '8M', '--buffer-size', '1M',
                           '--drive-chunk-size', '4M')
BLOCKED_PARTS = {'s03', 'checkpoint', 'checkpoints', 'optimizer', 'training', 'sqlite', 'database', 'db', 'genesis',
                 'lora', 'qlora', 'adapter', 'adapters', 'runs_owner_hybrid'}
ALLOWED_SUFFIX = {'.safetensors', '.gguf', '.bin', '.pt', '.pth'}
SHA = re.compile(r'^[0-9a-f]{64}$')
OWNER_MODEL_UPDATE_FLAG = Path('/root/nox/state/OWNER_MAINTENANCE.flag')
OWNER_STOP_PATHS = (
    Path('/root/nox/STOP'), Path('/root/nox/STOP.flag'),
    Path('/root/nox/stop.flag'), Path('/root/nox/.stop'),
    Path('/root/nox/program/STOP'), Path('/root/nox/state/STOP'),
    Path('/root/nox/state/STOP.flag'), Path('/workspace/NOX_STOP'),
)


def _owner_flag_present_or_hold(path):
    """Only ENOENT is absence; unreadable owner controls are never clear."""
    try:
        os.lstat(path)  # Also detects dangling symlinks; never follows the final link.
    except FileNotFoundError:
        return False
    except OSError:
        raise RuntimeError('HOLD_OWNER_STOP_UNREADABLE') from None
    return True


def owner_control_flags():
    """Inspect every alias, including maintenance, without short-circuiting errors."""
    stopped = False
    for path in OWNER_STOP_PATHS:
        if _owner_flag_present_or_hold(path):
            stopped = True
    maintenance = _owner_flag_present_or_hold(OWNER_MODEL_UPDATE_FLAG)
    return stopped, maintenance


def assert_owner_stop_clear():
    """Owner STOP/MODEL_UPDATE fence writes, including unreadable control paths."""
    stopped, maintenance = owner_control_flags()
    if stopped:
        raise RuntimeError('HOLD_OWNER_STOP')
    if maintenance:
        raise RuntimeError('HOLD_OWNER_MODEL_UPDATE')


def background_storage_checkpoint():
    """Read the serving arbiter's state and the container's resource budget."""
    assert_owner_stop_clear()
    try:
        active = read_priority_value('CHAT_ACTIVE')
        mode = read_priority_value('MODE')
        if active == '1' or mode == 'ACTIVE':
            raise RuntimeError('HOLD_BACKGROUND_OWNER_CHAT_ACTIVE')
        if active != '0' or mode != 'IDLE':
            raise ValueError
        last = datetime.fromisoformat(read_priority_value('LAST_OWNER_CHAT'))
        idle_minutes = int(read_priority_value('IDLE_MINUTES'))
        if last.tzinfo is None or not 1 <= idle_minutes <= 60:
            raise ValueError
    except (OSError, ValueError):
        raise RuntimeError('HOLD_BACKGROUND_PRIORITY_UNAVAILABLE') from None
    if (datetime.now(timezone.utc) - last).total_seconds() < idle_minutes * 60:
        raise RuntimeError('HOLD_BACKGROUND_OWNER_CHAT_RECENT')

    try:
        limit = int((NATIVE_CGROUP / 'memory.max').read_text().strip())
        current = int((NATIVE_CGROUP / 'memory.current').read_text().strip())
        if not 0 <= current <= limit:
            raise ValueError
        pressure = []
        for meter in ('memory.pressure', 'io.pressure'):
            parser = re.search(r'^full avg10=([0-9]+(?:\.[0-9]+)?)\s',
                               (NATIVE_CGROUP / meter).read_text(), re.MULTILINE)
            if parser is None:
                raise ValueError
            pressure.append(float(parser.group(1)))
    except (OSError, ValueError):
        raise RuntimeError('HOLD_BACKGROUND_RESOURCE_UNAVAILABLE') from None
    if limit - current < BACKGROUND_RAM_FLOOR:
        raise RuntimeError('HOLD_BACKGROUND_RAM_HEADROOM')
    if pressure[0] > 0 or pressure[1] >= 1:
        raise RuntimeError('HOLD_BACKGROUND_PRESSURE')


def read_priority_value(name):
    path = plain_path(PRIORITY_STATE / name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError
        data = os.read(fd, 129)
        if len(data) != info.st_size:
            raise ValueError
        return data.decode('ascii').strip()
    finally:
        os.close(fd)


def poll_checkpoint(checkpoint):
    """Recheck controls at most five times per second inside byte loops."""
    next_check = 0.0

    def poll():
        nonlocal next_check
        now = time.monotonic()
        if now >= next_check:
            checkpoint()
            next_check = now + 0.2

    return poll


def plain_path(value, must_exist=True):
    """Fail closed on unreadable ancestors, including optional receipt paths.

    Path.is_symlink() can return False on ELOOP/EACCES on newer Python,
    silently treating a blocked model/receipt parent as a safe directory.
    A genuinely absent path is still permitted for owner-created receipts;
    this is a preflight guard, not a substitute for atomic/no-follow writes.
    """
    p = Path(os.path.abspath(value))
    missing = False
    for part in (*reversed(p.parents), p):
        if missing:
            continue
        try:
            mode = os.lstat(part).st_mode
        except FileNotFoundError:
            missing = True
            continue
        except OSError as exc:
            raise ValueError('HOLD_PATH_UNREADABLE') from exc
        if stat.S_ISLNK(mode):
            raise ValueError('HOLD_SYMLINK_PATH')
        if part != p and not stat.S_ISDIR(mode):
            raise ValueError('HOLD_NON_DIRECTORY_PARENT')
    if must_exist:
        p.stat()
    return p


def assert_model(value):
    p = plain_path(value)
    s = p.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size <= 0 or p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError('HOLD_NOT_REGULAR_MODEL')
    if any(x.lower() in BLOCKED_PARTS or x.lower().startswith('checkpoint-') for x in p.parts):
        raise ValueError('HOLD_PROTECTED_PATH')
    if re.match(r'^(optimizer|scheduler|scaler|rng_state|training_args|adapter|lora|qlora)([._-]|$)', p.name.lower()):
        raise ValueError('HOLD_PROTECTED_TRAINING_STATE')
    if s.st_nlink != 1:
        raise ValueError('HOLD_HARDLINK_MODEL')
    return p


def identity(p):
    s = p.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def sha256(path, checkpoint=None):
    h = hashlib.sha256()
    poll = poll_checkpoint(checkpoint) if checkpoint else None
    read_started = time.monotonic()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(MIB if checkpoint else 4 * MIB), b''):
            if poll:
                poll()
            h.update(chunk)
            if poll:
                remaining = len(chunk) / BACKGROUND_HASH_RATE - (time.monotonic() - read_started)
                if remaining > 0:
                    time.sleep(remaining)
                read_started = time.monotonic()
    if checkpoint:
        checkpoint()
    return h.hexdigest()


def assert_remote(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}:[^\x00-\x1f\x7f]+', value):
        raise ValueError('HOLD_CONFIGURED_REMOTE_REQUIRED')
    if '..' in value.split(':', 1)[1].split('/') or '?' in value or '#' in value:
        raise ValueError('HOLD_REMOTE_PATH')
    return value.rstrip('/')


def command(args, timeout=3600, checkpoint=None):
    """Cooperatively cancel only our exact rclone child on owner STOP or timeout.

    Background transfers must not continue consuming I/O after a manual STOP.
    No native trainer/dispatcher process IDs are inferred or signalled here.
    """
    checkpoint = checkpoint or assert_owner_stop_clear
    checkpoint()
    deadline = time.monotonic() + timeout
    # Provider stderr can disclose signed URLs or credentials: never capture it.
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            checkpoint()
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError('HOLD_TRANSFER_TIMEOUT')
            try:
                output, _ = proc.communicate(timeout=min(0.2, left))
                break
            except subprocess.TimeoutExpired:
                continue
        checkpoint()
        if proc.returncode != 0:
            raise RuntimeError('HOLD_RCLONE_EXIT_' + str(proc.returncode))
        return output
    finally:
        if proc.poll() is None:
            proc.terminate()  # Exactly the process created above.
            try:
                proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
        if proc.stdout is not None:
            proc.stdout.close()


def stream_sha256(remote, size, timeout=3600, *, checkpoint=None, limits=()):
    """Hash complete remote bytes without disk spool; STOP is live throughout.

    This is the existing offsite *readback* used to issue a source receipt.
    Manual owner STOP must interrupt the data stream and post-EOF wait;
    a success receipt is forbidden if STOP is latched even after all bytes.
    Only the rclone child created here may be signalled.
    """
    remote = assert_remote(remote)
    if type(size) is not int or size < 1:
        raise ValueError('HOLD_READBACK_SIZE')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('HOLD_READBACK_TIMEOUT')
    poll = poll_checkpoint(checkpoint) if checkpoint else assert_owner_stop_clear
    checkpoint = checkpoint or assert_owner_stop_clear
    checkpoint()
    digest, count = hashlib.sha256(), 0
    deadline = time.monotonic() + timeout
    p = subprocess.Popen(
        ['rclone', 'cat', remote, '--retries', '2', '--low-level-retries', '2', *limits],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ)
            while sel.get_map():
                poll()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('HOLD_READBACK_TIMEOUT')
                for key, _ in sel.select(min(0.2, remaining)):
                    chunk = os.read(key.fd, min(1024 * 1024, size - count + 1))
                    if not chunk:
                        sel.unregister(key.fileobj)
                    else:
                        count += len(chunk)
                        if count > size:
                            raise RuntimeError('HOLD_READBACK_OVERSIZE')
                        digest.update(chunk)
        while p.poll() is None:
            poll()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('HOLD_READBACK_TIMEOUT')
            try:
                p.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                pass
        checkpoint()
        if p.returncode != 0 or count != size:
            raise RuntimeError('HOLD_READBACK_INCOMPLETE')
        return digest.hexdigest()
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()
        p.stdout.close()


MAX_VERIFIED_RANGE_BYTES = 1024 * 1024
MAX_RANGE_METADATA_BYTES = 64 * 1024


def _range_size_with_stop(remote, deadline, stop_probe):
    """Bounded metadata read sharing the range deadline and owner STOP."""
    proc = subprocess.Popen(
        ['rclone', 'size', '--json', remote],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    payload = bytearray()
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while sel.get_map():
                if stop_probe():
                    raise RuntimeError('HOLD_OWNER_STOP')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('HOLD_RANGE_TIMEOUT')
                for key, _ in sel.select(min(0.2, remaining)):
                    chunk = os.read(key.fd, min(4096, MAX_RANGE_METADATA_BYTES + 1 - len(payload)))
                    if not chunk:
                        sel.unregister(key.fileobj)
                        continue
                    payload.extend(chunk)
                    if len(payload) > MAX_RANGE_METADATA_BYTES:
                        raise RuntimeError('HOLD_RANGE_METADATA_OVERSIZE')
        while proc.poll() is None:
            if stop_probe():
                raise RuntimeError('HOLD_OWNER_STOP')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('HOLD_RANGE_TIMEOUT')
            try:
                proc.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                pass
        if proc.returncode != 0:
            raise RuntimeError('HOLD_RANGE_METADATA_INCOMPLETE')
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError('HOLD_RANGE_METADATA_INVALID') from None
        if (not isinstance(result, dict) or type(result.get('count')) is not int
                or type(result.get('bytes')) is not int):
            raise RuntimeError('HOLD_RANGE_METADATA_INVALID')
        return result
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()


def read_verified_range(remote, offset, length, object_size, block_sha256, timeout=30, stop_probe=None):
    """Bounded, immutable-hash-gated rclone range read; NO FUSE/SSD file/engine launch.

    Callers must obtain *independent* trusted SHA256 for this exact block before
    using it. A whole-object SHA is not a block SHA; this is not a Maya mmap
    adapter or authorization to consume unverified Google Drive data.
    """
    remote = assert_remote(remote)
    if (not remote.lower().endswith(tuple(ALLOWED_SUFFIX))
            or '/' not in remote.split(':', 1)[1]):
        raise ValueError('HOLD_RANGE_REMOTE_MODEL_REQUIRED')
    if (any(type(n) is not int for n in (offset, length, object_size))
            or object_size <= 0 or offset < 0 or length < 1
            or length > MAX_VERIFIED_RANGE_BYTES or offset >= object_size
            or length > object_size - offset):
        raise ValueError('HOLD_RANGE_BOUNDS')
    if not isinstance(block_sha256, str) or not SHA.fullmatch(block_sha256):
        raise ValueError('HOLD_RANGE_BLOCK_SHA_REQUIRED')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('HOLD_RANGE_TIMEOUT')
    caller_probe = stop_probe
    def stop_probe():
        # A caller-supplied probe is additive, never a replacement for the
        # original owner STOP and MODEL_UPDATE controls.
        stopped, maintenance = owner_control_flags()
        return stopped or maintenance or (caller_probe is not None and caller_probe())
    if stop_probe():
        raise RuntimeError('HOLD_OWNER_STOP')
    deadline = time.monotonic() + timeout
    meta = _range_size_with_stop(remote, deadline, stop_probe)
    if meta['count'] != 1 or meta['bytes'] != object_size:
        raise RuntimeError('HOLD_RANGE_OBJECT_SIZE_CHANGED')
    if stop_probe():
        raise RuntimeError('HOLD_OWNER_STOP')
    if deadline - time.monotonic() <= 0:
        raise RuntimeError('HOLD_RANGE_TIMEOUT')
    proc = subprocess.Popen(
        ['rclone', 'cat', remote, '--offset', str(offset), '--count', str(length),
         '--retries', '2', '--low-level-retries', '2'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = []
    count = 0
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                if stop_probe():
                    raise RuntimeError('HOLD_OWNER_STOP')
                left = deadline - time.monotonic()
                if left <= 0:
                    raise RuntimeError('HOLD_RANGE_TIMEOUT')
                if not selector.select(min(left, 0.2)):
                    continue
                data = os.read(proc.stdout.fileno(), min(65536, length + 1 - count))
                if not data:
                    break
                count += len(data)
                if count > length:
                    raise RuntimeError('HOLD_RANGE_OVERSIZE')
                chunks.append(data)
        while proc.poll() is None:
            if stop_probe():
                raise RuntimeError('HOLD_OWNER_STOP')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('HOLD_RANGE_TIMEOUT')
            try:
                proc.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                pass
        if proc.returncode != 0 or count != length:
            raise RuntimeError('HOLD_RANGE_INCOMPLETE')
        if stop_probe():
            raise RuntimeError('HOLD_OWNER_STOP')
        data = b''.join(chunks)
        if hashlib.sha256(data).hexdigest() != block_sha256:
            raise RuntimeError('HOLD_RANGE_SHA_MISMATCH')
        return data
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()


def atomic_json(path, obj):
    path = plain_path(path, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.nox-receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        d = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def maintenance_lock(root):
    import fcntl
    root = plain_path(root, False)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root/'.cold-storage.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('HOLD_STORAGE_WRITER_BUSY') from None
        yield
    finally:
        os.close(fd)


@contextmanager
def background_transfer_slot(enabled):
    if not enabled:
        yield
        return
    background_storage_checkpoint()
    with maintenance_lock(PRIORITY_STATE):
        yield


def copy_verified(job):
    src = assert_model(job['source'])
    background = job.get('background', False)
    if background:
        background_storage_checkpoint()
        if any('engram' in segment.lower() or segment.lower().startswith('deepseek-v4.1')
               for segment in src.parts):
            raise ValueError('HOLD_BACKGROUND_SERVING_MODEL')
        assert_not_open(src)
    before = identity(src)
    digest = sha256(src, background_storage_checkpoint) if background else sha256(src)
    expected = job.get('sha256')
    if expected is not None and (not SHA.fullmatch(expected) or digest != expected):
        raise ValueError('HOLD_SOURCE_SHA_MISMATCH')
    dest = assert_remote(job['remote']) + '/' + digest + '/' + src.name
    args = ['rclone','copyto',str(src),dest,'--immutable','--retries','3',
            '--transfers','1','--checkers','1','--multi-thread-streams','1']
    if background:
        command([*args, *BACKGROUND_RCLONE_LIMITS], job['timeout'], background_storage_checkpoint)
        remote_digest = stream_sha256(dest, before[2], job['timeout'],
                                      checkpoint=background_storage_checkpoint,
                                      limits=BACKGROUND_RCLONE_LIMITS)
    else:
        command(args, job['timeout'])
        remote_digest = stream_sha256(dest, before[2], job['timeout'])
    if remote_digest != digest:
        raise RuntimeError('HOLD_REMOTE_SHA_MISMATCH')
    if assert_model(src) != src or identity(src) != before:
        raise RuntimeError('HOLD_SOURCE_CHANGED_DURING_TRANSFER')
    if background:
        background_storage_checkpoint()
    rid = hashlib.sha256(str(src).encode()).hexdigest()[:16] + '-' + digest
    dest_receipt = Path(job['receipt_dir'])/(rid+'.json')
    row = {'schema_version':2,'source':str(src),'destination':dest,'size':before[2],
           'sha256':digest,'identity':before,'readback_verified':True,
           'verified_at':time.time(),'source_deleted':False,'worker_pid':os.getpid()}
    atomic_json(dest_receipt, row)
    return {'receipt':str(dest_receipt), **row}


def fresh_manifest(path, source):
    p = plain_path(path)
    if p.stat().st_size > 1024*1024:
        raise ValueError('HOLD_ACTIVE_MANIFEST_TOO_LARGE')
    obj = json.loads(p.read_text())
    ts = obj.get('generated_at')
    if type(ts) not in (int,float) or not math.isfinite(ts) or not -5 <= time.time()-ts <= 300:
        raise ValueError('HOLD_ACTIVE_MANIFEST_STALE')
    for name in ('active_paths','protected_paths','evict_paths'):
        if not isinstance(obj.get(name),list) or any(not isinstance(v,str) for v in obj[name]):
            raise ValueError('HOLD_ACTIVE_MANIFEST_SCHEMA')
    src = source.resolve()
    for value in obj['active_paths'] + obj['protected_paths']:
        p = Path(value).resolve()
        if src == p or p in src.parents:
            raise ValueError('HOLD_ACTIVE_OR_PROTECTED_MODEL')
    if str(src) not in {str(Path(v).resolve()) for v in obj['evict_paths']}:
        raise ValueError('HOLD_NOT_EXPLICITLY_EVICTABLE')


def assert_not_open(source, proc_root=Path('/proc')):
    """Fail closed on open file descriptors OR mapped inodes, including alias paths."""
    info = source.stat()
    target = (info.st_dev, info.st_ino)
    proc = proc_root
    if not proc.is_dir():
        raise RuntimeError('HOLD_NATIVE_PROCESS_INSPECTION_UNAVAILABLE')
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            for link in (pid/'fd').iterdir():
                try:
                    fd_info = link.stat()  # Follow /proc fd to the actual inode, not its display path.
                    if stat.S_ISREG(fd_info.st_mode) and (fd_info.st_dev, fd_info.st_ino) == target:
                        raise RuntimeError('HOLD_MODEL_OPEN_BY_PROCESS')
                except (FileNotFoundError, ProcessLookupError):
                    continue
            for line in (pid/'maps').read_text(errors='replace').splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) < 5 or not fields[4].isdigit() or int(fields[4]) == 0:
                    continue
                try:
                    major, minor = fields[3].split(':', 1)
                    dev = os.makedev(int(major, 16), int(minor, 16))
                except (ValueError, OverflowError):
                    raise RuntimeError('HOLD_PROCESS_MAPS_INODE_UNREADABLE') from None
                if (dev, int(fields[4])) == target:
                    raise RuntimeError('HOLD_MODEL_MEMORY_MAPPED')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise RuntimeError('HOLD_PROCESS_SCAN_PERMISSION') from None


def independent_restore(row, restore_test_dir, timeout=3600):
    """Full offsite recovery into an isolated mount; remote SHA alone is not proof."""
    if not restore_test_dir:
        raise RuntimeError('HOLD_INDEPENDENT_RESTORE_REQUIRED')
    source = assert_model(row['source'])
    root = plain_path(restore_test_dir)
    if not root.is_dir():
        raise ValueError('HOLD_RESTORE_TEST_DIR_REQUIRED')
    if root.stat().st_dev == source.stat().st_dev:
        raise ValueError('HOLD_RESTORE_NOT_INDEPENDENT_FILESYSTEM')
    remote = assert_remote(row['destination'])
    if remote.startswith('nox_pc:'):
        raise RuntimeError('HOLD_PC_ONLY_COPY_NEVER_AUTHORIZES_EVICTION')
    size, expected = row.get('size'), row.get('sha256')
    if type(size) is not int or size <= 0 or not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise ValueError('HOLD_RESTORE_RECEIPT_SCHEMA')
    if root.is_relative_to(Path('/dev/shm')):
        if memory_budget(root, 12) < size:
            raise RuntimeError('HOLD_RESTORE_RAM_RESERVE')
    elif shutil.disk_usage(root).free < size + 12 * GIB:
        raise RuntimeError('HOLD_RESTORE_DISK_RESERVE')
    fd, temp = tempfile.mkstemp(prefix='.nox-independent-restore-', dir=root)
    os.close(fd)
    try:
        command(['rclone', 'copyto', remote, temp, '--transfers', '1',
                 '--multi-thread-streams', '1', '--retries', '2'], timeout)
        if Path(temp).stat().st_size != size or sha256(temp) != expected:
            raise RuntimeError('HOLD_INDEPENDENT_RESTORE_SHA_MISMATCH')
    finally:
        Path(temp).unlink(missing_ok=True)
    return True


def evict_verified(row, active_manifest, restore_test_dir=None, timeout=3600):
    if str(row.get('destination', '')).startswith('nox_pc:'):
        raise RuntimeError('HOLD_PC_ONLY_COPY_NEVER_AUTHORIZES_EVICTION')
    if not active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    assert_owner_stop_clear()
    src = assert_model(row['source'])
    fresh_manifest(active_manifest, src)
    if identity(src)!=row['identity'] or sha256(src)!=row['sha256']:
        raise RuntimeError('HOLD_SOURCE_CHANGED_BEFORE_EVICTION')
    independent_restore(row, restore_test_dir, timeout)
    if identity(src)!=row['identity'] or sha256(src)!=row['sha256']:
        raise RuntimeError('HOLD_SOURCE_CHANGED_AFTER_RESTORE')
    assert_not_open(src)
    assert_owner_stop_clear()  # STOP can appear during remote restore.
    fresh_manifest(active_manifest, src)
    if identity(src)!=row['identity']:
        raise RuntimeError('HOLD_SOURCE_CHANGED_BEFORE_UNLINK')
    before, allocated = shutil.disk_usage(src.parent).free, src.stat().st_blocks*512
    # A serving process can open/mmap the model after the earlier scan and
    # manifest read. Reinspect immediately before irreversible unlink.
    # This narrows the TOCTOU window; the native controller lease is still mandatory.
    assert_not_open(src)
    assert_owner_stop_clear()  # Last check; native single-writer lease remains mandatory.
    src.unlink()  # One exact verified regular file; never recursive deletion.
    row.update(independent_restore_verified=True, source_deleted=True,
               source_logical_bytes_removed=row['size'],
               source_allocated_bytes=allocated,
               observed_free_bytes_delta=shutil.disk_usage(src.parent).free-before)
    atomic_json(Path(row['receipt']), {k:v for k,v in row.items() if k!='receipt'})
    return row


def upload(a):
    if a.background and a.evict:
        raise ValueError('HOLD_BACKGROUND_EVICTION_FORBIDDEN')
    if a.evict and not a.active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    if a.evict and not a.restore_test_dir:
        raise RuntimeError('HOLD_INDEPENDENT_RESTORE_REQUIRED')
    with background_transfer_slot(a.background), maintenance_lock(a.receipt_dir):
        row=copy_verified({'source':a.file,'remote':a.remote,'receipt_dir':a.receipt_dir,
                           'timeout':a.timeout,'sha256':a.sha256,'background':a.background})
        if a.evict:
            evict_verified(row,a.active_manifest,a.restore_test_dir,a.timeout)
        print(json.dumps(row,ensure_ascii=False))


def batch(a):
    if a.background and a.evict:
        raise ValueError('HOLD_BACKGROUND_EVICTION_FORBIDDEN')
    p=plain_path(a.manifest)
    if p.stat().st_size > 1024*1024:
        raise ValueError('HOLD_BATCH_TOO_LARGE')
    rows=json.loads(p.read_text()).get('files')
    if not isinstance(rows,list) or not 1<=len(rows)<=4096:
        raise ValueError('HOLD_BATCH_SCHEMA')
    jobs=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'path','sha256'} or not SHA.fullmatch(str(row['sha256'])):
            raise ValueError('HOLD_BATCH_FILE_SCHEMA')
        jobs.append({'source':str(assert_model(row['path'])),'sha256':row['sha256'],
                     'remote':assert_remote(a.remote),'receipt_dir':a.receipt_dir,'timeout':a.timeout,
                     'background':a.background})
    if len({j['source'] for j in jobs}) != len(jobs):
        raise ValueError('HOLD_DUPLICATE_BATCH_SOURCE')
    if a.evict and not a.active_manifest:
        raise ValueError('HOLD_ACTIVE_MANIFEST_REQUIRED')
    if a.evict and not a.restore_test_dir:
        raise RuntimeError('HOLD_INDEPENDENT_RESTORE_REQUIRED')
    with background_transfer_slot(a.background), maintenance_lock(a.receipt_dir):
        done, errors = [], []
        if a.background:
            for job in jobs:
                try:
                    done.append(copy_verified(job))
                except Exception as ex:
                    code = str(ex)
                    errors.append({'source':job['source'],
                                   'error':code if re.fullmatch(r'HOLD_[A-Z0-9_]+', code) else type(ex).__name__})
                    break
        else:
            with ProcessPoolExecutor(max_workers=a.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
                pending={pool.submit(copy_verified,j):j for j in jobs}
                for future in as_completed(pending):
                    try:
                        done.append(future.result())
                    except Exception as ex:
                        errors.append({'source':pending[future]['source'],'error':type(ex).__name__})
        summary={'requested':len(jobs),'copies_verified':len(done),'errors':errors,
                 'sources_deleted':0,'receipts':[r['receipt'] for r in done]}
        atomic_json(Path(a.receipt_dir)/'last-batch.json',summary)
        if errors:
            raise RuntimeError('HOLD_BATCH_INCOMPLETE_SOURCES_RETAINED')
        if a.evict:
            for row in done:
                evict_verified(row,a.active_manifest,a.restore_test_dir,a.timeout)
                summary['sources_deleted']+=1
                atomic_json(Path(a.receipt_dir)/'last-batch.json',summary)
        print(json.dumps(summary,ensure_ascii=False))


def memory_budget(dest_dir, reserve_gib):
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(fields['MemAvailable'].split()[0])*1024
    root=Path('/sys/fs/cgroup')
    if (root/'memory.max').is_file():
        cap=(root/'memory.max').read_text().strip()
        used=int((root/'memory.current').read_text())
        if cap!='max':
            available=min(available,max(0,int(cap)-used))
    elif (root/'memory/memory.limit_in_bytes').is_file():
        cap=int((root/'memory/memory.limit_in_bytes').read_text())
        used=int((root/'memory/memory.usage_in_bytes').read_text())
        available=min(available,max(0,cap-used))
    else:
        raise RuntimeError('HOLD_CGROUP_MEMORY_LIMIT_UNKNOWN')
    return min(available,shutil.disk_usage(dest_dir).free)-reserve_gib*GIB


def pc_link_target(link):
    """Resolve the owner-created reverse SSH link without shell execution."""
    if (not isinstance(link, dict) or link.get('schema') != 'NOX_PC_LINK_V1'
            or link.get('instance_id') != 60509551 or link.get('reverse_host') != '127.0.0.1'
            or type(link.get('reverse_port')) is not int or link['reverse_port'] != 46051):
        raise ValueError('HOLD_PC_LINK_IDENTITY')
    user = link.get('pc_user')
    if (not isinstance(user, str) or not re.fullmatch(r'[A-Za-z0-9_.@\\ -]{1,128}', user)
            or user != user.strip() or user.startswith('-')):
        raise ValueError('HOLD_PC_LINK_USER')
    location = link.get('backup_root')
    if not isinstance(location, str) or any(ord(c) < 32 for c in location):
        raise ValueError('HOLD_PC_BACKUP_ROOT')
    path = PureWindowsPath(location)
    if (not path.is_absolute() or not re.fullmatch(r'[A-Za-z]:', path.drive)
            or '..' in path.parts or any(c in location for c in '?*<>|"#')):
        raise ValueError('HOLD_PC_BACKUP_ROOT')
    raw = link.get('pc_host_key', '')
    if not isinstance(raw, str) or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}', raw):
        raise ValueError('HOLD_PC_HOST_KEY')
    try:
        decoded = base64.b64decode(raw.split()[1], validate=True)
        algorithm_size = struct.unpack('>I', decoded[:4])[0]
        key_size = struct.unpack('>I', decoded[4+algorithm_size:8+algorithm_size])[0]
        if decoded[4:4+algorithm_size] != b'ssh-ed25519' or key_size != 32 or len(decoded) != 8+algorithm_size+key_size:
            raise ValueError('invalid key')
    except Exception:
        raise ValueError('HOLD_PC_HOST_KEY') from None
    fingerprint = 'SHA256:'+base64.b64encode(hashlib.sha256(decoded).digest()).decode().rstrip('=')
    if link.get('pc_host_key_sha256') != fingerprint:
        raise ValueError('HOLD_PC_HOST_KEY_FINGERPRINT')
    return {'user':user, 'host_key':raw, 'fingerprint':fingerprint,
            'remote_root':'nox_pc:/'+path.as_posix().rstrip('/'),
            'backup_root':str(path)}


def configure_pc(root=Path('/root/nox')):
    """Bind the existing SFTP backend to the persistent owner's PC link.

    Writes only a dedicated local config and known_hosts entry. It neither
    opens a shell nor claims connectivity/readback. Every subsequent transfer
    authenticates the pinned host key; load retains its normal RAM/SHA gates.
    """
    root = plain_path(root)
    folder = plain_path(root/'state/pc_shell')
    connection = plain_path(folder/'connection.json')
    key = plain_path(folder/'operator_ed25519')
    for path in (connection, key):
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError('HOLD_PC_LINK_PRIVATE_FILE_MODE')
    if connection.stat().st_size > 32000:
        raise ValueError('HOLD_PC_LINK_METADATA_SIZE')
    target = pc_link_target(json.loads(connection.read_text()))
    known = plain_path(folder/'rclone_known_hosts', False)
    config = plain_path(root/'state/cold_pc.conf', False)
    payloads = {
        known:'[127.0.0.1]:46051 '+target['host_key']+'\n',
        config:('[nox_pc]\ntype = sftp\nhost = 127.0.0.1\nport = 46051\nuser = '+target['user']+
                '\nkey_file = '+str(key)+'\nknown_hosts_file = '+str(known)+
                '\nshell_type = none\ndisable_hashcheck = true\n'),
    }
    for path, text in payloads.items():
        fd, tmp = tempfile.mkstemp(prefix='.pc-target-', dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(text); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    return {'schema':'NOX_PC_COLD_TARGET_V1', 'configured':True, 'connectivity_verified':False,
            'server_readback_verified':False, 'eviction_allowed':False,
            'config':str(config), 'remote_root':target['remote_root'],
            'backup_remote_root':target['remote_root']+'/BACKUPS',
            'warm_remote_root':target['remote_root']+'/WARM',
            'note':'PC link must be live; full SHA readback and cgroup/RAM reserve are still required.'}


def load(a):
    # RAM hydration is background work: the owner's STOP wins even before
    # the metadata rclone request. A STOP must never publish new RAM weights.
    assert_owner_stop_clear()
    remote=assert_remote(a.remote)
    if not SHA.fullmatch(a.sha256):
        raise ValueError('HOLD_EXPECTED_SHA_REQUIRED')
    dest_dir=plain_path(a.ram_dir)
    if not dest_dir.is_dir() or not dest_dir.is_relative_to(Path('/dev/shm')):
        raise ValueError('HOLD_RAM_PATH_REQUIRED')
    name=remote.rsplit('/',1)[-1]
    if '/' not in remote.split(':',1)[1] or Path(name).suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError('HOLD_REMOTE_MODEL_FILE_REQUIRED')
    meta=json.loads(command(['rclone','size','--json',remote],a.timeout))
    size=meta.get('bytes',0)
    if type(size) is not int or size<=0 or meta.get('count')!=1:
        raise ValueError('HOLD_REMOTE_NOT_ONE_FILE')
    with maintenance_lock(dest_dir):
        assert_owner_stop_clear()
        if memory_budget(dest_dir,a.reserve_gib)<size:
            raise RuntimeError('HOLD_RAM_RESERVE')
        dest=dest_dir/name
        if os.path.lexists(dest):
            raise FileExistsError('HOLD_RAM_DESTINATION_EXISTS')
        fd,tmp=tempfile.mkstemp(prefix='.nox-load-',dir=dest_dir)
        os.close(fd); temp=Path(tmp)
        try:
            command(['rclone','copyto',remote,str(temp),'--transfers','1','--multi-thread-streams','1'],a.timeout)
            if temp.stat().st_size!=size or sha256(temp)!=a.sha256:
                raise RuntimeError('HOLD_RAM_SHA_MISMATCH')
            assert_owner_stop_clear()  # Stop may be raised during remote transfer.
            # A concurrent chat/trainer may consume RAM during the transfer.
            # Recheck actual cgroup+tmpfs headroom before publishing the model.
            if memory_budget(dest_dir,a.reserve_gib) < 0:
                raise RuntimeError('HOLD_RAM_RESERVE_AFTER_COPY')
            with temp.open('rb') as f:
                os.fsync(f.fileno())
            assert_owner_stop_clear()  # Final gate immediately before publication.
            os.link(temp,dest)  # Atomic no-replace publication, not destructive rename.
            print(json.dumps({'ram_model':str(dest),'bytes':size,'sha256':a.sha256}))
        finally:
            temp.unlink(missing_ok=True)



# SOURCE-only, read-only admission for exact DeepSeek IQ2_XXS on existing OneHost.
# Never an authorization to install, download, remove files or start another daemon.
DEEPSEEK_TOTAL_BYTES = 248834257920
DEEPSEEK_REVISION = "65d53bc8be65123e255ff02f3ded958b6dbf54fd"
DEEPSEEK_ENGRAM = "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"
DEEPSEEK_ALIAS = "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf"
DEEPSEEK_PINS = {
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf": (5780704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf": (39535781184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf": (39736712000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf": (39036908384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf": (19923784832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
    "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf": (110595290816, "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"),
}


def deepseek_storage_admission(manifest, root, verify_full=False, reserve_bytes=8*GIB):
    """Source-only seekable capacity gate. Does not attest OneHost owner authorization."""
    import mmap
    # Original MODEL_UPDATE STOP must not block safe read-only metadata audit.
    # Full SHA/mmap is resource-heavy: do not run it while stopped/maintenance.
    owner_stop_observed, maintenance_observed = owner_control_flags()
    if verify_full and (owner_stop_observed or maintenance_observed):
        raise RuntimeError('HOLD_OWNER_STOP_FULL_SCAN')
    if (not isinstance(manifest, dict)
            or manifest.get('revision') != DEEPSEEK_REVISION
            or manifest.get('repository') != "ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF"
            or manifest.get('quantization') != 'GSQ-RCO-IQ2_XXS'
            or manifest.get('total_unique_gguf_bytes') != DEEPSEEK_TOTAL_BYTES
            or type(reserve_bytes) is not int or reserve_bytes < 8*GIB):
        raise ValueError('HOLD_DEEPSEEK_MANIFEST_OR_RESERVE')
    rows = manifest.get('files')
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError('HOLD_DEEPSEEK_FILE_COUNT')
    observed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('HOLD_DEEPSEEK_FILE_SCHEMA')
        name = row['path']
        if name in observed or name not in DEEPSEEK_PINS or (row.get('bytes'), row.get('sha256')) != DEEPSEEK_PINS[name]:
            raise ValueError('HOLD_DEEPSEEK_FILE_PIN')
        observed[name] = True
    alias = manifest.get('alias')
    if (not isinstance(alias, dict) or alias.get('path') != DEEPSEEK_ALIAS
            or alias.get('target') != DEEPSEEK_ENGRAM
            or alias.get('duplicate_bytes') is not False
            or sum(v[0] for v in DEEPSEEK_PINS.values()) != DEEPSEEK_TOTAL_BYTES):
        raise ValueError('HOLD_DEEPSEEK_ENGRAM_ALIAS')
    root = plain_path(root)
    if not root.is_dir():
        raise ValueError('HOLD_DEEPSEEK_SEEKABLE_ROOT')
    filesystem = root.stat().st_dev
    # statvfs/disk_usage is only a filesystem-wide estimate. It does NOT
    # prove the owner's actual write quota, IAM, or one-native-writer lease.
    mount_readonly = bool(os.statvfs(root).f_flag & getattr(os, 'ST_RDONLY', 1))
    free = shutil.disk_usage(root).free
    unverified = verified = 0
    files = {}
    for name, (size, expected) in DEEPSEEK_PINS.items():
        path = root/name
        if not path.exists() and not path.is_symlink():
            files[name] = 'MISSING'; unverified += size; continue
        try:
            path = plain_path(path)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_dev != filesystem or info.st_size != size:
                raise RuntimeError('HOLD_FILE_SIZE_OR_MOUNT')
            if verify_full:
                original = identity(path)
                if sha256(path) != expected or identity(path) != original:
                    raise RuntimeError('HOLD_FILE_SHA_OR_IDENTITY')
                with path.open('rb') as fd:
                    for offset in (0, ((size-1)//mmap.ALLOCATIONGRANULARITY)*mmap.ALLOCATIONGRANULARITY):
                        with mmap.mmap(fd.fileno(), min(mmap.ALLOCATIONGRANULARITY,size-offset),
                                       access=mmap.ACCESS_READ, offset=offset) as data:
                            _ = data[0], data[-1]
                if identity(path) != original:
                    raise RuntimeError('HOLD_FILE_CHANGED')
                files[name] = 'SHA256_MMAP_VERIFIED'; verified += size
            else:
                files[name] = 'SIZE_ONLY_SHA_UNVERIFIED'; unverified += size
        except (OSError,ValueError,RuntimeError):
            files[name] = 'HOLD_UNVERIFIED_FILE'; unverified += size
    shared_alias = False
    alias_path = root/DEEPSEEK_ALIAS
    if os.path.lexists(alias_path):
        try:
            target = root/DEEPSEEK_ENGRAM
            shared_alias = (alias_path.resolve(strict=True) == target if alias_path.is_symlink()
                            else (alias_path.stat().st_dev, alias_path.stat().st_ino) ==
                                 (target.stat().st_dev, target.stat().st_ino))
        except (OSError,RuntimeError):
            shared_alias = False
    filesystem_capacity_candidate = (not mount_readonly and
                                     free >= unverified + reserve_bytes)
    # This source-only inspector has no owner-auth quota/lease attestation.
    # Never promote a statvfs free-space estimate into admission to transfer.
    capacity = False
    full = (filesystem_capacity_candidate and
            verified == DEEPSEEK_TOTAL_BYTES and shared_alias)
    return {'schema':'NOX_DEEPSEEK_STORAGE_READONLY_V1',
            'state':'LOCAL_ONLY_SEEKABLE_SHA_CANDIDATE' if full else 'HOLD_STORAGE_AUTH_OR_SEEKABLE_PLACEMENT',
            'unique_file_count':6,'unique_bytes':DEEPSEEK_TOTAL_BYTES,
            'metadata_only_bytes':5780704,'unverified_bytes':unverified,
            'sha256_verified_bytes':verified,'ssd_free_bytes':free,
            'ssd_reserve_bytes':reserve_bytes,'capacity_admitted':capacity,
            'filesystem_capacity_candidate':filesystem_capacity_candidate,
            'filesystem_readonly':mount_readonly,
            'owner_quota_free_bytes':None,
            'quota_status':'UNKNOWN_OWNER_NATIVE_QUOTA_READBACK_REQUIRED',
            'engram_alias_same_data':shared_alias,'files':files,
            'owner_stop_observed':owner_stop_observed,
            'owner_maintenance_flag_observed':maintenance_observed,
            'inspection_only_under_stop':owner_stop_observed or maintenance_observed,
            'owner_native_lease_verified':False,'server_oauth_verified':False,
            'native_model_installed':False,'downloads_started':0,'deleted_bytes':0}



def parser():
    p=argparse.ArgumentParser(description=__doc__)
    sp=p.add_subparsers(dest='action',required=True)
    for name in ('upload','batch'):
        q=sp.add_parser(name)
        q.add_argument('--file' if name=='upload' else '--manifest',required=True)
        q.add_argument('--remote',required=True)
        q.add_argument('--receipt-dir',default='./cold_receipts')
        q.add_argument('--active-manifest'); q.add_argument('--evict',action='store_true')
        q.add_argument('--background',action='store_true',
                       help='Use the owner chat arbiter and one constrained transfer; keep source files')
        q.add_argument('--restore-test-dir', help='Independent filesystem for full offsite restore (required for eviction)')
        q.add_argument('--timeout',type=int,default=3600)
        if name=='upload':
            q.add_argument('--sha256')
        else:
            q.add_argument('--workers',type=int,choices=range(1,7),default=6)
    q=sp.add_parser('load'); q.add_argument('--remote',required=True)
    q.add_argument('--ram-dir',default='/dev/shm/nox_models'); q.add_argument('--sha256',required=True)
    q.add_argument('--reserve-gib',type=int,default=12); q.add_argument('--timeout',type=int,default=3600)
    sp.add_parser('configure-pc', help='Configure the authenticated existing PC reverse link as a pinned SFTP target')
    return p


def main(argv=None):
    p=parser(); a=p.parse_args(argv)
    if a.action=='load' and a.reserve_gib<1:
        p.error('RAM reserve must be positive')
    if hasattr(a, 'timeout') and a.timeout<1:
        p.error('Timeout must be positive')
    try:
        if a.action == 'configure-pc':
            print(json.dumps(configure_pc(), ensure_ascii=False))
        else:
            {'upload':upload,'batch':batch,'load':load}[a.action](a)
    except Exception as ex:
        msg=str(ex)
        code=msg if re.fullmatch(r'HOLD_[A-Z0-9_]+',msg) else 'HOLD_'+type(ex).__name__.upper()
        print('NOX COLD: '+code,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
