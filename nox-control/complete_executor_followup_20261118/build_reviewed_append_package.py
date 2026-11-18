#!/usr/bin/env python3
"""Package an explicitly reviewed rescue/follow-up; never execute native work.

The failed model result remains a failed model result. This package submits a
separate OWNER_REVIEWED plan through the existing confined native executor.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
UTILS_SHA = '798c94caf1f156e313e2ba60fd5b8068999dfa88b8f6454f8021ec5d39939621'
SCHEMA = 'NOX_REVIEWED_PROJECT_CATALOG_APPEND_SPEC_V1'
CHAT_FILES = {'owner_chat_request_ledger.py', 'native_v29_full_bridge.py'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('spec', 'helper', 'assets-dir', 'prefix', 'entry', 'expected-helper-sha256',
                'expected-operator-sha256'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    utility_path = BASE / 'build_catalog_append_package.py'
    if hashlib.sha256(utility_path.read_bytes()).hexdigest() != UTILS_SHA:
        raise ValueError('HOLD_REVIEWED_PACKAGE_UTILITY_PIN')
    loader = importlib.util.spec_from_file_location('reviewed_append_package_utilities', utility_path)
    utility = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(utility)
    require, read, digest = utility.require, utility.read, utility.digest
    root = utility.plain(BASE / 'source_package')
    helper = read(args.helper)
    require(utility.SHA.fullmatch(args.expected_helper_sha256)
            and digest(helper) == args.expected_helper_sha256, 'REVIEWED_HELPER_PIN')
    specification = json.loads(read(args.spec))
    fields = {'schema', 'mode', 'assets', 'plan_asset', 'payload_assets', 'catalog_row',
              'required_task', 'expected_config_sha256', 'expected_callback_sha256',
              'expected_director', 'expected_workers', 'expected_source_pins'}
    require(isinstance(specification, dict) and set(specification) == fields
            and specification['schema'] == SCHEMA, 'REVIEWED_SPEC')
    mode = specification['mode']
    require(mode in ('FAILED_MODEL_RESCUE', 'VERIFIED_REVIEWED_FOLLOWUP'), 'REVIEWED_MODE')
    parent = '1A03' if mode == 'FAILED_MODEL_RESCUE' else '1A02'
    source_pins = specification['expected_source_pins']
    require(set(source_pins) == CHAT_FILES
            and all(utility.SHA.fullmatch(str(v)) for v in source_pins.values()), 'REVIEWED_SOURCE_PINS')
    for key in ('expected_config_sha256', 'expected_callback_sha256'):
        require(utility.SHA.fullmatch(str(specification[key])), 'REVIEWED_CONFIG_PIN')
    identities = [specification['expected_director'], *specification['expected_workers']]
    require(len(identities) == 4 and len({r['pid'] for r in identities}) == 4
            and all(set(r) == {'pid', 'start_ticks'} and type(r['pid']) is int and r['pid'] > 1
                    and type(r['start_ticks']) is int and r['start_ticks'] > 0 for r in identities),
            'REVIEWED_PROCESS_IDENTITIES')
    required = specification['required_task']
    pin_key = 'contract_sha256' if mode == 'FAILED_MODEL_RESCUE' else 'plan_sha256'
    require(set(required) == {'id', 'receipt_sha256', pin_key}
            and utility.ID.fullmatch(required['id']) and required['id'].startswith('1A03.')
            and utility.SHA.fullmatch(required['receipt_sha256'])
            and utility.SHA.fullmatch(required[pin_key]), 'REVIEWED_PREDECESSOR')
    assets_root = utility.plain(args.assets_dir)
    assets = {}
    require(isinstance(specification['assets'], dict) and 2 <= len(specification['assets']) <= 4,
            'REVIEWED_ASSETS')
    for name, pin in specification['assets'].items():
        require(utility.relative(name).name == name, 'ASSET_NAME')
        raw = read(assets_root / name)
        require(digest(raw) == pin, 'ASSET_BYTES')
        assets[name] = raw
    plan_name = specification['plan_asset']
    require(plan_name in assets, 'PLAN_ASSET')
    plan_raw = assets[plan_name]
    plan = json.loads(plan_raw)
    require(utility.encoded(plan) == plan_raw and plan.get('schema') == 'NOX_PROJECT_WORK_PLAN_V1'
            and plan.get('operation') == 'apply_reviewed_files'
            and plan.get('review_origin') == 'OWNER_REVIEWED'
            and plan.get('parent_task_id') == parent and plan.get('root_id') == 'NOX_PROJECT_SOURCE'
            and plan.get('queue_id') == 'Q1_RUNTIME_CHAT'
            and plan.get('original_task_accepted') is False, 'REVIEWED_PLAN_SCOPE')
    files = plan.get('files')
    require(isinstance(files, list) and 1 <= len(files) <= 2, 'REVIEWED_FILES')
    paths = {r['path'] for r in files}
    require(len(paths) == len(files) and paths <= CHAT_FILES
            and (mode != 'FAILED_MODEL_RESCUE' or paths == CHAT_FILES)
            and all(row['before_sha256'] == source_pins[row['path']]
                    and row['after_sha256'] == row['payload_sha256'] for row in files),
            'REVIEWED_PLAN_PREIMAGES')
    payloads = specification['payload_assets']
    require(isinstance(payloads, dict) and set(payloads) == {r['payload_sha256'] for r in files}
            and set(assets) == {plan_name, *payloads.values()}, 'REVIEWED_PAYLOADS')
    for pin, name in payloads.items():
        require(name in assets and digest(assets[name]) == pin, 'REVIEWED_PAYLOAD_PIN')
    row = specification['catalog_row']
    deps = [] if mode == 'FAILED_MODEL_RESCUE' else [required['id']]
    require(row.get('id') == plan.get('task_id') and utility.ID.fullmatch(row['id'])
            and row['id'].startswith(parent + '.') and row.get('handler') == 'owner_native_project_work'
            and row.get('queue_id') == 'Q1_RUNTIME_CHAT' and row.get('resource') == 'CPU_LIGHT'
            and row.get('deps') == deps and row.get('source_sha256') == specification['expected_callback_sha256']
            and row.get('params') == {'parent_task_id': parent, 'plan_sha256': digest(plan_raw)},
            'REVIEWED_CATALOG_ROW')
    prefix, entry = str(utility.relative(args.prefix)), str(utility.relative(args.entry))
    require(prefix.startswith('nox-control/') and entry.startswith('nox-control/')
            and entry.endswith('.py') and entry != utility.OPERATOR, 'REVIEWED_OUTPUT_SCOPE')
    # Pin substitution changes only SPEC. The original model-only utility and
    # native helper are retained; this is a distinct reviewed policy package.
    utility.HELPER_SHA256 = args.expected_helper_sha256
    entry_raw = utility.embedded_entry(helper, specification)
    compile(entry_raw.decode(), entry, 'exec')
    operator_path = root / utility.OPERATOR
    before_operator = read(operator_path)
    require(digest(before_operator) == args.expected_operator_sha256, 'OPERATOR_PREIMAGE')
    inspect_before = read(root / utility.STANDARD_INSPECT)
    asset_paths = [prefix + '/assets/' + name for name in assets]
    operator_raw, changed, old_route = utility.patched_operator(
        before_operator.decode(), entry, tuple(assets), tuple(asset_paths))
    for name, raw in assets.items():
        utility.write_additive(root, prefix + '/assets/' + name, raw)
    utility.write_additive(root, entry, entry_raw)
    utility.write_additive(root, prefix + '/spec.json', utility.encoded(specification))
    utility.write_additive(root, prefix + '/reviewed_helper.py', helper)
    utility.write_additive(root, prefix + '/build_reviewed_append_package.py', read(__file__))
    utility.replace_local(operator_path, operator_raw, expected=before_operator)
    require(read(root / utility.STANDARD_INSPECT) == inspect_before, 'INSPECT_CHANGED')
    qa = {'schema': 'NOX_REVIEWED_APPEND_PACKAGE_QA_V1', 'mode': mode,
          'plan_sha256': digest(plan_raw), 'helper_sha256': digest(helper),
          'entry_sha256': digest(entry_raw), 'old_repair_route': old_route,
          'new_repair_route': entry, 'operator_assignments_changed': changed,
          'inspect_preserved': True, 'native_calls': 0, 'native_source_writes': 0,
          'model_generated_code_claimed': False, 'original_task_acceptance_added': 0}
    utility.write_additive(root, prefix + '/package_qa.json', utility.encoded(qa))
    manifest = []
    for path in sorted(root.rglob('*')):
        if path.is_file():
            raw = read(path, 16 * 1024 * 1024)
            manifest.append({'path': str(path.relative_to(root)), 'bytes': len(raw), 'sha256': digest(raw),
                             'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})
    utility.replace_local(BASE / 'source_package_manifest.json',
                          json.dumps(manifest, indent=2).encode() + b'\n')
    print(json.dumps({**qa, 'files': len(manifest)}))


if __name__ == '__main__':
    main()
