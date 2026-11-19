#!/usr/bin/env python3
"""Exact accepted Qwen checkpoint6, read-only streaming encrypted export.

Native stdout is a binary RSA4096-OAEP/AES256-GCM envelope only. No plaintext
archive, pickle import, service operation, extraction, credential or corpus read.
The accepted checkpoint is immutable scope, independent of a later live window.
"""
from __future__ import annotations

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

INSTANCE = 60509551
ROOT = Path('/root/nox')
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CHECKPOINT = 'checkpoint-u00000006-a00000006-g01794804416868029665'
MANIFEST_SHA = 'bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293'
ACCEPTANCE_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
LINEAGE_SHA = '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190'
LINEAGE_FILE_SHA = '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0'
WINDOW_REQUEST = '6907513913'
WINDOW_SOURCE = '4d5f0b065309f3524dc4d5d08d3924a4d0223931'
WINDOW_SHA = '4547158a490e9c367a6f59f0936f6c0ae3836d40a797fe47b1f303dae38f4308'
BASE_MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
CHECKPOINT_BYTES = 519_882_866
CHECKPOINT_NAMES = ('README.md', 'adapter_config.json', 'adapter_model.safetensors',
                    'lineage.json', 'optimizer.pt', 'python_rng.json', 'rng_state.pt',
                    'scaler.pt', 'scheduler.pt', 'student_state.json')
EXTRA_NAMES = ('checkpoint_manifest.json', 'owner_acceptance.json', 'window6_receipt.json')
NAMES = CHECKPOINT_NAMES + EXTRA_NAMES
MAGIC = b'NOXQW6E1'
SCHEMA = 'NOX_QWEN6_ENCRYPTED_BACKUP_V1'
KEY_SCHEMA = 'NOX_QWEN6_BACKUP_PUBLIC_KEY_V1'
LABEL = b'NOX_QWEN6_ACCEPTED_CHECKPOINT_BACKUP_V1'
ALGORITHM = 'RSA4096-OAEP-SHA256+A256GCM'
MAX_TOTAL = 1024 ** 3
MAX_JSON = 256 * 1024
MAX_HEADER = 32768
BLOCK = 1024 * 1024
MAX_SECONDS = 900
MAX_KEY_TTL = 7200
PART_BYTES = 80 * 1024 ** 2
STOP_PATHS = tuple(ROOT / p for p in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) + (Path('/workspace/NOX_STOP'),)
SHA = re.compile('[a-f0-9]{64}')


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_QWEN6_BACKUP_' + code)


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
    return {'schema': 'NOX_QWEN6_BACKUP_SCOPE_V1', 'instance_id': INSTANCE,
            'checkpoint': CHECKPOINT, 'checkpoint_manifest_sha256': MANIFEST_SHA,
            'acceptance_sha256': ACCEPTANCE_SHA, 'lineage_sha256': LINEAGE_SHA,
            'lineage_file_sha256': LINEAGE_FILE_SHA, 'checkpoint_files': list(CHECKPOINT_NAMES),
            'checkpoint_bytes': CHECKPOINT_BYTES, 'archive_files': list(NAMES),
            'window_request': WINDOW_REQUEST, 'window_source_sha': WINDOW_SOURCE,
            'window_receipt_sha256': WINDOW_SHA, 'successful_optimizer_updates': 6,
            'skipped_optimizer_updates': 0, 'full_base_model_included': False,
            'corpus_included': False, 'scope': 'ACCEPTED_CHECKPOINT6_AND_RESTART_PROVENANCE'}


def scope_sha():
    return digest(canonical(scope()))


def identity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


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
    window = document(meta['window6_receipt.json'])
    require(digest(meta['checkpoint_manifest.json']) == MANIFEST_SHA
            and digest(meta['owner_acceptance.json']) == ACCEPTANCE_SHA
            and digest(meta['lineage.json']) == LINEAGE_FILE_SHA
            and digest(meta['window6_receipt.json']) == WINDOW_SHA, 'EXACT_PROVENANCE_SHA')
    require(manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1'
            and manifest.get('directory') == CHECKPOINT and manifest.get('successful_total') == 6
            and manifest.get('attempted_total') == 6 and manifest.get('lineage_sha256') == LINEAGE_SHA
            and digest(canonical(lineage)) == LINEAGE_SHA
            and set(manifest.get('files_sha256', {})) == set(CHECKPOINT_NAMES)
            and all(isinstance(v, str) and SHA.fullmatch(v) for v in manifest['files_sha256'].values()), 'MANIFEST_SCOPE')
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
            and certificate.get('checkpoint_manifest_sha256') == MANIFEST_SHA
            and certificate.get('checkpoint') == str(OUTPUT / CHECKPOINT), 'RESTART_CERTIFICATE')
    require(saved.get('successful_total') == saved.get('attempted_total') == 6
            and saved.get('skipped_total') == 0
            and saved.get('holdout_evaluated_successful_total') == 6
            and saved.get('update_evidence') == certificate.get('update_evidence')
            and len(saved.get('update_evidence', [])) == 6
            and manifest.get('adapter_tensor_sha256') == certificate.get('final_adapter_tensor_sha256'), 'SAVED_STATE')
    require(window.get('schema') == 'NOX_QWEN_WINDOW_ADVANCE_V1'
            and window.get('request') == WINDOW_REQUEST and window.get('source_sha') == WINDOW_SOURCE
            and window.get('initial_request') == '6907283384' and window.get('target_goal') == 6
            and window.get('state') == 'WINDOW_STARTED_ACCEPTANCE_PENDING', 'WINDOW_PROVENANCE')
    return manifest


class Snapshot:
    def __init__(self, budget):
        self.budget, self.files, self.meta = budget, {}, {}

    def __enter__(self):
        try:
            paths = {name: OUTPUT / CHECKPOINT / name for name in CHECKPOINT_NAMES}
            paths.update({'checkpoint_manifest.json': OUTPUT / CHECKPOINT / 'checkpoint_manifest.json',
                          'owner_acceptance.json': OUTPUT / 'owner_acceptance.json',
                          'window6_receipt.json': ROOT / 'state' / ('owner_qwen_window_' + WINDOW_REQUEST + '.json')})
            for name in NAMES:
                self.budget.check()
                fd, info = open_regular(paths[name])
                self.files[name] = {'fd': fd, 'info': info, 'path': paths[name]}
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
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def __exit__(self, *_):
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
            and files['window6_receipt.json']['sha256'] == WINDOW_SHA
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
        return {'schema': 'NOX_QWEN6_NATIVE_EXPORT_RECEIPT_V1', 'state': 'ENCRYPTED_EXACT_CHECKPOINT6_EXPORTED',
                'transfer_id': header['transfer_id'], 'scope_sha256': scope_sha(), 'source_sha': source_sha,
                'workflow_run_id': run_id, 'ciphertext_bytes': wire_bytes, 'ciphertext_sha256': cipher_hash.hexdigest(),
                'archive_bytes': plain_bytes, 'archive_files': len(NAMES), 'checkpoint_files': len(CHECKPOINT_NAMES),
                'checkpoint_bytes': CHECKPOINT_BYTES, 'all_source_sha256_verified_before_during_after': True,
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
        print('NOX_QWEN6_EXPORT=' + canonical(receipt).decode(), file=sys.stderr, flush=True)
        return 0
    except BaseException as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_QWEN6_BACKUP_[A-Z0-9_]{1,100}', reason):
            reason = 'HOLD_QWEN6_BACKUP_' + type(exc).__name__.upper()
        print('NOX_QWEN6_EXPORT_HOLD=' + reason, file=sys.stderr, flush=True)
        return 2
