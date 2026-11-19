#!/usr/bin/env python3
"""Install the productive relay into the sole existing owner dispatcher.

The reviewed bundle can change only six orchestration modules, their binding,
and content-addressed mission metadata. Source workspace, tests, model process,
checkpoints, S03 and existing task outcomes remain owned by the existing path.
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
PACKAGE = 'state/dispatcher/project_executor/package/'
SCHEMA = 'NOX_SYSTEMIC_RELAY_INSTALL_SPEC_V1'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
RUNTIME = frozenset(('owner_subagent_dispatcher.py', 'owner_subagent_processes.py',
    'owner_project_native.py', 'owner_project_planner.py',
    'owner_subagent_instruction_truth.py', 'owner_systemic_refill.py'))
SPEC = {}  # The packager embeds the exact reviewed installation specification.
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_SYSTEMIC_RELAY_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def load_module(name, raw):
    module = types.ModuleType(name)
    module.__file__ = '<reviewed-systemic-relay>/' + name + '.py'
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def decode(bundle, spec):
    require(spec.get('schema') == SCHEMA, 'SPEC_SCHEMA')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and 8 <= len(pins) <= 64
            and set(bundle) == set(pins), 'ASSET_SET')
    assets, total = {}, 0
    for name, pin in pins.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name)
                and re.fullmatch(r'[a-f0-9]{64}', str(pin))
                and isinstance(bundle[name], str) and len(bundle[name]) <= 2800000,
                'ASSET_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        total += len(raw)
        require(len(raw) <= 2 * 1024 * 1024 and total <= 12 * 1024 * 1024
                and digest(raw) == pin, 'ASSET_HASH')
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        assets[name] = raw
    helper = spec.get('helper_asset')
    require(helper in assets and digest(assets[helper]) == HELPER_SHA, 'HELPER_PIN')
    runtime_paths, package_paths = spec.get('runtime_paths'), spec.get('package_paths')
    require(isinstance(runtime_paths, dict) and isinstance(package_paths, dict)
            and set(runtime_paths.values()) == {'scripts/' + name for name in RUNTIME}
            and len(runtime_paths) == len(RUNTIME)
            and set(pins) == set(runtime_paths) | set(package_paths) | {helper}
            and not set(runtime_paths).intersection(package_paths), 'PAYLOAD_SCOPE')
    runtime = {path: assets[name] for name, path in runtime_paths.items()}
    package = {}
    for name, path in package_paths.items():
        match = re.fullmatch(PACKAGE + r'(contracts|relay)/([a-f0-9]{64})\.json', path)
        require(match and match[2] == digest(assets[name]), 'PACKAGE_PATH')
        doc = json.loads(assets[name])
        require(encoded(doc) == assets[name], 'CANONICAL_PACKAGE')
        package[path] = assets[name]
    return assets, runtime, package, load_module('_nox_relay_transaction', assets[helper])


def compose(old, runtime, spec):
    require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and old.get('instance_id') == 60509551 and old.get('owner_authorized') is True
            and old.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and old.get('mode') == 'NORMAL' and old.get('target') == 3
            and old.get('global_worker_cap') == 3, 'CONFIG_SCOPE')
    require('systemic_relay' not in old, 'ALREADY_INSTALLED')
    previous = old['module_pins']['owner_subagent_dispatcher.py']
    callback = digest(runtime['scripts/owner_subagent_dispatcher.py'])
    require(previous != callback, 'CALLBACK_UNCHANGED')
    new = copy.deepcopy(old)
    for name in RUNTIME:
        require(name in old['module_pins'] or name == 'owner_systemic_refill.py', 'MODULE_SCOPE')
        new['module_pins'][name] = digest(runtime['scripts/' + name])
    new['project_executor']['model']['source_pins']['owner_project_planner.py'] = new['module_pins']['owner_project_planner.py']
    for key in ('historical_project_source_sha256', 'historical_leaf_source_sha256'):
        pins = old.get(key, [])
        require(isinstance(pins, list) and len(pins) < 16
                and all(re.fullmatch(r'[a-f0-9]{64}', str(x)) for x in pins), 'HISTORY_PINS')
        new[key] = sorted(set(pins) | {previous})
    manifest_sha = spec.get('manifest_sha256')
    require(isinstance(manifest_sha, str) and re.fullmatch(r'[a-f0-9]{64}', manifest_sha), 'MANIFEST_PIN')
    new['systemic_relay'] = {'path': str(ROOT / (PACKAGE + 'relay/' + manifest_sha + '.json')),
                             'sha256': manifest_sha}
    undo = copy.deepcopy(new)
    undo['module_pins'] = old['module_pins']
    undo['project_executor']['model']['source_pins'] = old['project_executor']['model']['source_pins']
    undo.pop('systemic_relay')
    for key in ('historical_project_source_sha256', 'historical_leaf_source_sha256'):
        if key in old:
            undo[key] = old[key]
        else:
            undo.pop(key, None)
    require(undo == old, 'UNRELATED_CONFIG_CHANGE')
    require(callback.encode() in runtime['scripts/owner_subagent_instruction_truth.py'], 'TRUTH_CALLBACK_PIN')
    return new


def apply_tracked(root, changes, before, helper, applied):
    # Config is the final activation step; all previous writes are reversible.
    for path in sorted(changes, key=lambda path: path == CONFIG):
        try:
            current = helper.read_regular(root / path)
        except FileNotFoundError:
            current = None
        require(current == before[path], 'WRITE_PREIMAGE_CHANGED')
        if current == changes[path]:
            continue
        applied.append(path)
        helper.atomic(root / path, changes[path], 0o644 if path.startswith('scripts/') else 0o600)
        require(helper.read_regular(root / path) == changes[path], 'WRITE_READBACK')


def rollback_owned(root, changes, before, helper, applied):
    restored = []
    for path in reversed(applied):
        try:
            current = helper.read_regular(root / path)
        except FileNotFoundError:
            current = None
        # A write may fail before replace, or after replace but before readback.
        # Both states are owned; any third value belongs to another writer.
        if current == before[path]:
            continue
        require(current == changes[path], 'ROLLBACK_OWNERSHIP_CHANGED')
        if before[path] is None:
            (root / path).unlink()
        else:
            helper.atomic(root / path, before[path], 0o644 if path.startswith('scripts/') else 0o600)
        restored.append(path)
    return {'restored': restored, 'source_workspace_changed': False}


def verify_registry(manifest, helper):
    names = {'tasks':'project_work_tasks.json', 'ideas':'project_work_ideas.json',
             'receipts':'project_work_receipts_source.json', 'routing':'project_routing_4q.json'}
    docs = {}
    for key, name in names.items():
        raw = helper.read_regular(ROOT / 'state/dispatcher' / name, 16 * 1024 * 1024)
        require(hashlib.sha256(raw).hexdigest() == manifest['registry']['source_registry_sha256'][key], 'REGISTRY_NATIVE_PIN')
        docs[key] = json.loads(raw)
    specs = [*docs['tasks']['tasks'], *docs['ideas']['ideas']]
    by_id = {row['id']: row for row in specs}
    routing = {row['task_id']: row['queue_id'] for row in docs['routing']['tasks']}
    require(len(specs) == len(by_id) == len(routing) == 295 and set(by_id) == set(routing), 'REGISTRY_NATIVE_DENOMINATOR')
    for task_id, parent in manifest['registry']['parents'].items():
        spec = by_id.get(task_id)
        require(spec is not None and hashlib.sha256(encoded(spec)).hexdigest() == parent['spec_sha256']
                and routing[task_id] == parent['queue_id'] and spec.get('evidence') == parent['required_evidence'], 'REGISTRY_NATIVE_PARENT')


def mission_contracts(manifest, refill):
    contracts, ids = {}, []
    for mission in manifest['missions']:
        task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + refill._input(mission)[:16]
        raw = encoded(refill._contract(mission, task_id))
        pin = hashlib.sha256(raw).hexdigest()
        require(pin not in contracts and task_id not in ids, 'MANIFEST_DERIVED_DUPLICATE')
        contracts[pin] = raw
        ids.append(task_id)
    return contracts, ids


def run(bundle, spec, root=ROOT):
    request, source_sha = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source_sha), 'OWNER_CONTEXT')
    require(Path(root) == ROOT, 'INSTANCE_ROOT')
    assets, runtime, package, h = decode(bundle, spec)
    expected = spec['expected_native']
    before = h.preimages(root, expected)
    old = json.loads(before[CONFIG])
    require(all(expected.get('scripts/' + name) == pin for name, pin in old['module_pins'].items()), 'ALL_MODULE_PINS')
    new = compose(old, runtime, spec)
    manifest_path = PACKAGE + 'relay/' + spec['manifest_sha256'] + '.json'
    require(manifest_path in package, 'MANIFEST_ASSET')
    manifest = json.loads(package[manifest_path])
    refill = load_module('_nox_refill_review', runtime['scripts/owner_systemic_refill.py'])
    refill.validate_manifest(manifest)
    planner = load_module('_nox_planner_review', runtime['scripts/owner_project_planner.py'])
    expected_contracts, expected_task_ids = mission_contracts(manifest, refill)
    bundled = {Path(path).stem: raw for path, raw in package.items() if '/contracts/' in path}
    require(bundled == expected_contracts and sorted(spec.get('batch_task_ids', [])) == sorted(expected_task_ids), 'MANIFEST_CONTRACT_SET')
    require(manifest.get('previous_manifest_sha256') is None, 'INITIAL_MANIFEST_PREDECESSOR')
    contracts = {pin: json.loads(raw) for pin, raw in expected_contracts.items()}
    require(1 <= len(contracts) <= 30, 'CONTRACT_COUNT')
    marker_raw = h.read_regular(root / MARKER, 65536)
    require(digest(marker_raw) == spec['expected_bootstrap_sha256'], 'BOOTSTRAP_PREIMAGE')
    changes = {**runtime, **package, CONFIG: encoded(new)}
    for path in changes:
        if path in before:
            continue
        try:
            existing = h.read_regular(root / path)
        except FileNotFoundError:
            existing = None
        if path.startswith('scripts/'):
            require(existing is None, 'NEW_RUNTIME_PATH_EXISTS')
        else:
            require(existing is None or existing == changes[path], 'PACKAGE_COLLISION')
        before[path] = existing
    lock = root / 'state/owner_maintenance.lock'
    require(not lock.is_symlink(), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    protected = h.protected_snapshot(spec)
    applied, owned = [], []
    stopped = False
    baseline = snapshot = final_state = final_processes = None
    receipt = {'schema': 'NOX_SYSTEMIC_RELAY_INSTALL_RECEIPT_V1', 'request': request,
        'source_sha': source_sha, 'started_at': time.time(), 'state': 'PREFLIGHT',
        'model_restarted': False, 'training_started': False, 'original_tasks_accepted': 0,
        'source_workspace_writes': 0, 'trusted_test_writes': 0,
        'manifest_sha256': spec['manifest_sha256'], 'batch_task_ids': spec['batch_task_ids']}

    def guard():
        info, named = os.fstat(fd), lock.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and not info.st_mode & 0o022 and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'LEASE_CHANGED')
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
                    and event.get('task_id') == tid and event.get('original_task_accepted') is False, 'HISTORICAL_RECEIPT')
            result[tid] = h.exact_s03(root, event)
        return result

    def drain():
        deadline = time.monotonic() + 40
        while True:
            guard()
            state, active = h.queue_idle(root)
            processes = h.self_fd_children(spec)
            require(not set(receipt['batch_task_ids']).intersection(state['tasks']), 'BATCH_ALREADY_ADMITTED')
            if not active and not processes['unexpected_children']:
                return state, processes
            require(time.monotonic() < deadline, 'ACTIVE_WORK_DRAIN_TIMEOUT')
            time.sleep(.5)

    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Hold('HOLD_SYSTEMIC_RELAY_MAINTENANCE_BUSY') from exc
        guard()
        h.preimages(root, expected)
        baseline, processes = drain()
        old_history = history(baseline)
        verify_registry(manifest, h)
        snapshot = h.source_snapshot(root, old)
        require(snapshot['files_sha256'] == spec['expected_source_files_sha256'], 'SOURCE_PREIMAGE')
        allowed = set(old['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'])
        for contract in contracts.values():
            require(contract['root_id'] == 'NOX_PROJECT_SOURCE'
                    and set(row['path'] for row in contract['context']).issubset(allowed)
                    and not contract.get('allowed_new_paths')
                    and contract.get('original_task_accepted') is False
                    and contract.get('acceptance_scope') == 'SOURCE_PATCH_TESTED', 'CONTRACT_SCOPE')
            context = {row['path']: h.read_regular(root / SOURCE / h.relpath(row['path'])) for row in contract['context']}
            planner.validate_contract(contract, context)
        source_pins = {'NOX_PROJECT_SOURCE': {path: fact['sha256'] for path, fact in snapshot['files'].items()}}
        proposed = refill.select_next(manifest, baseline['tasks'], source_pins,
            {'slots_available': 3, 'callback_sha256': new['module_pins']['owner_subagent_dispatcher.py'],
             'manifest_sha256': spec['manifest_sha256'], 'now': time.time()})
        require(sorted(row['id'] for row in proposed['rows']) == sorted(expected_task_ids), 'INITIAL_MISSIONS_NOT_READY')
        budget_module, budget_stage = h.load_budget_module(root,
            {'scripts/owner_autonomy_pool.py': before['scripts/owner_autonomy_pool.py']}, expected, request)
        receipt['budget'] = h.budget_preflight(new, budget_module, budget_stage, 'systemic_before_stop')
        backup = root / 'state/dispatcher/systemic_relay_rollback' / request
        require(not backup.exists() and not backup.is_symlink(), 'BACKUP_EXISTS')
        backup.mkdir(parents=True, mode=0o700)
        for path in changes:
            if before[path] is not None:
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
                and history(final_state) == old_history and h.source_snapshot(root, old) == snapshot, 'STOPPED_PREIMAGE_CHANGED')
        apply_tracked(root, changes, before, h, applied)
        guard()
        require(h.source_snapshot(root, new) == snapshot
                and h.read_regular(root / MARKER, 65536) == marker_raw, 'SOURCE_OR_BOOTSTRAP_CHANGED')
        receipt['budget_before_start'] = h.budget_preflight(new, budget_module, budget_stage, 'systemic_before_start')
        receipt['new_director'] = h.start_update_checked(root, owned)
        guard()
        require(h.source_snapshot(root, new) == snapshot, 'SOURCE_CHANGED_BEFORE_ADMISSION')
        receipt.update(state='INSTALLED_REFILL_PENDING', config_sha256=digest(changes[CONFIG]),
            runtime_pins={path: digest(raw) for path, raw in runtime.items()},
            preserved_project_receipts=len(old_history), old_catalog_rows_preserved=len(old['catalog']['tasks']))
    except BaseException as exc:
        receipt['state'] = str(exc) if isinstance(exc, (Hold, h.Hold)) else 'HOLD_SYSTEMIC_RELAY_' + type(exc).__name__
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
                require(final_processes is not None, 'RESTORE_CHILD_CENSUS_MISSING')
                h.wait_previous_descendants_stopped(final_processes['children'])
                h.preimages(root, expected)
                require(h.source_snapshot(root, old) == snapshot, 'RESTORE_SOURCE_PREIMAGE')
                receipt['restored_director'] = h.start_checked(root)
        except Exception as failure:
            receipt['recovery'] = str(failure) if isinstance(failure, (Hold, h.Hold)) else type(failure).__name__
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        h.atomic(root / 'state/dispatcher' / ('systemic_relay_install_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_SYSTEMIC_RELAY_INSTALL=' + encoded(receipt).decode(), flush=True)
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
        'tasks': {tid: state['tasks'][tid] for tid in baseline['tasks']}}) == old_history, 'HISTORICAL_PROGRESS_CHANGED')
    require(h.stable_three(observations) and any(row['claim_present'] for row in observations[-1]['tasks']), 'THREE_WORKERS_OR_REFILL_UNVERIFIED')
    receipt.update(state='THREE_WORKERS_VERIFIED_REFILL_ADMITTED', observations=observations, finished_at=time.time())
    h.atomic(root / 'state/dispatcher' / ('systemic_relay_install_' + request + '.json'), encoded(receipt))
    print('NOX_MAINT_SYSTEMIC_RELAY_INSTALL=' + encoded(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
