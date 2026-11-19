#!/usr/bin/env python3
"""Compile the exact reviewed UI-only transaction; no native calls or tests."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONTROL = HERE.parents[1]
V5_SPEC_SHA = '0b3db4a0912660fae50db76b0239b77e73885f788cb8d113b0ce4797816cbd6c'
HOLD_READBACK_SHA = '7bdc8f5c58aa57dba86238b08533f1a92ea9c267a57a4f2fb98932f8a373b135'
HOLD_RECEIPT_SHA = '4f854c83232358d6f928558f7a41816a08213bbcecb04895e61c17a436207b7b'
COUNTER_READBACK_SHA = 'af4e38655364e37a740469db86058b03f48abfcd5539f29119dd9b836a963e09'
ASSETS = {
    'native_helpers.py': (CONTROL / 'owner_native_repair.py',
                         'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'),
    'public_chat.js': (HERE / 'nox-v24-chat-nonempty-current.js',
                       '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2'),
    'official_auth.py': (CONTROL / 'owner_media_acceptance_entry.py',
                         '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'),
}


def require(ok, code):
    if not ok:
        raise ValueError('HOLD_CHAT_UI_BUILD_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False).encode() + b'\n'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def load(path, expected):
    raw = path.read_bytes()
    require(0 < len(raw) <= 2 * 1024 * 1024 and sha(raw) == expected, 'READBACK_PIN')
    value = json.loads(raw)
    return value.get('data', value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chat-receipt', type=Path, required=True)
    parser.add_argument('--counter', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'package_ui_only_v1')
    args = parser.parse_args()
    previous_path = HERE / 'package_v5/install_spec.json'
    previous = load(previous_path, V5_SPEC_SHA)
    hold = load(args.chat_receipt, HOLD_READBACK_SHA)
    require(hold.get('NOX_MAINT_HOST_PIN') == ['VERIFIED']
            and hold.get('NOX_MAINT_AUTHENTICATED_INSTANCE') == [60509551]
            and hold.get('NOX_MAINT_AUTHORIZED_COMMENT_ID') == [6989410148], 'HOST_PROVENANCE')
    values = hold.get('NOX_MAINT_REPAIR', [])
    require(len(values) == 1 and values[0].get('kind') == 'chat_decomposition_install', 'RECEIPT_KIND')
    receipt = values[0]['data']
    digest = receipt.get('receipt_sha256')
    unhashed = {key: value for key, value in receipt.items() if key != 'receipt_sha256'}
    require(digest == HOLD_RECEIPT_SHA and sha(canonical(unhashed)) == digest, 'CANONICAL_RECEIPT')
    require(receipt.get('state') == 'HOLD_CHAT_DECOMPOSITION_INSTALL'
            and receipt.get('reason') == 'HOLD_CHAT_DECOMPOSITION_CHAT_REQUEST_ACTIVE'
            and receipt.get('changed') == [] and receipt.get('proxy_after') is None
            and receipt.get('proxy_stop_attempted') is False
            and receipt.get('source_install_verified') is False
            and receipt.get('proxy_restart_verified') is False, 'NO_MUTATION_PROOF')
    http = receipt.get('public_asset_before', {})
    require(http.get('port') == 8080 and http.get('path') == '/nox-web-v29/pc/v24/nox-v24-chat.js'
            and http.get('status') == 200 and http.get('content_encoding') == 'identity'
            and http.get('bytes_read') == 31906
            and http.get('sha256') == previous['before']['ui']
            and http.get('session_created') is True and http.get('session_closed') is True,
            'AUTHENTICATED_ASSET_PROOF')
    old_proxy = receipt['proxy_before']
    expected = previous['expected_proxy']
    require(old_proxy == {'pid': expected['pid'], 'pgrp': expected['pgrp'],
                          'starttime': str(expected['start_ticks'])}, 'PROXY_PROVENANCE')
    counter = load(args.counter, COUNTER_READBACK_SHA)
    require(counter.get('NOX_MAINT_HOST_PIN') == ['VERIFIED']
            and counter.get('NOX_MAINT_AUTHENTICATED_INSTANCE') == [60509551]
            and counter.get('NOX_MAINT_REMOTE_EXIT_CODE') == [0], 'COUNTER_PROVENANCE')
    values = counter.get('NOX_MAINT_CHAT_FOREGROUND_COUNTER_OBSERVE', [])
    require(len(values) == 1, 'COUNTER_REPORT')
    current = values[0]
    require(current.get('state') == 'READ_ONLY_COUNTER_OBSERVED'
            and current.get('protected_stable') is True
            and current.get('sources_unchanged') is True
            and current.get('source_writes') == 0 and current.get('service_restarts') == 0,
            'CURRENT_PROVENANCE')
    mapping = {'proxy': expected, 'model_8098': previous['protected_processes']['nox-ds41-8098'],
               'director': previous['protected_processes']['nox-dispatcher-t855u'],
               'worker_runtime': previous['protected_processes']['worker_0'],
               'worker_memory': previous['protected_processes']['worker_1'],
               'worker_weights': previous['protected_processes']['worker_2']}
    for phase in ('protected_before', 'protected_after'):
        require(set(current[phase]) == set(mapping), 'PROCESS_SET')
        for name, wanted in mapping.items():
            observed = current[phase][name]
            require(observed.get('matches') is True and observed.get('expected') == wanted
                    and all(observed['observed'].get(key) == value for key, value in wanted.items())
                    and observed['observed'].get('state') not in ('Z', 'X'), 'PROCESS_PIN')
    for name in ('chat_proxy.py', 'common.py'):
        require(current['sources'][name]['sha256'] == previous['guarded_sources'][name], 'SOURCE_PIN')
    bundle = {}
    for name, (path, pin) in ASSETS.items():
        raw = path.read_bytes()
        require(sha(raw) == pin, 'ASSET_PIN')
        if name.endswith('.py'):
            ast.parse(raw)
        bundle[name] = base64.b64encode(raw).decode('ascii')
    spec = {
        'schema': 'NOX_CHAT_UI_ONLY_INSTALL_SPEC_V1',
        'before_ui_sha256': previous['before']['ui'],
        'after_ui_sha256': previous['after_ui_sha256'],
        'asset_bytes': previous['asset_bytes'],
        'assets': {name: pin for name, (_, pin) in ASSETS.items()},
        'guarded_sources': {**previous['guarded_sources'],
                            'slim_chat_t885u.py': previous['before']['slim']},
        'protected_processes': previous['protected_processes'],
        'expected_proxy': expected,
        'provenance': {'v5_spec_sha256': V5_SPEC_SHA,
                       'unchanged_chat_hold_readback_sha256': HOLD_READBACK_SHA,
                       'unchanged_chat_hold_receipt_sha256': HOLD_RECEIPT_SHA,
                       'current_process_readback_sha256': COUNTER_READBACK_SHA,
                       'current_process_request': counter['NOX_MAINT_AUTHORIZED_COMMENT_ID']},
        'foreground_idle_required': False,
        'policy_write_or_reload': False,
        'acceptance_scope': 'STATIC_ASSET_HTTP_ONLY_BEHAVIOR_PENDING',
        'original_task_accepted': False,
    }
    template_path = HERE / 'owner_chat_ui_only_install.py'
    template = template_path.read_bytes()
    require(template.count(b'\nSPEC = {}\n') == 1
            and template.count(b'__NOX_BUNDLE_JSON__') == 1, 'TEMPLATE_ANCHOR')
    ast.parse(template)
    entry = template.replace(b'\nSPEC = {}\n', ('\nSPEC = ' + repr(spec) + '\n').encode(), 1)
    ast.parse(entry)
    ast.parse(entry.replace(b'__NOX_BUNDLE_JSON__', repr(bundle).encode(), 1))
    outputs = {'install_spec.json': encode(spec), 'install_bundle.json': encode(bundle),
               'owner_chat_ui_only_entry.py': entry}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, raw in outputs.items():
        target = args.output / name
        require(not target.exists() or target.read_bytes() == raw, 'OUTPUT_EXISTS')
        target.write_bytes(raw)
    metadata = {
        'schema': 'NOX_CHAT_UI_ONLY_BUILD_V1', 'native_deployment_performed': False,
        'template': str(template_path), 'template_sha256': sha(template),
        'entry': str(args.output / 'owner_chat_ui_only_entry.py'), 'entry_sha256': sha(entry),
        'assets': {name: {'source': str(path), 'sha256': pin} for name, (path, pin) in ASSETS.items()},
        'output_sha256': {name: sha(raw) for name, raw in outputs.items()},
        'source_scope': ['existing public nox-v24-chat.js'],
        'service_restarts': 0, 'policy_source_writes': 0, 'foreground_idle_required': False,
        'syntax_verified': True, 'tests_executed': False,
        'behavioral_acceptance_verified': False, 'original_task_accepted': False,
        'native_preconditions_pending': ['reachable authorized host', 'exact source and process pins',
            'official authenticated 8080 old/new asset SHA and byte length',
            'existing maintenance lease; no active chat or queue reset'],
        'old_v5_entry_after_success': 'WILL_HOLD_ON_OLD_UI_PIN; POLICY_RELOAD_REQUIRES_SEPARATE_REVIEWED_SPEC',
    }
    (args.output / 'build.json').write_bytes(encode(metadata))
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
