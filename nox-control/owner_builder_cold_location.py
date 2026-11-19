"""Read only the exact builder cold-storage transition; no generic symlinks.

The original Drive RAM receipt remains historical evidence.  This separate
root-owned receipt records a full-SHA-verified SSD file and one exact alias.
UI polls compare identities; transfer admission may request a fresh full hash.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/root/nox')
CANONICAL = ROOT / 'progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors'
ALIAS = Path('/dev/shm/nox_drive/3t724u/t724u_builder_best_holdout.safetensors')
RECEIPT = ROOT / 'state/owner_builder_storage_location.json'
RAM_RECEIPT = ROOT / 'state/owner_drive_ram/latest_receipt.json'
SIZE = 306787336
SHA = '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'
SCHEMA = 'NOX_BUILDER_STORAGE_LOCATION_V1'
PROOF_SHA = '51099ab51197ef614141eed6256737a04289e45a252b7d32f5130d8b3a55965c'
FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


class LocationHold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise LocationHold('HOLD_BUILDER_COLD_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {key: getattr(info, key) for key in FIELDS}


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(p.is_symlink() for p in (path, *path.parents)), 'PATH')
    return path


@contextmanager
def opened(path, maximum, *, private=False):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.geteuid() and not before.st_mode & 0o022
                and 0 <= before.st_size <= maximum
                and (not private or stat.S_IMODE(before.st_mode) == 0o600), 'REGULAR_FILE')
        yield fd, before
        require(identity(before) == identity(os.fstat(fd)) == identity(path.lstat()), 'FILE_CHANGED')
    finally:
        os.close(fd)


def read(path, maximum=65536, *, private=False):
    with opened(path, maximum, private=private) as (fd, info):
        raw = os.pread(fd, maximum + 1, 0)
        require(len(raw) == info.st_size, 'READ_SIZE')
        return raw


def document(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'DUPLICATE_JSON'); out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value


def owner_stop():
    return any(p.exists() or p.is_symlink() for p in (
        *(ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP', 'state/DRIVE_STOP.flag')),
        Path('/workspace/NOX_STOP')))


def full_hash(fd, deadline):
    before = os.fstat(fd); require(before.st_size == SIZE, 'HASH_SIZE')
    h = hashlib.sha256(); offset = 0
    while offset < SIZE:
        require(time.monotonic() < deadline and not owner_stop(), 'HASH_DEADLINE_OR_STOP')
        raw = os.pread(fd, min(1024 ** 2, SIZE - offset), offset)
        require(bool(raw), 'HASH_EOF'); h.update(raw); offset += len(raw)
    require(h.hexdigest() == SHA and identity(before) == identity(os.fstat(fd)), 'FULL_SHA_CHANGED')
    return h.hexdigest()


def checked_identity(value):
    require(isinstance(value, dict) and set(value) == set(FIELDS)
            and all(type(value[k]) is int and value[k] >= 0 for k in FIELDS), 'IDENTITY_SCHEMA')
    return value


def locate(*, rehash=False, deadline=None):
    raw = read(RECEIPT, private=True); value = document(raw)
    require(value.get('schema') == SCHEMA and value.get('state') == 'COLD_ON_SSD'
            and re.fullmatch(r'[0-9]{1,24}', value.get('request', ''))
            and re.fullmatch(r'[a-f0-9]{40}', value.get('source_sha', ''))
            and value.get('filename') == ALIAS.name and value.get('role') == 'builder'
            and value.get('bytes') == SIZE and value.get('sha256') == SHA
            and value.get('canonical_path') == str(CANONICAL) and value.get('alias_path') == str(ALIAS)
            and value.get('alias_target') == str(CANONICAL)
            and value.get('canonical_full_sha256_verified') is True
            and value.get('previous_ram_full_sha256_verified') is True
            and value.get('external_drive_proof_canonical_sha256') == PROOF_SHA
            and value.get('ram_resident') is False and value.get('automatic_ram_restage') is False
            and value.get('weights_merged') is False and value.get('active_model_changed') is False,
            'RECEIPT_SCOPE')
    stamp = value.get('verified_at')
    require(type(stamp) in (int, float) and math.isfinite(stamp) and 0 < stamp <= time.time() + 5, 'TIME')
    previous = read(RAM_RECEIPT, private=True)
    require(digest(previous) == value.get('previous_ram_receipt_sha256'), 'PREVIOUS_RAM_RECEIPT_CHANGED')
    canonical_id = checked_identity(value.get('canonical_identity'))
    alias_id = checked_identity(value.get('alias_identity'))
    plain(ALIAS.parent)
    link = ALIAS.lstat()
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == os.geteuid()
            and identity(link) == alias_id and os.readlink(ALIAS) == str(CANONICAL), 'ALIAS_CHANGED')
    with opened(CANONICAL, SIZE) as (fd, info):
        require(info.st_size == SIZE and identity(info) == canonical_id, 'CANONICAL_CHANGED')
        if rehash:
            full_hash(fd, deadline if deadline is not None else time.monotonic() + 30)
    require(identity(ALIAS.lstat()) == alias_id and os.readlink(ALIAS) == str(CANONICAL), 'ALIAS_CHANGED')
    require(read(RECEIPT, private=True) == raw and read(RAM_RECEIPT, private=True) == previous, 'RECEIPT_CHANGED')
    return {'state': 'COLD_ON_SSD', 'role': 'builder', 'filename': ALIAS.name,
            'bytes': SIZE, 'sha256': SHA, 'storage': 'SSD', 'ram_resident': False,
            'automatic_ram_restage': False, 'canonical_path': str(CANONICAL),
            'canonical_identity': canonical_id, 'receipt_sha256': digest(raw),
            'previous_ram_receipt_sha256': digest(previous), 'full_sha_recomputed': rehash,
            'verified_at': stamp}


def public_row(value):
    require(value.get('state') == 'COLD_ON_SSD', 'PUBLIC_ROW')
    return {'kind': 'adapter', 'role': 'builder', 'filename': ALIAS.name,
            'expected_bytes': SIZE, 'verified_bytes': SIZE, 'partial_bytes': 0,
            'state': 'SHA_VERIFIED_CURRENT_FILE', 'storage': 'SSD',
            'location_state': 'COLD_ON_SSD', 'ram_resident': False,
            'automatic_ram_restage': False, 'sha256': SHA,
            'storage_receipt_sha256': value['receipt_sha256']}
