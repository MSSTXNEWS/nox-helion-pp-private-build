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
CIPHER_SHA = '1248a6ce6b1c1cf928cc1037673137114c79086c01bddf097ffd77846e923862'
PACKET_SHA = '4a246d5a740aa659d58da0e8a7df6305c519aa12df4f9e75a6afbdece8ed904d'
ENTRY_SHA = '98fe42958494dfce84545080107101cb8777dfa6aaa8af915738d79a547df356'
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
