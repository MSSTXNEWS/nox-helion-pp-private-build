#!/usr/bin/env python3
"""Explicit rollback of the failed second public-weight download attempt."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

NAME = 'owner_qwen_retry_rollback.py'
SOURCE_SHA = '61f70c64f1b459fac35133bdbb41eaf287cc7a26a121560c2178aff697ba6dee'
REVIEW = {
    'schema': 'NOX_QWEN_RETRY_ROLLBACK_REVIEW_V1',
    'execution_revision': {
        'request': '6912442714',
        'source_sha': '7e27ab2ce0673205701727f4d3ef3f4a59b3d096',
        'receipt_sha256': 'c7304317a76fe08869eec9b6127ffd51107d69698e8b0ea678ae7c0f8d1e2858',
    },
    'diagnostic_sha256': '1f1e0554cb45ae1b17d6b433e8c450f51e67032c65814a9c93390239c452d696',
    'diagnostic_source_sha256': 'fba9af47f00030789a783ff1f62496868eb9452f1c0cbc6397053c2657f3da9a',
    'operation_receipt_sha256': '77dc5780f32f5ea6095151c6718a062f873e0c7d6ce9e6bbe022b32c7b4b3230',
    'finalize_receipt_absent': True,
    'expected_operation_reason': 'HOLD_QWEN_REVISION_INSTALL_NEW_HOLD_OR_PAUSE',
    'primary_diagnosis_reviewed': True,
    'primary_diagnosis_code': 'HOLD_MEMFD_PUBLIC_DOWNLOAD_INTERRUPTED',
}


def main():
    encoded = BUNDLE.get(NAME)
    if not isinstance(encoded, str) or not 0 < len(encoded) < 175000:
        raise RuntimeError('HOLD_QWEN_ROLLBACK_ENTRY_BUNDLE')
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('HOLD_QWEN_ROLLBACK_ENTRY_SOURCE_PIN')
    module = types.ModuleType('_nox_explicit_second_download_failure_rollback')
    module.__file__ = '/root/nox/scripts/' + NAME
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module.main(REVIEW)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        value = str(exc)
        reason = value if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', value) else type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_retry_rollback_entry',
              'data': {'state': 'HOLD', 'reason': reason}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
