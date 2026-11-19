#!/usr/bin/env python3
"""Finite owner transition: semantic memory, original chat layout, browser proof."""
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
    ('owner_s03_recover_activate.py', '55fbbb2bbdf346cb68dc8fc55594fe1971609a182c26ce2ff8b097cad9831a14'),
    ('owner_chat_layout_entry.py', '038ef7025b69be1c8cedfe26d90615f67705e233daf132b0afd91ccf4f9d162b'),
    ('owner_browser_qa_entry.py', '7baa663b475fee7bd8abd2d0b1348becf5a257fdfad04792a6ba8185fbbc5042'),
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
                raise RuntimeError('HOLD_ACCEPTANCE_COMPONENT_PIN')
            module = types.ModuleType('nox_memory_chat_' + name[:-3])
            module.__file__ = '/root/nox/scripts/' + name
            module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
            sys.modules[module.__name__] = module
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
            result = module.main()
            conventional_main = name == 'owner_browser_qa_entry.py' and result is None
            if not conventional_main and (type(result) is not int or result != 0):
                raise RuntimeError('HOLD_ACCEPTANCE_COMPONENT_RESULT')
        except (Exception, SystemExit) as exc:
            # A bundled stage can call sys.exit(0) before any durable S03
            # receipt is written. Never accept that as owner batch completion.
            value = str(exc)
            reason = ('HOLD_ACCEPTANCE_COMPONENT_SYSTEM_EXIT' if isinstance(exc, SystemExit)
                      else value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', value) else type(exc).__name__)
            failed.append({'component': name, 'reason': reason})
            emit('memory_chat_component_hold', failed[-1])
            # All later stages depend on S03 recovery and ordered owner acceptance.
            # Never mutate the chat layout or start browser QA after a failed stage.
            break
    emit('memory_chat_batch', {'failed': failed, 'training_started': False, 'private_content_exported': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
