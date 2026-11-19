#!/usr/bin/env python3
"""Authenticate and verify the fixed Qwen6 artifact; optional private tar parts.

Never extracts an archive or imports/unpickles a checkpoint. GCM authentication
finishes in a discard pass before a second pass parses any decrypted tar member.
Optional plaintext archive parts are local0600, suitable for the owner's private
Drive. No private key is copied or printed, and no network is used here.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tarfile

import owner_qwen6_backup_stream as core

RECEIPT_SCHEMA = 'NOX_QWEN6_ARTIFACT_RECEIPT_V1'
RESTORE_SCHEMA = 'NOX_QWEN6_PRIVATE_RESTORE_MANIFEST_V1'


class PartReader:
    def __init__(self, directory, rows):
        self.directory, self.rows, self.index, self.stream = Path(directory).absolute(), rows, 0, None
        self.hash, self.part_read, self.position = None, 0, 0
        self.fd_identity = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close(); self.stream = None

    def read(self, count):
        core.require(type(count) is int and 0 <= count <= core.BLOCK, 'LOCAL_READ_BOUND')
        chunks, pending = [], count
        while pending and self.index < len(self.rows):
            row = self.rows[self.index]
            path = self.directory / row['name']
            if self.stream is None:
                fd, info = core.open_regular(path, core.PART_BYTES)
                core.require(info.st_size == row['bytes'], 'PART_SIZE')
                self.stream, self.fd_identity = os.fdopen(fd, 'rb'), info
                self.hash, self.part_read = hashlib.sha256(), 0
            raw = self.stream.read(min(pending, row['bytes'] - self.part_read))
            self.hash.update(raw); self.part_read += len(raw)
            self.position += len(raw); pending -= len(raw); chunks.append(raw)
            if self.part_read == row['bytes']:
                core.require(self.stream.read(1) == b'' and self.hash.hexdigest() == row['sha256'], 'PART_SHA')
                core.checked_fd(self.stream.fileno(), path, self.fd_identity)
                self.stream.close(); self.stream = None; self.index += 1
            else:
                core.require(bool(raw), 'PART_TRUNCATED')
        return b''.join(chunks)


def exact(stream, count):
    result = bytearray()
    while len(result) < count:
        block = stream.read(min(core.BLOCK, count - len(result)))
        core.require(bool(block), 'ENVELOPE_TRUNCATED'); result.extend(block)
    return bytes(result)


def envelope_header(stream, public_meta):
    prefix = exact(stream, 12)
    core.require(prefix[:8] == core.MAGIC, 'ENVELOPE_MAGIC')
    size = struct.unpack('>I', prefix[8:])[0]
    core.require(0 < size <= core.MAX_HEADER, 'HEADER_BOUND')
    raw = exact(stream, size)
    header = core.document(raw, core.MAX_HEADER)
    core.require(core.canonical(header) == raw, 'HEADER_CANONICAL')
    core.validate_header(header, public_meta)
    return header, prefix + raw


def receipt_document(raw):
    value = core.document(raw)
    core.require(value.get('schema') == RECEIPT_SCHEMA and value.get('state') == 'CIPHERTEXT_READY_LOCAL_VERIFICATION_REQUIRED'
                 and value.get('scope_sha256') == core.scope_sha(), 'ARTIFACT_RECEIPT')
    rows = value.get('parts')
    core.require(isinstance(rows, list) and 1 <= len(rows) <= 13, 'PART_COUNT')
    for i, row in enumerate(rows):
        core.require(set(row) == {'name', 'bytes', 'sha256'}
                     and row['name'] == f'qwen6-cipher.part{i:03d}'
                     and type(row['bytes']) is int and 0 < row['bytes'] <= core.PART_BYTES
                     and isinstance(row['sha256'], str) and core.SHA.fullmatch(row['sha256'])
                     and (i == len(rows) - 1 or row['bytes'] == core.PART_BYTES), 'PART_ROW')
    core.require(sum(v['bytes'] for v in rows) == value.get('ciphertext_bytes')
                 and isinstance(value.get('ciphertext_sha256'), str) and core.SHA.fullmatch(value['ciphertext_sha256']), 'CIPHERTEXT_RECEIPT')
    native = value.get('native') or {}
    core.require(native.get('schema') == 'NOX_QWEN6_NATIVE_EXPORT_RECEIPT_V1'
                 and native.get('state') == 'ENCRYPTED_EXACT_CHECKPOINT6_EXPORTED'
                 and native.get('all_source_sha256_verified_before_during_after') is True
                 and native.get('ciphertext_sha256') == value['ciphertext_sha256']
                 and native.get('ciphertext_bytes') == value['ciphertext_bytes'], 'NATIVE_EXPORT_RECEIPT')
    return value


def private_key(path, public_meta):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    fd, info = core.open_regular(Path(path).absolute(), 16384)
    try:
        core.require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0, 'PRIVATE_KEY_PERMISSIONS')
        raw = os.read(fd, 16385)
        core.checked_fd(fd, Path(path).absolute(), info)
    finally:
        os.close(fd)
    key = serialization.load_pem_private_key(raw, password=None)
    core.require(isinstance(key, rsa.RSAPrivateKey) and key.key_size == 4096, 'PRIVATE_KEY_TYPE')
    core.require(key.public_key().public_numbers() == core.public_key(public_meta).public_numbers(), 'PRIVATE_KEY_MATCH')
    return key


class DecryptedReader:
    def __init__(self, stream, header, prefix, key, sink=None):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        secret = key.decrypt(base64.b64decode(header['wrapped_key'], validate=True),
                             padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=core.LABEL))
        core.require(len(secret) == 32, 'AES_KEY_SIZE')
        self.decryptor = Cipher(algorithms.AES(secret), modes.GCM(base64.b64decode(header['nonce'], validate=True))).decryptor()
        self.decryptor.authenticate_additional_data(prefix)
        self.stream, self.remaining, self.sink = stream, header['archive_bytes'], sink
        self.cipher_hash, self.plain_hash = hashlib.sha256(prefix), hashlib.sha256()
        self.finalized = False

    def read(self, count):
        core.require(type(count) is int and 0 <= count <= core.BLOCK, 'DECRYPT_READ_BOUND')
        if self.remaining == 0:
            self.finish(); return b''
        raw = exact(self.stream, min(count, self.remaining))
        self.remaining -= len(raw); self.cipher_hash.update(raw)
        plain = self.decryptor.update(raw); self.plain_hash.update(plain)
        if self.sink is not None:
            self.sink.write(plain)
        return plain

    def finish(self):
        core.require(self.remaining == 0, 'DECRYPT_INCOMPLETE')
        if not self.finalized:
            tag = exact(self.stream, 16); self.cipher_hash.update(tag)
            tail = self.decryptor.finalize_with_tag(tag)
            core.require(tail == b'' and self.stream.read(1) == b'', 'ENVELOPE_TRAILING_BYTES')
            self.finalized = True


class PrivateParts:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        # Refuse reuse/overwrites. Verify the existing parent chain before mkdir.
        parent = self.directory.parent
        core.require(parent.is_dir() and not any(p.is_symlink() for p in (parent, *parent.parents)), 'RESTORE_PARENT')
        self.directory.mkdir(mode=0o700)
        self.rows, self.stream, self.h, self.count = [], None, None, 0

    def write(self, raw):
        while raw:
            if self.stream is None:
                name = f'qwen6-restore.tar.part{len(self.rows):03d}'
                fd = os.open(self.directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                self.stream, self.h, self.count = os.fdopen(fd, 'wb'), hashlib.sha256(), 0
            block, raw = raw[:core.PART_BYTES - self.count], raw[core.PART_BYTES - self.count:]
            self.stream.write(block); self.h.update(block); self.count += len(block)
            if self.count == core.PART_BYTES:
                self.close_part()

    def close_part(self):
        if self.stream is not None:
            self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
            self.rows.append({'name': f'qwen6-restore.tar.part{len(self.rows):03d}', 'bytes': self.count, 'sha256': self.h.hexdigest()})
            self.stream = None

    def failure(self):
        # Leave private incomplete files for diagnosis; never advertise a restore manifest.
        if self.stream is not None:
            self.stream.close(); self.stream = None


def verify_tar(reader, files, size):
    """Parse only the thirteen fixed USTAR regular members; no extraction."""
    core.require(set(files) == set(core.NAMES) and size == core.archive_size(files), 'TAR_MANIFEST_SCOPE')
    metadata, verified, consumed = {}, {}, 0
    for expected in core.NAMES:
        member = tarfile.TarInfo.frombuf(exact(reader, 512), 'utf-8', 'strict')
        row = files[expected]
        core.require(member.name == expected and member.type == tarfile.REGTYPE
                     and member.size == row['bytes'] and member.linkname == ''
                     and member.mode == 0o600 and member.uid == member.gid == member.mtime == 0
                     and member.uname == member.gname == '' and not member.pax_headers,
                     'ARCHIVE_MEMBER_SCOPE')
        h, total, chunks = hashlib.sha256(), 0, []
        while total < member.size:
            block = exact(reader, min(core.BLOCK, member.size - total))
            total += len(block); h.update(block)
            if expected.endswith('.json'):
                core.require(total <= core.MAX_JSON, 'ARCHIVE_METADATA_BOUND'); chunks.append(block)
        core.require(h.hexdigest() == row['sha256'], 'RESTORED_FILE_SHA')
        padding = (-member.size) % 512
        core.require(exact(reader, padding) == b'\0' * padding, 'ARCHIVE_MEMBER_PADDING')
        consumed += 512 + member.size + padding
        verified[expected] = dict(row)
        if expected.endswith('.json'):
            metadata[expected] = b''.join(chunks)
    trailing = size - consumed
    core.require(trailing >= 1024, 'ARCHIVE_END_BLOCKS')
    while trailing:
        block = exact(reader, min(core.BLOCK, trailing)); trailing -= len(block)
        core.require(not any(block), 'ARCHIVE_TRAILING_DATA')
    core.require(reader.read(1) == b'', 'ARCHIVE_EXTRA_BYTES')
    manifest = core.validate_documents(metadata)
    core.require(all(verified[n]['sha256'] == manifest['files_sha256'][n] for n in core.CHECKPOINT_NAMES), 'RESTORED_MANIFEST_SHA')
    return verified


def verify(directory, receipt, public_meta, key, expected_source, expected_run, restore_dir=None):
    core.public_key(public_meta)  # The recorded export time, not current wall clock, binds TTL.
    core.require(receipt['native'].get('source_sha') == expected_source
                 and receipt['native'].get('workflow_run_id') == expected_run, 'EXPECTED_RUN')
    first_header, first_prefix = None, None
    # Pass1 authenticates all ciphertext without exposing or parsing plaintext.
    with PartReader(directory, receipt['parts']) as stream:
        header, prefix = envelope_header(stream, public_meta)
        core.require(header['source_sha'] == expected_source and header['workflow_run_id'] == expected_run, 'HEADER_RUN')
        plain = DecryptedReader(stream, header, prefix, key)
        while plain.read(core.BLOCK):
            pass
        core.require(plain.cipher_hash.hexdigest() == receipt['ciphertext_sha256'], 'FULL_CIPHERTEXT_SHA')
        first_header, first_prefix = header, prefix
    sink = PrivateParts(restore_dir) if restore_dir is not None else None
    try:
        with PartReader(directory, receipt['parts']) as stream:
            header, prefix = envelope_header(stream, public_meta)
            core.require(header == first_header and prefix == first_prefix, 'ENVELOPE_CHANGED')
            plain = DecryptedReader(stream, header, prefix, key, sink)
            verified = verify_tar(plain, header['files'], header['archive_bytes'])
            core.require(plain.cipher_hash.hexdigest() == receipt['ciphertext_sha256'], 'SECOND_CIPHERTEXT_SHA')
        if sink is not None:
            sink.close_part()
        result = {'schema': RESTORE_SCHEMA, 'state': 'ALL_FIXED_FILES_AUTHENTICATED_AND_HASH_VERIFIED',
                  'scope': core.scope(), 'source_sha': expected_source, 'workflow_run_id': expected_run,
                  'transfer_id': header['transfer_id'], 'ciphertext_sha256': receipt['ciphertext_sha256'],
                  'archive_sha256': plain.plain_hash.hexdigest(), 'archive_bytes': header['archive_bytes'],
                  'archive_format': 'USTAR_UNCOMPRESSED', 'files': verified,
                  'plaintext_archive_parts': sink.rows if sink else [], 'all_file_sha256_verified': True,
                  'pickle_or_model_loaded': False, 'archive_extracted': False, 'drive_copy_verified': False,
                  'gpu_restart_performed': False}
        if sink is not None:
            path = sink.directory / 'QWEN6_RESTORE_MANIFEST.json'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(core.canonical(result) + b'\n'); f.flush(); os.fsync(f.fileno())
        return result
    except BaseException:
        if sink is not None:
            sink.failure()
        raise


def verify_restore(directory, manifest, expected_source, expected_run):
    """Verify private Drive tar parts later, without the temporary RSA key."""
    core.require(manifest.get('schema') == RESTORE_SCHEMA
                 and manifest.get('state') == 'ALL_FIXED_FILES_AUTHENTICATED_AND_HASH_VERIFIED'
                 and manifest.get('scope') == core.scope()
                 and manifest.get('source_sha') == expected_source and manifest.get('workflow_run_id') == expected_run
                 and manifest.get('archive_format') == 'USTAR_UNCOMPRESSED'
                 and isinstance(manifest.get('archive_sha256'), str) and core.SHA.fullmatch(manifest['archive_sha256']),
                 'RESTORE_MANIFEST_SCOPE')
    files, rows = manifest.get('files'), manifest.get('plaintext_archive_parts')
    core.require(isinstance(files, dict) and set(files) == set(core.NAMES)
                 and isinstance(rows, list) and 1 <= len(rows) <= 13, 'RESTORE_PARTS')
    for row in files.values():
        core.require(set(row) == {'bytes', 'sha256'} and type(row['bytes']) is int and 0 < row['bytes'] <= core.MAX_TOTAL
                     and isinstance(row['sha256'], str) and core.SHA.fullmatch(row['sha256']), 'RESTORE_FILE_ROW')
    core.require(sum(row['bytes'] for row in files.values()) <= core.MAX_TOTAL
                 and sum(files[n]['bytes'] for n in core.CHECKPOINT_NAMES) == core.CHECKPOINT_BYTES,
                 'RESTORE_TOTAL_BOUND')
    for i, row in enumerate(rows):
        core.require(set(row) == {'name', 'bytes', 'sha256'}
                     and row['name'] == f'qwen6-restore.tar.part{i:03d}'
                     and type(row['bytes']) is int and 0 < row['bytes'] <= core.PART_BYTES
                     and isinstance(row['sha256'], str) and core.SHA.fullmatch(row['sha256'])
                     and (i == len(rows) - 1 or row['bytes'] == core.PART_BYTES), 'RESTORE_PART_ROW')
    core.require(sum(row['bytes'] for row in rows) == manifest.get('archive_bytes') == core.archive_size(files), 'RESTORE_ARCHIVE_SIZE')
    h = hashlib.sha256()
    with PartReader(directory, rows) as stream:
        class Reader:
            def read(self, count):
                raw = stream.read(count); h.update(raw); return raw
        verified = verify_tar(Reader(), files, manifest['archive_bytes'])
    core.require(h.hexdigest() == manifest['archive_sha256'], 'RESTORED_ARCHIVE_SHA')
    return {'schema': 'NOX_QWEN6_PRIVATE_ARCHIVE_READBACK_V1', 'state': 'ALL_FIXED_FILES_HASH_VERIFIED_WITHOUT_TRANSFER_KEY',
            'source_sha': expected_source, 'workflow_run_id': expected_run, 'verified_files': len(verified),
            'archive_bytes': manifest['archive_bytes'], 'archive_sha256': h.hexdigest(),
            'all_file_sha256_verified': True, 'private_key_required': False,
            'drive_copy_verified': False, 'gpu_restart_performed': False}


def read_small(path):
    fd, info = core.open_regular(Path(path).absolute(), core.MAX_JSON)
    try:
        raw = os.read(fd, core.MAX_JSON + 1)
        core.checked_fd(fd, Path(path).absolute(), info)
        return raw
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--parts-dir', required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--receipt'); choice.add_argument('--restore-manifest')
    p.add_argument('--public-meta'); p.add_argument('--private-key')
    p.add_argument('--expected-source', required=True); p.add_argument('--expected-run', required=True)
    p.add_argument('--restore-dir')
    args = p.parse_args()
    try:
        if args.restore_manifest:
            core.require(args.restore_dir is None and args.private_key is None and args.public_meta is None, 'READBACK_ARGUMENT_SCOPE')
            result = verify_restore(args.parts_dir, core.document(read_small(args.restore_manifest)), args.expected_source, args.expected_run)
        else:
            core.require(args.public_meta is not None and args.private_key is not None, 'DECRYPT_ARGUMENT_SCOPE')
            receipt = receipt_document(read_small(args.receipt))
            public = core.document(read_small(args.public_meta))
            key = private_key(args.private_key, public)
            result = verify(args.parts_dir, receipt, public, key, args.expected_source, args.expected_run, args.restore_dir)
        print(core.canonical({k: result[k] for k in ('schema', 'state', 'source_sha', 'workflow_run_id',
                                                   'archive_sha256', 'archive_bytes', 'all_file_sha256_verified',
                                                   'drive_copy_verified', 'gpu_restart_performed')}).decode())
        return 0
    except BaseException as exc:
        reason = str(exc)
        if not core.re.fullmatch('HOLD_QWEN6_BACKUP_[A-Z0-9_]{1,100}', reason):
            reason = 'HOLD_QWEN6_BACKUP_' + type(exc).__name__.upper()
        print(reason); return 2


if __name__ == '__main__':
    raise SystemExit(main())
