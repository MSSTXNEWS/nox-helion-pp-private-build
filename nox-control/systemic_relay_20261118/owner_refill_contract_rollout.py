#!/usr/bin/env python3
"""Install one owner-pinned refill contract runtime on the existing NOX director."""
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
import subprocess
import time
import types


ROOT = Path('/root/nox')
CONFIG = 'config/owner_native_subagents.json'
REFILL = 'scripts/owner_systemic_refill.py'
DIRECTOR = 'scripts/owner_subagent_dispatcher.py'
OLD = {
    CONFIG: '46d25dea55b290749ebd6bc5df5a202c0f029ff90ea3e54c3849801834db9a29',
    REFILL: '08b230ae02d0be832df68df53750c356a88b0c803f31562d9e8859697679437b',
}
DIRECTOR_SHA = 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
REFILL_SHA = '5fd359514c64e6ab1e15040c7c8fcc36c46257df6973bee99c3b212e6391375a'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
EXPECTED_PROCESSES = {
    'expected_director': {'pid': 762906, 'start_ticks': 189372583},
    'expected_workers': [
        {'pid': 763015, 'start_ticks': 189374028},
        {'pid': 763016, 'start_ticks': 189374028},
        {'pid': 763017, 'start_ticks': 189374028},
    ],
}
PROTECTED_SERVICES = ('nox-ds41-8098', 'nox-proxy', 'nox-web29-18775')
TERMINAL_SERVICES = ('STOPPED', 'FATAL', 'EXITED')
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_REFILL_CONTRACT_ROLLOUT_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode()


def load_module(name, raw):
    module = types.ModuleType(name)
    module.__file__ = '<owner-reviewed>/' + name + '.py'
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def decode_bundle(bundle):
    pins = {'owner_systemic_refill.py': REFILL_SHA,
            'continuous_transaction_helpers.py': HELPER_SHA}
    require(type(bundle) is dict and bundle.keys() == pins.keys(), 'BUNDLE_FILES')
    assets = {}
    for name, pin in pins.items():
        encoded = bundle[name]
        require(type(encoded) is str and len(encoded) <= 334000, 'BUNDLE_SIZE')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 250000 and sha(raw) == pin, 'BUNDLE_PIN')
        compile(raw, '<owner-reviewed>/' + name, 'exec')
        assets[name] = raw
    helper = load_module('_refill_rollout_transaction', assets['continuous_transaction_helpers.py'])
    return helper, assets['owner_systemic_refill.py']


def build_payload(repository):
    paths = {'owner_systemic_refill.py': repository / 'nox-control/systemic_relay_20261118'
                                          / 'runtime/owner_systemic_refill.py',
             'continuous_transaction_helpers.py': repository / 'nox-control'
                                                / 'continuous_executor_20261118/assets'
                                                / 'continuous_transaction_helpers.py'}
    assets = {name: base64.b64encode(path.read_bytes()).decode('ascii')
              for name, path in paths.items()}
    decode_bundle(assets)
    source = Path(__file__).read_text(encoding='utf-8')
    marker = '__NOX_' 'BUNDLE_JSON__'
    require(source.count(marker) == 1, 'BUNDLE_TEMPLATE')
    payload = source.replace(marker, json.dumps(assets, sort_keys=True))
    compile(payload, '<owner-refill-contract-rollout>', 'exec')
    return payload


def service_guard(helper):
    identities = {}
    for service in PROTECTED_SERVICES:
        result = subprocess.run(['supervisorctl', 'status', service], capture_output=True,
                                text=True, timeout=8)
        match = re.fullmatch(re.escape(service) + r'\s+RUNNING\s+pid\s+(\d+),[^\r\n]*',
                             result.stdout.strip())
        require(result.returncode == 0 and match, 'PROTECTED_SERVICE')
        identity = helper.process_identity(int(match[1]))
        require(identity is not None, 'PROTECTED_PROCESS')
        identities[service] = identity
    require(len({row['pid'] for row in identities.values()}) == len(PROTECTED_SERVICES),
            'PROTECTED_PROCESS_DUPLICATE')
    return identities


