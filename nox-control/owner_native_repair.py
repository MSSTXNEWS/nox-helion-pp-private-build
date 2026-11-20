"""Open only the pinned I-39 publisher using the existing owner CMS ingress."""

import base64
import gzip
from hashlib import sha256
import io
import os
from pathlib import Path
import re
import stat
import subprocess


KEY_DIR = Path('/root/nox/state/owner-wow-ingress-7015017904')
CERT_SHA = '9788202aecc431b4e1a92beb6790d7cea75f6f3dfccbebc373f029b33ee4f6d2'
CIPHER_SHA = 'c0ac2bb8b7cd1c72b47babc860c702b736f92bea9de95dc9de9f2824dc209fdf'
PACKET_SHA = 'a4ded4fbd57468888b120cf5df3e2ebcc7d749accf5f12f17015856b2007c764'
ENTRY_SHA = 'c758d5f8e45d1393bf720c40c1cce210078c79e99566efd0d71c0ed96d62dca5'
CIPHER_B64 = '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'


def require(allowed, reason):
    if not allowed:
        raise RuntimeError('HOLD_I39_INGRESS_' + reason)


def trusted_file(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    handle = os.fdopen(fd, 'rb')
    try:
        meta = os.fstat(handle.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1
                and meta.st_mode & 0o077 == 0 and 0 < meta.st_size <= limit, 'FILE_SCOPE')
    except BaseException:
        handle.close()
        raise
    return handle


def verify_ingress():
    for directory in (KEY_DIR, *KEY_DIR.parents):
        meta = directory.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0
                and meta.st_mode & 0o022 == 0, 'DIRECTORY_SCOPE')


def open_entry():
    verify_ingress()
    cert = KEY_DIR / 'ingress.pem'
    key = KEY_DIR / 'ingress.key'
    with trusted_file(cert, 3000) as handle:
        require(sha256(handle.read(3001)).hexdigest() == CERT_SHA, 'CERT_PIN')
    with trusted_file(key, 6000):
        pass
    ciphertext = base64.b64decode(CIPHER_B64, validate=True)
    require(0 < len(ciphertext) <= 80000 and sha256(ciphertext).hexdigest() == CIPHER_SHA, 'CIPHER_PIN')
    decrypted = subprocess.run(('/usr/bin/openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                                '-recip', str(cert), '-inkey', str(key)),
                               input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=8, check=False)
    packet = decrypted.stdout
    require(decrypted.returncode == 0 and 0 < len(packet) <= 80000
            and sha256(packet).hexdigest() == PACKET_SHA, 'PACKET_PIN')
    with gzip.GzipFile(fileobj=io.BytesIO(packet), mode='rb') as handle:
        module = handle.read(80001)
    require(0 < len(module) <= 80000 and sha256(module).hexdigest() == ENTRY_SHA, 'ENTRY_PIN')
    return module


def main():
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request) is not None
            and re.fullmatch(r'[a-f0-9]{40}', source) is not None, 'OWNER_SCOPE')
    module = open_entry()
    exec(compile(module, '<pinned-operator-reviewed-I39>', 'exec'), {'__name__': '__main__'})


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
        tag = str(failure)
        print('NOX_MAINT_RESULT=' + (tag if re.fullmatch(r'HOLD_I39_INGRESS_[A-Z_]+', tag)
                                   else 'HOLD_I39_INGRESS_UNAVAILABLE'), flush=True)
        raise SystemExit(2) from None
