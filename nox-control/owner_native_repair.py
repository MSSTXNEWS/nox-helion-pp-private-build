"""Read back the one published I-39 native task without touching the host state."""

from contextlib import closing
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


def trusted_file(path):
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, 'PARENT')
    meta = path.lstat()
    require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0
            and meta.st_nlink == 1 and not meta.st_mode & 0o022, 'FILE')
    return meta


def read(path, cap):
    before = trusted_file(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        require(0 < before.st_size <= cap and stamp(os.fstat(fd)) == stamp(before), 'FILE_SCOPE')
        raw = stream.read(cap + 1)
        require(len(raw) == before.st_size and stamp(os.fstat(fd)) == stamp(path.lstat()) == stamp(before),
                'FILE_DRIFT')
    return raw


def verify_s03(receipt, receipt_sha):
    wal = DB.with_name(DB.name + '-wal')
    try:
        trusted_file(DB)
        if wal.exists() or wal.is_symlink():
            if trusted_file(wal).st_size:
                return 'HOLD_WAL_PRESENT'
        # immutable + read-only prevents SQLite from writing journals or sidecars.
        uri = DB.as_uri() + '?mode=ro&immutable=1'
        text = f"NOX native job {receipt['job_id']} {receipt['phase']} receipt_sha256 {receipt_sha}"
        before = stamp(DB.lstat())
        with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as conn:
            conn.execute('PRAGMA query_only=ON')
            deadline = time.monotonic() + 2
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            items = conn.execute("SELECT meta,sha256 FROM s03_items WHERE segment='M2' AND text=? "
                                 "AND provenance='owner_native_subagents' LIMIT 2", (text,)).fetchall()
        if stamp(DB.lstat()) != before or ((wal.exists() or wal.is_symlink()) and trusted_file(wal).st_size):
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
    fields['source_current'] = source == pins.get('owner_subagent_dispatcher.py')
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


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request)
            and re.fullmatch(r'[0-9a-f]{40}', source), 'OWNER_CONTEXT')
    original = read(CONFIG, 2 * 1024 * 1024)
    config = json.loads(original)
    require(config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
            and config.get('instance_id') == 60509551 and config.get('owner_authorized') is True, 'OWNER_CONFIG')
    catalog = config.get('catalog')
    require(isinstance(catalog, dict) and digest(canonical(catalog)) == config.get('catalog_sha256')
            and isinstance(catalog.get('tasks'), list) and len(catalog['tasks']) <= 4096, 'CATALOG')
    entries = [entry for entry in catalog['tasks'] if isinstance(entry, dict) and entry.get('id') == TASK]
    require(len(entries) <= 1, 'CATALOG_DUPLICATE')
    state = json.loads(read(QUEUE, 16 * 1024 * 1024))
    require(isinstance(state.get('tasks'), dict), 'QUEUE')
    row = state['tasks'].get(TASK)
    require(row is None or isinstance(row, dict), 'QUEUE_ROW')
    answer = inspect(config, entries[0] if entries else None, row)
    verify_state = json.loads(read(QUEUE, 16 * 1024 * 1024))
    require(verify_state['tasks'].get(TASK) == row and read(CONFIG, 2 * 1024 * 1024) == original, 'SNAPSHOT_DRIFT')
    flags = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP',
             'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
    stop = any(path.exists() or path.is_symlink() for path in
               [*(ROOT / name for name in flags), Path('/workspace/NOX_STOP')])
    result = {'schema': 'NOX_I39_NATIVE_READBACK_V1', 'task_id': TASK, 'request_id': request,
              'config_sha256': digest(original), 'stop_flag_present': stop, 'original_task_accepted': False,
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