def read_queue(helper, root):
    raw = helper.read_regular(root / helper.STATE, 32 * 1024 * 1024)
    queue = json.loads(raw)
    tasks = queue.get('tasks')
    require(isinstance(tasks, dict) and all(isinstance(row, dict) for row in tasks.values()),
            'QUEUE_SHAPE')
    for row in tasks.values():
        lease = row.get('native_worker_lease')
        require(row.get('status') != 'running'
                and (not lease or isinstance(lease, dict) and lease.get('phase') == 'SETTLED'),
                'ACTIVE_QUEUE_CLAIM')
    return queue, sha(raw)


def verify_legacy_contracts(helper, root, config, old_module, module, queue):
    reference = config['systemic_relay']
    package = Path(config['project_executor']['package_root'])
    require(package.is_relative_to(root) and '..' not in package.parts, 'PACKAGE_ROOT')
    directory = package / 'relay'
    pin = reference.get('sha256')
    require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin)
            and reference.get('path') == str(directory / (pin + '.json')), 'MANIFEST_POINTER')
    visited, compared = {}, 0
    while pin is not None:
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin)
                and pin not in visited and len(visited) < 64, 'MANIFEST_CHAIN')
        raw = helper.read_regular(directory / (pin + '.json'), 2 * 1024 * 1024)
        manifest = json.loads(raw)
        require(sha(raw) == pin and encode(manifest) == raw, 'MANIFEST_PIN')
        old_module.validate_manifest(manifest)
        module.validate_manifest(manifest)
        visited[pin] = manifest
        for mission in manifest['missions']:
            old = old_module._input(mission)
            new = module._input(mission)
            task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + old[:16]
            require(old == new and encode(old_module._contract(mission, task_id)) ==
                    encode(module._contract(mission, task_id)), 'LEGACY_TASK_ID_OR_CONTRACT_CHANGED')
            compared += 1
        pin = manifest['previous_manifest_sha256']
    for task_id, task in queue['tasks'].items():
        if 'systemic_relay' not in task:
            continue
        record = task['systemic_relay']
        row = record['reviewed_row']
        contract_sha = row['params']['contract_sha256']
        require(row.get('id') == task_id and re.fullmatch('[0-9a-f]{64}', contract_sha)
                and record['manifest_sha256'] in visited, 'LEGACY_DURABLE_BINDING')
        raw = helper.read_regular(package / 'contracts' / (contract_sha + '.json'),
                                  2 * 1024 * 1024)
        require(sha(raw) == contract_sha, 'LEGACY_DURABLE_CONTRACT_PIN')
        contract = json.loads(raw)
        manifest = visited[record['manifest_sha256']]
        old_module.validate_binding(manifest, record['binding'], row, contract)
        module.validate_binding(manifest, record['binding'], row, contract)
    return compared, visited[reference['sha256']]


def verify_refill_request(module, relay, manifest, manifest_sha, queue):
    request = relay.get('refill_request')
    require(isinstance(request, dict) and request.get('schema') == 'NOX_SYSTEMIC_REFILL_REQUEST_V1'
            and relay.get('manifest_sha256') == manifest_sha
            and relay.get('eligible_proposals') == 0
            and request.get('previous_manifest_sha256') == manifest_sha
            and request.get('manifest_revision') == manifest['revision']
            and request.get('registry_pins') == manifest['registry']['source_registry_sha256'],
            'REFILL_REQUEST_SCOPE')
    states = request.get('original_task_states')
    members = {key: row for key, row in queue['tasks'].items()
               if key.split('.', 1)[0] in manifest['registry']['parents']}
    require(isinstance(states, list) and set(members) == {row['task_id'] for row in states}
            and len(states) == len(members) and states == sorted(states, key=lambda row: row['task_id']),
            'REFILL_REQUEST_ORIGINAL_TASK_IDS')
    for row in states:
        state = members[row['task_id']].get('status')
        normalized = state if state in module.ACTIVE | module.TERMINAL else 'unknown'
        require(row == {'task_id': row['task_id'], 'status': normalized}
                or (row == {'task_id': row['task_id'], 'status': 'unknown'}
                    and state in ('blocked', 'failed', 'cancelled')
                    and members[row['task_id']].get('handler') == 'owner_native_project_work'),
                'REFILL_REQUEST_ORIGINAL_TASK_STATUS')
    request_id = module.digest({'manifest_sha256': manifest_sha, 'source_pins': request['source_pins'],
                                'outcomes': request['outcomes'], 'original_task_states': states})
    require(module.digest(states) == request.get('original_task_states_sha256')
            and request_id == request.get('request_id') == relay.get('fingerprint'),
            'REFILL_REQUEST_BINDING')
    return request_id


