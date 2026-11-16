#!/usr/bin/env python3
"""Prepare a native, private transport key for the approved Drive RAM restore.

This entry emits only a public key and measured crypto capabilities. It neither
contacts Drive nor downloads weights, installs packages, changes access, or
touches the trainer. The private RSA key never leaves this host.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path('/root/nox')
STATE = ROOT / 'state/owner_drive_ram'
INSTANCE_ID = 60509551
MANIFEST_SHA256 = '73b8fa9336faabad2c2b1d197d6751d79b065158c7f0700e46155f371b74c816'
KEY_TTL_SECONDS = 3600
MAX_FILE = 32768
CRYPTO_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
              'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
              'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1'}


def fail(code):
    raise RuntimeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def plain(value):
    path = Path(os.path.abspath(value))
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            fail('HOLD_DRIVE_SYMLINK')
    return path


def private_directory(path):
    path = plain(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        fail('HOLD_DRIVE_PRIVATE_DIRECTORY')
    return path


def read_private(path, limit=MAX_FILE):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > limit):
            fail('HOLD_DRIVE_PRIVATE_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            value = source.read(limit + 1)
        if len(value) > limit:
            fail('HOLD_DRIVE_FILE_LIMIT')
        return value
    finally:
        os.close(fd)


def atomic_private(path, value):
    path = plain(path)
    private_directory(path.parent)
    if path.exists():
        read_private(path)
    fd, temp = tempfile.mkstemp(prefix='.drive-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def state_lock(name='prepare.lock'):
    private_directory(STATE)
    fd = os.open(plain(STATE / name), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            fail('HOLD_DRIVE_LOCK_FILE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('HOLD_DRIVE_OPERATION_BUSY')
        yield
    finally:
        os.close(fd)


CRYPTO_PROBE = r'''
import json,os,platform
try:
 import cryptography
 from cryptography.hazmat.backends import default_backend
 from cryptography.hazmat.primitives import hashes
 from cryptography.hazmat.primitives.asymmetric import padding,rsa
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12);aad=b'NOX_DRIVE_CAPABILITY_V1'
 aes=AESGCM(key);assert aes.decrypt(nonce,aes.encrypt(nonce,b'public probe',aad),aad)==b'public probe'
 private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 pad=padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)
 assert private.decrypt(private.public_key().encrypt(key,pad),pad)==key
 print(json.dumps({'available':True,'python_version':platform.python_version(),
 'cryptography_version':cryptography.__version__,'openssl_version':default_backend().openssl_version_text(),
 'aes_256_gcm_roundtrip':True,'rsa_oaep_sha256_roundtrip':True}))
except Exception as exc:
 print(json.dumps({'available':False,'error_class':type(exc).__name__}))
'''


CRYPTO_KEY = r'''
import hashlib,json,os,stat,sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
try:
 path=sys.argv[1];mode=sys.argv[2]
 if mode=='new':
  key=rsa.generate_private_key(public_exponent=65537,key_size=4096)
  raw=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 else:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(fd,'rb') as stream:
   info=os.fstat(stream.fileno())
   if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077 or info.st_nlink!=1 or info.st_size>16384:
    raise RuntimeError('PRIVATE_KEY_SCOPE')
   raw=stream.read(16385)
  key=serialization.load_pem_private_key(raw,password=None)
 if not isinstance(key,rsa.RSAPrivateKey) or key.key_size!=4096:raise RuntimeError('KEY_TYPE')
 public=key.public_key()
 der=public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 pem=public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
 print(json.dumps({'key_id':hashlib.sha256(der).hexdigest(),'public_key_pem':pem,'rsa_bits':4096}))
except Exception as exc:
 print(json.dumps({'error_class':type(exc).__name__}));raise SystemExit(2)
'''


def crypto_command(python, script, arguments=(), timeout=30, input_data=None):
    try:
        result = subprocess.run([str(python), '-I', '-c', script, *map(str, arguments)],
                                input=input_data, capture_output=True, timeout=timeout, env=CRYPTO_ENV)
    except (OSError, subprocess.TimeoutExpired):
        fail('HOLD_DRIVE_CRYPTO_SUBPROCESS')
    if result.returncode or len(result.stdout) > MAX_FILE:
        fail('HOLD_DRIVE_CRYPTO_RESULT')
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        fail('HOLD_DRIVE_CRYPTO_JSON')
    if not isinstance(value, dict):
        fail('HOLD_DRIVE_CRYPTO_SCHEMA')
    return value


def candidate_pythons():
    return list(dict.fromkeys(str(path) for path in
                             (Path(sys.executable), Path('/usr/bin/python3'), Path('/root/venv_volta/bin/python'))
                             if path.is_file()))


def context():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch(r'[0-9]{1,24}', request) or not re.fullmatch(r'[0-9a-f]{40}', source):
        fail('HOLD_OWNER_CONTEXT')
    return request, source


def prepare():
    request, source = context()
    with state_lock():
        private_directory(STATE / 'keys')
        folder = private_directory(STATE / 'keys' / request)
        key_path, metadata_path = folder / 'private_key.pem', folder / 'public_metadata.json'
        if metadata_path.exists():
            metadata = json.loads(read_private(metadata_path))
            if (metadata.get('schema') != 'NOX_DRIVE_RAM_PUBLIC_KEY_V1'
                    or metadata.get('request') != request or metadata.get('source_sha') != source
                    or metadata.get('manifest_sha256') != MANIFEST_SHA256
                    or metadata.get('instance_id') != INSTANCE_ID
                    or metadata.get('expires_at', 0) <= time.time()
                    or metadata.get('python') not in candidate_pythons()):
                fail('HOLD_DRIVE_EXISTING_KEY_CONTEXT')
            checked = crypto_command(metadata['python'], CRYPTO_KEY, (key_path, 'read'))
            if any(metadata.get(name) != checked.get(name) for name in ('key_id', 'public_key_pem', 'rsa_bits')):
                fail('HOLD_DRIVE_KEY_PAIR_MISMATCH')
            return metadata
        if key_path.exists():
            fail('HOLD_DRIVE_ORPHAN_PRIVATE_KEY')
        probes = []
        selected = None
        for python in candidate_pythons():
            try:
                probe = crypto_command(python, CRYPTO_PROBE)
            except RuntimeError:
                probe = {'available': False, 'error_class': 'ProbeFailed'}
            probes.append({'python': python, **probe})
            if (probe.get('available') is True and probe.get('aes_256_gcm_roundtrip') is True
                    and probe.get('rsa_oaep_sha256_roundtrip') is True):
                selected = python, probe
                break
        if selected is None:
            return {'schema': 'NOX_DRIVE_RAM_PUBLIC_KEY_V1', 'state': 'HOLD_CRYPTO_UNAVAILABLE',
                    'request': request, 'source_sha': source, 'capabilities': probes,
                    'private_key_exported': False, 'packages_installed': False}
        python, capability = selected
        public = crypto_command(python, CRYPTO_KEY, (key_path, 'new'), timeout=60)
        read_private(key_path, 16384)
        now = int(time.time())
        metadata = {'schema': 'NOX_DRIVE_RAM_PUBLIC_KEY_V1', 'state': 'PUBLIC_KEY_READY',
                    'instance_id': INSTANCE_ID, 'manifest_sha256': MANIFEST_SHA256,
                    'request': request, 'source_sha': source, 'python': python,
                    'prepared_at': now, 'expires_at': now + KEY_TTL_SECONDS,
                    'capability': capability, **public, 'private_key_exported': False,
                    'packages_installed': False, 'weight_downloads_started': False}
        atomic_private(metadata_path, canonical(metadata) + b'\n')
        return metadata


def main():
    try:
        result = prepare()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_ram_public_key', 'data': result},
                                             separators=(',', ':')), flush=True)
        if result.get('state') == 'PUBLIC_KEY_READY':
            print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
            return 0
        return 2
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r'HOLD_[A-Z0-9_]+', code):
            code = 'HOLD_DRIVE_PREPARE'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_ram_public_key',
                                             'data': {'state': 'HOLD', 'error': code}}), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
