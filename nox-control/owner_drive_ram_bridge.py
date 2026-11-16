#!/usr/bin/env python3
"""Sealed, exact-asset Drive download into native RAM; never a model merge.

Public input is ciphertext and a manifest containing only Drive-ID hashes.
The native RSA private key and decrypted, short-lived URLs remain private.
One joined partial per adapter avoids a second copy of the twelve pieces.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import secrets
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
import urllib.parse

PREPARE_PATH = Path('/root/nox/scripts/owner_drive_ram_prepare.py')
MANIFEST_PATH = Path('/root/nox/scripts/owner_drive_ram_assets.json')
PREPARE_SHA256 = 'dadd732db4db231be625a72606f85509c1c9b3fc519c1f71d7a11c99ca48ce43'
MANIFEST_FILE_SHA256 = '1910d8b09393f13af1749759509de5cc44f9347faf9b50d2c321377fc267b199'
MANIFEST_SHA256 = '73b8fa9336faabad2c2b1d197d6751d79b065158c7f0700e46155f371b74c816'
ROOT = Path('/root/nox')
STATE = ROOT / 'state/owner_drive_ram'
DESTINATION = Path('/dev/shm/nox_drive/3t724u')
INSTANCE_ID = 60509551
GIB = 1024 ** 3
BLOCK = 1024 ** 2
TOTAL_BYTES = 920362008
SHM_RESERVE = 3 * GIB
CGROUP_RESERVE = 32 * GIB
IO_MARGIN = 32 * BLOCK
MAX_ENVELOPE_BYTES = 256 * 1024
MAX_URL_BYTES = 12000
MAX_ENVELOPE_TTL = 300
MAX_TRANSFERS = 3
ALLOWED_HOST = re.compile(r'sdmntpr[a-z0-9]+\.oaiusercontent\.com\Z', re.ASCII)
ALLOWED_PATH = re.compile(r'/files/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/raw\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
LOCK = threading.Lock()
EMIT_LOCK = threading.Lock()
MEDIA_ASSETS = (
    ('checkpoints', 'sdxl_lightning_4step.safetensors', 6938040682),
    ('diffusion_models', 'wan2.1_t2v_1.3B_fp16.safetensors', 2838303560),
    ('text_encoders', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 6735906897),
    ('vae', 'wan_2.1_vae.safetensors', 253815318),
)


def fail(code):
    raise RuntimeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def safe_code(exc):
    value = str(exc)
    return value if re.fullmatch(r'HOLD_[A-Z0-9_]+', value) else 'HOLD_DRIVE_TRANSFER'


def global_stop():
    return any(path.exists() or path.is_symlink() for path in
               [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop',
                                         'program/STOP', 'state/STOP', 'state/DRIVE_STOP.flag')]
               + [Path('/workspace/NOX_STOP')])


def require_running():
    if global_stop():
        fail('HOLD_DRIVE_OWNER_STOP')


def emit(phase, **values):
    with EMIT_LOCK:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_ram_transfer',
                                             'data': {'phase': phase, **values}}, separators=(',', ':')), flush=True)


def plain(path):
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            fail('HOLD_DRIVE_SYMLINK')
    return path


def read_regular(path, limit, private=False):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_size > limit or info.st_mode & (0o077 if private else 0o022)):
            fail('HOLD_DRIVE_FILE_SCOPE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            value = stream.read(limit + 1)
        if len(value) > limit:
            fail('HOLD_DRIVE_FILE_LIMIT')
        return value
    finally:
        os.close(fd)


def load_prepare():
    source = read_regular(PREPARE_PATH, 40000)
    if hashlib.sha256(source).hexdigest() != PREPARE_SHA256:
        fail('HOLD_DRIVE_PREPARE_SOURCE_PIN')
    # Execute the exact bytes just hashed; an import loader could reopen a
    # changed pathname between verification and execution.
    spec = importlib.util.spec_from_loader('nox_owner_drive_ram_prepare_pinned', loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(PREPARE_PATH)
    exec(compile(source, str(PREPARE_PATH), 'exec'), module.__dict__)
    return module


def load_manifest():
    raw = read_regular(MANIFEST_PATH, 16384)
    if hashlib.sha256(raw).hexdigest() != MANIFEST_FILE_SHA256:
        fail('HOLD_DRIVE_MANIFEST_FILE_PIN')
    result = json.loads(raw)
    if hashlib.sha256(canonical(result)).hexdigest() != MANIFEST_SHA256:
        fail('HOLD_DRIVE_MANIFEST_PIN')
    if (result.get('schema') != 'NOX_DRIVE_RAM_APPROVED_ASSETS_V1'
            or result.get('instance_id') != INSTANCE_ID or result.get('collection') != '3t724u'
            or len(result.get('assets', [])) != 3
            or sum(asset['bytes'] for asset in result['assets']) != TOTAL_BYTES):
        fail('HOLD_DRIVE_MANIFEST_SCHEMA')
    return result


def validate_url(url):
    if (not isinstance(url, str) or not 1 <= len(url) <= MAX_URL_BYTES
            or not url.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in url)
            or '\\' in url or '#' in url):
        fail('HOLD_DRIVE_URL_FORMAT')
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.username is None and parsed.password is None
                 and parsed.port in (None, 443) and ALLOWED_HOST.fullmatch(parsed.hostname or '')
                 and ALLOWED_PATH.fullmatch(parsed.path))
    except ValueError:
        valid = False
    if not valid:
        fail('HOLD_DRIVE_URL_SCOPE')
    return parsed


def validate_links(links, manifest):
    expected = {part['drive_id_sha256'] for asset in manifest['assets'] for part in asset['parts']}
    if not isinstance(links, list) or len(links) != len(expected):
        fail('HOLD_DRIVE_LINK_COUNT')
    mapped = {}
    for row in links:
        if not isinstance(row, dict) or set(row) != {'drive_id', 'url'}:
            fail('HOLD_DRIVE_LINK_SCHEMA')
        drive_id = row['drive_id']
        if not isinstance(drive_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', drive_id):
            fail('HOLD_DRIVE_ID_FORMAT')
        digest = hashlib.sha256(drive_id.encode()).hexdigest()
        if digest not in expected or digest in mapped:
            fail('HOLD_DRIVE_ID_NOT_APPROVED')
        validate_url(row['url'])
        mapped[digest] = row['url']
    return mapped


def b64(value, length=None, maximum=MAX_ENVELOPE_BYTES):
    if not isinstance(value, str) or len(value) > 4 * ((maximum + 2) // 3):
        fail('HOLD_DRIVE_BASE64_LIMIT')
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        fail('HOLD_DRIVE_BASE64')
    if len(result) > maximum or (length is not None and len(result) != length):
        fail('HOLD_DRIVE_CRYPTO_LENGTH')
    return result


def validate_envelope(envelope, metadata, now=None):
    now = time.time() if now is None else now
    if not isinstance(envelope, dict) or set(envelope) != {'schema', 'aad', 'wrapped_key', 'nonce', 'ciphertext'}:
        fail('HOLD_DRIVE_ENVELOPE_SCHEMA')
    if envelope['schema'] != 'NOX_DRIVE_RAM_ENVELOPE_V1' or len(canonical(envelope)) > MAX_ENVELOPE_BYTES:
        fail('HOLD_DRIVE_ENVELOPE_LIMIT')
    aad = envelope['aad']
    fields = {'schema', 'instance_id', 'manifest_sha256', 'key_id', 'key_request', 'key_source_sha',
              'envelope_id', 'issued_at', 'expires_at'}
    if not isinstance(aad, dict) or set(aad) != fields:
        fail('HOLD_DRIVE_AAD_SCHEMA')
    if (aad['schema'] != 'NOX_DRIVE_RAM_AAD_V1' or aad['instance_id'] != INSTANCE_ID
            or aad['manifest_sha256'] != MANIFEST_SHA256
            or aad['key_id'] != metadata.get('key_id') or not SHA.fullmatch(aad['key_id'])
            or aad['key_request'] != metadata.get('request')
            or aad['key_source_sha'] != metadata.get('source_sha')
            or not isinstance(aad['envelope_id'], str) or not re.fullmatch('[a-f0-9]{32}', aad['envelope_id'])):
        fail('HOLD_DRIVE_AAD_BINDING')
    issued, expires = aad['issued_at'], aad['expires_at']
    if (type(issued) is not int or type(expires) is not int
            or not 0 < expires - issued <= MAX_ENVELOPE_TTL or issued > now + 15 or expires <= now
            or issued < metadata.get('prepared_at', now) - 15 or expires > metadata.get('expires_at', 0)):
        fail('HOLD_DRIVE_ENVELOPE_EXPIRED')
    if (metadata.get('schema') != 'NOX_DRIVE_RAM_PUBLIC_KEY_V1' or metadata.get('state') != 'PUBLIC_KEY_READY'
            or metadata.get('instance_id') != INSTANCE_ID or metadata.get('manifest_sha256') != MANIFEST_SHA256):
        fail('HOLD_DRIVE_KEY_METADATA')
    b64(envelope['wrapped_key'], 512)
    b64(envelope['nonce'], 12)
    if len(b64(envelope['ciphertext'])) < 16:
        fail('HOLD_DRIVE_CIPHERTEXT_LENGTH')
    return aad


DECRYPT = r'''
import base64,hashlib,json,os,resource,stat,sys
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
try:
 from cryptography.hazmat.primitives import hashes,serialization
 from cryptography.hazmat.primitives.asymmetric import padding,rsa
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 envelope=json.loads(sys.stdin.buffer.read(262145));aad=envelope['aad']
 fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  info=os.fstat(stream.fileno())
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077 or info.st_nlink!=1 or info.st_size>16384:
   raise RuntimeError('KEY_SCOPE')
  key=serialization.load_pem_private_key(stream.read(16385),password=None)
 if not isinstance(key,rsa.RSAPrivateKey) or key.key_size!=4096:raise RuntimeError('KEY_TYPE')
 der=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 if hashlib.sha256(der).hexdigest()!=aad['key_id']:raise RuntimeError('KEY_ID')
 pad=padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)
 aes_key=key.decrypt(base64.b64decode(envelope['wrapped_key'],validate=True),pad)
 if len(aes_key)!=32:raise RuntimeError('AES_KEY_SIZE')
 associated=json.dumps(aad,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 result=AESGCM(aes_key).decrypt(base64.b64decode(envelope['nonce'],validate=True),
                              base64.b64decode(envelope['ciphertext'],validate=True),associated)
 if len(result)>196608:raise RuntimeError('PAYLOAD_LIMIT')
 sys.stdout.buffer.write(result)
except Exception:
 raise SystemExit(2)
'''


def decrypt(envelope, metadata, helper):
    if metadata.get('python') not in helper.candidate_pythons():
        fail('HOLD_DRIVE_CRYPTO_PYTHON')
    key = plain(STATE / 'keys' / metadata['request'] / 'private_key.pem')
    try:
        result = subprocess.run([metadata['python'], '-I', '-c', DECRYPT, str(key)],
                                input=canonical(envelope), capture_output=True, timeout=20, env=helper.CRYPTO_ENV)
    except (OSError, subprocess.TimeoutExpired):
        fail('HOLD_DRIVE_DECRYPTION')
    if result.returncode or len(result.stdout) > 196608:
        fail('HOLD_DRIVE_AUTHENTICATION_FAILED')
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        fail('HOLD_DRIVE_PAYLOAD_JSON')
    if not isinstance(value, dict) or set(value) != {'schema', 'links'} or value['schema'] != 'NOX_DRIVE_RAM_LINKS_V1':
        fail('HOLD_DRIVE_PAYLOAD_SCHEMA')
    return value['links']


def seal(public_metadata, links, manifest=None, expires_at=None):
    """Local caller only: encrypt connector URLs; never prints plaintext."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    manifest = load_manifest() if manifest is None else manifest
    if hashlib.sha256(canonical(manifest)).hexdigest() != MANIFEST_SHA256:
        fail('HOLD_DRIVE_MANIFEST_PIN')
    validate_links(links, manifest)
    public = serialization.load_pem_public_key(public_metadata['public_key_pem'].encode('ascii'))
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size != 4096:
        fail('HOLD_DRIVE_PUBLIC_KEY_TYPE')
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != public_metadata['key_id']:
        fail('HOLD_DRIVE_PUBLIC_KEY_ID')
    now = int(time.time())
    expires = min(now + 240, public_metadata['expires_at']) if expires_at is None else expires_at
    aad = {'schema': 'NOX_DRIVE_RAM_AAD_V1', 'instance_id': INSTANCE_ID,
           'manifest_sha256': MANIFEST_SHA256, 'key_id': public_metadata['key_id'],
           'key_request': public_metadata['request'], 'key_source_sha': public_metadata['source_sha'],
           'envelope_id': secrets.token_hex(16), 'issued_at': now, 'expires_at': expires}
    aes_key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    wrapped = public.encrypt(aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                                 algorithm=hashes.SHA256(), label=None))
    ciphertext = AESGCM(aes_key).encrypt(nonce, canonical({'schema': 'NOX_DRIVE_RAM_LINKS_V1', 'links': links}), canonical(aad))
    envelope = {'schema': 'NOX_DRIVE_RAM_ENVELOPE_V1', 'aad': aad,
                'wrapped_key': base64.b64encode(wrapped).decode(),
                'nonce': base64.b64encode(nonce).decode(),
                'ciphertext': base64.b64encode(ciphertext).decode()}
    validate_envelope(envelope, public_metadata)
    return envelope


