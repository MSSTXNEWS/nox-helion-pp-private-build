"""Read the active web/edge binding and repair exact scoped S03 turn persistence."""
import base64
import hashlib
import json
import re
import sys
from types import ModuleType

BUNDLE = __NOX_BUNDLE_JSON__

def load(name, dependencies=()):
    raw = base64.b64decode(BUNDLE[name], validate=True)
    module = ModuleType(name.removesuffix('.py'))
    module.BUNDLE = {asset: BUNDLE[asset] for asset in dependencies}
    sys.modules[module.__name__] = module
    exec(compile(raw, name, 'exec'), module.__dict__)
    return module

def hold(marker, error):
    code = str(error)
    print(marker + (code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', code) else type(error).__name__), flush=True)

def main():
    portal = load('owner_vast_chat_portal_observe.py')
    if portal.main():
        raise RuntimeError('HOLD_PORTAL_OWNER_BINDING')
    matrix = load('owner_wow_served_asset_receipt.py', ('owner_media_acceptance_entry.py',))
    matrix.BUNDLE = {'owner_media_acceptance_entry.py': BUNDLE['owner_media_acceptance_entry.py']}
    matrix.OPTIONAL += ('nox-choice-pill-v5.css', 'nox-choice-pill-v5.js')
    record = {'schema': 'NOX_WOW_SERVED_ASSET_MATRIX_V1', 'assets': []}
    try:
        matrix.main(record)
        record['state'] = 'AUTHENTICATED_CURRENT_STATIC_MATRIX'
    except Exception as error:
        record['state'] = 'HOLD'
        hold('NOX_MAINT_WOW_MATRIX_HOLD=', error)
    print('NOX_MAINT_WOW_MATRIX=' + json.dumps(record, separators=(',', ':'), sort_keys=True), flush=True)
    repair = load('owner_scoped_s03_pair_entry.py')
    repair.BUNDLE = {key: BUNDLE[key] for key in repair.ASSETS}
    try:
        repair.main()
    except Exception as error:
        hold('NOX_MAINT_SCOPED_S03_PAIR_HOLD=', error)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)

if __name__ == '__main__':
    main()
