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
CIPHER_SHA = '6294ec73dd6984dc9662bca8a6aa0c848fdecdbff904055f0142b96b537a6209'
PACKET_SHA = '864b52485c2421f9a0b41f5e5fe401c0c6ddc7647c5c7aafff097a627db587b8'
ENTRY_SHA = 'd60ff72ca86e85d956bc80ec5eb11a643c9cf28eb74b54044454f17c2abccf9c'
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
