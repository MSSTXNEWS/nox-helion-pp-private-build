"""Bounded read-only inventory before replacing a source-pinned plan module."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time


class InventoryHold(RuntimeError):
    pass


def read(path, maximum):
    if any(p.is_symlink() for p in (*path.parents, path)):
        raise InventoryHold('HOLD_PLAN_INVENTORY_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise InventoryHold('HOLD_PLAN_INVENTORY_FILE_SCOPE')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    named = path.stat(follow_symlinks=False)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns')
    if len(raw) > maximum or any(getattr(before,k) != getattr(after,k) or getattr(before,k) != getattr(named,k) for k in fields):
        raise InventoryHold('HOLD_PLAN_INVENTORY_CHANGED')
    return raw


def observe(root=Path('/root/nox')):
    """No queue writes, imports of live controllers, locks or process actions."""
    result = {'schema':'NOX_ACTIVE_PLAN_INVENTORY_V1', 'observed_at':time.time(),
              'inventory_complete':False, 'content_exported':False, 'files_written':0}
    queue = root/'state/dispatcher/state.json'
    try:
        raw = read(queue, 16*1024*1024)
        state = json.loads(raw); tasks = state.get('tasks')
        if not isinstance(tasks,dict) or len(tasks) > 10000:
            raise InventoryHold('HOLD_PLAN_INVENTORY_QUEUE_SCHEMA')
        rows = []; sources = {}; active = {'pending','wait','retry','running','blocked'}
        for task_id, task in tasks.items():
            if not isinstance(task,dict):
                raise InventoryHold('HOLD_PLAN_INVENTORY_TASK_SCHEMA')
            plan_id = task.get('owner_plan_id')
            if not plan_id or task.get('handler') == 'owner_memory_sync':
                continue
            if not isinstance(plan_id,str) or not re.fullmatch('[a-f0-9]{24}',plan_id):
                raise InventoryHold('HOLD_PLAN_INVENTORY_ID_SCHEMA')
            if task.get('status') not in active:
                if task.get('status') not in ('done','failed','cancelled'):
                    raise InventoryHold('HOLD_PLAN_INVENTORY_STATUS_SCHEMA')
                continue
            if task.get('id') != task_id or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',task_id):
                raise InventoryHold('HOLD_PLAN_INVENTORY_TASK_ID')
            if len(rows) >= 2048 or len(sources) >= 128 and plan_id not in sources:
                raise InventoryHold('HOLD_PLAN_INVENTORY_BOUND')
            if plan_id not in sources:
                manifest = json.loads(read(root/'state/owner_plans'/plan_id/'manifest.json',262144))
                source = manifest.get('source_sha256')
                if (manifest.get('schema') != 'NOX_OWNER_PLAN_V1' or manifest.get('plan_id') != plan_id
                        or not isinstance(source,str) or not re.fullmatch('[a-f0-9]{64}',source)):
                    raise InventoryHold('HOLD_PLAN_INVENTORY_MANIFEST_SCHEMA')
                sources[plan_id] = source
            rows.append({'plan_id':plan_id,'task_id':task_id,'status':task['status'],
                         'manifest_source_sha256':sources[plan_id]})
        if read(queue,16*1024*1024) != raw:
            raise InventoryHold('HOLD_PLAN_INVENTORY_QUEUE_CHANGED')
        result.update(state='OBSERVED_STABLE', inventory_complete=True, queue_path=str(queue),
            queue_sha256=hashlib.sha256(raw).hexdigest(), active_plan_count=len(sources),
            active_tasks=sorted(rows,key=lambda row:(row['plan_id'],row['task_id'])))
    except (InventoryHold,OSError,ValueError,TypeError,AttributeError) as exc:
        result.update(state='HOLD', error=str(exc) if isinstance(exc,InventoryHold) else type(exc).__name__)
    return result
