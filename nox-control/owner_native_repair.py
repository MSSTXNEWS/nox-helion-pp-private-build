#!/usr/bin/env python3
"""Decrypt one owner-pinned source URL and stage, never serve, the WOW R6.2 archive."""

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zipfile import ZipFile

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
PARENT = ROOT / 'incoming_t800u'
DESTINATION = PARENT / 'wow-r62-full'
RECIPIENT_REQUEST = '7015017904'
RECIPIENT = ROOT / 'state' / ('owner-wow-ingress-' + RECIPIENT_REQUEST)
CERT_SHA = '9788202aecc431b4e1a92beb6790d7cea75f6f3dfccbebc373f029b33ee4f6d2'
CMS_NAME = 'NOX_WOW_R62_DRIVE_STAGE.cms'
CMS_SHA = 'd51253dc7129db6ca71deb15e068ae959a0c84c122a13209c2bfed542d80793d'
CMS_BYTES = 1063
ZIP_NAME = 'NOX_WEB_V14_CINEMA_ASSIST_20261119_R6_2_WOW_NO_DUPLICATES.zip'
ZIP_SHA = 'f10d2437f45018b846d0dca87691ab65d35c04c9c1ca8d0d7b0bab1538a0090c'
ZIP_BYTES = 84472731
EXPANDED_BYTES = 179184954
ENTRY_COUNT = 1270
MAX_MEMBER_BYTES = 30719241
CHUNK = 1024 * 1024
STOPS = tuple(ROOT / name for name in (
    'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP', 'state/STOP.flag',
    'state/OWNER_MAINTENANCE.flag',
)) + (Path('/workspace/NOX_STOP'),)


def require(ok, reason):
    if not ok:
        raise RuntimeError('HOLD_WOW_FULL_STAGE_' + reason)


def gate():
    require(not any(os.path.lexists(path) for path in STOPS), 'STOP_OR_MAINTENANCE')


def immutable_owner_directory(path, private=False):
    for ancestor in (*reversed(path.parents), path):
        info = ancestor.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                'DIRECTORY_SCOPE')
    if private:
        require(stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY_MODE')


def private_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= limit,
                'RECIPIENT_FILE_SCOPE')
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        named = path.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k)
                   == getattr(named, k) for k in fields), 'RECIPIENT_FILE_RACE')
        return raw
    finally:
        os.close(fd)


def decrypt_reference():
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == {CMS_NAME}, 'ENVELOPE_SCOPE')
    encoded = BUNDLE[CMS_NAME]
    require(isinstance(encoded, str) and 0 < len(encoded) <= 4096, 'ENVELOPE_BOUND')
    container = base64.b64decode(encoded, validate=True)
    require(len(container) == CMS_BYTES and hashlib.sha256(container).hexdigest() == CMS_SHA,
            'ENVELOPE_PIN')
    immutable_owner_directory(RECIPIENT, private=True)
    cert, key = RECIPIENT / 'ingress.pem', RECIPIENT / 'ingress.key'
    require(hashlib.sha256(private_read(cert, 3000)).hexdigest() == CERT_SHA, 'RECIPIENT_CERT_PIN')
    private_read(key, 8192)
    decrypted = subprocess.run(('/usr/bin/openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                               '-recip', str(cert), '-inkey', str(key)),
                              input=container, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=12, check=False)
    require(decrypted.returncode == 0 and 0 < len(decrypted.stdout) <= 8192, 'AUTHENTICATED_DECRYPTION')
    value = json.loads(decrypted.stdout)
    require(isinstance(value, dict) and set(value) == {'url', 'size', 'filename', 'sha256'}
            and type(value['size']) is int and (value['size'], value['filename'], value['sha256'])
            == (ZIP_BYTES, ZIP_NAME, ZIP_SHA), 'MANIFEST_PIN')
    url = value['url']
    require(isinstance(url, str) and re.fullmatch(r'https://[\x21-\x7e]{1,8000}', url), 'URL_FORMAT')
    parts = urlsplit(url)
    require(parts.scheme == 'https'
            and re.fullmatch(r'sdmntpr[a-z0-9-]{0,32}\.oaiusercontent\.com', parts.hostname or '')
            and parts.port in (None, 443) and not parts.username and not parts.password
            and parts.path.startswith('/') and parts.query and not parts.fragment, 'URL_ISSUER')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url, filename):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(url, method='GET', headers={'Accept-Encoding': 'identity', 'Connection': 'close'})
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as exc:
        raise RuntimeError('HOLD_WOW_FULL_STAGE_HTTP_' + str(exc.code)) from None
    digest, size = hashlib.sha256(), 0
    with response, filename.open('xb') as target:
        length = response.headers.get('Content-Length')
        require(response.status == 200 and response.geturl() == url
                and response.headers.get('Content-Encoding', 'identity') == 'identity'
                and (length is None or length == str(ZIP_BYTES)), 'DOWNLOAD_HEADER')
        while True:
            gate()
            data = response.read(CHUNK)
            if not data:
                break
            size += len(data)
            require(size <= ZIP_BYTES, 'DOWNLOAD_SIZE')
            digest.update(data)
            target.write(data)
        target.flush()
        os.fsync(target.fileno())
    require(size == ZIP_BYTES and digest.hexdigest() == ZIP_SHA, 'DOWNLOAD_HASH')


