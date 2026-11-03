"""Read-only independent E07 frozen-artifact admission. NOT QA01–QA10 acceptance.

Checks physical binaries and two already-produced official E07 handoffs on a
single immutable SetupSHA. It never rebuilds, installs, grants PASS or writes
release receipts. Manual independent E07 still requires 10 real Windows tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ORIGINAL_ZIP = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
LOG_NAMES = ('install', 'launch', 'update', 'rollback', 'uninstall')
IDENTITY_FIELDS = ('build_id', 'source_commit_sha1', 'original_zip_sha256',
                   'original_manifest_sha256', 'owner_729_manifest_sha256',
                   'e06_onehost_receipt_sha256', 'setup_sha256',
                   'published_exe_sha256')


class Hold(RuntimeError):
    """Fail-closed rejection; no release status is implied."""


def need(condition: bool, error_id: str) -> None:
    if not condition:
        raise Hold(error_id)


def _no_reparse(path: Path) -> None:
    current = path.absolute()
    while True:
        try:
            st = current.lstat()
        except FileNotFoundError:
            raise Hold('E07_INDEPENDENT_INPUT_MISSING') from None
        need(not stat.S_ISLNK(st.st_mode) and not
             bool(getattr(st, 'st_file_attributes', 0) & 0x400),
             'E07_INDEPENDENT_REPARSE_INPUT_HOLD')
        if current.parent == current:
            break
        current = current.parent


def _fingerprint(path: Path, max_bytes: int | None = None) -> tuple[bytes, str, int]:
    """Read a file using one descriptor and validate unchanged path identity."""
    _no_reparse(path)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Hold('E07_INDEPENDENT_OPEN_HOLD') from exc
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size > 0 and
             (max_bytes is None or before.st_size <= max_bytes),
             'E07_INDEPENDENT_INPUT_SIZE_HOLD')
        digest = hashlib.sha256()
        prefix = b''
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
            if len(prefix) < (max_bytes or 4096):
                prefix += chunk[:(max_bytes or 4096) - len(prefix)]
        after = os.fstat(fd)
        path_stat = path.lstat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size,
                              s.st_mtime_ns, s.st_ctime_ns)
        need(identity(before) == identity(after) == identity(path_stat),
             'E07_INDEPENDENT_FILE_IDENTITY_CHANGED_HOLD')
        _no_reparse(path)
        return prefix, digest.hexdigest(), before.st_size
    finally:
        os.close(fd)


def _receipt(path: Path) -> dict:
    raw, _, size = _fingerprint(path, max_bytes=8_388_608)
    need(len(raw) == size, 'E07_INDEPENDENT_RECEIPT_TRUNCATED_HOLD')
    def unique_pairs(pairs):
        values = {}
        seen = set()
        for key, value in pairs:
            folded = key.casefold()
            if folded in seen:
                raise ValueError('duplicate/case-ambiguous JSON key')
            seen.add(folded)
            values[key] = value
        return values
    try:
        data = json.loads(raw.decode('utf-8', 'strict'),
                          object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Hold('E07_INDEPENDENT_AMBIGUOUS_RECEIPT_JSON_HOLD') from exc
    need(type(data) is dict, 'E07_INDEPENDENT_RECEIPT_SCHEMA_HOLD')
    return data


def _physical_pe(path: Path) -> str:
    prefix, digest, size = _fingerprint(path)
    need(size >= 256 and prefix[:2] == b'MZ' and len(prefix) >= 0x40,
         'E07_INDEPENDENT_NOT_PE_BINARY_HOLD')
    offset = int.from_bytes(prefix[0x3c:0x40], 'little')
    need(0x40 <= offset <= 4092 and prefix[offset:offset+4] == b'PE\x00\x00',
         'E07_INDEPENDENT_PE_HEADER_HOLD')
    return digest


def check(built_path: Path, installed_path: Path, setup: Path,
          published: Path, installed_exe: Path, logs: dict[str, Path],
          expected_commit: str, expected_setup_sha: str) -> dict:
    need(bool(HEX40.fullmatch(expected_commit)) and
         bool(HEX64.fullmatch(expected_setup_sha)),
         'E07_INDEPENDENT_EXPECTED_IDENTITY_INVALID')
    # A physical installed file is required, not the build-output executable.
    need(installed_exe.absolute() != published.absolute() and
         not os.path.samefile(installed_exe, published),
         'E07_INDEPENDENT_INSTALLED_BINARY_NOT_SEPARATE')
    built, actual = _receipt(built_path), _receipt(installed_path)
    for row, phase in ((built, 'BUILT'), (actual, 'INSTALLED')):
        need(row.get('schema') == 'NOX_V16_E07_IMMUTABLE_HANDOFF_V1' and
             row.get('phase') == phase and
             row.get('release_accepted') is False and
             type(row.get('independent_e07_cases_accepted')) is int and
             row['independent_e07_cases_accepted'] == 0 and
             row.get('source_receipts_729_parity_verified') is True and
             type(row.get('source_files')) is int and row['source_files'] == 729,
             'E07_INDEPENDENT_HANDOFF_CONTRACT_HOLD')
        need(all(type(row.get(k)) is str and row[k] for k in IDENTITY_FIELDS),
             'E07_INDEPENDENT_HANDOFF_IDENTITY_MISSING')
    need(all(built[k] == actual[k] for k in IDENTITY_FIELDS),
         'E07_INDEPENDENT_BUILD_INSTALLED_IDENTITY_DRIFT')
    # Bind the claimed BuildID to the *actual* original owner recipe, not
    # merely the identical text copied into two handoffs.
    identity = '|'.join((ORIGINAL_ZIP, expected_commit,
                         expected_setup_sha, actual['published_exe_sha256']))
    computed_id = 'NOX-V16-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
    need(actual['build_id'] == computed_id,
         'E07_INDEPENDENT_BUILDID_RECIPE_DRIFT')
    need(actual['source_commit_sha1'] == expected_commit and
         actual['original_zip_sha256'] == ORIGINAL_ZIP and
         actual['setup_sha256'] == expected_setup_sha and
         bool(HEX64.fullmatch(actual['published_exe_sha256'])) and
         all(bool(HEX64.fullmatch(actual[k])) for k in (
             'original_manifest_sha256', 'owner_729_manifest_sha256',
             'e06_onehost_receipt_sha256')),
         'E07_INDEPENDENT_UNPINNED_IDENTITY_HOLD')
    need(built.get('installed_exe_sha256') is None and
         built.get('lifecycle_log_sha256') in ({}, None),
         'E07_INDEPENDENT_BUILT_PRETENDS_INSTALLED_HOLD')
    hashes = actual.get('lifecycle_log_sha256')
    need(type(hashes) is dict and set(hashes) == set(LOG_NAMES) and
         set(logs) == set(LOG_NAMES),
         'E07_INDEPENDENT_LIFECYCLE_EVIDENCE_MISSING')
    need(_physical_pe(setup) == expected_setup_sha,
         'E07_INDEPENDENT_PHYSICAL_SETUP_SHA_DRIFT')
    published_sha = _physical_pe(published)
    installed_sha = _physical_pe(installed_exe)
    need(published_sha == installed_sha == actual['published_exe_sha256'] ==
         actual.get('installed_exe_sha256'),
         'E07_INDEPENDENT_INSTALLED_WPF_SHA_DRIFT')
    for name in LOG_NAMES:
        need(type(hashes[name]) is str and bool(HEX64.fullmatch(hashes[name])),
             'E07_INDEPENDENT_LIFECYCLE_LOG_PIN_MISSING:' + name)
        _, actual_hash, _ = _fingerprint(logs[name], max_bytes=16_777_216)
        need(actual_hash == hashes[name],
             'E07_INDEPENDENT_LIFECYCLE_LOG_SHA_DRIFT:' + name)
    # Final physical readback closes source/identity drift during verification.
    need(_physical_pe(setup) == expected_setup_sha and
         _physical_pe(published) == published_sha and
         _physical_pe(installed_exe) == installed_sha,
         'E07_INDEPENDENT_BINARY_MUTATED_DURING_CHECK')
    return {'status': 'SHA_PREFLIGHT_PASS_NOT_E07_ACCEPTANCE',
            'build_id': actual['build_id'], 'setup_sha256': expected_setup_sha,
            'installed_wpf_sha256': installed_sha,
            'independent_e07_cases_accepted': 0, 'release_accepted': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('built', 'installed', 'setup', 'published', 'installed-exe',
                 'install-log', 'launch-log', 'update-log', 'rollback-log',
                 'uninstall-log'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--setup-sha256', required=True)
    args = parser.parse_args()
    log_paths = {name: getattr(args, name + '_log') for name in LOG_NAMES}
    try:
        result = check(args.built, args.installed, args.setup, args.published,
                       args.installed_exe, log_paths, args.source_commit,
                       args.setup_sha256)
    except (Hold, OSError) as exc:
        print('E07_INDEPENDENT_SHA_PREFLIGHT_HOLD', str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
