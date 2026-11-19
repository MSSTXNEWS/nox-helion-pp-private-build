#!/usr/bin/env python3
"""Offline, no-clobber assembly for *already staged* NOX split ZIP artifacts.

Used only for V13 pre-production library reuse. Never downloads, extracts,
starts a NOX service, resets STOP or installs packages. Both the part SHA256
and assembled archive SHA256 must be pinned before publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

CHUNK = 1024 * 1024
RESERVE = 256 * 1024 * 1024
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PARTS = 1024


def _reject_duplicate_keys(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("HOLD_DUPLICATE_MANIFEST_KEY")
        result[k] = v
    return result


def _name(x):
    if (not isinstance(x, str) or not x or x in ('.', '..') or
            x.startswith('.') or '/' in x or '\\' in x or Path(x).name != x):
        raise ValueError("HOLD_INVALID_LOCAL_NAME")
    return x


def _hash(x):
    if not isinstance(x, str) or SHA_RE.fullmatch(x) is None:
        raise ValueError("HOLD_INVALID_SHA256")
    return x


def _reject_nonfinite(value):
    raise ValueError("HOLD_MANIFEST_NONFINITE_JSON")


def _read_manifest_bounded(path):
    """No unbounded JSON allocation from a Drive/staging manifest."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("HOLD_MANIFEST_NOT_REGULAR")
        payload = f.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("HOLD_MANIFEST_TOO_LARGE")
    data = json.loads(payload.decode('utf-8'),
                      object_pairs_hook=_reject_duplicate_keys,
                      parse_constant=_reject_nonfinite)
    if not isinstance(data, dict):
        raise ValueError("HOLD_INVALID_MANIFEST_ROOT")
    return data


def _digest(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("HOLD_NONREGULAR_FILE")
        for b in iter(lambda: f.read(CHUNK), b''):
            h.update(b)
    return h.hexdigest()


def assemble(manifest_path: Path, *, before_publish=None, reserve=RESERVE):
    """Publish by *atomic no-overwrite hard link*; fail closed on unsupported FS.

    before_publish is a test-only injection point; production CLI never sets it.
    """
    manifest_path = Path(manifest_path).resolve(strict=True)
    root = manifest_path.parent
    m = _read_manifest_bounded(manifest_path)
    if m.get('schema') != 'NOX_SPLIT_ARCHIVE_V1':
        raise ValueError("HOLD_UNKNOWN_MANIFEST_SCHEMA")
    name = _name(m['archive'])
    archive_sha = _hash(m['archive_sha256'])
    total, parts = m['archive_bytes'], m['parts']
    if type(total) is not int or total <= 0 or not isinstance(parts, list) or not parts:
        raise ValueError("HOLD_INVALID_MANIFEST_SIZE")
    if len(parts) > MAX_PARTS:
        raise ValueError("HOLD_TOO_MANY_ARCHIVE_PARTS")
    if any(not isinstance(p, dict) for p in parts):
        raise ValueError("HOLD_INVALID_ARCHIVE_PART")
    known = set()
    for p in parts:
        f = _name(p['file'])
        if f == name or f in known:
            raise ValueError("HOLD_DUPLICATE_PART_PATH")
        known.add(f)
        if type(p.get('bytes')) is not int or p['bytes'] <= 0:
            raise ValueError("HOLD_INVALID_PART_SIZE")
        _hash(p['sha256'])
    if sum(p['bytes'] for p in parts) != total:
        raise ValueError("HOLD_PART_TOTAL_MISMATCH")
    dest = root / name
    if dest.is_file() and not dest.is_symlink() and dest.stat().st_size == total:
        if _digest(dest) == archive_sha:
            return dest  # Verified reuse: no disk bytes written
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("HOLD_EXISTING_ARCHIVE_DIFFERENT")
    if shutil.disk_usage(root).free < total + reserve:
        raise OSError("HOLD_INSUFFICIENT_DISK_RESERVE")
    tmp = root / (name + '.assembling-' + str(os.getpid()))
    if tmp.exists() or tmp.is_symlink():
        raise FileExistsError("HOLD_TEMPORARY_PATH_IN_USE")
    try:
        full_hash = hashlib.sha256()
        with tmp.open('xb') as out:
            for p in parts:
                src = root / p['file']
                fd = os.open(src, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                with os.fdopen(fd, 'rb') as inp:
                    st = os.fstat(inp.fileno())
                    if not stat.S_ISREG(st.st_mode) or st.st_size != p['bytes']:
                        raise ValueError("HOLD_PART_NOT_REGULAR_OR_SIZE_MISMATCH")
                    count = 0
                    h = hashlib.sha256()
                    for block in iter(lambda: inp.read(CHUNK), b''):
                        count += len(block)
                        if count > p['bytes']:
                            raise ValueError("HOLD_PART_GROWTH_DURING_READ")
                        h.update(block)
                        full_hash.update(block)
                        out.write(block)
                    if count != p['bytes'] or h.hexdigest() != p['sha256']:
                        raise ValueError("HOLD_PART_DIGEST_MISMATCH")
            out.flush()
            os.fsync(out.fileno())
        if tmp.stat().st_size != total or full_hash.hexdigest() != archive_sha:
            raise ValueError("HOLD_ASSEMBLED_DIGEST_MISMATCH")
        if before_publish is not None:
            before_publish(dest)
        # os.rename() can overwrite a file created after an exists() check!
        # os.link() is atomic no-clobber, on same filesystem, even under a race.
        os.link(tmp, dest, follow_symlinks=False)
        tmp.unlink()
        return dest
    finally:
        if tmp.exists():
            tmp.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    print('SOURCE_VERIFIED_OFFLINE_ONLY:', assemble(args.manifest))
