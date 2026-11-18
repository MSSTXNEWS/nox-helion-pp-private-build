#!/usr/bin/env python3
"""Build the reviewed chat installer locally from two exact native readbacks.

No network calls, native module imports, native writes, service changes or tests.
The generated entry still requires the normal owner operator bundle injection.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONTROL = HERE.parents[1]
PINS = {
    'nox-v24-chat.js': '92b952b6c7ee31f22ed74912d9444a88989c014694424083336660dce21a8a5b',
    'slim_chat_t885u.py': '8e1a83a68b336fc0c12f350d754ea47e5b5b72688584670aacc0de4079b1d37b',
    'owner_chat_stream.py': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09',
    'agent_loop.py': '0ecec93bcf3239b7decc768862d27fbdc60fe2b613103f201406761bb4850aaa',
    'chat_proxy.py': '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
    'nox_v29_chat_bridge.py': '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a',
    'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2',
    'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
}
ASSETS = {
    'native_helpers.py': (CONTROL / 'owner_native_repair.py',
                         'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'),
    'policy_patch.py': (HERE / 'owner_chat_decomposition_patch.py',
                      '024d2aab7f5ab75ebd6b08fc2e8ac1dc12891b4197c74af22b7dc3ad5d890965'),
    'public_chat.js': (HERE / 'nox-v24-chat-nonempty-current.js',
                      '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2'),
    'official_auth.py': (CONTROL / 'owner_media_acceptance_entry.py',
                        '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60'),
}
SYMBOLS = {'common.py:mark_chat': '156f8727e714a5864a10d34cfbdf6a97f78703c9f81893b49cb4ea21676c49ec',
           'chat_proxy.py:_ChatActivityStream': '12f8ccd256246c68d78caae05d0ce54ad90cc8803515f3ebc2f804b518defc57'}


def require(ok, code):
    if not ok:
        raise ValueError('HOLD_CHAT_BUILD_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'


def load(path):
    raw = path.read_bytes()
    require(0 < len(raw) <= 8 * 1024 * 1024, 'READBACK_BOUND')
    return json.loads(raw), sha(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--workers', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'package_v5')
    args = parser.parse_args()
    data, probe_sha = load(args.probe)
    require(data.get('NOX_MAINT_REMOTE_EXIT_CODE') == [0], 'PROBE_EXIT')
    reports = data.get('NOX_MAINT_CHAT_AUTONOMY_OBSERVE')
    require(isinstance(reports, list) and len(reports) == 1, 'PROBE_SET')
    report = reports[0]
    require(report.get('state') == 'READ_ONLY_SOURCE_OBSERVED'
            and report.get('protected_stable') is True
            and report.get('protected_all_running_verified') is True, 'PROBE_STATE')
    files = {row['name']: row for row in report['files']}
    require(set(files) == set(PINS), 'SOURCE_SET')
    require(all(files[name].get('sha256') == pin and files[name].get('state') == 'SOURCE_PINNED'
                for name, pin in PINS.items()), 'SOURCE_PIN')
    for key, pin in SYMBOLS.items():
        name, symbol = key.split(':', 1)
        rows = [row for row in files[name].get('exports', []) if row.get('symbol') == symbol]
        require(len(rows) == 1 and rows[0].get('state') == 'EXACT_SOURCE_EXPORTED'
                and rows[0].get('sha256') == pin and sha(rows[0]['text'].encode()) == pin, 'SYMBOL_PIN')
    services = {row['service']: row for row in report['protected_after']['services']}
    require(set(services) == {'nox-proxy', 'nox-ds41-8098', 'nox-web29-18775',
                             'nox-dispatcher-t855u'}, 'SERVICE_SET')
    protected = {name: row['identity'] for name, row in services.items() if name != 'nox-proxy'}
    worker_data, worker_sha = load(args.workers)
    require(worker_data.get('NOX_MAINT_REMOTE_EXIT_CODE') == [0], 'WORKER_EXIT')
    snapshots = worker_data.get('NOX_MAINT_SCOPE_POST_WORKERS', [])
    require(len(snapshots) >= 1, 'WORKER_SNAPSHOT')
    workers = snapshots[-1].get('workers', [])
    require(len(workers) == 3 and all(row.get('verified') is True for row in workers), 'THREE_VERIFIED_WORKERS')
    workers = sorted(workers, key=lambda row: row['observed']['pid'])
    for index, row in enumerate(workers):
        observed = row['observed']
        require(observed['ppid'] == protected['nox-dispatcher-t855u']['pid']
                and observed['state'] not in ('Z', 'X'), 'WORKER_PARENT')
        protected['worker_' + str(index)] = {key: observed[key] for key in ('pid', 'ppid', 'pgrp', 'start_ticks')}
    require(len({row['pid'] for row in protected.values()}) == 6, 'DISTINCT_PIDS')
    bundle = {}
    for name, (path, pin) in ASSETS.items():
        raw = path.read_bytes()
        require(sha(raw) == pin, 'ASSET_PIN')
        if name.endswith('.py'):
            ast.parse(raw)
        bundle[name] = base64.b64encode(raw).decode('ascii')
    assignment = (HERE / 'slim_rules_after.fragment').read_bytes()
    require(sha(assignment) == '64263a04bbdc3c8dd54eb644fbeb493f3b25f355b5143f6045e703ac27526a46',
            'NEW_RULES_PIN')
    rules = ast.literal_eval(ast.parse(assignment).body[0].value)
    require(len(rules.encode()) == 3980, 'RULES_BUDGET')
    spec = {'schema': 'NOX_CHAT_DECOMPOSITION_INSTALL_SPEC_V1',
            'before': {'slim': PINS['slim_chat_t885u.py'], 'ui': PINS['nox-v24-chat.js']},
            'assets': {name: pin for name, (path, pin) in ASSETS.items()},
            'new_rules_assignment_sha256': sha(assignment),
            'new_rules_utf8_bytes': 3980,
            'after_ui_sha256': ASSETS['public_chat.js'][1],
            'asset_bytes': {'before': files['nox-v24-chat.js']['size'],
                            'after': len(base64.b64decode(bundle['public_chat.js']))},
            'guarded_sources': {name: pin for name, pin in PINS.items()
                                if name not in ('slim_chat_t885u.py', 'nox-v24-chat.js')},
            'protected_processes': protected,
            'expected_proxy': services['nox-proxy']['identity'],
            'idle_gate': {'schema': 'NOX_COMMON_INFLIGHT_IDLE_V1', 'symbols': SYMBOLS,
                          'expected_path': '/root/nox/status/chat_state.json',
                          'required_inflight': 0, 'stable_samples': 2,
                          'atomic_admission_fence': False},
            'provenance': {'chat_probe_sha256': probe_sha, 'worker_readback_sha256': worker_sha,
                           'chat_probe_request': data['NOX_MAINT_AUTHORIZED_COMMENT_ID'],
                           'worker_readback_request': worker_data['NOX_MAINT_AUTHORIZED_COMMENT_ID']},
            'acceptance_scope': 'SOURCE_AND_PROXY_HEALTH_ONLY_BEHAVIOR_PENDING',
            'original_task_accepted': False}
    template = (HERE / 'owner_chat_decomposition_install_v5.py').read_bytes()
    require(template.count(b'\nSPEC = {}\n') == 1 and template.count(b'__NOX_BUNDLE_JSON__') == 1,
            'TEMPLATE_ANCHOR')
    ast.parse(template)
    entry = template.replace(b'\nSPEC = {}\n', ('\nSPEC = ' + repr(spec) + '\n').encode(), 1)
    ast.parse(entry)
    # Compile the final injected representation; do not execute either version.
    ast.parse(entry.replace(b'__NOX_BUNDLE_JSON__', repr(bundle).encode(), 1))
    args.output.mkdir(parents=True, exist_ok=True)
    outputs = {'install_spec.json': encode(spec), 'install_bundle.json': encode(bundle),
               'owner_chat_decomposition_entry.py': entry}
    for name, raw in outputs.items():
        target = args.output / name
        require(not target.exists() or target.read_bytes() == raw, 'OUTPUT_EXISTS')
        target.write_bytes(raw)
    metadata = {'schema': 'NOX_CHAT_DECOMPOSITION_BUILD_V1', 'native_deployment_performed': False,
                'tests_executed': False, 'syntax_verified': True,
                'template_sha256': sha(template), 'entry': str(args.output / 'owner_chat_decomposition_entry.py'),
                'entry_sha256': sha(entry), 'assets': {name: {'source': str(path), 'sha256': pin}
                                                    for name, (path, pin) in ASSETS.items()},
                'output_sha256': {name: sha(raw) for name, raw in outputs.items()},
                'probe_sha256': probe_sha, 'worker_readback_sha256': worker_sha,
                'native_preconditions_pending': ['reachable authorized host', 'exact source/process pins',
                    'stable zero current inflight count',
                    'official owner-authenticated8080 asset before/after SHA and length',
                    'fresh owner sessions closed before source mutation and on errors'],
                'behavioral_acceptance_verified': False, 'original_task_accepted': False}
    (args.output / 'build.json').write_bytes(encode(metadata))
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
