#!/usr/bin/env python3
"""NOX E06 R05: fail-closed, read-only 3-part / 729-member original attestation.

Requires the ORIGINAL raw source parts; historical Git SHA-1 or manifest metadata
alone is insufficient. No extraction, rewriting, or new SourceLock is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PINNED_LOCK_SHA256 = '806c748e939c9acca3c3055ae731a752504ef2723d077c0bb07fd89904fd98df'
PINNED_ARCHIVE_SHA256 = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
PINNED_ARCHIVE_BYTES = 60364346
PINNED_MEMBER_COUNT = 729
PINNED_PART_BYTES = (20971520, 20971520, 18421306)
PINNED_NAMES = ('source_00.part', 'source_01.part', 'source_02.part')
BUFFER = 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _regular_no_links(path: Path) -> int:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or path.is_symlink():
        raise ValueError(f'not an ordinary regular file: {path.name}')
    return st.st_size


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name and '\\' not in name and '\x00' not in name
                and not name.startswith('/') and not name.endswith('/')
                and all(seg not in ('', '.', '..') for seg in name.split('/'))
                and str(p) == name)


def attest(parts_dir: Path, lock_path: Path, *, lock_digest: str = PINNED_LOCK_SHA256,
           archive_digest: str = PINNED_ARCHIVE_SHA256,
           part_sizes: tuple[int, ...] = PINNED_PART_BYTES,
           expected_count: int = PINNED_MEMBER_COUNT) -> dict:
    receipt = {'schema': 'NOX_E06_R05_RAW_SOURCE_PARTS_READ_ONLY_ATTESTATION_V1',
               'status': 'HOLD', 'source_lock': str(lock_path),
               'source_lock_sha256': 'N/D', 'archive_sha256': 'N/D',
               'parts': [], 'file_members_verified': 0, 'error': None,
               'raw_original_verified': False}
    try:
        _regular_no_links(lock_path)
        raw_lock = lock_path.read_bytes()
        receipt['source_lock_sha256'] = sha256(raw_lock)
        if receipt['source_lock_sha256'] != lock_digest:
            raise ValueError('immutable SourceLock SHA-256 mismatch')
        lock = json.loads(raw_lock)
        files = lock.get('files')
        if not isinstance(files, list) or len(files) != expected_count:
            raise ValueError('SourceLock file-count mismatch')
        expected = {}
        for row in files:
            name, digest, size = row['path'], row['sha256'], row['bytes']
            if not _safe_member(name) or name.casefold() in (k.casefold() for k in expected):
                raise ValueError(f'unsafe/duplicate SourceLock path: {name}')
            if not isinstance(size, int) or size < 0 or len(digest) != 64:
                raise ValueError(f'invalid SourceLock row: {name}')
            expected[name] = (digest, size)
        if tuple(part_sizes) != PINNED_PART_BYTES and expected_count == PINNED_MEMBER_COUNT:
            raise ValueError('original expected part lengths cannot be overridden')
        with tempfile.TemporaryFile(mode='w+b') as stream:
            joined = hashlib.sha256()
            total = 0
            for name, expected_size in zip(PINNED_NAMES, part_sizes, strict=True):
                part = parts_dir / name
                size = _regular_no_links(part)
                if size != expected_size:
                    raise ValueError(f'{name}: size {size} != expected {expected_size}')
                digest = hashlib.sha256()
                with part.open('rb') as source:
                    while chunk := source.read(BUFFER):
                        digest.update(chunk)
                        joined.update(chunk)
                        stream.write(chunk)
                        total += len(chunk)
                receipt['parts'].append({'path': name, 'bytes': size,
                                         'raw_sha256': digest.hexdigest(),
                                         'git_blob_sha1': 'NOT_COMPUTED'})
            receipt['archive_bytes'] = total
            receipt['archive_sha256'] = joined.hexdigest()
            if total != sum(part_sizes) or receipt['archive_sha256'] != archive_digest:
                raise ValueError('concatenated original archive size/SHA-256 mismatch')
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                seen = set()
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    if not _safe_member(name) or name.casefold() in seen:
                        raise ValueError(f'unsafe/duplicate archive member: {name}')
                    seen.add(name.casefold())
                    if name not in expected:
                        raise ValueError(f'unlisted member in original ZIP: {name}')
                    digest_expected, size_expected = expected[name]
                    if info.file_size != size_expected:
                        raise ValueError(f'member length mismatch: {name}')
                    if (info.external_attr >> 16) & 0o170000 == stat.S_IFLNK:
                        raise ValueError(f'ZIP symlink not accepted: {name}')
                    digest = hashlib.sha256()
                    count = 0
                    with archive.open(info) as member:
                        while chunk := member.read(BUFFER):
                            digest.update(chunk)
                            count += len(chunk)
                            if count > size_expected:
                                raise ValueError(f'member expands beyond manifest: {name}')
                    if count != size_expected or digest.hexdigest() != digest_expected:
                        raise ValueError(f'member SHA-256 mismatch: {name}')
                    receipt['file_members_verified'] += 1
                if receipt['file_members_verified'] != expected_count:
                    raise ValueError('missing members from the original ZIP')
        receipt['status'] = 'RAW_BYTES_VERIFIED'
        receipt['raw_original_verified'] = True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            zipfile.BadZipFile, RuntimeError) as exc:
        receipt['error'] = str(exc)
    return receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parts-dir', type=Path, required=True)
    p.add_argument('--immutable-lock', type=Path, required=True)
    a = p.parse_args()
    result = attest(a.parts_dir, a.immutable_lock)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result['raw_original_verified'] else 2


if __name__ == '__main__':
    sys.exit(main())
