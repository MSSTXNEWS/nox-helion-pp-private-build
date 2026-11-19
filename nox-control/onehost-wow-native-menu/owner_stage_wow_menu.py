"""Decrypt the owner's pinned private WOW delta into the existing static installer input."""

from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
import tempfile


KEYS = Path('/root/nox/state/owner-wow-ingress-7015017904')
TARGET = Path('/root/nox/incoming_t800u/wow_r62_owner_private')
NAME = 'NOX_WOW_R6_2_NATIVE_MENU_ONLY.zip'
CERT_SHA = '9788202aecc431b4e1a92beb6790d7cea75f6f3dfccbebc373f029b33ee4f6d2'
CIPHER_SHA = '8bebf5b228381b4059fd6a8262523234faa3de5a701dc2b5a4c234acf60d6344'
ZIP_SHA = '6eddd41d275e8a09bf5c32c02f5504353bfabca7b7af164ef7404f1ddf2379b2'


def need(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_PRIVATE_WOW_MENU_' + reason)


def trusted(path):
    for parent in (path, *path.parents):
        data = parent.lstat()
        need(stat.S_ISDIR(data.st_mode) and data.st_uid == 0 and data.st_mode & 0o022 == 0,
             'DIRECTORY_MODE')


def bounded(path, limit, mode):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    with os.fdopen(os.open(path, flags), 'rb') as handle:
        item = os.fstat(handle.fileno())
        need(stat.S_ISREG(item.st_mode) and item.st_uid == 0 and item.st_nlink == 1
             and 0 < item.st_size <= limit and stat.S_IMODE(item.st_mode) == mode, 'FILE_MODE')
        data = handle.read(limit + 1)
        need(len(data) == item.st_size, 'FILE_SIZE')
        return data


def stage(cipher):
    need(os.geteuid() == 0 and len(cipher) <= 7000 and sha256(cipher).hexdigest() == CIPHER_SHA,
         'CIPHER_PIN')
    trusted(KEYS)
    trusted(TARGET.parent)
    cert = KEYS / 'ingress.pem'
    key = KEYS / 'ingress.key'
    need(sha256(bounded(cert, 2500, 0o600)).hexdigest() == CERT_SHA, 'RECIPIENT_PIN')
    bounded(key, 5000, 0o600)
    result = subprocess.run(('/usr/bin/openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                             '-recip', str(cert), '-inkey', str(key)), input=cipher,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False)
    raw = result.stdout
    need(result.returncode == 0 and len(raw) == 5460 and sha256(raw).hexdigest() == ZIP_SHA, 'ARCHIVE_PIN')
    TARGET.mkdir(mode=0o700, exist_ok=True)
    trusted(TARGET)
    need(stat.S_IMODE(TARGET.stat().st_mode) == 0o700, 'STAGE_MODE')
    if not os.path.lexists(TARGET / NAME):
        fd, temporary = tempfile.mkstemp(dir=TARGET, prefix='.menu-')
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, TARGET / NAME)
        finally:
            os.unlink(temporary)
    need(bounded(TARGET / NAME, 5460, 0o600) == raw, 'ARCHIVE_READBACK')
    fd = os.open(TARGET, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
