#!/usr/bin/env python3
"""Durable, owner-session-only reports derived from native task evidence.

This is an inline outbox, not another worker, scheduler or notification service.
Event files are immutable; reconnecting a browser only reads them and never
changes task admission, execution, cancellation or memory-learning acceptance.
Reads may repair interrupted local dedup/cursor indices under the existing lock.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path('/root/nox')
SCHEMA = 'NOX_OWNER_EVENT_V1'
REPORT_SCHEMA = 'NOX_OWNER_TASK_REPORT_V1'
SHA = re.compile(r'^[0-9a-f]{64}$')
IDENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$')
CODE = re.compile(r'^[A-Z][A-Z0-9_]{0,99}$')
_LOCK = threading.RLock()
_AVAILABILITY_LOCK = threading.Lock()
_AVAILABILITY_CACHE = {'at': 0.0, 'value': None}
MAX_EVENT_BYTES = 24000
ERROR_COOLDOWN = 300
PROGRESS_COOLDOWN = 60
KINDS = {'task_verified', 'task_failed', 'verification_pending', 'task_blocked',
         'repair_verified', 'task_progress'}


class OutboxHold(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def safe_id(value):
    if (not isinstance(value, str) or not IDENT.fullmatch(value)
            or re.search(r'(?i)(?:hf_|ghp_|github_pat_|sk-)[A-Za-z0-9_-]{8,}', value)):
        return 'private-task'
    return value


def safe_code(value, default='UNKNOWN'):
    return value if isinstance(value, str) and CODE.fullmatch(value) else default


def _directory():
    path = ROOT / 'state/owner_events'
    for item in (ROOT, ROOT / 'state', path):
        if item.is_symlink():
            raise OutboxHold('HOLD_OWNER_EVENTS_SYMLINK')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ('events', 'dedup', 'cooldowns'):
        child = path / name
        if child.is_symlink():
            raise OutboxHold('HOLD_OWNER_EVENTS_SYMLINK')
        child.mkdir(mode=0o700, exist_ok=True)
    return path


def read_json(path, limit=MAX_EVENT_BYTES):
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise OutboxHold('HOLD_OWNER_EVENTS_SIZE')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise OutboxHold('HOLD_OWNER_EVENTS_SIZE')
    return json.loads(raw)


def atomic_json(path, value):
    if path.is_symlink() or path.parent.is_symlink():
        raise OutboxHold('HOLD_OWNER_EVENTS_SYMLINK')
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if len(raw) > MAX_EVENT_BYTES:
        raise OutboxHold('HOLD_OWNER_EVENTS_SIZE')
    fd, temporary = tempfile.mkstemp(prefix='.outbox-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(shared=False):
    with _LOCK:
        root = _directory()
        fd = os.open(root / 'outbox.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            # A slow browser or another process must never stall a task runner.
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            yield root
        finally:
            os.close(fd)


def _event_path(root, sequence):
    return root / 'events' / (str(sequence).zfill(16) + '.json')


def _meta(root):
    try:
        value = read_json(root / 'cursor.json')
    except FileNotFoundError:
        return {'schema': 'NOX_OWNER_EVENT_CURSOR_V1', 'last_sequence': 0}
    if (not isinstance(value, dict) or value.get('schema') != 'NOX_OWNER_EVENT_CURSOR_V1'
            or type(value.get('last_sequence')) is not int or not 0 <= value['last_sequence'] < 10**15):
        raise OutboxHold('HOLD_OWNER_EVENT_CURSOR')
    return value


def _recover(root, meta):
    """Finish an interrupted event->dedup->cursor commit without duplicating it."""
    changed = False
    for _ in range(16):
        sequence = meta['last_sequence'] + 1
        path = _event_path(root, sequence)
        if not path.exists() and not path.is_symlink():
            break
        event = read_json(path)
        if (event.get('schema') != SCHEMA or event.get('sequence') != sequence
                or not SHA.fullmatch(str(event.get('dedup_sha256', '')))):
            raise OutboxHold('HOLD_OWNER_EVENT_RECOVERY')
        marker = root / 'dedup' / (event['dedup_sha256'] + '.json')
        if not marker.exists():
            atomic_json(marker, {'sequence': sequence, 'dedup_sha256': event['dedup_sha256']})
        channel = digest({'task': event['task']['id'], 'kind': event['kind'], 'state': event['state']})
        cooldown = root / 'cooldowns' / (channel + '.json')
        old = read_json(cooldown) if cooldown.exists() else {}
        if float(old.get('at', 0)) < event['created_at']:
            atomic_json(cooldown, {'at': event['created_at'], 'progress': event.get('progress')})
        meta['last_sequence'] = sequence
        changed = True
    else:
        raise OutboxHold('HOLD_OWNER_EVENT_RECOVERY_BUDGET')
    if changed:
        atomic_json(root / 'cursor.json', meta)


def proof_projection(value):
    """No arbitrary result text, prompts, file contents, URLs or credentials."""
    if not isinstance(value, dict):
        return None
    kind = value.get('kind')
    common = {}
    for key in ('receipt_sha256', 'source_sha256', 'config_sha256', 'job_sha256'):
        if isinstance(value.get(key), str) and SHA.fullmatch(value[key]):
            common[key] = value[key]
    if kind in ('bounded_native_component_check', 'bounded_native_plan_step', 'bounded_native_plan_join') and all(k in common for k in ('receipt_sha256', 'source_sha256')):
        blockers = value.get('blockers') or []
        if not isinstance(blockers, list):
            return None
        result = {'kind': kind, **common, 'scope': safe_code(value.get('scope')),
                  'blockers': [safe_code(item) for item in blockers[:12]]}
        if type(value.get('verified_children')) is int and 0 <= value['verified_children'] <= 6:
            result['verified_children'] = value['verified_children']
        return result
    if (kind == 'bounded_native_s03_index' and all(key in common for key in ('receipt_sha256', 'source_sha256'))
            and value.get('scope') == 'BOUNDED_S03_VECTOR_INDEX'
            and all(type(value.get(key)) is int and 0 <= value[key] <= 1_000_000 for key in ('indexed', 'stale_remaining'))
            and type(value.get('training_examples_accepted')) is int and value['training_examples_accepted'] == 0):
        return {'kind': kind, **common, 'scope': 'BOUNDED_S03_VECTOR_INDEX',
                'indexed': value['indexed'], 'stale_remaining': value['stale_remaining'],
                'training_examples_accepted': 0, 'blockers': []}
    if kind == 'native_supervisor_running' and value.get('state') == 'RUNNING' and type(value.get('pid')) is int and value['pid'] > 0:
        if value.get('service') not in ('nox-priority-scheduler', 'nox-gpu-watchdog-t865u'):
            return None
        return {'kind': kind, 'service': value['service'], 'state': 'RUNNING', 'pid': value['pid']}
    if kind == 'native_gguf_header' and value.get('magic') == 'GGUF' and type(value.get('bytes')) is int and value['bytes'] > 10_000_000_000:
        return {'kind': kind, 'bytes': value['bytes'], 'mtime_ns': value.get('mtime_ns') if type(value.get('mtime_ns')) is int else None,
                'scope': 'FILE_HEADER_ONLY'}
    if kind == 'native_worker_configuration' and value.get('workers') == 6 and 'config_sha256' in common:
        return {'kind': kind, **common, 'workers': 6, 'scope': 'CONFIGURATION_ONLY'}
    if kind == 'native_http_health' and value.get('port') in (8080, 8081, 8082) and value.get('http_status') == 200:
        return {'kind': kind, 'port': value['port'], 'http_status': 200, 'scope': 'HEALTH_ONLY'}
    if kind == 'native_adapter_receipt' and type(value.get('step')) is int and value['step'] > 0 and 'receipt_sha256' in common:
        return {'kind': kind, **common, 'step': value['step'], 'scope': 'RECEIPT_METADATA_ONLY'}
    if kind == 'native_cgroup_budget':
        keys = ('cpu_quota_cores', 'memory_max', 'memory_current')
        if all(type(value.get(k)) in (float, int) and math.isfinite(value[k]) and value[k] > 0 for k in keys):
            return {'kind': kind, **{k: value[k] for k in keys}, 'scope': 'OBSERVED_RESOURCE_BUDGET'}
    if kind == 'native_media_output' and 'job_sha256' in common and value.get('media_kind') in ('image', 'video'):
        outputs = value.get('outputs')
        if not isinstance(outputs, list) or not 1 <= len(outputs) <= 4:
            return None
        clean = []
        for row in outputs:
            if (not isinstance(row, dict) or not isinstance(row.get('sha256'), str) or not SHA.fullmatch(row['sha256'])
                    or not all(type(row.get(k)) is int and row[k] > 0 for k in ('bytes', 'width', 'height', 'frames'))):
                return None
            clean.append({k: row[k] for k in ('sha256', 'bytes', 'width', 'height', 'frames')})
        return {'kind': kind, **common, 'media_kind': value['media_kind'], 'outputs': clean,
                'scope': 'DECODE_AND_OUTPUT_HASH_VERIFIED', 'gpu1_released': value.get('gpu1_released') is True,
                'training_resume': safe_code(value.get('training_resume'))}
    return None


def project_report(record):
    if (not isinstance(record, dict) or record.get('schema') != REPORT_SCHEMA
            or record.get('kind') not in KINDS or record.get('persisted') is not True):
        raise OutboxHold('HOLD_OWNER_REPORT_SCHEMA')
    kind = record['kind']
    proof = proof_projection(record.get('verification'))
    if kind == 'task_verified' and proof is None:
        raise OutboxHold('HOLD_OWNER_REPORT_NOT_VERIFIED')
    if kind == 'repair_verified':
        repair = record.get('repair') or {}
        proof = proof_projection({'kind': 'native_supervisor_running', **(repair.get('after') or {}),
                                  'service': repair.get('service')})
        if proof is None or repair.get('command_rc') != 0:
            raise OutboxHold('HOLD_OWNER_REPAIR_NOT_VERIFIED')
    task = record.get('task') or {}
    task_id = safe_id(task.get('id'))
    claim = task.get('claim') if isinstance(task.get('claim'), str) and re.fullmatch(r'[0-9a-f]{24}', task['claim']) else None
    lifecycle = record.get('lifecycle') or {}
    result = {'kind': kind, 'task': {'id': task_id, 'handler': safe_id(task.get('handler')), 'claim': claim},
              'state': safe_code(record.get('state')), 'verification': proof,
              'lifecycle': {key: safe_code(lifecycle.get(key)) for key in ('memory', 'memory_retrieval', 'senior', 'research', 'optimization')},
              'learning': safe_code(record.get('learning'), 'NOT_ACCEPTED'),
              'journal_sha256': record.get('journal_sha256') if SHA.fullmatch(str(record.get('journal_sha256', ''))) else None}
    if kind == 'task_progress':
        progress = record.get('progress') or {}
        metric = progress.get('metric')
        if metric not in ('bytes', 'optimizer_steps', 'generation_submitted'):
            raise OutboxHold('HOLD_OWNER_PROGRESS_METRIC')
        current, total = progress.get('current'), progress.get('total')
        if (type(current) is not int or current < 1 or type(total) is not int or total < current
                or not SHA.fullmatch(str(progress.get('evidence_sha256', '')))):
            raise OutboxHold('HOLD_OWNER_PROGRESS_PROOF')
        result['progress'] = {'metric': metric, 'current': current, 'total': total,
                              'evidence_sha256': progress['evidence_sha256']}
    return result


def _text(event):
    kind, proof = event['kind'], event.get('verification') or {}
    if kind == 'task_verified':
        if proof.get('kind') == 'bounded_native_s03_index':
            return 'Общая память обновлена', ('Проверена индексация записей: ' + str(proof['indexed'])
                + '. Ожидают обновления: ' + str(proof['stale_remaining'])
                + '. Архивные тексты не приняты в обучающий набор автоматически.')
        if proof.get('kind') in ('bounded_native_component_check', 'bounded_native_plan_step', 'bounded_native_plan_join'):
            count = len(proof.get('blockers') or [])
            return 'Проверка завершена', 'Проверка задачи выполнена и подтверждена квитанцией.' + (
                ' Остались ограничения: ' + str(count) + '.' if count else '')
        if proof.get('kind') == 'native_media_output':
            return ('Изображение готово' if proof['media_kind'] == 'image' else 'Видео готово'), 'Результат декодирован; размеры и контрольные суммы файлов проверены.'
        return 'Результат проверен', 'Задача завершена в пределах указанной проверки.'
    if kind == 'repair_verified':
        return 'Сервис восстановлен', 'Запуск разрешённого сервиса подтверждён. Исходная задача ещё должна пройти повторную проверку.'
    if kind == 'task_failed':
        return 'Обнаружена ошибка', 'Исполнение не дало проверенного результата. Причина и состояние восстановления сохранены.'
    if kind == 'verification_pending':
        return 'Результат требует проверки', 'Обработчик сообщил о завершении, но независимого подтверждения пока нет.'
    if kind == 'task_blocked':
        return 'Исполнение приостановлено', 'Действует остановка владельца или не выполнено необходимое условие допуска.'
    return 'Есть подтверждённый прогресс', 'Получено новое наблюдение выполнения. Готовность результата ещё не заявляется.'


def publish(record, now=None):
    event = project_report(record)
    when = time.time() if now is None else float(now)
    # A repeated check of unchanged evidence is not new completed work.
    identity = {k: event[k] for k in ('kind', 'state', 'verification')}
    identity['task_id'] = event['task']['id']
    if event['kind'] != 'task_verified':
        identity['claim'] = event['task']['claim']
    if 'progress' in event:
        identity['progress'] = event['progress']
    key = digest(identity)
    with locked() as root:
        meta = _meta(root)
        _recover(root, meta)
        marker = root / 'dedup' / (key + '.json')
        if marker.exists():
            return {'state': 'DUPLICATE', 'sequence': read_json(marker)['sequence']}
        channel = digest({'task': event['task']['id'], 'kind': event['kind'], 'state': event['state']})
        cooldown_path = root / 'cooldowns' / (channel + '.json')
        old = read_json(cooldown_path) if cooldown_path.exists() else {}
        interval = ERROR_COOLDOWN if event['kind'] in ('task_failed', 'task_blocked', 'verification_pending') else 0
        if event['kind'] == 'task_progress':
            interval = PROGRESS_COOLDOWN
            previous = old.get('progress') or {}
            progress = event['progress']
            current, total = progress['current'], progress['total']
            previous_current = previous.get('current', 0) if previous.get('metric') == progress['metric'] and previous.get('total') == total else 0
            delta = current - previous_current
            floor = {'bytes': 256 * 1024**2, 'optimizer_steps': 5, 'generation_submitted': 1}[progress['metric']]
            if delta < floor and current < total:
                return {'state': 'BELOW_PROGRESS_THRESHOLD'}
            if previous_current and current < total and delta / total < 0.05:
                return {'state': 'BELOW_PROGRESS_THRESHOLD'}
        if interval and old and when - float(old.get('at', 0)) < interval:
            return {'state': 'COOLDOWN'}
        sequence = meta['last_sequence'] + 1
        title, message = _text(event)
        row = {'schema': SCHEMA, 'sequence': sequence, 'event_id': key[:32], 'dedup_sha256': key,
               'created_at': when, 'title': title, 'message': message,
               'severity': 'info' if event['kind'] in ('task_verified', 'task_progress', 'repair_verified') else 'warning',
               **event}
        atomic_json(_event_path(root, sequence), row)
        atomic_json(marker, {'sequence': sequence, 'dedup_sha256': key})
        atomic_json(cooldown_path, {'at': when, 'progress': event.get('progress')})
        meta['last_sequence'] = sequence
        atomic_json(root / 'cursor.json', meta)
        return {'state': 'RECORDED', 'sequence': sequence, 'event_id': row['event_id']}


def events_after(cursor=None, limit=20):
    if cursor is not None and (type(cursor) is not int or not 0 <= cursor < 10**15):
        raise ValueError('INVALID_EVENT_CURSOR')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('INVALID_EVENT_LIMIT')
    # A crash may persist the event before its cursor. Repair under the existing
    # exclusive, nonblocking lock so reconnect does not depend on another publish.
    with locked() as root:
        meta = _meta(root)
        _recover(root, meta)
        latest = meta['last_sequence']
        start = max(0, latest - limit) if cursor is None else min(cursor, latest)
        rows = []
        for sequence in range(start + 1, min(latest, start + limit) + 1):
            row = read_json(_event_path(root, sequence))
            if row.get('schema') != SCHEMA or row.get('sequence') != sequence:
                raise OutboxHold('HOLD_OWNER_EVENT_READBACK')
            rows.append(row)
        return {'schema': 'NOX_OWNER_EVENTS_V1', 'state': 'OBSERVED', 'events': rows,
                'next_cursor': rows[-1]['sequence'] if rows else start, 'latest_cursor': latest,
                'has_more': bool(rows and rows[-1]['sequence'] < latest),
                'initial_snapshot': cursor is None, 'delivery': 'OWNER_SESSION_POLL_ONLY'}



def _readonly_flags(directory=False):
    # Require O_NOATIME so this reader does not update event-store access times.
    noatime=getattr(os,'O_NOATIME',0)
    if not noatime:
        raise OutboxHold('HOLD_OWNER_EVENTS_NOATIME_UNAVAILABLE')
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0)|noatime
    if directory:
        flags|=os.O_DIRECTORY
    return flags


def _readonly_identity(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _readonly_directory(parent_fd,name):
    fd=os.open(name,_readonly_flags(True),dir_fd=parent_fd)
    info=os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid():
        os.close(fd)
        raise OutboxHold('HOLD_OWNER_EVENTS_DIRECTORY')
    return fd


@contextmanager
def _readonly_event_directories():
    """Anchor existing directories only; never mkdir, create a lock or recover."""
    fds=[]
    try:
        root_fd=os.open('/',_readonly_flags(True)); fds.append(root_fd)
        home_fd=_readonly_directory(root_fd,'root'); fds.append(home_fd)
        nox_fd=_readonly_directory(home_fd,'nox'); fds.append(nox_fd)
        state_fd=_readonly_directory(nox_fd,'state'); fds.append(state_fd)
        owner_fd=_readonly_directory(state_fd,'owner_events'); fds.append(owner_fd)
        events_fd=_readonly_directory(owner_fd,'events'); fds.append(events_fd)
        for fd in (owner_fd,events_fd):
            if stat.S_IMODE(os.fstat(fd).st_mode)&0o077:
                raise OutboxHold('HOLD_OWNER_EVENTS_DIRECTORY_MODE')
        yield (root_fd,home_fd,nox_fd,state_fd,owner_fd,events_fd)
        for parent_fd,name,fd in (
            (root_fd,'root',home_fd),(home_fd,'nox',nox_fd),
            (nox_fd,'state',state_fd),(state_fd,'owner_events',owner_fd),
            (owner_fd,'events',events_fd)):
            current=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            if (not stat.S_ISDIR(current.st_mode)
                    or _readonly_identity(current)!=_readonly_identity(os.fstat(fd))):
                raise OutboxHold('HOLD_OWNER_EVENTS_DIRECTORY_CHANGED')
    except OSError as exc:
        raise OutboxHold('HOLD_OWNER_EVENTS_READONLY_OPEN') from exc
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


def _readonly_json_at(dir_fd,name,limit=MAX_EVENT_BYTES):
    fd=os.open(name,_readonly_flags(False),dir_fd=dir_fd)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)&0o077
                or before.st_size<0 or before.st_size>limit):
            raise OutboxHold('HOLD_OWNER_EVENTS_FILE')
        raw=os.read(fd,limit+1)
        after=os.fstat(fd)
        try:
            current=os.stat(name,dir_fd=dir_fd,follow_symlinks=False)
        except OSError as exc:
            raise OutboxHold('HOLD_OWNER_EVENTS_FILE_CHANGED') from exc
        if (len(raw)>limit or len(raw)!=before.st_size
                or _readonly_identity(before)!=_readonly_identity(after)
                or _readonly_identity(after)!=_readonly_identity(current)):
            raise OutboxHold('HOLD_OWNER_EVENTS_FILE_CHANGED')
        def unique_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise OutboxHold('HOLD_OWNER_EVENTS_DUPLICATE_KEY')
                result[key]=value
            return result
        try:
            value=json.loads(raw,object_pairs_hook=unique_pairs,
                             parse_constant=lambda _value: (_ for _ in ()).throw(
                                 OutboxHold('HOLD_OWNER_EVENTS_NONFINITE')))
        except (ValueError,UnicodeDecodeError) as exc:
            if isinstance(exc,OutboxHold):
                raise
            raise OutboxHold('HOLD_OWNER_EVENTS_JSON') from exc
        return value,raw,_readonly_identity(after)
    finally:
        os.close(fd)


def _readonly_entry_exists(dir_fd,name):
    try:
        os.stat(name,dir_fd=dir_fd,follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise OutboxHold('HOLD_OWNER_EVENTS_ENTRY') from exc


def _readonly_validate_event(row,sequence):
    if (not isinstance(row,dict) or row.get('schema')!=SCHEMA
            or row.get('sequence')!=sequence
            or not SHA.fullmatch(str(row.get('dedup_sha256','')))):
        raise OutboxHold('HOLD_OWNER_EVENT_READBACK')
    return row


def events_snapshot_readonly(cursor=None,limit=20):
    """Bounded optimistic snapshot; no _recover, index writes, lock creation or event writes."""
    if cursor is not None and (type(cursor) is not int or not 0<=cursor<10**15):
        raise ValueError('INVALID_EVENT_CURSOR')
    if type(limit) is not int or not 1<=limit<=50:
        raise ValueError('INVALID_EVENT_LIMIT')
    with _readonly_event_directories() as (_root_fd,_home_fd,_nox_fd,
                                           _state_fd,owner_fd,events_fd):
        try:
            before_value,before_raw,before_identity=_readonly_json_at(owner_fd,'cursor.json')
        except FileNotFoundError:
            before_value,before_raw,before_identity=None,None,None
        if before_value is None:
            latest=0
        else:
            if (not isinstance(before_value,dict)
                    or before_value.get('schema')!='NOX_OWNER_EVENT_CURSOR_V1'
                    or type(before_value.get('last_sequence')) is not int
                    or not 0<=before_value['last_sequence']<10**15):
                raise OutboxHold('HOLD_OWNER_EVENT_CURSOR')
            latest=before_value['last_sequence']
        next_name=str(latest+1).zfill(16)+'.json'
        if _readonly_entry_exists(events_fd,next_name):
            raise OutboxHold('HOLD_OWNER_EVENT_RECOVERY_PENDING')
        if latest:
            _readonly_validate_event(
                _readonly_json_at(events_fd,str(latest).zfill(16)+'.json')[0],latest
            )
        start=max(0,latest-limit) if cursor is None else min(cursor,latest)
        rows=[]
        for sequence in range(start+1,min(latest,start+limit)+1):
            row=_readonly_json_at(events_fd,str(sequence).zfill(16)+'.json')[0]
            rows.append(_readonly_validate_event(row,sequence))
        try:
            after_value,after_raw,after_identity=_readonly_json_at(owner_fd,'cursor.json')
        except FileNotFoundError:
            after_value,after_raw,after_identity=None,None,None
        if ((before_value is None)!=(after_value is None)
                or before_raw!=after_raw or before_identity!=after_identity
                or _readonly_entry_exists(events_fd,next_name)):
            raise OutboxHold('HOLD_OWNER_EVENT_SNAPSHOT_CHANGED')
        return {'schema':'NOX_OWNER_EVENTS_V1','state':'OBSERVED','events':rows,
                'next_cursor':rows[-1]['sequence'] if rows else start,
                'latest_cursor':latest,
                'has_more':bool(rows and rows[-1]['sequence']<latest),
                'initial_snapshot':cursor is None,'delivery':'OWNER_SESSION_POLL_ONLY',
                'read_only_snapshot':True,'recovery_performed':False,
                'event_outbox_writes':0}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OutboxHold('HOLD_LOCAL_HEALTH_REDIRECT')


def _model_health():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open('http://127.0.0.1:8081/health', timeout=0.25) as response:
            return {'state': 'READY' if response.status == 200 else 'UNAVAILABLE', 'http_status': response.status}
    except urllib.error.HTTPError as exc:
        loading = False
        if exc.code == 503:
            try:
                value = json.loads(exc.read(4096))
                message = (value.get('error') or {}).get('message')
                loading = isinstance(message, str) and message.lower().strip() in ('loading model', 'model is loading', 'model loading')
            except (ValueError, AttributeError):
                pass
        return {'state': 'LOADING' if loading else 'UNAVAILABLE', 'http_status': exc.code}
    except (OSError, OutboxHold):
        return {'state': 'UNAVAILABLE', 'http_status': None}


def _shared_memory_ready():
    path = ROOT / 'kb/knowledge.sqlite'
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=0.05) as database:
            database.execute('PRAGMA query_only=ON')
            return database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='s03_items'").fetchone() is not None
    except sqlite3.Error:
        return False


def availability(now=None):
    """Small current observations, not an idle event or a consciousness claim."""
    when = time.time() if now is None else float(now)
    if not _AVAILABILITY_LOCK.acquire(blocking=False):
        old = _AVAILABILITY_CACHE.get('value')
        if isinstance(old, dict) and old.get('_root') == str(ROOT):
            return {key: value for key, value in old.items() if key != '_root'} | {'cache_reused': True}
        return {'state': 'unknown', 'reason': 'OBSERVATION_BUSY'}
    try:
        old = _AVAILABILITY_CACHE.get('value')
        if isinstance(old, dict) and old.get('_root') == str(ROOT) and 0 <= when - _AVAILABILITY_CACHE['at'] < 5:
            return {key: value for key, value in old.items() if key != '_root'} | {'cache_reused': True}
        workers_path = ROOT / 'status/agents_t856u.json'
        workers_fresh, busy, configured = False, None, None
        try:
            doc = read_json(workers_path, 750000)
            rows = doc.get('workers')
            if (isinstance(rows, list) and len(rows) == 6 and doc.get('n') == 6
                    and all(isinstance(row, dict) and re.fullmatch(r'nox-agent-[0-9]{2}', str(row.get('id', '')))
                            and row.get('status') in ('idle', 'busy') for row in rows)
                    and len({row['id'] for row in rows}) == 6
                    and all((row['status'] == 'busy') == isinstance(row.get('current_task'), dict) for row in rows)):
                claims = [row['current_task'].get('id') for row in rows if row['status'] == 'busy']
                if len(claims) == len(set(claims)) and all(isinstance(value, str) for value in claims):
                    workers_fresh = -5 <= when - workers_path.stat().st_mtime <= 45
                    configured = 6
                    busy = sum(row['status'] == 'busy' for row in rows) if workers_fresh else None
        except (OSError, ValueError, TypeError, OutboxHold):
            pass
        model = _model_health()
        memory_ready = _shared_memory_ready()
        held = (ROOT / 'state/TRAIN_HOLD.flag').exists() or (ROOT / 'state/TRAIN_HOLD.flag').is_symlink()
        pause = (ROOT / 'state/TRAIN_PAUSE_REQUEST.flag').exists() or (ROOT / 'state/TRAIN_PAUSE_REQUEST.flag').is_symlink()
        training = {'state': 'HELD' if held else ('CHECKPOINT_YIELD_REQUESTED' if pause else 'UNKNOWN'),
                    'reason': 'DURABLE_TRAIN_HOLD_PRESENT' if held else ('DURABLE_PAUSE_REQUEST_PRESENT' if pause else 'NO_FRESH_TRAINING_OBSERVATION')}
        try:
            heartbeat = ROOT / 'status/train_volta_t866u.json'
            row = read_json(heartbeat, 16000)
            if not held and not pause and -5 <= when - heartbeat.stat().st_mtime <= 90 and row.get('phase') in ('loading_owner_hybrid', 'train_owner_hybrid'):
                training.update(state='LOADING_HEARTBEAT_OBSERVED' if row['phase'] == 'loading_owner_hybrid' else 'TRAINING_HEARTBEAT_OBSERVED',
                                reason='FRESH_NATIVE_HEARTBEAT_PROCESS_LIVENESS_NOT_RECHECKED')
        except (OSError, ValueError, TypeError, OutboxHold):
            pass
        ready = model['state'] == 'READY' and memory_ready and workers_fresh
        state = ('busy' if busy else 'awake') if ready else ('offline' if model['state'] == 'UNAVAILABLE' and not memory_ready and not workers_fresh else 'drowsy')
        value = {'schema': 'NOX_OWNER_AVAILABILITY_V1', 'state': state, 'observed_at': when,
                 'basis': 'CURRENT_LOCAL_HEALTH_AND_FRESH_NATIVE_STATUS', 'chat_model': model,
                 'shared_memory_readable': memory_ready, 'dispatcher_status_fresh': workers_fresh,
                 'configured_workers': configured, 'busy_workers': busy, 'training': training,
                 'policy': {'continuous_core': ['chat', 'shared_memory', 'dispatcher', 'owner_reports'],
                            'background_learning_yields_by_checkpoint': True,
                            'reports_do_not_stop_core': True}, 'cache_reused': False}
        _AVAILABILITY_CACHE.update(at=when, value={**value, '_root': str(ROOT)})
        return value
    finally:
        _AVAILABILITY_LOCK.release()


def register_owner_events(app, trusted):
    """Attach to the existing app and its exact owner-session auth callbacks."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    globals()['Request'] = Request
    check, reject = trusted.get('_session_ok'), trusted.get('_unauthorized')
    if not callable(check) or not callable(reject):
        raise OutboxHold('HOLD_OWNER_EVENTS_AUTH_CALLBACK')
    if any(getattr(route, 'path', None) in ('/api/ui/events', '/api/ui/events/snapshot') for route in app.routes):
        raise OutboxHold('HOLD_OWNER_EVENTS_ROUTE_EXISTS')
    @app.get('/api/ui/events/snapshot')
    async def owner_events_snapshot(request: Request):
        # Exact owner-session auth; the snapshot reader never creates or repairs outbox state.
        if not check(request):
            return reject()
        try:
            cursor_text = request.query_params.get('cursor')
            limit_text = request.query_params.get('limit', '20')
            if ((cursor_text is not None and not re.fullmatch(r'[0-9]{1,15}', cursor_text))
                    or not re.fullmatch(r'[0-9]{1,2}', limit_text)):
                raise ValueError('INVALID_EVENT_QUERY')
            value = await asyncio.to_thread(
                events_snapshot_readonly,
                None if cursor_text is None else int(cursor_text),
                int(limit_text))
            return JSONResponse(value, headers={'Cache-Control': 'no-store'})
        except ValueError:
            return JSONResponse({'state': 'INVALID_EVENT_QUERY'}, status_code=422, headers={'Cache-Control': 'no-store'})
        except (OSError, OutboxHold):
            return JSONResponse({'state': 'EVENTS_TEMPORARILY_UNAVAILABLE'}, status_code=503, headers={'Cache-Control': 'no-store'})
    @app.get('/api/ui/events')
    async def owner_events(request: Request):
        # Check before parsing or opening any private event file.
        if not check(request):
            return reject()
        try:
            cursor_text = request.query_params.get('cursor')
            limit_text = request.query_params.get('limit', '20')
            if ((cursor_text is not None and not re.fullmatch(r'[0-9]{1,15}', cursor_text))
                    or not re.fullmatch(r'[0-9]{1,2}', limit_text)):
                raise ValueError('INVALID_EVENT_QUERY')
            value = await asyncio.to_thread(events_after, None if cursor_text is None else int(cursor_text), int(limit_text))
            value['availability'] = await asyncio.to_thread(availability)
            return JSONResponse(value, headers={'Cache-Control': 'no-store'})
        except ValueError:
            return JSONResponse({'state': 'INVALID_EVENT_QUERY'}, status_code=422, headers={'Cache-Control': 'no-store'})
        except (OSError, OutboxHold):
            return JSONResponse({'state': 'EVENTS_TEMPORARILY_UNAVAILABLE'}, status_code=503, headers={'Cache-Control': 'no-store'})
    return {'path': '/api/ui/events', 'authentication': 'EXISTING_OWNER_SESSION', 'schema': 'NOX_OWNER_EVENTS_V1'}
