#!/usr/bin/env python3
"""Prepare a pinned CP55/best input set for a future isolated EVAL_ONLY run.

Read-only: stream file hashes, never unpickle, import training modules, evaluate,
start/stop services, acquire/create a writer lease, or change any checkpoint,
guard, pointer, seal or memfd. The output is an input manifest, not admission.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/root/nox')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CORPUS = ROOT / 'state/qwen_corpus/6907283384'
CP55 = 'checkpoint-u00000055-a00000055-g01794833901774705882'
POINTER_SHA = '192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0'
MANIFEST_SHA = '458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65'
GUARD_SHA = 'fe2dc1c27c8fe5f71ee157190dccdcf91a5487edd4d3dc73168d98b062ec1b96'
LINEAGE_SHA = '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190'
EXPECTED_BEST_LOSS = 1.2216252349317074
SEALED_CONTROLLER_SHA = 'c8e6adccf85b9dd089486cdbcc192261d34390cba9fb68231b4966e82d7024bb'
OBSERVED_CONTROLLER_SHA = '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21'
SOURCE_PINS = {
    'qwen_student_training_entry_revision.py': '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03',
    'owner_qwen_execution_revision.py': 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14',
    'owner_qwen_training_guard.py': 'd5217f5bdfe21418d6210a18faac8eef422e49009d8abbcd3e71a06988a8b06b',
    'owner_qwen_training_contract.py': '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
}
SHA = re.compile(r'[a-f0-9]{64}')
NAME = re.compile(r'checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}')
REQUIRED = frozenset(('adapter_model.safetensors', 'adapter_config.json', 'optimizer.pt',
                      'scheduler.pt', 'scaler.pt', 'rng_state.pt', 'python_rng.json',
                      'student_state.json', 'lineage.json'))
ALLOWED = REQUIRED | {'README.md'}
GIB = 1024 ** 3


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def integer(value, low=0, high=1000000):
    return type(value) is int and low <= value <= high


def loss(value):
    return type(value) in (int, float) and 0 <= value <= 1000000 and math.isfinite(value)


class Reader:
    def __init__(self):
        self.deadline = time.monotonic() + 45.0
        self.total = 0

    def check(self):
        require(time.monotonic() < self.deadline, 'HOLD_PREPARE_READ_DEADLINE')

    def read(self, path, limit, *, materialize=False, expected=None):
        self.check()
        path = Path(path)
        require(path.is_absolute() and '..' not in path.parts, 'HOLD_PREPARE_PATH_SCOPE')
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        parent = os.open('/', flags | os.O_DIRECTORY)
        fd = None
        try:
            for part in path.parts[1:-1]:
                child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
                os.close(parent); parent = child
            fd = os.open(path.name, flags | os.O_NONBLOCK, dir_fd=parent)
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit,
                    'HOLD_PREPARE_FILE_BOUND')
            require(self.total + before.st_size <= 4 * GIB, 'HOLD_PREPARE_TOTAL_READ_BOUND')
            require(not materialize or limit <= 2 * 1024 ** 2, 'HOLD_PREPARE_METADATA_BOUND')
            hasher = hashlib.sha256(); chunks = []; remaining = before.st_size
            while remaining:
                self.check()
                block = os.read(fd, min(1024 ** 2, remaining))
                require(bool(block), 'HOLD_PREPARE_FILE_SHRANK')
                hasher.update(block); remaining -= len(block); self.total += len(block)
                if materialize:
                    chunks.append(block)
            require(not os.read(fd, 1), 'HOLD_PREPARE_FILE_GREW')
            after = os.fstat(fd)
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                require(getattr(before, key) == getattr(after, key) == getattr(named, key),
                        'HOLD_PREPARE_FILE_CHANGED')
            pin = hasher.hexdigest()
            require(expected is None or type(expected) is str and SHA.fullmatch(expected)
                    and pin == expected, 'HOLD_PREPARE_FILE_SHA')
            return {'sha256': pin, 'bytes': before.st_size}, b''.join(chunks) if materialize else None
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    def document(self, path, expected=None, limit=1024 ** 2):
        meta, raw = self.read(path, limit, materialize=True, expected=expected)
        def pairs(items):
            value = {}
            for key, item in items:
                require(key not in value, 'HOLD_PREPARE_DUPLICATE_JSON_KEY')
                value[key] = item
            return value
        def nonfinite(_):
            raise Hold('HOLD_PREPARE_NONFINITE_JSON')
        def finite(text):
            value = float(text)
            require(math.isfinite(value), 'HOLD_PREPARE_NONFINITE_JSON')
            return value
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite)
        require(isinstance(value, dict), 'HOLD_PREPARE_METADATA_OBJECT')
        return value, meta


def checkpoint(reader, row):
    name = row.get('directory')
    require(type(name) is str and NAME.fullmatch(name), 'HOLD_PREPARE_CHECKPOINT_NAME')
    require(type(row.get('manifest_sha256')) is str and SHA.fullmatch(row['manifest_sha256'])
            and row.get('evaluated_at_current_step') is True,
            'HOLD_PREPARE_CHECKPOINT_MANIFEST_PIN')
    path = OUTPUT / name
    manifest, manifest_meta = reader.document(path / 'checkpoint_manifest.json', row['manifest_sha256'])
    require(manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1'
            and manifest.get('directory') == name and manifest.get('lineage_sha256') == LINEAGE_SHA,
            'HOLD_PREPARE_CHECKPOINT_LINEAGE')
    counters = ('successful_total', 'attempted_total', 'holdout_evaluated_successful_total')
    require(all(integer(manifest.get(key)) for key in counters)
            and manifest['successful_total'] == manifest['holdout_evaluated_successful_total']
            and manifest['attempted_total'] >= manifest['successful_total']
            and manifest['successful_total'] == row.get('successful_total')
            and manifest['attempted_total'] == row.get('attempted_total')
            and loss(manifest.get('holdout_loss')) and manifest['holdout_loss'] == row.get('holdout_loss'),
            'HOLD_PREPARE_EVALUATED_COUNTERS')
    pins = manifest.get('files_sha256')
    require(isinstance(pins, dict) and REQUIRED <= set(pins) <= ALLOWED
            and all(type(pin) is str and SHA.fullmatch(pin) for pin in pins.values()),
            'HOLD_PREPARE_PAYLOAD_FILESET')
    files = {}
    for filename in sorted(pins):
        files[filename], _ = reader.read(path / filename, 2 * GIB, expected=pins[filename])
    require(sum(value['bytes'] for value in files.values()) <= 2 * GIB,
            'HOLD_PREPARE_CHECKPOINT_BYTES')
    lineage, _ = reader.document(path / 'lineage.json', pins['lineage.json'])
    state, _ = reader.document(path / 'student_state.json', pins['student_state.json'])
    require(digest(encoded(lineage)) == LINEAGE_SHA, 'HOLD_PREPARE_ORIGIN_LINEAGE')
    require(all(state.get(key) == manifest[key] for key in counters)
            and state.get('last_holdout_loss') == manifest['holdout_loss'],
            'HOLD_PREPARE_STUDENT_STATE_COUNTERS')
    for key in ('train_sha256', 'holdout_sha256', 'dataset_manifest_sha256'):
        require(type(lineage.get(key)) is str and SHA.fullmatch(lineage[key]),
                'HOLD_PREPARE_CORPUS_BINDING')
    require(lineage.get('sequence_length') == 512
            and lineage.get('loss_scope') == 'LAST_ASSISTANT_TOKENS_ONLY',
            'HOLD_PREPARE_EVALUATION_PROTOCOL')
    tokenized = lineage.get('tokenized_corpus')
    require(isinstance(tokenized, dict)
            and tokenized.get('schema') == 'NOX_QWEN_TOKENIZED_CORPUS_V1'
            and tokenized.get('sequence_length') == 512
            and tokenized.get('assistant_only_loss') is True
            and isinstance(tokenized.get('splits'), list) and len(tokenized['splits']) == 2,
            'HOLD_PREPARE_TOKENIZED_PROTOCOL')
    holdout = [row for row in tokenized['splits'] if isinstance(row, dict) and row.get('split') == 'holdout']
    require(len(holdout) == 1 and type(holdout[0].get('accepted_rows')) is int
            and holdout[0]['accepted_rows'] == 16
            and all(type(holdout[0].get(key)) is str and SHA.fullmatch(holdout[0][key])
                    for key in ('accepted_example_ids_sha256', 'tokenized_labels_sha256')),
            'HOLD_PREPARE_HOLDOUT_PROTOCOL')
    # Re-read the manifest after its full payload set, closing mixed-read windows.
    reader.document(path / 'checkpoint_manifest.json', manifest_meta['sha256'])
    return {'directory': name, 'manifest_sha256': manifest_meta['sha256'],
            'successful_total': manifest['successful_total'], 'holdout_loss': manifest['holdout_loss'],
            'lineage_sha256': LINEAGE_SHA, 'verified_files': files,
            'full_payload_file_hashes_verified': True,
            'semantic_model_optimizer_restore_verified': False}, lineage


def prepare():
    started = time.monotonic(); reader = Reader()
    result = {'schema': 'NOX_EVAL_ONLY_CHECKPOINT_INPUTSET_V1', 'state': 'HOLD_NOT_PREPARED',
              'files_written': 0, 'training_modules_imported': False, 'unpickle_called': False,
              'optimizer_updates': 0, 'evaluation_completed': False, 'evaluation_admitted': False,
              'quiescence_lease_acquired': False, 'consumer_must_revalidate_inputset': True,
              'guard_changed': False, 'old_seal_changed': False, 'checkpoint_pointer_changed': False,
              'chat_service_changed': False, 'memfd_released': False, 'raw_content_exported': False}
    try:
        guard, _ = reader.document(ROOT / 'state/owner_qwen_training_guard.json', GUARD_SHA)
        policy = guard.get('policy_state')
        require(isinstance(policy, dict) and guard.get('state') == 'INHIBITED' and policy.get('inhibit') is True
                and policy.get('reason') == 'HOLDOUT_REGRESSION'
                and policy.get('best_holdout_loss') == EXPECTED_BEST_LOSS,
                'HOLD_PREPARE_QUALITY_POLICY_CHANGED')
        pointer, _ = reader.document(OUTPUT / 'latest_checkpoint.json', POINTER_SHA)
        require(pointer == {'directory': CP55, 'manifest_sha256': MANIFEST_SHA},
                'HOLD_PREPARE_CP55_ANCHOR_CHANGED')
        ledger, ledger_meta = reader.document(OUTPUT / 'owner_checkpoints.json', limit=2 * 1024 ** 2)
        entries = ledger.get('checkpoints')
        require(ledger.get('schema') == 'NOX_QWEN_OWNED_CHECKPOINTS_V1'
                and ledger.get('lineage_sha256') == LINEAGE_SHA
                and isinstance(entries, list) and len(entries) <= 2000,
                'HOLD_PREPARE_CHECKPOINT_LEDGER')
        retained = [row for row in entries if isinstance(row, dict) and row.get('retained') is True]
        require(all(type(row.get('directory')) is str and NAME.fullmatch(row['directory']) for row in retained)
                and len({row['directory'] for row in retained}) == len(retained),
                'HOLD_PREPARE_RETAINED_CHECKPOINT_IDENTITIES')
        latest = [row for row in retained if row['directory'] == CP55 and row.get('manifest_sha256') == MANIFEST_SHA]
        measured = [row for row in retained if row.get('evaluated_at_current_step') is True and loss(row.get('holdout_loss'))]
        require(len(latest) == 1 and measured, 'HOLD_PREPARE_LATEST_OR_BEST_MISSING')
        best = min(measured, key=lambda row: (row['holdout_loss'], row['directory']))
        require(best['holdout_loss'] == EXPECTED_BEST_LOSS, 'HOLD_PREPARE_BEST_CHECKPOINT_NOT_RETAINED')
        selected = {}; common_lineage = None
        for role, row in (('cp55', latest[0]), ('best_retained', best)):
            selected[role], lineage = checkpoint(reader, row)
            require(common_lineage is None or common_lineage == lineage, 'HOLD_PREPARE_LINEAGE_DIVERGED')
            common_lineage = lineage
        corpus = {}
        for name, key in (('train.jsonl', 'train_sha256'), ('holdout.jsonl', 'holdout_sha256'),
                          ('corpus_manifest.json', 'dataset_manifest_sha256')):
            corpus[name], _ = reader.read(CORPUS / name, 32 * 1024 ** 2, expected=common_lineage[key])
        sources = {}
        for name, pin in SOURCE_PINS.items():
            sources[name], _ = reader.read(ROOT / 'scripts' / name, 300000, expected=pin)
        controller, _ = reader.read(ROOT / 'scripts/nox_dispatcher_t855u.py', 300000,
                                    expected=OBSERVED_CONTROLLER_SHA)
        reader.document(OUTPUT / 'owner_checkpoints.json', ledger_meta['sha256'], limit=2 * 1024 ** 2)
        reader.document(OUTPUT / 'latest_checkpoint.json', POINTER_SHA)
        reader.document(ROOT / 'state/owner_qwen_training_guard.json', GUARD_SHA)
        result.update(state='PREPARED_INPUTSET_EVALUATION_NOT_ADMITTED', checkpoints=selected,
                      corpus=corpus, source_pins=sources, ledger_sha256=ledger_meta['sha256'],
                      guard_sha256=GUARD_SHA, latest_pointer_sha256=POINTER_SHA,
                      observed_controller_sha256=controller['sha256'],
                      sealed_controller_sha256=SEALED_CONTROLLER_SHA,
                      protocol={'kind': 'EVAL_ONLY', 'holdout_examples': 16, 'sequence_length': 512,
                                'loss_scope': 'LAST_ASSISTANT_TOKENS_ONLY', 'optimizer_updates': 0,
                                'update_original_checkpoint_metadata': False,
                                'automatic_quality_latch_reset': False},
                      pending_gates=['REVIEWED_ISOLATED_EVAL_RUNNER', 'ADDITIVE_EXECUTION_CONTEXT',
                                     'VERIFIED_RESOURCE_HANDOFF_AND_CHAT_RESTORE_CONTRACT',
                                     'SEMANTIC_CHECKPOINT_RESTORE', 'FRESH_SAME_HOLDOUT_MEASUREMENTS'],
                      resources={'entry_raw_headroom_bytes': 32 * GIB,
                                 'memfd_stage_raw_base_headroom_bytes': 48 * GIB,
                                 'full_restage_raw_headroom_bytes': 70869001213,
                                 'gpu1_free_mib': 30000, 'disk_floor_bytes': 10 * GIB,
                                 'active_chat_memfd_must_be_preserved': True})
        result['inputset_sha256'] = digest(encoded({key: result[key] for key in
            ('checkpoints', 'corpus', 'source_pins', 'ledger_sha256', 'guard_sha256',
             'latest_pointer_sha256', 'observed_controller_sha256', 'protocol')}))
    except Hold as exc:
        result['state'] = str(exc)
    except (OSError, ValueError, TypeError, UnicodeError, KeyError, RecursionError, OverflowError):
        result['state'] = 'HOLD_PREPARE_SAFE_READ_OR_SCHEMA'
    result['streamed_read_bytes'] = reader.total
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    require(re.fullmatch(r'[0-9]{1,24}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            and re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')),
            'HOLD_PREPARE_OWNER_CONTEXT_REQUIRED')
    result = prepare()
    print('NOX_MAINT_EVAL_CHECKPOINT_PREPARE=' + json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return result


if __name__ == '__main__':
    main()
