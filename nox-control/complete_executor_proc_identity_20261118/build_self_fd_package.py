#!/usr/bin/env python3
"""Package the reviewed runner-only fix and one immutable retry, without native calls."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PREFIX = 'nox-control/complete_executor_proc_identity_20261118/'
ENTRY = 'nox-control/owner_kernel_self_fd_install.py'
UTILS_PIN = '798c94caf1f156e313e2ba60fd5b8068999dfa88b8f6454f8021ec5d39939621'
SPEC_PIN = 'a461e450552c5ecbc5a6437df5d74715a9a1ba07e10cc79204e8493b20e650ae'
CONFIG_PIN = '085fa4e3c8c96ae4ffb952dee53bb0d8bda0a1c50416a4d8a365017d043e95be'
RUNNER_PIN = '192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f'
PLAN_PIN = '457dbaf4484cfb5b7e14c5308285a42f01714dcec28358a54e6c926adf787e0b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer-sha256', required=True)
    parser.add_argument('--operator-sha256', required=True)
    args = parser.parse_args()
    utility_path = BASE / 'build_catalog_append_package.py'
    if hashlib.sha256(utility_path.read_bytes()).hexdigest() != UTILS_PIN:
        raise ValueError('HOLD_SELF_FD_PACKAGE_UTILITY_PIN')
    loader = importlib.util.spec_from_file_location('self_fd_packaging_utils', utility_path)
    utility = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(utility)
    require, read, digest = utility.require, utility.read, utility.digest
    root = utility.plain(BASE / 'source_package')
    helper_path = BASE / 'native/owner_kernel_self_fd_install.py'
    helper = read(helper_path)
    require(utility.SHA.fullmatch(args.installer_sha256)
            and digest(helper) == args.installer_sha256, 'SELF_FD_INSTALLER_PIN')
    raw_spec = read(BASE / 'native/self_fd_install_spec.json')
    require(digest(raw_spec) == SPEC_PIN, 'SELF_FD_SPEC_PIN')
    spec = json.loads(raw_spec)
    require(spec['schema'] == 'NOX_KERNEL_SELF_FD_RUNNER_INSTALL_SPEC_V1'
            and len(spec['assets']) == 5 and len(spec['expected_native']) == 15,
            'SELF_FD_INPUT_SCOPE')
    assets = {}
    for name, pin in spec['assets'].items():
        require(utility.relative(name).name == name, 'SELF_FD_ASSET_NAME')
        data = read(BASE / 'native/self_fd_install_assets' / name)
        require(digest(data) == pin, 'SELF_FD_ASSET_PIN')
        assets[name] = data
    raw_config = read(BASE / 'native/current_config_6967801407.json')
    require(digest(raw_config) == CONFIG_PIN, 'SELF_FD_CONFIG_PIN')
    # Local validation invokes only pure asset parsing/config composition. It
    # does not call install_self_fd, supervisor, preflight, or a remote command.
    helper_loader = importlib.util.spec_from_file_location('self_fd_installer_local_validation', helper_path)
    helper_module = importlib.util.module_from_spec(helper_loader)
    helper_loader.loader.exec_module(helper_module)
    runtime, package, descriptor = helper_module.self_fd_assets(
        {name: base64.b64encode(data).decode() for name, data in assets.items()}, spec)
    before, after = helper_module.self_fd_compose(raw_config, runtime, spec)
    require(len(before['catalog']['tasks']) == 20
            and after['catalog']['tasks'][:-1] == before['catalog']['tasks']
            and len(after['catalog']['tasks']) == 21, 'SELF_FD_CATALOG_PRESERVATION')
    require(set(runtime) == {'scripts/owner_project_test_runner.py'}
            and digest(runtime['scripts/owner_project_test_runner.py']) == RUNNER_PIN,
            'SELF_FD_ONLY_RUNNER')
    plan_path = 'state/dispatcher/project_executor/package/plans/' + PLAN_PIN + '.json'
    require(plan_path in package and digest(package[plan_path]) == PLAN_PIN, 'SELF_FD_PLAN_PIN')
    plan = json.loads(package[plan_path])
    require(plan['review_origin'] == 'OWNER_REVIEWED'
            and plan['parent_task_id'] == '1A03'
            and plan['task_id'] == '1A03.project.cursor_admission.proc_retry.20261118'
            and plan['verification']['min_tests'] == 30
            and plan['original_task_accepted'] is False
            and plan['acceptance_scope'] == 'SOURCE_PATCH_TESTED', 'SELF_FD_PLAN_SCOPE')
    require(descriptor['verification']['min_tests'] == 36
            and descriptor['shared_source_writes'] is False
            and descriptor['queue_claim_or_admission'] is False, 'SELF_FD_FD_PREFLIGHT_SCOPE')
    utility.HELPER_SHA256 = args.installer_sha256
    entry = utility.embedded_entry(helper, spec)
    compile(entry.decode(), ENTRY, 'exec')
    operator_path = root / utility.OPERATOR
    old_operator = read(operator_path)
    require(digest(old_operator) == args.operator_sha256, 'SELF_FD_OPERATOR_PREIMAGE')
    inspector = read(root / utility.STANDARD_INSPECT)
    operator, assignments, old_route = utility.patched_operator(
        old_operator.decode(), ENTRY, tuple(assets), tuple(PREFIX + 'assets/' + n for n in assets))
    for name, data in assets.items():
        utility.write_additive(root, PREFIX + 'assets/' + name, data)
    utility.write_additive(root, ENTRY, entry)
    utility.write_additive(root, PREFIX + 'install_spec.json', raw_spec)
    utility.write_additive(root, PREFIX + 'reviewed/owner_kernel_self_fd_install.py', helper)
    utility.write_additive(root, PREFIX + 'build_self_fd_package.py', read(__file__))
    evidence = [
        BASE / 'runtime_proc_identity_fix/manifest.json',
        BASE / 'runtime_proc_identity_fix/local_qa.json',
        BASE / 'runtime_proc_identity_fix/root_review.json',
        BASE / 'runtime_proc_identity_fix/kernel_self_fd.patch',
        BASE / 'runtime_proc_identity_fix/test_kernel_self_fd_adapter.py',
        BASE / 'bindings/reviewed_chat/proc_runtime_preflight/INDEPENDENT_ADAPTER_REVIEW.json',
        BASE / 'bindings/reviewed_chat/proc_runtime_preflight/INDEPENDENT_INSTALLER_REVIEW.json',
        BASE / 'native/kernel_self_fd_installer_local_qa.json',
        BASE / 'native/test_owner_kernel_self_fd_install.py',
        BASE / 'bindings/reviewed_chat/PROC_RETRY_BINDING_REVIEW.json',
        BASE / 'bindings/reviewed_chat/NO_LOSS_REVIEW.json',
        BASE / 'bindings/reviewed_chat/root_chain_review.json',
        BASE / 'userns_probe_134555511259.json',
        BASE / 'namespace_observe_134551881465.json',
        BASE / 'observe_134547237745.json',
    ]
    for path in evidence:
        utility.write_additive(root, PREFIX + 'evidence/' + path.name, read(path, 16 * 1024 * 1024))
    utility.write_additive(root, PREFIX + 'retry/READY.json', read(BASE / 'bindings/reviewed_chat/1A03_proc_retry/READY.json'))
    utility.replace_local(BASE / 'operator_before_self_fd.py', old_operator)
    utility.replace_local(operator_path, operator, expected=old_operator)
    require(read(root / utility.STANDARD_INSPECT) == inspector, 'SELF_FD_INSPECT_CHANGED')
    proposed = utility.encoded(after)
    utility.replace_local(BASE / 'native/proposed_config_self_fd.json', proposed)
    qa = {'schema': 'NOX_KERNEL_SELF_FD_PACKAGE_QA_V1',
          'installer_sha256': digest(helper), 'entry_sha256': digest(entry),
          'spec_sha256': digest(raw_spec), 'assets': len(assets),
          'runtime_changed': ['owner_project_test_runner.py'],
          'old_config_sha256': digest(raw_config), 'proposed_config_sha256': digest(proposed),
          'old_catalog_rows_preserved': 20, 'new_catalog_rows': 1,
          'operator_assignments_changed': assignments, 'previous_repair_route': old_route,
          'new_repair_route': ENTRY, 'inspect_preserved': True,
          'native_preflight_required': {'generic': 4, 'protected_chat': 30, 'fd_regression': 36},
          'native_calls': 0, 'source_workspace_writes': 0, 'original_task_acceptance_added': 0}
    qa_raw = json.dumps(qa, ensure_ascii=False, indent=2).encode() + b'\n'
    utility.replace_local(BASE / 'self_fd_package_local_qa.json', qa_raw)
    utility.write_additive(root, PREFIX + 'evidence/package_local_qa.json', qa_raw)
    manifest = []
    for path in sorted(root.rglob('*')):
        if path.is_file():
            data = read(path, 16 * 1024 * 1024)
            manifest.append({'path': str(path.relative_to(root)), 'bytes': len(data),
                             'sha256': digest(data),
                             'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()})
    utility.replace_local(BASE / 'source_package_manifest.json', json.dumps(manifest, indent=2).encode() + b'\n')
    print(json.dumps({**qa, 'files': len(manifest)}))


if __name__ == '__main__':
    main()
