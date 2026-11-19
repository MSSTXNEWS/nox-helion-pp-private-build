#!/usr/bin/env python3
"""Install exact reviewed bridge helpers and consume one sealed URL envelope.

The owner operator supplies a source-pinned BUNDLE. Its public repository copy
contains ciphertext only. Unknown existing helper bytes are never overwritten.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import tempfile

BUNDLE = __NOX_BUNDLE_JSON__
ENVELOPE_SHA256 = '36c5ec5dc1f7e0067e262810f4c0c970088daeb6ee9619ca46f9fd471d04d84f'
SCRIPTS = Path('/root/nox/scripts')
PINS = {
    'owner_drive_ram_prepare.py': 'dadd732db4db231be625a72606f85509c1c9b3fc519c1f71d7a11c99ca48ce43',
    'owner_drive_ram_bridge.py': '57893b187155b12c08b3ca0612a62397d117218302d448994a346c84f556b786',
    'owner_drive_ram_assets.json': '1910d8b09393f13af1749759509de5cc44f9347faf9b50d2c321377fc267b199',
}


def fail(code):
    raise RuntimeError(code)


def plain(path):
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            fail('HOLD_DRIVE_ENTRY_SYMLINK')
    return path


def read(path, maximum=65536):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > maximum):
            fail('HOLD_DRIVE_ENTRY_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            value = stream.read(maximum + 1)
        if len(value) > maximum:
            fail('HOLD_DRIVE_ENTRY_FILE_LIMIT')
        return value
    finally:
        os.close(fd)


def unpack(name, expected, maximum=65536):
    encoded = BUNDLE.get(name)
    if not isinstance(encoded, str) or len(encoded) > 4 * ((maximum + 2) // 3):
        fail('HOLD_DRIVE_ENTRY_BUNDLE_LIMIT')
    try:
        value = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        fail('HOLD_DRIVE_ENTRY_BUNDLE_ENCODING')
    if len(value) > maximum or hashlib.sha256(value).hexdigest() != expected:
        fail('HOLD_DRIVE_ENTRY_BUNDLE_PIN')
    return value


def install(name, data):
    if name not in PINS or hashlib.sha256(data).hexdigest() != PINS[name]:
        fail('HOLD_DRIVE_ENTRY_INSTALL_SCOPE')
    folder = plain(SCRIPTS)
    info = folder.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        fail('HOLD_DRIVE_ENTRY_DIRECTORY')
    target = plain(folder / name)
    if target.exists():
        if read(target) != data:
            fail('HOLD_DRIVE_ENTRY_UNKNOWN_EXISTING_SOURCE')
        return
    fd, temporary = tempfile.mkstemp(prefix='.drive-source-', dir=folder)
    try:
        os.fchmod(fd, 0o755 if name.endswith('.py') else 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if read(target) != data:
                fail('HOLD_DRIVE_ENTRY_SOURCE_APPEARED')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if read(target) != data:
        fail('HOLD_DRIVE_ENTRY_SOURCE_READBACK')


def main():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        fail('HOLD_OWNER_CONTEXT')
    if not re.fullmatch('[a-f0-9]{64}', ENVELOPE_SHA256):
        fail('HOLD_DRIVE_ENTRY_ENVELOPE_NOT_PINNED')
    envelope_raw = unpack('owner_drive_ram_envelope.json', ENVELOPE_SHA256, 262144)
    envelope = json.loads(envelope_raw)
    sources = {name: unpack(name, expected) for name, expected in PINS.items()}
    for name, data in sources.items():
        if name.endswith('.py'):
            compile(data, str(SCRIPTS / name), 'exec')
    for name, data in sources.items():
        install(name, data)
    name = 'owner_drive_ram_bridge.py'
    spec = importlib.util.spec_from_loader('nox_drive_ram_bridge_pinned', loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SCRIPTS / name)
    exec(compile(sources[name], module.__file__, 'exec'), module.__dict__)
    return module.run_envelope(envelope)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]+', code):
            code = 'HOLD_DRIVE_ENTRY'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_ram_transfer',
                                             'data': {'phase': 'held', 'error': code}}, separators=(',', ':')), flush=True)
        raise SystemExit(2)
