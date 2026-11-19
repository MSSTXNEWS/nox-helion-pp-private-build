#!/usr/bin/env python3
"""Inspect the exact media retry, then activate the reviewed Qwen continuation."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

GUARD_INSTALL = {"request":"6908244757","source_sha":"e22edc20f3feb19b438597c78736d467298dfc20","receipt_sha256":"a128adc426b747b72ac03573ea37dcb34011d07c5b73b37ccfd332a3319c08b3"}
ENTRIES = (
    ('owner_qwen_media_retry_observe.py', 'fce01bca74751ee01a993eba7aa8874b4fc58cb2a8b9656212d0d17923ad4018'),
    ('owner_qwen_guard_activate_entry.py', 'fd7700c453e4c91134b08d82a8393c48d66954ddef90a8052cda390a76aeb762'),
)


def prepared():
    modules = []
    for name, pin in ENTRIES:
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if not 0 < len(raw) <= 262144 or hashlib.sha256(raw).hexdigest() != pin:
            raise RuntimeError('HOLD_QWEN_GUARDED_CONTINUE_SOURCE_PIN')
        value = types.ModuleType('_reviewed_' + name[:-3])
        exec(compile(raw, name, 'exec'), value.__dict__)
        value.BUNDLE = BUNDLE
        modules.append(value)
    return modules


def main():
    observation, activation = prepared()
    if observation.main() != 0:
        return 2
    return activation.main(GUARD_INSTALL)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', reason):
            reason = 'HOLD_QWEN_GUARDED_CONTINUE_UNVERIFIED'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_guarded_continue_hold',
              'data': {'reason': reason}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
