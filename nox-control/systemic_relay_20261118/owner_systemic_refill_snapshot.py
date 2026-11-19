#!/usr/bin/env python3
"""Read the existing NOX refill request and produce inputs for its owner publisher."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import types


ROOT = Path('/root/nox')
INSTANCE = 60509551
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
PUBLISHER_ASSET = 'owner_systemic_relay_publish.py'
DISPOSITION_ASSET = 'all295_execution_disposition.json'
HELPER_ASSET = 'continuous_transaction_helpers.py'
REGISTRY_NAMES = {
    'tasks': 'project_work_tasks.json',
    'ideas': 'project_work_ideas.json',
    'receipts': 'project_work_receipts_source.json',
    'routing': 'project_routing_4q.json',
}
PROTECTED = {'chat': 'nox-ds41-8098', 'proxy': 'nox-proxy', 'web': 'nox-web29-18775'}
DIRECTOR = 'nox-dispatcher-t855u'
ROLES = {'runtime', 'memory', 'weights'}
SHA = re.compile(r'[a-f0-9]{64}\Z')
REQUEST_KEYS = (
    'schema', 'request_id', 'previous_manifest_sha256', 'manifest_revision',
    'registry_pins', 'source_pins', 'outcomes', 'original_task_states',
    'original_task_states_sha256', 'original_task_accepted', 'evidence_scope',
)
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


class SnapshotHold(ValueError):
    """Return only fixed reasons to the transport."""


def require(condition, reason):
    if not condition:
        raise SnapshotHold('HOLD_REFILL_SNAPSHOT_' + reason)


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, raw):
    module = types.ModuleType(name)
    module.__file__ = '<reviewed-refill-snapshot>/' + name + '.py'
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def bundle_asset(bundle, name, maximum):
    entry = bundle.get(name)
    require(isinstance(entry, dict) and set(entry) == {'content', 'sha256'}, 'BUNDLE_ASSET')
    content = entry['content']
    require(type(content) is str and len(content) <= 4 * ((maximum + 2) // 3),
            'BUNDLE_ASSET_SIZE')
    raw = base64.b64decode(content, validate=True)
    require(len(raw) <= maximum and sha(raw) == entry['sha256'], 'BUNDLE_ASSET_PIN')
    return raw


def maintenance_identity(fd, path):
    info, named = os.fstat(fd), path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022
            and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
            'MAINTENANCE_LOCK_IDENTITY')


def service_pids():
    services = [DIRECTOR, *PROTECTED.values()]
    call = subprocess.run(['supervisorctl', 'status', *services], capture_output=True, text=True,
                          timeout=5, check=False)
    require(call.returncode == 0 and len(call.stdout) < 4096, 'SUPERVISOR_STATUS')
    result = {}
    for line in call.stdout.splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)\s+RUNNING\s+pid ([1-9][0-9]*),[^\r\n]*', line)
        require(match and match[1] in services and match[1] not in result, 'SERVICE_STATE')
        result[match[1]] = int(match[2])
    require(set(result) == set(services) and len(set(result.values())) == len(services),
            'SERVICE_IDENTITIES')
    return result


def current_processes(native, helper, services):
    director = native['director']
    workers = native['workers']
    require(director.get('pid') == services[DIRECTOR] and isinstance(workers, list)
            and len(workers) == 3 and all(isinstance(row, dict) for row in workers)
            and {row.get('role') for row in workers} == ROLES
            and all(row.get('state') == 'RUNNING' and row.get('instance_id') == INSTANCE
                    and row.get('native_pid_verified') is True and row.get('current_task') is None
                    for row in workers), 'WORKERS_NOT_IDLE')
    director_pin = {'pid': director['pid'], 'start_ticks': director['process_starttime']}
    worker_pins = [{'pid': row['pid'], 'start_ticks': row['process_starttime']}
                   for row in sorted(workers, key=lambda row: row['role'])]
    expected = {'expected_director': director_pin, 'expected_workers': worker_pins}
    helper.expected_processes(expected)
    protected = {}
    for label, service in PROTECTED.items():
        identity = helper.process_identity(services[service])
        require(identity and identity['pid'] == services[service], 'PROTECTED_PROCESS')
        protected[label] = {'pid': identity['pid'], 'start_ticks': identity['start_ticks']}
    require(len({row['pid'] for row in [director_pin, *worker_pins, *protected.values()]}) == 7,
            'PROCESS_IDENTITIES')
    expected['protected_processes'] = protected
    helper.protected_snapshot(expected)
    return expected


def read_registry(root, helper, disposition, manifest_registry):
    pins, documents = {}, {}
    for key, name in REGISTRY_NAMES.items():
        raw = helper.read_regular(root / 'state/dispatcher' / name, 16 * 1024 * 1024)
        pins[key] = sha(raw)
        if key != 'receipts':
            documents[key] = json.loads(raw)
    require(pins == manifest_registry.get('source_registry_sha256')
            == disposition.get('source_registry_sha256'),
            'ORIGINAL_REGISTRY_DRIFT')
    specs = documents['tasks']['tasks'] + documents['ideas']['ideas']
    routes = {row['task_id']: row['queue_id'] for row in documents['routing']['tasks']}
    ledger = {row['task_id']: row for row in disposition['tasks']}
    require(len(documents['tasks']['tasks']) == 230 and len(documents['ideas']['ideas']) == 65
            and len(documents['routing']['tasks']) == len(disposition['tasks']) == len(ledger)
            == len(routes) == disposition.get('total_original_ids') == 295
            and len({row['id'] for row in specs}) == 295
            and set(routes) == set(ledger) == {row['id'] for row in specs}
            and disposition.get('original_acceptance_added') == 0, 'ORIGINAL_REGISTRY_COUNT')
    parents = manifest_registry['parents']
    require(set(parents) <= ledger.keys(), 'MANIFEST_ORIGINAL_PARENTS')
    for spec in specs:
        task_id = spec['id']
        row = ledger[task_id]
        require(row.get('spec') == spec and row.get('spec_sha256') == sha(encode(spec))
                and row.get('queue_id') == routes[task_id]
                and row.get('original_acceptance_added') is False, 'ORIGINAL_REGISTRY_BINDING')
        if task_id in parents:
            parent = parents[task_id]
            require(parent.get('spec_sha256') == row['spec_sha256']
                    and parent.get('queue_id') == routes[task_id]
                    and parent.get('required_evidence') == spec.get('evidence'),
                    'MANIFEST_ORIGINAL_PARENT_BINDING')
    return pins, set(ledger)


def active_queue_rows(tasks, relay):
    # Match the publisher's running guard and additionally reject unsettled
    # relay claims. Pending legacy rows may remain in the durable queue.
    return [task_id for task_id, row in tasks.items()
            if row.get('status') == 'running'
            or (isinstance(row.get('systemic_relay'), dict)
                and row['systemic_relay']
                and row.get('status') not in relay.TERMINAL)]


def normalized_task_states(tasks, original_ids, relay):
    rows = []
    for task_id in sorted(tasks):
        if task_id.split('.', 1)[0] in original_ids:
            status = tasks[task_id].get('status')
            rows.append({'task_id': task_id,
                         'status': status if status in relay.ACTIVE | relay.TERMINAL else 'unknown'})
    require(len(rows) <= 8192, 'ORIGINAL_STATE_BOUND')
    return rows


def verify_refill_request(native, manifest, manifest_sha, tasks, pins, relay, now):
    state = native['systemic_relay']
    require(state.get('state') == 'REFILL_REQUIRED' and state.get('manifest_sha256') == manifest_sha
            and state.get('eligible_proposals') == 0 and state.get('shared_queue') is True,
            'NO_CURRENT_REFILL_REQUIRED')
    request = state['refill_request']
    require(isinstance(request, dict) and request.get('schema') == 'NOX_SYSTEMIC_REFILL_REQUEST_V1',
            'NATIVE_REQUEST_SHAPE')
    require(set(REQUEST_KEYS) <= request.keys(), 'REFILL_REQUEST_CONTRACT_INCOMPATIBLE')
    source_pins = {}
    for root_id, paths in relay.source_requests(manifest).items():
        require(root_id == 'NOX_PROJECT_SOURCE' and set(paths) <= pins.keys(), 'REQUEST_SOURCE_SCOPE')
        source_pins[root_id] = {path: pins[path] for path in paths}
    outcomes = relay._outcomes(tasks)
    require(all(relay.ID.fullmatch(row['task_id']) and relay.MISSION.fullmatch(row['mission_id'])
                and SHA.fullmatch(row['input_sha256']) for row in outcomes), 'REQUEST_OUTCOME_SCOPE')
    original_states = normalized_task_states(tasks, manifest['registry']['parents'], relay)
    decision = relay.select_next(manifest, tasks, source_pins,
                                 {'slots_available': 3, 'callback_sha256': native['callback_sha256'],
                                  'manifest_sha256': manifest_sha, 'now': now,
                                  'reserved_sources': []})
    require(decision['state'] == 'REFILL_REQUIRED' and not decision['rows']
            and decision['refill_request'] is not None, 'REQUEST_NO_LONGER_CURRENT')
    require(request['outcomes'] == outcomes and request['original_task_states'] == original_states,
            'REQUEST_DURABLE_STATE_DRIFT')
    public_request = {key: request[key] for key in REQUEST_KEYS}
    require(public_request == {key: decision['refill_request'][key] for key in REQUEST_KEYS},
            'REQUEST_CAS_MISMATCH')
    require(all(relay.ID.fullmatch(row['task_id']) for row in original_states),
            'ORIGINAL_STATE_ID_SCOPE')
    return public_request


def observe_inputs(root, helper, disposition, get_services, now):
    require(helper.stop_clear(root), 'STOP_OR_MAINTENANCE')
    config_raw = helper.read_regular(root / helper.CONFIG, 2 * 1024 * 1024)
    config = json.loads(config_raw)
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('owner_authorized') is True and config.get('instance_id') == INSTANCE
            and config.get('mode') == 'NORMAL' and config.get('target') == 3
            and config.get('global_worker_cap', 3) == 3
            and config.get('execution_mode') == 'NATIVE_PROJECT_V1',
            'OWNER_RUNTIME_SCOPE')

    module_pins = config['module_pins']
    refill_raw = helper.read_regular(root / 'scripts/owner_systemic_refill.py', 1024 * 1024)
    callback = helper.read_regular(root / 'scripts/owner_subagent_dispatcher.py', 1024 * 1024)
    require(sha(refill_raw) == module_pins['owner_systemic_refill.py']
            and sha(callback) == module_pins['owner_subagent_dispatcher.py'], 'INSTALLED_RUNTIME_PIN')
    relay = load_module('_nox_snapshot_refill', refill_raw)
    require(callable(getattr(relay, 'acceptance_mapping_valid', None)),
            'REFILL_RUNTIME_CONTRACT_INCOMPATIBLE')

    reference = config['systemic_relay']
    manifest_sha = reference['sha256']
    require(type(manifest_sha) is str and SHA.fullmatch(manifest_sha), 'PREDECESSOR_SHA')
    manifest_path = root / 'state/dispatcher/project_executor/package/relay' / (manifest_sha + '.json')
    require(reference['path'] == str(manifest_path), 'PREDECESSOR_PATH')
    manifest_raw = helper.read_regular(manifest_path, 1024 * 1024)
    manifest = json.loads(manifest_raw)
    require(sha(manifest_raw) == manifest_sha and encode(manifest) == manifest_raw,
            'PREDECESSOR_PIN')
    relay.validate_manifest(manifest)
    registry_pins, original_ids = read_registry(root, helper, disposition, manifest['registry'])

    queue_raw = helper.read_regular(root / helper.STATE)
    tasks = json.loads(queue_raw)['tasks']
    require(isinstance(tasks, dict) and all(isinstance(row, dict) for row in tasks.values()),
            'DURABLE_QUEUE_SHAPE')
    require(not active_queue_rows(tasks, relay), 'ACTIVE_CLAIMS')

    native = json.loads(helper.read_regular(root / helper.STATUS, 2 * 1024 * 1024))[
        'native_subexecutors']
    observed_at = native.get('observed_at')
    require(type(observed_at) in (int, float) and -5 <= now - observed_at <= 60,
            'NATIVE_STATUS_STALE')
    project = native.get('project_queues')
    require(isinstance(project, dict)
            and project.get('state') == 'HANDOFF_RECEIVED_PROJECT_EXECUTION_BOUND'
            and project.get('dispatch_cap') == 3 and project.get('received_unique_tasks') == 295,
            'NATIVE_PROJECT_DISPATCH_SCOPE')
    processes = current_processes(native, helper, get_services())
    native['callback_sha256'] = sha(callback)

    source = helper.source_snapshot(root, config)
    pins = {path: row['sha256'] for path, row in source['files'].items()}
    require(all(type(pin) is str and SHA.fullmatch(pin) for pin in pins.values()),
            'SOURCE_FILE_PIN')
    request = verify_refill_request(native, manifest, manifest_sha, tasks, pins, relay, now)
    budget = helper.read_budget_snapshot(config)
    headroom = budget['max_bytes'] - budget['current_bytes']
    # This endpoint is evidence-only. The owner/CAS publisher independently
    # requires fresh >=minimum_headroom_bytes at EACH immutable package write
    # and again before config CAS. Do not suppress a valid low-memory snapshot
    # needed to prepare the NEXT reviewed taskpack.
    require(0 <= headroom <= budget['max_bytes'], 'RAW_CGROUP_HEADROOM')
    return {
        'config_sha256': sha(config_raw), 'previous_manifest_sha256': manifest_sha,
        'source': source, 'source_pins': pins, 'registry_pins': registry_pins,
        'queue_sha256': sha(queue_raw),
        'all_original_task_states_sha256': sha(encode(normalized_task_states(tasks, original_ids, relay))),
        'request': request, 'processes': processes,
        'resource_headroom_bytes': headroom,
        'refill_module_sha256': sha(refill_raw), 'callback_sha256': sha(callback),
    }


def capture(root, helper, disposition_raw, publisher_sha, request_id, owner_source_sha,
            *, now=time.time, get_services=service_pids):
    disposition = json.loads(disposition_raw)
    lock_path = root / 'state/owner_maintenance.lock'
    require(not any(path.is_symlink() for path in lock_path.parents), 'MAINTENANCE_LOCK_PATH')
    require(helper.stop_clear(root), 'STOP_OR_MAINTENANCE')
    _, active = helper.queue_idle(root)
    require(not active, 'ACTIVE_CLAIMS')
    fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        maintenance_identity(fd, lock_path)
        try:
            # Compatible with dispatcher's normal SH owner lease. A publisher
            # taking EX still blocks us; two identical complete snapshots
            # must be observed before encrypting the evidence.
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SnapshotHold('HOLD_REFILL_SNAPSHOT_MAINTENANCE_BUSY') from None
        start = time.monotonic()
        first = observe_inputs(root, helper, disposition, get_services, now())
        final = observe_inputs(root, helper, disposition, get_services, now())
        maintenance_identity(fd, lock_path)
        require(helper.stop_clear(root), 'STOP_OR_MAINTENANCE')
        require(time.monotonic() - start <= 15, 'SNAPSHOT_TIME_BOUND')
        resource_key = 'resource_headroom_bytes'
        observed_minimum_headroom = min(first.pop(resource_key), final.pop(resource_key))
        require(first == final, 'INPUTS_CHANGED')
        source = final['source']
        observed_at = now()
        request = final['request']
        processes = final['processes']
        process_sha = sha(encode({
            'director': processes['expected_director'], 'workers': processes['expected_workers'],
            'protected_processes': processes['protected_processes'],
        }))
        disposition_sha = sha(disposition_raw)
        readback = {
            'schema': 'NOX_SYSTEMIC_REFILL_NATIVE_READBACK_V1', 'instance_id': INSTANCE,
            'owner_request_id': request_id, 'owner_source_sha': owner_source_sha,
            'observed_at': observed_at, 'active_claim_count': 0, 'stop_clear': True,
            'native_dispatch_cap': 3,
            'queue_sha256': final['queue_sha256'],
            'config_sha256': final['config_sha256'],
            'previous_manifest_sha256': final['previous_manifest_sha256'],
            'registry_source_sha256': final['registry_pins'],
            'registry_disposition_sha256': disposition_sha,
            'all_original_task_states_sha256': final['all_original_task_states_sha256'],
            'source_files_sha256': source['files_sha256'],
            'process_identity_sha256': process_sha,
            'refill_request_sha256': sha(encode(request)),
            'refill_module_sha256': final['refill_module_sha256'],
            'callback_sha256': final['callback_sha256'],
            'minimum_observed_raw_headroom_bytes': observed_minimum_headroom,
            'publisher_template_sha256': publisher_sha,
            'native_write_performed': False, 'publication_authorized': False,
        }
        native_sha = sha(encode(readback))
        owner_snapshot = {
            'schema': 'NOX_SYSTEMIC_OWNER_PUBLISH_SNAPSHOT_V1', 'owner_id': INSTANCE,
            'observed_at': observed_at, 'config_sha256': final['config_sha256'],
            'previous_manifest_sha256': final['previous_manifest_sha256'],
            'registry_sha256': disposition_sha, 'source_files_sha256': source['files_sha256'],
            'refill_request_id': request['request_id'],
            'original_task_states_sha256': request['original_task_states_sha256'],
            'process_identity_sha256': process_sha,
            'native_readback_sha256': native_sha, 'active_claim_count': 0,
        }
        checkpoint = {
            'schema': 'NOX_SYSTEMIC_NATIVE_PUBLISH_CHECKPOINT_V1',
            'expected_config_sha256': final['config_sha256'],
            'previous_manifest_sha256': final['previous_manifest_sha256'],
            'expected_source_files_sha256': source['files_sha256'],
            'publisher_template_sha256': publisher_sha,
            'owner_snapshot_sha256': sha(encode(owner_snapshot)),
            **processes,
        }
        census = {
            'schema': 'NOX_SYSTEMIC_SOURCE_CENSUS_V1', 'atomic_snapshot': True,
            'current_cas_recheck_required': True, 'observed_config_sha256': final['config_sha256'],
            'observed_files_sha256': source['files_sha256'], 'observed_readback_sha256': native_sha,
            'original_task_accepted': False, 'roots': {'NOX_PROJECT_SOURCE': final['source_pins']},
        }
        return owner_snapshot, checkpoint, request, census, readback
    finally:
        os.close(fd)


def main():
    request_id = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    owner_source_sha = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(os.environ.get('NOX_OWNER_ACTION') == 'refill_snapshot'
            and os.environ.get('NOX_OWNER_INSTANCE_ID') == str(INSTANCE)
            and re.fullmatch(r'[1-9][0-9]{0,23}', request_id)
            and re.fullmatch(r'[a-f0-9]{40}', owner_source_sha), 'EXACT_OWNER_TRANSPORT')
    require(set(BUNDLE) == {HELPER_ASSET, PUBLISHER_ASSET, DISPOSITION_ASSET}, 'BUNDLE_SET')
    helper_raw = bundle_asset(BUNDLE, HELPER_ASSET, 128 * 1024)
    require(sha(helper_raw) == HELPER_SHA, 'TRANSACTION_HELPER_PIN')
    helper = load_module('_nox_snapshot_transaction', helper_raw)
    publisher_sha = sha(bundle_asset(BUNDLE, PUBLISHER_ASSET, 256 * 1024))
    disposition_raw = bundle_asset(BUNDLE, DISPOSITION_ASSET, 2 * 1024 * 1024)
    values = capture(ROOT, helper, disposition_raw, publisher_sha, request_id, owner_source_sha)
    markers = ('REFILL_OWNER_SNAPSHOT', 'REFILL_SNAPSHOT_CHECKPOINT', 'REFILL_REQUIRED_REQUEST',
               'REFILL_SOURCE_CENSUS', 'REFILL_NATIVE_READBACK')
    records = [encode(value) for value in values]
    require(all(len(raw) <= (1024 * 1024 if marker == 'REFILL_REQUIRED_REQUEST' else 64 * 1024)
                for marker, raw in zip(markers, records)), 'RECEIPT_SIZE')
    for marker, raw in zip(markers, records):
        print('NOX_MAINT_' + marker + '=' + raw.decode(), flush=True)
    print('NOX_MAINT_REFILL_SNAPSHOT_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SnapshotHold) else 'HOLD_REFILL_SNAPSHOT_READBACK'
        print('NOX_MAINT_REFILL_SNAPSHOT_HOLD=' + encode({'reason': reason}).decode(), flush=True)
        raise SystemExit(2)