def member_paths(archive):
    items = archive.infolist()
    require(len(items) == ENTRY_COUNT and sum(item.file_size for item in items) == EXPANDED_BYTES,
            'ZIP_INVENTORY')
    members = {}
    for item in items:
        name = item.filename
        path = PurePosixPath(name)
        require(path.parts[0:1] == ('site',) and 2 <= len(path.parts) <= 9 and str(path) == name
                and name == item.orig_filename and len(name) <= 1024
                and not re.search(r'[\x00-\x1f\x7f\\:]', name)
                and all(part not in ('', '.', '..') for part in path.parts)
                and not item.is_dir() and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                and not item.flag_bits & 1 and 0 <= item.file_size <= MAX_MEMBER_BYTES, 'ZIP_MEMBER')
        folded = name.casefold()
        require(folded not in members, 'ZIP_DUPLICATE')
        members[folded] = item
    for name in members:
        parts = name.split('/')
        require(not any('/'.join(parts[:depth]) in members for depth in range(1, len(parts))),
                'ZIP_FILE_DIRECTORY_COLLISION')
    return tuple(members.values())


def extract(filename, root):
    total = 0
    with ZipFile(filename) as archive:
        for item in member_paths(archive):
            gate()
            output = root.joinpath(*PurePosixPath(item.filename).parts)
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            count = 0
            with archive.open(item) as source, output.open('xb') as dest:
                while True:
                    data = source.read(CHUNK)
                    if not data:
                        break
                    count += len(data)
                    require(count <= item.file_size, 'ZIP_MEMBER_SIZE')
                    dest.write(data)
                require(count == item.file_size, 'ZIP_MEMBER_TRUNCATED')
                dest.flush()
                os.fchmod(dest.fileno(), 0o400)
                os.fsync(dest.fileno())
            total += count
    require(total == EXPANDED_BYTES, 'ZIP_EXPANDED_SIZE')


def write_receipt(directory, record):
    with (directory / 'receipt.json').open('xb') as output:
        raw = (json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n').encode()
        output.write(raw)
        output.flush()
        os.fchmod(output.fileno(), 0o400)
        os.fsync(output.fileno())
    return hashlib.sha256(raw).hexdigest()


def seal_directories(root):
    for directory, _, _ in os.walk(root, topdown=False):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fchmod(fd, 0o500)
            os.fsync(fd)
        finally:
            os.close(fd)


def publish(parent_fd, stage_name):
    function = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    require(function is not None, 'ATOMIC_NOREPLACE_UNAVAILABLE')
    function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    result = function(parent_fd, os.fsencode(stage_name), parent_fd, os.fsencode(DESTINATION.name), 1)
    require(result == 0, 'ATOMIC_NOREPLACE_FAILED')
    os.fsync(parent_fd)


def main(record):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(os.geteuid() == 0 and re.fullmatch(r'[1-9][0-9]{0,19}', request)
            and re.fullmatch(r'[0-9a-f]{40}', source), 'OWNER_CONTEXT')
    gate()
    record.update(request=request, source_sha=source, recipient_request=RECIPIENT_REQUEST)
    immutable_owner_directory(PARENT)
    require(not os.path.lexists(DESTINATION), 'DESTINATION_ALREADY_EXISTS')
    require(shutil.disk_usage(PARENT).free >= ZIP_BYTES + EXPANDED_BYTES + 512 * CHUNK, 'DISK_RESERVE')
    url = decrypt_reference()
    parent_fd = os.open(PARENT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stage_name = '.wow-r62-full-' + request + '.partial'
    stage = PARENT / stage_name
    own_stage = False
    stage_identity = None
    try:
        info = os.fstat(parent_fd)
        require(info.st_dev == PARENT.lstat().st_dev and info.st_ino == PARENT.lstat().st_ino, 'PARENT_RACE')
        os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        own_stage = True
        created = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
        stage_identity = created.st_dev, created.st_ino
        filename = stage / ZIP_NAME
        download(url, filename)
        url = None
        record['archive_verified'] = True
        extract(filename, stage)
        filename.chmod(0o400)
        gate()
        require(info.st_dev == PARENT.lstat().st_dev and info.st_ino == PARENT.lstat().st_ino, 'PARENT_RACE')
        record.update(state='VERIFIED_STAGED_ONLY', files=ENTRY_COUNT, expanded_bytes=EXPANDED_BYTES)
        receipt_sha = write_receipt(stage, record)
        seal_directories(stage)
        publish(parent_fd, stage_name)
        own_stage = False
        record['receipt_sha256'] = receipt_sha
    finally:
        try:
            if own_stage and stage_identity is not None:
                try:
                    remaining = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    remaining = None
                if remaining is not None and stat.S_ISDIR(remaining.st_mode) and (
                        remaining.st_dev, remaining.st_ino) == stage_identity:
                    shutil.rmtree(stage_name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)


def deadline(_signal, _frame):
    require(False, 'TIME_LIMIT')


if __name__ == '__main__':
    os.umask(0o077)
    result = {'schema':'NOX_WOW_R62_FULL_PRIVATE_STAGE_V1', 'state':'HOLD',
              'directory':str(DESTINATION), 'zip_filename':ZIP_NAME, 'zip_sha256':ZIP_SHA,
              'zip_bytes':ZIP_BYTES, 'active_site_changed':False, 'service_changes':0,
              'archive_bodies_exported':False, 'signed_url_exported':False}
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, deadline)
    signal.alarm(240)
    try:
        main(result)
        exit_code = 0
    except BaseException as error:
        safe = str(error)
        result.update(state='HOLD', reason=safe if re.fullmatch(r'HOLD_WOW_FULL_STAGE_[A-Z0-9_]{1,120}', safe)
                      else 'HOLD_WOW_FULL_STAGE_' + type(error).__name__.upper())
        exit_code = 2
    finally:
        signal.alarm(0)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind':'wow_r62_full_private_stage','data':result},
          sort_keys=True, separators=(',',':')), flush=True)
    if exit_code == 0:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    raise SystemExit(exit_code)
