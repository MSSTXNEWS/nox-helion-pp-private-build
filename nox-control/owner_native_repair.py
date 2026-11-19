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
CIPHER_SHA = 'd873f899e9262f47e08b63c7650b55a47eb4e7867e83ab12096267e30dfcdb44'
PACKET_SHA = '888565923a635a5f273d83c676caa4e36b781aea18c16f46a0e7cd24e7f42271'
ENTRY_SHA = '8fdba9849a4a21dc4f92d5f7b520758227691423b866f498328d8f0ddcebf679'
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
