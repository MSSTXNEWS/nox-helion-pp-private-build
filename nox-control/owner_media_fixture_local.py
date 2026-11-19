#!/usr/bin/env python3
"""Local-only private key creation and quiet-stdin synthetic media recovery."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time

sys.dont_write_bytecode = True
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import owner_media_fixture_transport as transport


def private_directory(path, *, create=False):
    path = transport.plain(path)
    if create:
        path.mkdir(mode=0o700, exist_ok=False)
    info = path.stat()
    transport.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                      'HOLD_MEDIA_FIXTURE_LOCAL_DIRECTORY')
    return path


def write_new(path, raw):
    path = transport.plain(path); private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def prepare(directory):
    directory = private_directory(directory, create=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    raw = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    public = private.public_key()
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    started = int(time.time())
    metadata = {'schema': 'NOX_MEDIA_REVIEW_PUBLIC_KEY_V1', 'key_id': transport.digest(der),
                'public_key_pem': pem.decode('ascii'), 'transfer_id': secrets.token_hex(16),
                'created_at': started, 'expires_at': started+transport.MAX_TTL,
                'manifest_sha256': transport.manifest_sha()}
    transport.public_key_metadata(metadata)
    write_new(directory/'private.pem', raw)
    public_raw = transport.canonical(metadata)+b'\n'
    write_new(directory/'public_metadata.json', public_raw)
    return {'schema': 'NOX_MEDIA_REVIEW_LOCAL_PREPARE_V1', 'key_id': metadata['key_id'],
            'public_metadata_path': str(directory/'public_metadata.json'),
            'public_metadata_sha256': transport.digest(public_raw), 'expires_at': metadata['expires_at'],
            'manifest_sha256': metadata['manifest_sha256']}


def recover(directory, raw, request, source):
    directory = private_directory(directory)
    private_pem = transport.read_regular(directory/'private.pem', 8192, private=True)
    public = transport.decode_json(transport.read_regular(directory/'public_metadata.json', 8192, private=True))
    rows = transport.decode_json(raw)
    # All envelope, AEAD and BOTH final file hashes pass before any plaintext
    # output is created. Exact filenames come only from the reviewed manifest.
    files, proof = transport.decrypt(rows, private_pem, public, request, source)
    destination = private_directory(directory/'recovered', create=True)
    for name, data in files:
        transport.require(name in {row['filename'] for row in transport.FILES}, 'HOLD_MEDIA_FIXTURE_OUTPUT_NAME')
        write_new(destination/name, data)
    write_new(destination/'receipt.json', transport.canonical(proof)+b'\n')
    for row in transport.FILES:
        value = transport.read_regular(destination/row['filename'], row['bytes'], private=True)
        transport.require(transport.digest(value) == row['sha256'], 'HOLD_MEDIA_FIXTURE_LOCAL_READBACK')
    return {'schema': 'NOX_MEDIA_REVIEW_LOCAL_READY_V1', 'state': 'FULL_SHA_VERIFIED_LOCAL_FILES',
            'envelope_sha256': proof['envelope_sha256'], 'visual_review_completed': False,
            'files': [{'filename': row['filename'], 'path': str(destination/row['filename']),
                       'bytes': row['bytes'], 'sha256': row['sha256']} for row in transport.FILES]}


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    generate = commands.add_parser('prepare'); generate.add_argument('--directory', required=True)
    consume = commands.add_parser('decrypt'); consume.add_argument('--directory', required=True)
    consume.add_argument('--request', required=True); consume.add_argument('--source', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.directory)
    else:
        raw = sys.stdin.buffer.read(transport.MAX_INPUT+1)
        transport.require(len(raw) <= transport.MAX_INPUT, 'HOLD_MEDIA_FIXTURE_INPUT_SIZE')
        result = recover(args.directory, raw, args.request, args.source)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        code = str(exc) if isinstance(exc, transport.TransportHold) else 'HOLD_MEDIA_FIXTURE_LOCAL_'+type(exc).__name__.upper()
        print(json.dumps({'state': 'HOLD', 'code': code}), file=sys.stderr)
        raise SystemExit(2)
