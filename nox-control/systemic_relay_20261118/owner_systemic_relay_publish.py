#!/usr/bin/env python3
"""Publish one reviewed successor mission pack without restarting the workers.

An automation may build this entry with an exact current predecessor. It only
stages content-addressed metadata and CAS-updates the existing relay pointer.
The running dispatcher owns all claims, execution, S03 and source integration.
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
import time
import types

ROOT = Path('/root/nox')
CONFIG = ROOT / 'config/owner_native_subagents.json'
PACKAGE = ROOT / 'state/dispatcher/project_executor/package'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
OWNER_SNAPSHOT_SCHEMA = 'NOX_SYSTEMIC_OWNER_PUBLISH_SNAPSHOT_V1'
NATIVE_RECEIPT_CONTRACT_SCHEMA = 'NOX_OWNER_REVIEWED_NATIVE_RECEIPT_CONTRACT_V1'
OWNER_SNAPSHOT_MAX_AGE_SEC = 600
GIB = 1024 ** 3
PUBLISH_COMPLETE_MARKER = 'NOX_MAINT_REFLEX_PUBLISH_COMPLETE=true'
HOLD_PREFIX = 'HOLD_SYSTEMIC_PUBLISH_'
HOLD_CODES = frozenset('''
ACCEPTANCE_MAPPING ACCEPTANCE_VERIFIER_ANCHOR ACCEPTANCE_VERIFIER_BINDING
ANCESTOR_PIN ASSETS ASSET_BOUND ASSET_PIN BACKUP_CONTENT_CHANGED BACKUP_EXISTS
BACKUP_READBACK CONFIG_PREDECESSOR CONFIG_READBACK CONTENT_ADDRESS_COLLISION CONTRACT_SCOPE
EXACTLY_ONE_SUCCESSOR_REQUIRED
FINAL_CAS_CHANGED HELPER_PIN LEASE_IDENTITY LEASE_PATH MAINTENANCE_BUSY
MANIFEST_CHAIN_BOUND MANIFEST_CONTRACT_SET MANIFEST_DERIVED_DUPLICATE MANIFEST_LINEAGE
MANIFEST_MISSING MANIFEST_PREDECESSOR MANIFEST_SHA MODULE_NAME NATIVE_RECEIPT_CONTRACT
NEXT_MISSIONS_NOT_READY ORIGINAL_PARENT_ALREADY_PRESENT ORIGINAL_QUEUE_STATE_CHANGED
OWNER_CONTEXT OWNER_SCOPE OWNER_SNAPSHOT_ACTIVE_CLAIMS OWNER_SNAPSHOT_BINDING
OWNER_SNAPSHOT_CONFIG_CHANGED OWNER_SNAPSHOT_PIN OWNER_SNAPSHOT_PROCESS_BINDING
OWNER_SNAPSHOT_SHAPE OWNER_SNAPSHOT_SOURCE_CHANGED OWNER_SNAPSHOT_STALE_OR_IDENTITY
OWNER_STOP PACKAGE_PATH PACKAGE_READBACK PACKAGE_SET PROCESS_IDENTITY_CHANGED
PRODUCER_EVIDENCE QUEUE_CHANGED QUEUE_STATE_SHAPE REFILL_REQUEST_BINDING_MISSING
REFILL_REQUEST_ID REFILL_REQUEST_OUTCOME REFILL_REQUEST_OUTCOME_STATE_MISMATCH
REFILL_REQUEST_STATE_DUPLICATE REFILL_REQUEST_STATE_PIN REGISTRY_NATIVE_ACCEPTANCE
REGISTRY_NATIVE_DENOMINATOR REGISTRY_NATIVE_PARENT REGISTRY_NATIVE_PIN
REGISTRY_NATIVE_UNREGISTERED_ACCEPTANCE RESOURCE_HEADROOM_BELOW_MINIMUM
RESOURCE_SNAPSHOT_FIELDS_OR_STALE RESOURCE_SNAPSHOT_SCHEMA RUNTIME_PIN SOURCE_PREIMAGE
SOURCE_ROOT SPEC_SCHEMA UNREGISTERED_ACCEPTANCE_MAPPING WAIT_ACTIVE_CLAIMS_SETTLE
'''.split()) | {'RECEIPT_WRITE', 'INTERNAL'}
HOLD_RECEIPT_STATES = frozenset(HOLD_PREFIX + code for code in HOLD_CODES)
SUCCESS_RECEIPT_STATES = frozenset({
    'PREFLIGHT', 'PUBLISHED_ONE_OWNER_REVIEWED_SUCCESSOR_PENDING_NATIVE_ADMISSION'})
SPEC = {}
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_SYSTEMIC_PUBLISH_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate_owner_snapshot(snapshot, now=None):
    require(isinstance(snapshot,dict) and set(snapshot) == {
        'schema','owner_id','observed_at','config_sha256','previous_manifest_sha256',
        'registry_sha256','source_files_sha256','refill_request_id',
        'original_task_states_sha256','process_identity_sha256',
        'native_readback_sha256','active_claim_count'}, 'OWNER_SNAPSHOT_SHAPE')
    current = time.time() if now is None else now
    observed = snapshot.get('observed_at')
    require(snapshot.get('schema') == OWNER_SNAPSHOT_SCHEMA
            and snapshot.get('owner_id') == 60509551
            and type(observed) in (int,float) and 0 <= observed <= 10**12
            and type(current) in (int,float) and -30 <= current-observed <= OWNER_SNAPSHOT_MAX_AGE_SEC,
            'OWNER_SNAPSHOT_STALE_OR_IDENTITY')
    for key in ('config_sha256','previous_manifest_sha256','registry_sha256',
                'source_files_sha256','refill_request_id','original_task_states_sha256',
                'process_identity_sha256','native_readback_sha256'):
        require(type(snapshot.get(key)) is str and re.fullmatch(r'[a-f0-9]{64}',snapshot[key]),
                'OWNER_SNAPSHOT_PIN')
    require(type(snapshot.get('active_claim_count')) is int
            and snapshot['active_claim_count'] == 0,'OWNER_SNAPSHOT_ACTIVE_CLAIMS')
    return snapshot


def require_budget_headroom(snapshot, now=None, max_age_sec=5):
    """Require a live cgroup-v2 sample with at least two GiB free."""
    require(isinstance(snapshot,dict) and snapshot.get('schema') == 'NOX_BOUNDED_CPU_BUDGET_V1'
            and snapshot.get('source') == 'cgroup_v2'
            and snapshot.get('instance_id') == 60509551,
            'RESOURCE_SNAPSHOT_SCHEMA')
    current, maximum, minimum = (snapshot.get('current_bytes'),snapshot.get('max_bytes'),
                                 snapshot.get('minimum_headroom_bytes'))
    observed = snapshot.get('observed_at')
    clock = time.time() if now is None else now
    require(type(current) is int and type(maximum) is int and type(minimum) is int
            and 0 <= current < maximum <= 2**63-1 and minimum == 2*GIB
            and type(observed) in (int,float) and 0 <= observed <= 10**12
            and type(clock) in (int,float) and type(max_age_sec) is int
            and 1 <= max_age_sec <= 30 and -5 <= clock-observed <= max_age_sec,
            'RESOURCE_SNAPSHOT_FIELDS_OR_STALE')
    headroom = maximum-current
    require(headroom >= minimum,'RESOURCE_HEADROOM_BELOW_MINIMUM')
    return {'schema':'NOX_SYSTEMIC_PUBLISH_RESOURCE_GATE_V1','state':'PASS',
            'headroom_bytes':headroom,'minimum_headroom_bytes':minimum,
            'observed_at':observed}


def safe_receipt_state(value):
    if type(value) is not str:
        return HOLD_PREFIX + 'INTERNAL'
    if value in SUCCESS_RECEIPT_STATES or value in HOLD_RECEIPT_STATES:
        return value
    return HOLD_PREFIX + 'INTERNAL'


def hold_state_from_exception(exc):
    value = str(exc)
    if value in HOLD_RECEIPT_STATES:
        return value
    if value.startswith(HOLD_PREFIX) and value[len(HOLD_PREFIX):] in HOLD_CODES:
        return value
    return HOLD_PREFIX + 'INTERNAL'


def persist_receipt(helper, request, receipt):
    receipt['state'] = safe_receipt_state(receipt.get('state'))
    receipt['finished_at'] = time.time()
    receipt['receipt_persisted'] = True
    try:
        helper.atomic(ROOT / 'state/dispatcher' / ('systemic_relay_publish_' + request + '.json'),
                      encoded(receipt))
    except BaseException:
        receipt['receipt_persisted'] = False
        if receipt.get('state') not in HOLD_RECEIPT_STATES:
            receipt['state'] = HOLD_PREFIX + 'RECEIPT_WRITE'
    print('NOX_MAINT_SYSTEMIC_RELAY_PUBLISH=' + encoded(receipt).decode(), flush=True)
    return receipt['receipt_persisted']


def emit_publish_complete_marker():
    print(PUBLISH_COMPLETE_MARKER, flush=True)


def owner_lock_path_matches(fd, lock, state_dir_fd):
    try:
        parent_opened = os.fstat(state_dir_fd)
        parent_named = lock.parent.lstat()
        opened = os.fstat(fd)
        named = os.stat(lock.name, dir_fd=state_dir_fd, follow_symlinks=False)
    except OSError:
        return False
    return (stat.S_ISDIR(parent_opened.st_mode) and parent_opened.st_uid == os.geteuid()
            and not parent_opened.st_mode & 0o022
            and (parent_opened.st_dev, parent_opened.st_ino) ==
                (parent_named.st_dev, parent_named.st_ino)
            and stat.S_ISREG(opened.st_mode) and opened.st_uid == os.geteuid()
            and opened.st_nlink == 1 and not opened.st_mode & 0o022
            and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino))


def verify_owner_lock_identity(fd, lock, state_dir_fd):
    require(lock.parent == ROOT / 'state' and owner_lock_path_matches(
        fd, lock, state_dir_fd), 'LEASE_IDENTITY')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        require(False, 'LEASE_IDENTITY')


def verify_publish_cas_preconditions(helper, config, owner_snapshot, fd, lock, state_dir_fd):
    budget = require_budget_headroom(helper.read_budget_snapshot(config), max_age_sec=5)
    validate_owner_snapshot(owner_snapshot)
    verify_owner_lock_identity(fd, lock, state_dir_fd)
    return budget


def secure_dirfd_matches(fd, path):
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        return False
    try:
        opened = os.fstat(fd)
        named = path.lstat()
    except OSError:
        return False
    return (stat.S_ISDIR(opened.st_mode) and opened.st_uid == os.geteuid()
            and not opened.st_mode & 0o022
            and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino))


def read_regular_at(directory_fd, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                 dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                'CONFIG_READBACK')
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        raw = b''.join(chunks)
        require(len(raw) <= maximum and (before.st_dev, before.st_ino,
                before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino,
                after.st_size, after.st_mtime_ns), 'CONFIG_READBACK')
        return raw
    finally:
        os.close(fd)


def atomic_owner_config(helper, raw, expected_raw, owner_snapshot, lock_fd,
                        lock, state_dir_fd, before_final_gate=None):
    """CAS the config through pinned dirfds while holding the maintenance lease.

    Both parents must be euid-owned and non-writable by group/others. All known
    config writers take this same flock; the protected state directory prevents
    an unprivileged actor from pruning/replacing its lock pathname. The final
    lease identity check is deliberately adjacent to the anchored rename.
    """
    config_dir_fd = os.open(CONFIG.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temp_name = None
    try:
        require(secure_dirfd_matches(config_dir_fd, CONFIG.parent)
                and secure_dirfd_matches(state_dir_fd, lock.parent), 'LEASE_PATH')
        require(read_regular_at(config_dir_fd, CONFIG.name, 2 * 1024 * 1024)
                == expected_raw, 'CONFIG_PREDECESSOR')
        for attempt in range(3):
            candidate = '.nox-systemic-publish-' + str(os.getpid()) + '-' + str(time.time_ns()) + '-' + str(attempt)
            try:
                temp_fd = os.open(candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=config_dir_fd)
                temp_name = candidate
                break
            except FileExistsError:
                continue
        require(temp_name is not None, 'CONFIG_READBACK')
        try:
            view = memoryview(raw)
            while view:
                written = os.write(temp_fd, view)
                require(written > 0, 'CONFIG_READBACK')
                view = view[written:]
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        if before_final_gate is not None:
            before_final_gate()
        require(secure_dirfd_matches(config_dir_fd, CONFIG.parent)
                and secure_dirfd_matches(state_dir_fd, lock.parent), 'LEASE_PATH')
        budget = require_budget_headroom(
            helper.read_budget_snapshot(json.loads(expected_raw)), max_age_sec=5)
        validate_owner_snapshot(owner_snapshot)
        require(read_regular_at(config_dir_fd, CONFIG.name, 2 * 1024 * 1024)
                == expected_raw, 'CONFIG_PREDECESSOR')
        verify_owner_lock_identity(lock_fd, lock, state_dir_fd)
        os.replace(temp_name, CONFIG.name,
                   src_dir_fd=config_dir_fd, dst_dir_fd=config_dir_fd)
        temp_name = None
        os.fsync(config_dir_fd)
        require(read_regular_at(config_dir_fd, CONFIG.name, 2 * 1024 * 1024)
                == raw, 'CONFIG_READBACK')
        return budget
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=config_dir_fd)
            except FileNotFoundError:
                pass
        os.close(config_dir_fd)


def write_package_with_budget_gate(helper, path, raw, config, owner_snapshot,
                                   owner_snapshot_sha256, lock_fd, lock,
                                   state_dir_fd):
    budget = require_budget_headroom(helper.read_budget_snapshot(config), max_age_sec=5)
    validate_owner_snapshot(owner_snapshot)
    require(sha(encoded(owner_snapshot)) == owner_snapshot_sha256,
            'OWNER_SNAPSHOT_BINDING')
    verify_owner_lock_identity(lock_fd, lock, state_dir_fd)
    helper.atomic(path, raw)
    return budget


def ensure_exact_backup(helper, backup, old_raw, config, owner_snapshot,
                        fd, lock, state_dir_fd):
    config_path = backup / 'config.json'
    require(not backup.is_symlink(), 'BACKUP_EXISTS')
    if backup.exists():
        require(backup.is_dir(), 'BACKUP_EXISTS')
        require({path.name for path in backup.iterdir()} == {'config.json'},
                'BACKUP_CONTENT_CHANGED')
        existing = helper.read_regular(config_path, 2 * 1024 * 1024)
        require(existing == old_raw, 'BACKUP_CONTENT_CHANGED')
        return {'state':'REUSED_EXACT', 'resource_gate':None}
    resource = require_budget_headroom(helper.read_budget_snapshot(config), max_age_sec=5)
    validate_owner_snapshot(owner_snapshot)
    verify_owner_lock_identity(fd, lock, state_dir_fd)
    helper.atomic(config_path, old_raw)
    require(helper.read_regular(config_path, 2 * 1024 * 1024) == old_raw,
            'BACKUP_READBACK')
    return {'state':'WRITTEN', 'resource_gate':resource}


def native_receipt_contract(mission, *, manifest_revision, previous_sha,
                             registry_sha, review_sha, refill):
    context = {row['path']:row['sha256'] for row in mission['context']}
    source_pins = [{'path':path,'sha256':context[path]}
                   for path in sorted(mission['editable_paths'])]
    test_pins = [{'module':module,'path':module.replace('.','/')+'.py',
                  'sha256':context[module.replace('.','/')+'.py']}
                 for module in sorted(mission['verification']['modules'])]
    input_sha = refill._input(mission)
    task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + input_sha[:16]
    acceptance = mission['registered_acceptance']
    return {'schema':NATIVE_RECEIPT_CONTRACT_SCHEMA,
        'manifest_revision':manifest_revision,'previous_manifest_sha256':previous_sha,
        'owner_review_sha256':review_sha,'registry_sha256':registry_sha,
        'original_task_id':mission['parent_task_id'],'successor_task_id':task_id,
        'original_task_spec_sha256':mission['parent_spec_sha256'],
        'registered_acceptance_sha256':sha(acceptance.encode('utf-8')),
        'source_pins':source_pins,'source_sha256':sha(encoded(source_pins)),
        'test_pins':test_pins,'test_sha256':sha(encoded(test_pins)),
        'required_receipt':{'schema':'NOX_NATIVE_SUBAGENT_RECEIPT_V1',
            'verified':True,'scope':'SOURCE_PATCH_TESTED',
            'receipt':{'schema':'NOX_NATIVE_SUBAGENT_RECEIPT_V1',
                'phase':'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED',
                'original_task_accepted':False,
                'worker_result.project_evidence.state':'INTEGRATED',
                'worker_result.project_evidence.integration_verified':True,
                'worker_result.project_evidence.tests.passed':True},
            's03':{'native_verified':True,'receipt_sha256_matches_receipt':True},
            'original_task_accepted':False},
        'acceptance_recorded':False}


def require_exactly_one_successor(manifest):
    missions = manifest.get('missions') if isinstance(manifest,dict) else None
    require(isinstance(missions,list) and len(missions) == 1,
            'EXACTLY_ONE_SUCCESSOR_REQUIRED')
    return missions[0]


def wait_settled_queue(helper, guard, expected, receipt):
    """Wait for the existing all-running guard without changing queue state."""
    deadline = time.monotonic() + 8
    while True:
        require(guard() == expected, 'PROCESS_IDENTITY_CHANGED')
        state, active = helper.queue_idle(ROOT)
        receipt['busy_count'] = len(active)
        receipt['busy_tasks'] = []
        for task_id in sorted(active)[:12]:
            row = state['tasks'][task_id]
            lease = row.get('native_worker_lease') or {}
            receipt['busy_tasks'].append({
                'id': str(task_id)[:128],
                'status': row.get('status')[:64] if isinstance(row.get('status'), str) else None,
                'handler': row.get('handler')[:128] if isinstance(row.get('handler'), str) else None,
                'lease_phase': lease.get('phase')[:64] if isinstance(lease.get('phase'), str) else None,
            })
        if not active:
            return state
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'WAIT_ACTIVE_CLAIMS_SETTLE')
        time.sleep(min(.05, remaining))


def module(name, raw):
    result = types.ModuleType(name)
    result.__file__ = '<reviewed-publisher>/' + name + '.py'
    exec(compile(raw, result.__file__, 'exec'), result.__dict__)
    return result


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
        if 'acceptance' in spec:
            acceptance = spec.get('acceptance')
            require(type(acceptance) is str and parent.get('registered_acceptance') == acceptance
                    and parent.get('registered_acceptance_sha256') == sha(acceptance.encode('utf-8')),
                    'REGISTRY_NATIVE_ACCEPTANCE')
        else:
            require('registered_acceptance' not in parent
                    and 'registered_acceptance_sha256' not in parent,
                    'REGISTRY_NATIVE_UNREGISTERED_ACCEPTANCE')


def verify_acceptance_anchors(contract, source_files):
    """Confirm each reviewed criterion anchor exists in its pinned test module."""
    acceptance = contract.get('registered_acceptance')
    mapping = contract.get('acceptance_mapping')
    if acceptance is None:
        require(mapping is None, 'UNREGISTERED_ACCEPTANCE_MAPPING')
        return True
    require(type(acceptance) is str and isinstance(mapping, dict)
            and isinstance(mapping.get('criteria'), list), 'ACCEPTANCE_MAPPING')
    for criterion in mapping['criteria']:
        module_name = criterion.get('verifier_module') if isinstance(criterion, dict) else None
        anchor = criterion.get('verifier_anchor') if isinstance(criterion, dict) else None
        require(type(module_name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*',module_name)
                and type(anchor) is str and anchor, 'ACCEPTANCE_VERIFIER_BINDING')
        verifier_path = module_name.replace('.','/') + '.py'
        raw = source_files.get(verifier_path)
        require(isinstance(raw, bytes) and anchor.encode('utf-8') in raw,
                'ACCEPTANCE_VERIFIER_ANCHOR')
    return True


def verify_refill_request_state(manifest, queue_state, refill):
    """Bind the reviewed refill request to a fresh native original-ID snapshot."""
    evidence = manifest.get('producer_evidence', {})
    binding = evidence.get('refill_request_binding') if isinstance(evidence, dict) else None
    require(isinstance(binding, dict), 'REFILL_REQUEST_BINDING_MISSING')
    states = binding.get('original_task_states')
    require(isinstance(states, list) and len(states) <= 8192
            and binding.get('original_task_states_sha256') == refill.digest(states)
            and evidence.get('refill_request_sha256') is not None
            and re.fullmatch(r'[a-f0-9]{64}', str(evidence['refill_request_sha256'])),
            'REFILL_REQUEST_STATE_PIN')
    expected_id = refill.digest({'manifest_sha256':manifest.get('previous_manifest_sha256'),
        'source_pins':binding.get('source_pins'),'outcomes':binding.get('outcomes'),
        'original_task_states':states})
    require(binding.get('request_id') == expected_id
            and evidence.get('refill_request_id') == expected_id,
            'REFILL_REQUEST_ID')
    expected = {row['task_id']:row['status'] for row in states}
    require(len(expected) == len(states), 'REFILL_REQUEST_STATE_DUPLICATE')
    parents = manifest['registry']['parents']
    for outcome in binding.get('outcomes',[]):
        require(isinstance(outcome,dict) and type(outcome.get('task_id')) is str
                and type(outcome.get('status')) is str, 'REFILL_REQUEST_OUTCOME')
        task_id = outcome['task_id']
        if task_id.split('.',1)[0] in parents:
            require(task_id not in expected or expected[task_id] == outcome['status'],
                    'REFILL_REQUEST_OUTCOME_STATE_MISMATCH')
            expected[task_id] = outcome['status']
    live_tasks = queue_state.get('tasks') if isinstance(queue_state, dict) else None
    require(isinstance(live_tasks, dict), 'QUEUE_STATE_SHAPE')
    current = []
    for task_id in sorted(live_tasks):
        if type(task_id) is not str or task_id.split('.',1)[0] not in parents:
            continue
        row = live_tasks[task_id]
        status = row.get('status') if isinstance(row, dict) else None
        current.append({'task_id':task_id,
            'status':status if status in refill.ACTIVE|refill.TERMINAL else 'unknown'})
    require(current == states, 'ORIGINAL_QUEUE_STATE_CHANGED')
    require(all(not any(task_id.split('.',1)[0] == mission['parent_task_id']
                        for task_id in expected)
                and not any(type(task_id) is str and
                            task_id.split('.',1)[0] == mission['parent_task_id']
                            for task_id in live_tasks)
                for mission in manifest['missions']), 'ORIGINAL_PARENT_ALREADY_PRESENT')
    return True


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


def run(bundle, spec):
    request, commit = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', commit), 'OWNER_CONTEXT')
    require(spec.get('schema') == 'NOX_SYSTEMIC_RELAY_PUBLISH_SPEC_V1', 'SPEC_SCHEMA')
    pins = spec.get('assets')
    require(isinstance(pins, dict) and set(bundle) == set(pins) and 2 <= len(pins) <= 64, 'ASSETS')
    assets, total = {}, 0
    for name, pin in pins.items():
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name)
                and re.fullmatch(r'[a-f0-9]{64}', str(pin))
                and isinstance(bundle[name], str) and len(bundle[name]) <= 2800000, 'ASSET_BOUND')
        raw = base64.b64decode(bundle[name], validate=True)
        total += len(raw)
        require(len(raw) <= 2 * 1024 * 1024 and total <= 12 * 1024 * 1024 and sha(raw) == pin, 'ASSET_PIN')
        assets[name] = raw
    helper_asset = spec.get('helper_asset')
    require(helper_asset in assets and sha(assets[helper_asset]) == HELPER_SHA, 'HELPER_PIN')
    h = module('_nox_publish_helpers', assets[helper_asset])
    paths = spec.get('package_paths')
    require(isinstance(paths, dict) and set(paths) | {helper_asset} == set(assets), 'PACKAGE_SET')
    payloads = {}
    for name, relative in paths.items():
        match = re.fullmatch(r'(relay|contracts)/([a-f0-9]{64})\.json', str(relative))
        require(match and match[2] == sha(assets[name]) and encoded(json.loads(assets[name])) == assets[name], 'PACKAGE_PATH')
        payloads[PACKAGE / relative] = assets[name]
    manifest_sha = spec.get('manifest_sha256')
    require(isinstance(manifest_sha, str) and re.fullmatch(r'[a-f0-9]{64}', manifest_sha), 'MANIFEST_SHA')
    manifest_path = PACKAGE / 'relay' / (manifest_sha + '.json')
    require(manifest_path in payloads, 'MANIFEST_MISSING')
    manifest = json.loads(payloads[manifest_path])
    receipt = {'schema': 'NOX_SYSTEMIC_RELAY_PUBLISH_RECEIPT_V1', 'request': request,
        'source_sha': commit, 'manifest_sha256': manifest_sha, 'started_at': time.time(),
        'state': 'PREFLIGHT', 'workers_restarted': 0, 'queue_writes': 0,
        'source_writes': 0, 'test_writes': 0, 'original_tasks_accepted': 0}
    try:
        require_exactly_one_successor(manifest)
        evidence = manifest.get('producer_evidence')
        require(isinstance(evidence,dict),'PRODUCER_EVIDENCE')
        owner_snapshot = validate_owner_snapshot(spec.get('owner_snapshot'))
        require(evidence.get('owner_snapshot') == owner_snapshot
                and evidence.get('owner_snapshot_sha256') == sha(encoded(owner_snapshot))
                and spec.get('owner_snapshot_sha256') == sha(encoded(owner_snapshot))
                and owner_snapshot.get('config_sha256') == spec.get('expected_config_sha256')
                and owner_snapshot.get('previous_manifest_sha256') == spec.get('previous_manifest_sha256')
                and owner_snapshot.get('source_files_sha256') == spec.get('expected_source_files_sha256')
                and owner_snapshot.get('registry_sha256') == evidence.get('registry_sha256')
                and owner_snapshot.get('refill_request_id') == evidence.get('refill_request_id')
                and owner_snapshot.get('original_task_states_sha256') ==
                    evidence.get('refill_request_binding',{}).get('original_task_states_sha256'),
                'OWNER_SNAPSHOT_BINDING')
        process_identity_sha = sha(encoded({'director':spec.get('expected_director'),
            'workers':spec.get('expected_workers'),
            'protected_processes':spec.get('protected_processes')}))
        require(owner_snapshot.get('process_identity_sha256') == process_identity_sha,
                'OWNER_SNAPSHOT_PROCESS_BINDING')
    except BaseException as exc:
        receipt['state'] = hold_state_from_exception(exc)
        raise
    finally:
        if receipt.get('state') in HOLD_RECEIPT_STATES:
            persist_receipt(h,request,receipt)
    lock = ROOT / 'state/owner_maintenance.lock'
    state_dir_fd = -1
    fd = -1
    try:
        require(lock.parent == ROOT / 'state' and not lock.parent.is_symlink()
                and not lock.is_symlink(), 'LEASE_PATH')
        state_dir_fd = os.open(lock.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = os.open(lock.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=state_dir_fd)
        require(owner_lock_path_matches(fd,lock,state_dir_fd), 'LEASE_IDENTITY')
    except BaseException as exc:
        if fd >= 0:
            os.close(fd)
        if state_dir_fd >= 0:
            os.close(state_dir_fd)
        receipt['state'] = hold_state_from_exception(exc)
        raise
    finally:
        if receipt.get('state') in HOLD_RECEIPT_STATES:
            persist_receipt(h,request,receipt)
    changed = False
    old_raw = new_raw = None
    try:
        deadline = time.monotonic() + 8
        while True:
            require(h.stop_clear(ROOT), 'OWNER_STOP')
            require(owner_lock_path_matches(fd,lock,state_dir_fd), 'LEASE_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'MAINTENANCE_BUSY')
                time.sleep(.05)
        def guard():
            verify_owner_lock_identity(fd,lock,state_dir_fd)
            require(h.stop_clear(ROOT), 'OWNER_STOP')
            return h.expected_processes(spec), h.protected_snapshot(spec)
        processes, protected = guard()
        baseline = wait_settled_queue(h, guard, (processes, protected), receipt)
        require(receipt['busy_count'] == 0,'OWNER_SNAPSHOT_ACTIVE_CLAIMS')
        old_raw = h.read_regular(CONFIG, 2 * 1024 * 1024)
        require(sha(old_raw) == spec.get('expected_config_sha256'), 'CONFIG_PREDECESSOR')
        require(sha(old_raw) == owner_snapshot['config_sha256'], 'OWNER_SNAPSHOT_CONFIG_CHANGED')
        old = json.loads(old_raw)
        require(old.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
                and old.get('owner_authorized') is True and old.get('instance_id') == 60509551
                and old.get('mode') == 'NORMAL' and old.get('target') == 3
                and old.get('global_worker_cap') == 3 and old.get('execution_mode') == 'NATIVE_PROJECT_V1', 'OWNER_SCOPE')
        receipt['resource_preflight'] = require_budget_headroom(h.read_budget_snapshot(old))
        previous = old.get('systemic_relay', {}).get('sha256')
        require(previous == spec.get('previous_manifest_sha256')
                and previous == manifest.get('previous_manifest_sha256') and previous != manifest_sha, 'MANIFEST_PREDECESSOR')
        runtime = {}
        for name, pin in old['module_pins'].items():
            require(re.fullmatch(r'[A-Za-z0-9_]+\.py', name), 'MODULE_NAME')
            raw = h.read_regular(ROOT / 'scripts' / name, 1024 * 1024)
            require(sha(raw) == pin, 'RUNTIME_PIN')
            if name in ('owner_systemic_refill.py', 'owner_project_planner.py'):
                runtime[name] = raw
        refill = module('_nox_publish_refill', runtime['owner_systemic_refill.py'])
        planner = module('_nox_publish_planner', runtime['owner_project_planner.py'])
        refill.validate_manifest(manifest)
        verify_registry(manifest, h)
        verify_refill_request_state(manifest, baseline, refill)
        expected_contracts, expected_task_ids = mission_contracts(manifest, refill)
        receipt_contract = evidence.get('native_receipt_contract')
        expected_receipt_contract = native_receipt_contract(manifest['missions'][0],
            manifest_revision=manifest['revision'],
            previous_sha=manifest['previous_manifest_sha256'],
            registry_sha=evidence.get('registry_sha256'),
            review_sha=evidence.get('review_sha256'),refill=refill)
        require(receipt_contract == expected_receipt_contract
                and spec.get('native_receipt_contract_sha256') == sha(encoded(receipt_contract)),
                'NATIVE_RECEIPT_CONTRACT')
        bundled = {path.stem: raw for path, raw in payloads.items() if path.parent.name == 'contracts'}
        require(bundled == expected_contracts, 'MANIFEST_CONTRACT_SET')
        ancestor, seen = previous, {manifest_sha}
        while ancestor is not None:
            require(re.fullmatch(r'[a-f0-9]{64}', str(ancestor)) and ancestor not in seen and len(seen) < 64, 'MANIFEST_CHAIN_BOUND')
            seen.add(ancestor)
            prior_raw = h.read_regular(PACKAGE / 'relay' / (ancestor + '.json'), 2 * 1024 * 1024)
            require(sha(prior_raw) == ancestor, 'ANCESTOR_PIN')
            prior = json.loads(prior_raw)
            refill.validate_manifest(prior)
            if ancestor == previous:
                require(manifest['revision'] == prior['revision'] + 1
                        and manifest['registry'] == prior['registry'], 'MANIFEST_LINEAGE')
            ancestor = prior['previous_manifest_sha256']
        project = old['project_executor']
        root = project['roots']['NOX_PROJECT_SOURCE']
        require(root['path'] == str(ROOT / 'projects/owner_executor/source_workspace')
                and root.get('integration_kind') == 'SOURCE_WORKSPACE', 'SOURCE_ROOT')
        snapshot = h.source_snapshot(ROOT, old)
        require(snapshot['files_sha256'] == spec.get('expected_source_files_sha256'), 'SOURCE_PREIMAGE')
        require(snapshot['files_sha256'] == owner_snapshot['source_files_sha256'],
                'OWNER_SNAPSHOT_SOURCE_CHANGED')
        for path, raw in payloads.items():
            if path.parent.name != 'contracts':
                continue
            contract = json.loads(raw)
            require(contract.get('root_id') == 'NOX_PROJECT_SOURCE'
                    and not contract.get('allowed_new_paths')
                    and contract.get('acceptance_scope') == 'SOURCE_PATCH_TESTED'
                    and contract.get('original_task_accepted') is False
                    and set(row['path'] for row in contract['context']).issubset(root['allowed_paths']), 'CONTRACT_SCOPE')
            source_files = {row['path']: h.read_regular(Path(root['path']) / h.relpath(row['path']))
                            for row in contract['context']}
            planner.validate_contract(contract, source_files)
            verify_acceptance_anchors(contract, source_files)
        source_pins = {'NOX_PROJECT_SOURCE': {path: fact['sha256'] for path, fact in snapshot['files'].items()}}
        proposed = refill.select_next(manifest, baseline['tasks'], source_pins,
            {'slots_available': 3, 'callback_sha256': old['module_pins']['owner_subagent_dispatcher.py'],
             'manifest_sha256': manifest_sha, 'now': time.time()})
        require(sorted(row['id'] for row in proposed['rows']) == sorted(expected_task_ids)
                and len(expected_task_ids) == len(proposed['rows']) == 1,
                'NEXT_MISSIONS_NOT_READY')
        for path, raw in payloads.items():
            try:
                existing = h.read_regular(path, 2 * 1024 * 1024)
            except FileNotFoundError:
                existing = None
            require(existing is None or existing == raw, 'CONTENT_ADDRESS_COLLISION')
            if existing is None:
                prewrite = write_package_with_budget_gate(
                    h, path, raw, old, owner_snapshot,
                    spec.get('owner_snapshot_sha256'), fd, lock, state_dir_fd)
                receipt.setdefault('resource_prewrite_checks', []).append({
                    'package_path':str(path.relative_to(PACKAGE)), **prewrite})
            require(h.read_regular(path, 2 * 1024 * 1024) == raw, 'PACKAGE_READBACK')
        new = copy.deepcopy(old)
        new['systemic_relay'] = {'path': str(manifest_path), 'sha256': manifest_sha}
        new_raw = encoded(new)
        require(h.stop_clear(ROOT) and h.protected_snapshot(spec) == protected
                and h.expected_processes(spec) == processes
                and h.read_regular(CONFIG, 2 * 1024 * 1024) == old_raw
                and h.source_snapshot(ROOT, old) == snapshot, 'FINAL_CAS_CHANGED')
        state, active = h.queue_idle(ROOT)
        require(not active and h.preserve_terminal_history(baseline, state)['verified'], 'QUEUE_CHANGED')
        verify_refill_request_state(manifest, state, refill)
        # Existing queues, source roots, model and module pins remain byte-for-byte
        # equivalent. Only the next reviewed immutable manifest pointer changes.
        backup = ROOT / 'state/dispatcher/systemic_relay_publish_rollback' / request
        backup_result = ensure_exact_backup(
            h,backup,old_raw,old,owner_snapshot,fd,lock,state_dir_fd)
        receipt['backup_state'] = backup_result['state']
        if backup_result['resource_gate'] is not None:
            receipt['resource_prebackup'] = backup_result['resource_gate']
        changed = True
        receipt['resource_precommit'] = verify_publish_cas_preconditions(
            h, old, owner_snapshot, fd, lock, state_dir_fd)
        receipt['resource_precommit'] = atomic_owner_config(
            h, new_raw, old_raw, owner_snapshot, fd, lock, state_dir_fd)
        receipt.update(state='PUBLISHED_ONE_OWNER_REVIEWED_SUCCESSOR_PENDING_NATIVE_ADMISSION',
            previous_manifest_sha256=previous,
            previous_config_sha256=sha(old_raw), config_sha256=sha(new_raw),
            preserved_task_count=len(baseline['tasks']), director=processes['director'],
            original_task_id=receipt_contract['original_task_id'],
            successor_task_id=receipt_contract['successor_task_id'],
            owner_snapshot_sha256=sha(encoded(owner_snapshot)),
            native_receipt_contract_sha256=sha(encoded(receipt_contract)),
            original_task_accepted=False, native_job_created=False)
    except BaseException as exc:
        receipt['state'] = hold_state_from_exception(exc)
        if changed and old_raw is not None and new_raw is not None:
            # Never overwrite a newer owner's config during recovery.
            try:
                if h.read_regular(CONFIG, 2 * 1024 * 1024) == new_raw:
                    atomic_owner_config(h, old_raw, new_raw, owner_snapshot,
                                        fd, lock, state_dir_fd)
                    receipt['config_restored'] = h.read_regular(
                        CONFIG, 2 * 1024 * 1024) == old_raw
            except BaseException as rollback_exc:
                receipt['config_restored'] = False
                receipt['rollback_state'] = hold_state_from_exception(rollback_exc)
        raise
    finally:
        os.close(fd)
        os.close(state_dir_fd)
        if not persist_receipt(h,request,receipt):
            raise RuntimeError('HOLD_SYSTEMIC_PUBLISH_RECEIPT_WRITE')
    emit_publish_complete_marker()
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
