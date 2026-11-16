#!/usr/bin/env python3
"""Exact quality-held Qwen checkpoint55, read-only streaming encrypted export.

Native stdout is a binary RSA4096-OAEP/AES256-GCM envelope only. No plaintext
archive, pickle import, service operation, extraction, credential or corpus read.
The immutable accepted6 certificate remains historical; CP55 is saved progress,
not new quality acceptance or permission to resume. Current held execution is
verified from exact sealed metadata and source bytes, without corpus traversal.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import struct
import sys
import tarfile
import time
import types

INSTANCE = 60509551
ROOT = Path('/root/nox')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CHECKPOINT = 'checkpoint-u00000055-a00000055-g01794833901774705882'
MANIFEST_SHA = '458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65'
ACCEPTANCE_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
LINEAGE_SHA = '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190'
LINEAGE_FILE_SHA = '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0'
ACCEPTED_CHECKPOINT = 'checkpoint-u00000006-a00000006-g01794804416868029665'
ACCEPTED_MANIFEST_SHA = 'bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293'
DESCRIPTOR_SHA = '5b4080bd36f24f24e8d166dbcc786a383e192842c15d763128be451458f523c4'
ADMISSION_SHA = 'a461be9ccedcac461ba87dcd88f89c970ee2eefd4b29159ec6a8e3f51bdc852a'
POINTER_SHA = '192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0'
FULL_PROOF_SHA = 'c55c3cd66a5660c7c970bb67d725074be5ef14b9dec4c67ed926f1b8718b33c7'
INSTALLER_SHA = 'd562ff23fcf21fb0873a93e6e68b23f0dffa87db07e3fe309bed3e750d0080e6'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
STUDENT_SHA = '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03'
GUARD_SHA = 'd5217f5bdfe21418d6210a18faac8eef422e49009d8abbcd3e71a06988a8b06b'
WATCHER_SHA = '1012f4d17d61eff0e42d18e96b9b3211cd133a31e235ca062c7e18fcaa090f02'
GUARD_NAME = 'owner_qwen_training_guard.py'
EXPECTED_REFERENCE = {
    'request': '6916464880', 'source_sha': '7029c77906b512faaa9fd4b8290b122ee8c8f1f6',
    'receipt_sha256': 'ad3a760fac2eb56445a8e60dd19fe842ebc3d17dd26ea105485c0631fdf7ce86',
}
EXPECTED_PROCESS = {'pid': 1091069, 'start_ticks': 162502565,
                    'boot_id': '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'}
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
AREA = STATE / 'owner_qwen_execution_revisions' / EXPECTED_REFERENCE['request']
PROC = Path('/proc')
OWNER_UID = 0
FLAG_PINS = {
    'TRAIN_HOLD.flag': ('f5a62613348f1e4516a45dee4ee5eeb791fa9e6ca0c36f10be4414f3f5079866', 54),
    'TRAIN_PAUSE_REQUEST.flag': ('8316e6c12b6a8f53c60d3126fcc421542110e0e9e48848df205ac2c7eaff5aec', 195),
}
JOURNAL_PINS = {
    'watcher_ready.json': 'b02d6e1e1d88d1d95d052613fde264cf97f44e02d8c84b59244bf40ea9d2c023',
    'start_receipt.json': '1bc85f8b30c393698b5fa0ca0a4d7d2cec6c304fbfdd987899c0e9e5488f4db6',
    'watcher_result.json': 'ebe521becaa6d7da9a05d4482003233f762469674b873e428b96f2eb80664efb',
    'activation.json': '33a5789e7e32822e1653ce7973e32dc1c690bd64fc3bfb96e1b357f2a09d3dce',
}
EXPECTED_QUALITY = {
    'inhibit': True, 'reason': 'HOLDOUT_REGRESSION', 'complete': False,
    'last_successful_updates': 55, 'last_evaluation_update': 55,
    'evaluation_age_updates': 0, 'best_holdout_loss': 1.2216252349317074,
    'regression_streak': 2, 'observed_distinct_evaluations': 4,
    'latched_at': 1794833906.8669827,
}
PAYLOAD_SHA = {'README.md': '737e3df079d72e8e52cb3b0b9a5a22e5dcec2a0b51e1bf97fbb5cc1f310ebaa2', 'adapter_config.json': 'c75a7a638e83a417c3b7c421898a9338acc0f90f1c4d62155034ebd10059d7af', 'adapter_model.safetensors': '7969b80d2b9909bcaad50984904c8e83ed0563560d06c7c4f1e6e707b1d616e8', 'lineage.json': '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0', 'optimizer.pt': '94807af108a97210c97280bce06d86ac4ad4aa4e89a0273a796bb0de56707646', 'python_rng.json': '6c1f7cf78612e65f70f7a963bd3f439eeecfacb362f4634bd4737d7e1eddd292', 'rng_state.pt': '41ab9806d56bbaea53567f18abce55dcd283228f5a8cde9778209b779476bddc', 'scaler.pt': 'db8f0b608f7ff901407e7d87d867046142d258cffcd768734737a63f381286ca', 'scheduler.pt': '2d16dd7d402e127a4670c00fd419dfb6f1c35a9a9828b1c219cb13c28614fa77', 'student_state.json': 'ca349563443f14cf02e6333cf7a593bf59b68a20ba1160e5388edb130f3fb2f8'}
BASE_MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
CHECKPOINT_BYTES = 519_936_310
CHECKPOINT_NAMES = ('README.md', 'adapter_config.json', 'adapter_model.safetensors',
                    'lineage.json', 'optimizer.pt', 'python_rng.json', 'rng_state.pt',
                    'scaler.pt', 'scheduler.pt', 'student_state.json')
EXTRA_NAMES = ('checkpoint_manifest.json', 'owner_acceptance.json', 'execution_descriptor.json')
NAMES = CHECKPOINT_NAMES + EXTRA_NAMES
MAGIC = b'NOXQ55E1'
SCHEMA = 'NOX_QWEN55_ENCRYPTED_BACKUP_V1'
KEY_SCHEMA = 'NOX_QWEN55_BACKUP_PUBLIC_KEY_V1'
LABEL = b'NOX_QWEN55_QUALITY_HELD_CHECKPOINT_BACKUP_V1'
ALGORITHM = 'RSA4096-OAEP-SHA256+A256GCM'
MAX_TOTAL = 1024 ** 3
MAX_JSON = 256 * 1024
MAX_HEADER = 32768
BLOCK = 1024 * 1024
MAX_SECONDS = 900
MAX_KEY_TTL = 7200
PART_BYTES = 80 * 1024 ** 2
STOP_PATHS = tuple(ROOT / p for p in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP', 'state/OWNER_MAINTENANCE.flag')) + (Path('/workspace/NOX_STOP'),)
SHA = re.compile('[a-f0-9]{64}')


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_QWEN55_BACKUP_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(rows):
    value = {}
    for key, item in rows:
        require(key not in value, 'DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def document(raw, maximum=MAX_JSON):
    require(isinstance(raw, bytes) and 0 < len(raw) <= maximum, 'JSON_SIZE')
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop(); visited += 1
        require(depth <= 32 and visited <= 30000, 'JSON_COMPLEXITY')
        if type(item) is float:
            require(math.isfinite(item), 'NONFINITE_JSON')
        elif isinstance(item, dict):
            pending.extend((part, depth + 1) for part in item.values())
        elif isinstance(item, list):
            pending.extend((part, depth + 1) for part in item)
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value


def scope():
    return {'schema': 'NOX_QWEN55_BACKUP_SCOPE_V1', 'instance_id': INSTANCE,
            'checkpoint': CHECKPOINT, 'checkpoint_manifest_sha256': MANIFEST_SHA,
            'checkpoint_payload_sha256': dict(PAYLOAD_SHA), 'checkpoint_bytes': CHECKPOINT_BYTES,
            'checkpoint_files': list(CHECKPOINT_NAMES), 'archive_files': list(NAMES),
            'historical_accepted6_sha256': ACCEPTANCE_SHA, 'lineage_sha256': LINEAGE_SHA,
            'lineage_file_sha256': LINEAGE_FILE_SHA, 'execution_revision': dict(EXPECTED_REFERENCE),
            'execution_descriptor_sha256': DESCRIPTOR_SHA, 'current_admission_sha256': ADMISSION_SHA,
            'runtime_entry_sha256': STUDENT_SHA, 'execution_verifier_sha256': SHARED_SHA,
            'historical_activation_permit_sha256': JOURNAL_PINS['activation.json'],
            'after_exit_full_proof_sha256': FULL_PROOF_SHA, 'successful_optimizer_updates': 55,
            'new_execution_optimizer_updates': 30, 'skipped_optimizer_updates': 0,
            'quality_state': 'HOLDOUT_REGRESSION', 'checkpoint_quality_accepted': False,
            'permission_to_resume': False, 'full_base_model_included': False, 'corpus_included': False,
            'scope': 'SAVED_CHECKPOINT55_WITH_QUALITY_HOLD_AND_HISTORICAL_ACCEPTED6'}


def scope_sha():
    return digest(canonical(scope()))


def identity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
                 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def open_regular(path, maximum=MAX_TOTAL):
    """Resolve every parent with directory FDs, never follow a symlink."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_SCOPE')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= maximum, 'REGULAR_FILE_BOUND')
        except BaseException:
            os.close(fd); raise
        return fd, info
    finally:
        os.close(parent)


