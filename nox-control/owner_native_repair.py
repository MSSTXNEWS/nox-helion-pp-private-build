"""Activate the native NOX V38 owner dialog in an authenticated maintenance run."""

import base64
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType


BUNDLE = __NOX_BUNDLE_JSON__
BUNDLE_MANIFEST = {'assets': {'owner_refresh_cognition_c02_stop.py': '2a6f8c1655af53b03f0e29b5c64616ebff8a525e7581b5b3fa1501c8a489cbee', 'owner_ndjson_stop_patch.py': '6dc38439d3688c1575ceabdb68c1ec158ab8a13960e777d1cd09ae1e43258ce5', 'nox_v38_native_context.py': '1c45cedb5a775a550563107f16707b7c667113d811f48604d5b75d9259aa8390', 'nox_v38_s03_native.py': 'ea4cea470c196973d0c83f4edc0172b5758992febc63d231f1235e18364ab7f0', 'owner_previous_product_dialog.py': 'bdfb1f585222eb4ee4ded231f1ebbbaefa87ee2061edca5a646927e1ff50f940'}, 'installed': {'nox_v29_chat_bridge.py': 'f9163a748c969198b990cd98d7366fa2eaba69eb97c44f5fa8ea4d5d7a10bdcf', 'nox_v38_native_context.py': '1c45cedb5a775a550563107f16707b7c667113d811f48604d5b75d9259aa8390', 'nox_v38_s03_native.py': 'ea4cea470c196973d0c83f4edc0172b5758992febc63d231f1235e18364ab7f0'}}
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
    control = module('owner_refresh_cognition_c02_stop', raw.pop('owner_refresh_cognition_c02_stop.py'))
    patch = module('owner_ndjson_stop_patch', raw.pop('owner_ndjson_stop_patch.py'))
    dialog_module = module('owner_previous_product_dialog', raw.pop('owner_previous_product_dialog.py'))
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
    bridge = 'nox_v29_chat_bridge.py'
    raw[bridge] = patch.transform(bridge, control.current_patch_preimages()[bridge])
    receipt = control.activate(payloads=raw, sha256=BUNDLE_MANIFEST['installed'])
    print('NOX_MAINT_COGNITION_ACTIVE=' + json.dumps(receipt, separators=(',', ':'), sort_keys=True))
    try:
        status = dialog_module.resume_product_dialog()
        print('NOX_MAINT_COGNITION_DIALOG=' + json.dumps(status, separators=(',', ':'), sort_keys=True), flush=True)
    except Exception as error:
        reason = str(error)
        import re
        print('NOX_MAINT_COGNITION_DIALOG_HOLD=' + (reason if re.fullmatch(r'HOLD_SMART_CHAT_QA_[A-Z0-9_]{1,100}', reason) else type(error).__name__), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
