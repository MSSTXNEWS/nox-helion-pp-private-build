#!/usr/bin/env python3
"""Read the failed trainer, install current chat evidence, test real browser UI."""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

STAGES = (
    ('owner_training_failure_probe.py', '56876b13f16729c7c6b706d10f354352a643521f7e598a0fa70fbf82a2846b3c'),
    ('owner_chat_evidence_entry.py', '39b397bd07ca870a8b0ebb433c2eea7ee91738c99dcdd296f334340ec7dd660a'),
    ('owner_browser_qa_entry.py', 'f31450ec85f7285784d8394e6a233bff4518d4ccb67d13457556032fb0507f28'),
)


def emit(kind, data):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def main():
    failed = []
    for name, expected in STAGES:
        if any((Path('/root/nox') / flag).exists() for flag in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP')):
            failed.append({'component': name, 'reason': 'HOLD_OWNER_STOP'})
            break
        try:
            raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
            if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != expected:
                raise RuntimeError('HOLD_FOLLOWUP_COMPONENT_PIN')
            module = types.ModuleType('nox_training_chat_' + name[:-3])
            module.__file__ = '/root/nox/scripts/' + name
            module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
            sys.modules[module.__name__] = module
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
            result = module.main()
            conventional_main = name == 'owner_browser_qa_entry.py' and result is None
            if not conventional_main and (type(result) is not int or result != 0):
                raise RuntimeError('HOLD_FOLLOWUP_COMPONENT_RESULT')
        except Exception as exc:
            value = str(exc)
            failed.append({'component': name, 'reason': value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', value) else type(exc).__name__})
            emit('training_chat_component_hold', failed[-1])
    emit('training_chat_followup', {'failed': failed, 'training_control_performed': False, 'private_content_exported': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
