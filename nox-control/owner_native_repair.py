"""Transfer only pinned installed Python preimages to the owner's recipient key."""

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


RECIPIENT = "-----BEGIN CERTIFICATE-----\nMIIEHTCCAoWgAwIBAgIUWPB8+f5aD3qwXOI/l24IZP2FLmswDQYJKoZIhvcNAQEL\nBQAwHjEcMBoGA1UEAwwTTk9YLXNvdXJjZS10cmFuc2ZlcjAeFw0yNjExMTkxNTEx\nMDRaFw0yNjExMjExNTExMDRaMB4xHDAaBgNVBAMME05PWC1zb3VyY2UtdHJhbnNm\nZXIwggGiMA0GCSqGSIb3DQEBAQUAA4IBjwAwggGKAoIBgQDTdIgdISeWdwYW7GOq\nU0MVaUtqVcJK/6EQJ0LlEwhl/8GsKijGHmrcGt5hgKcHiR0P0xzI/Sp3eRf3p5I7\n91BaMASsjVgE/XP3Z95xgtKhQsc+04unLf9Bw/q0jD67ttlUGyVw96ex0KDNHad7\nh+HsEYymWV4bj33Vp3BHNckYE8Ey0Olxgg2ldVSdaLFKbuNgCWCf3rUa1H9Udwbk\nLJDjmM6Vo1j5AIWpGlVwvuUPfu9k5GHDIvbvEi9eE3Yn50QaQUqJ2i7xJ8WM81fs\nVQ9zvpW52pcAjDzqftxT+k95a52GWT5ATwuwpsRsKmGQEs0iSrnvUt0+lKdFUfhx\n8eKlTCfUt9x6y55su/LRNi96AUBwqq2nszN0xUTfgf9AizM6jcHBLAgrII7tObG+\nbC/sxgDYH4yd/JjcDKEXTO6FUmCzQzXMhCfjmSsR6BCKmIBKACYYpUazilU01KYu\nnQqNmXFIyLv0qCR0bWCW1oXSgfDeu6UQZBHU+GnUYFv1OgkCAwEAAaNTMFEwHQYD\nVR0OBBYEFCb957iBIhBzpFkrooZC6TNv1/zbMB8GA1UdIwQYMBaAFCb957iBIhBz\npFkrooZC6TNv1/zbMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggGB\nAD6EXB50FOaKVgzSu3gcK3KG8SZIIcrd1r+fO20JcE1einlVlItO84K751VItA6E\nWGULJWDw5okbEkd3dKaE3bOVl4W18ypvOidgNKOFOT1GSgI8ghpgT+cVYSe8imQc\nRv2lQar8jkPXhZuHqZVr4fVlpG/qjs6BnIj+fL/WXsSQ9oi4q+PYGDUygIBE+PIw\nHCMEz8cZ8O2XaPD3z5V+ZmNfOOOzLVIjIaNm8YZ1IM/YWtbQ8a5fcHCFufT7CCpQ\nu7mbyBp6OMi483UpmzNFtokBq/Zv0XPilkb8Az4wOt+CkjaK8nmMAbOgK4F1+Pgn\njjjSuuApOImAailNA51A05ex0Z/5elF+pBvM0WGP3WxMwMxUj4cF3MOCQcTsYstC\nZN2c5HUKZnPlz7Q9VkTZS3VDAl9tdEj1QpVy+imujgbQtfirN6sxk6OlHG7QRIQV\nypoF64A46Qmih3xFZarisIpWATuVP8omD6Zar4ubeFKfQt+HcEH8V9B5hOw4sr3g\nVg==\n-----END CERTIFICATE-----\n"
ROOT = Path('/root/nox/scripts')
PINS = {
    'chat_proxy.py': 'cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb',
    'nox_v29_chat_bridge.py': '2d7145293fa5566fee38a61e772780b4b0dd0e2d1bcad71b5ceedf77974a75a7',
    'owner_chat_stream.py': 'a26ec83aadac240d7284959b53cf7e59575e8e487d27c962cec7236892ccc7af',
    's03_memory.py': '776a6dc25726540d75ec51216d1e333ca89b24e803ba3620f9b5e470a3c81476',
    'common.py': '177fbe5df042ba75a94cf9b7c03c8ffe58bde99f12599193db0cf383cc1305dd',
}


def require(condition, code):
    if not condition:
        raise RuntimeError('HOLD_COGNITION_PREIMAGE_' + code)


def preimages():
    result = {}
    for part in (ROOT, *ROOT.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0, 'DIRECTORY')
    root = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name, expected in PINS.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=root)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                        and 0 < info.st_size <= 256 * 1024, 'SOURCE_SCOPE')
                raw = stream.read(info.st_size + 1)
                current = os.stat(name, dir_fd=root, follow_symlinks=False)
                require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino)
                        and hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_CHANGED')
                result[name] = base64.b64encode(raw).decode('ascii')
    finally:
        os.close(root)
    return result


def main():
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == 0 and labels == {'60509551'}
            and re.fullmatch('[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            and re.fullmatch('[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')), 'OWNER')
    data = gzip.compress(json.dumps(preimages(), separators=(',', ':')).encode())
    require(len(data) <= 192 * 1024, 'TRANSFER_LIMIT')
    with tempfile.TemporaryDirectory(prefix='nox-public-recipient-') as temporary:
        cert = Path(temporary) / 'recipient.pem'
        cert.write_text(RECIPIENT, encoding='ascii')
        envelope = subprocess.run(['/usr/bin/openssl', 'cms', '-encrypt', '-binary', '-aes-256-gcm',
                                   '-outform', 'DER', str(cert)], input=data, timeout=8,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(envelope.returncode == 0 and 0 < len(envelope.stdout) <= 200 * 1024, 'ENVELOPE')
    encoded = base64.b64encode(envelope.stdout).decode('ascii')
    chunks = [encoded[i:i + 8000] for i in range(0, len(encoded), 8000)]
    for index, chunk in enumerate(chunks):
        print(f'NOX_MAINT_COGNITION_ENVELOPE_{index:03d}={chunk}', flush=True)
    print('NOX_MAINT_COGNITION_ENVELOPE_META=' + json.dumps({'chunks': len(chunks),
        'sha256': hashlib.sha256(envelope.stdout).hexdigest(), 'files': len(PINS)}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        code = str(error)
        print('NOX_MAINT_COGNITION_PREIMAGE_HOLD=' + (code if re.fullmatch('HOLD_[A-Z0-9_]+', code)
                                                   else type(error).__name__), flush=True)
        raise SystemExit(2) from None
