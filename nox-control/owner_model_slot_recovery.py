#!/usr/bin/env python3
"""Repair bounded model-slot contention and retry two exact blocked model tasks.

The request pins every runtime byte, existing source preimage and new contract.
Only the existing idle dispatcher is restarted. Model services, source files,
S03 contents and all historical claims remain unchanged. Exact failed receipts
authorize new task IDs after the model client has changed; no claim is replayed.
"""
from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import importlib.util
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
SCHEMA = 'NOX_MODEL_SLOT_RECOVERY_INSTALL_SPEC_V1'
MODULES = {'owner_project_model_client.py'}
EXTRA_TOOLS = set()
SPEC = {'schema': 'NOX_MODEL_SLOT_RECOVERY_INSTALL_SPEC_V1', 'assets': {'slot_contract_3f43e152774c159bbe45.json': '3f43e152774c159bbe452f0ac917b047db2f450197554cdf4858801eb3a83abe', 'slot_contract_60a6abf6691f6c3fb186.json': '60a6abf6691f6c3fb186b428e8a856da9119ed5a245f77e65a0734ef1168fd14', 'slot_transaction_helpers.py': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609', 'slot_model_client.py': 'f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f'}, 'helper_asset': 'slot_transaction_helpers.py', 'helper_sha256': '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609', 'runtime_paths': {'slot_model_client.py': 'scripts/owner_project_model_client.py'}, 'source_test_paths': {}, 'package_paths': {'slot_contract_3f43e152774c159bbe45.json': 'state/dispatcher/project_executor/package/contracts/3f43e152774c159bbe452f0ac917b047db2f450197554cdf4858801eb3a83abe.json', 'slot_contract_60a6abf6691f6c3fb186.json': 'state/dispatcher/project_executor/package/contracts/60a6abf6691f6c3fb186b428e8a856da9119ed5a245f77e65a0734ef1168fd14.json'}, 'catalog_append': [{'deps': [], 'estimated_cost': 2, 'handler': 'owner_native_project_work', 'id': '6V14-12.project.readonly_transient_retry.slot_retry.20261118', 'params': {'contract_sha256': '3f43e152774c159bbe452f0ac917b047db2f450197554cdf4858801eb3a83abe', 'parent_task_id': '6V14-12'}, 'priority': 'P1', 'queue_id': 'Q4_INTEGRATION_ACCEPTANCE', 'resource': 'CPU_LIGHT', 'source_sha256': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'title': 'Resume bounded read-only probes after transient failures without requiring a senior model'}, {'deps': [], 'estimated_cost': 2, 'handler': 'owner_native_project_work', 'id': '4A02.project.bilingual_task_matrix.slot_retry.20261118', 'params': {'contract_sha256': '60a6abf6691f6c3fb186b428e8a856da9119ed5a245f77e65a0734ef1168fd14', 'parent_task_id': '4A02'}, 'priority': 'P1', 'queue_id': 'Q3_TRAINING_WEIGHTS', 'resource': 'CPU_LIGHT', 'source_sha256': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'title': 'Require independent Russian and Spanish coverage for every training and evaluation task'}], 'recovery_requirements': [{'old_task_mutation_allowed': False, 'original_task_accepted': False, 'parent_task_id': '6V14-12', 'predecessor_changed_candidate_paths': [], 'predecessor_claim_nonce': '42ff37487498fc7207f9224c', 'predecessor_completed_model_turns': 0, 'predecessor_contract_sha256': '510dbdec4dd2538ebeac2f8fdd0ecda8305ba9ee370ec53820a1f62b92c5a16e', 'predecessor_job_id': 'nox-project-0dbeb482e6f17525d54eb1a3', 'predecessor_owner_claim': {'at': '2026-11-18 18:22:08 Europe/Moscow (UTC+3)', 'nonce': '42ff37487498fc7207f9224c', 'pid': 27386, 'worker': 'nox-agent-02'}, 'predecessor_plan_sha256': None, 'predecessor_planner_receipt_sha256': 'eee8445e490b86c908c6354e0537c9ed1f6de6a43c8479e0d25c0067c3ecaa43', 'predecessor_project_source_changed': False, 'predecessor_reason': 'HOLD_PROJECT_PLANNER_MODEL_SLOT_BUSY', 'predecessor_receipt_phase': 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED', 'predecessor_receipt_sha256': '96c6b450edbc7e81e4e5b6dbc0a2e3bb2197362fa03adf520010160f907f14df', 'predecessor_s03_item_id': 'S03-92864f46e6c14349', 'predecessor_status': 'blocked', 'predecessor_task_id': '6V14-12.project.readonly_transient_retry.20261118', 'retry_task_id': '6V14-12.project.readonly_transient_retry.slot_retry.20261118', 'source_context_pins': {'owner_dispatcher_mentor.py': 'b980a61884965f4838f8deafd43dac2ea4642e41dea7870d6a6904ee5a274fc6', 'test_3b05_skill_ancestor_swap.py': '21f8538fec15d39b4dbc875a4087be1c911c60b06ba04e2c682e8810f7b8b8fd', 'test_nox_readonly_retry_backoff.py': '98075e700bac561c814155a60a6448d2b78f0c52ccad22f6b3e62f311fd4479f', 'test_nox_skill_evidence_strict_json.py': '623bfb4ba2d28d3dd3dbc5e46852ed5be5c29d516d20a390aed69c2ec5c3089c'}}, {'old_task_mutation_allowed': False, 'original_task_accepted': False, 'parent_task_id': '4A02', 'predecessor_changed_candidate_paths': [], 'predecessor_claim_nonce': 'fd1e9993222d05a57e6987d5', 'predecessor_completed_model_turns': 0, 'predecessor_contract_sha256': '683c5086d66e750d4ed19a2ddc8b0fa8f88878050797eb0f989ee5ef70894251', 'predecessor_job_id': 'nox-project-58f6a3879f922c922f307097', 'predecessor_owner_claim': {'at': '2026-11-18 18:22:02 Europe/Moscow (UTC+3)', 'nonce': 'fd1e9993222d05a57e6987d5', 'pid': 27386, 'worker': 'nox-agent-03'}, 'predecessor_plan_sha256': None, 'predecessor_planner_receipt_sha256': '896627bd20aaee31b18dcba51b4d1250a13c78ede85fc42c4d131cc55a44c21d', 'predecessor_project_source_changed': False, 'predecessor_reason': 'HOLD_PROJECT_PLANNER_MODEL_SLOT_BUSY', 'predecessor_receipt_phase': 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED', 'predecessor_receipt_sha256': 'c103ceddde86b35cd5a92bac7240502357c8359b5e2920b73069c46425a2f89c', 'predecessor_s03_item_id': 'S03-4beec9d9e7d74391', 'predecessor_status': 'blocked', 'predecessor_task_id': '4A02.project.bilingual_task_matrix.20261118', 'retry_task_id': '4A02.project.bilingual_task_matrix.slot_retry.20261118', 'source_context_pins': {'forge_split_guard.py': '06940cb13bd568d4cfaa893aab9e43c6d0b03010163cba13f2f5bf5ea144db00', 'test_forge_split_guard.py': '3efe025681c3a54cbfac10f0da6f20ff7b2e249ed087b8db39d582002f32c080', 'test_nox_forge_language_task_coverage.py': '7f44a17db729ac2a4e74c6581e47db538880bc83fc386a02a753c6dc89434de1', 'test_nox_forge_split_coverage.py': 'fd815f9a743bfcdf6e71a8ebb035a180c031aa8f0c5e0484164d36aaf309f6cf'}}], 'expected_native': {'scripts/nox_dispatcher_t855u.py': '9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21', 'scripts/owner_subagent_dispatcher.py': '84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b', 'scripts/owner_subagent_processes.py': 'f6b2f98ac5c7c291ffef009886442302d407921ad12827044443e72e75eb0aae', 'scripts/owner_autonomy_pool.py': 'd5fb476f53e64d2014f27465c7bd64192158b5bcdd79a72ff7c962d853602339', 'scripts/owner_subagent_instruction_truth.py': '61ef5e5ba66f6d65af2f59fbf5bc67bffcf5687fb76dfa36d594d600ac454ed8', 'scripts/owner_task_plans.py': '7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773', 'scripts/owner_component_tasks.py': '190bf9948dbe821b5fe3512e3edbc0a7a9348b14aa2a154274e78f058d5d6d5d', 'scripts/owner_resource_policy.py': '3a7b02a269508472b2a950f28cb067045913842261f8e80bc0804c7cc7cab834', 'config/owner_native_subagents.json': '5407848d326d704caf0611c78045938b9cb6c4f11ba0e48150c130bb0c3a9f38', 'scripts/owner_project_executor.py': 'fcb77cc59eb9a88dde68da62db05195a494fbeda40dad2954c77de95a807eae6', 'scripts/owner_project_model_bridge.py': '7f18d69529582b65f7b8d1d708f30070839bda7c4eb90719cf66dbc54deb58c9', 'scripts/owner_project_model_client.py': '52e62a143d16f387899ff1737ce4eb698dee5ceca510fc6f97f931c11a0aec10', 'scripts/owner_project_native.py': '2c83ec53f7ee7c2d76bc1fac21c80adf76c58f83c5a219ba0294f9b3f713d707', 'scripts/owner_project_planner.py': 'e7bc83e4dea75f08ecb4e92fedf6ef98e0620f17c7b3b28ccb4728c6ddda68ac', 'scripts/owner_project_test_runner.py': '192d0c1b7b87447d4f088073fb6f6bfe9f733cf542df8f9b0eaf911d374f1e3f', 'scripts/owner_dispatcher_mentor.py': '12211a29f77de8e5181d4dd78c35d5da2ed5de0dc6ea529149d32f0896809292'}, 'expected_extra_tools': {}, 'expected_bootstrap_sha256': 'fe6b09c8a571418f67835a343d1484f9f6f5a6877baba927c8d2266e3fb4e7fc', 'expected_source_files_sha256': '864b117e13171f3b4d5faa4d86dbf04a611093258597486b84fa587900e6f7ba', 'expected_director': {'pid': 27386, 'start_ticks': 180803640}, 'expected_workers': [{'pid': 27518, 'start_ticks': 180804769}, {'pid': 27519, 'start_ticks': 180804769}, {'pid': 27520, 'start_ticks': 180804769}], 'protected_processes': {'chat': {'pgrp': 3266857, 'pid': 3266857, 'ppid': 114, 'start_ticks': 172046662}, 'proxy': {'pgrp': 3703386, 'pid': 3703386, 'ppid': 114, 'start_ticks': 175609570}, 'web': {'pgrp': 3505392, 'pid': 3505392, 'ppid': 114, 'start_ticks': 173653097}}}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_MODEL_SLOT_RECOVERY_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def decode(bundle, spec):
    require(spec.get('schema') == SCHEMA, 'SPEC_SCHEMA')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and 1 <= len(pins) <= 32
            and set(bundle) == set(pins), 'ASSET_SET')
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
    require(helper_name in assets and digest(assets[helper_name]) == spec['helper_sha256'],
            'HELPER_PIN')
    helper = types.ModuleType('_nox_frozen_transaction_helpers')
    exec(compile(assets[helper_name], helper_name, 'exec'), helper.__dict__)
    return assets, helper






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




def compose(old, runtime, additions, contracts, rows):
    require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and old.get('instance_id') == 60509551 and old.get('owner_authorized') is True
            and old.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and old.get('mode') == 'NORMAL' and old.get('target') == 3
            and old.get('global_worker_cap') == 3, 'CONFIG_SCOPE')
    path = 'scripts/owner_project_model_client.py'
    require(set(runtime) == {path} and not additions, 'RUNTIME_SCOPE')
    catalog = old.get('catalog') or {}
    require(catalog.get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1'
            and digest(encoded(catalog)) == old.get('catalog_sha256'), 'CATALOG_PIN')
    pin = digest(runtime[path])
    require(pin != old['module_pins']['owner_project_model_client.py'], 'CLIENT_UNCHANGED')
    require(old['project_executor']['model']['source_pins']['owner_project_model_client.py']
            == old['module_pins']['owner_project_model_client.py'], 'OLD_CLIENT_BINDING')
    new = copy.deepcopy(old)
    new['module_pins']['owner_project_model_client.py'] = pin
    new['project_executor']['model']['source_pins']['owner_project_model_client.py'] = pin
    root = new['project_executor']['roots']['NOX_PROJECT_SOURCE']
    require(root['path'] == str(ROOT / SOURCE) and root['integration_kind'] == 'SOURCE_WORKSPACE',
            'SOURCE_ROOT')
    require(len(rows) == len(contracts) == 2, 'BATCH_COUNT')
    known = {row['id'] for row in catalog['tasks']}
    require(len(known) == len(catalog['tasks']), 'OLD_CATALOG_DUPLICATES')
    parents = set()
    for row in rows:
        contract_pin = row.get('params', {}).get('contract_sha256')
        contract = contracts.get(contract_pin)
        require(isinstance(contract, dict) and contract_pin == digest(encoded(contract)), 'CONTRACT_PIN')
        parent = contract.get('parent_task_id')
        require(contract.get('schema') == 'NOX_PROJECT_PLANNER_CONTRACT_V1'
                and contract.get('root_id') == 'NOX_PROJECT_SOURCE'
                and contract.get('acceptance_scope') == 'SOURCE_PATCH_TESTED'
                and contract.get('original_task_accepted') is False, 'CONTRACT_SCOPE')
        require(row.get('id') == contract['task_id'] and row['id'].startswith(parent + '.')
                and '.slot_retry.' in row['id'] and row['id'] not in known
                and row.get('handler') == 'owner_native_project_work'
                and row.get('resource') == 'CPU_LIGHT' and row.get('deps') == []
                and row.get('source_sha256') == old['module_pins']['owner_subagent_dispatcher.py']
                and row.get('queue_id') == contract['queue_id']
                and row.get('params') == {'parent_task_id': parent, 'contract_sha256': contract_pin},
                'CATALOG_ROW_SCOPE')
        require(parent in ('6V14-12', '4A02') and parent not in parents, 'BATCH_PARENT_SCOPE')
        parents.add(parent)
        known.add(row['id'])
        new['catalog']['tasks'].append(copy.deepcopy(row))
    new['catalog_sha256'] = digest(encoded(new['catalog']))
    undo = copy.deepcopy(new)
    undo['module_pins'] = old['module_pins']
    undo['project_executor']['model']['source_pins'] = old['project_executor']['model']['source_pins']
    undo['catalog'], undo['catalog_sha256'] = old['catalog'], old['catalog_sha256']
    require(undo == old, 'UNRELATED_CONFIG_CHANGE')
    return new


