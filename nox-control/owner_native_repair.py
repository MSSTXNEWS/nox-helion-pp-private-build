"""Read back the one published I-39 native task without touching the host state."""

from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time


ROOT = Path('/root/nox')
CONFIG = ROOT / 'config/owner_native_subagents.json'
QUEUE = ROOT / 'state/dispatcher/state.json'
DB = ROOT / 'kb/knowledge.sqlite'
FORGE = ROOT / 'projects/owner_executor/source_workspace/forge_split_guard.py'
DIRECTOR = ROOT / 'scripts/owner_subagent_dispatcher.py'
CONFIG_SHA = '01101f81e0b76e54a53f0f6c2734082ef164ae32b39832c6d74b154a809084e5'
DIRECTOR_SHA = 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
OWNER_UID = 0
TASK = 'I-39.project.forge_exact_content_dedup.v1'
PLAN = '3cf22ef77659b7186dedda1c3153af659bc45e8d114b42d69e28317e570b68bd'
POSTIMAGE = 'f38a9b3592c281b00c621270206f8b97f7918e430f26f007ec1cdc797e88c534'
HANDLER = 'owner_native_project_work'
QUEUE_ID = 'Q3_TRAINING_WEIGHTS'
SCHEMA = 'NOX_NATIVE_SUBAGENT_RECEIPT_V1'
PHASES = {'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED', 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'}
STATUSES = {'running', 'pending', 'blocked', 'done', 'failed', 'cancelled', 'retry', 'wait', 'catalog'}
SHA = re.compile(r'[0-9a-f]{64}')


def require(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_I39_READBACK_' + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def trusted_directory(info):
    return stat.S_ISDIR(info.st_mode) and info.st_uid == OWNER_UID and not info.st_mode & 0o022


@contextmanager
def open_parent(path):
    require(path.is_absolute() and path.is_relative_to(ROOT) and '..' not in path.parts, 'PATH_SCOPE')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = os.open('/', flags)
    try:
        require(trusted_directory(os.fstat(parent)), 'ROOT_ANCESTOR')
        private_ancestor = False
        for part in path.parts[1:-1]:
            child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child
            info = os.fstat(parent)
            if not private_ancestor:
                require(trusted_directory(info), 'UNTRUSTED_ANCESTOR')
                # A root-owned directory without group/other search permission
                # protects the fixed path below it, even for shared-mode subdirectories.
                private_ancestor = not info.st_mode & 0o011
        yield parent
    finally:
        os.close(parent)


@contextmanager
def open_regular(parent, name):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    fd = os.open(name, flags, dir_fd=parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == OWNER_UID
                and info.st_nlink == 1 and not info.st_mode & 0o022, 'FILE')
        yield fd, info
    finally:
        os.close(fd)


def same_file(path, parent, fd, before):
    entry = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
    path_entry = path.lstat()
    return stamp(os.fstat(fd)) == stamp(entry) == stamp(path_entry) == stamp(before)


def read(path, cap):
    with open_parent(path) as parent, open_regular(parent, path.name) as (fd, before):
        require(0 < before.st_size <= cap, 'FILE_SCOPE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(cap + 1)
        require(len(raw) == before.st_size and same_file(path, parent, fd, before), 'FILE_DRIFT')
    return raw


def wal_present(parent):
    try:
        with open_regular(parent, DB.name + '-wal') as (_, info):
            return info.st_size != 0
    except FileNotFoundError:
        return False


def verify_s03(receipt, receipt_sha):
    try:
        with open_parent(DB) as parent, open_regular(parent, DB.name) as (fd, before):
            if wal_present(parent):
                return 'HOLD_WAL_PRESENT'
            # Read the selected inode. Immutable read-only SQLite creates no sidecars.
            uri = f'file:/proc/self/fd/{fd}?mode=ro&immutable=1'
            text = f"NOX native job {receipt['job_id']} {receipt['phase']} receipt_sha256 {receipt_sha}"
            with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as conn:
                conn.execute('PRAGMA query_only=ON')
                deadline = time.monotonic() + 2
                conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                items = conn.execute("SELECT meta,sha256 FROM s03_items WHERE segment='M2' AND text=? "
                                     "AND provenance='owner_native_subagents' LIMIT 2", (text,)).fetchall()
            if not same_file(DB, parent, fd, before) or wal_present(parent):
                return 'HOLD_SNAPSHOT_CHANGED'
        exact = len(items) == 1 and items[0][1] == digest(('M2|' + text).encode())
        return 'VERIFIED' if exact and json.loads(items[0][0]).get('receipt') == receipt else 'UNVERIFIED'
    except (OSError, sqlite3.Error, ValueError, AttributeError, RuntimeError):
        return 'UNAVAILABLE'


def safe_code(value):
    return value if type(value) is str and re.fullmatch(r'HOLD_(?:PROJECT|SUBAGENT|NATIVE)_[A-Z0-9_]{1,72}', value) else None


def inspect(config, catalog, row):
    fields = {'catalog_bound': catalog is not None, 'queue_row_present': row is not None,
              'mode': config.get('mode') if config.get('mode') in ('NORMAL', 'FORSAZH') else 'OTHER',
              'target': config.get('target') if type(config.get('target')) is int else None}
    if catalog is None:
        return {**fields, 'state': 'TASK_NOT_IN_CATALOG'}
    pins = config['module_pins']
    source = catalog.get('source_sha256')
    params = catalog.get('params')
    require(catalog.get('handler') == HANDLER and catalog.get('queue_id') == QUEUE_ID
            and catalog.get('priority') == 'P3'
            and isinstance(params, dict) and params.get('plan_sha256') == PLAN
            and params.get('parent_task_id') == 'I-39'
            and isinstance(source, str) and SHA.fullmatch(source), 'CATALOG_BINDING')
    require(source == pins.get('owner_subagent_dispatcher.py') == DIRECTOR_SHA, 'RUNTIME_BINDING')
    fields['source_current'] = True
    if row is None:
        return {**fields, 'state': 'CATALOG_ONLY'}
    parameters = row.get('params')
    require(row.get('id') == TASK and row.get('handler') == HANDLER and row.get('queue_id') == QUEUE_ID
            and isinstance(parameters, dict) and parameters.get('plan_sha256') == PLAN
            and parameters.get('parent_task_id') == 'I-39' and parameters.get('source_sha256') == source,
            'QUEUE_BINDING')
    status = row.get('status')
    fields['queue_status'] = status if isinstance(status, str) and status in STATUSES else 'OTHER'
    lease = row.get('native_worker_lease')
    phase = lease.get('phase') if isinstance(lease, dict) else None
    fields['worker_lease_phase'] = phase if phase in ('ACTIVE', 'RETIRING', 'SETTLED') else None
    admission = row.get('native_admission')
    fields['native_admission_bound'] = isinstance(admission, dict) and admission.get('task_id') == TASK
    outcome = row.get('result')
    terminal = row.get('native_project_terminal')
    if not isinstance(terminal, dict):
        return {**fields, 'state': 'QUEUE_ROW_WITHOUT_TERMINAL_RECEIPT', 'hold_code': safe_code(outcome)}
    receipt = terminal.get('receipt')
    job = parameters.get('job_id')
    require(isinstance(receipt, dict) and receipt.get('schema') == SCHEMA and terminal.get('verified') is True
            and receipt.get('task_id') == TASK and receipt.get('parent_task_id') == 'I-39'
            and receipt.get('queue_id') == QUEUE_ID and receipt.get('plan_sha256') == PLAN
            and receipt.get('source_sha256') == source and receipt.get('claim') == row.get('owner_claim')
            and type(job) is str and re.fullmatch(r'nox-project-[0-9a-f]{24}', job)
            and receipt.get('job_id') == job and receipt.get('original_task_accepted') is False
            and receipt.get('phase') in PHASES, 'RECEIPT_BINDING')
    receipt_sha = digest(canonical(receipt))
    require(terminal.get('receipt_sha256') == receipt_sha, 'RECEIPT_SHA')
    evidence = receipt.get('worker_result', {}).get('project_evidence', {})
    result_sha = outcome.get('receipt_sha256') if isinstance(outcome, dict) else None
    try:
        postimage = digest(read(FORGE, 2 * 1024 * 1024)) == POSTIMAGE
    except (OSError, RuntimeError):
        postimage = None
    return {**fields, 'state': 'TERMINAL_RECEIPT_VERIFIED', 'receipt_sha256': receipt_sha,
            'receipt_phase': receipt['phase'], 'queue_result_binds_receipt': result_sha == receipt_sha,
            'hold_code': safe_code(evidence.get('reason')), 'forge_postimage_matches': postimage,
            's03_readback': verify_s03(receipt, receipt_sha)}


def task_row():
    state = json.loads(read(QUEUE, 16 * 1024 * 1024))
    require(isinstance(state.get('tasks'), dict), 'QUEUE')
    row = state['tasks'].get(TASK)
    require(row is None or isinstance(row, dict), 'QUEUE_ROW')
    return row


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request)
            and re.fullmatch(r'[0-9a-f]{40}', source), 'OWNER_CONTEXT')
    original = read(CONFIG, 2 * 1024 * 1024)
    config_sha = digest(original)
    require(config_sha == CONFIG_SHA, 'CONFIG_PIN')
    require(digest(read(DIRECTOR, 2 * 1024 * 1024)) == DIRECTOR_SHA, 'RUNTIME_PIN')
    config = json.loads(original)
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('instance_id') == 60509551 and config.get('owner_authorized') is True, 'OWNER_CONFIG')
    catalog = config.get('catalog')
    require(isinstance(catalog, dict) and digest(canonical(catalog)) == config.get('catalog_sha256')
            and isinstance(catalog.get('tasks'), list) and len(catalog['tasks']) <= 4096, 'CATALOG')
    entries = [entry for entry in catalog['tasks'] if isinstance(entry, dict) and entry.get('id') == TASK]
    require(len(entries) <= 1, 'CATALOG_DUPLICATE')
    row = task_row()
    answer = inspect(config, entries[0] if entries else None, row)
    require(task_row() == row and read(CONFIG, 2 * 1024 * 1024) == original
            and digest(read(DIRECTOR, 2 * 1024 * 1024)) == DIRECTOR_SHA, 'SNAPSHOT_DRIFT')
    flags = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP',
             'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    stop = any(path.exists() or path.is_symlink() for path in
               [*(ROOT / name for name in flags), Path('/workspace/NOX_STOP')])
    result = {'schema': 'NOX_I39_NATIVE_READBACK_V1', 'task_id': TASK, 'request_id': request,
              'config_sha256': config_sha, 'stop_flag_present': stop, 'original_task_accepted': False,
              'read_only': True, **answer}
    print('NOX_MAINT_I39_NATIVE_READBACK=' + canonical(result).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        reason = str(error)
        print('NOX_MAINT_RESULT=' + (reason if re.fullmatch(r'HOLD_I39_READBACK_[A-Z_]+', reason)
                                   else 'HOLD_I39_READBACK_UNAVAILABLE'), flush=True)
        raise SystemExit(2) from None
