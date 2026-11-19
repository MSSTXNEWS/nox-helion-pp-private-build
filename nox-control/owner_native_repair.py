"""Install the encrypted owner-only WOW R6.2 menu and use the existing HTTPS session path."""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
from types import ModuleType

BUNDLE = __NOX_BUNDLE_JSON__

def load(name, dependencies=None):
    module = ModuleType(name.removesuffix('.py'))
    sys.modules[module.__name__] = module
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dependencies or {}
    exec(compile(base64.b64decode(BUNDLE[name], validate=True), name, 'exec'), module.__dict__)
    return module

def emit(prefix, result):
    print(prefix + json.dumps(result, sort_keys=True, separators=(',', ':')), flush=True)

def hold(prefix, error):
    value = str(error)
    print(prefix + (value if re.fullmatch(r'HOLD_[A-Z0-9_]{1,120}', value) else type(error).__name__), flush=True)

def main():
    try:
        stage = load('owner_stage_wow_menu.py')
        wrapped = base64.b64decode(BUNDLE['wow-menu.cms.b64'], validate=True)
        stage.stage(base64.b64decode(wrapped, validate=True))
        deps = {name: BUNDLE[name] for name in ('owner_wow_served_asset_receipt.py',)}
        deps['owner_chat_stream_asset_install_v2.py'] = BUNDLE['owner_pinned_wow_exchange.py']
        deps['owner_media_acceptance_entry.py'] = BUNDLE['owner_frozen_wow_route_auth.py']
        menu = load('owner_wow_r62_menu_only_apply.py', deps)
        record = {'schema':'NOX_WOW_R6_2_MENU_ONLY_RECEIPT_V1', 'state':'HOLD',
                  'archive_sha256': menu.ZIP_SHA, 'files':[], 'started_at':int(time.time()),
                  'service_restarts':0, 'asset_bytes_exported':False}
        signal.signal(signal.SIGALRM, menu.check_stop)
        signal.alarm(150)
        try:
            menu.run(record)
        finally:
            signal.alarm(0)
        emit('NOX_MAINT_WOW_MENU=', record)
    except Exception as error:
        hold('NOX_MAINT_WOW_MENU_HOLD=', error)
    try:
        path = Path('/root/nox/ops/nox-quick-chat/active.json')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'rb') as handle:
            item = os.fstat(handle.fileno())
            if not stat.S_ISREG(item.st_mode) or item.st_uid != 0 or item.st_nlink != 1 or item.st_mode & 0o077:
                raise RuntimeError('HOLD_RESONANCE_TUNNEL_RECEIPT_MODE')
            tunnel = json.loads(handle.read(4096))
        if tunnel.get('request') != '7015221558' or tunnel.get('expires_unix', 0) <= time.time():
            raise RuntimeError('HOLD_RESONANCE_TUNNEL_RECEIPT_SCOPE')
        auth = load('owner_frozen_wow_route_auth.py')
        result = load('owner_quick_chat_receipt.py').prove(tunnel, auth.OwnerClient)
        emit('NOX_MAINT_HTTPS_RESONANCE=', result)
    except Exception as error:
        hold('NOX_MAINT_HTTPS_RESONANCE_HOLD=', error)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)

if __name__ == '__main__':
    main()
