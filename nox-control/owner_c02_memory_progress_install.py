#!/usr/bin/env python3
"""Admit one reviewed C02 memory capacity contract to the existing executor.

No runtime module changes. The request pins every existing native/source byte,
adds exactly two immutable tests and one model contract, and preserves all
historical claims and S03 receipts. Only the idle dispatcher is restarted;
the existing workers implement the contract in the existing source workspace.
"""
from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

ROOT = Path('/root/nox')
CONFIG = 'config/owner_native_subagents.json'
SOURCE = 'projects/owner_executor/source_workspace'
MARKER = SOURCE + '/NOX_EXECUTOR_BOOTSTRAP.json'
SCHEMA = 'NOX_C02_MEMORY_PROGRESS_INSTALL_SPEC_V1'
CALLBACK_SHA256 = '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b'
MODEL_CLIENT_SHA256 = 'f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f'
FROZEN_HELPER_SHA256 = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
C02_SOURCE = 'nox_runpod/teacher_mesh/v38/synaptic_brain.py'
TRUSTED_TESTS = frozenset(('test_nox_c02_optional_starvation.py',
                           'test_nox_c02_existing_cognition.py'))
SPEC = {'schema': 'NOX_C02_MEMORY_PROGRESS_INSTALL_SPEC_V1', 'assets': {'c02_contract_4a8f20c371f3211c2351.json': '4a8f20c371f3211c2351294bbe106a69a53f7a31e7051a039de9b227bcfd7f98', 'c02_test_nox_c02_existing_cognition.py': 'a88d35436d6ae9b1b3a368d7fd9e79ef907635067a92f53e1037486ccb3d5ab9', 'c02_test_nox_c02_optional_starvation.py': '02fdfef831c66c114d17840b3a212f5e6604f6a0d3c03acb9a9c0de7878d4e64', 'c02_transaction_helpers.py': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'}, 'helper_asset': 'c02_transaction_helpers.py', 'helper_sha256': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609', 'runtime_paths': {}, 'source_test_paths': {'c02_test_nox_c02_existing_cognition.py': 'test_nox_c02_existing_cognition.py', 'c02_test_nox_c02_optional_starvation.py': 'test_nox_c02_optional_starvation.py'}, 'package_paths': {'c02_contract_4a8f20c371f3211c2351.json': 'state/dispatcher/project_executor/package/contracts/4a8f20c371f3211c2351294bbe106a69a53f7a31e7051a039de9b227bcfd7f98.json'}, 'catalog_append': [{'deps': [], 'estimated_cost': 2, 'handler': 'owner_native_project_work', 'id': '3A01.project.c02_memory_capacity.20261118', 'params': {'contract_sha256': '4a8f20c371f3211c2351294bbe106a69a53f7a31e7051a039de9b227bcfd7f98', 'parent_task_id': '3A01'}, 'priority': 'P1', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'resource': 'CPU_LIGHT', 'title': 'Keep an existing CPU worker available for S03 across successive chat requests', 'source_sha256': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b'}], 'expected_native': {'config/owner_native_subagents.json': '28ae787888cdc90cf1cccfc7cc86dcbd4a80b8fb34f471e306f25708b9e75d0f', 'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_autonomy_pool.py': 'd5fb476f53e64d2014f27465c7bd64192158b5bcdd79a72ff7c962d853602339', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292', 'scripts/owner_project_executor.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': 'f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f', 'scripts/owner_project_native.py': '2c83ec53f7ee7c2d76bc1fac21c80adf76c58f83c5a219ba0294f9b3f713d707', 'scripts/owner_project_planner.py': 'e7bc83e4dea75f08ecb4e92fedf6ef98e0620f17c7b3b28ccb4728c6ddda68ac', 'scripts/owner_project_test_runner.py': '192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'scripts/owner_subagent_dispatcher.py': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'scripts/owner_subagent_instruction_truth.py': '61ef5e5ba66f6d65af2f59fbf5bc67bffcf5687fb76dfa36d594d600ac454ed8', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773'}, 'expected_extra_tools': {}, 'expected_bootstrap_sha256': 'fe6b09c8a571418f67835a343d1484f9f6f5a6877baba927c8d2266e3fb4e7fc', 'expected_source_files_sha256': 'b454f3ada8f808ee8b0c0d99413138a0e55435e2b44da8c54167a6e262e1bd44', 'expected_director': {'pid': 36299, 'start_ticks': 180899762}, 'expected_workers': [{'pid': 36447, 'start_ticks': 180901031}, {'pid': 36448, 'start_ticks': 180901031}, {'pid': 36449, 'start_ticks': 180901031}], 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_C02_MEMORY_PROGRESS_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def decode(bundle, spec):
    require(spec.get('schema') == SCHEMA, 'SPEC_SCHEMA')
    tests, package = spec.get('source_test_paths'), spec.get('package_paths')
    require(spec.get('runtime_paths') == {} and spec.get('expected_extra_tools', {}) == {},
            'RUNTIME_SCOPE')
    require(isinstance(tests, dict) and len(tests) == 2
            and set(tests.values()) == TRUSTED_TESTS
            and isinstance(package, dict) and len(package) == 1, 'ASSET_SCOPE')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and len(pins) == 4
            and set(bundle) == set(pins)
            and set(pins) == set(tests) | set(package) | {spec.get('helper_asset')}, 'ASSET_SET')
    assets = {}
    total = 0
    for name, pin in pins.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name)
                and re.fullmatch(r'[a-f0-9]{64}', str(pin))
                and isinstance(bundle[name], str) and len(bundle[name]) <= 2800000,
                'ASSET_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        total += len(raw)
        require(len(raw) <= 2 * 1024 * 1024 and total <= 8 * 1024 * 1024
                and digest(raw) == pin, 'ASSET_HASH')
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        assets[name] = raw
    helper_name = spec['helper_asset']
    require(spec.get('helper_sha256') == FROZEN_HELPER_SHA256
            and helper_name in assets and digest(assets[helper_name]) == spec['helper_sha256'],
            'HELPER_PIN')
    helper = types.ModuleType('_nox_frozen_transaction_helpers')
    exec(compile(assets[helper_name], helper_name, 'exec'), helper.__dict__)
    return assets, helper


def compose(old, runtime, additions, contracts, rows):
    require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and old.get('instance_id') == 60509551 and old.get('owner_authorized') is True
            and old.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and old.get('mode') == 'NORMAL' and old.get('target') == 3
            and old.get('global_worker_cap') == 3, 'CONFIG_SCOPE')
    require(runtime == {}, 'RUNTIME_SCOPE')
    old_catalog = old.get('catalog') or {}
    require(old_catalog.get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1'
            and digest(encoded(old_catalog)) == old.get('catalog_sha256'), 'CATALOG_PIN')
    callback = old['module_pins']['owner_subagent_dispatcher.py']
    require(callback == CALLBACK_SHA256
            and old['module_pins'].get('owner_project_model_client.py') == MODEL_CLIENT_SHA256
            and old['project_executor']['model']['source_pins'].get('owner_project_model_client.py')
                == MODEL_CLIENT_SHA256, 'EXISTING_RUNTIME_PINS')
    new = copy.deepcopy(old)
    root = new['project_executor']['roots']['NOX_PROJECT_SOURCE']
    require(root['path'] == str(ROOT / SOURCE) and root['integration_kind'] == 'SOURCE_WORKSPACE',
            'SOURCE_ROOT')
    require(set(additions) == TRUSTED_TESTS and C02_SOURCE in root['allowed_paths'],
            'TRUSTED_TEST_SCOPE')
    require(not set(additions) & set(root['allowed_paths']), 'TEST_ALREADY_ALLOWED')
    root['allowed_paths'] = list(root['allowed_paths']) + sorted(additions)
    require(len(rows) == len(contracts) == 1, 'BATCH_COUNT')
    known = {row['id'] for row in old_catalog['tasks']}
    require(len(known) == len(old_catalog['tasks']), 'OLD_CATALOG_DUPLICATES')
    for row in rows:
        pin = row.get('params', {}).get('contract_sha256')
        contract = contracts.get(pin)
        require(isinstance(contract, dict) and pin == digest(encoded(contract)), 'CONTRACT_PIN')
        parent = contract.get('parent_task_id')
        require(contract.get('schema') == 'NOX_PROJECT_PLANNER_CONTRACT_V1'
                and parent == '3A01' and contract.get('queue_id') == 'Q2_MEMORY_KNOWLEDGE'
                and contract.get('root_id') == 'NOX_PROJECT_SOURCE'
                and contract.get('acceptance_scope') == 'SOURCE_PATCH_TESTED'
                and contract.get('original_task_accepted') is False, 'CONTRACT_SCOPE')
        require(contract.get('editable_paths') == [C02_SOURCE]
                and contract.get('allowed_new_paths') == []
                and isinstance(contract.get('context'), list) and len(contract['context']) == 3
                and {entry['path'] for entry in contract['context']} == TRUSTED_TESTS | {C02_SOURCE}
                and contract.get('verification', {}).get('kind') == 'python_unittest'
                and set(contract['verification'].get('modules', [])) == {p[:-3] for p in TRUSTED_TESTS}
                and contract['verification'].get('min_tests') == 22, 'CONTRACT_EDIT_AND_TEST_SCOPE')
        require(row.get('id') == contract['task_id'] and row['id'].startswith(parent + '.')
                and row['id'] not in known and row.get('handler') == 'owner_native_project_work'
                and row.get('resource') == 'CPU_LIGHT' and row.get('deps') == []
                and row.get('source_sha256') == callback and row.get('queue_id') == contract['queue_id']
                and row.get('params') == {'parent_task_id': parent, 'contract_sha256': pin},
                'CATALOG_ROW_SCOPE')
        known.add(row['id'])
        new['catalog']['tasks'].append(copy.deepcopy(row))
    new['catalog_sha256'] = digest(encoded(new['catalog']))
    # Reverting precisely the reviewed fields must reconstruct the complete old config.
    undo = copy.deepcopy(new)
    undo['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'] = old['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths']
    undo['catalog'], undo['catalog_sha256'] = old['catalog'], old['catalog_sha256']
    require(undo == old, 'UNRELATED_CONFIG_CHANGE')
    return new


