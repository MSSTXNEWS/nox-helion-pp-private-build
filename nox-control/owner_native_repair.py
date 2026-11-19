"""Activate the native NOX V38 owner dialog in an authenticated maintenance run."""

import base64
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import ModuleType


BUNDLE = __NOX_BUNDLE_JSON__
BUNDLE_MANIFEST = {'assets': {'owner_refresh_cognition_c04.py': 'fdd6e646c8cef1fad9a6d39afa2723375fa2e6126bf4da4989b751ffc2355de0', 'nox_v38_native_context.py': '451aa75d323c4429767f8a886300c90941adc59f30b395fec15c1f29b60d3180', 'owner_previous_product_dialog.py': '205a9bae92ad60e64d16de05faea8ba921383f681eb528b08226aeacfbcc38c3', 'owner_stage_native_drive_payload.py': '25649ad8b4ea5430cc2ddcfa74fe432030b4893bf427ebcbc16364e835d6a255'}, 'installed': {'nox_v38_native_context.py': '451aa75d323c4429767f8a886300c90941adc59f30b395fec15c1f29b60d3180'}}
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
    control = module('owner_refresh_cognition_c04', raw.pop('owner_refresh_cognition_c04.py'))
    drive = module('owner_stage_native_drive_payload', raw.pop('owner_stage_native_drive_payload.py'))
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
    receipt = control.activate(payloads=raw, sha256=BUNDLE_MANIFEST['installed'])
    print('NOX_MAINT_COGNITION_ACTIVE=' + json.dumps(receipt, separators=(',', ':'), sort_keys=True))
    try:
        status = dialog_module.resume_product_dialog()
        print('NOX_MAINT_COGNITION_DIALOG=' + json.dumps(status, separators=(',', ':'), sort_keys=True), flush=True)
    except Exception as error:
        reason = str(error)
        import re
        print('NOX_MAINT_COGNITION_DIALOG_HOLD=' + (reason if re.fullmatch(r'HOLD_SMART_CHAT_QA_[A-Z0-9_]{1,100}', reason) else type(error).__name__), flush=True)
    import time
    deadline = time.monotonic() + 18
    while True:
        try:
            drive.main()
            break
        except drive.Hold as error:
            code = str(error)
            if code != 'HOLD_NATIVE_DRIVE_STAGE_OWNER_LEASE_BUSY' or time.monotonic() >= deadline:
                print('NOX_MAINT_NATIVE_DRIVE_HOLD=' + code, flush=True)
                break
            time.sleep(0.2)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
