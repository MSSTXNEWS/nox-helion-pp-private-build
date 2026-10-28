#!/usr/bin/env python3
"""NOX V16 E06: one read-only, fail-closed no-loss gate over the EXISTING unified staging tree.

No new host, downloader, chat, database, renderer, or installer. The original 729-file
source archive audit is delegated to the repository's existing source-lock module.
A source PASS is deliberately NOT an installed/release acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

SCHEMA = 'NOX_V16_EXPRESS_MAIN_BLOB_LOCK_V1'
REPO = 'MSSTXNEWS/nox-helion-pp-private-build'
ORIGINAL_BASE = '0b3a7d435be735148d64171deb9027093a89646e'
REQUIRED_PARTS = ('source_00.part', 'source_01.part', 'source_02.part')


class Hold(ValueError):
    pass


def regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise Hold(f'MISSING_OR_UNREADABLE:{path}') from exc
    if (not stat.S_ISREG(info.st_mode) or
            (getattr(info, 'st_file_attributes', 0) &
             getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))):
        raise Hold(f'SYMLINK_REPARSE_OR_SPECIAL:{path}')
    return info


def stream_hash(path: Path, algorithm: str) -> tuple[str, int]:
    before = regular_file(path)
    h = hashlib.new(algorithm)
    if algorithm == 'sha1':
        h.update(f'blob {before.st_size}\0'.encode('ascii'))
    read = 0
    with path.open('rb') as f:
        opened = os.fstat(f.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != before.st_dev or
                opened.st_ino != before.st_ino or opened.st_size != before.st_size):
            raise Hold(f'RACE_OR_REPLACED:{path}')
        for chunk in iter(lambda: f.read(1 << 20), b''):
            read += len(chunk)
            h.update(chunk)
    after = regular_file(path)
    if (read != before.st_size or after.st_ino != before.st_ino or
            after.st_dev != before.st_dev or after.st_size != before.st_size):
        raise Hold(f'SOURCE_CHANGED_DURING_AUDIT:{path}')
    return h.hexdigest(), read


def safe_relpath(name: str) -> bool:
    # A portable Windows staging path must not contain case collisions, UNC,
    # traversal, trailing spaces/periods or device-name components.
    from re import compile, IGNORECASE
    reserved = compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', IGNORECASE)
    if not isinstance(name, str) or not name or name.startswith('/') or '\\' in name:
        return False
    parts = name.split('/')
    return all(p not in ('', '.', '..') and not p.endswith((' ', '.'))
               and not any(c in p for c in '<>:"|?*\x00\r\n')
               and not reserved.match(p) for p in parts)


def verify_tracked(root: Path, lock: dict) -> list[dict]:
    if not isinstance(lock, dict) or not isinstance(lock.get('files'), list):
        raise Hold('INVALID_LOCK_SCHEMA')
    seen, evidence = set(), []
    for row in lock['files']:
        if not isinstance(row, dict):
            raise Hold('INVALID_LOCK_ROW')
        rel, sha = row.get('path'), row.get('git_blob_sha1')
        if not safe_relpath(rel) or not isinstance(sha, str) or len(sha) != 40:
            raise Hold('UNSAFE_OR_UNPINNED_ORIGINAL_PATH')
        if rel.casefold() in seen:
            raise Hold('DUPLICATE_ORIGINAL_CASEFOLD_PATH')
        seen.add(rel.casefold())
        observed, size = stream_hash(root / rel, 'sha1')
        if observed != sha:
            raise Hold(f'ORIGINAL_BLOB_MISMATCH:{rel}')
        evidence.append({'path': rel, 'bytes': size, 'git_blob_sha1': observed})
    for part in REQUIRED_PARTS:
        if part not in {x['path'] for x in evidence}:
            raise Hold(f'ORIGINAL_ARCHIVE_PART_UNPINNED:{part}')
    return evidence


def scan_stage(root: Path) -> dict:
    files: list[dict] = []
    cases = set()
    for folder, dirs, filenames in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '.git')
        for d in dirs:
            p = Path(folder) / d
            info = p.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or (
                getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
                raise Hold('STAGE_UNSAFE_DIRECTORY:' + str(p))
        for name in sorted(filenames):
            p = Path(folder) / name
            rel = p.relative_to(root).as_posix()
            if not safe_relpath(rel):
                raise Hold('STAGE_UNSAFE_PATH:' + rel)
            folded = rel.casefold()
            if folded in cases:
                raise Hold('STAGE_WINDOWS_CASE_COLLISION:' + rel)
            cases.add(folded)
            sha, size = stream_hash(p, 'sha256')
            files.append({'path': rel, 'bytes': size, 'sha256': sha})
    return {'file_count': len(files), 'files': sorted(files, key=lambda r: r['path'])}


def delegate_original_archive_audit(root: Path) -> dict:
    path = root / 'coordination' / 'source-lock' / 'verify_original_archive.py'
    regular_file(path)
    spec = importlib.util.spec_from_file_location('nox_original_existing_audit', path)
    if spec is None or spec.loader is None:
        raise Hold('ORIGINAL_ARCHIVE_AUDIT_UNAVAILABLE')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.audit(root, 729)


def audit(root: Path, lock: dict, *, original_zip=True) -> dict:
    if lock.get('schema') != SCHEMA or lock.get('repository') != REPO or lock.get('original_main_commit') != ORIGINAL_BASE:
        raise Hold('BASELINE_LOCK_SCHEMA_OR_COMMIT_MISMATCH')
    if len(lock.get('files', [])) != 25:
        raise Hold('ORIGINAL_MAIN_EXPECTED_25_FILE_BLOBS')
    originals = verify_tracked(root, lock)
    stage = scan_stage(root)
    if stage['file_count'] < len(originals):
        raise Hold('STAGE_FELL_BELOW_ORIGINAL_FILE_COUNT')
    original = delegate_original_archive_audit(root) if original_zip else None
    return {
        'schema': 'NOX_V16_E06_EXPRESS_STAGE_READONLY_SHA_V1',
        'status': 'SOURCE_AUDITED_RELEASE_HOLD',
        'acceptance': {'one_host': 'NOT_VERIFIED', 'native_windows_exe': 'NOT_RUN', 'e07_same_sha': 'NOT_RUN'},
        'original_baseline': lock['original_main_commit'],
        'original_tracked_file_count': len(originals),
        'original_tracked': originals,
        'stage': stage,
        'original_729_archive': original,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--lock', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.absolute()
        if not root.is_dir() or root.is_symlink():
            raise Hold('UNTRUSTED_STAGING_DIRECTORY')
        lock = json.loads(args.lock.read_text(encoding='utf-8'))
        result = audit(root, lock)
        # Outputs are receipts, not a mutation of sources; preserve old receipts.
        if args.output.is_symlink() or args.output.exists():
            raise Hold('RECEIPT_PATH_ALREADY_EXISTS')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(json.dumps({k: v for k, v in result.items() if k not in ('original_tracked', 'stage', 'original_729_archive')}))
        print('STAGED_GIT_FILES=', result['stage']['file_count'])
        print('ZIP_729_SOURCE_VERIFIED=', result['original_729_archive']['file_count'] == 729)
        print('FINAL_EXE_AND_E07=HOLD')
        return 0
    except (OSError, Hold, ValueError) as exc:
        print(json.dumps({'status': 'HOLD', 'reason': str(exc)}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())