def extend_marker(marker, additions, source_sha):
    require(marker.get('schema') == 'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
            and marker.get('root') == str(ROOT / SOURCE), 'BOOTSTRAP_SCOPE')
    old_pins = marker['file_pins']
    require(not set(old_pins) & set(additions), 'BOOTSTRAP_TEST_COLLISION')
    updated = copy.deepcopy(marker)
    updated['file_pins'].update({p: digest(raw) for p, raw in additions.items()})
    updated['source_file_count'] = len(updated['file_pins'])
    updated['source_refs'] = list(marker.get('source_refs', [])) + [{
        'kind': 'OWNER_REVIEWED_TRUSTED_TEST_APPEND', 'source_sha': source_sha,
        'previous_marker_sha256': digest(encoded(marker)), 'paths': sorted(additions)}]
    updated['manifest_sha256'] = digest(encoded({'schema': 'NOX_PROJECT_SOURCE_BASELINE_V1',
        'files': updated['file_pins'], 'source_refs': updated['source_refs']}))
    return updated


def apply_tracked(root, changes, before, helper, applied):
    """Expose partial progress to the caller even if a later atomic write fails."""
    for path, raw in changes.items():
        try:
            current = helper.read_regular(Path(root) / path)
        except FileNotFoundError:
            current = None
        require(current == before.get(path), 'CONCURRENT_WRITE_' + Path(path).name)
        applied.append(path)
        helper.atomic(Path(root) / path, raw, 0o644 if path.endswith('.py') else 0o600)
        require(helper.read_regular(Path(root) / path) == raw, 'WRITE_READBACK_' + Path(path).name)


