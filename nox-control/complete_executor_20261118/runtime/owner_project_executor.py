"""Reviewed project edits for the existing NOX worker pool.

Workers construct an exact source snapshot and run fixed tests in confinement.
The native parent alone integrates a prepared result under its current queue
claim/STOP/writer lease. Journals are durable before every shared-source write.
This module owns no scheduler, service, queue, S03 connection or model endpoint.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import sysconfig
import time

SCHEMA = 'NOX_PROJECT_WORK_PLAN_V1'
CONFIG_SCHEMA = 'NOX_PROJECT_EXECUTOR_CONFIG_V1'
CONTRACT_SCHEMA = 'NOX_PROJECT_PLANNER_CONTRACT_V1'
EVIDENCE_SCHEMA = 'NOX_PROJECT_EXECUTION_EVIDENCE_V1'
PROJECT_HANDLER = 'owner_native_project_work'
PROJECT_MODE = 'NATIVE_PROJECT_V1'
QUEUE_IDS = ('Q1_RUNTIME_CHAT', 'Q2_MEMORY_KNOWLEDGE',
             'Q3_TRAINING_WEIGHTS', 'Q4_INTEGRATION_ACCEPTANCE')
SHA = re.compile(r'^[0-9a-f]{64}$')
ID = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
CLAIM = re.compile(r'^[0-9a-f]{24}$')
MODULE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$')
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
SOURCE_FILES = ('owner_project_executor.py', 'owner_project_test_runner.py')
SCOPES = ('SOURCE_PATCH_TESTED', 'SOURCE_IMPLEMENTATION_TESTED', 'SOURCE_REQUIREMENT_VERIFIED')
TERMINAL_WITHOUT_CHANGES = ('FAILED_TESTS', 'BLOCKED_SANDBOX', 'BLOCKED_SOURCE_CHANGED',
                            'BLOCKED_PLAN', 'BLOCKED_PLANNER', 'STOPPED', 'ROLLED_BACK')


class ProjectHold(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def relpath(value):
    if (not isinstance(value, str) or not value or len(value) > 240
            or '\\' in value or '\x00' in value or value.startswith('/')
            or any(piece in ('', '.', '..') for piece in value.split('/'))):
        raise ProjectHold('HOLD_PROJECT_RELATIVE_PATH')
    path = PurePosixPath(value)
    if any(piece.startswith('.') for piece in path.parts):
        raise ProjectHold('HOLD_PROJECT_HIDDEN_PATH')
    return value


def plain(path):
    path = Path(path)
    if not path.is_absolute() or any(item.is_symlink() for item in (*path.parents, path)):
        raise ProjectHold('HOLD_PROJECT_ABSOLUTE_PATH')
    return path


def read(path, limit=MAX_FILE_BYTES):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ProjectHold('HOLD_PROJECT_FILE_SIZE_OR_TYPE')
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if (len(raw) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ProjectHold('HOLD_PROJECT_FILE_CHANGED_DURING_READ')
    return raw


def document(path):
    value = json.loads(read(path))
    if not isinstance(value, dict):
        raise ProjectHold('HOLD_PROJECT_DOCUMENT')
    return value


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_atomic(path, raw, mode=0o600):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    plain(path.parent)
    temp = path.with_name(path.name + '.tmp-' + os.urandom(8).hex())
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _allowed(path, patterns):
    return any(path == item or (item.endswith('/') and path.startswith(item)) for item in patterns)


def validate_config(config):
    if (not isinstance(config, dict) or config.get('schema') != CONFIG_SCHEMA
            or config.get('enabled') is not True or config.get('max_workers') != 3):
        raise ProjectHold('HOLD_PROJECT_CONFIG')
    for key in ('package_root', 'state_root'):
        plain(config[key])
    roots = config.get('roots')
    if not isinstance(roots, dict) or not roots:
        raise ProjectHold('HOLD_PROJECT_ROOTS')
    for name, root in roots.items():
        if (not ID.fullmatch(name) or not isinstance(root, dict)
                or root.get('integration_kind') != 'SOURCE_WORKSPACE'
                or not isinstance(root.get('allowed_paths'), list) or not root['allowed_paths']):
            raise ProjectHold('HOLD_PROJECT_ROOT_POLICY')
        plain(root['path'])
        for item in root['allowed_paths']:
            relpath(item[:-1] if item.endswith('/') else item)
        for path in root.get('deny_paths', []):
            relpath(path[:-1] if path.endswith('/') else path)
    sandbox = config.get('sandbox') or {}
    if (sandbox.get('backend') not in ('bwrap_seccomp', 'chroot_seccomp')
            or type(sandbox.get('uid')) is not int or not 1 <= sandbox['uid'] <= 65534
            or type(sandbox.get('gid')) is not int or not 1 <= sandbox['gid'] <= 65534
            or type(sandbox.get('memory_mb')) is not int or not 96 <= sandbox['memory_mb'] <= 512):
        raise ProjectHold('HOLD_PROJECT_SANDBOX_CONFIG')
    python = plain(sandbox['python'])
    if digest(read(python, 32 * 1024 * 1024)) != sandbox.get('python_sha256'):
        raise ProjectHold('HOLD_PROJECT_PYTHON_SOURCE')
    if sandbox['backend'] == 'bwrap_seccomp':
        if digest(read(plain(sandbox['bwrap']), 8 * 1024 * 1024)) != sandbox.get('bwrap_sha256'):
            raise ProjectHold('HOLD_PROJECT_BWRAP_SOURCE')
    pins = config.get('source_pins')
    if not isinstance(pins, dict) or set(pins) != set(SOURCE_FILES):
        raise ProjectHold('HOLD_PROJECT_EXECUTOR_PINS')
    for name in SOURCE_FILES:
        if digest(read(Path(__file__).parent / name)) != pins.get(name):
            raise ProjectHold('HOLD_PROJECT_EXECUTOR_SOURCE_CHANGED')
    return config


def _verification(value):
    if (not isinstance(value, dict)
            or set(value) - {'kind', 'modules', 'min_tests', 'timeout_sec', 'policy_id'}
            or value.get('kind') != 'python_unittest'
            or not isinstance(value.get('modules'), list) or not 1 <= len(value['modules']) <= 16
            or any(not isinstance(name, str) or not MODULE.fullmatch(name) for name in value['modules'])
            or len(set(value['modules'])) != len(value['modules'])
            or type(value.get('min_tests')) is not int or not 1 <= value['min_tests'] <= 10000
            or type(value.get('timeout_sec')) is not int or not 1 <= value['timeout_sec'] <= 120):
        raise ProjectHold('HOLD_PROJECT_VERIFICATION_POLICY')


def validate_plan(plan, config, *, approved_contract_sha256=None):
    fields = {'schema', 'task_id', 'parent_task_id', 'queue_id', 'root_id', 'operation',
              'review_origin', 'context', 'files', 'verification', 'acceptance_scope',
              'original_task_accepted'}
    if (not isinstance(plan, dict) or not fields <= set(plan)
            or set(plan) - fields - {'spec_sha256', 'contract_sha256'}
            or plan.get('schema') != SCHEMA or plan.get('operation') != 'apply_reviewed_files'
            or not ID.fullmatch(str(plan.get('task_id', '')))
            or not ID.fullmatch(str(plan.get('parent_task_id', '')))
            or not plan['task_id'].startswith(plan['parent_task_id'] + '.')
            or plan.get('queue_id') not in QUEUE_IDS or plan.get('root_id') not in config['roots']
            or plan.get('review_origin') not in ('OWNER_REVIEWED', 'MODEL_CANDIDATE')
            or plan.get('acceptance_scope') not in SCOPES
            or plan.get('original_task_accepted') is not False):
        raise ProjectHold('HOLD_PROJECT_PLAN_SCOPE')
    _verification(plan['verification'])
    root = config['roots'][plan['root_id']]
    context = plan['context']
    files = plan['files']
    if (not isinstance(context, list) or not 1 <= len(context) <= 128
            or not isinstance(files, list) or not 1 <= len(files) <= 32):
        raise ProjectHold('HOLD_PROJECT_PLAN_BOUNDS')
    old = {}
    changes = {}
    for row in context:
        if (not isinstance(row, dict) or set(row) != {'path', 'sha256'}
                or not SHA.fullmatch(str(row.get('sha256', '')))):
            raise ProjectHold('HOLD_PROJECT_CONTEXT_SCHEMA')
        path = relpath(row['path'])
        if path in old:
            raise ProjectHold('HOLD_PROJECT_DUPLICATE_CONTEXT')
        old[path] = row['sha256']
    for row in files:
        if (not isinstance(row, dict)
                or set(row) != {'path', 'before_sha256', 'after_sha256', 'payload_sha256'}
                or not SHA.fullmatch(str(row.get('after_sha256', '')))
                or row['after_sha256'] != row.get('payload_sha256')
                or (row.get('before_sha256') is not None
                    and not SHA.fullmatch(str(row['before_sha256'])))):
            raise ProjectHold('HOLD_PROJECT_FILE_PLAN_SCHEMA')
        path = relpath(row['path'])
        if (path in changes or row['before_sha256'] == row['after_sha256']
                or (row['before_sha256'] is not None and old.get(path) != row['before_sha256'])
                or (row['before_sha256'] is None and path in old)):
            raise ProjectHold('HOLD_PROJECT_PREIMAGE_OR_NOOP')
        changes[path] = row
    for path in old.keys() | changes.keys():
        if not _allowed(path, root['allowed_paths']) or _allowed(path, root.get('deny_paths', [])):
            raise ProjectHold('HOLD_PROJECT_PATH_POLICY')
    for name in plan['verification']['modules']:
        path = name.replace('.', '/') + '.py'
        if path not in old and path not in changes:
            raise ProjectHold('HOLD_PROJECT_TEST_NOT_PINNED')
    if plan['review_origin'] == 'MODEL_CANDIDATE':
        sha = plan.get('contract_sha256')
        if (not SHA.fullmatch(str(sha)) or sha != approved_contract_sha256):
            raise ProjectHold('HOLD_PROJECT_UNAPPROVED_MODEL_CONTRACT')
        raw = read(Path(config['package_root']) / 'contracts' / (sha + '.json'))
        if digest(raw) != sha:
            raise ProjectHold('HOLD_PROJECT_CONTRACT_SOURCE')
        contract = json.loads(raw)
        shared = ('task_id', 'parent_task_id', 'queue_id', 'root_id', 'context',
                  'verification', 'acceptance_scope')
        if (not isinstance(contract, dict) or contract.get('schema') != CONTRACT_SCHEMA
                or any(plan.get(key) != contract.get(key) for key in shared)):
            raise ProjectHold('HOLD_PROJECT_MODEL_CONTRACT_CHANGED')
        editable = contract.get('editable_paths', [])
        new = contract.get('allowed_new_paths', [])
        for path, row in changes.items():
            if path not in (new if row['before_sha256'] is None else editable):
                raise ProjectHold('HOLD_PROJECT_MODEL_EDIT_SCOPE')
        trusted_tests = {name.replace('.', '/') + '.py' for name in plan['verification']['modules']}
        trusted_tests.update(contract.get('protected_paths', []))
        if changes.keys() & trusted_tests or any(path not in old for path in trusted_tests):
            raise ProjectHold('HOLD_PROJECT_MODEL_TEST_MUTATION')
    return plan


def materialize_plan(plan, payloads, config, *, approved_contract_sha256=None):
    """Trusted parent builder API; model output cannot choose storage paths."""
    validate_config(config)
    validate_plan(plan, config, approved_contract_sha256=approved_contract_sha256)
    required = {row['payload_sha256'] for row in plan['files']}
    if set(payloads) != required or sum(len(raw) for raw in payloads.values()) > MAX_TOTAL_BYTES:
        raise ProjectHold('HOLD_PROJECT_PAYLOAD_SET')
    for sha, raw in payloads.items():
        if not isinstance(raw, bytes) or len(raw) > MAX_FILE_BYTES or digest(raw) != sha:
            raise ProjectHold('HOLD_PROJECT_PAYLOAD_SOURCE')
        target = Path(config['package_root']) / 'blobs' / sha
        if target.exists():
            if read(target) != raw:
                raise ProjectHold('HOLD_PROJECT_IMMUTABLE_PAYLOAD_CHANGED')
        else:
            write_atomic(target, raw)
    raw = encoded(plan)
    sha = digest(raw)
    target = Path(config['package_root']) / 'plans' / (sha + '.json')
    if target.exists() and read(target) != raw:
        raise ProjectHold('HOLD_PROJECT_IMMUTABLE_PLAN_CHANGED')
    if not target.exists():
        write_atomic(target, raw)
    return {'plan_sha256':sha}


def load_plan(reference, config):
    validate_config(config)
    if (not isinstance(reference, dict) or set(reference) - {'plan_sha256', 'contract_sha256'}
            or not SHA.fullmatch(str(reference.get('plan_sha256', '')))):
        raise ProjectHold('HOLD_PROJECT_PLAN_REFERENCE')
    raw = read(Path(config['package_root']) / 'plans' / (reference['plan_sha256'] + '.json'))
    if digest(raw) != reference['plan_sha256']:
        raise ProjectHold('HOLD_PROJECT_PLAN_SOURCE')
    plan = json.loads(raw)
    validate_plan(plan, config, approved_contract_sha256=reference.get('contract_sha256'))
    return plan


def load_contract_metadata(reference, config):
    """Validate a catalog contract without comparing mutable live preimages.

    Execution's bridge.load_contract performs that fresh comparison. Completed
    work must not invalidate the entire catalog when its source has changed.
    """
    validate_config(config)
    if (not isinstance(reference, dict) or set(reference) != {'contract_sha256'}
            or not SHA.fullmatch(str(reference['contract_sha256']))):
        raise ProjectHold('HOLD_PROJECT_CONTRACT_REFERENCE')
    raw = read(Path(config['package_root']) / 'contracts' / (reference['contract_sha256'] + '.json'))
    if digest(raw) != reference['contract_sha256']:
        raise ProjectHold('HOLD_PROJECT_CONTRACT_SOURCE')
    contract = json.loads(raw)
    if (not isinstance(contract, dict) or contract.get('schema') != CONTRACT_SCHEMA
            or encoded(contract) != raw or contract.get('root_id') not in config['roots']
            or not ID.fullmatch(str(contract.get('task_id', '')))
            or not ID.fullmatch(str(contract.get('parent_task_id', '')))
            or not contract['task_id'].startswith(contract['parent_task_id'] + '.')
            or contract.get('queue_id') not in QUEUE_IDS or contract.get('acceptance_scope') not in SCOPES
            or not isinstance(contract.get('context'), list) or not 1 <= len(contract['context']) <= 128):
        raise ProjectHold('HOLD_PROJECT_CONTRACT_SCOPE')
    _verification(contract.get('verification'))
    root = config['roots'][contract['root_id']]
    pinned = {}
    for row in contract['context']:
        if not isinstance(row, dict) or set(row) != {'path', 'sha256'} or not SHA.fullmatch(str(row['sha256'])):
            raise ProjectHold('HOLD_PROJECT_CONTRACT_CONTEXT')
        path = relpath(row['path'])
        if path in pinned or not _allowed(path, root['allowed_paths']) or _allowed(path, root.get('deny_paths', [])):
            raise ProjectHold('HOLD_PROJECT_CONTRACT_PATH')
        pinned[path] = row['sha256']
    editable, new = contract.get('editable_paths'), contract.get('allowed_new_paths', [])
    if (not isinstance(editable, list) or not editable or not isinstance(new, list)
            or not set(editable) <= pinned.keys() or set(new) & pinned.keys()):
        raise ProjectHold('HOLD_PROJECT_CONTRACT_EDITABLE')
    tests = {name.replace('.', '/') + '.py' for name in contract['verification']['modules']}
    if not tests <= pinned.keys() or tests & (set(editable) | set(new)):
        raise ProjectHold('HOLD_PROJECT_CONTRACT_TESTS')
    return contract


class RootTree:
    """Directory-fd anchored reads/replacements; reject symlink traversal."""
    def __init__(self, root):
        self.path = plain(root)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.identity = os.fstat(self.fd)
    def close(self):
        os.close(self.fd)
    def assert_current(self):
        current = plain(self.path).stat()
        if (current.st_dev, current.st_ino) != (self.identity.st_dev, self.identity.st_ino):
            raise ProjectHold('HOLD_PROJECT_ROOT_REPLACED')
    @contextlib.contextmanager
    def parent(self, path, create=False):
        pieces = relpath(path).split('/')
        current = os.dup(self.fd)
        try:
            for part in pieces[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o755, dir_fd=current)
                        os.fsync(current)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = child
            yield current, pieces[-1]
        finally:
            os.close(current)
    def get(self, path):
        try:
            with self.parent(path) as (folder, name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
                with os.fdopen(fd, 'rb') as handle:
                    before = os.fstat(handle.fileno())
                    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
                        raise ProjectHold('HOLD_PROJECT_TARGET_TYPE_OR_SIZE')
                    raw = handle.read(MAX_FILE_BYTES + 1)
                    after = os.fstat(handle.fileno())
                if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                    raise ProjectHold('HOLD_PROJECT_TARGET_CHANGED_DURING_READ')
                return raw, stat.S_IMODE(before.st_mode)
        except FileNotFoundError:
            return None, None
    def replace(self, path, raw, mode):
        self.assert_current()
        with self.parent(path, create=raw is not None) as (folder, name):
            if raw is None:
                os.unlink(name, dir_fd=folder)
                os.fsync(folder)
                return
            temp = name + '.nox-' + os.urandom(8).hex()
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode & 0o777, dir_fd=folder)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, name, src_dir_fd=folder, dst_dir_fd=folder)
                os.fsync(folder)
            finally:
                try:
                    os.unlink(temp, dir_fd=folder)
                except FileNotFoundError:
                    pass


@contextlib.contextmanager
def tree(root):
    value = RootTree(root)
    try:
        yield value
    finally:
        value.close()


def _check_source(handle, plan, *, integrated=False):
    expected = {row['path']:row['sha256'] for row in plan['context']}
    expected.update({row['path']:row['after_sha256'] if integrated else row['before_sha256']
                     for row in plan['files']})
    total = 0
    snapshot = {}
    for path, sha in expected.items():
        raw, mode = handle.get(path)
        if (digest(raw) if raw is not None else None) != sha:
            raise ProjectHold('HOLD_PROJECT_SOURCE_CAS_CHANGED')
        if raw is not None:
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ProjectHold('HOLD_PROJECT_CONTEXT_BYTES')
            snapshot[path] = (raw, mode)
    handle.assert_current()
    return snapshot


def _attempt(config, plan, claim):
    if not CLAIM.fullmatch(str(claim)):
        raise ProjectHold('HOLD_PROJECT_CLAIM')
    return plain(Path(config['state_root']) / 'attempts' / digest(plan['task_id'].encode())
                 / claim / digest(encoded(plan)))


def _journal(path, value):
    write_atomic(path / 'journal.json', encoded(value))


def _base_evidence(plan, reference, claim):
    fields = Path('/proc/self/stat').read_text().split(') ', 1)[1].split()
    return {'schema':EVIDENCE_SCHEMA, 'task_id':plan['task_id'],
            'parent_task_id':plan['parent_task_id'], 'queue_id':plan['queue_id'],
            'plan_sha256':reference['plan_sha256'], 'claim':claim,
            'root_id':plan['root_id'], 'acceptance_scope':plan['acceptance_scope'],
            'original_task_accepted':False, 'worker':{'pid':os.getpid(), 'ppid':os.getppid(),
                'process_starttime':int(fields[19])}, 'started_at':time.time(),
            'project_source_changed':False, 'model_commands_executed':False}


def _cancelled(stop_check):
    try:
        return stop_check() is not False
    except Exception:
        return True


def _prepared_result(evidence):
    tests = evidence.get('tests') or {}
    isolation = tests.get('sandbox') or {}
    verified = all(isolation.get(key) is True for key in ('network_denied', 'fork_denied',
                   'exec_denied', 'host_path_hidden', 'no_new_privs', 'seccomp_filter'))
    return {'state':evidence['state'], 'passed':evidence['state'] == 'PREPARED',
            'plan_sha256':evidence['plan_sha256'], 'sandbox_verified':verified,
            'trusted_tests_unchanged':evidence.get('trusted_tests_unchanged') is True,
            'tests_run':tests.get('tests_run', 0), 'project_evidence':evidence,
            'project_evidence_sha256':digest(encoded(evidence))}


def _dependencies(config, attempt):
    reference = config.get('dependency_manifest')
    if reference is None:
        return [], []
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}
            or not SHA.fullmatch(str(reference.get('sha256', '')))):
        raise ProjectHold('HOLD_PROJECT_DEPENDENCY_REFERENCE')
    raw = read(plain(reference['path']), 4 * 1024 * 1024)
    if digest(raw) != reference['sha256']:
        raise ProjectHold('HOLD_PROJECT_DEPENDENCY_MANIFEST')
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get('schema') != 'NOX_PROJECT_TEST_DEPENDENCIES_V1'
            or not isinstance(manifest.get('roots'), list) or not 1 <= len(manifest['roots']) <= 4
            or not isinstance(manifest.get('files'), list) or not 1 <= len(manifest['files']) <= 3000
            or not isinstance(manifest.get('preload_modules'), list)
            or any(not MODULE.fullmatch(str(name)) for name in manifest['preload_modules'])):
        raise ProjectHold('HOLD_PROJECT_DEPENDENCY_SCHEMA')
    for root in manifest['roots']:
        plain(root)
    destination = attempt / 'dependencies'
    destination.mkdir(mode=0o755, exist_ok=True)
    total, paths = 0, set()
    for row in manifest['files']:
        if (not isinstance(row, dict) or set(row) != {'root_index', 'path', 'sha256'}
                or type(row['root_index']) is not int or not 0 <= row['root_index'] < len(manifest['roots'])
                or not SHA.fullmatch(str(row['sha256']))):
            raise ProjectHold('HOLD_PROJECT_DEPENDENCY_FILE')
        path = relpath(row['path'])
        if path in paths:
            raise ProjectHold('HOLD_PROJECT_DEPENDENCY_DUPLICATE')
        paths.add(path)
        source = Path(manifest['roots'][row['root_index']]) / path
        raw = read(source, 24 * 1024 * 1024)
        if digest(raw) != row['sha256']:
            raise ProjectHold('HOLD_PROJECT_DEPENDENCY_CHANGED')
        total += len(raw)
        if total > 96 * 1024 * 1024:
            raise ProjectHold('HOLD_PROJECT_DEPENDENCY_BYTES')
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        write_atomic(target, raw, 0o644)
    return [str(destination)], manifest['preload_modules']


def _test_report(attempt, work, plan, config, stop_check, heartbeat):
    sandbox = config['sandbox']
    backend = sandbox['backend']
    runner = Path(__file__).parent / 'owner_project_test_runner.py'
    host_canary = attempt / 'host-isolation-canary'
    write_atomic(host_canary, os.urandom(32))
    dependency_paths, preload_modules = _dependencies(config, attempt)
    spec = {**{key:plan['verification'][key] for key in ('modules', 'min_tests', 'timeout_sec')},
            'backend':backend, 'uid':sandbox['uid'], 'gid':sandbox['gid'],
            'memory_mb':sandbox['memory_mb'], 'host_canary':str(host_canary),
            'worker_pid':os.getpid(), 'preload_modules':preload_modules,
            'dependency_paths':dependency_paths}
    os.chmod(work, 0o777)  # Private ancestor remains 0700; only isolated /work is writable.
    if backend == 'bwrap_seccomp':
        spec['dependency_paths'] = ['/packages'] if dependency_paths else []
        spec_path = attempt / 'test-spec.json'
        write_atomic(spec_path, encoded(spec), 0o644)
        argv = [sandbox['bwrap'], '--unshare-user', '--unshare-pid', '--unshare-ipc',
                '--unshare-uts', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
                '--uid', str(sandbox['uid']), '--gid', str(sandbox['gid']), '--clearenv']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists():
                argv += ['--ro-bind', path, path]
        # Only a reviewed interpreter under /usr is supported in this backend.
        if not str(sandbox['python']).startswith('/usr/'):
            raise ProjectHold('HOLD_PROJECT_SANDBOX_PYTHON_ROOT')
        argv += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                 '--bind', str(work), '/work', '--ro-bind', str(runner), '/runner.py',
                 '--ro-bind', str(spec_path), '/spec.json', '--chdir', '/work',
                 '--', sandbox['python'], '-I', '-S', '-B', '/runner.py', '/spec.json']
        if dependency_paths:
            insertion = argv.index('--')
            argv[insertion:insertion] = ['--ro-bind', dependency_paths[0], '/packages']
    elif backend == 'chroot_seccomp':
        if os.getuid() != 0:
            raise ProjectHold('HOLD_PROJECT_SANDBOX_REQUIRES_ROOT')
        rootfs = attempt / 'rootfs'
        rootfs.mkdir(mode=0o755, exist_ok=True)
        target = rootfs / 'work'
        if target.exists():
            raise ProjectHold('HOLD_PROJECT_SANDBOX_WORKTREE_EXISTS')
        os.rename(work, target)
        # The interpreter is already running when chroot occurs; standard lib
        # files and preloaded extension dependencies suffice for fixed tests.
        stdlib = Path(sandbox.get('stdlib', sysconfig.get_path('stdlib')))
        plain(stdlib)
        if not (stdlib / 'unittest/__init__.py').is_file():
            raise ProjectHold('HOLD_PROJECT_STDLIB')
        shutil.copytree(stdlib, rootfs / 'python', symlinks=False,
                        ignore=shutil.ignore_patterns('site-packages', 'dist-packages',
                            '__pycache__', '*.pyc', 'test', 'tests', 'ensurepip', 'idlelib', 'tkinter'))
        if dependency_paths:
            shutil.copytree(dependency_paths[0], rootfs / 'packages', copy_function=os.link)
        # Python packages loaded before chroot retain their original __path__,
        # loader origins and code filenames. Provide internal aliases for just
        # those pinned roots, so lazy imports/resources resolve inside chroot.
        # Absolute symlink targets are interpreted relative to the new root.
        aliases = [(str(stdlib), '/python')]
        if dependency_paths:
            aliases.append((dependency_paths[0], '/packages'))
        for source_path, isolated_path in aliases:
            alias = rootfs / Path(source_path).relative_to('/')
            if alias == rootfs / isolated_path.lstrip('/'):
                continue
            alias.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if alias.exists() or alias.is_symlink():
                raise ProjectHold('HOLD_PROJECT_SANDBOX_ALIAS_COLLISION')
            alias.symlink_to(isolated_path, target_is_directory=True)
        (rootfs / 'tmp').mkdir(mode=0o777)
        os.chmod(rootfs / 'tmp', 0o1777)
        os.chown(target, sandbox['uid'], sandbox['gid'])
        os.chmod(target, 0o755)
        spec['rootfs'] = str(rootfs)
        spec_path = attempt / 'test-spec.json'
        write_atomic(spec_path, encoded(spec))
        argv = [sandbox['python'], '-I', '-S', '-B', str(runner), str(spec_path)]
    else:
        raise ProjectHold('HOLD_PROJECT_SANDBOX_BACKEND')
    output = bytearray()
    selector = selectors.DefaultSelector()
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, close_fds=True, start_new_session=True,
                             env={'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1'})
    deadline = time.monotonic() + plan['verification']['timeout_sec'] + 8
    reason = None
    try:
        selector.register(child.stdout, selectors.EVENT_READ)
        last_heartbeat = 0.0
        while True:
            now = time.monotonic()
            if _cancelled(stop_check):
                reason = 'STOPPED'
                break
            if now >= deadline:
                reason = 'HOLD_PROJECT_TEST_TIMEOUT'
                break
            if now-last_heartbeat >= 1:
                heartbeat()
                last_heartbeat = now
            for key, _ in selector.select(.05):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if chunk:
                    output.extend(chunk)
                    if len(output) > 131072:
                        reason = 'HOLD_PROJECT_TEST_OUTPUT_LIMIT'
                        break
                else:
                    selector.unregister(key.fileobj)
            if reason or (child.poll() is not None and not selector.get_map()):
                break
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.wait(timeout=3)
        selector.close()
        child.stdout.close()
        if backend == 'chroot_seccomp' and (attempt / 'rootfs/work').exists():
            os.rename(attempt / 'rootfs/work', work)
    if reason:
        raise ProjectHold(reason)
    prefix = b'NOX_PROJECT_TEST_REPORT_V1:'
    rows = [line[len(prefix):] for line in bytes(output).splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise ProjectHold('HOLD_PROJECT_SANDBOX_NO_VALID_REPORT')
    report = json.loads(rows[0])
    if report.get('schema') != 'NOX_PROJECT_TEST_REPORT_V1':
        raise ProjectHold('HOLD_PROJECT_TEST_REPORT_SCHEMA')
    if report.get('completed') is not True:
        reason = report.get('reason', 'HOLD_PROJECT_TEST_INCOMPLETE')
        detail = report.get('exception_detail')
        raise ProjectHold(reason + (': ' + str(detail)[:300] if detail else ''))
    facts = report.get('sandbox') or {}
    if (facts.get('uid') != sandbox['uid'] or facts.get('gid') != sandbox['gid']
            or any(facts.get(key) is not True for key in ('network_denied', 'fork_denied',
                'exec_denied', 'host_path_hidden', 'no_new_privs', 'seccomp_filter'))
            or report.get('modules') != plan['verification']['modules']
            or type(report.get('tests_run')) is not int
            or report['tests_run'] < plan['verification']['min_tests']):
        raise ProjectHold('HOLD_PROJECT_TEST_REPORT_PROOF')
    report['passed'] = (child.returncode == 0 and report.get('passed') is True
                        and report.get('failures') == 0 and report.get('errors') == 0
                        and report.get('skipped') == 0)
    return report


def prepare(reference, config, claim, *, stop_check=lambda:False, heartbeat=lambda:None):
    """Worker operation: real edits and tests in an isolated per-claim worktree."""
    plan = load_plan(reference, config)
    attempt = _attempt(config, plan, claim)
    evidence = _base_evidence(plan, reference, claim)
    attempt.mkdir(parents=True, exist_ok=True, mode=0o700)
    journal_path = attempt / 'journal.json'
    if journal_path.exists():
        previous = document(journal_path)
        if (previous.get('plan_sha256') == reference['plan_sha256']
                and previous.get('claim') == claim and previous.get('state') == 'PREPARED'):
            return _prepared_result(previous)
        raise ProjectHold('HOLD_PROJECT_ATTEMPT_REQUIRES_RECOVERY')
    work = attempt / 'work'
    work.mkdir(mode=0o755)
    evidence.update(state='STAGING')
    _journal(attempt, evidence)
    try:
        if _cancelled(stop_check):
            raise ProjectHold('STOPPED')
        with tree(config['roots'][plan['root_id']]['path']) as handle:
            snapshot = _check_source(handle, plan)
        for path, (raw, _) in snapshot.items():
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            write_atomic(target, raw, 0o644)
        for row in plan['files']:
            raw = read(Path(config['package_root']) / 'blobs' / row['payload_sha256'])
            if digest(raw) != row['after_sha256']:
                raise ProjectHold('HOLD_PROJECT_PAYLOAD_SOURCE')
            target = work / row['path']
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            write_atomic(target, raw, 0o644)
        evidence.update(state='VERIFYING')
        _journal(attempt, evidence)
        report = _test_report(attempt, work, plan, config, stop_check, heartbeat)
        with tree(work) as handle:
            _check_source(handle, plan, integrated=True)
        if _cancelled(stop_check):
            raise ProjectHold('STOPPED')
        evidence.update(state='PREPARED' if report['passed'] else 'FAILED_TESTS',
                        tests=report, tests_sha256=digest(encoded(report)),
                        trusted_tests_unchanged=True,
                        postimages={row['path']:row['after_sha256'] for row in plan['files']},
                        finished_at=time.time())
    except (OSError, ValueError, ProjectHold) as exc:
        reason = str(exc) if isinstance(exc, ProjectHold) else 'HOLD_PROJECT_PREPARE_'+type(exc).__name__
        state = ('STOPPED' if reason == 'STOPPED' else 'BLOCKED_SOURCE_CHANGED'
                 if 'SOURCE_CAS' in reason or 'PAYLOAD_SOURCE' in reason else 'BLOCKED_SANDBOX')
        evidence.update(state=state, reason=reason, finished_at=time.time())
    _journal(attempt, evidence)
    return _prepared_result(evidence)


def verify_candidate(plan, payloads, config, claim, *, approved_contract_sha256=None,
                     stop_check=lambda:False, heartbeat=lambda:None):
    reference = materialize_plan(plan, payloads, config,
                                 approved_contract_sha256=approved_contract_sha256)
    if approved_contract_sha256:
        reference['contract_sha256'] = approved_contract_sha256
    return prepare(reference, config, claim, stop_check=stop_check, heartbeat=heartbeat)


@contextlib.contextmanager
def _integration_lock(config, plan):
    path = Path(config['state_root']) / 'locks' / (digest(plan['root_id'].encode()) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(plain(path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProjectHold('WAIT_PROJECT_INTEGRATION_LOCK') from exc
        yield
    finally:
        os.close(fd)


def _restore(handle, plan, attempt, evidence):
    evidence['state'] = 'ROLLING_BACK'
    evidence['project_source_changed'] = None
    _journal(attempt, evidence)
    for row in reversed(plan['files']):
        current, _ = handle.get(row['path'])
        current_sha = digest(current) if current is not None else None
        if current_sha == row['before_sha256']:
            continue
        if current_sha != row['after_sha256']:
            raise ProjectHold('HOLD_PROJECT_ROLLBACK_CONCURRENT_WRITE')
        backup = evidence['backups'][row['path']]
        raw = read(attempt / 'backups' / backup['sha256']) if backup['sha256'] else None
        if raw is not None and digest(raw) != row['before_sha256']:
            raise ProjectHold('HOLD_PROJECT_ROLLBACK_BACKUP_SOURCE')
        handle.replace(row['path'], raw, backup['mode'] or 0o644)
    _check_source(handle, plan)
    evidence.update(state='ROLLED_BACK', project_source_changed=False,
                    rollback_verified=True, finished_at=time.time())
    _journal(attempt, evidence)


def integrate_prepared(reference, config, claim, *, gate):
    """Parent-only CAS; caller holds native current claim and queue writer lock."""
    if not callable(gate):
        raise ProjectHold('HOLD_PROJECT_PARENT_GATE')
    plan = load_plan(reference, config)
    attempt = _attempt(config, plan, claim)
    evidence = document(attempt / 'journal.json')
    if (evidence.get('plan_sha256') != reference['plan_sha256'] or evidence.get('claim') != claim
            or evidence.get('task_id') != plan['task_id'] or evidence.get('original_task_accepted') is not False):
        raise ProjectHold('HOLD_PROJECT_PREPARED_IDENTITY')
    with _integration_lock(config, plan), tree(config['roots'][plan['root_id']]['path']) as handle:
        if evidence.get('state') == 'INTEGRATED':
            _check_source(handle, plan, integrated=True)
            return evidence  # Durable idempotent readback; no write replay.
        if (evidence.get('state') != 'PREPARED' or evidence.get('tests', {}).get('passed') is not True
                or evidence.get('tests_sha256') != digest(encoded(evidence.get('tests')))):
            raise ProjectHold('HOLD_PROJECT_NOT_PREPARED')
        if _cancelled(lambda: not gate()):
            raise ProjectHold('STOPPED')
        snapshot = _check_source(handle, plan)
        with tree(attempt / 'work') as staged:
            _check_source(staged, plan, integrated=True)
        backups = {}
        for row in plan['files']:
            raw, mode = snapshot.get(row['path'], (None, None))
            sha = digest(raw) if raw is not None else None
            if raw is not None:
                write_atomic(attempt / 'backups' / sha, raw)
            backups[row['path']] = {'sha256':sha, 'mode':mode}
        evidence.update(state='INTEGRATING', backups=backups, integration_started_at=time.time(),
                        project_source_changed=None)
        _journal(attempt, evidence)
        try:
            for row in plan['files']:
                if _cancelled(lambda: not gate()):
                    raise ProjectHold('STOPPED')
                current, mode = handle.get(row['path'])
                if (digest(current) if current is not None else None) != row['before_sha256']:
                    raise ProjectHold('HOLD_PROJECT_SOURCE_CAS_CHANGED')
                raw = read(attempt / 'work' / row['path'])
                if digest(raw) != row['after_sha256']:
                    raise ProjectHold('HOLD_PROJECT_PREPARED_FILE_CHANGED')
                handle.replace(row['path'], raw, mode or 0o644)
            _check_source(handle, plan, integrated=True)
            if _cancelled(lambda: not gate()):
                raise ProjectHold('STOPPED')
            evidence.update(state='INTEGRATED', project_source_changed=True,
                            integration_verified=True, finished_at=time.time())
            _journal(attempt, evidence)
        except (OSError, ValueError, ProjectHold) as exc:
            evidence['reason'] = str(exc) if isinstance(exc, ProjectHold) else 'HOLD_PROJECT_INTEGRATION_IO'
            try:
                _restore(handle, plan, attempt, evidence)
            except (OSError, ValueError, ProjectHold) as rollback_exc:
                evidence.update(state='HOLD_RECOVERY_REQUIRED', rollback_verified=False,
                    project_source_changed=None,
                    reason=str(rollback_exc) if isinstance(rollback_exc, ProjectHold) else 'HOLD_PROJECT_ROLLBACK_IO')
                _journal(attempt, evidence)
        return evidence


def recover_interrupted(reference, config, original_claim, *, gate):
    """Explicit recovery of one previous attempt; never re-executes a test/job."""
    plan = load_plan(reference, config)
    attempt = _attempt(config, plan, original_claim)
    evidence = document(attempt / 'journal.json')
    if (evidence.get('plan_sha256') != reference['plan_sha256'] or evidence.get('claim') != original_claim
            or evidence.get('task_id') != plan['task_id'] or not gate()):
        raise ProjectHold('HOLD_PROJECT_RECOVERY_GATE')
    with _integration_lock(config, plan), tree(config['roots'][plan['root_id']]['path']) as handle:
        if evidence.get('state') == 'INTEGRATED':
            _check_source(handle, plan, integrated=True)
        elif evidence.get('state') in ('INTEGRATING', 'ROLLING_BACK', 'HOLD_RECOVERY_REQUIRED'):
            _restore(handle, plan, attempt, evidence)
        elif evidence.get('state') in ('STAGING', 'VERIFYING', 'PREPARED'):
            # Source was never modified in these phases. Cancel the old attempt;
            # a new nonce may retry only after the parent reconciles worker PID.
            _check_source(handle, plan)
            evidence.update(state='STOPPED', reason='PREVIOUS_ATTEMPT_RECONCILED',
                            project_source_changed=False, finished_at=time.time())
            _journal(attempt, evidence)
        elif evidence.get('state') not in TERMINAL_WITHOUT_CHANGES:
            raise ProjectHold('HOLD_PROJECT_RECOVERY_STATE')
    return evidence


def execute(item, *, cancelled=lambda:False, heartbeat=lambda:None):
    """Private existing-worker IPC entry; it never commits shared project files."""
    context = item.get('_native_project_context')
    if (not isinstance(context, dict) or set(context) != {'reference', 'config', 'claim'}
            or not CLAIM.fullmatch(str(context.get('claim', '')))):
        raise ProjectHold('HOLD_PROJECT_WORKER_CONTEXT')
    plan = load_plan(context['reference'], context['config'])
    if item.get('id') != plan['task_id']:
        raise ProjectHold('HOLD_PROJECT_WORKER_TASK')
    return prepare(context['reference'], context['config'], context['claim'],
                   stop_check=cancelled, heartbeat=heartbeat)
