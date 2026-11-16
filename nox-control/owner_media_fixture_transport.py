"""Memory-only authenticated transport of two fixed synthetic QA artifacts."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FILES = (
    {'kind': 'image', 'filename': 'nox-qa-image.png', 'bytes': 291929,
     'sha256': '996e8f1aa156c82768ad3496508440be1a2c96a49fb285943904f12c79295ac2',
     'native_path': '/root/nox/media/outputs/nox/42d0a67a275d41719fcf2e8768f2975d/image_00001_.png'},
    {'kind': 'video', 'filename': 'nox-qa-video.webm', 'bytes': 29349,
     'sha256': '8f00e2b96cb170342af8a7cbd65d9ed938849c0a7dd7172d0f9c9dc56d86b135',
     'native_path': '/root/nox/media/outputs/nox/69c88f3914c77079db0f31af39c3b1a2/video_00001_.webm'},
)
ACCEPTED_RECEIPT_SHA = 'f224353628c1aef7ac5ff70c9d74a0f4a1b82569bccb70ab59faf234bdbe4fdb'
INSTANCE_ID = 60509551
ALGORITHM = 'RSA4096-OAEP-SHA256+A256GCM'
OAEP_LABEL = b'NOX_SYNTHETIC_MEDIA_REVIEW_V1'
CHUNK_CHARS = 60000  # JSON overhead stays well below an 80KB public log line.
MAX_INPUT = 700000
MAX_TTL = 3600


class TransportHold(RuntimeError):
    pass


def require(condition, code='HOLD_MEDIA_FIXTURE_TRANSPORT'):
    if not condition:
        raise TransportHold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'HOLD_MEDIA_FIXTURE_DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def decode_json(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_INPUT, 'HOLD_MEDIA_FIXTURE_INPUT_SIZE')
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(TransportHold('HOLD_MEDIA_FIXTURE_JSON_NUMBER')))


def public_files():
    return [{key: row[key] for key in ('kind', 'filename', 'bytes', 'sha256')} for row in FILES]


def manifest():
    return {'schema': 'NOX_SYNTHETIC_MEDIA_MANIFEST_V1', 'instance_id': INSTANCE_ID,
            'accepted_receipt_sha256': ACCEPTED_RECEIPT_SHA, 'files': public_files()}


def manifest_sha():
    return digest(canonical(manifest()))


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and not any(item.is_symlink() for item in (path, *path.parents)), 'HOLD_MEDIA_FIXTURE_PATH')
    return path


def read_regular(path, maximum, *, private=False):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & (0o077 if private else 0o022)
                and before.st_nlink == 1 and 0 <= before.st_size <= maximum, 'HOLD_MEDIA_FIXTURE_FILE_SCOPE')
        parts = []; count = 0
        while True:
            block = os.read(fd, min(65536, maximum+1-count))
            if not block:
                break
            count += len(block); require(count <= maximum, 'HOLD_MEDIA_FIXTURE_FILE_SIZE'); parts.append(block)
        after = os.fstat(fd); named = path.stat(follow_symlinks=False)
        for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            require(getattr(before, key) == getattr(after, key) == getattr(named, key), 'HOLD_MEDIA_FIXTURE_FILE_CHANGED')
        require(count == before.st_size, 'HOLD_MEDIA_FIXTURE_FILE_SIZE')
        return b''.join(parts)
    finally:
        os.close(fd)


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def unb64(value, maximum):
    require(isinstance(value, str) and len(value) <= ((maximum+2)//3)*4, 'HOLD_MEDIA_FIXTURE_BASE64_SIZE')
    raw = base64.b64decode(value, validate=True)
    require(len(raw) <= maximum and b64(raw) == value, 'HOLD_MEDIA_FIXTURE_BASE64')
    return raw


def public_key_metadata(value, *, now=None):
    now = int(time.time()) if now is None else now
    require(isinstance(value, dict) and set(value) == {'schema', 'key_id', 'public_key_pem', 'transfer_id',
            'created_at', 'expires_at', 'manifest_sha256'}, 'HOLD_MEDIA_FIXTURE_KEY_METADATA')
    require(value['schema'] == 'NOX_MEDIA_REVIEW_PUBLIC_KEY_V1' and value['manifest_sha256'] == manifest_sha()
            and isinstance(value['transfer_id'], str) and re.fullmatch('[a-f0-9]{32}', value['transfer_id'])
            and type(value['created_at']) is int and type(value['expires_at']) is int
            and 0 < value['expires_at']-value['created_at'] <= MAX_TTL
            and value['created_at']-5 <= now < value['expires_at'], 'HOLD_MEDIA_FIXTURE_KEY_CONTEXT')
    pem = value['public_key_pem']
    require(isinstance(pem, str) and pem.startswith('-----BEGIN PUBLIC KEY-----\n') and len(pem) <= 1200,
            'HOLD_MEDIA_FIXTURE_PUBLIC_KEY')
    key = serialization.load_pem_public_key(pem.encode('ascii'))
    require(isinstance(key, rsa.RSAPublicKey) and key.key_size == 4096 and key.public_numbers().e == 65537,
            'HOLD_MEDIA_FIXTURE_PUBLIC_KEY')
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    require(value['key_id'] == digest(der), 'HOLD_MEDIA_FIXTURE_KEY_ID')
    return key


def owner_context(request, source):
    require(isinstance(request, str) and re.fullmatch('[0-9]{1,24}', request)
            and isinstance(source, str) and re.fullmatch('[a-f0-9]{40}', source), 'HOLD_MEDIA_FIXTURE_OWNER_CONTEXT')
    return {'request': request, 'source_sha': source}


def read_native_files():
    result = []
    for row in FILES:
        raw = read_regular(row['native_path'], row['bytes'])
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'HOLD_MEDIA_FIXTURE_NATIVE_SHA')
        result.append(raw)
    return result


def seal(public_metadata, request, source):
    """Native entry: only the two immutable approved paths may be read."""
    public = public_key_metadata(public_metadata)
    context = owner_context(request, source)
    raw = b''.join(read_native_files())
    cipher_bytes = len(raw)+16
    cipher_chars = ((cipher_bytes+2)//3)*4
    aad = {'schema': 'NOX_MEDIA_REVIEW_AAD_V1', 'algorithm': ALGORITHM, 'manifest': manifest(),
           'manifest_sha256': manifest_sha(), 'key_id': public_metadata['key_id'],
           'transfer_id': public_metadata['transfer_id'], 'created_at': int(time.time()),
           'expires_at': public_metadata['expires_at'], 'context': context, 'plaintext_bytes': len(raw),
           'chunk_chars': CHUNK_CHARS, 'chunk_count': (cipher_chars+CHUNK_CHARS-1)//CHUNK_CHARS,
           'ciphertext_bytes': cipher_bytes}
    aes = AESGCM.generate_key(bit_length=256); nonce = os.urandom(12)
    wrapped = public.encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                              algorithm=hashes.SHA256(), label=OAEP_LABEL))
    cipher = AESGCM(aes).encrypt(nonce, raw, canonical(aad))
    envelope = {'schema': 'NOX_MEDIA_REVIEW_ENVELOPE_V1', 'aad': aad, 'wrapped_key': b64(wrapped),
                'nonce': b64(nonce), 'ciphertext': b64(cipher), 'ciphertext_bytes': len(cipher),
                'ciphertext_sha256': digest(cipher)}
    encoded = envelope['ciphertext']
    chunks = [encoded[i:i+CHUNK_CHARS] for i in range(0, len(encoded), CHUNK_CHARS)]
    sha = digest(canonical(envelope))
    header = {'schema': 'NOX_MEDIA_REVIEW_TRANSFER_V1', 'envelope_sha256': sha,
              'chunks': len(chunks), 'chunk_chars': CHUNK_CHARS, 'ciphertext_chars': len(encoded),
              'metadata': {key: value for key, value in envelope.items() if key != 'ciphertext'}}
    rows = [{'kind': 'media_fixture_ciphertext_header', 'data': header}]
    rows += [{'kind': 'media_fixture_ciphertext_chunk', 'data': {'envelope_sha256': sha, 'index': i,
                                                               'chunks': len(chunks), 'ciphertext': chunk}}
             for i, chunk in enumerate(chunks)]
    require(all(len(canonical(row)) < 79000 for row in rows), 'HOLD_MEDIA_FIXTURE_LOG_LINE_SIZE')
    return rows


def assemble(rows):
    require(isinstance(rows, list) and 2 <= len(rows) <= 20, 'HOLD_MEDIA_FIXTURE_CHUNK_COUNT')
    headers = [row['data'] for row in rows if isinstance(row, dict) and set(row) == {'kind', 'data'}
               and row['kind'] == 'media_fixture_ciphertext_header']
    require(len(headers) == 1, 'HOLD_MEDIA_FIXTURE_SINGLE_HEADER')
    header = headers[0]
    require(isinstance(header, dict) and set(header) == {'schema', 'envelope_sha256', 'chunks', 'chunk_chars',
            'ciphertext_chars', 'metadata'} and header['schema'] == 'NOX_MEDIA_REVIEW_TRANSFER_V1'
            and type(header['chunks']) is int and 1 <= header['chunks'] <= 16
            and header['chunk_chars'] == CHUNK_CHARS and type(header['ciphertext_chars']) is int
            and 0 < header['ciphertext_chars'] <= MAX_INPUT and len(rows) == header['chunks']+1,
            'HOLD_MEDIA_FIXTURE_HEADER')
    chunks = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'kind', 'data'}, 'HOLD_MEDIA_FIXTURE_CHUNK_SCHEMA')
        if row['kind'] == 'media_fixture_ciphertext_header':
            continue
        part = row['data']
        require(row['kind'] == 'media_fixture_ciphertext_chunk' and isinstance(part, dict)
                and set(part) == {'envelope_sha256', 'index', 'chunks', 'ciphertext'}
                and part['envelope_sha256'] == header['envelope_sha256'] and part['chunks'] == header['chunks']
                and type(part['index']) is int and 0 <= part['index'] < header['chunks'] and part['index'] not in chunks
                and isinstance(part['ciphertext'], str), 'HOLD_MEDIA_FIXTURE_CHUNK_SCHEMA')
        expected = CHUNK_CHARS if part['index'] < header['chunks']-1 else header['ciphertext_chars']-CHUNK_CHARS*(header['chunks']-1)
        require(0 < expected <= CHUNK_CHARS and len(part['ciphertext']) == expected, 'HOLD_MEDIA_FIXTURE_CHUNK_SIZE')
        chunks[part['index']] = part['ciphertext']
    metadata = header['metadata']
    require(isinstance(metadata, dict) and set(metadata) == {'schema', 'aad', 'wrapped_key', 'nonce',
            'ciphertext_bytes', 'ciphertext_sha256'}, 'HOLD_MEDIA_FIXTURE_ENVELOPE_SCHEMA')
    envelope = dict(metadata, ciphertext=''.join(chunks[i] for i in range(header['chunks'])))
    require(digest(canonical(envelope)) == header['envelope_sha256'], 'HOLD_MEDIA_FIXTURE_ENVELOPE_SHA')
    return envelope, header['envelope_sha256']


def decrypt(rows, private_pem, public_metadata, request, source):
    public_key_metadata(public_metadata)
    context = owner_context(request, source)
    envelope, outer_sha = assemble(rows)
    aad = envelope['aad']
    total = sum(row['bytes'] for row in FILES)
    expected_chunks = ((((total+16+2)//3)*4)+CHUNK_CHARS-1)//CHUNK_CHARS
    require(envelope['schema'] == 'NOX_MEDIA_REVIEW_ENVELOPE_V1' and isinstance(aad, dict)
            and set(aad) == {'schema', 'algorithm', 'manifest', 'manifest_sha256', 'key_id', 'transfer_id',
                            'created_at', 'expires_at', 'context', 'plaintext_bytes',
                            'chunk_chars', 'chunk_count', 'ciphertext_bytes'}
            and aad['schema'] == 'NOX_MEDIA_REVIEW_AAD_V1' and aad['algorithm'] == ALGORITHM
            and aad['manifest'] == manifest() and aad['manifest_sha256'] == manifest_sha()
            and aad['key_id'] == public_metadata['key_id'] and aad['transfer_id'] == public_metadata['transfer_id']
            and aad['expires_at'] == public_metadata['expires_at'] and aad['context'] == context
            and type(aad['created_at']) is int and public_metadata['created_at']-5 <= aad['created_at'] <= int(time.time())+5
            and aad['created_at'] < aad['expires_at'] and aad['plaintext_bytes'] == total
            and aad['chunk_chars'] == CHUNK_CHARS and aad['chunk_count'] == expected_chunks
            and aad['ciphertext_bytes'] == total+16
            and envelope['ciphertext_bytes'] == total+16, 'HOLD_MEDIA_FIXTURE_AAD')
    private = serialization.load_pem_private_key(private_pem, password=None)
    require(isinstance(private, rsa.RSAPrivateKey) and private.key_size == 4096, 'HOLD_MEDIA_FIXTURE_PRIVATE_KEY')
    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    require(digest(der) == public_metadata['key_id'], 'HOLD_MEDIA_FIXTURE_PRIVATE_KEY')
    cipher = unb64(envelope['ciphertext'], total+16)
    require(len(cipher) == total+16 and digest(cipher) == envelope['ciphertext_sha256'], 'HOLD_MEDIA_FIXTURE_CIPHERTEXT_SHA')
    wrapped = unb64(envelope['wrapped_key'], 512); nonce = unb64(envelope['nonce'], 12)
    require(len(wrapped) == 512 and len(nonce) == 12, 'HOLD_MEDIA_FIXTURE_CRYPTO_SIZE')
    aes = private.decrypt(wrapped, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                              algorithm=hashes.SHA256(), label=OAEP_LABEL))
    require(len(aes) == 32, 'HOLD_MEDIA_FIXTURE_CRYPTO_KEY_SIZE')
    raw = AESGCM(aes).decrypt(nonce, cipher, canonical(aad))
    require(len(raw) == total, 'HOLD_MEDIA_FIXTURE_PLAINTEXT_SIZE')
    offset = 0; files = []
    for row in FILES:
        item = raw[offset:offset+row['bytes']]; offset += row['bytes']
        require(digest(item) == row['sha256'], 'HOLD_MEDIA_FIXTURE_RECOVERED_SHA')
        files.append((row['filename'], item))
    return files, {'schema': 'NOX_MEDIA_REVIEW_LOCAL_RECEIPT_V1', 'envelope_sha256': outer_sha,
                   'manifest_sha256': manifest_sha(), 'key_id': public_metadata['key_id'],
                   'context': context, 'files': public_files(), 'visual_review_completed': False}
