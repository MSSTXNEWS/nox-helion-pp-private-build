#!/usr/bin/env python3
"""Bounded admission over retained media history; keep the native planner.

The native ca8 file remains unchanged. Only its module-global ingestion
function is replaced before the dispatcher lifecycle starts. Existing task
records, claims, jobs, inbox records and all generation controls stay intact.
"""
import hashlib
import os
from pathlib import Path
import stat

RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
RUNTIME_PATH = Path('/root/nox/scripts/owner_media_runtime.py')
MAX_INBOX_ENTRIES = 200
MAX_NEW_TASKS = 3
MARKER = '_owner_media_inbox_fair_bound'
BOUND = None


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_MEDIA_INBOX_FAIR_' + code)


def source_bytes(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 262144, 'SOURCE_BOUND')
        raw = stream.read(262145)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'SOURCE_CHANGED')
    return raw


def inbox_paths(runtime):
    directory = runtime.ROOT / 'state/media/inbox'
    require(not any(path.is_symlink() for path in (*directory.parents, directory)), 'INBOX_SYMLINK')
    if not directory.exists():
        return []
    paths = []
    with os.scandir(directory) as entries:
        for scanned, entry in enumerate(entries, 1):
            # A 201st directory entry is only an overflow sentinel. No payload
            # is read and no tasks are admitted on an oversized history.
            require(scanned <= MAX_INBOX_ENTRIES, 'HISTORY_BOUND')
            path = Path(entry.path)
            if (path.suffix == '.json' and runtime.JOB_ID.fullmatch(path.stem)
                    and entry.is_file(follow_symlinks=False)):
                paths.append(path)
    return sorted(paths)


def ingest(runtime, state):
    require(isinstance(state, dict) and isinstance(state.get('tasks', {}), dict), 'TASK_STATE')
    paths = inbox_paths(runtime)
    tasks = state.setdefault('tasks', {})
    count = 0
    for path in paths:
        task_id = 'owner.media.' + path.stem
        if task_id in tasks:
            continue
        value = runtime.read_json(path)
        if not isinstance(value, dict) or value.get('job_id') != path.stem:
            continue
        try:
            job = runtime.load_job(path.stem)
        except runtime.MediaHold:
            continue
        if job.get('state') != 'QUEUED':
            continue
        request = job.get('request')
        kind = request.get('kind') if isinstance(request, dict) else None
        if kind not in ('image', 'video'):
            continue
        # This is the original task shape. owner_task_plans.auto_media retains
        # authority to create the engine/budget/generation DAG and its claims.
        tasks[task_id] = {'id': task_id, 'handler': 'owner_media', 'class': 'owner_order', 'priority': 0,
            'status': 'pending', 'deps': [], 'locks': ['gpu1'], 'params': {'job_id': path.stem},
            'title': 'Owner ' + kind + ' generation', 'retries': 0, 'max_retries': 1,
            'timeout_sec': 2100, 'source': 'authenticated_owner_media'}
        count += 1
        if count == MAX_NEW_TASKS:
            break
    return count


def bind_dispatcher(namespace, runtime):
    global BOUND
    require(namespace.get('_owner_media_bound') is True and namespace.get('_owner_plans_bound') is True
            and not namespace.get('_owner_lifecycle_bound') and not namespace.get(MARKER), 'BINDING_ORDER')
    require(Path(runtime.__file__) == RUNTIME_PATH
            and hashlib.sha256(source_bytes(runtime.__file__)).hexdigest() == RUNTIME_SHA, 'RUNTIME_PIN')
    original = runtime.ingest_media_tasks
    require(callable(original) and original.__globals__ is runtime.__dict__
            and original.__name__ == 'ingest_media_tasks', 'NATIVE_FUNCTION')
    def replacement(state):
        return ingest(runtime, state)
    runtime.ingest_media_tasks = replacement
    BOUND = {'runtime': runtime, 'original': original, 'replacement': replacement}
    namespace[MARKER] = True
