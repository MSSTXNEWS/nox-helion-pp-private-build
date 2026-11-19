"""Repair scoped S03 and issue a short-lived owner session to the authenticated relay only."""
import base64
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from types import ModuleType

BUNDLE = __NOX_BUNDLE_JSON__

def activate():
    name = 'owner_scoped_s03_pair_repair.py'
    repair = ModuleType(name.removesuffix('.py'))
    sys.modules[repair.__name__] = repair
    repair.__dict__['__NOX_' + 'BUNDLE_JSON__'] = {key: value for key, value in BUNDLE.items() if key != name}
    exec(compile(base64.b64decode(BUNDLE[name], validate=True), name, 'exec'), repair.__dict__)
    try:
        repair.main()
    except Exception as error:
        code = str(error)
        print('NOX_MAINT_SCOPED_S03_PAIR_HOLD=' + (code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,120}', code) else type(error).__name__), flush=True)

def relay_session():
    receipt = Path('/root/nox/ops/nox-quick-chat/active.json')
    with os.fdopen(os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as stream:
        node = os.fstat(stream.fileno())
        if not stat.S_ISREG(node.st_mode) or node.st_uid != 0 or node.st_mode & 0o077:
            raise RuntimeError('HOLD_EDGE_RECEIPT_SCOPE')
        active = json.loads(stream.read(4096))
    if (active.get('request') != '7015221558' or active.get('url') != 'https://correct-geometry-feof-meal.trycloudflare.com/chat'
            or active.get('expires_unix', 0) <= time.time()):
        raise RuntimeError('HOLD_EDGE_RECEIPT_PIN')
    current = int(Path('/sys/fs/cgroup/memory.current').read_text())
    maximum = int(Path('/sys/fs/cgroup/memory.max').read_text())
    if maximum - current < 2 * 1024**3:
        raise RuntimeError('HOLD_EDGE_RESERVE')
    if sha256(Path('/root/nox/scripts/chat_proxy.py').read_bytes()).hexdigest() != '9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3':
        raise RuntimeError('HOLD_EDGE_AUTH_SOURCE')
    key = Path('/root/nox/secrets/chat_session_key')
    with os.fdopen(os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK), 'rb') as stream:
        node = os.fstat(stream.fileno())
        if not stat.S_ISREG(node.st_mode) or node.st_uid != 0 or node.st_nlink != 1 or node.st_mode & 0o077 or not 32 <= node.st_size <= 512:
            raise RuntimeError('HOLD_EDGE_KEY_SCOPE')
        secret = stream.read(513).strip()
        if len(secret) < 32:
            raise RuntimeError('HOLD_EDGE_KEY_SIZE')
    value = str(int(time.time()) + 150) + '.' + secrets.token_urlsafe(16)
    cookie = value + '.' + hmac.new(secret, value.encode(), sha256).hexdigest()
    print('NOX_PRIVATE_HTTPS_RELAY=' + json.dumps({'cookie':cookie, 'tunnel':active}, separators=(',', ':')), flush=True)

if __name__ == '__main__':
    activate()
    try:
        relay_session()
    except Exception as exc:
        code = str(exc)
        print('NOX_MAINT_HTTPS_RELAY_HOLD=' + (code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', code) else type(exc).__name__), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
