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
    lock = ROOT / 'state/owner_maintenance.lock'
    require(not lock.is_symlink(), 'LEASE_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    changed = False
    old_raw = new_raw = None
    receipt = {'schema': 'NOX_SYSTEMIC_RELAY_PUBLISH_RECEIPT_V1', 'request': request,
        'source_sha': commit, 'manifest_sha256': manifest_sha, 'started_at': time.time(),
        'state': 'PREFLIGHT', 'workers_restarted': 0, 'queue_writes': 0,
        'source_writes': 0, 'test_writes': 0, 'original_tasks_accepted': 0}
    try:
        deadline = time.monotonic() + 8
        while True:
            require(h.stop_clear(ROOT), 'OWNER_STOP')
            waiting, named = os.fstat(fd), lock.stat()
            require(stat.S_ISREG(waiting.st_mode) and waiting.st_nlink == 1
                    and (waiting.st_dev, waiting.st_ino) == (named.st_dev, named.st_ino), 'LEASE_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'MAINTENANCE_BUSY')
                time.sleep(.05)
        def guard():
            info, named = os.fstat(fd), lock.stat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                    and not info.st_mode & 0o022 and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'LEASE_IDENTITY')
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
                h.atomic(path, raw)
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
        require(not backup.exists() and not backup.is_symlink(), 'BACKUP_EXISTS')
        h.atomic(backup / 'config.json', old_raw)
        changed = True
        h.atomic(CONFIG, new_raw)
        require(h.read_regular(CONFIG, 2 * 1024 * 1024) == new_raw, 'CONFIG_READBACK')
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
        receipt['state'] = str(exc) if str(exc).startswith('HOLD_') else 'HOLD_SYSTEMIC_PUBLISH_' + type(exc).__name__
        if changed and old_raw is not None and new_raw is not None:
            # Never overwrite a newer owner's config during recovery.
            if h.read_regular(CONFIG, 2 * 1024 * 1024) == new_raw:
                h.atomic(CONFIG, old_raw)
                receipt['config_restored'] = h.read_regular(CONFIG, 2 * 1024 * 1024) == old_raw
        raise
    finally:
        os.close(fd)
        receipt['finished_at'] = time.time()
        h.atomic(ROOT / 'state/dispatcher' / ('systemic_relay_publish_' + request + '.json'), encoded(receipt))
        print('NOX_MAINT_SYSTEMIC_RELAY_PUBLISH=' + encoded(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


if __name__ == '__main__':
    run(BUNDLE, SPEC)
