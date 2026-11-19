#!/usr/bin/env python3
"""Bind verified Qwen status, then refresh the existing dispatcher callback."""
import base64
import hashlib
import json
import os
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRIES = (
    ('owner_qwen_training_status_entry.py', '4610f1eece18307bdbfef7b7895f2d78deee059d4afd6e75c80914cfc8a36781'),
    ('owner_subagent_fresh_install_entry.py', '670cad05144157a4a2294dbdb07fee7504346587120275c8c85649c5253f2fd4'),
)
CONTEXT = {
    'request': '6907513913',
    'source_sha': '4d5f0b065309f3524dc4d5d08d3924a4d0223931',
    'receipt_sha256': '4547158a490e9c367a6f59f0936f6c0ae3836d40a797fe47b1f303dae38f4308',
}


def prepared():
    values = []
    for name, pin in ENTRIES:
        raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
        if not raw or len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != pin:
            raise RuntimeError('HOLD_QWEN_STATUS_DISPATCHER_BATCH_SOURCE')
        module = types.ModuleType('_reviewed_' + name[:-3])
        exec(compile(raw, name, 'exec'), module.__dict__)
        module.BUNDLE = BUNDLE
        values.append(module)
    # Validate both complete dependency closures before either installer runs.
    values[0].configure().dependencies()
    values[1].load_helpers()
    return values


def main():
    modules = prepared()
    os.environ['NOX_TRAINING_RECOVERY_CONTEXT'] = json.dumps(CONTEXT, sort_keys=True)
    for module in modules:
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
        if not re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+', reason):
            reason = 'HOLD_QWEN_STATUS_DISPATCHER_BATCH_' + type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_status_dispatcher_batch_hold',
              'data': {'reason': reason}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
