#!/usr/bin/env python3
"""Bind three reviewed native review workers to the EXISTING NOX dispatcher.

The original queue, claim nonce, lifecycle, STOP and S03 remain authoritative.
Workers observe only fixed technical sources and ask the existing local model
for advice. An answer is a candidate, never executable code or a training win.
This module creates no daemon, HTTP route, model instance or database table.
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
import urllib.request

import owner_autonomy_pool as autonomy
from owner_subagent_processes import GateError, Subagents

ROOT = Path('/root/nox')
CONFIG = ROOT/'config/owner_native_subagents.json'
POLICY = ROOT/'state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md'
DB = ROOT/'kb/knowledge.sqlite'
ROLES = ('runtime', 'memory', 'weights')
HANDLER = 'owner_native_subagent_review'
SCHEMA = 'NOX_NATIVE_SUBAGENT_BINDING_V1'
RECEIPT = 'NOX_NATIVE_SUBAGENT_RECEIPT_V1'
MARKER = 'NOX_NATIVE_SUBAGENTS_BIND_V1'
SHA = re.compile(r'^[a-f0-9]{64}$')
CLAIM = re.compile(r'^[a-f0-9]{24}$')
POLICY_ID = 'NOX_WEB_WEIGHTS_V06'
MAX_POLICY = 65536
_BOUND = None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def plain(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (*path.parents, path)):
        raise GateError('HOLD_SUBAGENT_PATH')
    return path


def read(path, limit=262144):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise GateError('HOLD_SUBAGENT_FILE_SCOPE')
        raw = handle.read(limit+1)
        after = os.fstat(handle.fileno())
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise GateError('HOLD_SUBAGENT_FILE_CHANGED')
    return raw


def document(path, limit=262144):
    value = json.loads(read(path, limit))
    if not isinstance(value, dict):
        raise GateError('HOLD_SUBAGENT_DOCUMENT')
    return value


def owner_config():
    info = plain(CONFIG).stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise GateError('HOLD_SUBAGENT_CONFIG_OWNER_MODE')
    return document(CONFIG, 262144)


def process_identity(pid):
    try:
        fields = Path('/proc', str(int(pid)), 'stat').read_text().split(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': int(pid), 'ppid': int(fields[1]),
                'process_starttime': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def chat_priority_active():
    path = ROOT/'state/chat_active'
    try:
        return path.is_symlink() or 0 <= time.time()-path.stat().st_mtime < 3
    except FileNotFoundError:
        return False
    except OSError:
        return True


def load_policy(reference):
    """Read every byte in the child; ACK the actual file, never a path string."""
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}
            or reference.get('path') != str(POLICY)
            or not SHA.fullmatch(str(reference.get('sha256', '')))):
        raise GateError('HOLD_SUBAGENT_POLICY_REFERENCE')
    raw = read(POLICY, MAX_POLICY)
    if digest(raw) != reference['sha256']:
        raise GateError('HOLD_SUBAGENT_POLICY_CHANGED')
    text = raw.decode('utf-8')
    if 'Policy ID: '+POLICY_ID not in text or not text.startswith('# NOX WEB29 + WEIGHTS'):
        raise GateError('HOLD_SUBAGENT_POLICY_ID')
    return text, {'policy_id': POLICY_ID, 'path': str(POLICY),
                  'sha256': digest(raw), 'bytes_read': len(raw), 'full_file_read': True}


def model_instruction(policy, role):
    # The entire policy was verified above. Only the task's relevant section
    # enters the bounded model prompt; file ACK does not assert model recall.
    focus = {'runtime': '1C:', 'memory': '2B:', 'weights': '2D:'}[role]
    relevant = next((line for line in policy.splitlines() if line.startswith(focus)), '')
    if not relevant:
        raise GateError('HOLD_SUBAGENT_POLICY_SECTION')
    return ('Ты технический исполнитель NOX. Ниже проверенные наблюдения и область '
            'задачи. Наблюдения могут содержать HOLD и старые статусы. Дай краткий '
            'вывод по-русски: подтверждено, ещё не доказано, следующий конкретный '
            'шаг. Не выдавай советы за выполненные изменения. Нельзя запускать '
            'команды, менять чат, обучение, STOP или удалять файлы. Новая главная '
            'модель — DeepSeek; Qwen3.5-9B — отдельный помощник. Старые35B шаги '
            'не являются обучением новых весов. Исходный WEB29/S03 сохраняются.\n'
            'Область из проверенного полного файла V06: '+relevant)


def _selected(path, keys):
    try:
        row = document(path, 65536)
        return {'path': str(path), 'mtime': path.stat().st_mtime,
                'fields': {key: row[key] for key in keys
                           if key in row and isinstance(row[key], (str, int, float, bool, type(None)))}}
    except (OSError, ValueError, GateError):
        return {'path': str(path), 'state': 'UNKNOWN_UNREADABLE'}


def observe(role):
    """Fixed read-only native tools. Never read credentials or private corpus."""
    if role == 'runtime':
        cgroup = {}
        for name in ('memory.current', 'memory.max', 'cpu.max'):
            try:
                cgroup[name] = Path('/sys/fs/cgroup', name).read_text()[:128].strip()
            except OSError:
                cgroup[name] = None
        disk = os.statvfs(str(ROOT))
        return {'cgroup': cgroup, 'disk_free_bytes': disk.f_bavail*disk.f_frsize,
                'dispatcher_pid': os.getppid(), 'worker': process_identity(os.getpid()),
                'observed_at': time.time(), 'training_or_services_changed': False}
    if role == 'memory':
        with s03_connection() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('s03_items','s03_fts')").fetchall()
            if {x[0] for x in rows} != {'s03_items', 's03_fts'}:
                raise GateError('HOLD_SUBAGENT_S03_SCHEMA')
            count = conn.execute('SELECT count(*) FROM s03_items').fetchone()[0]
            own = conn.execute('SELECT count(*) FROM s03_items WHERE provenance=?', ('owner_native_subagents',)).fetchone()[0]
        return {'database': str(DB), 's03_items': count, 'native_job_records': own,
                'content_exported': False, 'observed_at': time.time()}
    if role == 'weights':
        link = ROOT/'models/current.gguf'
        try:
            target = link.resolve(strict=True)
            active = {'configured_path': str(link), 'target': str(target), 'bytes': target.stat().st_size,
                      'endpoint_model_identity_verified': False}
        except OSError:
            active = {'state': 'UNKNOWN_UNREADABLE'}
        return {'active_model_file': active,
                'training_status': _selected(ROOT/'status/train_volta_t866u.json',
                    ('phase', 'step', 'global_step', 'max_steps', 'loss', 'successful_optimizer_steps', 'skipped_optimizer_steps')),
                'new_model_training_verified': False, 'observed_at': time.time()}
    raise GateError('HOLD_UNREVIEWED_NATIVE_OPERATION')


def worker_input(item):
    context = item.get('_native_context')
    if (not isinstance(context, dict) or set(context) != {'policy', 'operation', 'claim'}
            or context['operation'] not in ROLES or item.get('subagent') != context['operation']
            or not CLAIM.fullmatch(str(context['claim']))):
        raise GateError('HOLD_SUBAGENT_NATIVE_CONTEXT')
    policy, ack = load_policy(context['policy'])
    facts = observe(context['operation'])
    prompt = model_instruction(policy, context['operation'])+'\nФакты: '+encoded(facts).decode()
    if len(prompt.encode()) > 8192:
        raise GateError('HOLD_SUBAGENT_MODEL_CONTEXT_BUDGET')
    proof = {'policy_ack': ack, 'operation': context['operation'], 'facts': facts,
             'facts_sha256': digest(encoded(facts)), 'claim': context['claim'],
             'worker': process_identity(os.getpid()), 'model_policy_scope': 'VERIFIED_RELEVANT_EXCERPT'}
    return {**item, 'task': prompt}, proof


@contextlib.contextmanager
def s03_connection():
    plain(DB)
    conn = sqlite3.connect(DB.as_uri()+'?mode=ro', uri=True, timeout=0.2)
    try:
        conn.execute('PRAGMA query_only=ON')
        deadline = time.monotonic()+2
        conn.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
        yield conn
    finally:
        conn.close()


def memory_text(receipt):
    return ('NOX native job '+receipt['job_id']+' '+receipt['phase']+
            ' receipt_sha256 '+digest(encoded(receipt)))


def s03_readback(receipt):
    text = memory_text(receipt)
    with s03_connection() as conn:
        rows = conn.execute("SELECT id,text,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                            (text, 'owner_native_subagents')).fetchall()
    if len(rows) != 1 or rows[0][3] != digest(('M2|'+text).encode()):
        return None
    try:
        meta = json.loads(rows[0][2])
    except (ValueError, TypeError):
        return None
    if meta.get('receipt') != receipt:
        return None
    return {'native_verified': True, 'task_id': receipt['task_id'], 'job_id': receipt['job_id'],
            'receipt_sha256': digest(encoded(receipt)), 's03_item_id': rows[0][0],
            'database': str(DB), 'phase': receipt['phase']}


def remember(receipt):
    """Existing loopback S03 API; readback handles ambiguous HTTP completion."""
    previous = s03_readback(receipt)
    if previous:
        return previous
    payload = {'text': memory_text(receipt), 'segment': 'M2', 'salience': 0.1,
               'provenance': 'owner_native_subagents', 'meta': {'receipt': receipt}}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise GateError('HOLD_SUBAGENT_S03_REDIRECT')
    request = urllib.request.Request('http://127.0.0.1:8080/nox/s03/remember',
        data=encoded(payload), method='POST', headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=4) as response:
            response.read(16385)
    except (OSError, ValueError, GateError):
        pass  # No blind second write; only exact durable readback decides.
    proof = s03_readback(receipt)
    if proof is None:
        raise GateError('HOLD_SUBAGENT_S03_WRITE_UNVERIFIED')
    return proof


MEMORY_PRESSURE_LIMIT = .95
CPU_PRESSURE_LIMIT = 50.0
IO_PRESSURE_LIMIT = 50.0
DISK_FREE_RATIO_LIMIT = .05
DISK_FREE_BYTES_LIMIT = 5 * 1024**3


def cgroup_memory_working_set(current, maximum, stat_text):
    """Exclude reclaimable inactive file cache from cgroup memory pressure."""
    if type(current) is not int or current < 0 or type(maximum) is not int or maximum <= 0:
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    if not isinstance(stat_text, str):
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    inactive_file = None
    for line in stat_text.splitlines():
        fields = line.split()
        if fields and fields[0] == 'inactive_file':
            if len(fields) != 2 or inactive_file is not None:
                raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
            try:
                inactive_file = int(fields[1])
            except ValueError as exc:
                raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA') from exc
    if inactive_file is None or inactive_file < 0:
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    inactive_file = min(inactive_file, current)
    working_set = max(0, current - inactive_file)
    return working_set, inactive_file, working_set / maximum


def psi_avg10(text):
    """Return Linux PSI some avg10 in percentage points, fail closed."""
    if not isinstance(text, str):
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    match = re.search(r'^some\s+avg10=([0-9]+(?:\.[0-9]+)?)', text, re.M)
    if not match:
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    value = float(match[1])
    if not math.isfinite(value) or value < 0:
        raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
    return value


def resource_wait_reason(snapshot):
    """One fresh chat/RAM/CPU/I/O/disk observation gates each native submit."""
    if (not isinstance(snapshot, dict) or snapshot.get('native_verified') is not True
            or snapshot.get('instance_id') != 60509551
            or snapshot.get('stop_active') is not False
            or snapshot.get('owner_scope_verified') is not True
            or snapshot.get('source_sha_verified') is not True):
        return 'HOLD_NATIVE_SUBAGENT_ADMISSION'
    numeric = ('cgroup_memory_ratio', 'cpu_pressure', 'io_pressure', 'disk_free_ratio')
    values = [snapshot.get(key) for key in numeric]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
           for value in values):
        return 'HOLD_NATIVE_SUBAGENT_RESOURCE_METADATA'
    free_bytes = snapshot.get('disk_free_bytes')
    if type(free_bytes) is not int or free_bytes < 0 or values[3] > 1:
        return 'HOLD_NATIVE_SUBAGENT_RESOURCE_METADATA'
    if (values[0] >= MEMORY_PRESSURE_LIMIT or values[1] >= CPU_PRESSURE_LIMIT
            or values[2] >= IO_PRESSURE_LIMIT or values[3] <= DISK_FREE_RATIO_LIMIT
            or free_bytes <= DISK_FREE_BYTES_LIMIT):
        return 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'
    return None


class Native:
    def __init__(self, namespace):
        self.ns = namespace
        self.config = owner_config()
        if (self.config.get('schema') != SCHEMA or self.config.get('policy_id') != POLICY_ID
                or self.config.get('mode') != 'NORMAL' or self.config.get('target') != 3):
            raise GateError('HOLD_SUBAGENT_INSTALL_CONFIG')
        self.policy = self.config['policy']
        load_policy(self.policy)
        self.source = digest(read(Path(__file__)))
        pins = self.config.get('module_pins', {})
        for name in ('owner_subagent_processes.py', 'owner_autonomy_pool.py', 'owner_subagent_dispatcher.py'):
            if digest(read(Path(__file__).parent/name)) != pins.get(name):
                raise GateError('HOLD_SUBAGENT_INSTALLED_SOURCE')
        self.catalog = self.config['catalog']
        if digest(encoded(self.catalog)) != self.config.get('catalog_sha256'):
            raise GateError('HOLD_SUBAGENT_CATALOG_CHANGED')
        autonomy.validate_submission(self.catalog, allowed_handlers={HANDLER})
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        self.pool = None
        self.state = None
        self.completed = {}
        self.interrupted = {}
        self.lease_fd = None
        self.last_tick = 0.0
        self.last_status = {'state': 'NOT_YET_ADMITTED', 'jobs_started': 0}
        self.admissions = {}

    def allowed_handlers(self):
        return {HANDLER}

    def owner_allowed(self):
        return self.config.get('owner_authorized') is True and self.config.get('instance_id') == 60509551

    def stop_active(self):
        path = ROOT/'state/STOP'
        return self.ns['owner_mentor'].stop_active() is not False or path.exists() or path.is_symlink()

    def writer_lease(self):
        with self.lock:
            if self.lease_fd is None:
                path = plain(ROOT/'state/dispatcher/native_subagents.lock')
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    return False
                self.lease_fd = fd
            return True

    def read_reviewed_catalog(self):
        load_policy(self.policy)
        latest = owner_config()
        if any(latest.get(key) != self.config.get(key) for key in (
                'schema', 'policy', 'policy_id', 'owner_request', 'owner_source_sha',
                'module_pins', 'instance_id', 'owner_authorized', 'mode', 'target')):
            raise GateError('HOLD_SUBAGENT_CONFIG_SCOPE_CHANGED')
        catalog = latest.get('catalog')
        if digest(encoded(catalog)) != latest.get('catalog_sha256'):
            raise GateError('HOLD_SUBAGENT_CATALOG_CHANGED')
        rows = autonomy.validate_submission(catalog, allowed_handlers={HANDLER})['ordered']
        if any(set(row['params']) != {'role'} or row['params']['role'] not in ROLES
               or row['source_sha256'] != self.policy['sha256'] for row in rows):
            raise GateError('HOLD_SUBAGENT_CATALOG_SCOPE')
        self.catalog = catalog
        return self.catalog

    def read_resource_snapshot(self):
        if chat_priority_active():
            raise autonomy.AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                'http://127.0.0.1:8081/slots', timeout=1) as response:
            slots = json.loads(response.read(262145))
        if not isinstance(slots, list) or not slots or len(slots) > 128:
            raise autonomy.AutoHold('HOLD_NATIVE_MODEL_SLOTS_UNKNOWN')
        flags = [slot.get('is_processing', slot.get('processing')) for slot in slots
                 if isinstance(slot, dict)]
        if len(flags) != len(slots) or any(type(flag) is not bool for flag in flags):
            raise autonomy.AutoHold('HOLD_NATIVE_MODEL_SLOTS_UNKNOWN')
        with self.lock:
            owned = len(self.pool.active) if self.pool is not None else 0
        if sum(flags) > owned:
            raise autonomy.AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        current = int(Path('/sys/fs/cgroup/memory.current').read_text().strip())
        maximum_text = Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if maximum_text == 'max':
            raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
        maximum = int(maximum_text)
        memory_stat = Path('/sys/fs/cgroup/memory.stat').read_text()
        working_set, inactive_file, memory_ratio = cgroup_memory_working_set(
            current, maximum, memory_stat)
        cpu_pressure = psi_avg10(Path('/sys/fs/cgroup/cpu.pressure').read_text())
        io_pressure = psi_avg10(Path('/sys/fs/cgroup/io.pressure').read_text())
        disk = os.statvfs(ROOT)
        if disk.f_blocks <= 0 or disk.f_frsize <= 0:
            raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
        disk_total_bytes = disk.f_blocks * disk.f_frsize
        disk_free_bytes = disk.f_bavail * disk.f_frsize
        if disk_free_bytes < 0 or disk_free_bytes > disk_total_bytes:
            raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
        with self.ns['_qlock']:
            status = {key: value.get('status') for key, value in self.state['tasks'].items()
                      if value.get('handler') == HANDLER}
        snapshot = {'native_verified': True, 'instance_id': 60509551,
                    'stop_active': self.stop_active(), 'source_sha_verified': True,
                    'owner_scope_verified': self.owner_allowed(), 'task_status': status,
                    'cgroup_memory_ratio': memory_ratio,
                    'cgroup_memory_working_set_bytes': working_set,
                    'cgroup_memory_inactive_file_bytes': inactive_file,
                    'cpu_pressure': cpu_pressure, 'io_pressure': io_pressure,
                    'disk_free_ratio': disk_free_bytes/disk_total_bytes,
                    'disk_free_bytes': disk_free_bytes, 'gpu_available': False}
        reason = resource_wait_reason(snapshot)
        if reason:
            raise autonomy.AutoHold(reason)
        snapshot['resource_admission_allowed'] = True
        snapshot['resource_admission_observed_at'] = time.time()
        snapshot['resource_admission_snapshot_sha256'] = autonomy.fingerprint(snapshot)
        return snapshot

    def _fresh_admission_reason(self):
        # read_resource_snapshot also checks the real local chat/slot gate.
        # A previously created pool is never permission to reuse a stale check.
        try:
            return resource_wait_reason(self.read_resource_snapshot())
        except (OSError, ValueError, TypeError, KeyError, GateError):
            return 'HOLD_NATIVE_SUBAGENT_ADMISSION'

    def review_status(self):
        """Counts of the reviewed catalog only; no model prose becomes status."""
        ids = {row['id'] for row in self.catalog['tasks']}
        counts = {key: 0 for key in ('not_admitted', 'pending', 'running', 'done',
                                    'blocked', 'failed', 'unknown')}
        with self.ns['_qlock']:
            tasks = (self.state or {}).get('tasks', {})
            for task_id in ids:
                task = tasks.get(task_id)
                value = 'not_admitted' if task is None else task.get('status')
                counts[value if value in counts else 'unknown'] += 1
        with self.lock:
            active = len(self.pool.active) if self.pool is not None else 0
        return {'scope': 'NATIVE_TECHNICAL_REVIEW_CANDIDATES',
                'catalog_tasks': len(ids), 'queue_counts': counts,
                'owned_model_requests_active': active,
                'fresh_resource_check': 'BEFORE_EVERY_SUBMIT',
                'model_answers_authoritative': False, 'candidate_actions_applied': False,
                'training_updates_verified': False, 'capacity_maximum_measured': False}

    def ensure_processes(self, count):
        if count != 3 or self.stop_active():
            return False
        with self.lock:
            if self.pool is not None:
                self._drain()
                if len(self.process_readback()) != 3:
                    # Replace the pool only after all task-bound results have
                    # been drained and no worker owns an uncertain in-flight job.
                    if self.pool.active:
                        return False
                    self.close_pool()
            if self.pool is None:
                self.pool = Subagents(list(ROLES), timeout=60,
                                      worker_prepare=worker_input).__enter__()
            return len(self.process_readback()) == 3

    def process_readback(self):
        with self.lock:
            if self.pool is None:
                return []
            rows = []
            now = time.time()
            for role, child in self.pool.processes.items():
                identity = process_identity(child.pid)
                heartbeat = self.pool.heartbeats.get(role)
                if (type(heartbeat) not in (int, float) or not math.isfinite(heartbeat)
                        or identity is None or not child.is_alive()
                        or identity['ppid'] != os.getpid()):
                    continue
                age = now - heartbeat
                if not 0 <= age <= 600:
                    continue
                rows.append({**identity, 'role': role, 'native_pid_verified': True,
                    'native_heartbeat_verified': True, 'heartbeat_age_seconds': age,
                    'state': 'RUNNING', 'instance_id': 60509551, 'origin': 'existing_onehost',
                    'heartbeat_at': heartbeat, 'current_task': self.pool.active.get(role)})
            return rows

    def native_duplicate_check(self, task_id):
        with self.ns['_qlock']:
            return task_id in self.state['tasks']

    def native_queue_claim(self, task, owner_pids):
        if sorted(owner_pids) != sorted(row['pid'] for row in self.process_readback()):
            raise GateError('HOLD_SUBAGENT_POOL_IDENTITY_CHANGED')
        role = task['params'].get('role')
        if role not in ROLES or task['source_sha256'] != self.policy['sha256']:
            raise GateError('HOLD_SUBAGENT_CATALOG_SCOPE')
        job_id = 'nox-native-'+digest(encoded({'task': task['id'], 'policy': self.policy['sha256']}))[:24]
        admission = {'schema': RECEIPT, 'phase': 'QUEUE_ADMITTED_NOT_EXECUTED',
                     'task_id': task['id'], 'job_id': job_id,
                     'policy_sha256': self.policy['sha256'], 'source_sha256': self.source}
        row = {'id': task['id'], 'handler': HANDLER, 'class': 'owner_order', 'lane': 'owner_order',
               'priority': 1, 'status': 'blocked', 'deps': task['deps'],
               'locks': ['native_subagent_'+role], 'retries': 0, 'max_retries': 1,
               'timeout_sec': 90, 'title': task['title'], 'source': SCHEMA,
               'params': {'role': role, 'policy_sha256': self.policy['sha256'], 'job_id': job_id},
               'native_admission': admission, 'note': 'WAIT_S03_ADMISSION_READBACK'}
        with self.ns['_qlock']:
            if task['id'] in self.state['tasks']:
                raise GateError('HOLD_SUBAGENT_DUPLICATE_TASK')
            self.state['tasks'][task['id']] = row
            self.ns['save_state'](self.state)
        proof = remember(admission)
        with self.ns['_qlock']:
            row.update(status='pending', note='ADMITTED_NOT_EXECUTED', native_admission_s03=proof)
            self.ns['save_state'](self.state)
        self.admissions[task['id']] = admission
        return {'job_id': job_id}

    def s03_readback(self, task_id, job_id):
        receipt = self.admissions.get(task_id)
        return s03_readback(receipt) if receipt and receipt['job_id'] == job_id else None

    def _claim_current(self, task, durable=False):
        with self.ns['_qlock']:
            persisted = ((document(self.ns['STATE'], 16*1024*1024) if durable else self.state)
                         ['tasks'].get(task['id'], {}))
        claim = task.get('owner_claim') or {}
        return (task.get('status') == 'running' and persisted.get('status') == 'running'
                and CLAIM.fullmatch(str(claim.get('nonce', ''))) is not None
                and persisted.get('owner_claim') == claim and claim.get('pid') == os.getpid())

    def _submit_intent_from_disk(self, task):
        with self.ns['_qlock']:
            persisted = document(self.ns['STATE'], 16*1024*1024)
            row = persisted.get('tasks', {}).get(task['id'], {})
            intent = row.get('native_submit_intent')
        if intent is None:
            return None
        claim = task.get('owner_claim') or {}
        expected = {'task_id': task['id'], 'claim_nonce': claim.get('nonce'),
                    'role': task.get('params', {}).get('role'),
                    'policy_sha': task.get('params', {}).get('policy_sha256'),
                    'job_id': task.get('params', {}).get('job_id')}
        if not isinstance(intent, dict) or any(intent.get(key) != value
                                               for key, value in expected.items()):
            raise GateError('HOLD_SUBAGENT_SUBMIT_INTENT_MISMATCH')
        return intent

    def _persist_submit_intent(self, task):
        claim = task.get('owner_claim') or {}
        intent = {'task_id': task['id'], 'claim_nonce': claim.get('nonce'),
                  'role': task['params']['role'], 'policy_sha': task['params']['policy_sha256'],
                  'job_id': task['params']['job_id'], 'state': 'UNCERTAIN'}
        with self.ns['_qlock']:
            durable = document(self.ns['STATE'], 16*1024*1024)
            durable_row = durable.get('tasks', {}).get(task['id'], {})
            row = self.state.get('tasks', {}).get(task['id'], {})
            if (durable_row.get('status') != 'running'
                    or durable_row.get('owner_claim') != claim
                    or row.get('status') != 'running'
                    or row.get('owner_claim') != claim):
                raise GateError('HOLD_NATIVE_OWNER_CLAIM_CHANGED')
            if durable_row.get('native_submit_intent') is not None or row.get('native_submit_intent') is not None:
                raise GateError('HOLD_SUBAGENT_SUBMIT_INTENT_EXISTS')
            row['native_submit_intent'] = intent
            self.ns['save_state'](self.state)
            readback = document(self.ns['STATE'], 16*1024*1024)
            saved = readback.get('tasks', {}).get(task['id'], {}).get('native_submit_intent')
            if saved != intent:
                raise GateError('HOLD_SUBAGENT_SUBMIT_INTENT_UNVERIFIED')
        return intent

    def _mark_submit_result_s03_verified(self, task, intent, receipt, proof):
        if (not isinstance(proof, dict) or proof.get('native_verified') is not True
                or proof.get('task_id') != task['id']
                or proof.get('job_id') != intent['job_id']):
            raise GateError('HOLD_SUBAGENT_S03_RESULT_READBACK')
        with self.ns['_qlock']:
            durable = document(self.ns['STATE'], 16*1024*1024)
            durable_row = durable.get('tasks', {}).get(task['id'], {})
            saved_intent = durable_row.get('native_submit_intent')
            if (not isinstance(saved_intent, dict)
                    or any(saved_intent.get(key) != intent.get(key)
                           for key in ('task_id', 'claim_nonce', 'role', 'policy_sha', 'job_id'))
                    or durable_row.get('owner_claim') != task.get('owner_claim')):
                raise GateError('HOLD_SUBAGENT_SUBMIT_INTENT_MISMATCH')
            row = self.state.get('tasks', {}).get(task['id'], {})
            advanced = {**saved_intent, 'state': 'S03_VERIFIED',
                        'result_sha256': digest(encoded(receipt)),
                        's03_receipt_sha256': proof['receipt_sha256']}
            row['native_submit_intent'] = advanced
            self.ns['save_state'](self.state)
            readback = document(self.ns['STATE'], 16*1024*1024)
            if readback.get('tasks', {}).get(task['id'], {}).get('native_submit_intent') != advanced:
                raise GateError('HOLD_SUBAGENT_SUBMIT_RESULT_UNVERIFIED')
        return advanced

    def _s03_verified_evidence(self, task, intent):
        """Rebuild one exact completed result from S03; never call the worker."""
        claim = task.get('owner_claim')
        params = task.get('params') or {}
        required = {'task_id', 'claim_nonce', 'role', 'policy_sha', 'job_id',
                    'state', 'result_sha256', 's03_receipt_sha256'}
        if (not isinstance(intent, dict) or set(intent) != required
                or intent.get('state') != 'S03_VERIFIED'
                or task.get('handler') != HANDLER
                or not isinstance(claim, dict)
                or not CLAIM.fullmatch(str(claim.get('nonce', '')))
                or claim.get('nonce') != intent.get('claim_nonce')
                or task.get('id') != intent.get('task_id')
                or params.get('role') != intent.get('role')
                or params.get('policy_sha256') != intent.get('policy_sha')
                or params.get('job_id') != intent.get('job_id')
                or intent.get('role') not in ROLES
                or intent.get('policy_sha') != self.policy.get('sha256')
                or not re.fullmatch(r'nox-native-[a-f0-9]{24}', str(intent.get('job_id', '')))
                or not SHA.fullmatch(str(intent.get('result_sha256', '')))
                or not SHA.fullmatch(str(intent.get('s03_receipt_sha256', '')))):
            return None
        prefix = ('NOX native job ' + intent['job_id'] +
                  ' NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED receipt_sha256 ')
        with s03_connection() as conn:
            rows = conn.execute(
                "SELECT id,text,meta,sha256 FROM s03_items "
                "WHERE segment='M2' AND provenance=? AND substr(text,1,?)=? LIMIT 2",
                ('owner_native_subagents', len(prefix), prefix)).fetchall()
        if len(rows) != 1:
            return None
        item_id, text_value, meta_raw, item_sha = rows[0]
        if (not isinstance(text_value, str) or not text_value.startswith(prefix)
                or item_sha != digest(('M2|' + text_value).encode())):
            return None
        row_receipt_sha = text_value[len(prefix):]
        if not SHA.fullmatch(row_receipt_sha):
            return None
        try:
            meta = json.loads(meta_raw)
        except (TypeError, ValueError):
            return None
        receipt = meta.get('receipt') if isinstance(meta, dict) else None
        observation = (receipt.get('worker_result') or {}).get('native_observation') if isinstance(receipt, dict) else None
        worker = observation.get('worker') if isinstance(observation, dict) else None
        policy_ack = observation.get('policy_ack') if isinstance(observation, dict) else None
        receipt_sha = digest(encoded(receipt)) if isinstance(receipt, dict) else None
        if (not isinstance(receipt, dict) or memory_text(receipt) != text_value
                or receipt_sha != row_receipt_sha
                or receipt_sha != intent.get('result_sha256')
                or receipt_sha != intent.get('s03_receipt_sha256')
                or receipt.get('schema') != RECEIPT
                or receipt.get('phase') != 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED'
                or receipt.get('task_id') != task.get('id')
                or receipt.get('job_id') != intent.get('job_id')
                or receipt.get('claim') != claim
                or receipt.get('source_sha256') != self.source
                or receipt.get('policy_sha256') != intent.get('policy_sha')
                or receipt.get('training_started') is not False
                or receipt.get('optimizer_steps_verified') is not False
                or receipt.get('service_or_weights_changed') is not False
                or not isinstance(observation, dict)
                or observation.get('claim') != claim.get('nonce')
                or not isinstance(policy_ack, dict)
                or policy_ack.get('sha256') != intent.get('policy_sha')
                or policy_ack.get('full_file_read') is not True
                or not isinstance(worker, dict)
                or worker.get('pid') != (receipt.get('worker_result') or {}).get('pid')):
            return None
        proof = s03_readback(receipt)
        if (not proof or proof.get('task_id') != task.get('id')
                or proof.get('job_id') != intent.get('job_id')
                or proof.get('receipt_sha256') != receipt_sha
                or proof.get('s03_item_id') != item_id):
            return None
        evidence = {'schema': RECEIPT, 'verified': True,
                    'scope': 'NATIVE_REVIEW_AND_S03_RECEIPT',
                    'receipt': receipt, 's03': proof,
                    'receipt_sha256': receipt_sha, 'candidate_applied': False}
        return evidence if self.verify(task, evidence) else None

    def _reconcile_s03_verified_queue(self, state):
        """Complete only a dead parent's exact S03-verified claim; no resubmit."""
        if (not self.owner_allowed() or self.stop_active()
                or chat_priority_active() or not self.writer_lease()):
            return 0
        fd = None
        try:
            fd = os.open(plain(ROOT/'state/owner_maintenance.lock'),
                         os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except (OSError, GateError):
            if fd is not None:
                os.close(fd)
            return 0
        recovered = 0
        try:
            tasks = state.get('tasks') if isinstance(state, dict) else None
            if not isinstance(tasks, dict):
                return 0
            active_ids = set(self.pool.active.values()) if self.pool is not None else set()
            for task_id, task in list(tasks.items()):
                if (not isinstance(task, dict) or task.get('id') != task_id
                        or task.get('handler') != HANDLER or task.get('status') != 'running'
                        or task_id in active_ids):
                    continue
                claim = task.get('owner_claim') or {}
                intent = task.get('native_submit_intent')
                if (not isinstance(claim, dict) or type(claim.get('pid')) is not int
                        or claim.get('pid') == os.getpid()
                        or not isinstance(intent, dict) or intent.get('state') != 'S03_VERIFIED'):
                    continue
                with self.ns['_qlock']:
                    durable = document(self.ns['STATE'], 16*1024*1024)
                    persisted = durable.get('tasks', {}).get(task_id, {})
                    if (persisted.get('status') != 'running'
                            or persisted.get('owner_claim') != claim
                            or persisted.get('native_submit_intent') != intent):
                        continue
                evidence = self._s03_verified_evidence(task, intent)
                if evidence is None:
                    continue
                verification = self.verify(task, evidence)
                if not verification:
                    continue
                if (not self.owner_allowed() or self.stop_active()
                        or chat_priority_active() or not self.writer_lease()):
                    continue
                with self.ns['_qlock']:
                    durable = document(self.ns['STATE'], 16*1024*1024)
                    persisted = durable.get('tasks', {}).get(task_id, {})
                    current = state.get('tasks', {}).get(task_id)
                    if (not isinstance(current, dict) or current.get('status') != 'running'
                            or current.get('owner_claim') != claim
                            or current.get('native_submit_intent') != intent
                            or persisted.get('status') != 'running'
                            or persisted.get('owner_claim') != claim
                            or persisted.get('native_submit_intent') != intent
                            or (current.get('result') is not None and current.get('result') != evidence)
                            or (current.get('verification') is not None
                                and current.get('verification') != verification)):
                        continue
                    current.update(status='done', result=evidence, verification=verification,
                                   note='S03_VERIFIED_RECOVERED')
                    self.ns['save_state'](state)
                    readback = document(self.ns['STATE'], 16*1024*1024).get('tasks', {}).get(task_id, {})
                    if (readback.get('status') == 'done'
                            and readback.get('owner_claim') == claim
                            and readback.get('native_submit_intent') == intent
                            and readback.get('result') == evidence
                            and readback.get('verification') == verification):
                        recovered += 1
        except (OSError, ValueError, TypeError, sqlite3.Error, GateError):
            return recovered
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
        return recovered

    def _drain(self):
        if self.pool is None:
            return
        for _ in range(32):
            event = self.pool.poll(timeout=0)
            if event is not None:
                self.completed[event['id']] = event

    def handle(self, task):
        fd = None
        try:
            fd = os.open(plain(ROOT/'state/owner_maintenance.lock'),
                         os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return self._handle(task)
        except (OSError, GateError):
            return 'wait', 'HOLD_NATIVE_MAINTENANCE_LEASE'
        finally:
            if fd is not None:
                os.close(fd)

    def _handle(self, task):
        params = task.get('params') or {}
        role = params.get('role')
        approved = next((row for row in self.catalog['tasks'] if row['id'] == task.get('id')), None)
        if (approved is None or role not in ROLES or role != approved['params'].get('role')
                or set(params) != {'role', 'policy_sha256', 'job_id'}
                or params.get('policy_sha256') != self.policy['sha256']
                or not self._claim_current(task, durable=True)):
            return False, 'HOLD_SUBAGENT_NATIVE_CLAIM'
        try:
            # A persisted intent means pool.submit may already have happened.
            # Never replay it under this or a later owner claim.
            if self._submit_intent_from_disk(task) is not None:
                return False, 'HOLD_SUBAGENT_SUBMIT_INTENT_EXISTS'
        except GateError as exc:
            return False, str(exc)
        except (OSError, ValueError):
            return False, 'HOLD_SUBAGENT_SUBMIT_INTENT_UNREADABLE'
        if self.stop_active() or not self.writer_lease():
            return 'wait', 'HOLD_OWNER_STOP_OR_WRITER_LEASE'
        if self.pool is None:
            try:
                reason = self._fresh_admission_reason()
                if reason:
                    return 'wait', reason
                if not self.ensure_processes(3):
                    return 'wait', 'HOLD_SUBAGENT_POOL_NOT_READY'
            except (OSError, ValueError, autonomy.AutoHold):
                return 'wait', 'HOLD_NATIVE_SUBAGENT_ADMISSION'
        try:
            with self.lock:
                if self.pool is None:
                    raise GateError('HOLD_SUBAGENT_POOL_NOT_READY')
                # Recheck resource admission immediately before the sole submit.
                reason = self._fresh_admission_reason()
                if reason:
                    return 'wait', reason
                self.interrupted.pop(task['id'], None)
                intent = self._persist_submit_intent(task)
                self.pool.submit({'id': task['id'], 'subagent': role, 'task': task['title'], 'depends_on': [],
                    '_native_context': {'policy': self.policy, 'operation': role,
                                        'claim': task['owner_claim']['nonce']}})
            deadline = time.monotonic()+70
            event = None
            while time.monotonic() < deadline:
                if not self._claim_current(task):
                    self.close_pool()
                    raise GateError('HOLD_NATIVE_OWNER_CLAIM_CHANGED')
                with self.lock:
                    reason = self.interrupted.pop(task['id'], None)
                    self._drain()
                    event = self.completed.pop(task['id'], None)
                stop_reason = None
                if self.stop_active():
                    stop_reason = 'WAIT_OWNER_STOP_OR_CHAT_PRIORITY'
                elif chat_priority_active():
                    stop_reason = 'WAIT_OWNER_STOP_OR_CHAT_PRIORITY'
                if event is not None:
                    break
                if stop_reason:
                    self.close_pool(stop_reason)
                    return False, 'HOLD_SUBAGENT_SUBMIT_OUTCOME_UNRESOLVED'
                if reason:
                    return False, 'HOLD_SUBAGENT_SUBMIT_INTERRUPTED'
                time.sleep(0.1)
            if event is None:
                self.close_pool()
                return False, 'HOLD_SUBAGENT_RESULT_TIMEOUT'
            if event.get('state') != 'CANDIDATE_NOT_APPLIED':
                raise GateError(event.get('state', 'HOLD_SUBAGENT_RESULT'))
            # Redact with the same queue function before storing the receipt.
            event = self.ns['owner_mentor'].clean(event)
            observation = event.get('native_observation', {})
            if (observation.get('claim') != task['owner_claim']['nonce']
                    or observation.get('policy_ack', {}).get('sha256') != self.policy['sha256']
                    or observation.get('policy_ack', {}).get('full_file_read') is not True
                    or observation.get('worker', {}).get('pid') != event['pid']):
                raise GateError('HOLD_SUBAGENT_WORKER_PROOF')
            result = {'schema': RECEIPT, 'phase': 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED',
                      'task_id': task['id'], 'job_id': params['job_id'], 'claim': task['owner_claim'],
                      'source_sha256': self.source, 'policy_sha256': self.policy['sha256'],
                      'worker_result': event, 'finished_at': time.time(),
                      'training_started': False, 'optimizer_steps_verified': False,
                      'service_or_weights_changed': False}
            if not self._claim_current(task, durable=True):
                raise GateError('HOLD_NATIVE_OWNER_CLAIM_CHANGED')
            proof = remember(result)
            self._mark_submit_result_s03_verified(task, intent, result, proof)
            # A durable result already found by the drain is committed to S03
            # before workers are torn down to yield to chat/STOP.
            if self.stop_active() or chat_priority_active():
                self.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
            return True, {'schema': RECEIPT, 'verified': True, 'scope': 'NATIVE_REVIEW_AND_S03_RECEIPT',
                          'receipt': result, 's03': proof, 'receipt_sha256': digest(encoded(result)),
                          'candidate_applied': False}
        except (OSError, ValueError, sqlite3.Error, GateError) as exc:
            return False, str(exc) if isinstance(exc, GateError) else 'HOLD_SUBAGENT_NATIVE_IO'

    def verify(self, task, evidence):
        if task.get('handler') != HANDLER or not isinstance(evidence, dict):
            return None
        receipt = evidence.get('receipt')
        if (not isinstance(receipt, dict) or receipt.get('task_id') != task.get('id')
                or receipt.get('phase') != 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED'
                or receipt.get('claim') != task.get('owner_claim')
                or receipt.get('source_sha256') != self.source
                or digest(encoded(receipt)) != evidence.get('receipt_sha256')):
            return None
        proof = s03_readback(receipt)
        if proof:
            return {'kind': 'bounded_native_component_check', 'task_id': task['id'],
                    'scope': 'NATIVE_REVIEW_AND_S03_RECEIPT', 'receipt_sha256': proof['receipt_sha256'],
                    'source_sha256': self.source, 's03_item_id': proof['s03_item_id'],
                    'candidate_applied': False, 'training_verified': False, 'blockers': []}
        return None

    def close_pool(self, reason=None):
        with self.lock:
            if self.pool is not None:
                if reason is not None:
                    for task_id in set(self.pool.active.values()) | set(self.completed):
                        self.interrupted[task_id] = reason
                    self.completed.clear()
                self.pool.__exit__(None, None, None)
                self.pool = None

    def close(self):
        self.close_pool()
        if self.lease_fd is not None:
            os.close(self.lease_fd)
            self.lease_fd = None

    def tick(self, state):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            self.state = state
            if self.stop_active():
                self.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
                self.last_status = {'state': 'HOLD_OWNER_STOP_OR_MAINTENANCE', 'jobs_started': 0}
                return
            with self.lock:
                self._drain()
            # Crash after a successful S03 admission is recoverable by exact
            # readback. A missing/ambiguous result is never blindly replayed.
            for task in list(state['tasks'].values()):
                if task.get('handler') == HANDLER and task.get('note') == 'WAIT_S03_ADMISSION_READBACK':
                    proof = s03_readback(task['native_admission'])
                    if proof:
                        with self.ns['_qlock']:
                            task.update(status='pending', note='ADMITTED_NOT_EXECUTED', native_admission_s03=proof)
                            self.ns['save_state'](state)
            if time.monotonic()-self.last_tick < 5:
                return
            self.last_tick = time.monotonic()
            recovered = self._reconcile_s03_verified_queue(state)
            self.last_status = autonomy.tick_existing_dispatcher(self.ns, state, mode='NORMAL')
            if recovered:
                self.last_status['s03_verified_queue_recovered'] = recovered
        except Exception as exc:
            self.last_status = {'state': str(exc) if isinstance(exc, GateError) else 'HOLD_NATIVE_SUBAGENT_TICK',
                                'jobs_started': 0}
        finally:
            self.tick_lock.release()


def bind_dispatcher(namespace):
    global _BOUND
    if namespace.get('_nox_owner_autonomy_native') is not None:
        raise GateError('HOLD_NATIVE_SUBAGENT_ALREADY_BOUND')
    if (not isinstance(namespace.get('HANDLERS'), dict) or '_qlock' not in namespace
            or any(not callable(namespace.get(name)) for name in ('save_state', 'write_status', 'write_agents_status', '_nox_owner_task_admitted'))
            or namespace.get('owner_mentor') is None or namespace.get('_owner_lifecycle_bound') is not True):
        raise GateError('HOLD_NATIVE_SUBAGENT_DISPATCHER_CONTRACT')
    native = Native(namespace)
    _BOUND = native
    namespace['_nox_owner_autonomy_native'] = native
    namespace['HANDLERS'][HANDLER] = native.handle
    for role in ROLES:
        namespace['LOCKS']['native_subagent_'+role] = threading.Lock()
    old_verify = namespace['owner_mentor'].verify_success
    def verify(task, evidence=None):
        return native.verify(task, evidence) if task.get('handler') == HANDLER else old_verify(task, evidence)
    namespace['owner_mentor'].verify_success = verify
    old_admission = namespace['_nox_owner_task_admitted']
    def admission(task):
        if task.get('handler') == HANDLER and (native.stop_active() or chat_priority_active()):
            return False  # Keep paused jobs pending until the original gate opens.
        return old_admission(task)
    namespace['_nox_owner_task_admitted'] = admission
    old_status, old_agents = namespace['write_status'], namespace['write_agents_status']
    def status(state):
        value = old_status(state)
        native.tick(state)  # Existing main/ticker only; no new scheduler thread.
        return value
    def agents():
        value = old_agents()
        path = namespace['AGENT_STATUS']
        row = document(path, 750000)
        row['native_subexecutors'] = {'mode': 'NORMAL', 'target': 3,
            'director': process_identity(os.getpid()), 'observed_at': time.time(),
            'workers': native.process_readback(), 'last_admission': native.last_status,
            'thread_runner_count': namespace['WORKERS'], 'same_model_shared': True,
            'review_status': native.review_status()}
        namespace['atomic_write'](path, row)
        return value
    namespace['write_status'], namespace['write_agents_status'] = status, agents
    atexit.register(native.close)


def patch_dispatcher(source, expected_sha256):
    if digest(source.encode()) != expected_sha256 or MARKER in source:
        raise GateError('HOLD_NATIVE_DISPATCHER_SOURCE_CHANGED')
    anchor = 'if __name__ == "__main__":\n    main()'
    if source.count(anchor) != 1 or 'owner_task_lifecycle.bind_dispatcher(' not in source:
        raise GateError('HOLD_NATIVE_DISPATCHER_BIND_ANCHOR')
    result = source.replace(anchor, '# '+MARKER+'\nimport owner_subagent_dispatcher\n'
                            'owner_subagent_dispatcher.bind_dispatcher(globals())\n\n'+anchor)
    ast.parse(result)
    return result