def rollback_owned(root, changes, before, helper, applied):
    outcomes = helper.rollback_transaction(root, changes, before, applied)
    for path in reversed(applied):
        if not path.startswith(SOURCE + '/') or before.get(path) is not None:
            continue
        try:
            current = helper.read_regular(Path(root) / path)
        except FileNotFoundError:
            outcomes[path] = 'NEW_TEST_ABSENT'
            continue
        require(current == changes[path], 'NEW_TEST_CHANGED_NO_CLEANUP')
        (Path(root) / path).unlink()
        directory = os.open((Path(root) / path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        outcomes[path] = 'OWN_NEW_TEST_REMOVED_AFTER_ROLLBACK'
    return outcomes


def run(bundle, spec, root=ROOT):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha),
            'OWNER_CONTEXT')
    require(Path(root) == ROOT, 'INSTANCE_ROOT')
    assets, h = decode(bundle, spec)
    expected = spec['expected_native']
    before = h.preimages(root, expected)
    old = json.loads(before[CONFIG])
    require(all(expected.get('scripts/' + name) == pin for name, pin in old['module_pins'].items()),
            'ALL_MODULE_PINS')
    runtime = {path: assets[name] for name, path in spec['runtime_paths'].items()}
    additions = {path: assets[name] for name, path in spec['source_test_paths'].items()}
    package = {path: assets[name] for name, path in spec['package_paths'].items()}
    contracts = {}
    for path, raw in package.items():
        match = re.fullmatch(r'state/dispatcher/project_executor/package/contracts/([a-f0-9]{64})\.json', path)
        require(match and match[1] == digest(raw), 'PACKAGE_PATH')
        doc = json.loads(raw)
        require(encoded(doc) == raw, 'CANONICAL_CONTRACT')
        contracts[match[1]] = doc
    new = compose(old, runtime, additions, contracts, spec['catalog_append'])
    marker_raw = h.read_regular(root / MARKER, 65536)
    require(digest(marker_raw) == spec['expected_bootstrap_sha256'], 'BOOTSTRAP_PREIMAGE')
    marker = extend_marker(json.loads(marker_raw), additions, source_sha)
    before[MARKER] = marker_raw
    changes = dict(runtime)
    for path, raw in {**package, **{SOURCE + '/' + p: b for p, b in additions.items()}}.items():
        try:
            existing = h.read_regular(root / path)
        except FileNotFoundError:
            existing = None
        require(existing is None, 'ADDITIVE_FILE_EXISTS')
        before[path] = None
        changes[path] = raw
    changes[MARKER], changes[CONFIG] = encoded(marker), encoded(new)
    lock = root / 'state/owner_maintenance.lock'
    require(not lock.is_symlink(), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    protected = h.protected_snapshot(spec)
    applied, owned = [], []
    stopped = False
    baseline = snapshot = None
    receipt = {'schema': 'NOX_C02_MEMORY_PROGRESS_INSTALL_RECEIPT_V1',
        'request': request, 'source_sha': source_sha, 'started_at': time.time(), 'state': 'PREFLIGHT',
        'model_restarted': False, 'training_started': False, 'queue_writes': 0,
        'runtime_modules_changed': [],
        'original_tasks_accepted': 0, 'batch_task_ids': [r['id'] for r in spec['catalog_append']]}

    def guard():
        info = os.fstat(fd)
        named = lock.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and not info.st_mode & 0o022 and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
                'LEASE_CHANGED')
        require(h.stop_clear(root), 'OWNER_STOP')
        require(h.protected_snapshot(spec) == protected, 'PROTECTED_PROCESS_CHANGED')

    def history(state):
        result = {}
        for tid, row in state['tasks'].items():
            if row.get('handler') != 'owner_native_project_work':
                continue
            require(row.get('status') in ('done', 'blocked'), 'PROJECT_NOT_TERMINAL')
            event = (row.get('result') or {}).get('receipt') or {}
            require(event and (row.get('result') or {}).get('verified') is True
                    and event.get('claim') == row.get('owner_claim')
                    and event.get('task_id') == tid and event.get('original_task_accepted') is False,
                    'HISTORICAL_RECEIPT')
            result[tid] = h.exact_s03(root, event)
        return result

    def drain():
        deadline = time.monotonic() + 45
        while True:
            guard()
            state, active = h.queue_idle(root)
            processes = h.self_fd_children(spec)
            require(not set(receipt['batch_task_ids']) & set(state['tasks']), 'BATCH_ALREADY_ADMITTED')
            if not active and not processes['unexpected_children']:
                return state, processes
            require(time.monotonic() < deadline, 'ACTIVE_WORK_DRAIN_TIMEOUT')
            time.sleep(.5)

    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold('HOLD_C02_MEMORY_PROGRESS_MAINTENANCE_BUSY') from exc
        guard()
        h.preimages(root, expected)
        baseline, processes = drain()
        old_history = history(baseline)
        snapshot = h.source_snapshot(root, old)
        require(snapshot['files_sha256'] == spec['expected_source_files_sha256']
                and snapshot['bootstrap_sha256'] == spec['expected_bootstrap_sha256'], 'SOURCE_PREIMAGE')
        # Every model contract is validated against exactly the currently observed source
        # and its new immutable tests before any service is stopped.
        sys.path.insert(0, str(root / 'scripts'))
        import owner_project_planner as planner
        require(digest(h.read_regular(Path(planner.__file__))) == old['module_pins']['owner_project_planner.py'],
                'LOADED_PLANNER_PIN')
        for contract in contracts.values():
            context = {row['path']: additions[row['path']] if row['path'] in additions
                       else h.read_regular(root / SOURCE / h.relpath(row['path']))
                       for row in contract['context']}
            planner.validate_contract(contract, context)
        budget_module, budget_stage = h.load_budget_module(root,
            {'scripts/owner_autonomy_pool.py': before['scripts/owner_autonomy_pool.py']}, expected, request)
        receipt['budget'] = h.budget_preflight(new, budget_module, budget_stage, 'c02_memory_before_stop')
        backup = root / 'state/dispatcher/c02_memory_progress_rollback' / request
        require(not backup.exists() and not backup.is_symlink(), 'BACKUP_EXISTS')
        backup.mkdir(parents=True, mode=0o700)
        for path in changes:
            if before.get(path) is not None:
                h.atomic(backup / path, before[path])
        h.atomic(backup / 'queue_before.json', encoded(baseline))
        h.atomic(backup / 'source_before.json', encoded(snapshot))
        receipt['backup_path'] = str(backup)
        guard()
        h.preimages(root, expected)
        final_state, final_processes = drain()
        require(processes['processes'] == final_processes['processes']
                and h.preserve_terminal_history(baseline, final_state)['verified']
                and history(final_state) == old_history
                and h.source_snapshot(root, old) == snapshot, 'PREFLIGHT_CHANGED')
        stopped = True
        h.stop_checked()
        receipt['old_children_stopped'] = h.wait_previous_descendants_stopped(final_processes['children'])
        guard()
        final_state, active = h.queue_idle(root)
        require(not active and h.preserve_terminal_history(baseline, final_state)['verified']
                and history(final_state) == old_history
                and h.source_snapshot(root, old) == snapshot, 'STOPPED_PREIMAGE_CHANGED')
        apply_tracked(root, changes, before, h, applied)
        guard()
        after_source = h.source_snapshot(root, new)
        require(all(after_source['files'].get(p) == fact for p, fact in snapshot['files'].items())
                and set(after_source['files']) == set(snapshot['files']) | set(additions)
                and after_source['git_pins'] == snapshot['git_pins'], 'EXISTING_SOURCE_CHANGED')
        receipt['budget_before_start'] = h.budget_preflight(new, budget_module, budget_stage,
                                                         'c02_memory_before_start')
        guard()
        h.wait_previous_descendants_stopped(final_processes['children'])
        receipt['new_director'] = h.start_update_checked(root, owned)
        guard()
        require(h.source_snapshot(root, new) == after_source, 'SOURCE_CHANGED_BEFORE_ADMISSION')
        receipt.update(state='INSTALLED_ADMISSION_PENDING',
            preserved_runtime_pins=copy.deepcopy(old['module_pins']),
            config_sha256=digest(changes[CONFIG]), preserved_project_receipts=len(old_history),
            trusted_tests_added=sorted(additions), old_catalog_rows_preserved=len(old['catalog']['tasks']))
    except BaseException as exc:
        receipt['state'] = str(exc) if isinstance(exc, (Hold, h.Hold)) else 'HOLD_C02_MEMORY_PROGRESS_' + type(exc).__name__
        try:
            guard()
            if applied:
                current = h.supervisor('status')
                if current['state'] == 'RUNNING':
                    require(owned and h.process_identity(current.get('pid')) == owned[0], 'FOREIGN_DIRECTOR_NO_ROLLBACK')
                    descendants = h.descendant_snapshot(current['pid'])
                    h.stop_checked()
                    h.wait_previous_descendants_stopped(descendants)
                else:
                    require(current['state'] in ('STOPPED', 'FATAL', 'EXITED'), 'UNKNOWN_PROCESS_NO_ROLLBACK')
                receipt['rollback'] = rollback_owned(root, changes, before, h, applied)
                require(h.source_snapshot(root, old) == snapshot, 'ROLLBACK_SOURCE_CHANGED')
            if stopped and h.supervisor('status')['state'] in ('STOPPED', 'FATAL', 'EXITED'):
                h.preimages(root, expected)
                require(h.source_snapshot(root, old) == snapshot, 'RESTORE_SOURCE_PREIMAGE')
                h.wait_previous_descendants_stopped(final_processes['children'])
                receipt['budget_before_restore'] = h.budget_preflight(old, budget_module, budget_stage,
                                                                    'c02_memory_before_restore')
                guard()
                receipt['restored_director'] = h.start_checked(root)
        except Exception as failure:
            receipt['recovery'] = str(failure) if isinstance(failure, (Hold, h.Hold)) else type(failure).__name__
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        h.atomic(root / 'state/dispatcher' / ('c02_memory_progress_install_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_C02_MEMORY_PROGRESS_INSTALL=' + encoded(receipt).decode(), flush=True)
    observations = []
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        require(h.stop_clear(root) and h.protected_snapshot(spec) == protected, 'POST_ADMISSION_SCOPE_CHANGED')
        item = h.acceptance_snapshot(root, receipt['batch_task_ids'])
        if len(item['workers']) == 3 and item['director'] == receipt['new_director']:
            observations.append(item)
            if len(observations) > 2:
                observations = [observations[0], observations[-1]]
            if h.stable_three(observations) and any(row['claim_present'] for row in item['tasks']):
                break
        time.sleep(2)
    state, _ = h.queue_idle(root)
    require(h.preserve_terminal_history(final_state, state)['verified'] and history({
        'tasks': {tid: state['tasks'][tid] for tid in baseline['tasks']}}) == old_history,
        'HISTORICAL_PROGRESS_CHANGED')
    require(h.stable_three(observations) and any(row['claim_present'] for row in observations[-1]['tasks']),
            'THREE_WORKERS_OR_ADMISSION_UNVERIFIED')
    receipt.update(state='THREE_WORKERS_VERIFIED_C02_MEMORY_TASK_ADMITTED', observations=observations,
                   finished_at=time.time())
    h.atomic(root / 'state/dispatcher' / ('c02_memory_progress_install_' + request + '.json'), encoded(receipt))
    print('NOX_MAINT_C02_MEMORY_PROGRESS_INSTALL=' + encoded(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
