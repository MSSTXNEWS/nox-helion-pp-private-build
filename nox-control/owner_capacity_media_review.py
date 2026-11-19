#!/usr/bin/env python3
"""Measure the current BOOST profile and export only encrypted public QA fixtures."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PINS = {
    'owner_media_fixture_export.py': '749147c08f158b93b5f4e20e0ef79257ee00f0844ccf64413d52154cb02e4388',
    'owner_capacity_measure_entry.py': '6fafe435ac6d93417fbce76ec38c74c65e016d38e223d7e8ec5084444f9592e3',
}


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def main():
    os.environ['NOX_CAPACITY_MODE'] = 'TASK_BOOST'
    failed = []
    for name, pin in PINS.items():
        if any((Path('/root/nox') / flag).exists() for flag in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP')):
            failed.append({'component': name, 'reason': 'HOLD_OWNER_STOP'})
            break
        try:
            raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
            if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != pin:
                raise RuntimeError('HOLD_REVIEW_COMPONENT_PIN')
            module = types.ModuleType('nox_capacity_media_' + name[:-3])
            module.__file__ = '/root/nox/scripts/' + name
            module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
            sys.modules[module.__name__] = module
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
            result = module.main()
            if type(result) is not int or result != 0:
                raise RuntimeError('HOLD_REVIEW_COMPONENT_RESULT')
        except Exception as exc:
            value = str(exc)
            failed.append({'component': name, 'reason': value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', value) else type(exc).__name__})
            emit('capacity_media_component_hold', failed[-1])
    emit('capacity_media_batch', {'failed': failed, 'training_started': False, 'plain_media_exported': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
