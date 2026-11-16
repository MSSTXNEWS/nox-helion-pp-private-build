#!/usr/bin/env python3
"""Compose a normal-motion probe from six exact sources; install nothing.

The existing isolated CPU browser runtime, resource gates, auth, one-POST limit,
private receipt and process timeout remain the frozen stream-only entry's code.
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

ENTRY = 'owner_browser_stream_only_entry.py'
HELPER = 'owner_chat_normal_motion_qa.py'
PINS = {
    ENTRY: '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
    'owner_chat_browser_transport_qa.py': 'e8d256f4ab4de1d53859c1da74237622871354b5d84442bdff1171631f9f05f0',
    'owner_chat_browser_release_qa.py': '42abf7b769b4103f9f3799048fe68da5c93937dbef9b56a8e4a2b5aac2072bc7',
    'owner_chat_stream_only_qa.py': '534e09c9fd8ed0bbfc3c0e973eaf4790fa850b65e5483b4a011f8a92ce058e90',
    HELPER: 'd7b0c58bec74f87215725c541d530317df35d6c6ef448b2f0f713ba7778a0b71',
}
SCOPE = 'AUTHENTICATED_NATIVE_ENDPOINT_VISIBLE_PARTIALS_S03_NORMAL_MOTION_ONLY'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_NORMAL_MOTION_ENTRY_' + code)


def sources():
    values = {}
    for name, pin in PINS.items():
        require(re.fullmatch('[a-f0-9]{64}', pin), 'UNREVIEWED_PIN')
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 350000, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 262144 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); values[name] = raw
    return values


def child_program(original, blobs):
    program = original(blobs).decode()
    old = ' scope.install(core,raw,transport,traw,release,rraw)\n'
    require(program.count(old) == 1, 'CHILD_ANCHOR')
    new = (" normal=loaded['owner_chat_normal_motion_qa'][0]\n"
           " normal.install(core,raw,transport,traw,release,rraw,scope,loaded['owner_chat_stream_only_qa'][1])\n")
    return program.replace(old, new, 1).encode()


def receipt_scope(value):
    require(value.get('scope') == SCOPE and value.get('normal_motion_probe_schema') == 'NOX_OWNER_BROWSER_NORMAL_MOTION_PROBE_V1'
        and value.get('browser_motion_preference') == 'no-preference'
        and value.get('maximum_native_posts') == value.get('maximum_new_dialogs') == 1
        and value.get('production_configuration_changed') is False
        and value.get('full_browser_qa_evaluated') is False and value.get('full_browser_qa_promoted') is False
        and value.get('markdown_rendering_evaluated') is False
        and value.get('upstream_model_inference_verified') is False
        and value.get('upstream_model_request_bound') is False
        and value.get('upstream_SSE_binding_verified') is False, 'CHILD_SCOPE')
    if value.get('state') == 'STREAM_ONLY_ACCEPTED':
        require(value.get('normal_motion_probe_verified') is True
            and value.get('normal_motion_mode_verified') is True
            and value.get('normal_animation_evaluated') is True
            and type(value.get('native_posts_admitted')) is int and value['native_posts_admitted'] == 1
            and value.get('normal_motion_observation_state') == 'VERIFIED'
            and value.get('strict_progressive_stream_observed') is True
            and value.get('two_proper_prefixes_before_done') is True
            and value.get('s03_readback_verified') is True
            and value.get('synthetic_number_sequence_pass') is True, 'CHILD_ACCEPTANCE')


def prepared():
    blobs = sources()
    entry = types.ModuleType('_nox_exact_stream_only_entry')
    entry.__file__ = '<' + ENTRY + '>'
    exec(compile(blobs[ENTRY], entry.__file__, 'exec'), entry.__dict__)
    original_pins = dict(entry.PINS)
    require(original_pins == {name: PINS[name] for name in original_pins}
        and set(original_pins) == set(PINS) - {ENTRY, HELPER}, 'ENTRY_CLOSURE')
    entry.PINS = {**original_pins, HELPER: PINS[HELPER]}
    entry.BUNDLE = {name: BUNDLE[name] for name in entry.PINS}
    original_child, original_emit = entry.child_program, entry.emit
    entry.child_program = lambda values: child_program(original_child, values)

    def emit(kind, value):
        if kind == 'browser_stream_only_receipt':
            receipt_scope(value)
            kind = 'browser_normal_motion_receipt'
        elif kind == 'browser_stream_only_sources':
            value = {**value, 'normal_motion_probe': True, 'frozen_entry_sha256': PINS[ENTRY],
                'maximum_native_posts': 1, 'markdown_or_full_ui_acceptance': False}
            kind = 'browser_normal_motion_sources'
        elif kind == 'browser_stream_only_hold':
            kind = 'browser_normal_motion_hold'
        original_emit(kind, value)

    entry.emit = emit
    program = entry.child_program({name: blobs[name] for name in entry.PINS})
    compile(program, '<normal-motion-child>', 'exec')
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
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'browser_normal_motion_entry_hold',
            'data': {'state': 'HOLD', 'reason': reason, 'normal_motion_probe_verified': False,
                     'native_post_state': 'NOT_OBSERVED_BY_ENTRY', 'private_exception_exported': False}},
            separators=(',', ':'), allow_nan=False), flush=True)
        raise SystemExit(2)
