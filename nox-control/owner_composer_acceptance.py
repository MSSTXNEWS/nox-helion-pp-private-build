#!/usr/bin/env python3
"""Install bounded report layout and require a real native browser stream."""
import base64
import hashlib
import json
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

STAGES = (
    ('owner_chat_composer_entry.py', '2063208d885654244f54a33f75d60be2169df763bf1bf027505b57c915c5b930'),
    ('owner_browser_qa_entry.py', '39da4fd758c48269a6c9ca1bfb1412f2214b3e2aa1bcab371a2550acafb2a9b0'),
)


def main():
    for name, expected in STAGES:
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError('HOLD_COMPOSER_ACCEPTANCE_PIN')
        module = types.ModuleType('nox_composer_' + name[:-3])
        module.__file__ = '/root/nox/scripts/' + name
        module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
        sys.modules[module.__name__] = module
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        result = module.main()
        if name == 'owner_browser_qa_entry.py' and result is None:
            continue
        if type(result) is not int or result != 0:
            raise RuntimeError('HOLD_COMPOSER_COMPONENT_RESULT')
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc) if str(exc).startswith('HOLD_') and len(str(exc)) < 160 else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'composer_acceptance_hold', 'data': {'reason': reason}}), flush=True)
        raise SystemExit(2)
