#!/usr/bin/env python3
"""NOX E07 pre-deserialization JSON provenance validation.

Independent QA helper for the original three immutable receipts. Never edits a
receipt, never emits a BuildID or asserts installed Windows acceptance. The
single product integrator decides if this helper is admitted into existing E06.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import stat
import sys
import unicodedata

MAX_RECEIPT_BYTES = 4_194_304


def read_unambiguous(path: Path) -> dict:
    path = path.absolute()
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, 'st_file_attributes', 0) &
            getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        ):
            raise ValueError('E07_RECEIPT_REPARSE_HOLD')
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_RECEIPT_BYTES:
        raise ValueError('E07_RECEIPT_MISSING_OR_TOO_LARGE')
    with path.open('rb') as handle:
        raw = handle.read(MAX_RECEIPT_BYTES + 1)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('E07_RECEIPT_TOO_LARGE')
    try:
        data = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise ValueError('E07_RECEIPT_NOT_UTF8') from exc

    def unique(pairs):
        out, names = {}, set()
        for key, value in pairs:
            normalized = unicodedata.normalize('NFC', key).casefold()
            if not key or normalized in names:
                raise ValueError('E07_RECEIPT_DUPLICATE_JSON_PROPERTY')
            names.add(normalized)
            out[key] = value
        return out

    def nonfinite(_):
        raise ValueError('E07_RECEIPT_NONFINITE_NUMBER')

    def finite_float(token):
        number = float(token)
        if not math.isfinite(number):
            raise ValueError('E07_RECEIPT_NONFINITE_NUMBER')
        return number

    try:
        parsed = json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite,
                            parse_float=finite_float)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('E07_RECEIPT_INVALID_JSON') from exc
    if not isinstance(parsed, dict):
        raise ValueError('E07_RECEIPT_OBJECT_REQUIRED')
    return {'schema': parsed.get('schema'), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'status': 'RAW_JSON_UNAMBIGUOUS_ONLY'}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ('original', 'owner', 'onehost'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    proof = {}
    try:
        for name in ('original', 'owner', 'onehost'):
            proof[name] = read_unambiguous(getattr(args, name))
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'HOLD', 'reason': str(exc),
                          'release_accepted': False}), file=sys.stderr)
        return 2
    print(json.dumps({'status': 'PASS_SOURCE_JSON_ONLY', 'receipts': proof,
                      'release_accepted': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
