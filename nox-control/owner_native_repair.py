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
CIPHER_SHA = '4d1ea1446691dd15455d3f2bd9e08f869457e2cd93114a9034037b2f4d085d65'
PACKET_SHA = '515fc7f841e5966385645167fd1c4fbb459760a0caed875379f673ec24e8ecf8'
ENTRY_SHA = 'e6a197bb8b6cabbedf7b4bab76df1a1269dcd9a7f8f9e8ec9e7e62aae6f49916'
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
