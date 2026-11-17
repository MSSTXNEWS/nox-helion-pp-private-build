#!/usr/bin/env python3
"""Bounded read-only GGUF v2/v3 metadata inspection. Never reads tensor data."""
import argparse
import json
import math
import os
import re
import stat
import struct

PRIMARY = '/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf'
MAX_METADATA = 64 * 1024 * 1024
MAX_ITEMS = 1_000_000
SCALARS = {0: ('B', 1), 1: ('b', 1), 2: ('H', 2), 3: ('h', 2),
           4: ('I', 4), 5: ('i', 4), 6: ('f', 4), 7: ('?', 1),
           10: ('Q', 8), 11: ('q', 8), 12: ('d', 8)}
GENERAL = {'general.architecture', 'general.name', 'general.file_type', 'general.quantization_version'}
MODEL_FIELDS = re.compile(r'^[a-zA-Z0-9_-]+\.(context_length|block_count|embedding_length|attention\.(head_count|head_count_kv|key_length|value_length|sliding_window)|rope\.(dimension_count|freq_base|scaling\.[a-zA-Z0-9_]+))$')


class InvalidGGUF(ValueError):
    pass


def inspect_gguf(path=PRIMARY, max_metadata_bytes=MAX_METADATA):
    if not 24 <= max_metadata_bytes <= MAX_METADATA:
        raise InvalidGGUF('metadata budget must be between 24 bytes and 64 MiB')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb', buffering=0) as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise InvalidGGUF('input must be a regular file')
        read_bytes = skipped_bytes = 0

        def bound(n):
            if n < 0 or file.tell() + n > min(before.st_size, max_metadata_bytes):
                raise InvalidGGUF('truncated metadata or 64 MiB metadata budget exceeded')

        def read(n):
            nonlocal read_bytes
            bound(n)
            data = file.read(n)
            read_bytes += len(data)
            if len(data) != n:
                raise InvalidGGUF('truncated metadata')
            return data

        def skip(n):
            nonlocal skipped_bytes
            bound(n)
            file.seek(n, os.SEEK_CUR)
            skipped_bytes += n

        def u32():
            return struct.unpack('<I', read(4))[0]

        def u64():
            return struct.unpack('<Q', read(8))[0]

        def string(capture=False):
            size = u64()
            if capture:
                if size > 4096:
                    raise InvalidGGUF('key or selected scalar string exceeds 4096 bytes')
                try:
                    return read(size).decode('utf-8')
                except UnicodeDecodeError as exc:
                    raise InvalidGGUF('invalid UTF-8 metadata') from exc
            skip(size)

        magic = read(4)
        version = u32()
        if magic != b'GGUF' or version not in (2, 3):
            raise InvalidGGUF('only little-endian GGUF v2/v3 supported')
        tensor_count, count = u64(), u64()
        if count > 65536:
            raise InvalidGGUF('metadata entry count exceeds bound')
        selected = {}
        array_items = 0
        for _ in range(count):
            key, kind = string(True), u32()
            capture = key in GENERAL or MODEL_FIELDS.fullmatch(key) is not None
            if capture and key in selected:
                raise InvalidGGUF('duplicate selected metadata key')
            if kind in SCALARS:
                fmt, size = SCALARS[kind]
                value = struct.unpack('<' + fmt, read(size))[0]
                if capture:
                    if isinstance(value, float) and not math.isfinite(value):
                        raise InvalidGGUF('non-finite selected scalar')
                    selected[key] = value
            elif kind == 8:
                value = string(capture)
                if capture:
                    selected[key] = value
            elif kind == 9:
                item_type, length = u32(), u64()
                array_items += length
                if array_items > MAX_ITEMS:
                    raise InvalidGGUF('array item budget exceeded')
                if item_type in SCALARS:
                    skip(length * SCALARS[item_type][1])
                elif item_type == 8:
                    for _ in range(length):
                        string(False)
                else:
                    raise InvalidGGUF('unknown/nested array type')
                if capture:
                    selected[key] = {'array_skipped': True, 'items': length, 'gguf_item_type': item_type}
            else:
                raise InvalidGGUF('unknown GGUF value type')
        after = os.fstat(file.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise InvalidGGUF('file changed during metadata inspection')
        architecture = selected.get('general.architecture')
        declared = selected.get(str(architecture) + '.context_length') if isinstance(architecture, str) else None
        return {'schema': 'NOX_GGUF_METADATA_PROBE_V1', 'status': 'METADATA_READ',
                'path': os.fspath(path), 'gguf_version': version, 'byte_order': 'little',
                'file_bytes': before.st_size, 'tensor_count_declared': tensor_count,
                'metadata_entries_declared': count, 'metadata_end_offset': file.tell(),
                'bytes_read': read_bytes, 'bytes_seek_skipped': skipped_bytes,
                'metadata_budget_bytes': max_metadata_bytes, 'metadata': selected,
                'model_context_declared': declared,
                'runtime_configured_total_context': None, 'runtime_per_sequence_context': None,
                'context_semantics': 'GGUF metadata only; allocation, trained support and effective quality require separate evidence',
                'tensor_data_read': False, 'weights_sha256_computed': False,
                'other_shards_inspected': False, 'native_context_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', default=PRIMARY)
    args = parser.parse_args()
    try:
        result = inspect_gguf(args.path)
    except (OSError, ValueError, struct.error) as exc:
        print('NOX_GGUF_METADATA=' + json.dumps({'status': 'HOLD', 'reason': str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
    print('NOX_GGUF_METADATA=' + json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
