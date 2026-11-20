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
CIPHER_SHA = '00047e87b37c81fd58765bcbf1b0b2865d7adb915c340cce09f2cfe41699b0dd'
PACKET_SHA = 'c991ec3542e3ad13f9814fbfc5c020baa791233d5f50c83aaab682aca8d649d7'
ENTRY_SHA = '825c6a7e9d91bfd6c42fdcf81e6a90bcb93379e63defe4592629212975ab5277'
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
