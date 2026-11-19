"""Publish a narrow HTTPS entry for the original NOX product."""
import base64
import json
import re
import sys
from types import ModuleType

BUNDLE = __NOX_BUNDLE_JSON__

def load(name, dependencies=()):
    value = ModuleType(name.removesuffix('.py'))
    sys.modules[value.__name__] = value
    value.__dict__['__NOX_' + 'BUNDLE_JSON__'] = {key: BUNDLE[key] for key in dependencies}
    raw = base64.b64decode(BUNDLE[name], validate=True)
    exec(compile(raw, name, 'exec'), value.__dict__)
    return value

def emit(name, value):
    print(name + json.dumps(value, sort_keys=True, separators=(',', ':')), flush=True)

def hold(name, error):
    code = str(error)
    print(name + (code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', code) else type(error).__name__), flush=True)

def main():
    repair = load('owner_scoped_s03_pair_entry.py', (
        'owner_refresh_cognition_c04.py', 'nox_s03_scoped_pair.py', 'native-bridge.patch'))
    try:
        repair.main()
    except Exception as error:
        hold('NOX_MAINT_SCOPED_S03_PAIR_HOLD=', error)
    load('owner_quick_tunnel_launch.py')
    installer = load('owner_quick_chat_install.py')
    try:
        tunnel = installer.install_and_launch(base64.b64decode(BUNDLE['owner_resonance_gateway.py'], validate=True))
    except Exception as error:
        hold('NOX_MAINT_QUICK_CHAT_HOLD=', error)
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return
    emit('NOX_MAINT_QUICK_CHAT_TUNNEL=', tunnel)
    proof = load('owner_quick_chat_receipt.py')
    auth = load('owner_frozen_wow_route_auth.py')
    try:
        emit('NOX_MAINT_HTTPS_RESONANCE=', proof.prove(tunnel, auth.OwnerClient))
    except Exception as error:
        hold('NOX_MAINT_HTTPS_RESONANCE_HOLD=', error)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)

if __name__ == '__main__':
    main()
