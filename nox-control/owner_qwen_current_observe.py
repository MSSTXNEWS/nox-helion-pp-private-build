#!/usr/bin/env python3
"""Pinned read-only observation of the actually started guarded1000 window."""
import base64
import hashlib
import json
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRY = 'owner_qwen_window_observe_entry.py'
ENTRY_SHA = '3bfc67e5a88657400c27b09f8802f46ea8b1fe1c8c6f80b35295f074c240d962'
WINDOW_CONTEXT = {
    'request': '6908281920',
    'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
    'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662',
}


def main():
    value = BUNDLE.get(ENTRY)
    if not isinstance(value, str) or len(value) > 1024 ** 2:
        raise RuntimeError('HOLD_QWEN_CURRENT_OBSERVER_BUNDLE_BOUND')
    raw = base64.b64decode(value, validate=True)
    if hashlib.sha256(raw).hexdigest() != ENTRY_SHA:
        raise RuntimeError('HOLD_QWEN_CURRENT_OBSERVER_PIN')
    module = types.ModuleType('_nox_current_guarded_qwen_observer')
    module.__file__ = '/root/nox/scripts/' + ENTRY
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module.main(dict(WINDOW_CONTEXT))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_window1000_observation',
              'data': {'state': 'HOLD', 'reason': 'HOLD_QWEN_CURRENT_OBSERVER_UNVERIFIED', 'read_only': True}}), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
