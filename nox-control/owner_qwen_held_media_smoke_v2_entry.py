#!/usr/bin/env python3
"""One image acceptance bound to the verified second rollback receipt."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

NAME = 'owner_qwen_held_media_smoke_v2.py'
SOURCE_SHA = '8339a216b49482096d8be02ad0fdec583ca5fa69196a59bc5a25f5fd13f88933'
ROLLBACK_REFERENCE = {
    'request': '6913049268',
    'source_sha': 'a0fe9630a469713919a38c0542dc7116ae3e2d9f',
    'receipt_sha256': 'bad7e57d3934c433bc0709a12351ab6df3cfd83110b8cc031544395bc9ff5353',
}


def main():
    encoded = BUNDLE.get(NAME)
    if not isinstance(encoded, str) or not 0 < len(encoded) < 131072:
        raise RuntimeError('HOLD_QWEN_HELD_MEDIA_ENTRY_BUNDLE')
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('HOLD_QWEN_HELD_MEDIA_ENTRY_SOURCE_PIN')
    module = types.ModuleType('_nox_exact_held_media_smoke')
    module.__file__ = '/root/nox/scripts/' + NAME
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module.main(ROLLBACK_REFERENCE)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', value) else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_held_media_smoke_entry',
              'data': {'state': 'HOLD', 'reason': reason}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
