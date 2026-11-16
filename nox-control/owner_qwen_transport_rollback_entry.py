#!/usr/bin/env python3
"""Explicit held-state rollback of the expired third transport attempt."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

NAME = 'owner_qwen_transport_rollback.py'
SOURCE_SHA = 'e36375c3e3a463ce88afdfb089f45ece35d052b223a80af16b62f16ba6f66451'
REVIEW = {
    'schema': 'NOX_QWEN_TRANSPORT_ROLLBACK_REVIEW_V1',
    'execution_revision': {
        'request': '6913811534',
        'source_sha': 'c09a784a1842638cda0107bc8c67f1d92758557c',
        'receipt_sha256': 'c6f983a9704d21a6330234ef937bde6c2cc5bf12305820eb0cfba80a89022e0c',
    },
    'diagnostic_sha256': '4bd398db632874c7dc673b3ddddef87387b1a6298b19db202bc56abf324e2ec3',
    'diagnostic_source_sha256': '2863d6cab7cfd8410e09babde9d5d836a309a358610a3c67d6266a7fceb63d66',
    'operation_receipt_sha256': '206834ae10828483e7d9b3bd4b7d14eb998e3183687bc6cb8628820071af0088',
    'finalizer': {
        'request': '6914095251',
        'source_sha': 'b80643667d505542f6bfdde9b959bb5bf9f95ad2',
        'receipt_sha256': '2ca874ea7977b56489579ea4ef110061e3c9f96cd55369c945587a40de7e84f7',
    },
    'expected_operation_state': 'BOOTSTRAP_LOADING_PENDING',
    'expected_finalizer_state': 'BOOTSTRAP_LOADING_PENDING',
    'primary_diagnosis_reviewed': True,
    'primary_diagnosis_code': 'HOLD_MEMFD_TRANSPORT_DEADLINE',
    'finalizer_action_completed': True,
}


def main():
    encoded = BUNDLE.get(NAME)
    if not isinstance(encoded, str) or not 0 < len(encoded) < 175000:
        raise RuntimeError('HOLD_QWEN_ROLLBACK_ENTRY_BUNDLE')
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise RuntimeError('HOLD_QWEN_ROLLBACK_ENTRY_SOURCE_PIN')
    module = types.ModuleType('_nox_explicit_third_transport_failure_rollback')
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
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_transport_rollback_entry',
              'data': {'state': 'HOLD', 'reason': reason}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
