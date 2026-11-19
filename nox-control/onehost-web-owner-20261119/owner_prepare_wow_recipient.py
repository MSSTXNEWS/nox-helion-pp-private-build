"""Create one root-private receiving key for the owner's WOW visual package."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess


ROOT = Path('/root/nox/state')


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    if os.geteuid() != 0 or not re.fullmatch(r'[1-9][0-9]{0,19}', request):
        raise RuntimeError('HOLD_WOW_OWNER_REQUEST')
    for parent in (ROOT, *ROOT.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('HOLD_WOW_TRANSPORT_ROOT')
    target = ROOT / ('owner-wow-ingress-' + request)
    target.mkdir(mode=0o700)
    previous = os.umask(0o077)
    try:
        generated = subprocess.run(('/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-subj', '/CN=NOX-WOW-Owner-Transport', '-days', '1', '-keyout', str(target / 'ingress.key'),
            '-out', str(target / 'ingress.pem')), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=12, check=False)
    finally:
        os.umask(previous)
    if generated.returncode != 0:
        raise RuntimeError('HOLD_WOW_TRANSPORT_CERT')
    key = (target / 'ingress.key').lstat()
    cert = (target / 'ingress.pem').read_bytes()
    if not stat.S_ISREG(key.st_mode) or key.st_nlink != 1 or key.st_uid != 0 or stat.S_IMODE(key.st_mode) != 0o600 or not 0 < len(cert) <= 3000:
        raise RuntimeError('HOLD_WOW_TRANSPORT_CERT')
    print('NOX_MAINT_WOW_RECIPIENT=' + json.dumps({'request': request, 'cert_sha256': hashlib.sha256(cert).hexdigest(),
        'cert_pem_b64': base64.b64encode(cert).decode('ascii')}, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