def checked_fd(fd, path, original):
    fresh, info = open_regular(path)
    try:
        require(identity(os.fstat(fd)) == identity(info) == identity(original), 'FILE_IDENTITY_CHANGED')
    finally:
        os.close(fresh)


class Budget:
    def __init__(self, seconds=MAX_SECONDS, native=False):
        self.deadline = time.monotonic() + seconds
        self.native = native
        self.next_check = 0.0
        self.binding_check = None
        self.next_binding_check = 0.0

    def check(self):
        now = time.monotonic()
        require(now < self.deadline, 'TIME_BOUND')
        if self.native and now >= self.next_check:
            self.next_check = now + 1
            require(not any(p.exists() or p.is_symlink() for p in STOP_PATHS), 'OWNER_STOP')
            values = []
            for name in ('memory.current', 'memory.max'):
                fd = os.open('/sys/fs/cgroup/' + name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    raw = os.read(fd, 128).strip()
                    require(raw.isdigit(), 'CGROUP_MEMORY_UNKNOWN')
                    values.append(int(raw))
                finally:
                    os.close(fd)
            require(values[1] - values[0] >= 512 * 1024 ** 2, 'CGROUP_MEMORY_RESERVE')
        if self.binding_check is not None and now >= self.next_binding_check:
            self.next_binding_check = now + 1
            self.binding_check()


def hash_fd(fd, size, budget, *, keep=False):
    require(not keep or size <= MAX_JSON, 'METADATA_BOUND')
    os.lseek(fd, 0, os.SEEK_SET)
    h, total, chunks = hashlib.sha256(), 0, []
    while total < size:
        budget.check()
        raw = os.read(fd, min(BLOCK, size - total))
        require(bool(raw), 'TRUNCATED_FILE')
        total += len(raw); h.update(raw)
        if keep:
            chunks.append(raw)
    require(os.read(fd, 1) == b'', 'GROWING_FILE')
    return h.hexdigest(), b''.join(chunks)


def validate_documents(meta):
    manifest = document(meta['checkpoint_manifest.json'])
    certificate = document(meta['owner_acceptance.json'])
    lineage = document(meta['lineage.json'])
    saved = document(meta['student_state.json'])
    desc = document(meta['execution_descriptor.json'])
    require(digest(meta['checkpoint_manifest.json']) == MANIFEST_SHA
            and digest(meta['owner_acceptance.json']) == ACCEPTANCE_SHA
            and digest(meta['lineage.json']) == LINEAGE_FILE_SHA
            and digest(meta['student_state.json']) == PAYLOAD_SHA['student_state.json']
            and digest(meta['execution_descriptor.json']) == DESCRIPTOR_SHA, 'EXACT_PROVENANCE_SHA')
    require(manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1'
            and manifest.get('directory') == CHECKPOINT and manifest.get('successful_total') == 55
            and manifest.get('attempted_total') == 55 and manifest.get('lineage_sha256') == LINEAGE_SHA
            and digest(canonical(lineage)) == LINEAGE_SHA
            and manifest.get('files_sha256') == PAYLOAD_SHA
            and set(PAYLOAD_SHA) == set(CHECKPOINT_NAMES), 'MANIFEST_SCOPE')
    require(certificate.get('schema') == 'NOX_QWEN35_9B_UPDATE_PROOF_V1'
            and certificate.get('state') == 'STUDENT_RESTART_AND_UPDATES_VERIFIED'
            and certificate.get('successful_optimizer_steps') == 6
            and certificate.get('new_successful_optimizer_steps') == 1
            and certificate.get('attempted_steps') == 6 and certificate.get('skipped_steps') == 0
            and certificate.get('reload_verified') is True
            and certificate.get('independent_holdout_accepted') is True
            and certificate.get('holdout_finite') is True
            and certificate.get('holdout_evaluated_successful_total') == 6
            and certificate.get('base_manifest_sha256') == BASE_MANIFEST_SHA
            and certificate.get('lineage_sha256') == LINEAGE_SHA
            and certificate.get('checkpoint_manifest_sha256') == ACCEPTED_MANIFEST_SHA
            and certificate.get('checkpoint') == str(OUTPUT / ACCEPTED_CHECKPOINT), 'HISTORICAL_SIX_CERTIFICATE')
    binding = {'schema': 'NOX_QWEN_EXECUTION_BINDING_V1', 'execution_revision': dict(EXPECTED_REFERENCE),
               'descriptor_sha256': DESCRIPTOR_SHA, 'admission_sha256': ADMISSION_SHA,
               'origin_lineage_sha256': LINEAGE_SHA, 'runtime_entry_sha256': STUDENT_SHA,
               'verifier_sha256': SHARED_SHA}
    updates = saved.get('update_evidence')
    witness = saved.get('last_evaluation_witness') or {}
    require(saved.get('successful_total') == saved.get('attempted_total') == 55
            and saved.get('skipped_total') == 0 and saved.get('holdout_evaluated_successful_total') == 55
            and isinstance(updates, list) and len(updates) == 55
            and updates[:6] == certificate.get('update_evidence')
            and len(certificate.get('update_evidence', [])) == 6
            and manifest.get('execution_binding') == binding == saved.get('execution_binding')
            and manifest.get('process_identity') == EXPECTED_PROCESS == witness.get('process_identity')
            and witness.get('schema') == 'NOX_QWEN_EVALUATION_WITNESS_V1'
            and witness.get('execution_binding') == binding and witness.get('kind') == 'PERIODIC'
            and witness.get('evaluated_successful_total') == 55 and witness.get('holdout_examples') == 16
            and witness.get('before') == witness.get('after')
            and manifest.get('holdout_loss') == saved.get('last_holdout_loss') == witness.get('holdout_loss')
            and type(saved.get('last_holdout_loss')) in (int, float)
            and math.isfinite(saved['last_holdout_loss']) and saved['last_holdout_loss'] >= 0,
            'SAVED_CURRENT_EXECUTION')
    require(desc.get('schema') == 'NOX_QWEN_EXECUTION_SUCCESSOR_DESCRIPTOR_V1'
            and desc.get('request') == EXPECTED_REFERENCE['request']
            and desc.get('source_sha') == EXPECTED_REFERENCE['source_sha']
            and desc.get('origin', {}).get('acceptance_sha256') == ACCEPTANCE_SHA
            and desc.get('origin', {}).get('lineage_sha256') == LINEAGE_SHA
            and desc.get('runtime_sources') == {'qwen_student_training_entry_revision.py': STUDENT_SHA,
                                                'owner_qwen_execution_revision.py': SHARED_SHA}
            and desc.get('activation_issuer_sha256') == INSTALLER_SHA
            and desc.get('activation_watcher_sha256') == WATCHER_SHA, 'EXECUTION_DESCRIPTOR')
    return manifest


def read_record(path, expected=None, *, private=False, maximum=MAX_JSON):
    path = Path(path)
    fd, info = open_regular(path, maximum)
    try:
        require(info.st_uid == OWNER_UID and info.st_nlink == 1 and not info.st_mode & 0o022
                and (not private or stat.S_IMODE(info.st_mode) == 0o600), 'BOUND_RECORD_METADATA')
        raw = os.read(fd, maximum + 1)
        require(len(raw) == info.st_size and (expected is None or digest(raw) == expected), 'BOUND_RECORD_SHA')
        checked_fd(fd, path, info)
        return {'raw': raw, 'identity': identity(info), 'sha256': digest(raw), 'bytes': len(raw)}
    finally:
        os.close(fd)


def native_module(name, pin):
    raw = read_record(SCRIPTS / name, pin)['raw']
    value = types.ModuleType('_nox_qwen55_export_' + name.removesuffix('.py'))
    value.__file__ = str(SCRIPTS / name)
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def process_observer(shared):
    name = 'owner_qwen_training_observe.py'
    pin = shared.HISTORICAL[name]
    raw = read_record(SCRIPTS / name, pin)['raw']
    observer = native_module(name, pin)
    node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'trainers')
    scanner = ast.get_source_segment(raw.decode(), node)
    old = "script = str(SCRIPTS / 'qwen_student_training_entry.py').encode()"
    require(scanner.count(old) == 1 and shared.ENTRY == 'qwen_student_training_entry_revision.py',
            'PROCESS_SCANNER_TEMPLATE')
    # Exact same explicit current-basename scanner adaptation as shared d3b.
    scanner = scanner.replace(old, "script = str(SCRIPTS / '" + shared.ENTRY + "').encode()", 1)
    exec(compile(scanner, '<pinned-qwen55-current-scanner>', 'exec'), observer.__dict__)
    return observer


