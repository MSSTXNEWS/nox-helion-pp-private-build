"""Fail-closed, bounded native receipt admission for the original E06 WPF builder.

On success stdout is ONE line: raw SHA256, a TAB, and unambiguous JSON.
No policy grant is generated; the existing PowerShell release gates still apply.
"""
import hashlib
import json
import math
import os
import stat
import sys

MAX_PROOF_BYTES = 1024 * 1024
MAX_DEPTH = 48


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("nonfinite number")
    return value


def _integer(raw):
    value = int(raw)
    if value < -(2**63) or value > (2**63 - 1):
        raise ValueError("integer out of range")
    return value


def _reject_constant(_):
    raise ValueError("nonfinite constant")


def _check(node, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("excessive JSON depth")
    if isinstance(node, dict):
        for k, v in node.items():
            _check(k, depth + 1)
            _check(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _check(v, depth + 1)
    elif isinstance(node, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in node):
            raise ValueError("unpaired surrogate")


def admit(path):
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or (
        getattr(metadata, 'st_file_attributes', 0) & 0x400
    ):
        raise ValueError("nonregular or reparse receipt")
    if metadata.st_size < 2 or metadata.st_size > MAX_PROOF_BYTES:
        raise ValueError("receipt size")
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or (
            getattr(current, 'st_file_attributes', 0) & 0x400
        ):
            raise ValueError("redirected descriptor")
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(MAX_PROOF_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) < 2 or len(data) > MAX_PROOF_BYTES:
        raise ValueError("receipt read size")
    decoded = data.decode('utf-8-sig', errors='strict')
    obj = json.loads(decoded, object_pairs_hook=_unique,
                     parse_float=_number, parse_int=_integer,
                     parse_constant=_reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("receipt root must be object")
    _check(obj)
    canonical = json.dumps(obj, ensure_ascii=True,
                           allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(data).hexdigest() + '\t' + canonical


def main():
    if len(sys.argv) != 2:
        raise ValueError("one receipt path required")
    print(admit(sys.argv[1]))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, UnicodeError, RecursionError, json.JSONDecodeError):
        print("E06_NATIVE_RECEIPT_STRICT_JSON_HOLD", file=sys.stderr)
        sys.exit(2)
