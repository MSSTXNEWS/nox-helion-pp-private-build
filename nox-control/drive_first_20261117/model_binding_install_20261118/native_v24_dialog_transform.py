"""Compatibility adapter for the unchanged successful OneHost installer base.

The old module name is retained only for its import ABI. All three source
pre/postimages are exact-reviewed current revisions. The UI reader is bound by
the installer to the same existing no-follow stable_read implementation.
"""
from pathlib import Path
import hashlib

import source_transform as identity
import native_menu_overlay_transform as menu

UI_PATH = Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-ui.js')
UI_READER = None
TRANSFORMS = {
    'chat_proxy.py': {'before_sha256': identity.PINS['chat_proxy.py'], 'before_bytes': 103637,
                     'after_sha256': '30207a85eed6c87df4a6ee4dd8614442a62622eefacac7fae822b23ad385b343', 'after_bytes': 103831},
    'owner_chat_stream.py': {'before_sha256': identity.PINS['owner_chat_stream.py'], 'before_bytes': 26210,
                           'after_sha256': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09', 'after_bytes': 26955},
    'nox_v29_chat_bridge.py': {'before_sha256': menu.BRIDGE_BEFORE_SHA256, 'before_bytes': menu.BRIDGE_BEFORE_BYTES,
                             'after_sha256': menu.BRIDGE_AFTER_SHA256, 'after_bytes': menu.BRIDGE_AFTER_BYTES},
}


def transform(name, raw, rollback=False):
    if name not in TRANSFORMS or type(rollback) is not bool:
        raise ValueError('HOLD_MODEL_BINDING_TRANSFORM_SCOPE')
    pins = TRANSFORMS[name]
    side = 'after' if rollback else 'before'
    if hashlib.sha256(raw).hexdigest() != pins[side + '_sha256'] or len(raw) != pins[side + '_bytes']:
        raise ValueError('HOLD_MODEL_BINDING_PREIMAGE')
    if name == 'nox_v29_chat_bridge.py':
        if UI_READER is None:
            raise ValueError('HOLD_MODEL_BINDING_UI_READER_UNBOUND')
        candidate = menu.transform(raw, UI_READER(UI_PATH, 65536)[0], rollback=rollback)
    elif rollback:
        candidate = identity._replace(raw.decode(), [(new, old) for old, new in reversed(identity.EDITS[name])]).encode()
        if identity.transform(name, candidate) != raw:
            raise ValueError('HOLD_MODEL_BINDING_INVERSE')
    else:
        candidate = identity.transform(name, raw)
    target = 'before' if rollback else 'after'
    if hashlib.sha256(candidate).hexdigest() != pins[target + '_sha256'] or len(candidate) != pins[target + '_bytes']:
        raise ValueError('HOLD_MODEL_BINDING_POSTIMAGE')
    compile(candidate, name, 'exec')
    return candidate
