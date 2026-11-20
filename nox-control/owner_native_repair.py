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
CIPHER_SHA = 'f967c9486829ee119bd34296e2f126950756842a2cfc4060f579f703a49bcdf4'
PACKET_SHA = '4953ab3293a5c57207f55b4318021f44ed26a28404cc7458dfe35609c7f947d2'
ENTRY_SHA = '950889f4acacf8f086e314440cd1d82138f5b911f179aa07b6d2fcac01e8de27'
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
