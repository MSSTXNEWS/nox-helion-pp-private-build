#!/usr/bin/env python3
"""Read-only adapter bytes/layout/provenance audit for NOX.

Hash the bounded adapter files, read only the 26 HF shard headers, and keep
structural matching separate from original-base identity and prior merging.
No tensor values, private experience, or raw provenance text are exported.
No checkpoint is loaded through pickle, and no model is merged or deleted.
Format references: https://github.com/safetensors/safetensors
https://huggingface.co/docs/peft/developer_guides/checkpoint
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import threading
import time

ROOT = Path('/root/nox')
BASE = ROOT / 'progress_pull_t784u/workspace-2-2/nox36/ckpt/final/merged_hf'
BASE_CONFIG_PREVIOUS_SHA = '93a4693fa9d8392fbfccd4b3c9873f4bfdcb14fdede978b123d07d19675efe99'
STATE = ROOT / 'state/owner_adapter_lineage'
DRIVE_STATE = ROOT / 'state/owner_drive_ram/latest_receipt.json'
DRIVE_MANIFEST_SHA = '73b8fa9336faabad2c2b1d197d6751d79b065158c7f0700e46155f371b74c816'
DRIVE_BRIDGE_SHA = '57893b187155b12c08b3ca0612a62397d117218302d448994a346c84f556b786'
HYBRID_OUTPUT = ROOT / 'lora/qlora_t866u/runs_owner_hybrid'
SCHEMA = 'NOX_OWNER_ADAPTER_LINEAGE_AUDIT_V1'
MAX_HEADER = 8 * 1024 ** 2
MAX_ADAPTER = 512 * 1024 ** 2
MAX_JSON = 8 * 1024 ** 2
MAX_TENSORS = 100000
MAX_FULL_HASH = 8 * 1024 ** 3
MAX_HEADER_TOTAL = 48 * 1024 ** 2
MAX_SECONDS = 100
SHA = re.compile(r'[a-f0-9]{64}\Z')
TENSOR_NAME = re.compile(r'[A-Za-z0-9_.]{1,512}\Z')
LORA = re.compile(r'(.+)\.lora_([AB])(?:\.([A-Za-z0-9_-]{1,80}))?\.weight\Z')
DTYPE_BYTES = {'BOOL': 1, 'I8': 1, 'U8': 1, 'I16': 2, 'U16': 2, 'F16': 2, 'BF16': 2,
               'I32': 4, 'U32': 4, 'F32': 4, 'I64': 8, 'U64': 8, 'F64': 8,
               'F8_E4M3': 1, 'F8_E5M2': 1, 'F8_E4M3FN': 1, 'F8_E5M2FNUZ': 1}
FLOAT_DTYPES = {'F16', 'BF16', 'F32', 'F64'}
KNOWN_REFERENCE_NAMES = {'/workspace/base36/Qwen3.6-35B-A3B', '/dev/shm/base36',
                         '/root/nox/base_nf4', 'unsloth/Qwen2.5-Coder-7B', str(BASE)}
TARGETS = ({'id': 'existing_01', 'kind': 'existing_adapter', 'path': '/root/nox/lora/cycles/c0001/adapter/adapter_model.safetensors', 'config_path': '/root/nox/lora/cycles/c0001/adapter/adapter_config.json', 'expected_bytes': 100688544}, {'id': 'existing_02', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/intellect_snapshot_step169/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/intellect_snapshot_step169/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_03', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/core_self/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/core_self/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_04', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_05', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_pref/run/checkpoint-105/ref/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_pref/run/checkpoint-105/ref/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_06', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_07', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/mix_final_pref_best_holdout/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/mix_final_pref_best_holdout/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_08', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/mix_final_pref_best_holdout/ref/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/mix_final_pref_best_holdout/ref/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_09', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_pc_t809u/lora_pc/weights/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/lora_pc/weights/adapter_config.json', 'expected_bytes': 80792880}, {'id': 'existing_10', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_pc_t809u/adapters/a100_20261112/last.prev/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/adapters/a100_20261112/last.prev/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'existing_11', 'kind': 'existing_adapter', 'path': '/root/nox/progress_pull_pc_t809u/adapters/a100_20261112/final/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/adapters/a100_20261112/final/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'checkpoint_01', 'kind': 'checkpoint_adapter', 'path': '/root/nox/progress_pull_pc_t809u/lora_pc/output/checkpoint-50/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/lora_pc/output/checkpoint-50/adapter_config.json', 'expected_bytes': 80792880}, {'id': 'checkpoint_02', 'kind': 'checkpoint_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/mix_final_sft/run/checkpoint-383/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/mix_final_sft/run/checkpoint-383/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'checkpoint_03', 'kind': 'checkpoint_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_pref/run/checkpoint-105/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_pref/run/checkpoint-105/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'checkpoint_04', 'kind': 'checkpoint_adapter', 'path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_sft/run/checkpoint-64/adapter_model.safetensors', 'config_path': '/root/nox/progress_pull_t784u/workspace-2-2/nox36/ckpt/offload_overlay_t733u/next/understanding_sft/run/checkpoint-64/adapter_config.json', 'expected_bytes': 306787336}, {'id': 'drive_core_self', 'role': 'core_self', 'kind': 'restored_drive', 'path': '/dev/shm/nox_drive/3t724u/t724u_core_self_final.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/adapters/t724u_meta/meta/ckpt/core_self/final/adapter_config.json', 'config_association': 'NAMED_BACKUP_CONFIG_CANDIDATE_NOT_CRYPTOGRAPHICALLY_BOUND', 'expected_bytes': 306787336, 'expected_sha256': 'e5e98c7e2969aaf2f2fdda38c5814a8764c0e607265c141096e5e673b648f476'}, {'id': 'drive_intellect', 'role': 'intellect', 'kind': 'restored_drive', 'path': '/dev/shm/nox_drive/3t724u/t724u_intellect_best_holdout.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/adapters/t724u_meta/meta/ckpt/intellect/best_holdout/adapter_config.json', 'config_association': 'NAMED_BACKUP_CONFIG_CANDIDATE_NOT_CRYPTOGRAPHICALLY_BOUND', 'expected_bytes': 306787336, 'expected_sha256': '9e76a6bf88bff25b0b7efdf34032c72dbd7044def371be21e540319307f846b6'}, {'id': 'drive_builder', 'role': 'builder', 'kind': 'restored_drive', 'path': '/dev/shm/nox_drive/3t724u/t724u_builder_best_holdout.safetensors', 'config_path': '/root/nox/progress_pull_pc_t809u/adapters/t724u_meta/meta/ckpt/builder/best_holdout/adapter_config.json', 'config_association': 'NAMED_BACKUP_CONFIG_CANDIDATE_NOT_CRYPTOGRAPHICALLY_BOUND', 'expected_bytes': 306787336, 'expected_sha256': '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'})
EXPECTED_SHARDS = {'model-00001-of-00026.safetensors': 3996199712, 'model-00002-of-00026.safetensors': 1284907696, 'model-00003-of-00026.safetensors': 3357898360, 'model-00004-of-00026.safetensors': 3370808712, 'model-00005-of-00026.safetensors': 3357898360, 'model-00006-of-00026.safetensors': 3959424904, 'model-00007-of-00026.safetensors': 1096788232, 'model-00008-of-00026.safetensors': 3946842008, 'model-00009-of-00026.safetensors': 1096460848, 'model-00010-of-00026.safetensors': 3946841992, 'model-00011-of-00026.safetensors': 1096460752, 'model-00012-of-00026.safetensors': 3409971080, 'model-00013-of-00026.safetensors': 1633331664, 'model-00014-of-00026.safetensors': 3422553872, 'model-00015-of-00026.safetensors': 1633659224, 'model-00016-of-00026.safetensors': 3946842136, 'model-00017-of-00026.safetensors': 1096460608, 'model-00018-of-00026.safetensors': 3946841992, 'model-00019-of-00026.safetensors': 1096460808, 'model-00020-of-00026.safetensors': 3409971072, 'model-00021-of-00026.safetensors': 1633331744, 'model-00022-of-00026.safetensors': 3370808752, 'model-00023-of-00026.safetensors': 3357898392, 'model-00024-of-00026.safetensors': 3370808752, 'model-00025-of-00026.safetensors': 3832888256, 'model-00026-of-00026.safetensors': 2231416848}
EMIT_LOCK = threading.Lock()


class AuditHold(RuntimeError):
    pass


def fail(code):
    raise AuditHold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def stop_active():
    return any(path.exists() or path.is_symlink() for path in
               [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP')]
               + [Path('/workspace/NOX_STOP')])


class Budget:
    def __init__(self, seconds=MAX_SECONDS):
        self.deadline = time.monotonic() + seconds
        self.hashed = 0
        self.headers = 0
        self.lock = threading.Lock()
        self.next_stop_check = 0
        self.stopped = False

    def check(self):
        now = time.monotonic()
        if now >= self.deadline:
            fail('HOLD_ADAPTER_AUDIT_DEADLINE')
        if now >= self.next_stop_check:
            with self.lock:
                if now >= self.next_stop_check:
                    self.stopped = self.stopped or stop_active()
                    self.next_stop_check = now + .2
        if self.stopped:
            fail('HOLD_ADAPTER_AUDIT_OWNER_STOP')

    def reserve(self, kind, count):
        self.check()
        with self.lock:
            old = getattr(self, kind)
            maximum = MAX_FULL_HASH if kind == 'hashed' else MAX_HEADER_TOTAL
            if type(count) is not int or count < 0 or old + count > maximum:
                fail('HOLD_ADAPTER_AUDIT_BYTE_BUDGET')
            setattr(self, kind, old + count)


def plain(path):
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            fail('HOLD_ADAPTER_AUDIT_SYMLINK')
    return path


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def opened(path, maximum):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= maximum:
            fail('HOLD_ADAPTER_AUDIT_FILE_SCOPE')
        yield fd, before
        after = os.fstat(fd)
        if identity(before) != identity(after) or identity(path.stat()) != identity(after):
            fail('HOLD_ADAPTER_AUDIT_FILE_CHANGED')
    finally:
        os.close(fd)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('HOLD_ADAPTER_AUDIT_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def json_value(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: fail('HOLD_ADAPTER_AUDIT_NONFINITE_JSON'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        fail('HOLD_ADAPTER_AUDIT_JSON')


def small_json(path, maximum=MAX_JSON):
    with opened(path, maximum) as (fd, info):
        raw = os.pread(fd, info.st_size + 1, 0)
        if len(raw) != info.st_size:
            fail('HOLD_ADAPTER_AUDIT_JSON_SIZE')
        value = json_value(raw)
    if not isinstance(value, dict):
        fail('HOLD_ADAPTER_AUDIT_JSON_OBJECT')
    return value, digest(raw), info


def shape_fingerprint(tensors):
    hashed = hashlib.sha256()
    for name in sorted(tensors):
        value = tensors[name]
        hashed.update(canonical([name, value['dtype'], value['shape']]) + b'\n')
    return hashed.hexdigest()


def header_fd(fd, info, budget):
    prefix = os.pread(fd, 8, 0)
    if len(prefix) != 8:
        fail('HOLD_SAFETENSORS_PREFIX')
    count = struct.unpack('<Q', prefix)[0]
    if not 2 <= count <= MAX_HEADER or 8 + count > info.st_size:
        fail('HOLD_SAFETENSORS_HEADER_LIMIT')
    budget.reserve('headers', count + 8)
    raw = os.pread(fd, count, 8)
    if len(raw) != count or not raw.startswith(b'{'):
        fail('HOLD_SAFETENSORS_HEADER_SIZE')
    document = json_value(raw)
    if not isinstance(document, dict) or not 1 <= len(document) <= MAX_TENSORS + 1:
        fail('HOLD_SAFETENSORS_HEADER_SCHEMA')
    tensors, spans = {}, []
    data_bytes = info.st_size - 8 - count
    metadata = document.get('__metadata__')
    if metadata is not None and (not isinstance(metadata, dict)
                                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in metadata.items())):
        fail('HOLD_SAFETENSORS_METADATA_SCHEMA')
    for name, value in document.items():
        budget.check()
        if name == '__metadata__':
            continue
        if not isinstance(name, str) or not TENSOR_NAME.fullmatch(name) or not isinstance(value, dict):
            fail('HOLD_SAFETENSORS_TENSOR_SCHEMA')
        if set(value) != {'dtype', 'shape', 'data_offsets'}:
            fail('HOLD_SAFETENSORS_TENSOR_FIELDS')
        shape, dtype, offsets = value['shape'], value['dtype'], value['data_offsets']
        if (not isinstance(shape, list) or len(shape) > 8
                or any(type(d) is not int or not 0 <= d <= 2 ** 31 for d in shape)
                or not isinstance(dtype, str) or dtype not in DTYPE_BYTES or not isinstance(offsets, list) or len(offsets) != 2
                or any(type(d) is not int for d in offsets)
                or not 0 <= offsets[0] <= offsets[1] <= data_bytes):
            fail('HOLD_SAFETENSORS_SHAPE_OR_OFFSET')
        elements = math.prod(shape)
        if elements > 2 ** 63 or elements * DTYPE_BYTES[dtype] != offsets[1] - offsets[0]:
            fail('HOLD_SAFETENSORS_DTYPE_BYTE_PRODUCT')
        tensors[name] = {'shape': shape, 'dtype': dtype}
        if offsets[1] > offsets[0]:
            spans.append((offsets[0], offsets[1]))
    cursor = 0
    for begin, end in sorted(spans):
        if begin != cursor:
            fail('HOLD_SAFETENSORS_OVERLAP_OR_HOLE')
        cursor = end
    if cursor != data_bytes:
        fail('HOLD_SAFETENSORS_UNINDEXED_PAYLOAD')
    if not tensors:
        fail('HOLD_SAFETENSORS_NO_TENSORS')
    summary = {'state': 'HEADER_LAYOUT_VALIDATED', 'header_bytes': count + 8,
               'header_sha256': digest(prefix + raw), 'tensor_count': len(tensors),
               'shape_dtype_sha256': shape_fingerprint(tensors),
               'dtypes': dict(sorted(Counter(v['dtype'] for v in tensors.values()).items())),
               'zero_element_tensors': sum(math.prod(v['shape']) == 0 for v in tensors.values()),
               'metadata_values_exported': False, 'numerical_finiteness_tested': False}
    return tensors, summary


def read_safetensors(path, budget, full_hash=False):
    maximum = MAX_ADAPTER if full_hash else 8 * 1024 ** 3
    with opened(path, maximum) as (fd, info):
        try:
            tensors, summary = header_fd(fd, info, budget)
        except AuditHold as exc:
            if not full_hash or str(exc) in ('HOLD_ADAPTER_AUDIT_OWNER_STOP', 'HOLD_ADAPTER_AUDIT_DEADLINE',
                                             'HOLD_ADAPTER_AUDIT_BYTE_BUDGET'):
                raise
            tensors = {}
            summary = {'state': 'HEADER_UNVERIFIED', 'reason': safe_failure(exc),
                       'metadata_values_exported': False, 'numerical_finiteness_tested': False}
        if full_hash:
            budget.reserve('hashed', info.st_size)
            hashed, offset = hashlib.sha256(), 0
            while offset < info.st_size:
                budget.check()
                block = os.pread(fd, min(4 * 1024 ** 2, info.st_size - offset), offset)
                if not block:
                    fail('HOLD_ADAPTER_AUDIT_HASH_TRUNCATED')
                hashed.update(block)
                offset += len(block)
            summary.update(full_file_sha256=hashed.hexdigest(), full_file_sha256_verified=True)
        else:
            summary['full_file_sha256_verified'] = False
        summary.update(bytes=info.st_size, stat_identity=list(identity(info)), hardlinks=info.st_nlink,
                       allocated_bytes=info.st_blocks * 512, tensor_values_exported=False)
    return tensors, summary


def config_projection(config):
    result = {}
    for key in ('model_type', 'peft_type', 'task_type', 'torch_dtype', 'dtype', 'bias'):
        value = config.get(key)
        if isinstance(value, str) and re.fullmatch('[A-Za-z0-9_.-]{1,80}', value):
            result[key] = value
    for key in ('r', 'lora_alpha', 'lora_dropout', 'hidden_size', 'intermediate_size', 'num_hidden_layers',
                'num_attention_heads', 'num_key_value_heads', 'vocab_size', 'num_experts',
                'num_local_experts', 'num_experts_per_tok', 'head_dim'):
        value = config.get(key)
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 2 ** 40:
            result[key] = value
    for key in ('tie_word_embeddings', 'fan_in_fan_out', 'inference_mode', 'use_dora', 'use_rslora'):
        if type(config.get(key)) is bool:
            result[key] = config[key]
    architectures = config.get('architectures')
    if isinstance(architectures, list) and len(architectures) <= 8:
        result['architectures'] = [v for v in architectures if isinstance(v, str) and re.fullmatch('[A-Za-z0-9_]{1,100}', v)]
    for key in ('target_modules', 'modules_to_save', 'target_parameters', 'rank_pattern', 'alpha_pattern'):
        value = config.get(key)
        if value is not None:
            result[key + '_entries'] = len(value) if isinstance(value, (dict, list)) else None
            result[key + '_sha256'] = digest(canonical(value))
    for key in ('base_model_name_or_path', '_name_or_path'):
        value = config.get(key)
        if isinstance(value, str):
            result[key] = value if value in KNOWN_REFERENCE_NAMES else {'unrecognized_value_sha256': digest(value.encode())}
    for key in ('revision', '_commit_hash'):
        value = config.get(key)
        if isinstance(value, str):
            result[key] = {'immutable_commit': bool(re.fullmatch('[a-f0-9]{40}', value)),
                           'value': value if re.fullmatch('[a-f0-9]{40}', value) else None,
                           'value_sha256': digest(value.encode())}
    for key in ('text_config', 'vision_config'):
        if isinstance(config.get(key), dict):
            child = {k: v for k, v in config[key].items() if k not in ('text_config', 'vision_config')}
            result[key] = config_projection(child)
    return result


def read_config(path):
    try:
        value, sha, info = small_json(path, 512 * 1024)
        return value, {'path': str(path), 'state': 'CONFIG_OBSERVED', 'sha256': sha,
                       'bytes': info.st_size, 'fields': config_projection(value)}
    except FileNotFoundError:
        return None, {'path': str(path), 'state': 'CONFIG_MISSING'}
    except (OSError, AuditHold, ValueError, TypeError):
        return None, {'path': str(path), 'state': 'CONFIG_UNVERIFIED'}


def inspect_base(budget):
    config, config_summary = read_config(BASE / 'config.json')
    index, index_sha, _ = small_json(BASE / 'model.safetensors.index.json')
    weight_map = index.get('weight_map')
    if not isinstance(weight_map, dict) or not 1 <= len(weight_map) <= MAX_TENSORS:
        fail('HOLD_BASE_WEIGHT_INDEX')
    if any(not isinstance(name, str) or not TENSOR_NAME.fullmatch(name)
           or not isinstance(file, str) or file not in EXPECTED_SHARDS for name, file in weight_map.items()):
        fail('HOLD_BASE_WEIGHT_INDEX_SCOPE')
    files = []
    for index_entry, path in enumerate(plain(BASE).iterdir()):
        budget.check()
        if index_entry >= 1000:
            fail('HOLD_BASE_DIRECTORY_BUDGET')
        if path.name.endswith('.safetensors'):
            files.append(path.name)
    files.sort()
    if files != sorted(EXPECTED_SHARDS) or set(weight_map.values()) != set(EXPECTED_SHARDS):
        fail('HOLD_BASE_SHARD_SET')
    tensors, shards, total_bytes = {}, [], 0
    for filename in sorted(EXPECTED_SHARDS):
        value, summary = read_safetensors(BASE / filename, budget)
        if any(name in tensors for name in value):
            fail('HOLD_BASE_DUPLICATE_TENSOR_NAME')
        expected_names = {name for name, file in weight_map.items() if file == filename}
        if set(value) != expected_names:
            fail('HOLD_BASE_INDEX_HEADER_MISMATCH')
        if len(tensors) + len(value) > MAX_TENSORS:
            fail('HOLD_BASE_TENSOR_BUDGET')
        tensors.update(value)
        total_bytes += summary['bytes']
        shards.append({'filename': filename, **summary,
                       'bytes_match_previous_inventory': summary['bytes'] == EXPECTED_SHARDS[filename]})
    result = {'path': str(BASE), 'state': 'BASE_LAYOUT_AND_INDEX_VALIDATED', 'config': config_summary,
              'config_matches_previous_inventory': config_summary.get('sha256') == BASE_CONFIG_PREVIOUS_SHA,
              'index_sha256': index_sha, 'shard_count': len(shards), 'file_bytes': total_bytes,
              'tensor_count': len(tensors), 'shape_dtype_sha256': shape_fingerprint(tensors), 'shards': shards,
              'shard_payloads_read': False, 'base_full_weight_digest_verified': False,
              'exact_original_base_revision_verified': False,
              'previous_adapter_merge_inclusion': 'UNKNOWN_REQUIRES_BOUND_MERGE_LINEAGE_AND_OUTPUT_BYTES'}
    return {'public': result, 'tensors': tensors, 'config': config}


def inspect_adapter(target, budget):
    path = Path(target['path'])
    result = {'id': target['id'], 'kind': target['kind'], 'path': str(path),
              'config_association': target.get('config_association', 'SAME_PACKAGE_DIRECTORY'),
              'merge_performed': False}
    config, config_summary = read_config(Path(target['config_path']))
    result['config'] = config_summary
    tensors, header = read_safetensors(path, budget, full_hash=True)
    result.update(state='ADAPTER_FULL_FILE_SHA_VERIFIED', file=header)
    result['storage_class'] = ('ROOT_VOLUME' if path.is_relative_to(ROOT) and header['stat_identity'][0] == ROOT.stat().st_dev
                               else 'RAM_RESTORE' if path.is_relative_to(Path('/dev/shm/nox_drive')) else 'UNKNOWN_VOLUME')
    result['bytes_match_previous_inventory'] = target.get('expected_bytes') == header['bytes']
    if target.get('expected_sha256'):
        result['matches_approved_drive_sha256'] = header['full_file_sha256'] == target['expected_sha256']
        if result['matches_approved_drive_sha256'] is not True:
            result['state'] = 'HOLD_RESTORED_FILE_EXPECTED_SHA_MISMATCH'
    trainer_path = path.parent / 'trainer_state.json'
    if trainer_path.exists():
        try:
            trainer, trainer_sha, _ = small_json(trainer_path, 3 * MAX_JSON)
            step = trainer.get('global_step')
            result['trainer_state'] = {'sha256': trainer_sha, 'global_step': step if type(step) is int else None,
                                       'positive_step_recorded': type(step) is int and step > 0,
                                       'proof_scope': 'RECORDED_STEP_ONLY_OPTIMIZER_NOT_REHASHED'}
        except (OSError, AuditHold, ValueError, TypeError):
            result['trainer_state'] = {'state': 'UNKNOWN_TRAINER_STATE_NOT_PARSED'}
    return {'public': result, 'tensors': tensors, 'config': config}


def structure(adapter_tensors, base_tensors, config, base_complete=True):
    """Validate only the explicit two-dimensional PEFT linear subset."""
    pairs, unsupported, collisions = {}, [], []
    for name, value in adapter_tensors.items():
        match = LORA.fullmatch(name)
        if not match:
            unsupported.append(name)
            continue
        module, side, adapter_name = match.groups()
        if module.startswith('base_model.model.'):
            module = module[len('base_model.model.'):]
        key = module + '.weight'
        entry = pairs.setdefault(key, {})
        if side in entry:
            collisions.append(key)
        entry[side] = (value, adapter_name)
    matched, missing, incompatible, unsupported_pairs = [], [], [], []
    orientation_required = bool(config and config.get('fan_in_fan_out') is True)
    rank_patterns = bool(config and config.get('rank_pattern'))
    for key, pair in pairs.items():
        if set(pair) != {'A', 'B'} or pair['A'][1] != pair['B'][1]:
            unsupported_pairs.append({'target': key, 'reason': 'PAIR_OR_ADAPTER_NAME_MISMATCH'})
            continue
        a, b = pair['A'][0], pair['B'][0]
        if len(a['shape']) != 2 or len(b['shape']) != 2 or a['dtype'] not in FLOAT_DTYPES or b['dtype'] not in FLOAT_DTYPES:
            unsupported_pairs.append({'target': key, 'reason': 'NOT_SUPPORTED_2D_FLOAT_LINEAR_PAIR'})
            continue
        if not a['shape'][0] or a['shape'][0] != b['shape'][1] or not a['shape'][1] or not b['shape'][0]:
            incompatible.append({'target': key, 'reason': 'LORA_PAIR_RANK_OR_EMPTY_DIMENSION'})
            continue
        if config and type(config.get('r')) is int and not rank_patterns and config['r'] != a['shape'][0]:
            incompatible.append({'target': key, 'reason': 'RECORDED_GLOBAL_RANK_DIFFERS'})
            continue
        base = base_tensors.get(key)
        if base is None:
            missing.append(key)
            continue
        expected = [b['shape'][0], a['shape'][1]]
        if orientation_required:
            expected.reverse()
        if base['dtype'] not in FLOAT_DTYPES:
            unsupported_pairs.append({'target': key, 'reason': 'BASE_DTYPE_REQUIRES_LOADER_SPECIFIC_HANDLING'})
        elif base['shape'] != expected:
            incompatible.append({'target': key, 'reason': 'BASE_WEIGHT_SHAPE_DIFFERS',
                                 'adapter_product_shape': expected, 'base_shape': base['shape']})
        else:
            matched.append(key)
    semantics = []
    if config is None:
        semantics.append('ADAPTER_CONFIG_MISSING')
    else:
        if config.get('peft_type') != 'LORA':
            semantics.append('PEFT_TYPE_NOT_CONFIRMED_LORA')
        for key in ('rank_pattern', 'alpha_pattern', 'modules_to_save', 'target_parameters', 'trainable_token_indices'):
            if config.get(key):
                semantics.append(key.upper() + '_REQUIRES_LOADER_VALIDATION')
        for key in ('use_dora', 'use_rslora'):
            if config.get(key):
                semantics.append(key.upper() + '_SCALING_OR_BASE_SEMANTICS_NOT_VERIFIED')
        if config.get('bias', 'none') != 'none':
            semantics.append('BIAS_UPDATES_REQUIRE_EXPLICIT_HANDLING')
        init = config.get('init_lora_weights', True)
        if isinstance(init, str) and init not in ('gaussian',):
            semantics.append('INITIALIZATION_MAY_REQUIRE_ALTERED_BASE_LINEAGE')
    if orientation_required:
        semantics.append('FAN_IN_FAN_OUT_REQUIRES_BASE_MODULE_ORIENTATION_EVIDENCE')
    if not base_complete:
        status = 'UNKNOWN_BASE_LAYOUT_NOT_COMPLETE'
    elif collisions or unsupported or unsupported_pairs or not pairs:
        status = 'UNKNOWN_UNSUPPORTED_OR_AMBIGUOUS_ADAPTER_LAYOUT'
    elif incompatible:
        status = 'INCOMPATIBLE_OBSERVED_LINEAR_DIMENSIONS'
    elif missing:
        status = 'UNKNOWN_TARGET_NAMES_NOT_FOUND_NO_GUESSED_RENAMING'
    elif orientation_required:
        status = 'TRANSPOSED_DIMENSIONS_MATCH_ORIENTATION_UNVERIFIED'
    else:
        status = 'SUPPORTED_LINEAR_DIMENSIONS_MATCH'
    return {'state': status, 'pairs': len(pairs), 'exact_name_and_dimension_pairs': len(matched),
            'missing_target_count': len(missing), 'incompatible_pair_count': len(incompatible),
            'unsupported_tensor_count': len(unsupported), 'unsupported_pair_count': len(unsupported_pairs),
            'normalization_collision_count': len(collisions), 'missing_target_examples': missing[:8],
            'incompatible_examples': incompatible[:8], 'unsupported_examples': unsupported[:8],
            'unsupported_pair_examples': unsupported_pairs[:8], 'config_semantics_not_verified': semantics,
            'original_base_identity_proved': False, 'previous_merge_excluded': False,
            'numeric_delta_or_finiteness_tested': False, 'automatic_merge_allowed': False}


def origin_assessment(adapter, base):
    a, b = adapter.get('config') or {}, base.get('config') or {}
    name_a = a.get('base_model_name_or_path')
    name_b = b.get('_name_or_path')
    revision_a, revision_b = a.get('revision'), b.get('_commit_hash')
    revision_match = bool(isinstance(revision_a, str) and re.fullmatch('[a-f0-9]{40}', revision_a)
                          and revision_a == revision_b)
    return {'recorded_base_reference_equal': bool(isinstance(name_a, str) and name_a and name_a == name_b),
            'recorded_immutable_revision_equal': revision_match,
            'base_reference_is_content_proof': False, 'exact_base_weights': 'UNKNOWN_NOT_HASHED',
            'prior_merge_inclusion': 'UNKNOWN_NOT_EXCLUDED',
            'reapply_gate': 'HOLD_ORIGIN_AND_PREVIOUS_MERGE_UNVERIFIED'}


def provenance_candidates(targets):
    roots = {BASE, BASE.parent, BASE.parent.parent, BASE.parent.parent.parent, HYBRID_OUTPUT}
    for target in targets:
        roots.update((Path(target['path']).parent, Path(target['path']).parent.parent,
                      Path(target['config_path']).parent))
    paths, visited, entries = [], set(), 0
    for root in sorted(roots):
        if root in visited or not root.exists():
            continue
        plain(root)
        visited.add(root)
        for path in root.iterdir():
            entries += 1
            if entries > 3000:
                return paths, True
            if (path.suffix.lower() == '.json' and re.search('(merge|export|provenance|manifest|lineage|receipt)', path.name, re.I)
                    and path.name not in ('adapter_config.json', 'model.safetensors.index.json')):
                paths.append(path)
                if len(paths) >= 64:
                    return paths, True
    return sorted(set(paths)), False


def inspect_provenance(targets, adapter_hashes, budget):
    paths, truncated = provenance_candidates(targets)
    rows, total = [], 0
    for path in paths:
        budget.check()
        try:
            obj, sha, info = small_json(path, 512 * 1024)
            total += info.st_size
            if total > 8 * 1024 ** 2:
                truncated = True
                break
            raw = canonical(obj)
            mentions = sorted(set(re.findall(rb'[a-f0-9]{64}', raw)) & {value.encode() for value in adapter_hashes})
            applied, output_hashes = set(), 0
            stack = [(obj, False)]
            walked = 0
            while stack:
                node, applied_context = stack.pop()
                walked += 1
                if walked > 20000:
                    break
                if isinstance(node, dict):
                    for key, value in node.items():
                        context = applied_context or key in ('merged_adapters', 'applied_adapters', 'merged_adapter_sha256s')
                        if context and isinstance(value, str) and value in adapter_hashes:
                            applied.add(value)
                        if key in ('output_shards_sha256', 'shard_sha256', 'files_sha256') and isinstance(value, dict):
                            output_hashes += sum(name in EXPECTED_SHARDS and isinstance(h, str) and bool(SHA.fullmatch(h))
                                                 for name, h in value.items())
                        if isinstance(value, (dict, list)):
                            stack.append((value, context))
                elif isinstance(node, list):
                    for value in node:
                        if applied_context and isinstance(value, str) and value in adapter_hashes:
                            applied.add(value)
                        if isinstance(value, (dict, list)):
                            stack.append((value, applied_context))
            rows.append({**provenance_path(path), 'bytes': info.st_size, 'sha256': sha,
                         'observed_adapter_digest_references': [value.decode() for value in mentions],
                         'declared_applied_adapter_digests': sorted(applied),
                         'declared_output_shard_digest_count': output_hashes,
                         'state': 'UNVERIFIED_RECORD_REFERENCES_ONLY', 'walk_truncated': bool(stack),
                         'raw_text_exported': False, 'output_tensor_digests_checked': False})
        except (OSError, AuditHold, ValueError, TypeError):
            rows.append({**provenance_path(path), 'state': 'UNKNOWN_PROVENANCE_UNREADABLE', 'raw_text_exported': False})
    return {'records': rows, 'coverage_truncated': truncated, 'bytes_read': total,
            'prior_merge_exclusion_proved': False,
            'reason': 'SOURCE_NAMES_AND_RECORDS_DO_NOT_PROVE_CURRENT_HF_WEIGHT_CONTENT_OR_COMPLETE_MERGE_HISTORY'}


def provenance_path(path):
    # Unknown record names can themselves contain private text. Fixed package
    # filenames remain useful publicly; every other name is represented by SHA.
    if re.fullmatch(r'(?:owner_lineage|owner_last_result|owner_receipt_step_[0-9]{1,5}|merge_manifest|merge_receipt|export_manifest|export_receipt|provenance|manifest|nox_provenance)\.json', path.name):
        return {'path': str(path)}
    return {'parent_path': str(path.parent), 'filename_sha256': digest(path.name.encode()), 'filename_redacted': True}


def drive_proof(adapters):
    expected = {target['id']: target for target in TARGETS if target['kind'] == 'restored_drive'}
    verified = {value['public']['id']: value['public'] for value in adapters
                if value['public']['kind'] == 'restored_drive' and value['public'].get('matches_approved_drive_sha256') is True}
    try:
        with opened(ROOT / 'scripts/owner_drive_ram_bridge.py', 65536) as (fd, implementation_info):
            implementation_sha = digest(os.pread(fd, implementation_info.st_size, 0))
        receipt, sha, receipt_info = small_json(DRIVE_STATE, 128 * 1024)
        assets = receipt.get('assets')
        valid = (implementation_sha == DRIVE_BRIDGE_SHA and receipt.get('schema') == 'NOX_DRIVE_RAM_RECEIPT_V1'
                 and receipt.get('state') == 'RAM_FILES_SHA_VERIFIED_NOT_MERGED'
                 and receipt.get('manifest_sha256') == DRIVE_MANIFEST_SHA
                 and receipt.get('private_urls_exported') is False and receipt.get('weights_merged') is False
                 and isinstance(assets, list) and len(assets) == 3
                 and receipt_info.st_uid == os.geteuid() and not receipt_info.st_mode & 0o077
                 and isinstance(receipt.get('request'), str) and bool(re.fullmatch('[0-9]{1,24}', receipt['request']))
                 and isinstance(receipt.get('source_sha'), str) and bool(re.fullmatch('[a-f0-9]{40}', receipt['source_sha']))
                 and isinstance(receipt.get('envelope_sha256'), str) and bool(SHA.fullmatch(receipt['envelope_sha256']))
                 and type(receipt.get('finished_at')) in (int, float)
                 and math.isfinite(receipt['finished_at']) and 0 <= time.time() - receipt['finished_at'] <= 3600)
        rows = {row.get('role'): row for row in assets if isinstance(row, dict)} if isinstance(assets, list) else {}
        for key, target in expected.items():
            row = rows.get(target['role'], {})
            valid = valid and (key in verified and row.get('filename') == Path(target['path']).name
                               and row.get('bytes') == target['expected_bytes']
                               and row.get('sha256') == target['expected_sha256'] and row.get('verified') is True)
        return {'state': 'FRESH_CONNECTOR_READBACK_AND_RAM_SHA_VERIFIED' if valid else 'UNKNOWN_RECEIPT_OR_RAM_PROOF',
                'receipt_sha256': sha, 'verified_at': receipt.get('finished_at') if valid else None,
                'verified_adapter_sha256s': sorted(target['expected_sha256'] for target in expected.values()) if valid else [],
                'bridge_implementation_sha_verified': implementation_sha == DRIVE_BRIDGE_SHA,
                'direct_drive_api_recheck_performed': False, 'ram_is_durable_backup': False}
    except (OSError, AuditHold, ValueError, TypeError):
        return {'state': 'UNKNOWN_NO_VERIFIED_DRIVE_READBACK', 'verified_adapter_sha256s': [],
                'direct_drive_api_recheck_performed': False, 'ram_is_durable_backup': False}


def duplicate_groups(adapters, drive):
    groups = defaultdict(list)
    for value in adapters:
        row = value['public']
        if row.get('file', {}).get('full_file_sha256_verified') is True:
            groups[(row['file']['full_file_sha256'], row['file']['bytes'])].append(row)
    result = []
    for (sha, size), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        ssd = [row for row in rows if row.get('storage_class') == 'ROOT_VOLUME']
        protected = [row for row in ssd if any(part.startswith('checkpoint-') for part in Path(row['path']).parts)]
        eligible = [row for row in ssd if row not in protected and row['file']['hardlinks'] == 1]
        inodes = {(row['file']['stat_identity'][0], row['file']['stat_identity'][1]) for row in ssd}
        confirmed_drive = sha in drive['verified_adapter_sha256s']
        # A proposal always retains one SSD inode, all configs/provenance, and
        # every checkpoint. It is not an eviction receipt or a deletion action.
        # A checkpoint may later be pruned by a trainer, so it never replaces
        # the required retained standalone SSD copy in this proposal.
        proposal = max(0, len(eligible) - 1)
        result.append({'sha256': sha, 'bytes_per_file': size, 'paths': [row['path'] for row in rows],
                       'distinct_ssd_inodes': len(inodes), 'checkpoint_paths_protected': [row['path'] for row in protected],
                       'fresh_drive_readback_verified': confirmed_drive,
                       'ssd_dedup_review_candidate': bool(confirmed_drive and proposal > 0 and len(inodes) > 1),
                       'maximum_reviewable_duplicate_bytes': proposal * size if confirmed_drive else 0,
                       'retained_ssd_copy_required': True, 'active_use_and_inode_recheck_required': True,
                       'all_configs_and_provenance_must_be_preserved': True,
                       'original_weight_paths_must_remain_resolvable': True,
                       'deletion_authorized_by_this_audit': False})
    return result


def safe_failure(exc):
    code = str(exc)
    return code if re.fullmatch('HOLD_[A-Z0-9_]+', code) else 'UNKNOWN_READ_OR_FORMAT'


def audit():
    budget = Budget()
    adapters, failures, base = [], [], None
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix='nox-adapter-audit') as pool:
        futures = {pool.submit(inspect_base, budget): ('base', None)}
        for target in TARGETS:
            futures[pool.submit(inspect_adapter, target, budget)] = ('adapter', target)
        for future in as_completed(futures):
            kind, target = futures[future]
            try:
                value = future.result()
                if kind == 'base':
                    base = value
                else:
                    adapters.append(value)
            except Exception as exc:
                failures.append({'kind': kind, 'path': str(BASE) if target is None else target['path'],
                                 'id': None if target is None else target['id'], 'state': safe_failure(exc)})
    if base is None:
        base = {'public': {'path': str(BASE), 'state': 'UNKNOWN_BASE_LAYOUT',
                           'base_full_weight_digest_verified': False}, 'tensors': {}, 'config': None}
    for adapter in adapters:
        adapter['public']['structure'] = structure(adapter['tensors'], base['tensors'], adapter['config'],
                                                   base['public']['state'] == 'BASE_LAYOUT_AND_INDEX_VALIDATED')
        adapter['public']['origin'] = origin_assessment(adapter, base)
    hashes = {adapter['public']['file']['full_file_sha256'] for adapter in adapters}
    try:
        provenance = inspect_provenance(TARGETS, hashes, budget)
    except (OSError, AuditHold, ValueError, TypeError) as exc:
        provenance = {'state': safe_failure(exc), 'coverage_truncated': True, 'records': [],
                      'prior_merge_exclusion_proved': False, 'raw_text_exported': False}
    drive = drive_proof(adapters)
    groups = duplicate_groups(adapters, drive)
    public = sorted((value['public'] for value in adapters), key=lambda row: row['id'])
    return {'schema': SCHEMA, 'state': 'READ_ONLY_AUDIT_COMPLETE', 'base': base['public'], 'adapters': public,
            'unverified_targets': failures, 'provenance': provenance, 'drive_readback': drive,
            'exact_byte_duplicate_groups': groups,
            'counts': {'requested_adapter_paths': len(TARGETS), 'full_sha_verified_adapter_files': len(adapters),
                       'restored_drive_files_verified': sum(row.get('matches_approved_drive_sha256') is True for row in public),
                       'unique_adapter_file_sha256s': len(hashes), 'duplicate_groups': len(groups),
                       'base_shards_header_verified': base['public'].get('shard_count', 0)},
            'bytes_read_for_adapter_hashes': budget.hashed, 'header_bytes_read': budget.headers,
            'maximum_parallel_read_jobs': 6, 'source_scope': 'FIXED_PATHS_FROM_PREVIOUS_VERIFIED_INVENTORY_PLUS_APPROVED_DRIVE_RESTORE',
            'different_file_hash_does_not_prove_numerical_weight_difference': True,
            'overall_merge_gate': 'HOLD_ORIGINAL_BASE_AND_PREVIOUS_MERGE_INCLUSION_UNVERIFIED',
            'merged_hf_may_already_include_t724u': True, 'tensor_values_exported': False,
            'weight_merges': 0, 'weight_deletions': 0, 'runtime_model_changes': 0, 'native_files_written': 0}


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_OWNER_CONTEXT')
    started = time.time()
    result = audit()
    result.update(request=request, source_sha=source, started_at=started, finished_at=time.time())
    for name in ('base', 'adapters', 'unverified_targets', 'provenance', 'drive_readback', 'exact_byte_duplicate_groups'):
        rows = result[name] if isinstance(result[name], list) else [result[name]]
        for row in rows:
            print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'adapter_lineage_' + name, 'data': row}, separators=(',', ':')), flush=True)
    summary = {key: value for key, value in result.items() if key not in (
        'base', 'adapters', 'unverified_targets', 'provenance', 'drive_readback', 'exact_byte_duplicate_groups')}
    summary['audit_sha256'] = digest(canonical(result))
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'adapter_lineage_summary', 'data': summary}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'adapter_lineage_hold', 'data': {'state': safe_failure(exc)}}), flush=True)
        raise SystemExit(2)
