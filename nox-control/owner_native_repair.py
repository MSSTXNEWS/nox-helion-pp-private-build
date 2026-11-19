"""Activate the native NOX V38 owner dialog in an authenticated maintenance run."""

import base64
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType


BUNDLE = __NOX_BUNDLE_JSON__
BUNDLE_MANIFEST = {'assets': {'owner_activate_native_cognition.py': 'eed24dfb7bebb104e43b9c1010d05c20f6179c4150717c4cdc3e2e808d346422', 'owner_cognition_patch.py': '43b08f711bc4a9c80f9dc470fbc1987166d70a195a61d2359dea7d53df04ae38', 'nox_v38_native_context.py': '175a44a09746beade0950fb9411ceb262bd6b2f7a69bf730a362cfd330004ccf', 'nox_v38_s03_native.py': 'c700f675f8b70a95bad04b0d58b4c836f4e0137797aaa89a18f8f46f64e8e44f'}, 'installed': {'chat_proxy.py': '9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3', 'nox_v29_chat_bridge.py': '29121089891a27a0ae28795d1240788421320743a17370858c4d53aca1789e8b', 'nox_v38_native_context.py': '175a44a09746beade0950fb9411ceb262bd6b2f7a69bf730a362cfd330004ccf', 'nox_v38_s03_native.py': 'c700f675f8b70a95bad04b0d58b4c836f4e0137797aaa89a18f8f46f64e8e44f'}}
INSTALLED_MANIFEST = '1b296411a4b9e297f285fb8a67c8cd0555e85bbed561d1a55fdcb94b6cdcd683'
BRAIN = Path('/root/nox/ops/nox-brain-v38')
BRAIN_FILES = frozenset(('__init__.py', 'synaptic_brain.py', 'native_bridge_v38.py', 'durable_runtime.py'))


def digest(raw):
    return sha256(raw).hexdigest()


def module(name, source):
    value = ModuleType(name)
    sys.modules[name] = value
    exec(compile(source, name + '.py', 'exec'), value.__dict__)
    return value


def main():
    if set(BUNDLE) != set(BUNDLE_MANIFEST['assets']):
        raise RuntimeError('HOLD_COGNITION_BUNDLE_SCOPE')
    raw = {name: base64.b64decode(value, validate=True) for name, value in BUNDLE.items()}
    if any(digest(data) != BUNDLE_MANIFEST['assets'][name] for name, data in raw.items()):
        raise RuntimeError('HOLD_COGNITION_BUNDLE_PIN')
    control = module('owner_activate_native_cognition', raw.pop('owner_activate_native_cognition.py'))
    patch = module('owner_cognition_patch', raw.pop('owner_cognition_patch.py'))
    with ExitStack() as stack:
        release = control.directory(stack, BRAIN)
        manifest, _ = control.read(release, 'release.json')
        if manifest is None or digest(manifest) != INSTALLED_MANIFEST:
            raise RuntimeError('HOLD_COGNITION_BRAIN_MANIFEST')
        package = control.directory(stack, BRAIN / 'v38')
        pins = json.loads(manifest)['files_sha256']
        for name in BRAIN_FILES:
            data, _ = control.read(package, name)
            if data is None or digest(data) != pins['v38/' + name]:
                raise RuntimeError('HOLD_COGNITION_BRAIN_MODULE')
    for name, old in control.current_patch_preimages().items():
        raw[name] = patch.transform(name, old)
    receipt = control.activate(payloads=raw, sha256=BUNDLE_MANIFEST['installed'])
    print('NOX_MAINT_COGNITION_ACTIVE=' + json.dumps(receipt, separators=(',', ':'), sort_keys=True))


if __name__ == '__main__':
    main()
