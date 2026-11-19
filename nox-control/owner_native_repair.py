"""Activate and verify the owner-scoped Drive conversation route."""

from base64 import b64decode
import json
import re
import sys
from types import ModuleType


BUNDLE = r'''__NOX_BUNDLE_JSON__'''
ACTIVATION = 'owner_drive_proxy_activation'
CONTROL = 'owner_refresh_cognition_c04.py'
ROUTE = 'owner_drive_chat_route'
HELPERS = ('nox_dialog_followup', 'owner_drive_chat_health', 'owner_native_drive_probe')


def load_module(name, files):
    module = ModuleType(name)
    module.__file__ = name + '.py'
    sys.modules[name] = module
    exec(compile(files[module.__file__], module.__file__, 'exec'), module.__dict__)
    return module


def main():
    encoded = json.loads(BUNDLE)
    expected = {CONTROL, *(name + '.py' for name in (*HELPERS, ROUTE, ACTIVATION))}
    if set(encoded) != expected:
        raise RuntimeError('HOLD_DRIVE_CHAT_BUNDLE_SCOPE')
    files = {name: b64decode(value, validate=True) for name, value in encoded.items()}
    for name in HELPERS:
        load_module(name, files)
    activation = load_module(ACTIVATION, files)
    route = load_module(ROUTE, files)
    receipt = activation.activate(files[CONTROL], route.transform_proxy,
                                  {name: files[name] for name in activation.COMPANIONS})
    activation.emit(receipt)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error)
        if not re.fullmatch(r'HOLD_[A-Z0-9_]{1,120}', reason):
            reason = 'HOLD_DRIVE_CHAT_ACTIVATION'
        print('NOX_MAINT_RESULT=' + reason, flush=True)
        raise SystemExit(2) from None