def maintenance_lease(fd, path, helper, root):
    info, named = os.fstat(fd), path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022
            and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
            'MAINTENANCE_LOCK_IDENTITY')
    require(helper.stop_clear(root), 'OWNER_STOP')


def acquire_lease(fd, lock, helper, root):
    deadline = time.monotonic() + 6
    while True:
        maintenance_lease(fd, lock, helper, root)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            require(time.monotonic() < deadline, 'MAINTENANCE_BUSY')
            time.sleep(.15)
    maintenance_lease(fd, lock, helper, root)


def start_owned_director(helper):
    before = helper.supervisor('status')
    require(before.get('state') in TERMINAL_SERVICES and before.get('pid') is None,
            'START_REQUIRES_STOPPED_DIRECTOR')
    ack = helper.supervisor('start')
    require(ack == {'action': 'start', 'rc': 0}, 'START_NOT_ACKNOWLEDGED')
    observed = helper.supervisor('status')
    require(observed.get('state') == 'RUNNING', 'START_NOT_RUNNING')
    owned = helper.process_identity(observed.get('pid'))
    require(owned is not None and helper.supervisor('status') == observed
            and helper.process_identity(observed.get('pid')) == owned, 'START_IDENTITY')
    return owned


def recover_director(helper, present, owned, original, children, candidate_start_attempted):
    live = helper.process_identity(present.get('pid'))
    if live is not None:
        require(live != original, 'ORIGINAL_DIRECTOR_STILL_LIVE')
        require(owned is not None and live == owned, 'RECOVERY_FOREIGN_DIRECTOR')
        descendants = helper.descendant_snapshot(live['pid'])
        helper.stop_checked()
        helper.wait_previous_descendants_stopped(descendants, timeout=10)
    elif present.get('state') == 'BACKOFF' and present.get('pid') is None and candidate_start_attempted:
        helper.stop_checked()
        stopped = helper.supervisor('status')
        require(stopped.get('state') in TERMINAL_SERVICES and stopped.get('pid') is None,
                'RECOVERY_BACKOFF_NOT_STOPPED')
        helper.wait_previous_descendants_stopped(children, timeout=10)
    else:
        require(present.get('state') in TERMINAL_SERVICES and present.get('pid') is None,
                'RECOVERY_UNKNOWN_DIRECTOR')
        helper.wait_previous_descendants_stopped(children, timeout=10)


def headroom(helper, config):
    budget = helper.read_budget_snapshot(config)
    free = budget['max_bytes'] - budget['current_bytes']
    require(budget['minimum_headroom_bytes'] == 2 ** 31 and free >= 2 ** 31,
            'RAW_CGROUP_HEADROOM')
    return free


def read_idle_workers(helper, root, director):
    document = json.loads(helper.read_regular(root / helper.STATUS, 2 * 1024 * 1024))
    native = document['native_subexecutors']
    status = native['director']
    workers = native['workers']
    require(status.get('pid') == director['pid']
            and status.get('process_starttime') == director['start_ticks']
            and 0 <= time.time() - native['observed_at'] <= 15, 'NATIVE_STATUS_IDENTITY')
    require(isinstance(workers, list) and len(workers) == 3
            and {worker.get('role') for worker in workers} == {'runtime', 'memory', 'weights'}
            and all(worker.get('current_task') is None and worker.get('state') == 'RUNNING'
                    and worker.get('native_pid_verified') is True for worker in workers),
            'NATIVE_WORKERS_NOT_IDLE')
    helper.expected_processes({'expected_director': director, 'expected_workers': [
        {'pid': worker['pid'], 'start_ticks': worker['process_starttime']} for worker in workers]})
    return native


