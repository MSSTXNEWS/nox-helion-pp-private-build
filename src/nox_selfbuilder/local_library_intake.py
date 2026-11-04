"""Bounded read-only physical library intake for the EXISTING NOX FirstBoot.

The signed native OneHost owner supplies policy, path attestation and STOP. This
module never imports artifacts into S03, executes code, downloads a model, or
marks a source/licence/weight installed. A downstream native owner must recheck
file handles, rights and digests before granting any admission.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from .firstboot_coordinator import _policy, _utc, FirstBootHold, MAX_FOUND_ITEMS

MAX_DIRS = 64
MAX_SCAN_ENTRIES = 2048
MAX_DEPTH = 3
MAX_SCAN_BYTES = 16 * 1024**3
_CHUNK = 1024 * 1024
_CATEGORIES = {
    '.gguf': 'MODEL_WEIGHTS', '.safetensors': 'MODEL_WEIGHTS',
    '.whl': 'PYTHON_WHEEL', '.nupkg': 'DOTNET_NUGET',
    '.zip': 'ARCHIVE_DONOR', '.7z': 'ARCHIVE_DONOR',
    '.py': 'SOURCE_CANDIDATE', '.cs': 'SOURCE_CANDIDATE',
    '.js': 'SOURCE_CANDIDATE', '.mjs': 'SOURCE_CANDIDATE',
    '.png': 'DESIGN_CANDIDATE', '.webp': 'DESIGN_CANDIDATE',
    '.exe': 'INSTALLER_CANDIDATE',
}


def _no_link_ancestors(path):
    """Reject symlinks and Windows junction/reparse-point ancestors."""
    current = Path(os.path.abspath(path))
    while True:
        meta = current.lstat()
        if stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0) & 0x400:
            raise FirstBootHold('LOCAL_SCAN_SYMLINK_REPARSE_DENIED')
        if current.parent == current:
            return
        current = current.parent


def _sha_regular(path, *, stop, remaining):
    _no_link_ancestors(path)
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise FirstBootHold('LOCAL_SCAN_NONREGULAR_OR_EMPTY_FILE')
    if before.st_size > remaining:
        raise FirstBootHold('LOCAL_SCAN_BYTE_BUDGET_EXHAUSTED')
    # O_NOFOLLOW protects the final component on POSIX. On Windows the native
    # OneHost path-attestation callback MUST enforce reparse-safe open handles.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    digest = hashlib.sha256()
    count = 0
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or
                (opened.st_dev, opened.st_ino, opened.st_size) !=
                (before.st_dev, before.st_ino, before.st_size)):
            raise FirstBootHold('LOCAL_SCAN_FILE_CHANGED_BEFORE_READ')
        while True:
            stop()
            chunk = os.read(fd, min(_CHUNK, remaining - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > remaining:
                raise FirstBootHold('LOCAL_SCAN_BYTE_BUDGET_EXHAUSTED')
            digest.update(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    _no_link_ancestors(path)
    disk = os.lstat(path)
    for latest in (after, disk):
        if (latest.st_dev, latest.st_ino, latest.st_size, latest.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise FirstBootHold('LOCAL_SCAN_FILE_MUTATED_DURING_HASH')
    if count != before.st_size:
        raise FirstBootHold('LOCAL_SCAN_FILE_SIZE_CHANGED')
    return digest.hexdigest(), count


def scan_approved_local_library(session, *, now, native_policy, native_path_proof,
                                stop_requested, stop_epoch):
    """Scan ONLY signed, explicit native-approved roots; return untrusted SHA candidates.

    Native path proof must bind the Windows user SID, ACL, effective realpath,
    no-reparse open and the exact signed root grant. This function cannot mint
    that proof. No scanning occurs if any native callback is absent/denies.
    """
    if not all(callable(fn) for fn in (native_policy, native_path_proof,
                                      stop_requested, stop_epoch)):
        raise FirstBootHold('LOCAL_SCAN_NATIVE_OWNER_PORTS_REQUIRED')
    now = _utc(now)
    epoch = stop_epoch()
    if type(epoch) is not int or epoch < 0:
        raise FirstBootHold('LOCAL_SCAN_NATIVE_STOP_EPOCH_REQUIRED')

    def stop():
        if stop_requested() is not False or stop_epoch() != epoch:
            raise FirstBootHold('LOCAL_SCAN_STOP_OR_REVOKE')

    stop()
    roots = _policy(native_policy(session), now)
    if not roots:
        raise FirstBootHold('LOCAL_SCAN_EXPLICIT_ROOTS_REQUIRED')
    roots_abs = []
    for raw in roots:
        if (not os.path.isabs(raw) or os.path.normpath(raw) != raw or
                os.path.dirname(os.path.normpath(raw)) == os.path.normpath(raw)):
            raise FirstBootHold('LOCAL_SCAN_EXPLICIT_SUBFOLDER_REQUIRED')
        _no_link_ancestors(raw)
        if not Path(raw).is_dir():
            raise FirstBootHold('LOCAL_SCAN_ROOT_NOT_DIRECTORY')
        if native_path_proof(session, raw, 'ROOT') is not True:
            raise FirstBootHold('LOCAL_SCAN_ROOT_NATIVE_PERMISSION_REQUIRED')
        roots_abs.append(raw)
    if len(set(os.path.normcase(x) for x in roots_abs)) != len(roots_abs):
        raise FirstBootHold('LOCAL_SCAN_DUPLICATE_ROOT')

    seen = {}
    visited = set()
    directories = [(root, 0) for root in reversed(roots_abs)]
    total_bytes = 0
    examined = 0
    entries_seen = 0
    while directories:
        stop()
        path, depth = directories.pop()
        _no_link_ancestors(path)
        identity = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(identity.st_mode):
            raise FirstBootHold('LOCAL_SCAN_DIRECTORY_CHANGED')
        marker = (identity.st_dev, identity.st_ino)
        if marker in visited:
            continue
        visited.add(marker)
        if len(visited) > MAX_DIRS:
            raise FirstBootHold('LOCAL_SCAN_DIRECTORY_LIMIT')
        if native_path_proof(session, path, 'DIRECTORY') is not True:
            raise FirstBootHold('LOCAL_SCAN_DIRECTORY_NATIVE_PERMISSION_REQUIRED')
        # Never materialize an unbounded listing, including ignored file types.
        with os.scandir(path) as cursor:
            entries = []
            for entry in cursor:
                stop()
                entries_seen += 1
                if entries_seen > MAX_SCAN_ENTRIES:
                    raise FirstBootHold('LOCAL_SCAN_DIRECTORY_ENTRY_LIMIT')
                entries.append(entry)
        entries.sort(key=lambda e: e.name.casefold())
        for entry in entries:
            stop()
            candidate = entry.path
            _no_link_ancestors(candidate)
            if native_path_proof(session, candidate, 'ENTRY') is not True:
                raise FirstBootHold('LOCAL_SCAN_ENTRY_NATIVE_PERMISSION_REQUIRED')
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                if depth < MAX_DEPTH:
                    directories.append((candidate, depth + 1))
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            kind = _CATEGORIES.get(Path(candidate).suffix.lower())
            if kind is None:
                continue
            examined += 1
            if examined > MAX_FOUND_ITEMS:
                raise FirstBootHold('LOCAL_SCAN_FILE_LIMIT')
            sha, size = _sha_regular(candidate, stop=stop,
                                     remaining=MAX_SCAN_BYTES - total_bytes)
            total_bytes += size
            # The native Windows owner must reattest the path after hashing;
            # never persist paths/ACLs or use any candidate as installed proof.
            if native_path_proof(session, candidate, 'POST_HASH') is not True:
                raise FirstBootHold('LOCAL_SCAN_REVOKED_AFTER_HASH')
            prior = seen.get(sha)
            if prior is not None:
                if prior['kind'] != kind or prior['size_bytes'] != size:
                    raise FirstBootHold('LOCAL_SCAN_CONFLICTING_DIGEST_METADATA')
                prior['duplicate_paths'] += 1
            else:
                seen[sha] = {'sha256': sha, 'size_bytes': size,
                             'kind': kind, 'duplicate_paths': 0,
                             'status': 'DISCOVERED_UNTRUSTED_NOT_IMPORTED',
                             'license': 'REVIEW_REQUIRED', 'rights': 'REVIEW_REQUIRED'}
    stop()
    return {'schema': 'NOX-LOCAL-LIBRARY-INTAKE-v1',
            'status': 'READ_ONLY_SOURCE_CANDIDATES',
            'roots_approved': len(roots_abs), 'files_examined': examined,
            'bytes_hashed': total_bytes,
            'candidates': sorted(seen.values(), key=lambda x: x['sha256']),
            'models_installed': False, 'download_performed': False,
            'source_executed': False, 'imported_into_s03': False,
            'native_admission_required': True, 'reviewed_artifacts': 0}