def sealed_context(core, shared):
    """Exact sealed metadata/source reader; never traverse historical corpus data.

This is export admission for one already full-verified checkpoint, not the
training current_context API and not authorization to start/resume a process.
"""
    records = {}
    def read(path, pin=None, private=False, maximum=MAX_JSON):
        record = read_record(path, pin, private=private, maximum=maximum)
        records[Path(path)] = record
        require(len(records) <= 64 and sum(r['bytes'] for r in records.values()) <= 8 * 1024 ** 2,
                'BOUND_METADATA_TOTAL')
        return record['raw']
    config_raw = read(shared.CONFIG, private=True, maximum=32768)
    config = document(config_raw)
    require(config == {'schema': shared.CONFIG_SCHEMA, 'enabled': True, 'source_sha256': SHARED_SHA,
                       'execution_revision': EXPECTED_REFERENCE}, 'CURRENT_CONFIG')
    receipt_raw = read(AREA / 'admission_receipt.json', EXPECTED_REFERENCE['receipt_sha256'], True)
    receipt = document(receipt_raw)
    desc_raw = read(AREA / 'descriptor.json', DESCRIPTOR_SHA, True)
    desc = shared.descriptor(document(desc_raw))
    require(desc['request'] == EXPECTED_REFERENCE['request'] and desc['source_sha'] == EXPECTED_REFERENCE['source_sha']
            and desc['runtime_sources'] == {shared.ENTRY: STUDENT_SHA, shared.SELF: SHARED_SHA}
            and desc['activation_issuer_sha256'] == INSTALLER_SHA
            and desc['activation_watcher_sha256'] == WATCHER_SHA
            and desc['consumer_sources'][GUARD_NAME] == GUARD_SHA, 'CURRENT_DESCRIPTOR')
    admission_raw = read(shared.ADMISSION, ADMISSION_SHA, True, 64000)
    admission = document(admission_raw)
    predecessor = document(read(AREA / 'predecessor_admission.json',
                                shared.PREDECESSOR['admission_sha256'], True, 64000))
    require(admission == shared.make_admission(predecessor, desc, DESCRIPTOR_SHA, admission.get('created_at')),
            'CURRENT_ADMISSION')
    require(isinstance(receipt.get('wrapper_sha256'), str) and SHA.fullmatch(receipt['wrapper_sha256']),
            'WRAPPER_RECEIPT_PIN')
    wrapper = read(shared.WRAPPER, receipt['wrapper_sha256'])
    require(wrapper == shared.make_wrapper(admission, ADMISSION_SHA), 'CURRENT_WRAPPER')
    require(receipt.get('schema') == shared.RECEIPT_SCHEMA
            and receipt.get('state') == 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED'
            and receipt.get('request') == EXPECTED_REFERENCE['request']
            and receipt.get('source_sha') == EXPECTED_REFERENCE['source_sha']
            and receipt.get('descriptor_sha256') == DESCRIPTOR_SHA
            and receipt.get('new_admission_sha256') == ADMISSION_SHA
            and receipt.get('predecessor_execution_revision') == shared.PREDECESSOR['reference']
            and receipt.get('predecessor_descriptor_sha256') == shared.PREDECESSOR['descriptor_sha256']
            and receipt.get('previous_admission_sha256') == shared.PREDECESSOR['admission_sha256']
            and receipt.get('origin_window') == shared.ORIGIN_WINDOW
            and receipt.get('origin_lineage_sha256') == LINEAGE_SHA
            and receipt.get('anchor_checkpoint_manifest_sha256') == shared.ANCHOR['manifest_sha256']
            and receipt.get('activation_watcher_sha256') == WATCHER_SHA
            and receipt.get('runtime_sources') == desc['runtime_sources'], 'SEALED_RECEIPT_BINDINGS')
    pins = {}
    for group in (core.PROTECTED, shared.ORIGINAL_SOURCES, shared.HISTORICAL,
                  desc['runtime_sources'], desc['consumer_sources'],
                  {'owner_qwen_revision_install.py': INSTALLER_SHA, shared.WATCHER: WATCHER_SHA}):
        for name, pin in group.items():
            require(re.fullmatch('[A-Za-z0-9_.-]+', name) and SHA.fullmatch(pin)
                    and (name not in pins or pins[name] == pin), 'SOURCE_GRAPH_SCOPE')
            pins[name] = pin
    for name, pin in pins.items():
        read(SCRIPTS / name, pin)
    lineage_raw = read(OUTPUT / 'owner_lineage.json', LINEAGE_FILE_SHA)
    certificate_raw = read(OUTPUT / 'owner_acceptance.json', ACCEPTANCE_SHA)
    require(digest(canonical(document(lineage_raw))) == LINEAGE_SHA, 'OWNER_LINEAGE')
    ctx = {'execution': {'reference': dict(EXPECTED_REFERENCE), 'directory': AREA, 'descriptor': desc,
                'descriptor_sha256': DESCRIPTOR_SHA, 'receipt': receipt,
                'receipt_sha256': EXPECTED_REFERENCE['receipt_sha256'], 'admission_sha256': ADMISSION_SHA,
                'wrapper_sha256': digest(wrapper), 'runtime_entry_sha256': STUDENT_SHA, 'verifier_sha256': SHARED_SHA},
           'context': dict(EXPECTED_REFERENCE), 'raw': admission_raw, 'wrapper': wrapper,
           'admission': admission, 'profile': admission['student_profile'], 'output': OUTPUT,
           'config_sha256': digest(config_raw), 'admission_sha256': ADMISSION_SHA,
           'wrapper_sha256': digest(wrapper), 'lineage_sha256': LINEAGE_SHA,
           'lineage': document(lineage_raw), 'certificate': document(certificate_raw),
           'argv': shared.make_argv(admission, ADMISSION_SHA), 'observer': process_observer(shared)}
    return ctx, records


