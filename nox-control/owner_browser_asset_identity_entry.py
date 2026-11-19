#!/usr/bin/env python3
"""Add a passive loaded-asset identity gate to the frozen normal-motion entry.

All browser/runtime/auth/one-POST/normal-span/S03/timeout gates remain delegated
to exact reviewed sources. No native source, model or service is changed here.
"""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

NORMAL_ENTRY = 'owner_browser_normal_motion_entry.py'
HELPER = 'owner_chat_asset_identity_qa.py'
PINS = {
    NORMAL_ENTRY: '0237037073d8c4d31b4bb062b0f7f5e11e2ad24fc53fb011e6f37adf8b2ac649',
    'owner_browser_stream_only_entry.py': '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
    'owner_chat_browser_transport_qa.py': 'e8d256f4ab4de1d53859c1da74237622871354b5d84442bdff1171631f9f05f0',
    'owner_chat_browser_release_qa.py': '42abf7b769b4103f9f3799048fe68da5c93937dbef9b56a8e4a2b5aac2072bc7',
    'owner_chat_stream_only_qa.py': '534e09c9fd8ed0bbfc3c0e973eaf4790fa850b65e5483b4a011f8a92ce058e90',
    'owner_chat_normal_motion_qa.py': 'd7b0c58bec74f87215725c541d530317df35d6c6ef448b2f0f713ba7778a0b71',
    HELPER: '8d29ac9c318d09ccdc1cf65eb3c07fe8b454fb1a0ecd36764ab2f8f3c90287d0',
}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_ASSET_IDENTITY_ENTRY_' + code)


def sources():
    values = {}
    total = 0
    for name, pin in PINS.items():
        require(re.fullmatch('[a-f0-9]{64}', pin), 'UNREVIEWED_PIN')
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 350000, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        total += len(raw)
        require(0 < len(raw) <= 262144 and total <= 262144
            and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); values[name] = raw
    return values


def child_program(original, blobs):
    program = original(blobs).decode()
    anchor = " normal.install(core,raw,transport,traw,release,rraw,scope,loaded['owner_chat_stream_only_qa'][1])\n"
    require(program.count(anchor) == 1, 'CHILD_ANCHOR')
    replacement = (" asset=loaded['owner_chat_asset_identity_qa'][0]\n"
        " asset.install(core,raw,transport,traw,release,rraw,scope,loaded['owner_chat_stream_only_qa'][1],normal,loaded['owner_chat_normal_motion_qa'][1])\n")
    return program.replace(anchor, replacement, 1).encode()


def receipt_scope(value, helper):
    require(value.get('asset_identity_scope') == helper.SCOPE
        and isinstance(value.get('asset_binding'), dict)
        and value['asset_binding'].get('schema') == helper.SCHEMA
        and value['asset_binding'].get('path') == helper.ASSET_PATH
        and value['asset_binding'].get('expected_sha256') == helper.ASSET_SHA
        and value['asset_binding'].get('expected_bytes') == helper.ASSET_BYTES
        and value['asset_binding'].get('separate_asset_request_issued') is False
        and value['asset_binding'].get('raw_body_or_headers_exported') is False, 'CHILD_SCOPE')
    if value.get('state') == 'STREAM_ONLY_ACCEPTED':
        require(value.get('asset_identity_verified') is True
            and helper.complete(value['asset_binding']), 'CHILD_ASSET_ACCEPTANCE')


def prepared():
    blobs = sources()
    normal = types.ModuleType('_nox_exact_normal_entry')
    normal.__file__ = '<' + NORMAL_ENTRY + '>'
    exec(compile(blobs[NORMAL_ENTRY], normal.__file__, 'exec'), normal.__dict__)
    require(normal.PINS == {name: pin for name, pin in PINS.items()
        if name not in (NORMAL_ENTRY, HELPER)}, 'NORMAL_CLOSURE')
    normal.BUNDLE = {name: BUNDLE[name] for name in normal.PINS}
    entry, _ = normal.prepared()
    helper = types.ModuleType('_nox_exact_asset_identity')
    helper.__file__ = '<' + HELPER + '>'
    exec(compile(blobs[HELPER], helper.__file__, 'exec'), helper.__dict__)
    entry.PINS = {**entry.PINS, HELPER: PINS[HELPER]}
    entry.BUNDLE = {name: BUNDLE[name] for name in entry.PINS}
    original_child, original_emit = entry.child_program, entry.emit
    entry.child_program = lambda values: child_program(original_child, values)

    # Preserve the frozen normal parent validator as well as the native entry's
    # schema/rc checks. Only rename the safe emitted kind after both validators.
    def emit(kind, value):
        if kind == 'browser_stream_only_receipt':
            normal.receipt_scope(value)
            receipt_scope(value, helper)
            kind = 'browser_normal_asset_receipt'
        elif kind == 'browser_stream_only_sources':
            value = {**value, 'normal_motion_probe': True, 'passive_loaded_asset_binding': True,
                'frozen_normal_entry_sha256': PINS[NORMAL_ENTRY],
                'maximum_native_posts': 1, 'separate_asset_request_issued': False,
                'markdown_or_full_ui_acceptance': False}
            kind = 'browser_normal_asset_sources'
        elif kind == 'browser_stream_only_hold':
            kind = 'browser_normal_asset_hold'
        # Unknown names pass through the frozen wrapper unchanged; the renamed
        # names above cannot be accepted as its original receipt kind.
        original_emit(kind, value)

    entry.emit = emit
    program = entry.child_program({name: blobs[name] for name in entry.PINS})
    compile(program, '<normal-asset-child>', 'exec')
    return entry, program


def main():
    entry, _ = prepared()
    return entry.main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,140}', reason):
            reason = type(exc).__name__
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'browser_normal_asset_entry_hold',
            'data': {'state': 'HOLD', 'reason': reason, 'asset_identity_verified': False,
                'native_post_state': 'NOT_OBSERVED_BY_ENTRY', 'private_exception_exported': False}},
            separators=(',', ':'), allow_nan=False), flush=True)
        raise SystemExit(2)
