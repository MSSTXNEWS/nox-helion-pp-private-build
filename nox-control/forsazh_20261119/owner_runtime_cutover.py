"""Guarded dispatcher cutover engine for the exact private handoff.

This module has no command-line execution path. An authenticated owner driver
must supply exact Supervisor lifecycle observations and the local model probe.
It never controls the model, holder, proxy or web processes.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import fcntl
import http.client
import json
from pathlib import Path
import os
import re
import stat
import time

import systemic_transaction_helpers as files


CONFIG = 'config/owner_native_subagents.json'
OWNER_LOCK = 'state/owner_maintenance.lock'
BACKUPS = 'state/dispatcher/runtime-cutover'
SCRIPTS = tuple('scripts/' + name for name in (
    'owner_autonomy_pool.py', 'owner_project_native.py', 'owner_subagent_dispatcher.py',
    'owner_subagent_processes.py', 'owner_subagent_instruction_truth.py', 'owner_systemic_refill.py'))
PROJECT_EXECUTOR = 'scripts/owner_project_executor.py'
FORSAZH_SCRIPTS = tuple('scripts/' + name for name in (
    'owner_autonomy_pool.py', 'owner_project_native.py', 'owner_subagent_dispatcher.py',
    'owner_subagent_instruction_truth.py')) + (PROJECT_EXECUTOR,)
NORMAL_ROLES = frozenset(('runtime', 'memory', 'weights'))
FORSAZH_ROLES = NORMAL_ROLES | frozenset(('runtime-2', 'memory-2', 'weights-2'))
PROTECTED = {'model', 'engram_holder', 'proxy', 'web'}
OWNER_FLAGS = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
               'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
SHA = re.compile(r'[a-f0-9]{64}')
ID = re.compile(r'[A-Za-z0-9._-]{1,128}')
TERMINAL = {'done', 'completed', 'failed', 'cancelled', 'canceled'}
LOAD_WAIT_SECONDS = 12
RAW_FORSAZH_HEADROOM = 2 * 1024**3


class Hold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Hold('HOLD_RUNTIME_CUTOVER_' + code)


@dataclass(frozen=True)
class Process:
    pid: int
    start_ticks: int

    def valid(self):
        return type(self.pid) is int and self.pid > 1 and type(self.start_ticks) is int and self.start_ticks > 0


@dataclass(frozen=True)
class Observation:
    """Only the owner driver can obtain these from the live process/control plane."""
    authenticated: bool
    boot_id: str
    sampled_at: float
    director_state: str
    director: Process | None
    protected: dict[str, Process]
    direct_model_health: bool


def observe(driver, boot_id, *, require_model_health=True):
    value = driver.observe()
    require(isinstance(value, Observation) and value.authenticated is True
            and value.boot_id == boot_id and 0 <= time.time()-value.sampled_at <= 15,
            'OWNER_OR_OBSERVATION')
    require(set(value.protected) == PROTECTED and all(
            isinstance(item, Process) and item.valid() for item in value.protected.values()),
            'PROTECTED_PROCESS_IDENTITY')
    require(len({item.pid for item in value.protected.values()}) == len(PROTECTED)
            and (not require_model_health or value.direct_model_health is True), 'PROTECTED_MODEL_HEALTH')
    if value.director_state == 'RUNNING':
        require(isinstance(value.director, Process) and value.director.valid()
                and value.director.pid not in {item.pid for item in value.protected.values()}, 'DIRECTOR_IDENTITY')
    else:
        require(value.director_state == 'STOPPED' and value.director is None, 'DIRECTOR_UNCERTAIN')
    return value


def require_stop_clear(root):
    paths = [root / name for name in OWNER_FLAGS]
    if root == files.ROOT:
        paths.append(Path('/workspace/NOX_STOP'))
    for path in paths:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise Hold('HOLD_RUNTIME_CUTOVER_OWNER_STOP')


def _stamp(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink


@contextmanager
def owner_fence(root):
    path = root / OWNER_LOCK
    require(path.is_absolute() and not any(parent.is_symlink() for parent in (path, *path.parents)), 'LOCK_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022 and info.st_nlink == 1, 'LOCK_FILE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Hold('HOLD_RUNTIME_CUTOVER_OWNER_BUSY') from None

        def check(*, stop_clear=True):
            require(_stamp(path.lstat()) == _stamp(info), 'OWNER_LOCK_CHANGED')
            if stop_clear:
                require_stop_clear(root)

        check()
        yield check
    finally:
        os.close(fd)


def queue_witness(root):
    tasks = json.loads(files.read_regular(root / files.STATE, 16*1024*1024))['tasks']
    require(type(tasks) is dict, 'QUEUE_SCHEMA')
    for row in tasks.values():
        require(type(row) is dict and isinstance(row.get('status'), str), 'QUEUE_ROW_SCHEMA')
        lease = row.get('native_worker_lease')
        require(lease is None or (isinstance(lease, dict) and lease.get('phase') == 'SETTLED'),
                'UNSETTLED_WORKER_LEASE')
        require(row['status'] not in ('running', 'admitted')
                and (row['status'] in TERMINAL or not any(row.get(key) for key in
                     ('claim', 'owner_claim', 'native_pool_recovery'))), 'QUEUE_NOT_QUIESCENT')
    return files.digest(files.encoded(tasks))


def require_forsazh_admission(root):
    current = int(files.read_regular(Path('/sys/fs/cgroup/memory.current'), 128))
    maximum = int(files.read_regular(Path('/sys/fs/cgroup/memory.max'), 128))
    require(maximum > 0 and current >= 0 and maximum - current >= RAW_FORSAZH_HEADROOM,
            'FORSAZH_RAW_CGROUP_HEADROOM')
    with closing(http.client.HTTPConnection('127.0.0.1', 8098, timeout=1)) as connection:
        try:
            connection.request('GET', '/slots', headers={'Connection': 'close'})
            reply = connection.getresponse()
            raw = reply.read(65537)
            require(reply.status == 200 and len(raw) <= 65536, 'FORSAZH_CHAT_SLOTS_UNKNOWN')
            slots = json.loads(raw)
        except (OSError, ValueError, http.client.HTTPException) as failure:
            raise Hold('HOLD_RUNTIME_CUTOVER_FORSAZH_CHAT_SLOTS_UNKNOWN') from failure
    require(isinstance(slots, list) and 1 <= len(slots) <= 64, 'FORSAZH_CHAT_SLOTS_UNKNOWN')
    for row in slots:
        flags = [row[key] for key in ('processing', 'is_processing') if key in row] if isinstance(row, dict) else []
        require(flags and all(flag is False for flag in flags), 'FORSAZH_CHAT_BUSY_OR_UNKNOWN')
    for path in (root/'state/chat_active', root/'state/priority/LAST_OWNER_CHAT'):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and info.st_nlink == 1 and not info.st_mode & 0o002
                and time.time() - info.st_mtime >= 3, 'FORSAZH_CHAT_BUSY_OR_UNKNOWN')


def stage(root, spec, sources, priority):
    """Read-only. Verify all preimages, compile all postimages and compose config."""
    target_mode = spec.get('target_mode', 'NORMAL')
    require(target_mode in ('NORMAL', 'FORSAZH'), 'TARGET_MODE')
    boost = target_mode == 'FORSAZH'
    scripts = FORSAZH_SCRIPTS if boost else SCRIPTS
    old_pins = spec['runtime_preimage_sha256']
    new_pins = spec['runtime_candidate_sha256']
    require(set(old_pins) == set(new_pins) == set(sources) == set(scripts), 'FILE_SCOPE')
    require(all(isinstance(pin, str) and SHA.fullmatch(pin)
                for pin in (*old_pins.values(), *new_pins.values(), spec['config_preimage_sha256'])), 'SHA_FORMAT')
    raw_config = files.read_regular(root / CONFIG, 262144)
    require(files.digest(raw_config) == spec['config_preimage_sha256'], 'CONFIG_PREIMAGE')
    cfg = json.loads(raw_config)
    require(cfg.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1' and cfg.get('instance_id') == 60509551
            and cfg.get('owner_authorized') is True and cfg.get('mode') == 'NORMAL' and cfg.get('target') == 3,
            'CONFIG_SCOPE')
    require(isinstance(cfg.get('module_pins'), dict)
            and all(cfg['module_pins'].get(Path(path).name) == pin for path, pin in old_pins.items()), 'CONFIG_MODULE_PINS')
    if boost:
        project = cfg.get('project_executor')
        source_pins = project.get('source_pins') if isinstance(project, dict) else None
        name = Path(PROJECT_EXECUTOR).name
        require(cfg.get('execution_mode') == 'NATIVE_PROJECT_V1'
                and cfg.get('global_worker_cap', 3) == 3, 'PROJECT_WORKER_CAP_PREIMAGE')
        require(isinstance(source_pins, dict) and project.get('max_workers') == 3
                and source_pins.get(name) == old_pins[PROJECT_EXECUTOR], 'PROJECT_EXECUTOR_PREIMAGE')
        source_pins[name] = new_pins[PROJECT_EXECUTOR]
        project['max_workers'] = 6
        cfg.update(mode='FORSAZH', target=6, global_worker_cap=6)
    require(isinstance(priority, bytes) and files.digest(priority) == spec['priority_fragment_sha256'],
            'PRIORITY_FRAGMENT_PIN')
    parsed = json.loads(priority)
    ids = parsed.get('owner_priority_parent_task_ids')
    require(set(parsed) == {'owner_priority_parent_task_ids'} and type(ids) is list
            and len(ids) == 295 and all(isinstance(item, str) and ID.fullmatch(item) for item in ids)
            and len(set(ids)) == len(ids), 'PRIORITY_FRAGMENT_SHAPE')
    before, after = {}, {}
    for path in scripts:
        old = files.read_regular(root / path)
        new = sources[path]
        require(files.digest(old) == old_pins[path] and isinstance(new, bytes)
                and files.digest(new) == new_pins[path], 'EXACT_MODULE_PINS')
        compile(new, path, 'exec', dont_inherit=True)
        before[path], after[path] = old, new
    wrapper = after['scripts/owner_subagent_instruction_truth.py']
    callback = new_pins['scripts/owner_subagent_dispatcher.py']
    require(wrapper.count(f"CALLBACK_SHA = '{callback}'".encode()) == 1, 'WRAPPER_CALLBACK_PIN')
    cfg['module_pins'].update({Path(path).name: pin for path, pin in new_pins.items()})
    previous = old_pins['scripts/owner_subagent_dispatcher.py']
    for key in ('historical_project_source_sha256', 'historical_leaf_source_sha256'):
        pins = cfg.setdefault(key, [])
        require(type(pins) is list and all(isinstance(pin, str) and SHA.fullmatch(pin) for pin in pins)
                and len(pins) == len(set(pins)), 'HISTORY_PINS')
        if previous not in pins:
            pins.append(previous)
        require(len(pins) <= 32, 'HISTORY_PIN_CAPACITY')
    cfg['owner_priority_parent_task_ids'] = ids
    if not boost:
        cfg['idle_worker_release_below_bytes'] = 8 * 1024**3
    before[CONFIG], after[CONFIG] = raw_config, files.encoded(cfg)
    modes = {}
    for path in before:
        info = (root/path).lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_nlink == 1 and not info.st_mode & 0o7022, 'MODULE_METADATA')
        modes[path] = stat.S_IMODE(info.st_mode)
    require(modes[CONFIG] == 0o600, 'CONFIG_MODE')
    return before, after, modes


def verify_loaded(root, director, started_at, *, mode='NORMAL', verify_workers=None):
    """Validate the fresh loading generation while the exclusive lease is held."""
    require(mode in ('NORMAL', 'FORSAZH'), 'TARGET_MODE')
    roles = FORSAZH_ROLES if mode == 'FORSAZH' else NORMAL_ROLES
    target = len(roles)
    status = json.loads(files.read_regular(root / files.STATUS, 2*1024*1024)).get('native_subexecutors') or {}
    identity = status.get('director', {})
    at = status.get('observed_at', 0)
    require((identity.get('pid'), identity.get('process_starttime')) == (director.pid, director.start_ticks)
            and type(at) in (int, float) and started_at <= at <= time.time() and time.time()-at <= 15,
            'LOADED_STATUS_NOT_FRESH')
    require(status.get('mode') == mode and status.get('target') == target, 'LOADED_STATUS_SCOPE')
    workers = status.get('workers')
    require(isinstance(workers, list) and len(workers) in (0, target), 'LOADED_WORKER_COUNT')
    require(verify_workers is None or len(workers) == target, 'FULL_WORKER_COUNT_UNVERIFIED')
    if not workers:
        last = status.get('last_admission') or {}
        require(last.get('jobs_started') == 0 and last.get('state') in (
                'HOLD_OWNER_STOP_OR_MAINTENANCE', 'HOLD_MAINTENANCE_IDLE_POOL_RETAINED',
                'NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED', 'NATIVE_QUEUE_DEPENDENCY_WAIT',
                'NATIVE_QUEUE_IDLE'), 'IDLE_WORKER_STATE_UNVERIFIED')
    else:
        require(all(isinstance(row, dict) for row in workers)
                and {row['role'] for row in workers} == roles
                and len({row['pid'] for row in workers}) == target
                and all(row.get('ppid') == director.pid and row.get('native_pid_verified') is True
                        and type(row.get('pid')) is int and row['pid'] > 1
                        and type(row.get('process_starttime')) is int and row['process_starttime'] > 0
                        and row.get('state') == 'RUNNING'
                        and (verify_workers is not None or row.get('current_task') is None)
                        for row in workers), 'NATIVE_WORKER_IDENTITY')
        if verify_workers is not None:
            generations = tuple(Process(row['pid'], row['process_starttime']) for row in workers)
            require(verify_workers(director, generations) is True, 'NATIVE_WORKER_KERNEL_READBACK')
    return len(workers)


def verify_forsazh(root, driver, boot_id, receipt):
    """Independently prove all six worker PIDs after releasing the write fence."""
    require(receipt['configured_mode'] == 'FORSAZH', 'TARGET_MODE')
    expected = Process(receipt['director_pid'], receipt['director_start_ticks'])
    current = observe(driver, boot_id)
    require(current.director == expected, 'POST_RELEASE_DIRECTOR_CHANGED')
    count = verify_loaded(root, expected, receipt['started_at'], mode='FORSAZH',
                          verify_workers=driver.verify_worker_generations)
    require(observe(driver, boot_id).director == expected, 'POST_RELEASE_DIRECTOR_CHANGED')
    return count


def wait_loaded(root, driver, boot_id, director, protected, queue, started_at, check, *, mode='NORMAL'):
    deadline = time.monotonic() + LOAD_WAIT_SECONDS
    while True:
        check()
        current = observe(driver, boot_id)
        require(current.director == director and current.protected == protected
                and queue_witness(root) == queue, 'LOAD_GENERATION_OR_QUEUE_DRIFT')
        try:
            return verify_loaded(root, director, started_at, mode=mode)
        except FileNotFoundError:
            require(time.monotonic() < deadline, 'LOADED_STATUS_MISSING')
        except Hold as failed:
            if str(failed) not in ('HOLD_RUNTIME_CUTOVER_LOADED_STATUS_NOT_FRESH',
                                   'HOLD_RUNTIME_CUTOVER_IDLE_WORKER_STATE_UNVERIFIED') or time.monotonic() >= deadline:
                raise
        time.sleep(0.25)


def _record(backup, state, **details):
    files.atomic(backup / 'transaction.json', files.encoded({'state': state, **details}))


def _apply(root, before, after, modes, check):
    for path in before:
        check()
        require(files.read_regular(root / path) == before[path]
                and stat.S_IMODE((root/path).lstat().st_mode) == modes[path], 'FILE_CHANGED_BEFORE_WRITE')
        files.atomic(root / path, after[path], modes[path])
        require(files.read_regular(root / path) == after[path], 'POSTIMAGE_READBACK')


def _restore(root, before, after, modes, check):
    current = {path: files.read_regular(root / path) for path in before}
    require(all(raw in (before[path], after[path]) for path, raw in current.items()), 'FOREIGN_FILE_CHANGE')
    for path in before:
        check(stop_clear=False)  # Restoring original bytes does not start work under STOP.
        require(files.read_regular(root / path) == current[path]
                and stat.S_IMODE((root/path).lstat().st_mode) == modes[path], 'ROLLBACK_FILE_CHANGED')
        if current[path] != before[path]:
            files.atomic(root / path, before[path], modes[path])
        require(files.read_regular(root / path) == before[path], 'ROLLBACK_READBACK')


def cutover(root, spec, sources, priority, driver, *, boot_id, request_id):
    """Transaction under verified owner EX lease. The driver owns stop/start RPC.

    Driver stop(expected, check=...) and start(check=...) must use the exact authenticated
    Supervisor program and return only after generation-qualified readback.
    An ambiguous start never licenses stopping an unidentified process.
    """
    require(isinstance(request_id, str) and re.fullmatch(r'[0-9]{1,24}', request_id), 'REQUEST_ID')
    driver.validate_transaction(root, spec, boot_id, request_id)
    with owner_fence(root) as check:
        before, after, modes = stage(root, spec, sources, priority)
        mode = spec.get('target_mode', 'NORMAL')
        original = observe(driver, boot_id)
        require(original.director_state == 'RUNNING', 'INITIAL_DIRECTOR')
        if mode == 'FORSAZH':
            require_forsazh_admission(root)
        queue = queue_witness(root)
        backup = root / BACKUPS / request_id
        require(not any(path.is_symlink() for path in (backup, *backup.parents)), 'BACKUP_PATH')
        backup.mkdir(parents=True, mode=0o700, exist_ok=False)
        for path in before:
            files.atomic(backup / 'before' / path, before[path])
            files.atomic(backup / 'candidate' / path, after[path])
        require(all(files.read_regular(backup/'before'/path) == raw for path, raw in before.items())
                and all(files.read_regular(backup/'candidate'/path) == raw for path, raw in after.items()), 'BACKUP_READBACK')
        manifest = files.encoded(dict(queue_sha256=queue,
                    before_sha256={path: files.digest(raw) for path, raw in before.items()},
                    candidate_sha256={path: files.digest(raw) for path, raw in after.items()}, modes=modes))
        files.atomic(backup / 'files.json', manifest)
        require(files.read_regular(backup / 'files.json') == manifest, 'BACKUP_MANIFEST_READBACK')
        _record(backup, 'BACKUP_VERIFIED', queue_sha256=queue, backup_manifest_sha256=files.digest(manifest))

        owned, write_intent = None, False
        try:
            check()
            observed = observe(driver, boot_id)
            require(observed.director == original.director and observed.protected == original.protected
                    and queue_witness(root) == queue, 'PRE_STOP_DRIFT')
            if mode == 'FORSAZH':
                require_forsazh_admission(root)
            driver.stop(original.director, check=check)
            stopped = observe(driver, boot_id)
            require(stopped.director_state == 'STOPPED' and stopped.protected == original.protected
                    and queue_witness(root) == queue, 'SAFE_STOP_UNVERIFIED')
            _record(backup, 'WRITE_INTENT', queue_sha256=queue)
            write_intent = True
            _apply(root, before, after, modes, check)
            check()
            started_at = time.time()
            owned = driver.start(check=check)
            require(isinstance(owned, Process) and owned.valid() and owned != original.director, 'START_IDENTITY')
            workers = wait_loaded(root, driver, boot_id, owned, original.protected, queue,
                                  started_at, check, mode=mode)
            check()
            require(all(files.read_regular(root/path) == raw for path, raw in after.items()), 'FINAL_POSTIMAGE_DRIFT')
            receipt = dict(workers=workers, configured_mode=mode, director_pid=owned.pid,
                           director_start_ticks=owned.start_ticks, started_at=started_at,
                           queue_sha256=queue, model_restart_verified=False,
                           chat_end_to_end_verified=False, original_tasks_accepted=0)
            _record(backup, 'DISPATCHER_LOADED_UNDER_OWNER_FENCE', **receipt)
            return {**receipt, 'state':'DISPATCHER_LOADED_UNDER_OWNER_FENCE'}
        except BaseException:
            try:
                check(stop_clear=False)
                current = observe(driver, boot_id, require_model_health=False)
                require(current.protected == original.protected, 'ROLLBACK_PROTECTED_DRIFT')
                if current.director_state == 'RUNNING' and current.director == owned:
                    driver.stop(owned, check=check, rollback=True)
                    current = observe(driver, boot_id, require_model_health=False)
                if write_intent:
                    require(current.director_state == 'STOPPED' and current.protected == original.protected,
                            'ROLLBACK_DIRECTOR_NOT_STOPPED')
                    _restore(root, before, after, modes, check)
                if current.director_state == 'STOPPED':
                    if current.direct_model_health is not True:
                        _record(backup, 'PREIMAGE_RESTORED_MODEL_HEALTH_PENDING', queue_sha256=queue)
                    else:
                        check()  # Existing STOP remains authoritative for any start.
                        require(queue_witness(root) == queue
                                and all(files.read_regular(root/path) == raw for path, raw in before.items()),
                                'OLD_START_PREIMAGE_DRIFT')
                        old_start_at = time.time()
                        restored = driver.start(check=check, rollback=True)
                        observed = observe(driver, boot_id)
                        require(isinstance(restored, Process) and observed.director == restored
                                and observed.protected == original.protected, 'ROLLBACK_START_UNVERIFIED')
                        wait_loaded(root, driver, boot_id, restored, original.protected, queue, old_start_at, check)
                        _record(backup, 'PREIMAGE_RESTORED_BEFORE_RELEASE', queue_sha256=queue)
                else:
                    require(not write_intent and current.director == original.director, 'ROLLBACK_FOREIGN_DIRECTOR')
                    _record(backup, 'UNCHANGED_DIRECTOR', queue_sha256=queue)
            except (Exception, KeyboardInterrupt) as failed:
                _record(backup, 'RECOVERY_REQUIRED_BACKUPS_RETAINED', failure=type(failed).__name__)
            raise