def private_snapshot(shared, path, maximum, expected):
    return read_record(path, expected, private=True, maximum=maximum)


def exited(core, shared, ctx):
    """No admitted child and no PID reuse; do not signal or open its descriptors."""
    core.global_stop()
    row = core.trainer(ctx, required=False)
    require(row.get('process_identity') is None and row.get('service') == {'state': 'FATAL', 'pid': None},
            'TRAINER_NOT_STABLY_EXITED')
    require(shared.process_identity_valid(EXPECTED_PROCESS), 'EXPECTED_WRITER')
    boot = (PROC / 'sys/kernel/random/boot_id').read_bytes()
    require(len(boot) <= 128 and boot.strip() == EXPECTED_PROCESS['boot_id'].encode(), 'BOOT_CHANGED')
    try:
        (PROC / str(EXPECTED_PROCESS['pid'])).stat(follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        # Even a different start time is a reuse collision, never absence proof.
        require(False, 'WRITER_PID_PRESENT_OR_REUSED')
    return row


def active(shared, ctx):
    value = shared.activation_status(ctx)
    require(value.get('active') is True and value.get('bootstrap_pending') is False
            and value.get('permit_sha256') == JOURNAL_PINS['activation.json']
            and value.get('initial_process_identity') == EXPECTED_PROCESS
            and value.get('baseline_successful_total') == 25,
            'ACTIVATION_REQUIRED')
    return value


def flag_snapshot(core, shared):
    core.global_stop()
    rows = {}
    for name, (pin, size) in FLAG_PINS.items():
        rows[name] = private_snapshot(shared, STATE / name, 4096, pin)
        require(rows[name]['bytes'] == size, 'FLAG_SIZE')
    require(rows['TRAIN_HOLD.flag']['raw'] == ('OWNER_QWEN_WINDOW_FAILED request='
            + EXPECTED_REFERENCE['request'] + ' goal=1000\n').encode(), 'HOLD_CURRENT_REQUEST')
    return rows


def stable_flags(core, shared, before):
    require(flag_snapshot(core, shared) == before, 'FLAGS_CHANGED')


def historical_records(shared, ctx, permission):
    rows = {name: private_snapshot(shared, ctx['execution']['directory'] / name, 131072, pin)
            for name, pin in JOURNAL_PINS.items()}
    ready, start, result = (shared.parse(rows[name]['raw']) for name in
                           ('watcher_ready.json', 'start_receipt.json', 'watcher_result.json'))
    require(all(row.get('execution_revision') == ctx['context'] for row in (ready, start, result)),
            'HISTORICAL_REFERENCE')
    require(ready.get('schema') == 'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1'
            and ready.get('watcher_source_sha256') == WATCHER_SHA
            and ready.get('issuer_source_sha256') == INSTALLER_SHA
            and ready.get('verifier_sha256') == SHARED_SHA and ready.get('start_capability') is False
            and shared.process_identity_valid(ready.get('process_identity')), 'READY_BINDING')
    started = start.get('trainer') or {}
    require(start.get('schema') == 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1'
            and start.get('start_command_issued') is True and type(start.get('start_command_returncode')) is int
            and start['start_command_returncode'] == 0
            and started.get('process_identity') == EXPECTED_PROCESS
            and started.get('service', {}).get('state') == 'RUNNING'
            and shared.integer(started.get('service', {}).get('pid')) and started['service']['pid'] > 1
            and start.get('watcher_ready_sha256') == rows['watcher_ready.json']['sha256'], 'START_BINDING')
    require(result.get('schema') == 'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1'
            and result.get('state') == 'EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED'
            and result.get('active') is True and result.get('optimizer_permission_issued') is True
            and result.get('ordinary_guard_verified') is True and result.get('finalizer_called_once') is True
            and result.get('watcher_source_sha256') == WATCHER_SHA
            and result.get('process_identity') == ready['process_identity']
            and result.get('start_receipt_sha256') == rows['start_receipt.json']['sha256'], 'RESULT_BINDING')
    times = (ctx['execution']['descriptor']['created_at'], ready.get('armed_at'), start.get('started_at'),
             start.get('sampled_at'), permission['permit'].get('issued_at'), result.get('finished_at'), time.time())
    require(all(shared.finite(t) for t in times) and all(a <= b for a, b in zip(times, times[1:])),
            'HISTORICAL_TIMES')
    require(shared.parse(rows['activation.json']['raw']) == permission['permit'], 'ACTIVATION_RECORD')
    return rows


def quality_hold(shared, guard, ctx, snapshot, flags):
    """Allow heartbeat time/disk telemetry to change; never alter quality policy."""
    config, config_sha = guard.checked_config(expected_source=GUARD_SHA)
    require(config.get('execution_revision') == ctx['context'] and config.get('policy') == shared.GUARD_POLICY,
            'GUARD_CONFIG')
    expected = guard.bindings(config, config_sha, ctx)
    for attempt in range(3):
        try:
            row, raw_sha = guard.previous_state(expected)
            break
        except guard.GuardHold as exc:
            if str(exc) != 'HOLD_QWEN_GUARD_FILE_CHANGED' or attempt == 2:
                raise
    require(isinstance(row, dict) and row.get('state') == 'INHIBITED', 'QUALITY_HOLD_REQUIRED')
    policy = row.get('policy_state') or {}
    require(all(type(policy.get(k)) is type(v) and policy[k] == v for k, v in EXPECTED_QUALITY.items()),
            'QUALITY_POLICY_CHANGED')
    now = time.time()
    require(shared.finite(row.get('sampled_at')) and 0 <= now - row['sampled_at'] <= 30, 'GUARD_STALE')
    cp = row.get('checkpoint') or {}
    require(cp.get('manifest_sha256') == digest(snapshot['manifest_raw'])
            and cp.get('student_state_sha256') == digest(snapshot['state_raw'])
            and cp.get('pointer_sha256') == digest(snapshot['pointer_raw'])
            and cp.get('successful_updates') == 55 and cp.get('attempted_updates') == 55
            and cp.get('skipped_updates') == 0 and cp.get('evaluated_at_update') == 55
            and cp.get('holdout_loss') == snapshot['saved']['last_holdout_loss'], 'GUARD_CHECKPOINT')
    require(guard.pause_token(row) == flags['TRAIN_PAUSE_REQUEST.flag']['raw'], 'GUARD_PAUSE_BINDING')
    return {'semantic': {'bindings': expected, 'quality': {k: policy[k] for k in EXPECTED_QUALITY},
                         'checkpoint_manifest_sha256': cp['manifest_sha256'], 'state': row['state']},
            'row_sha256': raw_sha, 'sampled_at': row['sampled_at']}


class HeldExecution:
    """Metadata-only binding during the fixed archive's full payload hash passes."""
    def __init__(self):
        self.core = native_module('owner_qwen_revision_install.py', INSTALLER_SHA)
        self.shared = native_module('owner_qwen_execution_revision.py', SHARED_SHA)
        self.guard = native_module(GUARD_NAME, GUARD_SHA)
        require(self.core.PINS[self.core.SHARED_ASSET] == SHARED_SHA
                and self.core.PINS[self.core.STUDENT_ASSET] == STUDENT_SHA, 'ISSUER_SOURCE_GRAPH')
        self.core.global_stop(); self.core.protected()
        self.ctx, self.records = sealed_context(self.core, self.shared)
        self.permission = active(self.shared, self.ctx)
        self.history = historical_records(self.shared, self.ctx, self.permission)
        self.flags = flag_snapshot(self.core, self.shared)
        self.dead = exited(self.core, self.shared, self.ctx)
        for name, row in self.history.items(): self.records[AREA / name] = row
        pointer = read_record(OUTPUT / 'latest_checkpoint.json', POINTER_SHA)
        manifest = read_record(OUTPUT / CHECKPOINT / 'checkpoint_manifest.json', MANIFEST_SHA)
        state = read_record(OUTPUT / CHECKPOINT / 'student_state.json', PAYLOAD_SHA['student_state.json'])
        self.records.update({OUTPUT / 'latest_checkpoint.json': pointer,
                             OUTPUT / CHECKPOINT / 'checkpoint_manifest.json': manifest,
                             OUTPUT / CHECKPOINT / 'student_state.json': state})
        require(document(pointer['raw']).get('directory') == CHECKPOINT
                and document(pointer['raw']).get('manifest_sha256') == MANIFEST_SHA, 'LATEST_CHECKPOINT')
        self.snapshot = {'pointer_raw': pointer['raw'], 'manifest_raw': manifest['raw'],
                         'state_raw': state['raw'], 'saved': document(state['raw'])}
        witness = self.shared.evaluation_witness(self.ctx, self.snapshot['saved']['last_evaluation_witness'])
        require(witness['process_identity'] == EXPECTED_PROCESS and witness['evaluated_successful_total'] == 55,
                'CURRENT_EVALUATION_PROCESS')
        self.quality = quality_hold(self.shared, self.guard, self.ctx, self.snapshot, self.flags)
        self.records[self.shared.GUARD_CONFIG] = read_record(self.shared.GUARD_CONFIG, private=True, maximum=32768)

    def check(self):
        self.core.global_stop()
        stable_flags(self.core, self.shared, self.flags)
        for path, row in self.records.items():
            require(identity(path.stat(follow_symlinks=False)) == row['identity'], 'BOUND_IDENTITY_CHANGED')
        require(exited(self.core, self.shared, self.ctx) == self.dead, 'TRAINER_CHANGED')
        value = quality_hold(self.shared, self.guard, self.ctx, self.snapshot, self.flags)
        require(value['semantic'] == self.quality['semantic'], 'QUALITY_HOLD_CHANGED')

    def reverify(self, metadata):
        self.check()
        for path, row in self.records.items():
            fresh = read_record(path, row['sha256'])
            require(fresh == row, 'BOUND_RECORD_CHANGED')
        ctx, records = sealed_context(self.core, self.shared)
        require(all(records[path] == self.records[path] for path in records)
                and ctx['execution'] == self.ctx['execution'], 'SEALED_CONTEXT_CHANGED')
        self.core.protected()
        require(active(self.shared, ctx) == self.permission
                and historical_records(self.shared, ctx, self.permission) == self.history,
                'HISTORICAL_ADMISSION_CHANGED')
        require(metadata['checkpoint_manifest.json'] == self.snapshot['manifest_raw']
                and metadata['student_state.json'] == self.snapshot['state_raw']
                and metadata['execution_descriptor.json'] == self.records[AREA / 'descriptor.json']['raw'],
                'EXPORTED_EXECUTION_CHANGED')
        self.check()


class Snapshot:
    def __init__(self, budget):
        self.budget, self.files, self.meta, self.held = budget, {}, {}, None

    def __enter__(self):
        try:
            require(self.budget.binding_check is None, 'BUDGET_BINDING_REUSE')
            self.held = HeldExecution()
            self.budget.binding_check = self.held.check
            paths = {name: OUTPUT / CHECKPOINT / name for name in CHECKPOINT_NAMES}
            paths.update({'checkpoint_manifest.json': OUTPUT / CHECKPOINT / 'checkpoint_manifest.json',
                          'owner_acceptance.json': OUTPUT / 'owner_acceptance.json',
                          'execution_descriptor.json': AREA / 'descriptor.json'})
            for name in NAMES:
                self.budget.check()
                fd, info = open_regular(paths[name])
                self.files[name] = {'fd': fd, 'info': info, 'path': paths[name]}
                require(info.st_uid == OWNER_UID and info.st_nlink == 1 and not info.st_mode & 0o022,
                        'PAYLOAD_OWNERSHIP')
            # Bound the complete fixed set before hashing any large payload.
            require(sum(self.files[n]['info'].st_size for n in CHECKPOINT_NAMES) == CHECKPOINT_BYTES, 'CHECKPOINT_BYTES')
            require(sum(v['info'].st_size for v in self.files.values()) <= MAX_TOTAL, 'TOTAL_BYTES')
            for name in NAMES:
                row = self.files[name]
                fd, info = row['fd'], row['info']
                pin, raw = hash_fd(fd, info.st_size, self.budget, keep=name.endswith('.json'))
                checked_fd(fd, paths[name], info)
                self.files[name].update(sha256=pin, bytes=info.st_size)
                if name.endswith('.json'):
                    self.meta[name] = raw
            manifest = validate_documents(self.meta)
            require(all(self.files[n]['sha256'] == manifest['files_sha256'][n] for n in CHECKPOINT_NAMES), 'CHECKPOINT_SHA')
            # The output-level lineage is independently pinned but not duplicated in the archive.
            fd, info = open_regular(OUTPUT / 'owner_lineage.json', MAX_JSON)
            try:
                pin, raw = hash_fd(fd, info.st_size, self.budget, keep=True)
                require(pin == LINEAGE_FILE_SHA and raw == self.meta['lineage.json'], 'OWNER_LINEAGE')
                checked_fd(fd, OUTPUT / 'owner_lineage.json', info)
            finally:
                os.close(fd)
            self.held.reverify(self.meta)
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def __exit__(self, *_):
        self.budget.binding_check = None
        for row in self.files.values():
            os.close(row['fd'])
        self.files.clear()

    def projection(self):
        return {name: {'bytes': self.files[name]['bytes'], 'sha256': self.files[name]['sha256']} for name in NAMES}

    def reverify(self):
        for name in NAMES:
            row = self.files[name]
            pin, _ = hash_fd(row['fd'], row['bytes'], self.budget)
            require(pin == row['sha256'], 'POST_EXPORT_SHA')
            checked_fd(row['fd'], row['path'], row['info'])
        self.held.reverify(self.meta)


def archive_size(files):
    require(set(files) == set(NAMES), 'ARCHIVE_NAMES')
    total = 1024 + sum(512 + ((files[n]['bytes'] + 511) // 512) * 512 for n in NAMES)
    return ((total + 10239) // 10240) * 10240


def public_key(meta, *, now=None):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    require(set(meta) == {'schema', 'scope_sha256', 'transfer_id', 'created_at', 'expires_at', 'public_key_pem', 'key_id'}, 'PUBLIC_METADATA_KEYS')
    require(meta['schema'] == KEY_SCHEMA and meta['scope_sha256'] == scope_sha()
            and isinstance(meta['transfer_id'], str) and re.fullmatch('[a-f0-9]{32}', meta['transfer_id'])
            and type(meta['created_at']) is int and type(meta['expires_at']) is int
            and 0 < meta['expires_at'] - meta['created_at'] <= MAX_KEY_TTL, 'PUBLIC_METADATA_SCOPE')
    if now is not None:
        require(meta['created_at'] - 30 <= now <= meta['expires_at'], 'PUBLIC_KEY_EXPIRED')
    pem = meta['public_key_pem']
    require(isinstance(pem, str) and len(pem) <= 2048 and 'PRIVATE' not in pem, 'PUBLIC_PEM_SCOPE')
    key = serialization.load_pem_public_key(pem.encode('ascii'))
    require(isinstance(key, rsa.RSAPublicKey) and key.key_size == 4096 and key.public_numbers().e == 65537, 'PUBLIC_RSA4096')
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    require(meta['key_id'] == digest(der), 'PUBLIC_KEY_FINGERPRINT')
    return key


def validate_header(header, public_meta):
    require(set(header) == {'schema', 'algorithm', 'scope_sha256', 'public_metadata_sha256', 'transfer_id',
                           'key_id', 'created_at', 'source_sha', 'workflow_run_id', 'nonce', 'wrapped_key',
                           'archive_format', 'archive_bytes', 'files'}, 'HEADER_KEYS')
    require(header['schema'] == SCHEMA and header['algorithm'] == ALGORITHM
            and header['scope_sha256'] == scope_sha()
            and header['public_metadata_sha256'] == digest(canonical(public_meta))
            and header['transfer_id'] == public_meta['transfer_id'] and header['key_id'] == public_meta['key_id']
            and type(header['created_at']) is int
            and public_meta['created_at'] - 30 <= header['created_at'] <= public_meta['expires_at']
            and isinstance(header['source_sha'], str) and re.fullmatch('[a-f0-9]{40}', header['source_sha'])
            and isinstance(header['workflow_run_id'], str) and re.fullmatch('[0-9]{1,24}', header['workflow_run_id'])
            and header['archive_format'] == 'USTAR_UNCOMPRESSED', 'HEADER_SCOPE')
    files = header['files']
    require(isinstance(files, dict) and set(files) == set(NAMES), 'HEADER_FILES')
    for row in files.values():
        require(isinstance(row, dict) and set(row) == {'bytes', 'sha256'}
                and type(row['bytes']) is int and 0 < row['bytes'] <= MAX_TOTAL
                and isinstance(row['sha256'], str) and SHA.fullmatch(row['sha256']), 'HEADER_FILE_ROW')
    require(sum(files[n]['bytes'] for n in CHECKPOINT_NAMES) == CHECKPOINT_BYTES
            and sum(row['bytes'] for row in files.values()) <= MAX_TOTAL
            and files['checkpoint_manifest.json']['sha256'] == MANIFEST_SHA
            and files['owner_acceptance.json']['sha256'] == ACCEPTANCE_SHA
            and files['lineage.json']['sha256'] == LINEAGE_FILE_SHA
            and files['execution_descriptor.json']['sha256'] == DESCRIPTOR_SHA
            and all(files[name]['sha256'] == pin for name, pin in PAYLOAD_SHA.items())
            and type(header['archive_bytes']) is int and header['archive_bytes'] == archive_size(files), 'HEADER_EXACT_CHECKPOINT')
    require(len(base64.b64decode(header['nonce'], validate=True)) == 12
            and len(base64.b64decode(header['wrapped_key'], validate=True)) == 512, 'HEADER_CRYPTO_LENGTH')
    return header


class HashReader:
    def __init__(self, row, budget):
        self.row, self.budget, self.total, self.hash = row, budget, 0, hashlib.sha256()
        os.lseek(row['fd'], 0, os.SEEK_SET)

    def read(self, count):
        self.budget.check()
        require(0 <= count <= BLOCK and self.total + count <= self.row['bytes'], 'TAR_READ_BOUND')
        raw = os.read(self.row['fd'], count)
        self.total += len(raw); self.hash.update(raw)
        return raw


def export(public_meta, source_sha, run_id, stream, budget):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    key = public_key(public_meta, now=int(time.time()))
    with Snapshot(budget) as snapshot:
        aes, nonce = os.urandom(32), os.urandom(12)
        wrapped = key.encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=LABEL))
        files = snapshot.projection()
        header = {'schema': SCHEMA, 'algorithm': ALGORITHM, 'scope_sha256': scope_sha(),
                  'public_metadata_sha256': digest(canonical(public_meta)), 'transfer_id': public_meta['transfer_id'],
                  'key_id': public_meta['key_id'], 'created_at': int(time.time()), 'source_sha': source_sha,
                  'workflow_run_id': run_id, 'nonce': base64.b64encode(nonce).decode(),
                  'wrapped_key': base64.b64encode(wrapped).decode(), 'archive_format': 'USTAR_UNCOMPRESSED',
                  'archive_bytes': archive_size(files), 'files': files}
        validate_header(header, public_meta)
        raw_header = canonical(header)
        require(len(raw_header) <= MAX_HEADER, 'HEADER_SIZE')
        prefix = MAGIC + struct.pack('>I', len(raw_header)) + raw_header
        encryptor = Cipher(algorithms.AES(aes), modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(prefix)
        cipher_hash, wire_bytes, plain_bytes = hashlib.sha256(), 0, 0

        def wire(raw):
            nonlocal wire_bytes
            budget.check(); stream.write(raw); cipher_hash.update(raw); wire_bytes += len(raw)

        class Writer:
            def write(self, raw):
                nonlocal plain_bytes
                require(len(raw) <= BLOCK, 'STREAM_BUFFER')
                plain_bytes += len(raw)
                require(plain_bytes <= header['archive_bytes'], 'ARCHIVE_BOUND')
                wire(encryptor.update(raw))
                return len(raw)

        wire(prefix)
        with tarfile.open(mode='w|', fileobj=Writer(), format=tarfile.USTAR_FORMAT, bufsize=BLOCK) as archive:
            for name in NAMES:
                row = snapshot.files[name]
                member = tarfile.TarInfo(name)
                member.size, member.mode, member.mtime = row['bytes'], 0o600, 0
                member.uid = member.gid = 0
                member.uname = member.gname = ''
                reader = HashReader(row, budget)
                archive.addfile(member, reader)
                require(reader.total == row['bytes'] and reader.hash.hexdigest() == row['sha256'], 'STREAM_SOURCE_SHA')
                checked_fd(row['fd'], row['path'], row['info'])
        require(plain_bytes == header['archive_bytes'], 'ARCHIVE_SIZE')
        # No authentication tag is released unless every original file is rehashed.
        snapshot.reverify()
        budget.check()
        require(int(time.time()) <= public_meta['expires_at'], 'PUBLIC_KEY_EXPIRED')
        wire(encryptor.finalize()); wire(encryptor.tag); stream.flush()
        require(wire_bytes == len(prefix) + header['archive_bytes'] + 16, 'WIRE_LENGTH')
        return {'schema': 'NOX_QWEN55_NATIVE_EXPORT_RECEIPT_V1', 'state': 'ENCRYPTED_EXACT_CHECKPOINT55_EXPORTED',
                'transfer_id': header['transfer_id'], 'scope_sha256': scope_sha(), 'source_sha': source_sha,
                'workflow_run_id': run_id, 'ciphertext_bytes': wire_bytes, 'ciphertext_sha256': cipher_hash.hexdigest(),
                'archive_bytes': plain_bytes, 'archive_files': len(NAMES), 'checkpoint_files': len(CHECKPOINT_NAMES),
                'checkpoint_bytes': CHECKPOINT_BYTES, 'all_source_sha256_verified_before_during_after': True,
                'execution_revision': dict(EXPECTED_REFERENCE), 'after_exit_full_proof_sha256': FULL_PROOF_SHA,
                'quality_hold_preserved': True, 'historical_accepted6_preserved': True,
                'admitted_process_absent_before_during_after': True, 'permission_to_resume': False,
                'checkpoint_quality_accepted': False,
                'native_plaintext_files_written': 0, 'native_service_actions': 0, 'native_files_deleted': 0,
                'local_decryption_verified': False, 'drive_copy_verified': False}


def native_main(public_meta, source_sha, run_id):
    try:
        import resource
        os.umask(0o077)
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 ** 2, 512 * 1024 ** 2))
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        signal.signal(signal.SIGALRM, lambda *_: require(False, 'TIME_BOUND'))
        signal.alarm(MAX_SECONDS)
        receipt = export(public_meta, source_sha, run_id, sys.stdout.buffer, Budget(native=True))
        print('NOX_QWEN55_EXPORT=' + canonical(receipt).decode(), file=sys.stderr, flush=True)
        return 0
    except BaseException as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_QWEN55_BACKUP_[A-Z0-9_]{1,100}', reason):
            reason = 'HOLD_QWEN55_BACKUP_' + type(exc).__name__.upper()
        print('NOX_QWEN55_EXPORT_HOLD=' + reason, file=sys.stderr, flush=True)
        return 2
