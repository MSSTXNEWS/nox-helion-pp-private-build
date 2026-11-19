#!/usr/bin/env python3
"""Bounded NOX storage audit; exact audited ephemeral files may be reclaimed.

Default AUDIT changes only a private receipt. RECLAIM requires the exact fresh
audit receipt SHA. No model, checkpoint, source, memory database, credential,
download partial, directory tree, or active log is ever deleted here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time

ROOT = Path('/root/nox')
HOME_ROOT = Path('/root')
SHM = Path('/dev/shm')
PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
GIB = 1024 ** 3
SCHEMA = 'NOX_OWNER_STORAGE_RECLAIM_V1'
INSTANCE = 60509551
MAX_ENTRIES = 160000
MAX_DIRS = 20000
MAX_CANDIDATES = 128
MAX_DELETIONS = 32
MAX_PAGE_CACHE_FILES = 32
MAX_PAGE_CACHE_ADVISE_BYTES = 4 * GIB
MAX_PAGE_CACHE_BYTES_PER_FILE = 512 * 1024 * 1024
MIN_NATIVE_ADMISSION_HEADROOM = 2 * GIB
BROWSER_RUNTIME_HEADROOM = 4 * GIB
BROWSER_RUNTIME_DISK_HEADROOM = 7 * GIB
AUDIT_SECONDS = 24
RECLAIM_SECONDS = 35
AUDIT_TTL = 900
MEDIA_BYTES = 6938040682 + 2838303560 + 6735906897 + 253815318
LEGACY_TEACHERS = {
    '/root/nox/models/teachers/Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf': 4920745856,
    '/root/nox/models/teachers/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf': 4920733824,
    '/root/nox/models/teachers/NousResearch_DeepHermes-3-Llama-3-8B-Preview-Q4_K_M.gguf': 4920740800,
    '/root/nox/models/teachers/saiga_nemo_12b.Q4_K_M.gguf': 7477204832,
    '/root/nox/models/teachers/vikhr-nemo-12b-instruct-r-21-09-24-q4_k_m.gguf': 7477218656,
}
SAFE_TEACHER_STORAGE_HOLD_CODES = frozenset({
    'HOLD_STORAGE_SYMLINK',
    'HOLD_STORAGE_FILE_SCOPE',
    'HOLD_NOT_REGULAR_EPHEMERAL_FILE',
})
PAGE_CACHE_SAFE_CATEGORIES = frozenset({
    'PIP_DOWNLOAD_CACHE', 'PIP_WHEEL_CACHE',
    'OLD_DEBUG_LOG_ROTATION', 'INACTIVE_ELF_CORE',
})
PARTIAL = re.compile(r'(?i)(?:\.part(?:ial)?|\.incomplete|\.download|\.tmp|\.lock)(?:[.-]|$)')
WEIGHT_SUFFIX = {'.gguf', '.safetensors', '.pt', '.pth', '.bin', '.ckpt', '.onnx', '.h5', '.npz'}
PROTECTED_WORDS = {'s03', 'memory', 'memories', 'checkpoints', 'checkpoint', 'ckpt', 'lora',
                   'training', 'weights', 'models', 'scripts', 'source', 'src', 'pc_shell',
                   'credentials', 'secrets', 'backup', 'backups', 'distill', 'datasets'}
LOG_PROTECTED = re.compile(r'(?i)(?:journal|audit|memory|s03|dialog|train|checkpoint|owner|receipt|distill|learn|event|report)')


class StorageHold(RuntimeError):
    pass


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_nlink]


def plain(path):
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise StorageHold('HOLD_STORAGE_SYMLINK')
    return path


def bounded_bytes(path, maximum=262144):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise StorageHold('HOLD_STORAGE_FILE_SCOPE')
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise StorageHold('HOLD_STORAGE_FILE_SCOPE')
    return raw


def optional_json(path, maximum=262144):
    try:
        value = json.loads(bounded_bytes(path, maximum))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, StorageHold):
        return {}


def receipt_directory():
    path = plain(ROOT / 'state/owner_storage')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.geteuid():
        raise StorageHold('HOLD_STORAGE_RECEIPT_OWNER')
    os.chmod(path, 0o700)
    return path


def write_receipt(path, value, replace=False):
    path = plain(path)
    if path.parent != receipt_directory() or (path.exists() and not replace):
        raise StorageHold('HOLD_STORAGE_RECEIPT_EXISTS_OR_SCOPE')
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    if len(raw) > 2 * 1024 * 1024:
        raise StorageHold('HOLD_STORAGE_RECEIPT_SIZE')
    fd, temporary = tempfile.mkstemp(prefix='.storage-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest_bytes(raw)


def write_receipt_exclusive(path, value):
    """Create a new receipt with O_EXCL; never replace an earlier action receipt."""
    path = plain(path)
    if path.parent != receipt_directory():
        raise StorageHold('HOLD_STORAGE_RECEIPT_EXISTS_OR_SCOPE')
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    if len(raw) > 2 * 1024 * 1024:
        raise StorageHold('HOLD_STORAGE_RECEIPT_SIZE')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise StorageHold('HOLD_PAGE_CACHE_ONE_SHOT_ALREADY_USED') from exc
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd >= 0:
            os.close(fd)
    return digest_bytes(raw)


def root_specs():
    # Reclaimable owner-approved areas first: NOX and venv can each contain
    # >100k protected files and exhaust the bounded audit budget before logs.
    # The same inode is counted only once by audit(); no new deletion kind.
    return [('PIP_CACHE', HOME_ROOT / '.cache/pip'),
            ('NOX_LOGS', ROOT / 'logs'), ('NOX_TMP', ROOT / 'tmp'),
            ('SUPERVISOR_LOGS', Path('/var/log/supervisor')),
            ('RAM_TMPFS', SHM),
            ('NOX', ROOT),
            ('HF_CACHE_PROTECTED', HOME_ROOT / '.cache/huggingface'),
            ('TORCH_CACHE_PROTECTED', HOME_ROOT / '.cache/torch'),
            ('UV_CACHE_PROTECTED', HOME_ROOT / '.cache/uv'),
            ('VOLTA_ENVIRONMENT', HOME_ROOT / 'venv_volta'),
            ('OTHER_ENVIRONMENTS', HOME_ROOT / 'venv_v100'),
            ('OTHER_ENVIRONMENTS', HOME_ROOT / 'venv_new')]


def category(label, path):
    if label != 'NOX':
        return label
    relative = path.relative_to(ROOT)
    parts = tuple(x.lower() for x in relative.parts)
    if 'merged_hf' in parts:
        return 'TRAINING_HF_BASE_PROTECTED'
    if parts[:2] == ('progress_pull_t784u', 'gguf') or (parts and parts[0] == 'gguf'):
        return 'CHAT_GGUF_PROTECTED'
    if parts[:2] in (('models', 'teachers'), ('models', 'teachers_ondisk')):
        return 'TEACHER_WEIGHTS_PROTECTED'
    if parts[:2] == ('media', 'models'):
        return 'MEDIA_WEIGHTS_PROTECTED'
    if parts and parts[0] in ('lora', 'ckpt', 'checkpoints'):
        return 'TRAINING_CHECKPOINTS_PROTECTED'
    if parts and parts[0] in ('memory', 'kb', 'state'):
        return 'MEMORY_STATE_CREDENTIALS_PROTECTED'
    if 'venv' in parts or 'site-packages' in parts:
        return 'NOX_ENVIRONMENTS_PROTECTED'
    if parts and parts[0] in ('models', 'weights'):
        return 'OTHER_MODEL_WEIGHTS_PROTECTED'
    if parts and parts[0] == 'logs':
        return 'NOX_LOGS'
    if parts and parts[0] in ('backup', 'backups'):
        return 'BACKUPS_PROTECTED'
    if parts and parts[0] in ('scripts', 'src', 'source', 'media'):
        return 'SOURCE_RUNTIME_PROTECTED'
    return 'NOX_OTHER_PROTECTED'


def known_aliases():
    result = []
    for label, path in (('ACTIVE_CHAT', ROOT / 'models/current.gguf'),
                        ('DISK_TEACHER', ROOT / 'models/teachers_ondisk/current.gguf')):
        try:
            if not path.is_symlink():
                continue
            target = Path(os.path.abspath(path.parent / os.readlink(path)))
            if not target.is_relative_to(ROOT):
                continue
            plain(target)
            info = target.stat()
            if stat.S_ISREG(info.st_mode):
                result.append({'alias': label, 'target_identity': [info.st_dev, info.st_ino],
                               'logical_bytes_referenced': info.st_size,
                               'additional_weight_copy': False})
        except (OSError, StorageHold):
            pass
    return result


def process_usage(deadline, ignore_fd=None):
    """Only inode metadata and tool-name booleans; no argv/maps text is exported."""
    used, deleted = set(), {}
    counts = Counter()
    active_package_manager = False
    complete = True
    try:
        with os.scandir(PROC) as entries:
            pids = [entry.name for entry in entries if entry.name.isdigit()]
        if len(pids) > 2048:
            raise StorageHold('HOLD_PROCESS_SCAN_BUDGET')
        for pid in pids:
            if time.monotonic() > deadline:
                raise StorageHold('HOLD_PROCESS_SCAN_BUDGET')
            process = PROC / pid
            try:
                with (process / 'cmdline').open('rb') as stream:
                    argv = stream.read(8193)
                if len(argv) > 8192:
                    raise StorageHold('HOLD_PROCESS_SCAN_BUDGET')
                args = argv.split(b'\0')
                command = os.path.basename(args[0]) if args else b''
                active_package_manager |= (bool(re.fullmatch(rb'(?:pip\d*(?:\.\d+)?|uv)', command))
                                           or any(args[i:i + 2] == [b'-m', b'pip'] for i in range(len(args))))
                with os.scandir(process / 'fd') as fds:
                    for entry in fds:
                        if ignore_fd == (int(pid), entry.name):
                            continue
                        counts['file_descriptors'] += 1
                        if counts['file_descriptors'] > 40000 or time.monotonic() > deadline:
                            raise StorageHold('HOLD_PROCESS_SCAN_BUDGET')
                        try:
                            info = entry.stat(follow_symlinks=True)
                            if not stat.S_ISREG(info.st_mode):
                                continue
                            key = (info.st_dev, info.st_ino)
                            used.add(key)
                            if os.readlink(entry.path).endswith(' (deleted)'):
                                deleted[key] = info.st_blocks * 512
                        except (FileNotFoundError, ProcessLookupError):
                            continue
                with (process / 'maps').open('rb') as stream:
                    raw = stream.read(2 * 1024 * 1024 + 1)
                counts['map_bytes'] += len(raw)
                if len(raw) > 2 * 1024 * 1024 or counts['map_bytes'] > 64 * 1024 * 1024:
                    raise StorageHold('HOLD_PROCESS_SCAN_BUDGET')
                for line in raw.splitlines():
                    fields = line.split(None, 5)
                    if len(fields) >= 5 and fields[4].isdigit() and int(fields[4]):
                        major, minor = fields[3].split(b':')
                        used.add((os.makedev(int(major, 16), int(minor, 16)), int(fields[4])))
                counts['processes'] += 1
            except (FileNotFoundError, ProcessLookupError):
                continue  # Process/descriptor exited during this bounded scan.
            except (PermissionError, OSError, ValueError):
                complete = False
                counts['unreadable_processes'] += 1
    except (OSError, StorageHold):
        complete = False
        counts['scan_budget_or_access_failures'] += 1
    return {'used': used, 'complete': complete, 'active_package_manager': active_package_manager,
            'counts': dict(counts), 'deleted_open_allocated_bytes': sum(deleted.values()),
            'deleted_open_unique_inodes': len(deleted), 'scope': 'CURRENT_PID_NAMESPACE'}


def prefix(path, count=32):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise StorageHold('HOLD_NOT_REGULAR_EPHEMERAL_FILE')
        return stream.read(count)


def teacher_candidate_review(path, info=None, usage=None, observation_error=None):
    """Explain why a known legacy teacher remains held; never authorizes deletion."""
    path = Path(path)
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return None
    expected = LEGACY_TEACHERS.get(str(Path('/root/nox') / relative))
    if expected is None:
        return None
    path = str(path)
    codes = ['TEACHER_WEIGHTS_PROTECTED',
             'TWO_INDEPENDENT_SHA_VERIFIED_PC_AND_DRIVE_COPIES_REQUIRED']
    observation = 'OBSERVED_METADATA' if info is not None else 'NOT_OBSERVED_WITHIN_BOUNDED_AUDIT'
    safe_exception_reason = None
    if observation_error is not None:
        observation = 'OBSERVATION_ERROR'
        if observation_error == 'SYMLINK_NOT_FOLLOWED':
            safe_exception_reason = 'SYMLINK_NOT_FOLLOWED'
        elif isinstance(observation_error, StorageHold):
            token = str(observation_error)
            safe_exception_reason = (token if token in SAFE_TEACHER_STORAGE_HOLD_CODES
                                     else 'STORAGE_HOLD_UNCLASSIFIED')
        elif isinstance(observation_error, OSError):
            code = errno.errorcode.get(observation_error.errno, 'UNKNOWN')
            if not re.fullmatch(r'E[A-Z0-9]+|UNKNOWN', code):
                code = 'UNKNOWN'
            safe_exception_reason = 'OSERROR_' + code
        else:
            safe_exception_reason = 'OBSERVATION_ERROR_UNCLASSIFIED'
        codes.append(safe_exception_reason)
    if info is None and observation_error is None:
        codes.append('NOT_OBSERVED_WITHIN_BOUNDED_AUDIT')
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            codes.append('FILE_NOT_REGULAR')
        if info.st_size != expected:
            codes.append('EXPECTED_SIZE_MISMATCH')
        if info.st_nlink != 1:
            codes.append('LINK_COUNT_NOT_ONE')
        if info.st_uid != os.geteuid():
            codes.append('OWNER_UID_MISMATCH')
        if usage is None or not usage.get('complete'):
            codes.append('PROCESS_INSPECTION_INCOMPLETE')
        elif (info.st_dev, info.st_ino) in usage.get('used', set()):
            codes.append('OPEN_OR_MEMORY_MAPPED')
    return {'path_id': digest_bytes(path.encode())[:20], 'observation': observation,
            'expected_bytes': expected, 'observed_bytes': info.st_size if info is not None else None,
            'safe_exception_reason': safe_exception_reason,
            'hold_codes': list(dict.fromkeys(codes)), 'deletion_authorized': False}


def deletion_kind(path):
    """A closed allowlist, not a general filesystem cleanup predicate."""
    path = Path(path)
    if path.suffix.lower() in WEIGHT_SUFFIX or PARTIAL.search(path.name):
        return None
    parts = {part.lower() for part in path.parts}
    if parts & PROTECTED_WORDS or any(part.lower().startswith('checkpoint-') for part in path.parts):
        return None
    pip_root = HOME_ROOT / '.cache/pip'
    if path.is_relative_to(pip_root):
        relative = path.relative_to(pip_root)
        if relative.parts and relative.parts[0] in ('http', 'http-v2') and re.fullmatch(r'[0-9a-f]{40,64}(?:\.body)?', path.name):
            return 'PIP_DOWNLOAD_CACHE', 86400
        if relative.parts and relative.parts[0] == 'wheels' and path.suffix == '.whl':
            return 'PIP_WHEEL_CACHE', 86400
        return None
    log_root = ROOT / 'logs'
    system_log = Path('/var/log/supervisor')
    if path.is_relative_to(log_root) or (path.is_relative_to(system_log) and path.name.lower().startswith(('nox-', 'nox_'))):
        match = re.fullmatch(r'.+\.log\.(\d+)(?:\.(?:gz|xz|zst))?', path.name)
        if match and int(match[1]) >= 3 and not LOG_PROTECTED.search(path.name):
            return 'OLD_DEBUG_LOG_ROTATION', 3 * 86400
    if (path.parent == ROOT or path.is_relative_to(ROOT / 'logs') or path.is_relative_to(ROOT / 'tmp')) and re.fullmatch(r'core(?:\.\d+)?', path.name):
        return 'INACTIVE_ELF_CORE', 86400
    return None


def qualify(path, info, now, usage):
    kind = deletion_kind(path)
    if kind is None:
        return None, 'PROTECTED_OR_NOT_ALLOWLISTED'
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
            or info.st_blocks * 512 < 1024 * 1024):
        return None, 'OWNERSHIP_LINK_TYPE_OR_SMALL_FILE'
    if now - max(info.st_mtime, info.st_ctime) < kind[1]:
        return None, 'RECENT_FILE'
    if not usage['complete']:
        return None, 'PROCESS_INSPECTION_INCOMPLETE'
    if (info.st_dev, info.st_ino) in usage['used']:
        return None, 'OPEN_OR_MEMORY_MAPPED'
    if kind[0].startswith('PIP_') and usage['active_package_manager']:
        return None, 'PACKAGE_MANAGER_ACTIVE'
    try:
        plain(path)
        head = prefix(path)
    except (OSError, StorageHold):
        return None, 'FILE_NOT_STABLE_OR_READABLE'
    # Defend even against an incorrectly named model placed in a cache folder.
    safetensors_header = len(head) >= 9 and 8 <= int.from_bytes(head[:8], 'little') <= 16 * 1024 * 1024 and head[8:9] == b'{'
    if head.startswith((b'GGUF', b'\x80\x02', b'\x80\x03', b'\x80\x04', b'\x80\x05')) or safetensors_header:
        return None, 'MODEL_OR_SERIALIZED_STATE_HEADER'
    if kind[0] == 'INACTIVE_ELF_CORE':
        if len(head) < 18 or head[:4] != b'\x7fELF' or head[5] not in (1, 2) or int.from_bytes(head[16:18], 'little' if head[5] == 1 else 'big') != 4:
            return None, 'NOT_ELF_CORE'
    return {'path': str(path), 'category': kind[0], 'minimum_age_seconds': kind[1],
            'identity': identity(info), 'allocated_bytes': info.st_blocks * 512,
            'prefix_sha256': digest_bytes(head), 'path_id': digest_bytes(str(path).encode())[:20]}, None


def filesystem_budget():
    disk, ram = shutil.disk_usage(ROOT), shutil.disk_usage(SHM)
    result = {'ssd': {'total_bytes': disk.total, 'used_bytes': disk.used, 'free_bytes': disk.free},
              'tmpfs': {'total_bytes': ram.total, 'used_bytes': ram.used, 'free_bytes': ram.free}}
    try:
        limit = int((CGROUP / 'memory.max').read_text())
        current = int((CGROUP / 'memory.current').read_text())
        if limit <= 0 or current < 0 or current > limit:
            raise ValueError('invalid cgroup memory values')
        result['cgroup'] = {'limit_bytes': limit, 'current_bytes': current,
                            'headroom_bytes': max(0, limit - current), 'state': 'VERIFIED'}
    except (OSError, ValueError):
        result['cgroup'] = {'headroom_bytes': 0, 'state': 'UNVERIFIED_LIMIT'}
    return result


def verified_cgroup_budget(budget):
    if not isinstance(budget, dict):
        return False
    cgroup = budget.get('cgroup')
    if not isinstance(cgroup, dict) or cgroup.get('state') != 'VERIFIED':
        return False
    limit = cgroup.get('limit_bytes')
    current = cgroup.get('current_bytes')
    headroom = cgroup.get('headroom_bytes')
    return (type(limit) is int and type(current) is int and type(headroom) is int
            and limit > 0 and 0 <= current <= limit
            and headroom == limit - current)


def placement(budget, categories):
    ram_budget = max(0, min(budget['tmpfs']['free_bytes'] - 3 * GIB,
                            budget['cgroup']['headroom_bytes'] - 32 * GIB))
    ssd_budget = max(0, budget['ssd']['free_bytes'] - 6 * GIB)
    hf_bytes = categories.get('TRAINING_HF_BASE_PROTECTED', {}).get('unique_logical_bytes', 0)
    # This is admission for an entirely new selected package. Existing or
    # partial assets require the installer's exact SHA/resume reconciliation.
    return {'ram_cache_admission_bytes': ram_budget, 'ssd_download_admission_bytes': ssd_budget,
            'ram_reserve_bytes': 3 * GIB, 'cgroup_reserve_bytes': 32 * GIB, 'ssd_reserve_bytes': 6 * GIB,
            'selected_media_package_bytes': MEDIA_BYTES,
            'selected_media_new_package_placement': 'RAM_CANDIDATE_REQUIRES_INSTALLER_SHA_AND_RECHECK' if MEDIA_BYTES <= ram_budget else
                'SSD_CANDIDATE_REQUIRES_INSTALLER_SHA_AND_RECHECK' if MEDIA_BYTES <= ssd_budget else 'BLOCKED_NEW_PACKAGE_CAPACITY',
            'existing_assets_reused_by_installer': True, 'extra_full_weight_copy_created': False,
            'hf_base_observed_bytes': hf_bytes, 'hf_base_full_tmpfs_fit_now': bool(hf_bytes and hf_bytes <= ram_budget),
            'hf_base_policy': 'KEEP_SSD_READ_VERIFIED_SHARDS_NO_REDUNDANT_FULL_RAM_COPY',
            'active_chat_policy': 'KEEP_EXISTING_GGUF_AND_OS_PAGE_CACHE',
            'memory_source_checkpoint_policy': 'KEEP_LOCAL_AND_BACK_UP_INDEPENDENTLY',
            'pc_drive_warm_policy': 'VERIFIED_COPY_THEN_ON_DEMAND_SHA_CHECKED_RAM_RESTORE',
            'ram_is_durable_backup': False, 'downloads_started': False, 'model_moved': False}


def audit(request, source):
    started = time.time()
    end = time.monotonic() + AUDIT_SECONDS
    usage = process_usage(min(end, time.monotonic() + 5))
    groups = defaultdict(lambda: Counter(files=0, unique_inodes=0, unique_logical_bytes=0, unique_allocated_bytes=0, repeated_inode_paths=0))
    seen, candidates, possible_copies = set(), [], defaultdict(set)
    counts, refusals = Counter(), Counter()
    teacher_reviews = {}
    for teacher_path in LEGACY_TEACHERS:
        teacher_path = ROOT / Path(teacher_path).relative_to(Path('/root/nox'))
        row = teacher_candidate_review(teacher_path)
        teacher_reviews[row['path_id']] = row
    coverage = []
    now = time.time()
    for label, root in root_specs():
        row = {'category': label, 'complete': True, 'entries': 0, 'directories': 0}
        coverage.append(row)
        try:
            plain(root)
            initial = root.stat()
            if not stat.S_ISDIR(initial.st_mode):
                row['state'] = 'NOT_DIRECTORY'; continue
        except FileNotFoundError:
            row['state'] = 'ABSENT'; continue
        except (OSError, StorageHold):
            row.update(state='UNREADABLE_OR_SYMLINK', complete=False); continue
        stack = [(root, 0)]
        while stack:
            if time.monotonic() > end or counts['entries'] >= MAX_ENTRIES or counts['directories'] >= MAX_DIRS:
                row.update(complete=False, state='BOUNDED_PARTIAL'); break
            directory, depth = stack.pop()
            counts['directories'] += 1; row['directories'] += 1
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if time.monotonic() > end or counts['entries'] >= MAX_ENTRIES:
                            row.update(complete=False, state='BOUNDED_PARTIAL'); break
                        counts['entries'] += 1; row['entries'] += 1
                        path = Path(entry.path)
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode):
                                counts['symlinks_not_followed'] += 1
                                review = teacher_candidate_review(path, observation_error='SYMLINK_NOT_FOLLOWED')
                                if review is not None:
                                    teacher_reviews[review['path_id']] = review
                                continue
                            if info.st_dev != initial.st_dev:
                                counts['other_mounts_not_crossed'] += 1; continue
                            if stat.S_ISDIR(info.st_mode):
                                if depth >= 18:
                                    row['complete'] = False
                                else:
                                    stack.append((path, depth + 1))
                                continue
                            if not stat.S_ISREG(info.st_mode):
                                counts['special_files_not_read'] += 1; continue
                            group = groups[category(label, path)]
                            group['files'] += 1
                            review = teacher_candidate_review(path, info, usage)
                            if review is not None:
                                teacher_reviews[review['path_id']] = review
                            key = (info.st_dev, info.st_ino)
                            if key in seen:
                                group['repeated_inode_paths'] += 1
                                continue
                            seen.add(key)
                            group['unique_inodes'] += 1
                            group['unique_logical_bytes'] += info.st_size
                            group['unique_allocated_bytes'] += info.st_blocks * 512
                            if info.st_size >= 8 * 1024 * 1024 and len(possible_copies) < 4096:
                                possible_copies[(path.name, info.st_size)].add(key)
                            candidate, reason = qualify(path, info, now, usage)
                            if candidate is not None:
                                candidates.append(candidate)
                                if len(candidates) > MAX_CANDIDATES * 2:
                                    candidates.sort(key=lambda x: x['allocated_bytes'], reverse=True)
                                    candidates = candidates[:MAX_CANDIDATES]
                            elif deletion_kind(path) is not None:
                                refusals[reason] += 1
                        except (OSError, StorageHold) as exc:
                            counts['unreadable_entries'] += 1; row['complete'] = False
                            review = teacher_candidate_review(path, observation_error=exc)
                            if review is not None:
                                teacher_reviews[review['path_id']] = review
            except OSError:
                row['complete'] = False
        row.setdefault('state', 'OBSERVED' if row['complete'] else 'BOUNDED_PARTIAL')
    candidates.sort(key=lambda x: x['allocated_bytes'], reverse=True)
    candidates = candidates[:MAX_CANDIDATES]
    aggregate = dict(groups)
    budget = filesystem_budget()
    copy_groups = [len(value) for value in possible_copies.values() if len(value) > 1]
    pc = optional_json(ROOT / 'state/pc_shell/connection.json', 16384)
    stamp = pc.get('connected_utc')
    receipt = {'schema': SCHEMA, 'instance_id': INSTANCE, 'action': 'AUDIT', 'request': request,
               'source_sha': source, 'helper_sha256': digest_bytes(bounded_bytes(__file__, 2 * 1024 * 1024)),
               'started_at': started, 'finished_at': time.time(), 'state': 'AUDIT_COMPLETE_NO_DELETION',
               'coverage': coverage, 'counts': dict(counts), 'categories': aggregate,
               'allocation_basis': 'ST_BLOCKS_BY_DEVICE_AND_INODE_REFLINK_EXTENTS_NOT_DEDUPLICATED',
               'aliases': known_aliases(), 'distinct_inode_same_name_size_groups': len(copy_groups),
               'distinct_inode_same_name_size_files': sum(copy_groups), 'content_duplicate_verified': False,
               'process_scan': {k: v for k, v in usage.items() if k != 'used'},
               'cleanup_candidates': candidates, 'cleanup_refusals': dict(refusals),
               'teacher_candidate_holds': sorted(teacher_reviews.values(), key=lambda row: row['path_id']),
               'eligible_allocated_bytes': sum(x['allocated_bytes'] for x in candidates),
               'reclaim_batch_limit': MAX_DELETIONS, 'budget': budget, 'placement': placement(budget, aggregate),
               'pc_registration_present': bool(pc.get('schema') == 'NOX_PC_LINK_V1' and stamp),
               'pc_connectivity_verified_by_this_audit': False,
               'weight_eviction': {'allowed': False, 'bytes_deleted': 0,
                   'blockers': ['TWO_INDEPENDENT_SHA_VERIFIED_PC_AND_DRIVE_COPIES_REQUIRED'],
                   'backup_registration_or_ram_copy_is_not_two_copy_proof': True},
               'files_deleted': 0, 'public_output_contains_paths_or_private_text': False}
    return receipt


@contextmanager
def reclaim_locks():
    storage = os.open(receipt_directory() / 'reclaim.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    maintenance = os.open(plain(ROOT / 'state/owner_maintenance.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(storage, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(maintenance, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageHold('HOLD_STORAGE_OR_NATIVE_MAINTENANCE_BUSY')
        yield
    finally:
        os.close(maintenance); os.close(storage)


def open_parent(path):
    """Walk directory handles without following any symlink at any level."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.name in ('', '.', '..'):
        raise StorageHold('HOLD_STORAGE_PATH_SCOPE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for piece in path.parts[1:-1]:
            child = os.open(piece, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise StorageHold('HOLD_STORAGE_DIRECTORY_OWNER_OR_WRITABLE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def reclaim_candidate(candidate, deadline):
    path = Path(candidate.get('path', ''))
    if deletion_kind(path) is None:
        raise StorageHold('HOLD_STORAGE_PROTECTED_TARGET')
    parent_fd = open_parent(path)
    fd = None
    try:
        info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if identity(info) != candidate.get('identity'):
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent_fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if identity(os.fstat(fd)) != candidate['identity']:
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        head = os.read(fd, 32)
        if digest_bytes(head) != candidate.get('prefix_sha256'):
            raise StorageHold('HOLD_STORAGE_PREFIX_CHANGED')
        usage = process_usage(min(deadline, time.monotonic() + 4), ignore_fd=(os.getpid(), str(fd)))
        fresh, reason = qualify(path, info, time.time(), usage)
        if fresh is None or fresh['identity'] != candidate['identity'] or fresh['category'] != candidate['category']:
            raise StorageHold('HOLD_STORAGE_' + str(reason or 'CANDIDATE_CHANGED'))
        if time.monotonic() > deadline:
            raise StorageHold('HOLD_STORAGE_TIME_BUDGET')
        if identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)) != candidate['identity']:
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        # One audited regular file only; no recursive removal or truncation.
        os.unlink(path.name, dir_fd=parent_fd)
        os.close(fd); fd = None  # Release our read handle before measuring free space.
        try:
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return {'path_id': candidate['path_id'], 'category': candidate['category'],
                    'allocated_bytes_unlinked': candidate['allocated_bytes'], 'logical_bytes_unlinked': info.st_size,
                    'state': 'EXACT_AUDITED_FILE_UNLINKED', 'process_scan_complete': usage['complete']}
        raise StorageHold('HOLD_STORAGE_NAME_RECREATED_AFTER_UNLINK')
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def reclaim_page_cache_candidate(candidate, deadline, maximum_bytes):
    """Issue DONTNEED only for one exact, unused ephemeral file range."""
    path = Path(candidate.get('path', ''))
    category = candidate.get('category')
    if (category not in PAGE_CACHE_SAFE_CATEGORIES or deletion_kind(path) is None
            or not hasattr(os, 'posix_fadvise')
            or not hasattr(os, 'POSIX_FADV_DONTNEED')):
        raise StorageHold('HOLD_PAGE_CACHE_CANDIDATE_SCOPE')
    parent_fd = open_parent(path)
    fd = None
    try:
        info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if identity(info) != candidate.get('identity'):
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent_fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(fd)
        if identity(info) != candidate.get('identity'):
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        head = os.pread(fd, 32, 0)
        if digest_bytes(head) != candidate.get('prefix_sha256'):
            raise StorageHold('HOLD_STORAGE_PREFIX_CHANGED')
        usage = process_usage(min(deadline, time.monotonic() + 4),
                              ignore_fd=(os.getpid(), str(fd)))
        fresh, reason = qualify(path, info, time.time(), usage)
        if (fresh is None or fresh['identity'] != candidate['identity']
                or fresh['category'] != category):
            raise StorageHold('HOLD_STORAGE_' + str(reason or 'CANDIDATE_CHANGED'))
        if time.monotonic() > deadline:
            raise StorageHold('HOLD_STORAGE_TIME_BUDGET')
        if identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)) != candidate['identity']:
            raise StorageHold('HOLD_STORAGE_IDENTITY_CHANGED')
        advised = min(max(0, info.st_size), max(0, maximum_bytes),
                      MAX_PAGE_CACHE_BYTES_PER_FILE)
        if advised <= 0:
            raise StorageHold('HOLD_PAGE_CACHE_EMPTY_RANGE')
        # POSIX_FADV_DONTNEED is a best-effort hint for clean page-cache pages.
        # It neither writes file contents nor guarantees reclaim; dirty pages
        # may remain cached. The open/mmap census above protects warm users.
        os.posix_fadvise(fd, 0, advised, os.POSIX_FADV_DONTNEED)
        return {'path_id': candidate['path_id'], 'category': category,
                'logical_bytes_advised': advised,
                'allocated_bytes_observed': candidate['allocated_bytes'],
                'state': 'DONTNEED_HINT_ACCEPTED',
                'actual_reclaimed_bytes_confirmed': 0,
                'reclaim_amount_unverified': True}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def reclaim_page_cache(request, source, audit_request, expected_sha):
    """Perform one no-retry DONTNEED pass against an exact fresh audit receipt."""
    if (not isinstance(request, str) or not request.isdigit()
            or request != audit_request or not audit_request.isdigit()
            or not re.fullmatch(r'[0-9a-f]{64}', expected_sha)):
        raise StorageHold('HOLD_EXACT_STORAGE_AUDIT_PIN_REQUIRED')
    audit_path = receipt_directory() / ('audit_' + audit_request + '.json')
    raw = bounded_bytes(audit_path, 2 * 1024 * 1024)
    if digest_bytes(raw) != expected_sha:
        raise StorageHold('HOLD_STORAGE_AUDIT_SHA_CHANGED')
    previous = json.loads(raw)
    if not verified_cgroup_budget(previous.get('budget')):
        raise StorageHold('HOLD_PAGE_CACHE_AUDIT_RESOURCE_UNVERIFIED')
    if (previous.get('schema') != SCHEMA or previous.get('action') != 'AUDIT'
            or previous.get('instance_id') != INSTANCE
            or previous.get('request') != audit_request
            or previous.get('source_sha') != source
            or previous.get('helper_sha256') != digest_bytes(bounded_bytes(__file__, 2 * 1024 * 1024))
            or type(previous.get('finished_at')) not in (int, float)
            or not 0 <= time.time() - previous['finished_at'] <= AUDIT_TTL
            or previous.get('process_scan', {}).get('complete') is not True
            or not isinstance(previous.get('cleanup_candidates'), list)
            or len(previous['cleanup_candidates']) > MAX_CANDIDATES):
        raise StorageHold('HOLD_STORAGE_AUDIT_IDENTITY_OR_FRESHNESS')
    if any(row.get('category') not in PAGE_CACHE_SAFE_CATEGORIES
           for row in previous['cleanup_candidates']):
        raise StorageHold('HOLD_PAGE_CACHE_CANDIDATE_SCOPE')
    with reclaim_locks():
        started = time.time()
        end = time.monotonic() + RECLAIM_SECONDS
        before = filesystem_budget()
        cgroup = before.get('cgroup', {})
        headroom = cgroup.get('headroom_bytes')
        limit = cgroup.get('limit_bytes')
        if not verified_cgroup_budget(before):
            raise StorageHold('HOLD_PAGE_CACHE_HEADROOM_UNVERIFIED')
        output = receipt_directory() / ('page_cache_' + request + '.json')
        receipt = {'schema': SCHEMA, 'instance_id': INSTANCE,
                   'action': 'PAGE_CACHE_RECLAIM', 'request': request,
                   'source_sha': source, 'audit_request': audit_request,
                   'audit_sha256': expected_sha, 'started_at': started,
                   'before': before,
                   'native_admission_threshold_bytes': MIN_NATIVE_ADMISSION_HEADROOM,
                   'browser_runtime_memory_threshold_bytes': BROWSER_RUNTIME_HEADROOM,
                   'browser_runtime_disk_threshold_bytes': BROWSER_RUNTIME_DISK_HEADROOM,
                   'browser_runtime_disk_threshold_checked': False,
                   'page_cache_advice_budget_bytes': MAX_PAGE_CACHE_ADVISE_BYTES,
                   'page_cache_max_files': MAX_PAGE_CACHE_FILES,
                   'page_cache_max_bytes_per_file': MAX_PAGE_CACHE_BYTES_PER_FILE,
                   'browser_runtime_admitted': False,
                   'headroom_at_start_bytes': headroom, 'advised_files': [],
                   'browser_memory_threshold_observed_during_pass': False,
                   'advice_budget_exhausted': False, 'file_budget_exhausted': False,
                   'logical_bytes_advised': 0,
                   'actual_reclaimed_bytes_confirmed': 0,
                   'reclaim_amount_unverified': True,
                   'model_files_touched': False, 'files_unlinked': 0,
                   'processes_killed': 0, 'services_restarted': 0,
                   'weights_or_S03_modified': False,
                   'one_shot_no_retry': True, 'state': 'PAGE_CACHE_RECLAIM_IN_PROGRESS'}
        # Claim the action receipt before any page-cache advice. O_EXCL makes
        # repeated requests, including recovery from an inflight receipt, fail closed.
        write_receipt_exclusive(output, receipt)
        receipt_info = os.stat(output, follow_symlinks=False)
        if (not stat.S_ISREG(receipt_info.st_mode)
                or receipt_info.st_uid != os.geteuid()
                or receipt_info.st_nlink != 1):
            raise StorageHold('HOLD_PAGE_CACHE_RECEIPT_OWNERSHIP')
        receipt_identity = identity(receipt_info)
        def update_owned_receipt():
            nonlocal receipt_identity
            current = os.stat(output, follow_symlinks=False)
            if (identity(current) != receipt_identity
                    or not stat.S_ISREG(current.st_mode)
                    or current.st_uid != os.geteuid()
                    or current.st_nlink != 1):
                raise StorageHold('HOLD_PAGE_CACHE_RECEIPT_OWNERSHIP_CHANGED')
            write_receipt(output, receipt, replace=True)
            updated = os.stat(output, follow_symlinks=False)
            if (not stat.S_ISREG(updated.st_mode)
                    or updated.st_uid != os.geteuid()
                    or updated.st_nlink != 1):
                raise StorageHold('HOLD_PAGE_CACHE_RECEIPT_OWNERSHIP_CHANGED')
            receipt_identity = identity(updated)
        if headroom >= BROWSER_RUNTIME_HEADROOM:
            receipt['state'] = 'SKIPPED_HEADROOM_AT_OR_ABOVE_4_GIB'
        else:
            for candidate in previous['cleanup_candidates'][:MAX_PAGE_CACHE_FILES]:
                if time.monotonic() > end:
                    receipt['budget_exhausted'] = True
                    receipt['stop_reason'] = '35_SECOND_TIME_BUDGET'
                    break
                remaining = MAX_PAGE_CACHE_ADVISE_BYTES - receipt['logical_bytes_advised']
                if remaining <= 0:
                    receipt['advice_budget_exhausted'] = True
                    receipt['stop_reason'] = '4_GIB_ADVICE_BUDGET'
                    break
                receipt['inflight'] = {'path_id': candidate.get('path_id'),
                    'category': candidate.get('category'),
                    'identity': candidate.get('identity'),
                    'state': 'EXACT_FILE_CENSUS_AND_RECHECK_REQUIRED'}
                update_owned_receipt()
                try:
                    row = reclaim_page_cache_candidate(candidate, end, remaining)
                    receipt['advised_files'].append(row)
                    receipt['logical_bytes_advised'] += row['logical_bytes_advised']
                except (OSError, StorageHold) as exc:
                    code = str(exc)
                    receipt.setdefault('skipped', []).append({
                        'path_id': candidate.get('path_id'),
                        'reason': code if re.fullmatch(r'HOLD_[A-Z_]+', code)
                                  else 'HOLD_PAGE_CACHE_OS_OPERATION'})
                receipt['inflight'] = None
                update_owned_receipt()
                latest_budget = filesystem_budget()
                latest_cgroup = latest_budget.get('cgroup', {})
                latest_headroom = latest_cgroup.get('headroom_bytes')
                if not verified_cgroup_budget(latest_budget):
                    receipt['headroom_recheck_state'] = 'UNVERIFIED_STOPPED'
                    receipt['stop_reason'] = 'HEADROOM_RECHECK_UNVERIFIED'
                    receipt['after'] = latest_budget
                    receipt['headroom_after_bytes'] = None
                    receipt['two_gib_admission_memory_threshold_met_after'] = None
                    receipt['browser_memory_prerequisite_met_after'] = None
                    receipt['browser_disk_prerequisite_checked'] = False
                    receipt['browser_runtime_admitted'] = False
                    receipt['headroom_delta_includes_other_processes'] = True
                    receipt['finished_at'] = time.time()
                    receipt['state'] = 'HOLD_PAGE_CACHE_HEADROOM_UNVERIFIED'
                    receipt['one_shot_no_retry'] = True
                    receipt['page_cache_reclaimed_bytes_claimed'] = 0
                    receipt['native_job_admitted'] = False
                    update_owned_receipt()
                    return receipt
                if latest_headroom >= BROWSER_RUNTIME_HEADROOM:
                    receipt['browser_memory_threshold_observed_during_pass'] = True
                    receipt['stop_reason'] = '4_GIB_OBSERVED_DURING_PASS'
                    break
            else:
                if len(previous['cleanup_candidates']) > MAX_PAGE_CACHE_FILES:
                    receipt['file_budget_exhausted'] = True
                    receipt['stop_reason'] = '32_FILE_LIMIT'
                else:
                    receipt['stop_reason'] = 'SAFE_CANDIDATES_EXHAUSTED'
        receipt['finished_at'] = time.time()
        receipt['after'] = filesystem_budget()
        after_cgroup = receipt['after'].get('cgroup', {})
        after_headroom = after_cgroup.get('headroom_bytes')
        if not verified_cgroup_budget(receipt['after']):
            receipt['headroom_recheck_state'] = 'UNVERIFIED_STOPPED'
            receipt['stop_reason'] = 'FINAL_HEADROOM_UNVERIFIED'
            receipt['headroom_after_bytes'] = None
            receipt['two_gib_admission_memory_threshold_met_after'] = None
            receipt['browser_memory_prerequisite_met_after'] = None
            receipt['browser_disk_prerequisite_checked'] = False
            receipt['browser_runtime_admitted'] = False
            receipt['headroom_delta_includes_other_processes'] = True
            receipt['finished_at'] = time.time()
            receipt['state'] = 'HOLD_PAGE_CACHE_HEADROOM_UNVERIFIED'
            receipt['one_shot_no_retry'] = True
            receipt['page_cache_reclaimed_bytes_claimed'] = 0
            receipt['native_job_admitted'] = False
            update_owned_receipt()
            return receipt
        receipt['headroom_after_bytes'] = after_headroom
        receipt['two_gib_admission_memory_threshold_met_after'] = (
            type(after_headroom) is int
            and after_headroom >= MIN_NATIVE_ADMISSION_HEADROOM)
        receipt['browser_memory_prerequisite_met_after'] = (
            type(after_headroom) is int
            and after_headroom >= BROWSER_RUNTIME_HEADROOM)
        receipt['browser_disk_prerequisite_checked'] = False
        receipt['browser_runtime_admitted'] = False
        receipt['headroom_delta_includes_other_processes'] = True
        if receipt.get('state') == 'SKIPPED_HEADROOM_AT_OR_ABOVE_4_GIB':
            if not receipt['browser_memory_prerequisite_met_after']:
                receipt['state'] = 'HEADROOM_FELL_BELOW_4_GIB_AFTER_SKIPPED_START'
        elif receipt['browser_memory_prerequisite_met_after']:
            receipt['state'] = 'BROWSER_MEMORY_PREREQUISITE_MET_AFTER_ACTION'
        elif receipt.get('budget_exhausted'):
            receipt['state'] = 'TIME_BUDGET_EXHAUSTED_BELOW_4_GIB'
        elif receipt.get('advice_budget_exhausted'):
            receipt['state'] = '4_GIB_ADVICE_BUDGET_EXHAUSTED_BELOW_4_GIB'
        elif receipt.get('file_budget_exhausted'):
            receipt['state'] = '32_FILE_LIMIT_REACHED_BELOW_4_GIB'
        elif receipt.get('stop_reason') == '4_GIB_OBSERVED_DURING_PASS':
            receipt['state'] = 'HEADROOM_FELL_BELOW_4_GIB_AFTER_PASS'
        elif receipt.get('headroom_recheck_state') == 'UNVERIFIED_STOPPED':
            receipt['state'] = 'HEADROOM_UNVERIFIED_AFTER_PASS'
        else:
            receipt['state'] = 'SAFE_CANDIDATES_EXHAUSTED_BELOW_4_GIB'
        receipt['one_shot_no_retry'] = True
        receipt['page_cache_reclaimed_bytes_claimed'] = 0
        receipt['native_job_admitted'] = False
        update_owned_receipt()
        return receipt


