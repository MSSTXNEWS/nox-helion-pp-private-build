#!/usr/bin/env python3
"""Continue only the admitted checkpoint25 bootstrap; never restart a trainer."""
import hashlib
import json
from pathlib import Path
import re
import types

PATH = Path('/root/nox/scripts/owner_qwen_revision_install.py')
PIN = '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468'


def main():
    if any(p.is_symlink() for p in (*PATH.parents, PATH)):
        raise RuntimeError('HOLD_REVISION_FINALIZE_SOURCE_PATH')
    raw = PATH.read_bytes()
    if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != PIN:
        raise RuntimeError('HOLD_REVISION_FINALIZE_SOURCE_PIN')
    module = types.ModuleType('_nox_revision_finalize_issuer')
    module.__file__ = str(PATH)
    exec(compile(raw, str(PATH), 'exec'), module.__dict__)
    return module.finalize_current()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,160}', value) else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_execution_revision_finalize',
              'data': {'state': 'UNVERIFIED', 'reason': reason, 'start_command_issued': False}},
              separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
