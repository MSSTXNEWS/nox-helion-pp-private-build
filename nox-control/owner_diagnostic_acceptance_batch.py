#!/usr/bin/env python3
"""Independent native memory diagnosis, real browser QA and adapter audit."""
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
    'owner_s03_activate_entry.py': '7be8a29b8b3f274eb22c7149723bec16c381b1601cc9490a89e57cb7301ad3bc',
    'owner_browser_qa_entry.py': '8d02d7cc38cfba3380528a1f71d07a51938a2e1a245580a0755b82ca7e40e0b4',
    'owner_adapter_lineage_audit.py': '99a8ca5f6a8e2340347bf3ac1b9964d493fe39500502c097ec266e69923a6e35',
}
STOP = tuple(Path('/root/nox') / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP')) + (Path('/workspace/NOX_STOP'),)


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, separators=(',', ':')), flush=True)


def load(name):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise RuntimeError('HOLD_DIAGNOSTIC_COMPONENT_PIN')
    module = types.ModuleType('nox_diagnostic_batch_' + name[:-3])
    module.__file__ = '/root/nox/scripts/' + name
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    sys.modules[module.__name__] = module
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    completed, failed = [], []
    for name in PINS:
        if any(path.exists() or path.is_symlink() for path in STOP):
            failed.append({'component': name, 'reason': 'HOLD_OWNER_STOP'})
            break
        try:
            module = load(name)
            if name == 'owner_s03_activate_entry.py':
                result = module.read_only_probe()
                if (not isinstance(result, dict) or result.get('schema') != 'NOX_OWNER_S03_RECALL_DIAGNOSTIC_V1'
                        or result.get('request') != request or result.get('source_sha') != source
                        or result.get('live_sources_changed') is not False):
                    raise RuntimeError('HOLD_S03_DIAGNOSTIC_RESULT')
                state = 'READ_ONLY_DIAGNOSTIC_RECORDED'
            else:
                result = module.main()
                if result is not None and (type(result) is not int or result != 0):
                    raise RuntimeError('HOLD_DIAGNOSTIC_COMPONENT_RETURN')
                state = 'REAL_BROWSER_ACCEPTANCE_PASSED' if name == 'owner_browser_qa_entry.py' else 'READ_ONLY_ADAPTER_AUDIT_COMPLETE'
            completed.append({'component': name, 'state': state})
        except Exception as exc:
            message = str(exc)
            reason = message if re.fullmatch('HOLD_[A-Z0-9_]+', message) else type(exc).__name__
            failed.append({'component': name, 'reason': reason})
            emit('diagnostic_component_hold', failed[-1])
    emit('diagnostic_batch_result', {'request': request, 'source_sha': source, 'completed': completed,
                                    'failed': failed, 'shared_memory_activated_by_this_batch': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