def reclaim(request, source, audit_request, expected_sha):
    if not audit_request.isdigit() or not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
        raise StorageHold('HOLD_EXACT_STORAGE_AUDIT_PIN_REQUIRED')
    path = receipt_directory() / ('audit_' + audit_request + '.json')
    raw = bounded_bytes(path, 2 * 1024 * 1024)
    if digest_bytes(raw) != expected_sha:
        raise StorageHold('HOLD_STORAGE_AUDIT_SHA_CHANGED')
    previous = json.loads(raw)
    if (previous.get('schema') != SCHEMA or previous.get('action') != 'AUDIT' or previous.get('instance_id') != INSTANCE
            or previous.get('request') != audit_request or previous.get('helper_sha256') != digest_bytes(bounded_bytes(__file__, 2 * 1024 * 1024))
            or type(previous.get('finished_at')) not in (int, float) or not 0 <= time.time() - previous['finished_at'] <= AUDIT_TTL
            or not isinstance(previous.get('cleanup_candidates'), list) or len(previous['cleanup_candidates']) > MAX_CANDIDATES):
        raise StorageHold('HOLD_STORAGE_AUDIT_IDENTITY_OR_FRESHNESS')
    with reclaim_locks():
        started = time.time()
        end = time.monotonic() + RECLAIM_SECONDS
        before = filesystem_budget()
        receipt = {'schema': SCHEMA, 'instance_id': INSTANCE, 'action': 'RECLAIM', 'request': request,
                   'source_sha': source, 'audit_request': audit_request, 'audit_sha256': expected_sha,
                   'started_at': started, 'state': 'RECLAIM_IN_PROGRESS', 'before': before,
                   'files_deleted': 0, 'allocated_bytes_unlinked': 0, 'deleted': [], 'skipped': [],
                   'weight_bytes_deleted': 0, 'checkpoint_bytes_deleted': 0, 'source_memory_credentials_bytes_deleted': 0}
        output = receipt_directory() / ('reclaim_' + request + '.json')
        write_receipt(output, receipt)
        for candidate in previous['cleanup_candidates'][:MAX_DELETIONS]:
            if time.monotonic() > end:
                receipt['budget_exhausted'] = True; break
            receipt['inflight'] = {'path_id': candidate.get('path_id'), 'category': candidate.get('category'),
                                   'identity': candidate.get('identity'), 'state': 'EXACT_FILE_RECHECK_REQUIRED'}
            write_receipt(output, receipt, replace=True)
            try:
                row = reclaim_candidate(candidate, end)
                receipt['deleted'].append(row)
                receipt['files_deleted'] += 1
                receipt['allocated_bytes_unlinked'] += row['allocated_bytes_unlinked']
            except (OSError, StorageHold) as exc:
                code = str(exc)
                receipt['skipped'].append({'path_id': candidate.get('path_id'),
                    'reason': code if re.fullmatch(r'HOLD_[A-Z_]+', code) else 'HOLD_STORAGE_OS_OPERATION'})
            receipt['inflight'] = None
            write_receipt(output, receipt, replace=True)
        receipt.update(state='BOUNDED_EPHEMERAL_RECLAIM_COMPLETE', finished_at=time.time(), after=filesystem_budget())
        receipt['observed_ssd_free_bytes_delta'] = receipt['after']['ssd']['free_bytes'] - before['ssd']['free_bytes']
        receipt['free_delta_may_include_concurrent_activity'] = True
        receipt['weight_eviction_blockers'] = ['TWO_INDEPENDENT_SHA_VERIFIED_PC_AND_DRIVE_COPIES_REQUIRED']
        write_receipt(output, receipt, replace=True)
        return receipt


