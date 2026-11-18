"""Deterministically rebuild the frozen existing-route native payload."""
from pathlib import Path
import base64
import hashlib
import json
import zlib

ROOT = Path(__file__).resolve().parent
INPUTS = {
    'installer':('delivery/native_current_recovery_install.py','5fe28f37a81069c4e0b69d78e0ef9c41e9eade3fb7c4d94b2f8e7e7ef7f293ce'),
    'composer':('delivery/prepare_current_recovery_install.py','a6f1eac524e026fd424af7fb59a9132f53017d2653111b7e58cb665bc2e44f47'),
    'dispatcher':('repo/owner_subagent_dispatcher.py','5f134b8b1915851de15318e23885951885ca84d6515ca1e48c56286862830db5'),
}
EXPECTED_PAYLOAD = '18233bbc4f569c2d20caea6990c42394eaa47715c881fce194f805885e8774ea'


def build():
    sources = {}
    for name,(relative,expected) in INPUTS.items():
        raw = (ROOT/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('HOLD_BUILD_SOURCE_PIN_'+name)
        sources[name] = raw
    pins = {name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in sources.items()}
    body = json.dumps({name:base64.b64encode(raw).decode() for name,raw in sources.items()},
                      sort_keys=True,separators=(',',':')).encode()
    if len(body) >= 200000:
        raise ValueError('HOLD_BUILD_BOUND')
    packed = base64.b85encode(zlib.compress(body,9)).decode()
    script = '''#!/usr/bin/env python3
"""Immutable scoped owner repair; no operator/route/permission changes."""
import base64, hashlib, json, sys, types, zlib
_EXPECTED = '''+repr(pins)+'''
_PACKED = '''+repr(packed)+'''
def _main():
    decoder = zlib.decompressobj()
    raw = decoder.decompress(base64.b85decode(_PACKED), 200001)
    if len(raw) > 200000 or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise RuntimeError('HOLD_RECOVERY_EMBEDDED_BOUND')
    value = json.loads(raw)
    if set(value) != set(_EXPECTED):
        raise RuntimeError('HOLD_RECOVERY_EMBEDDED_FILESET')
    sources = {}
    for name, encoded in value.items():
        source = base64.b64decode(encoded, validate=True)
        if len(source) != _EXPECTED[name]['bytes'] or hashlib.sha256(source).hexdigest() != _EXPECTED[name]['sha256']:
            raise RuntimeError('HOLD_RECOVERY_EMBEDDED_PIN')
        compile(source, name+'.py', 'exec')
        sources[name] = source
    modules = {}
    for name in ('composer','installer'):
        module = types.ModuleType('_nox_current_recovery_'+name)
        module.__file__ = '<owner-current-recovery/'+name+'.py>'
        sys.modules[module.__name__] = module
        exec(compile(sources[name], module.__file__, 'exec'), module.__dict__)
        modules[name] = module
    modules['installer'].COMPOSER = modules['composer']
    modules['installer'].DISPATCHER_SOURCE = sources['dispatcher']
    modules['installer'].main()
if __name__ == '__main__':
    _main()
'''
    raw = script.encode()
    if len(raw) >= 125000 or hashlib.sha256(raw).hexdigest() != EXPECTED_PAYLOAD:
        raise ValueError('HOLD_BUILD_PAYLOAD_PIN')
    compile(raw,'owner_current_four_queue_recovery_payload.py','exec')
    path = ROOT/'delivery/owner_current_four_queue_recovery_payload.py'
    if not path.exists():
        path.write_bytes(raw)
    elif path.read_bytes() != raw:
        raise ValueError('HOLD_BUILD_EXISTING_PAYLOAD_DRIFT')
    return {'sha256':EXPECTED_PAYLOAD,'bytes':len(raw),'embedded_files':len(sources)}


if __name__ == '__main__':
    print(json.dumps(build(),sort_keys=True))
