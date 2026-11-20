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
CIPHER_SHA = '7935986525eb01c0f84538dacac1a1461aee7027caa5c49adf339882bc186c25'
PACKET_SHA = 'e162fe64645444dd30a07f1f5ffa294896eb7cfc0051b8df3fc9d5479bddc4a6'
ENTRY_SHA = '3559b8c799ea5660032bc507b47722b364970515911bd66d3c632eea308d0618'
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