RESOLVE = "import json,socket,sys;print(json.dumps(sorted({r[4][0] for r in socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))"


def resolve_public(host):
    try:
        result = subprocess.run([sys.executable, '-I', '-c', RESOLVE, host], capture_output=True,
                                timeout=8, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout) > 4096:
            fail('HOLD_DRIVE_DNS')
        addresses = json.loads(result.stdout)
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= 32:
            fail('HOLD_DRIVE_DNS')
        values = [ipaddress.ip_address(item) for item in addresses]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        fail('HOLD_DRIVE_DNS')
    if any(not value.is_global or value.is_multicast or value.is_reserved for value in values):
        fail('HOLD_DRIVE_NONPUBLIC_ADDRESS')
    return sorted(values, key=lambda value: value.version)


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = str(address)

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def open_response(url, offset, deadline, attempt=0):
    first = validate_url(url)
    current = url
    for redirect in range(3):
        parsed = validate_url(current)
        if parsed.hostname != first.hostname:
            fail('HOLD_DRIVE_CROSS_HOST_REDIRECT')
        left = deadline - time.monotonic()
        if left <= 0:
            fail('HOLD_DRIVE_ENVELOPE_EXPIRED')
        addresses = resolve_public(parsed.hostname)
        connection = PinnedHTTPS(parsed.hostname, addresses[attempt % len(addresses)], min(15, left))
        headers = {'User-Agent': 'NOX-owner-Drive-RAM/1', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = 'bytes=' + str(offset) + '-'
        path = parsed.path + ('?' + parsed.query if parsed.query else '')
        try:
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
        except Exception:
            connection.close()
            raise
        if response.status in (301, 302, 303, 307, 308):
            location = response.getheader('Location')
            response.close()
            connection.close()
            if not isinstance(location, str) or len(location) > MAX_URL_BYTES:
                fail('HOLD_DRIVE_REDIRECT')
            current = urllib.parse.urljoin(current, location)
            # Validate before DNS or the next request; never forward a signed
            # path to a cross-host redirect, even another allowlisted host.
            redirected = validate_url(current)
            if redirected.hostname != first.hostname:
                fail('HOLD_DRIVE_CROSS_HOST_REDIRECT')
            continue
        return connection, response
    fail('HOLD_DRIVE_REDIRECT_LIMIT')


def checked_size(path, maximum, allowed_links=1):
    path = plain(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        return 0
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum or info.st_nlink != allowed_links:
        fail('HOLD_DRIVE_RESOURCE_FILE')
    return info.st_size


def media_pending():
    ram, total = 0, 0
    for subdir, filename, size in MEDIA_ASSETS:
        ram_path = Path('/dev/shm/nox_media/models') / subdir / filename
        disk_path = ROOT / 'media/weights/models' / subdir / filename
        if checked_size(ram_path, size) == size or checked_size(disk_path, size) == size:
            continue
        disk_partial = disk_path.with_name(filename + '.partial')
        if disk_partial.exists():
            total += size - checked_size(disk_partial, size)
        else:
            pending = size - checked_size(ram_path.with_name(filename + '.partial'), size)
            ram += pending
            total += pending
    return ram, total


def remaining_bytes(manifest):
    pending = 0
    for asset in manifest['assets']:
        path = plain(DESTINATION / asset['filename'])
        final = checked_size(path, asset['bytes'], allowed_links=2 if known_publication_pair(asset) else 1)
        if final == asset['bytes']:
            continue
        if final:
            fail('HOLD_DRIVE_EXISTING_FINAL_SIZE')
        pending += asset['bytes'] - checked_size(path.with_name(path.name + '.partial'), asset['bytes'])
    return pending


def resource_snapshot():
    try:
        limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
        used = int(Path('/sys/fs/cgroup/memory.current').read_text())
    except (OSError, ValueError):
        fail('HOLD_DRIVE_FINITE_CGROUP_REQUIRED')
    if not 0 <= used < limit:
        fail('HOLD_DRIVE_CGROUP_LIMIT')
    return {'shm_free': shutil.disk_usage('/dev/shm').free, 'memory_free': limit - used}


def require_tmpfs_destination():
    # No mounts or permissions are changed: only the existing /dev/shm tmpfs
    # is an admitted destination. Reject an unexpected nested disk mount.
    with open('/proc/self/mountinfo', 'rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        fail('HOLD_DRIVE_MOUNTINFO_LIMIT')
    tmpfs = False
    for line in raw.decode('ascii', errors='strict').splitlines():
        fields = line.split()
        if len(fields) > 9 and fields[4] == '/dev/shm' and ' - ' in line:
            tmpfs = line.split(' - ', 1)[1].split()[0] == 'tmpfs'
    if not tmpfs or DESTINATION.stat().st_dev != Path('/dev/shm').stat().st_dev:
        fail('HOLD_DRIVE_RAM_DESTINATION')


def admit(manifest):
    require_running()
    pending = remaining_bytes(manifest)
    media_ram, media_total = media_pending()
    actual = resource_snapshot()
    if actual['shm_free'] < pending + media_ram + SHM_RESERVE + IO_MARGIN:
        fail('HOLD_DRIVE_SHM_RESERVE')
    if actual['memory_free'] < pending + media_total + CGROUP_RESERVE + IO_MARGIN:
        fail('HOLD_DRIVE_CGROUP_RESERVE')
    return {'pending_bytes': pending, 'media_pending_ram_bytes': media_ram,
            'media_pending_bytes': media_total, 'shm_reserve_bytes': SHM_RESERVE,
            'cgroup_reserve_bytes': CGROUP_RESERVE, 'io_margin_bytes': IO_MARGIN,
            **actual}


def hash_fd(fd, size):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        fail('HOLD_DRIVE_FINAL_SIZE')
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        require_running()
        block = os.pread(fd, min(4 * BLOCK, size - offset), offset)
        if not block:
            fail('HOLD_DRIVE_HASH_TRUNCATED')
        digest.update(block)
        offset += len(block)
    after = os.fstat(fd)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        fail('HOLD_DRIVE_FILE_CHANGED')
    return digest.hexdigest(), after


def open_owned(path, create=False, allowed_links=1):
    flags = os.O_RDWR if create else os.O_RDONLY
    if create:
        flags |= os.O_CREAT
    fd = os.open(plain(path), flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != allowed_links or info.st_mode & 0o077):
        os.close(fd)
        fail('HOLD_DRIVE_PARTIAL_SCOPE')
    return fd


def receive_part(fd, part, global_start, url, deadline, manifest):
    retries = 0
    end = global_start + part['bytes']
    while os.fstat(fd).st_size < end:
        require_running()
        offset = os.fstat(fd).st_size - global_start
        if not 0 <= offset < part['bytes'] or time.monotonic() >= deadline:
            fail('HOLD_DRIVE_PART_OR_EXPIRY')
        connection = response = None
        try:
            connection, response = open_response(url, offset, deadline, retries)
            if response.status in (408, 429, 500, 502, 503, 504):
                raise ConnectionError('TRANSIENT')
            if response.status not in (200, 206):
                fail('HOLD_DRIVE_HTTP_STATUS')
            if offset or response.status == 206:
                expected = 'bytes %d-%d/%d' % (offset, part['bytes'] - 1, part['bytes'])
                if response.status != 206 or response.getheader('Content-Range') != expected:
                    fail('HOLD_DRIVE_CONTENT_RANGE')
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                fail('HOLD_DRIVE_CONTENT_ENCODING')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or int(length) != part['bytes'] - offset):
                fail('HOLD_DRIVE_CONTENT_LENGTH')
            while True:
                if time.monotonic() >= deadline:
                    fail('HOLD_DRIVE_ENVELOPE_EXPIRED')
                left = end - os.fstat(fd).st_size
                block = response.read(min(BLOCK, left + 1))
                if time.monotonic() >= deadline:
                    fail('HOLD_DRIVE_ENVELOPE_EXPIRED')
                if not block:
                    if left:
                        raise ConnectionError('INCOMPLETE')
                    break
                if len(block) > left:
                    fail('HOLD_DRIVE_BYTE_QUOTA')
                with LOCK:
                    admit(manifest)
                    if os.lseek(fd, 0, os.SEEK_END) != end - left:
                        fail('HOLD_DRIVE_PARTIAL_CHANGED')
                    view = memoryview(block)
                    while view:
                        written = os.write(fd, view)
                        if not written:
                            fail('HOLD_DRIVE_WRITE')
                        view = view[written:]
            return
        except (OSError, http.client.HTTPException):
            retries += 1
            if retries >= 3:
                fail('HOLD_DRIVE_NETWORK_RETRY_LIMIT')
            if time.monotonic() + min(retries, 2) >= deadline:
                fail('HOLD_DRIVE_ENVELOPE_EXPIRED')
            time.sleep(min(retries, 2))
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()


def partial_identity(asset):
    return {'schema': 'NOX_DRIVE_RAM_PARTIAL_V1', 'manifest_sha256': MANIFEST_SHA256,
            'filename': asset['filename'], 'bytes': asset['bytes'], 'sha256': asset['sha256']}


def known_publication_pair(asset):
    """Recognize only our exact interrupted link/unlink; SHA still runs later."""
    path = plain(DESTINATION / asset['filename'])
    partial = plain(path.with_name(path.name + '.partial'))
    ledger = plain(path.with_name(path.name + '.partial.json'))
    if not path.exists() or not partial.exists() or not ledger.exists():
        return False
    info, other = path.stat(), partial.stat()
    if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(other.st_mode)
            or info.st_nlink != 2 or other.st_nlink != 2 or info.st_size != asset['bytes']
            or info.st_uid != os.geteuid() or info.st_mode & 0o077
            or (info.st_dev, info.st_ino) != (other.st_dev, other.st_ino)):
        return False
    return json.loads(read_regular(ledger, 16384, private=True)) == partial_identity(asset)


def transfer_asset(asset, links, manifest, helper, deadline):
    require_running()
    path = plain(DESTINATION / asset['filename'])
    partial = plain(path.with_name(path.name + '.partial'))
    ledger = plain(path.with_name(path.name + '.partial.json'))
    expected_ledger = partial_identity(asset)
    if path.exists():
        interrupted_publication = known_publication_pair(asset)
        fd = open_owned(path, allowed_links=2 if interrupted_publication else 1)
        try:
            digest, info = hash_fd(fd, asset['bytes'])
            if digest != asset['sha256']:
                fail('HOLD_DRIVE_EXISTING_FINAL_SHA')
            if interrupted_publication:
                # Complete only our known, identical interrupted publication;
                # the retained final inode has just received a full SHA check.
                if partial.stat().st_ino != info.st_ino:
                    fail('HOLD_DRIVE_PARTIAL_CHANGED')
                require_running()
                os.unlink(partial)
                info = os.fstat(fd)
        finally:
            os.close(fd)
        return {'role': asset['role'], 'filename': asset['filename'], 'bytes': asset['bytes'],
                'sha256': digest, 'verified': True, 'reused': True, 'stat_inode': info.st_ino,
                'stat_mtime_ns': info.st_mtime_ns}
    if ledger.exists():
        if json.loads(read_regular(ledger, 16384, private=True)) != expected_ledger:
            fail('HOLD_DRIVE_PARTIAL_IDENTITY')
    elif partial.exists():
        fail('HOLD_DRIVE_UNBOUND_PARTIAL')
    else:
        helper.atomic_private(ledger, canonical(expected_ledger) + b'\n')
    fd = open_owned(partial, create=True)
    try:
        if os.fstat(fd).st_size > asset['bytes']:
            fail('HOLD_DRIVE_PARTIAL_SIZE')
        start = 0
        for part in asset['parts']:
            end = start + part['bytes']
            if os.fstat(fd).st_size < end:
                receive_part(fd, part, start, links[part['drive_id_sha256']], deadline, manifest)
            start = end
            emit('part_bytes_received', role=asset['role'], ordinal=part['ordinal'], bytes=part['bytes'],
                 sha_verified=False)
        os.fsync(fd)
        digest, info = hash_fd(fd, asset['bytes'])
        if digest != asset['sha256']:
            fail('HOLD_DRIVE_JOINED_SHA')
        current = partial.stat()
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != \
                (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            fail('HOLD_DRIVE_PARTIAL_CHANGED')
        # link() publishes atomically without overwriting any existing path.
        # Removing only this owned partial name leaves the same verified inode
        # in RAM, without a second model-sized copy.
        require_running()
        try:
            os.link(partial, path, follow_symlinks=False)
        except FileExistsError:
            fail('HOLD_DRIVE_FINAL_APPEARED')
        os.unlink(partial)
        info = os.fstat(fd)
        result = {'role': asset['role'], 'filename': asset['filename'], 'bytes': asset['bytes'],
                  'sha256': digest, 'verified': True, 'reused': False, 'stat_inode': info.st_ino,
                  'stat_mtime_ns': info.st_mtime_ns}
        emit('adapter_sha_verified', **result)
        return result
    finally:
        os.close(fd)


def consume(envelope):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    helper = load_prepare()
    request, source = helper.context()
    manifest = load_manifest()
    if not isinstance(envelope, dict) or len(canonical(envelope)) > MAX_ENVELOPE_BYTES:
        fail('HOLD_DRIVE_ENVELOPE_LIMIT')
    aad = envelope.get('aad', {})
    key_request = aad.get('key_request') if isinstance(aad, dict) else None
    if not isinstance(key_request, str) or not re.fullmatch('[0-9]{1,24}', key_request):
        fail('HOLD_DRIVE_KEY_REQUEST')
    metadata = json.loads(read_regular(STATE / 'keys' / key_request / 'public_metadata.json', 32768, private=True))
    validate_envelope(envelope, metadata)
    links = validate_links(decrypt(envelope, metadata, helper), manifest)
    # No plaintext URLs/IDs are persisted, placed in argv, or emitted.
    deadline = time.monotonic() + max(0, aad['expires_at'] - time.time())
    envelope_sha = hashlib.sha256(canonical(envelope)).hexdigest()
    with helper.state_lock('transfer.lock'):
        helper.private_directory(STATE / 'consumed')
        receipt_path = STATE / 'consumed' / (envelope_sha + '.json')
        if receipt_path.exists():
            fail('HOLD_DRIVE_ENVELOPE_ALREADY_CONSUMED')
        helper.private_directory(DESTINATION.parent)
        helper.private_directory(DESTINATION)
        require_tmpfs_destination()
        before = admit(manifest)
        receipt = {'schema': 'NOX_DRIVE_RAM_RECEIPT_V1', 'request': request, 'source_sha': source,
                   'state': 'DOWNLOADING', 'started_at': time.time(), 'envelope_sha256': envelope_sha,
                   'manifest_sha256': MANIFEST_SHA256, 'key_id': metadata['key_id'], 'assets': [],
                   'private_urls_exported': False, 'weights_merged': False, 'active_model_changed': False,
                   'ram_is_durable_backup': False}
        helper.atomic_private(receipt_path, canonical(receipt) + b'\n')
        emit('admitted', maximum_transfers=MAX_TRANSFERS, total_bytes=TOTAL_BYTES, **before)
        failures = []
        try:
            with ThreadPoolExecutor(max_workers=MAX_TRANSFERS, thread_name_prefix='nox-drive-ram') as pool:
                futures = [pool.submit(transfer_asset, asset, links, manifest, helper, deadline)
                           for asset in manifest['assets']]
                for future in as_completed(futures):
                    try:
                        receipt['assets'].append(future.result())
                    except Exception as exc:
                        failures.append(safe_code(exc))
            if failures:
                fail(failures[0])
            if len(receipt['assets']) != 3 or not all(item.get('verified') is True for item in receipt['assets']):
                fail('HOLD_DRIVE_FINAL_PROOF')
            receipt['state'] = 'RAM_FILES_SHA_VERIFIED_NOT_MERGED'
            receipt['destination'] = str(DESTINATION)
        except Exception as exc:
            receipt['state'] = 'HOLD_DRIVE_REHYDRATION'
            receipt['error'] = safe_code(exc)
        finally:
            receipt['finished_at'] = time.time()
            receipt['assets'].sort(key=lambda asset: asset['role'])
            helper.atomic_private(receipt_path, canonical(receipt) + b'\n')
            helper.atomic_private(STATE / 'latest_receipt.json', canonical(receipt) + b'\n')
            emit('receipt', **receipt)
        if receipt['state'] != 'RAM_FILES_SHA_VERIFIED_NOT_MERGED':
            fail(receipt['error'])
        return receipt


def run_envelope(envelope):
    """Native entry wrapper: public output contains fixed codes and proof only."""
    try:
        consume(envelope)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return 0
    except Exception as exc:
        emit('held', state='HOLD', error=safe_code(exc))
        return 2
