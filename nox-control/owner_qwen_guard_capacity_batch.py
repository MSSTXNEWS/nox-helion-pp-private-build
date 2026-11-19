#!/usr/bin/env python3
"""Install the inactive guard, then measure current inference concurrency."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRIES = (
    ('owner_qwen_guard_install_entry.py', '8eb645c63a132b690cbd25220241fef86c43070a531327881aed4e486ee422e5'),
    ('owner_capacity_current_load_entry.py', 'd7e2dc220af614cf1cfe5f8341a469e0d17e615d40c7165fc53f712c931ce6c3'),
)


def prepared():
    result = []
    for name, pin in ENTRIES:
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if not 0 < len(raw) <= 262144 or hashlib.sha256(raw).hexdigest() != pin:
            raise RuntimeError('HOLD_QWEN_GUARD_CAPACITY_BATCH_PIN')
        value = types.ModuleType('_reviewed_' + name[:-3])
        exec(compile(raw, name, 'exec'), value.__dict__)
        value.BUNDLE = BUNDLE; result.append(value)
    # Resolve the exact definition-only dependency closures before mutations.
    result[0].helpers(result[0].bundle())
    result[1].helpers()
    return result


def main():
    for module in prepared():
        code = module.main()
        if code != 0:
            print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
            return 2
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', reason):
            reason = 'HOLD_QWEN_GUARD_CAPACITY_BATCH_UNVERIFIED'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_guard_capacity_batch_hold',
              'data': {'reason': reason}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
