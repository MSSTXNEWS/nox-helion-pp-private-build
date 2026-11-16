#!/usr/bin/env python3
"""Read back accepted media, diagnose memory identity, install live inventory and verify UI."""
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
    'owner_s03_activate_entry.py': '2a55d6ccf2a64e03b1f743680f2b8be5e3acdd7b4f46240f76f08f34da2594cb',
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_browser_qa_entry.py': 'ea9a6ee219b7662a8b1f203f666995fbf5551b92325b7d8468d57397a90e7d99',
}
STOP = tuple(Path('/root/nox') / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'state/STOP')) + (Path('/workspace/NOX_STOP'),)
MEDIA_RECEIPT = Path('/root/nox/state/owner_media_acceptance/accepted_6904718718.json')
MEDIA_SHA = 'f224353628c1aef7ac5ff70c9d74a0f4a1b82569bccb70ab59faf234bdbe4fdb'
ARTIFACTS = {
 '/root/nox/media/outputs/nox/42d0a67a275d41719fcf2e8768f2975d/image_00001_.png': (291929, '996e8f1aa156c82768ad3496508440be1a2c96a49fb285943904f12c79295ac2'),
 '/root/nox/media/outputs/nox/69c88f3914c77079db0f31af39c3b1a2/video_00001_.webm': (29349, '8f00e2b96cb170342af8a7cbd65d9ed938849c0a7dd7172d0f9c9dc56d86b135'),
}


def emit(kind, value):
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': kind, 'data': value}, separators=(',', ':')), flush=True)


def read(path, maximum):
    path = Path(path)
    if any(item.is_symlink() for item in (*path.parents, path)):
        raise RuntimeError('HOLD_READY_READ_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_size > maximum:
            raise RuntimeError('HOLD_READY_READ_FILE')
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = path.stat(follow_symlinks=False)
    if len(data) > maximum or any(getattr(before, k) != getattr(other, k)
        for other in (after, current) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
        raise RuntimeError('HOLD_READY_READ_CHANGED')
    return data


def media_readback():
    raw = read(MEDIA_RECEIPT, 131072)
    if hashlib.sha256(raw).hexdigest() != MEDIA_SHA:
        raise RuntimeError('HOLD_READY_MEDIA_RECEIPT_SHA')
    value = json.loads(raw)
    if (value.get('schema') != 'NOX_OWNER_MEDIA_ACCEPTANCE_V1'
        or value.get('request') != '6904718718'
        or value.get('source') != '4cfc1fc8fcab16a70d1c637ef4593ef2fc496f8a'
        or value.get('state') != 'GENERATED_DECODED_AND_GPU_RELEASED'):
        raise RuntimeError('HOLD_READY_MEDIA_RECEIPT_CONTEXT')
    for path, (size, digest) in ARTIFACTS.items():
        content = read(path, size)
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError('HOLD_READY_MEDIA_OUTPUT_SHA')
    emit('media_accepted_readback', {'receipt': str(MEDIA_RECEIPT), 'receipt_sha256': MEDIA_SHA,
        'current_artifact_files_full_sha_verified': 2, 'regenerated_jobs': 0, 'record': value})


def load(name):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    if len(raw) > 200000 or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise RuntimeError('HOLD_READY_COMPONENT_PIN')
    module = types.ModuleType('nox_ready_followup_' + name[:-3])
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
    actions = [('media_accepted_readback', media_readback)] + [(name, None) for name in PINS]
    for name, action in actions:
        if any(path.exists() or path.is_symlink() for path in STOP):
            failed.append({'component': name, 'reason': 'HOLD_OWNER_STOP'})
            break
        try:
            if action:
                action()
            else:
                module = load(name)
                if name == 'owner_s03_activate_entry.py':
                    value = module.identity_only_probe()
                    if not isinstance(value, dict) or value.get('request') != request or value.get('source_sha') != source:
                        raise RuntimeError('HOLD_READY_IDENTITY_DIAGNOSTIC')
                else:
                    result = module.main()
                    if result is not None and (type(result) is not int or result != 0):
                        raise RuntimeError('HOLD_READY_COMPONENT_RETURN')
            completed.append(name)
        except Exception as exc:
            value = str(exc)
            reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', value) else type(exc).__name__
            failed.append({'component': name, 'reason': reason})
            emit('ready_followup_component_hold', failed[-1])
    emit('ready_followup_result', {'request': request, 'source_sha': source, 'completed': completed,
        'failed': failed, 'memory_activated': False, 'training_started': False, 'media_regenerated': False})
    if not failed:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
