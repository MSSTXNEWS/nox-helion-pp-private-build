#!/usr/bin/env python3
"""Activate the prepared shared memory and verify the actual chat UI."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

PINS = {
    'owner_s03_activate_entry.py': 'b33697bd57f8338527da3ffca4b3529c440bcb683a65b1dd5b70891b2c21dacb',
    'owner_browser_qa_entry.py': '8d02d7cc38cfba3380528a1f71d07a51938a2e1a245580a0755b82ca7e40e0b4',
}


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, separators=(',', ':')), flush=True)


def load(name):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise RuntimeError('HOLD_MEMORY_UI_ENTRY_PIN')
    module = types.ModuleType('nox_memory_ui_' + name[:-3])
    module.__file__ = '/root/nox/scripts/' + name
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    sys.modules[module.__name__] = module
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def receipt_context():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_MEMORY_UI_OWNER_CONTEXT')
    path = Path('/root/nox/state/owner_s03') / ('activation_' + request + '.json')
    if any(part.is_symlink() for part in (*path.parents, path)):
        raise RuntimeError('HOLD_MEMORY_UI_RECEIPT_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
            raise RuntimeError('HOLD_MEMORY_UI_RECEIPT_SIZE')
        raw = stream.read(524289)
    value = json.loads(raw)
    if (value.get('request') != request or value.get('source_sha') != source
            or value.get('state') != 'LIVE_SHARED_SEMANTIC_MEMORY_AND_NATIVE_INDEX_VERIFIED'):
        raise RuntimeError('HOLD_MEMORY_UI_RECEIPT_CONTEXT')
    return {'request': request, 'source_sha': source,
            'receipt_sha256': hashlib.sha256(raw).hexdigest(),
            'state': value['state'], 'path': str(path)}


def main():
    os.environ['NOX_S03_PREPARE_REQUEST'] = '6904379098'
    os.environ['NOX_S03_PREPARE_SHA256'] = 'f6be4b08c1eb3a053b65c977479367354ffa31a50d479ce527b42e096929981c'
    for name in PINS:
        module = load(name)
        result = module.main()
        if type(result) is not int or result != 0:
            emit('memory_ui_component_hold', {'component': name, 'returncode': result})
            return 2
        if name == 'owner_s03_activate_entry.py':
            emit('s03_activation_context', receipt_context())
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        emit('memory_ui_hold', {'reason': value if re.fullmatch('HOLD_[A-Z0-9_]+', value) else type(exc).__name__})
        raise SystemExit(2)
