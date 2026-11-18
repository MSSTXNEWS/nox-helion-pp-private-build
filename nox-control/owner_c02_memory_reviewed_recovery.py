#!/usr/bin/env python3
"""Admit the exact owner-reviewed C02 recovery through the native executor.

The failed model claim remains canonical. This entry stages one reviewed plan
and its one content-addressed payload, then appends a new catalog row. Runtime,
source, bootstrap, tests and history remain unchanged during installation;
the native executor tests the reviewed patch before any source integration.
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
SCHEMA = 'NOX_C02_MEMORY_REVIEWED_RECOVERY_INSTALL_SPEC_V1'
CALLBACK_SHA256 = '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b'
MODEL_CLIENT_SHA256 = 'f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f'
FROZEN_HELPER_SHA256 = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
C02_SOURCE = 'nox_runpod/teacher_mesh/v38/synaptic_brain.py'
TRUSTED_TESTS = frozenset(('test_nox_c02_optional_starvation.py',
                           'test_nox_c02_existing_cognition.py'))
SOURCE_PREIMAGE_SHA256 = '8657ad367e6dd25b48ca8d6d7c4a947c0e1b0d4b979d63fbdaaf2a8e9ba5e74c'
FAILED_TASK = '3A01.project.c02_memory_capacity.20261118'
REVIEWED_TASK = FAILED_TASK + '.reviewed_reserve'
FAILED_CONTRACT_SHA256 = '4a8f20c371f3211c2351294bbe106a69a53f7a31e7051a039de9b227bcfd7f98'
FAILED_RECEIPT_SHA256 = '399e3dc5f153ac8832dfb41d74fead6b30f76f2be5257820af39a6e86dea7599'
FAILED_S03_ID = 'S03-1460ca0811874a9c'
FAILED_JOB = 'nox-project-a4fd720ef33ad332e23ab255'
FAILED_CLAIM = {'at': '2026-11-18 19:02:31 Europe/Moscow (UTC+3)',
                'nonce': '724c94a7150fa8f9415e0a28', 'pid': 49091, 'worker': 'nox-agent-01'}
PACKAGE = 'state/dispatcher/project_executor/package'
SPEC = {'schema': 'NOX_C02_MEMORY_REVIEWED_RECOVERY_INSTALL_SPEC_V1', 'reviewed_plan_sha256': '5d05ba50d058981ce8baeef6ba05a70a7d718709a84a4224a8adccfbf90df268', 'reviewed_payload_sha256': 'b504248ac1ae4a09338236fd7ad2402ca43cd561e2cc801f127ce221eb8cf44a', 'assets': {'c02r_payload_b504248ac1ae4a093382.source': 'b504248ac1ae4a09338236fd7ad2402ca43cd561e2cc801f127ce221eb8cf44a', 'c02r_plan_5d05ba50d058981ce8ba.json': '5d05ba50d058981ce8baeef6ba05a70a7d718709a84a4224a8adccfbf90df268', 'c02r_transaction_helpers.py': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'}, 'helper_asset': 'c02r_transaction_helpers.py', 'helper_sha256': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609', 'runtime_paths': {}, 'source_test_paths': {}, 'package_paths': {'c02r_plan_5d05ba50d058981ce8ba.json': 'state/dispatcher/project_executor/package/plans/5d05ba50d058981ce8baeef6ba05a70a7d718709a84a4224a8adccfbf90df268.json', 'c02r_payload_b504248ac1ae4a093382.source': 'state/dispatcher/project_executor/package/blobs/b504248ac1ae4a09338236fd7ad2402ca43cd561e2cc801f127ce221eb8cf44a'}, 'catalog_append': [{'id': '3A01.project.c02_memory_capacity.20261118.reviewed_reserve', 'handler': 'owner_native_project_work', 'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2, 'source_sha256': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'params': {'parent_task_id': '3A01', 'plan_sha256': '5d05ba50d058981ce8baeef6ba05a70a7d718709a84a4224a8adccfbf90df268'}, 'title': 'Apply the independently reviewed C02 capacity repair after preserving the failed model attempt'}], 'expected_bootstrap_sha256': '4140c8476a52d9d5e4f0f79f5ed3130acd8c3068b93d7ea0475c90771ceb7767', 'expected_director': {'pid': 49091, 'start_ticks': 181045817}, 'expected_extra_tools': {}, 'expected_native': {'config/owner_native_subagents.json': '84b0f78f6d7042b58f6ef003b5bd1ba3423e5244f635dded87b7affd617a3869', 'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_autonomy_pool.py': 'd5fb476f53e64d2014f27465c7bd64192158b5bcdd79a72ff7c962d853602339', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292', 'scripts/owner_project_executor.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': 'f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f', 'scripts/owner_project_native.py': '2c83ec53f7ee7c2d76bc1fac21c80adf76c58f83c5a219ba0294f9b3f713d707', 'scripts/owner_project_planner.py': 'e7bc83e4dea75f08ecb4e92fedf6ef98e0620f17c7b3b28ccb4728c6ddda68ac', 'scripts/owner_project_test_runner.py': '192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'scripts/owner_subagent_dispatcher.py': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'scripts/owner_subagent_instruction_truth.py': '61ef5e5ba66f6d65af2f59fbf5bc67bffcf5687fb76dfa36d594d600ac454ed8', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773'}, 'expected_source_files_sha256': 'cd8458a5f28420e3281c108e7fd27804aea02c726c10f8793e3e10588a095757', 'expected_workers': [{'pid': 49289, 'start_ticks': 181047780}, {'pid': 49290, 'start_ticks': 181047780}, {'pid': 49291, 'start_ticks': 181047780}], 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_C02_MEMORY_REVIEWED_RECOVERY_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def reviewed_pins(spec):
    plan_pin, payload_pin = spec.get('reviewed_plan_sha256'), spec.get('reviewed_payload_sha256')
    require(all(isinstance(pin, str) and re.fullmatch(r'[a-f0-9]{64}', pin)
                for pin in (plan_pin, payload_pin)) and plan_pin != payload_pin, 'REVIEWED_PINS')
    return plan_pin, payload_pin


def decode(bundle, spec):
    require(spec.get('schema') == SCHEMA, 'SPEC_SCHEMA')
    plan_pin, payload_pin = reviewed_pins(spec)
    tests, package = spec.get('source_test_paths'), spec.get('package_paths')
    require(spec.get('runtime_paths') == {} and tests == {}
            and spec.get('expected_extra_tools', {}) == {},
            'RUNTIME_SCOPE')
    require(isinstance(package, dict) and len(package) == 2
            and set(package.values()) == {PACKAGE + '/plans/' + plan_pin + '.json',
                                          PACKAGE + '/blobs/' + payload_pin}, 'ASSET_SCOPE')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and len(pins) == 3
            and set(bundle) == set(pins)
            and set(pins) == set(package) | {spec.get('helper_asset')}, 'ASSET_SET')
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


def compose(old, runtime, additions, plans, rows, spec):
    plan_pin, payload_pin = reviewed_pins(spec)
    require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and old.get('instance_id') == 60509551 and old.get('owner_authorized') is True
            and old.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and old.get('mode') == 'NORMAL' and old.get('target') == 3
            and old.get('global_worker_cap') == 3, 'CONFIG_SCOPE')
    require(runtime == {} and additions == {}, 'RUNTIME_SCOPE')
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
    require(TRUSTED_TESTS | {C02_SOURCE} <= set(root['allowed_paths']), 'EXISTING_SOURCE_SCOPE')
    require(len(rows) == len(plans) == 1, 'BATCH_COUNT')
    known = {row['id'] for row in old_catalog['tasks']}
    require(len(known) == len(old_catalog['tasks']), 'OLD_CATALOG_DUPLICATES')
    for row in rows:
        pin = row.get('params', {}).get('plan_sha256')
        plan = plans.get(pin)
        require(pin == plan_pin and isinstance(plan, dict)
                and pin == digest(encoded(plan)), 'REVIEWED_PLAN_PIN')
        require(plan.get('schema') == 'NOX_PROJECT_WORK_PLAN_V1'
                and plan.get('task_id') == REVIEWED_TASK and plan.get('parent_task_id') == '3A01'
                and plan.get('queue_id') == 'Q2_MEMORY_KNOWLEDGE'
                and plan.get('root_id') == 'NOX_PROJECT_SOURCE'
                and plan.get('operation') == 'apply_reviewed_files'
                and plan.get('review_origin') == 'OWNER_REVIEWED' and 'contract_sha256' not in plan
                and plan.get('acceptance_scope') == 'SOURCE_PATCH_TESTED'
                and plan.get('original_task_accepted') is False, 'REVIEWED_PLAN_SCOPE')
        require(plan.get('files') == [{'path': C02_SOURCE, 'before_sha256': SOURCE_PREIMAGE_SHA256,
                'after_sha256': payload_pin, 'payload_sha256': payload_pin}]
                and isinstance(plan.get('context'), list) and len(plan['context']) == 3
                and {entry['path'] for entry in plan['context']} == TRUSTED_TESTS | {C02_SOURCE}
                and plan.get('verification', {}).get('kind') == 'python_unittest'
                and set(plan['verification'].get('modules', [])) == {p[:-3] for p in TRUSTED_TESTS}
                and plan['verification'].get('min_tests') == 22, 'REVIEWED_EDIT_AND_TEST_SCOPE')
        require(row.get('id') == REVIEWED_TASK
                and row['id'] not in known and row.get('handler') == 'owner_native_project_work'
                and row.get('resource') == 'CPU_LIGHT' and row.get('deps') == []
                and row.get('source_sha256') == callback and row.get('queue_id') == plan['queue_id']
                and row.get('params') == {'parent_task_id': '3A01', 'plan_sha256': pin},
                'CATALOG_ROW_SCOPE')
        known.add(row['id'])
        new['catalog']['tasks'].append(copy.deepcopy(row))
    new['catalog_sha256'] = digest(encoded(new['catalog']))
    # Reverting precisely the reviewed fields must reconstruct the complete old config.
    undo = copy.deepcopy(new)
    undo['catalog'], undo['catalog_sha256'] = old['catalog'], old['catalog_sha256']
    require(undo == old, 'UNRELATED_CONFIG_CHANGE')
    return new


def check_failed_model(state, root, helper):
    task = state['tasks'].get(FAILED_TASK) or {}
    result = task.get('result') or {}
    receipt = result.get('receipt') or {}
    event = receipt.get('worker_result') or {}
    evidence = event.get('project_evidence') or {}
    planner = event.get('planner_receipt') or {}
    require(task.get('handler') == 'owner_native_project_work' and task.get('status') == 'blocked'
            and task.get('owner_claim') == FAILED_CLAIM and result.get('verified') is True
            and digest(encoded(receipt)) == result.get('receipt_sha256') == FAILED_RECEIPT_SHA256
            and receipt.get('claim') == FAILED_CLAIM and receipt.get('task_id') == FAILED_TASK
            and receipt.get('job_id') == FAILED_JOB and receipt.get('parent_task_id') == '3A01'
            and receipt.get('queue_id') == 'Q2_MEMORY_KNOWLEDGE'
            and receipt.get('source_sha256') == CALLBACK_SHA256
            and receipt.get('phase') == 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
            and receipt.get('project_source_changed') is False
            and receipt.get('original_task_accepted') is False
            and receipt.get('live_service_deployed') is False, 'EXACT_FAILED_MODEL_RECEIPT')
    trace = planner.get('trace')
    require(event.get('state') == evidence.get('reason') == planner.get('state')
            == 'PLANNER_REPEATED_ACTION_NO_PROGRESS'
            and evidence.get('state') == 'BLOCKED_PLANNER'
            and evidence.get('task_id') == planner.get('task_id') == FAILED_TASK
            and evidence.get('claim') == FAILED_CLAIM['nonce']
            and evidence.get('project_source_changed') is False
            and receipt.get('plan_sha256') is None and evidence.get('plan_sha256') is None
            and evidence.get('tests_sha256') is None
            and planner.get('contract_sha256') == FAILED_CONTRACT_SHA256
            and planner.get('original_task_accepted') is False
            and isinstance(trace, list) and len(trace) == 10
            and all(isinstance(row, dict) and row.get('action') == 'read'
                    and row.get('path') == C02_SOURCE for row in trace), 'FAILED_MODEL_NO_SOURCE_PROGRESS')
    proof = helper.exact_s03(root, receipt)
    require(proof.get('verified') is True and proof.get('s03_item_id') == FAILED_S03_ID
            and proof.get('receipt_sha256') == FAILED_RECEIPT_SHA256, 'FAILED_MODEL_S03_CHANGED')
    return {'task_id': FAILED_TASK, 'receipt_sha256': FAILED_RECEIPT_SHA256,
            'claim': copy.deepcopy(FAILED_CLAIM), 's03': proof,
            'model_read_turns': len(trace), 'model_source_changed': False,
            'recovery_review_origin': 'OWNER_REVIEWED'}


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
        if not path.startswith(PACKAGE + '/') or before.get(path) is not None:
            continue
        try:
            current = helper.read_regular(Path(root) / path)
        except FileNotFoundError:
            outcomes[path] = 'NEW_ASSET_ABSENT'
            continue
        require(current == changes[path], 'NEW_ASSET_CHANGED_NO_CLEANUP')
        (Path(root) / path).unlink()
        directory = os.open((Path(root) / path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        outcomes[path] = 'OWN_NEW_ASSET_REMOVED_AFTER_ROLLBACK'
    return outcomes


def run(bundle, spec, root=ROOT):
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha),
            'OWNER_CONTEXT')
    require(Path(root) == ROOT, 'INSTANCE_ROOT')
    assets, h = decode(bundle, spec)
    plan_pin, payload_pin = reviewed_pins(spec)
    expected = spec['expected_native']
    before = h.preimages(root, expected)
    old = json.loads(before[CONFIG])
    require(all(expected.get('scripts/' + name) == pin for name, pin in old['module_pins'].items()),
            'ALL_MODULE_PINS')
    runtime = {path: assets[name] for name, path in spec['runtime_paths'].items()}
    additions = {path: assets[name] for name, path in spec['source_test_paths'].items()}
    package = {path: assets[name] for name, path in spec['package_paths'].items()}
    plans = {}
    for path, raw in package.items():
        if path == PACKAGE + '/plans/' + plan_pin + '.json':
            require(digest(raw) == plan_pin, 'REVIEWED_PLAN_PIN')
            doc = json.loads(raw)
            require(encoded(doc) == raw, 'CANONICAL_PLAN')
            plans[plan_pin] = doc
        else:
            require(path == PACKAGE + '/blobs/' + payload_pin
                    and digest(raw) == payload_pin, 'PACKAGE_PAYLOAD_PIN')
            compile(raw, C02_SOURCE, 'exec')
    new = compose(old, runtime, additions, plans, spec['catalog_append'], spec)
    marker_raw = h.read_regular(root / MARKER, 65536)
    require(digest(marker_raw) == spec['expected_bootstrap_sha256'], 'BOOTSTRAP_PREIMAGE')
    changes = dict(runtime)
    for path, raw in {**package, **{SOURCE + '/' + p: b for p, b in additions.items()}}.items():
        try:
            existing = h.read_regular(root / path)
        except FileNotFoundError:
            existing = None
        require(existing is None, 'ADDITIVE_FILE_EXISTS')
        before[path] = None
        changes[path] = raw
    changes[CONFIG] = encoded(new)
    lock = root / 'state/owner_maintenance.lock'
    require(not lock.is_symlink(), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    protected = h.protected_snapshot(spec)
    applied, owned = [], []
    stopped = False
    baseline = snapshot = None
    receipt = {'schema': 'NOX_C02_MEMORY_REVIEWED_RECOVERY_INSTALL_RECEIPT_V1',
        'request': request, 'source_sha': source_sha, 'started_at': time.time(), 'state': 'PREFLIGHT',
        'model_restarted': False, 'training_started': False, 'queue_writes': 0,
        'runtime_modules_changed': [],
        'source_tree_writes': 0, 'review_origin': 'OWNER_REVIEWED', 'model_generated_recovery': False,
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
            raise Hold('HOLD_C02_MEMORY_REVIEWED_RECOVERY_MAINTENANCE_BUSY') from exc
        guard()
        h.preimages(root, expected)
        baseline, processes = drain()
        old_history = history(baseline)
        receipt['failed_model_predecessor'] = check_failed_model(baseline, root, h)
        snapshot = h.source_snapshot(root, old)
        require(snapshot['files_sha256'] == spec['expected_source_files_sha256']
                and snapshot['bootstrap_sha256'] == spec['expected_bootstrap_sha256'], 'SOURCE_PREIMAGE')
        # Validate the owner-reviewed plan and its exact source/test preimages
        # before stopping anything. Tests and integration remain native work.
        sys.path.insert(0, str(root / 'scripts'))
        import owner_project_executor as executor
        require(digest(h.read_regular(Path(executor.__file__))) == old['module_pins']['owner_project_executor.py'],
                'LOADED_EXECUTOR_PIN')
        executor.validate_config(old['project_executor'])
        for plan in plans.values():
            executor.validate_plan(plan, old['project_executor'])
            for row in plan['context']:
                require(digest(h.read_regular(root / SOURCE / h.relpath(row['path']))) == row['sha256'],
                        'REVIEWED_CONTEXT_CHANGED')
        budget_module, budget_stage = h.load_budget_module(root,
            {'scripts/owner_autonomy_pool.py': before['scripts/owner_autonomy_pool.py']}, expected, request)
        receipt['budget'] = h.budget_preflight(new, budget_module, budget_stage, 'c02_reviewed_before_stop')
        backup = root / 'state/dispatcher/c02_memory_reviewed_recovery_rollback' / request
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
        require(after_source == snapshot, 'EXISTING_SOURCE_CHANGED')
        receipt['budget_before_start'] = h.budget_preflight(new, budget_module, budget_stage,
                                                         'c02_reviewed_before_start')
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
        receipt['state'] = str(exc) if isinstance(exc, (Hold, h.Hold)) else 'HOLD_C02_MEMORY_REVIEWED_RECOVERY_' + type(exc).__name__
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
                                                                    'c02_reviewed_before_restore')
                guard()
                receipt['restored_director'] = h.start_checked(root)
        except Exception as failure:
            receipt['recovery'] = str(failure) if isinstance(failure, (Hold, h.Hold)) else type(failure).__name__
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        h.atomic(root / 'state/dispatcher' / ('c02_memory_reviewed_recovery_install_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_C02_MEMORY_REVIEWED_RECOVERY_INSTALL=' + encoded(receipt).decode(), flush=True)
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
    receipt.update(state='THREE_WORKERS_VERIFIED_C02_REVIEWED_RECOVERY_ADMITTED', observations=observations,
                   finished_at=time.time())
    h.atomic(root / 'state/dispatcher' / ('c02_memory_reviewed_recovery_install_' + request + '.json'), encoded(receipt))
    print('NOX_MAINT_C02_MEMORY_REVIEWED_RECOVERY_INSTALL=' + encoded(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