def public_summary(receipt):
    keys = ('schema', 'instance_id', 'action', 'request', 'state', 'started_at', 'finished_at',
            'coverage', 'counts', 'categories', 'allocation_basis', 'aliases',
            'distinct_inode_same_name_size_groups', 'distinct_inode_same_name_size_files', 'content_duplicate_verified',
            'process_scan', 'cleanup_refusals', 'eligible_allocated_bytes', 'reclaim_batch_limit',
            'budget', 'placement', 'pc_registration_present', 'pc_connectivity_verified_by_this_audit',
            'weight_eviction', 'files_deleted', 'allocated_bytes_unlinked', 'weight_bytes_deleted',
            'native_admission_threshold_bytes', 'browser_runtime_memory_threshold_bytes',
            'browser_runtime_disk_threshold_bytes', 'browser_runtime_disk_threshold_checked',
            'page_cache_advice_budget_bytes', 'page_cache_max_files',
            'page_cache_max_bytes_per_file', 'stop_reason', 'one_shot_no_retry',
            'advice_budget_exhausted', 'file_budget_exhausted', 'browser_runtime_admitted', 'browser_memory_prerequisite_met_after',
            'browser_memory_threshold_observed_during_pass', 'browser_disk_prerequisite_checked',
            'headroom_at_start_bytes', 'headroom_after_bytes',
            'logical_bytes_advised', 'actual_reclaimed_bytes_confirmed',
            'reclaim_amount_unverified', 'page_cache_reclaimed_bytes_claimed',
            'two_gib_admission_memory_threshold_met_after', 'native_job_admitted',
            'checkpoint_bytes_deleted', 'source_memory_credentials_bytes_deleted', 'observed_ssd_free_bytes_delta',
            'free_delta_may_include_concurrent_activity', 'weight_eviction_blockers', 'before', 'after')
    value = {key: receipt[key] for key in keys if key in receipt}
    if 'cleanup_candidates' in receipt:
        totals = defaultdict(lambda: Counter(files=0, allocated_bytes=0))
        for row in receipt['cleanup_candidates']:
            totals[row['category']]['files'] += 1
            totals[row['category']]['allocated_bytes'] += row['allocated_bytes']
        value['eligible_by_category'] = dict(totals)
    if 'skipped' in receipt:
        value['skip_reasons'] = dict(Counter(row['reason'] for row in receipt['skipped']))
    if 'advised_files' in receipt:
        advised = Counter()
        for row in receipt['advised_files']:
            advised[row['category']] += row['logical_bytes_advised']
        value['page_cache_files_advised'] = len(receipt['advised_files'])
        value['page_cache_bytes_advised_by_category'] = dict(advised)
    if 'skipped' in receipt and receipt.get('action') == 'PAGE_CACHE_RECLAIM':
        value['page_cache_skip_reasons'] = dict(
            Counter(row['reason'] for row in receipt['skipped']))
    return value


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or len(request) > 20 or not re.fullmatch(r'[0-9a-f]{40}', source):
        raise StorageHold('HOLD_OWNER_CONTEXT')
    os.nice(10)
    action = os.environ.get('NOX_STORAGE_ACTION', 'AUDIT')
    if action == 'AUDIT':
        receipt = audit(request, source)
        path = receipt_directory() / ('audit_' + request + '.json')
        sha = write_receipt(path, receipt)
    elif action == 'RECLAIM':
        receipt = reclaim(request, source, os.environ.get('NOX_STORAGE_AUDIT_REQUEST', ''), os.environ.get('NOX_STORAGE_AUDIT_SHA256', ''))
        path = receipt_directory() / ('reclaim_' + request + '.json')
        sha = digest_bytes(bounded_bytes(path, 2 * 1024 * 1024))
    elif action == 'PAGE_CACHE_RECLAIM':
        receipt = reclaim_page_cache(request, source,
            os.environ.get('NOX_STORAGE_AUDIT_REQUEST', ''),
            os.environ.get('NOX_STORAGE_AUDIT_SHA256', ''))
        path = receipt_directory() / ('page_cache_' + request + '.json')
        sha = digest_bytes(bounded_bytes(path, 2 * 1024 * 1024))
    else:
        raise StorageHold('HOLD_STORAGE_ACTION')
    emit('storage_' + action.lower(), {**public_summary(receipt), 'receipt_path': str(path), 'receipt_sha256': sha})
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        reason = str(exc)
        emit('storage_hold', {'state': reason if re.fullmatch(r'HOLD_[A-Z_]+', reason) else 'HOLD_STORAGE_' + type(exc).__name__.upper(),
                              'private_text_exported': False})
        raise SystemExit(2)
