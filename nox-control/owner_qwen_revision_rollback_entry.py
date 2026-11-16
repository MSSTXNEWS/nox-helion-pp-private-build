#!/usr/bin/env python3
"""One reviewed recovery of the failed public-weight download attempt."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

NAME = 'owner_qwen_revision_rollback.py'
SOURCE_SHA = '0ed7a7a7622b7f2ace806fa189995bd39bc61bd96883ef3fed891095e4e7b535'
REVIEW = {
    'schema': 'NOX_QWEN_REVISION_ROLLBACK_REVIEW_V1',
    'execution_revision': {
        'request': '6911497014',
        'source_sha': 'ee85d1e294274428c4f03734d84be9517ad61b40',
        'receipt_sha256': '40f0c6f435a301f4f994120c0e03ded7afb7cbdb30b8c8541d5f5c0e695aa82d',
    },
    'diagnostic_sha256': '8ff3b9f79fce1d0b129e456e3df5c5a4bec0ed3c7fda0f28245162d7b2551bb8',
    'diagnostic_source_sha256': '48c49cda434d88b01d97f60ad5edbad086c148b35336105b4225961ecd432c92',
    'finalize_receipt_sha256': '23a0a441ba77675e4d50787e0cb2cf90309dbc8abfddb38e29fffbd91cd5a9b2',
    'expected_finalize_reason': 'HOLD_QWEN_REVISION_INSTALL_NEW_HOLD_OR_PAUSE',
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
    module = types.ModuleType('_nox_explicit_download_failure_rollback')
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
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_revision_rollback_entry',
              'data': {'state': 'HOLD', 'reason': reason}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