def check_recovery_predecessors(state, spec, root, helper):
    required = spec['recovery_requirements']
    require(isinstance(required, list) and len(required) == 2, 'PREDECESSOR_COUNT')
    result = {}
    retries = {row['id'] for row in spec['catalog_append']}
    require({row['retry_task_id'] for row in required} == retries, 'RETRY_BINDING')
    for need in required:
        tid = need['predecessor_task_id']
        task = state['tasks'].get(tid) or {}
        value = task.get('result') or {}
        event = value.get('receipt') or {}
        worker = event.get('worker_result') or {}
        evidence = worker.get('project_evidence') or {}
        planner = worker.get('planner_receipt') or {}
        require(task.get('status') == 'blocked' and task.get('handler') == 'owner_native_project_work'
                and task.get('owner_claim') == need['predecessor_owner_claim']
                and value.get('verified') is True
                and digest(encoded(event)) == value.get('receipt_sha256') == need['predecessor_receipt_sha256']
                and event.get('claim') == task['owner_claim']
                and event.get('task_id') == tid and event.get('original_task_accepted') is False
                and event.get('project_source_changed') is False
                and event.get('job_id') == need['predecessor_job_id']
                and event.get('phase') == need['predecessor_receipt_phase'], 'EXACT_BLOCKED_PREDECESSOR')
        require(worker.get('state') == evidence.get('reason') == planner.get('state')
                == 'HOLD_PROJECT_PLANNER_MODEL_SLOT_BUSY'
                and evidence.get('state') == 'BLOCKED_PLANNER'
                and evidence.get('project_source_changed') is False
                and planner.get('completed_model_turns') == 0 and planner.get('trace') == []
                and planner.get('changed_candidate_paths') == []
                and planner.get('task_id') == tid
                and planner.get('contract_sha256') == need['predecessor_contract_sha256']
                and digest(encoded(planner)) == need['predecessor_planner_receipt_sha256'],
                'PREDECESSOR_NOT_ZERO_TURN_SLOT_FAILURE')
        proof = helper.exact_s03(root, event)
        require(proof.get('verified') is True and proof.get('s03_item_id') == need['predecessor_s03_item_id'],
                'PREDECESSOR_S03_CHANGED')
        result[tid] = proof
    return result


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
    for path in runtime:
        if path not in before:
            try:
                before[path] = h.read_regular(root / path)
            except FileNotFoundError:
                before[path] = None
            require(before[path] is None or digest(before[path]) == spec['expected_extra_tools'].get(path),
                    'EXTRA_TOOL_PREIMAGE')
    changes[CONFIG] = encoded(new)
    lock = root / 'state/owner_maintenance.lock'
    require(not lock.is_symlink(), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    protected = h.protected_snapshot(spec)
    applied, owned = [], []
    stopped = False
    baseline = snapshot = None
    receipt = {'schema': 'NOX_MODEL_SLOT_RECOVERY_INSTALL_RECEIPT_V1',
        'request': request, 'source_sha': source_sha, 'started_at': time.time(), 'state': 'PREFLIGHT',
        'model_restarted': False, 'training_started': False, 'queue_writes': 0,
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
            raise Hold('HOLD_MODEL_SLOT_RECOVERY_MAINTENANCE_BUSY') from exc
        guard()
        h.preimages(root, expected)
        baseline, processes = drain()
        old_history = history(baseline)
        receipt['recovery_predecessors'] = check_recovery_predecessors(baseline, spec, root, h)
        snapshot = h.source_snapshot(root, old)
        require(snapshot['files_sha256'] == spec['expected_source_files_sha256']
                and snapshot['bootstrap_sha256'] == spec['expected_bootstrap_sha256'], 'SOURCE_PREIMAGE')
        # Every model contract is validated against exactly the currently observed source
        # and its existing immutable tests before any service is stopped.
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
        receipt['budget'] = h.budget_preflight(new, budget_module, budget_stage, 'model_slot_before_stop')
        backup = root / 'state/dispatcher/model_slot_recovery_rollback' / request
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
                                                         'model_slot_before_start')
        receipt['new_director'] = h.start_update_checked(root, owned)
        guard()
        require(h.source_snapshot(root, new) == after_source, 'SOURCE_CHANGED_BEFORE_ADMISSION')
        receipt.update(state='INSTALLED_ADMISSION_PENDING',
            runtime_pins={p: digest(b) for p, b in runtime.items()},
            config_sha256=digest(changes[CONFIG]), preserved_project_receipts=len(old_history),
            trusted_tests_added=sorted(additions), old_catalog_rows_preserved=len(old['catalog']['tasks']))
    except BaseException as exc:
        receipt['state'] = str(exc) if isinstance(exc, (Hold, h.Hold)) else 'HOLD_MODEL_SLOT_RECOVERY_' + type(exc).__name__
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
                receipt['rollback'] = h.rollback_transaction(root, changes, before, applied)
                require(h.source_snapshot(root, old) == snapshot, 'ROLLBACK_SOURCE_CHANGED')
            if stopped and h.supervisor('status')['state'] in ('STOPPED', 'FATAL', 'EXITED'):
                h.preimages(root, expected)
                require(h.source_snapshot(root, old) == snapshot, 'RESTORE_SOURCE_PREIMAGE')
                h.wait_previous_descendants_stopped(final_processes['children'])
                receipt['restored_director'] = h.start_checked(root)
        except Exception as failure:
            receipt['recovery'] = str(failure) if isinstance(failure, (Hold, h.Hold)) else type(failure).__name__
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        h.atomic(root / 'state/dispatcher' / ('model_slot_recovery_install_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_MODEL_SLOT_RECOVERY_INSTALL=' + encoded(receipt).decode(), flush=True)
    observations = []
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        require(h.stop_clear(root) and h.protected_snapshot(spec) == protected, 'POST_ADMISSION_SCOPE_CHANGED')
        item = h.acceptance_snapshot(root, receipt['batch_task_ids'])
        if len(item['workers']) == 3 and item['director'] == receipt['new_director']:
            observations.append(item)
            if len(observations) > 2:
                observations = [observations[0], observations[-1]]
            if h.stable_three(observations) and all(row['claim_present'] for row in item['tasks']):
                break
        time.sleep(2)
    state, _ = h.queue_idle(root)
    require(h.preserve_terminal_history(final_state, state)['verified'] and history({
        'tasks': {tid: state['tasks'][tid] for tid in baseline['tasks']}}) == old_history,
        'HISTORICAL_PROGRESS_CHANGED')
    require(h.stable_three(observations) and all(row['claim_present'] for row in observations[-1]['tasks']),
            'THREE_WORKERS_OR_ADMISSION_UNVERIFIED')
    receipt.update(state='THREE_WORKERS_VERIFIED_TWO_MODEL_RETRIES_ADMITTED', observations=observations,
                   finished_at=time.time())
    h.atomic(root / 'state/dispatcher' / ('model_slot_recovery_install_' + request + '.json'), encoded(receipt))
    print('NOX_MAINT_MODEL_SLOT_RECOVERY_INSTALL=' + encoded(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
