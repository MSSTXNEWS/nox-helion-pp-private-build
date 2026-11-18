#!/usr/bin/env python3
"""Read-only bounded witness for an already-running GGUF serving process.

No model calls, supervisor actions, environment reads or full-weight hashing.
Evidence is scoped to PID start ticks, mapped file inode and parsed GGUF metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

MAX_CMDLINE = 8192
MAX_MAPS = 8 * 1024 * 1024
MAX_GGUF_HEADER = 16 * 1024 * 1024
MAX_KV = 256
MAX_ARRAY_ITEMS = 262144  # Per individual array, not combined across all fields.
MAX_TOTAL_VALUES = 4194304  # CPU bound; accommodates multi-array tokenizers.
MAX_STRING = 131072
TARGET_KEYS = {"general.name", "tokenizer.ggml.model", "tokenizer.ggml.pre", "tokenizer.chat_template"}


class EvidenceUnavailable(Exception):
    pass


def pid_start_ticks(pid: int, proc_root: Path = Path('/proc')) -> int:
    text = (proc_root / str(pid) / 'stat').read_text()
    if ') ' not in text:
        raise EvidenceUnavailable('BAD_PROC_STAT')
    fields = text.rsplit(') ', 1)[1].split()
    if len(fields) < 20:
        raise EvidenceUnavailable('SHORT_PROC_STAT')
    return int(fields[19])


def model_arg(pid: int, proc_root: Path = Path('/proc')) -> str | None:
    with (proc_root / str(pid) / 'cmdline').open('rb') as stream:
        raw = stream.read(MAX_CMDLINE + 1)
    if len(raw) > MAX_CMDLINE:
        raise EvidenceUnavailable('CMDLINE_TOO_LONG')
    args = [x.decode('utf-8', 'surrogateescape') for x in raw.split(b'\0') if x]
    for idx, value in enumerate(args):
        if value in ('-m', '--model', '--model-path') and idx + 1 < len(args):
            return args[idx + 1]
        for prefix in ('--model=', '--model-path='):
            if value.startswith(prefix):
                return value[len(prefix):]
    return None


def mapped_inode(pid: int, dev: int, inode: int, proc_root: Path = Path('/proc')) -> bool:
    total = 0
    with (proc_root / str(pid) / 'maps').open('rb') as stream:
        for raw in stream:
            total += len(raw)
            if total > MAX_MAPS:
                raise EvidenceUnavailable('MAPS_BUDGET_EXCEEDED')
            parts = raw.split(None, 5)
            if len(parts) < 5:
                continue
            try:
                major_s, minor_s = parts[3].decode('ascii').split(':', 1)
                matching = (int(major_s, 16) == os.major(dev)
                            and int(minor_s, 16) == os.minor(dev)
                            and int(parts[4]) == inode and inode > 0)
            except (ValueError, UnicodeError):
                matching = False
            if matching:
                return True
    return False


class HeaderReader:
    def __init__(self, stream):
        self.stream = stream
        self.offset = 0
        self.actions = 0
        self.digest = None  # Only selected metadata bytes, never tensor data.

    def read(self, n):
        if n < 0 or self.offset + n > MAX_GGUF_HEADER:
            raise EvidenceUnavailable('GGUF_HEADER_BUDGET')
        data = self.stream.read(n)
        if len(data) != n:
            raise EvidenceUnavailable('TRUNCATED_GGUF')
        self.offset += n
        if self.digest is not None:
            self.digest.update(data)
        return data

    def scalar(self, fmt):
        return struct.unpack('<' + fmt, self.read(struct.calcsize('<' + fmt)))[0]

    def string(self, store=False):
        size = self.scalar('Q')
        if size > MAX_STRING:
            raise EvidenceUnavailable('GGUF_STRING_BUDGET')
        raw = self.read(size)
        return raw if store else None

    def value(self, kind, store=False):
        self.actions += 1
        if self.actions > MAX_TOTAL_VALUES:
            raise EvidenceUnavailable('GGUF_TOTAL_VALUE_BUDGET')
        fmt = {0:'B', 1:'b', 2:'H', 3:'h', 4:'I', 5:'i', 6:'f', 7:'B',
               10:'Q', 11:'q', 12:'d'}
        if kind in fmt:
            out = self.scalar(fmt[kind])
            return out if store else None
        if kind == 8:
            return self.string(store)
        if kind == 9:
            child_kind = self.scalar('I')
            count = self.scalar('Q')
            if count > MAX_ARRAY_ITEMS:
                raise EvidenceUnavailable('GGUF_ARRAY_COUNT_BUDGET')
            for _ in range(count):
                self.value(child_kind, False)
            return None
        raise EvidenceUnavailable('UNSUPPORTED_GGUF_TYPE')


def gguf_metadata(stream):
    reader = HeaderReader(stream)
    if reader.read(4) != b'GGUF':
        raise EvidenceUnavailable('NOT_GGUF')
    version = reader.scalar('I')
    if version not in (2, 3):
        raise EvidenceUnavailable('UNSUPPORTED_GGUF_VERSION')
    n_tensors, n_kv = reader.scalar('Q'), reader.scalar('Q')
    if n_kv > MAX_KV:
        raise EvidenceUnavailable('GGUF_KV_BUDGET')
    found = {}
    tokenizer_digest = hashlib.sha256()
    tokenizer_fields = 0
    for _ in range(n_kv):
        key_bytes = reader.string(True)
        key = key_bytes.decode('utf-8', 'strict')
        kind = reader.scalar('I')
        # Include *all* tokenizer.* metadata (vocab, merges, scores, types,
        # templates and extension keys), not just the short display fields.
        # The digest is a bounded GGUF metadata fingerprint, NOT a tokenizer
        # file SHA, weight SHA, or proof of which tokenizer serving uses.
        if key.startswith('tokenizer.'):
            tokenizer_digest.update(struct.pack('<Q', len(key_bytes)))
            tokenizer_digest.update(key_bytes)
            tokenizer_digest.update(struct.pack('<I', kind))
            tokenizer_fields += 1
            reader.digest = tokenizer_digest
        try:
            value = reader.value(kind, key in TARGET_KEYS)
        finally:
            reader.digest = None
        if key in TARGET_KEYS and isinstance(value, bytes):
            found[key] = {'sha256': hashlib.sha256(value).hexdigest(),
                          'length': len(value)}
            if key != 'tokenizer.chat_template':
                found[key]['value'] = value.decode('utf-8', 'replace')[:160]
    return {'version': version, 'tensor_count': n_tensors,
            'kv_count': n_kv, 'metadata': found, 'header_bytes_parsed': reader.offset,
            'tokenizer_metadata_fields': tokenizer_fields,
            'tokenizer_metadata_sha256': tokenizer_digest.hexdigest() if tokenizer_fields else None,
            'tokenizer_metadata_scope': 'GGUF_TOKENIZER_FIELDS_ONLY_NOT_RUNTIME_TOKENIZER_FILE'}


def _file_signature(st):
    """Identity plus mutation stamps; atime deliberately ignored."""
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def witness(pid: int, expected_start_ticks: int, model_file: str | None = None,
            proc_root: Path = Path('/proc')) -> dict:
    result = {'schema': 'NOX_MODEL_IDENTITY_WITNESS_V1', 'pid': pid,
              'expected_start_ticks': expected_start_ticks, 'scope': 'READ_ONLY',
              'loaded_model_sha256': None, 's03_result': 'NOT_CHECKED'}
    try:
        before = pid_start_ticks(pid, proc_root)
        if before != expected_start_ticks:
            raise EvidenceUnavailable('PID_START_TICKS_MISMATCH')
        arg = model_arg(pid, proc_root)
        chosen = model_file if model_file is not None else arg
        if not chosen:
            raise EvidenceUnavailable('MODEL_PATH_NOT_IN_CMDLINE')
        with open(chosen, 'rb') as f:
            st = os.fstat(f.fileno())
            mapped = mapped_inode(pid, st.st_dev, st.st_ino, proc_root)
            metadata = gguf_metadata(f)
            # Parsing a current pathname is not evidence for the mapped file
            # if that pathname was replaced or the inode mutated mid-probe.
            if (_file_signature(os.fstat(f.fileno())) != _file_signature(st)
                    or _file_signature(os.stat(chosen)) != _file_signature(st)):
                raise EvidenceUnavailable('MODEL_FILE_CHANGED_DURING_PROBE')
            result.update({'model_file': chosen, 'model_size': st.st_size,
                           'model_inode': st.st_ino, 'model_device': st.st_dev,
                           'model_cmdline_match': arg == chosen,
                           'file_inode_mapped_by_pid': mapped,
                           'gguf': metadata})
        if pid_start_ticks(pid, proc_root) != before:
            raise EvidenceUnavailable('PID_CHANGED_DURING_PROBE')
        result['state'] = 'MAPPED_GGUF_METADATA_VERIFIED' if mapped else 'MODEL_FILE_NOT_MAPPED_UNKNOWN_LOAD'
        result['loaded_model_sha256'] = None  # A mapped inode is never a full-weight digest.
    except (EvidenceUnavailable, OSError, UnicodeError, ValueError, struct.error) as exc:
        result['state'] = 'UNKNOWN'
        result['reason'] = str(exc) if isinstance(exc, EvidenceUnavailable) else type(exc).__name__
        result.pop('gguf', None)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--expected-start-ticks', type=int, required=True)
    p.add_argument('--model-file', help='Optional known model shard; must independently match process maps')
    a = p.parse_args()
    result = witness(a.pid, a.expected_start_ticks, a.model_file)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['state'] == 'MAPPED_GGUF_METADATA_VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