def wait_for_request(helper, root, module, started, manifest, manifest_sha, baseline):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        queue, _ = read_queue(helper, root)
        try:
            native = read_idle_workers(helper, root, started)
            request_id = verify_refill_request(module, native['systemic_relay'],
                                              manifest, manifest_sha, queue)
            require(baseline['tasks'] == queue['tasks'], 'QUEUE_HISTORY_CHANGED')
            return request_id
        except (OSError, KeyError, ValueError, TypeError, RuntimeError, helper.Hold):
            time.sleep(.5)
    require(False, 'POSTBOOT_REFILL_REQUEST')


def wait_for_legacy_workers(helper, root, director):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            read_idle_workers(helper, root, director)
            return
        except (OSError, KeyError, ValueError, TypeError, RuntimeError, helper.Hold):
            time.sleep(.5)
    require(False, 'ROLLBACK_WORKERS_NOT_VERIFIED')


def rollout(helper, root, candidate, request, source):
    current = helper.preimages(root, OLD)
    config = json.loads(current[CONFIG])
    pins = config.get('module_pins') or {}
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('instance_id') == 60509551 and config.get('owner_authorized') is True
            and config.get('mode') == 'NORMAL' and config.get('target') == 3
            and config.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and config.get('global_worker_cap', 3) == 3
            and config.get('policy_id') == 'NOX_WEB_WEIGHTS_V06'
            and pins.get(Path(REFILL).name) == OLD[REFILL]
            and pins.get(Path(DIRECTOR).name) == DIRECTOR_SHA, 'CONFIG_SCOPE')
    require(sha(helper.read_regular(root / DIRECTOR)) == DIRECTOR_SHA, 'DIRECTOR_SOURCE')
    old_module = load_module('_refill_rollout_legacy', current[REFILL])
    module = load_module('_refill_rollout_candidate', candidate)
    updated = copy.deepcopy(config)
    updated['module_pins'][Path(REFILL).name] = REFILL_SHA
    changes = {REFILL: candidate, CONFIG: encode(updated)}
    lock = root / 'state/owner_maintenance.lock'
    require(not any(path.is_symlink() for path in (lock, *lock.parents)), 'LOCK_PATH')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    applied, owned = [], None
    stop_attempted, candidate_start_attempted, released = False, False, False
    receipt = {'schema': 'NOX_OWNER_REFILL_CONTRACT_ROLLOUT_V1', 'request': request,
               'source_sha': source, 'state': 'PREFLIGHT', 'original_295_accepted': 0}
    try:
        acquire_lease(fd, lock, helper, root)
        observed = helper.expected_processes(EXPECTED_PROCESSES)
        old = observed['director']
        require(helper.supervisor('status') == {'state': 'RUNNING', 'pid': old['pid']},
                'DIRECTOR_NOT_RUNNING')
        children = helper.descendant_snapshot(old['pid'])
        protected = service_guard(helper)
        baseline, queue_sha = read_queue(helper, root)
        compared, manifest = verify_legacy_contracts(helper, root, config, old_module, module, baseline)
        headroom(helper, config)
        backup = root / 'state/dispatcher/refill_contract_rollouts' / request
        require(not any(path.is_symlink() for path in (backup, *backup.parents)), 'BACKUP_SCOPE')
        backup.mkdir(parents=True, mode=0o700)
        for rel, raw in current.items():
            saved = backup / Path(rel).name
            helper.atomic(saved, raw)
            require(helper.read_regular(saved) == raw, 'BACKUP_READBACK')
        helper.atomic(backup / 'queue_sha256.txt', (queue_sha + '\n').encode())
        require(helper.preimages(root, OLD) == current and service_guard(helper) == protected
                and helper.expected_processes(EXPECTED_PROCESSES) == observed
                and read_queue(helper, root)[1] == queue_sha, 'PRESTOP_DRIFT')
        maintenance_lease(fd, lock, helper, root)
        old_status = read_idle_workers(helper, root, old)
        require({(worker['pid'], worker['process_starttime']) for worker in old_status['workers']}
                == {(row['pid'], row['start_ticks']) for row in EXPECTED_PROCESSES['expected_workers']},
                'PRESTOP_WORKER_IDENTITY')
        receipt['raw_headroom_bytes'] = headroom(helper, config)
        stop_attempted = True
        helper.stop_checked()
        helper.wait_previous_descendants_stopped(children, timeout=10)
        require(read_queue(helper, root)[1] == queue_sha and service_guard(helper) == protected,
                'STOPPED_QUEUE_OR_SERVING_DRIFT')
        maintenance_lease(fd, lock, helper, root)
        headroom(helper, config)
        applied = helper.apply_transaction(root, changes, current)
        maintenance_lease(fd, lock, helper, root)
        require(read_queue(helper, root)[1] == queue_sha and service_guard(helper) == protected,
                'PRESTART_QUEUE_OR_SERVING_DRIFT')
        receipt['prestart_headroom_bytes'] = headroom(helper, config)
        candidate_start_attempted = True
        owned = start_owned_director(helper)
        fcntl.flock(fd, fcntl.LOCK_UN)
        released = True
        request_id = wait_for_request(helper, root, module, owned, manifest,
                                      config['systemic_relay']['sha256'], baseline)
        require(helper.stop_clear(root) and service_guard(helper) == protected
                and all(helper.read_regular(root / rel) == raw for rel, raw in changes.items())
                and sha(helper.read_regular(root / DIRECTOR)) == DIRECTOR_SHA, 'POSTBOOT_DRIFT')
        receipt.update(state='REFILL_CONTRACT_RUNTIME_INSTALLED', new_director=owned,
                       old_director=old, worker_count=3, legacy_contracts_checked=compared,
                       refill_request_id=request_id, installed_refill_sha256=REFILL_SHA,
                       installed_config_sha256=sha(changes[CONFIG]))
    except BaseException as failure:
        reason = str(failure)
        receipt['state'] = reason if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', reason) else (
            'HOLD_REFILL_CONTRACT_ROLLOUT_' + type(failure).__name__.upper())
        try:
            if stop_attempted:
                if released:
                    acquire_lease(fd, lock, helper, root)
                maintenance_lease(fd, lock, helper, root)
                read_queue(helper, root)
                require(service_guard(helper) == protected, 'RECOVERY_SERVING_DRIFT')
                present = helper.supervisor('status')
                recover_director(helper, present, owned, old, children, candidate_start_attempted)
                helper.rollback_transaction(root, changes, current, applied)
                require(helper.preimages(root, OLD) == current, 'ROLLBACK_PREIMAGES')
                receipt['rollback_preimages_verified'] = True
                receipt['restored_director'] = start_owned_director(helper)
                fcntl.flock(fd, fcntl.LOCK_UN)
                wait_for_legacy_workers(helper, root, receipt['restored_director'])
                receipt['rollback_verified'] = True
        except BaseException as recovery:
            reason = str(recovery)
            receipt['recovery'] = reason if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', reason) else (
                'HOLD_REFILL_CONTRACT_RECOVERY_' + type(recovery).__name__.upper())
        print('NOX_MAINT_REFLEX_RESTORE=' + encode(receipt).decode(), flush=True)
        raise
    finally:
        os.close(fd)
    print('NOX_MAINT_REFLEX_RESTORE=' + encode(receipt).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return receipt


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[1-9][0-9]{0,23}', request)
            and re.fullmatch('[0-9a-f]{40}', source), 'OWNER_CONTEXT')
    helper, candidate = decode_bundle(BUNDLE)
    return rollout(helper, ROOT, candidate, request, source)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        state = str(exc)
        if not re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', state):
            state = 'HOLD_REFILL_CONTRACT_ROLLOUT_' + type(exc).__name__.upper()
        print('NOX_MAINT_REFLEX_RESTORE=' + encode({'state': state}).decode(), flush=True)
        raise SystemExit(2)
