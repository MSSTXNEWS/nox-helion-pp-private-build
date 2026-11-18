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
import owner_project_executor as project_executor
from owner_subagent_processes import GateError, Subagents

ROOT = Path('/root/nox')
CONFIG = ROOT/'config/owner_native_subagents.json'
POLICY = ROOT/'state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md'
DB = ROOT/'kb/knowledge.sqlite'
ROLES = ('runtime', 'memory', 'weights')
HANDLER = 'owner_native_subagent_review'
LEAF_HANDLER = 'owner_native_typed_leaf'
LEAF_MODE = 'NATIVE_LEAF_V1'
PROJECT_HANDLER = project_executor.PROJECT_HANDLER
PROJECT_MODE = project_executor.PROJECT_MODE
LEAF_OPERATIONS = {
    'chat_health': ('Q1_RUNTIME_CHAT', 'HEALTH_ONLY'),
    'memory_schema': ('Q2_MEMORY_KNOWLEDGE', 'READ_ONLY_MEMORY_SCHEMA_STATUS'),
    'training_prerequisites': ('Q3_TRAINING_WEIGHTS', 'TRAINING_PREREQUISITES_ONLY'),
    'queue_regression': ('Q4_INTEGRATION_ACCEPTANCE', 'SOURCE_QUEUE_REGRESSION_SUBSET_ONLY'),
}
LEAF_SOURCE_FILES = ('owner_component_tasks.py', 'owner_task_plans.py',
                     'test_owner_four_queue.py', 'test_owner_normal3_continuity.py',
                     'owner_resource_policy.py')
PROJECT_FILES = {
    'work_tasks_sha256': ROOT/'state/dispatcher/project_work_tasks.json',
    'work_ideas_sha256': ROOT/'state/dispatcher/project_work_ideas.json',
    'routing_sha256': ROOT/'state/dispatcher/project_routing_4q.json',
}
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


def _leaf_sources(pins):
    if not isinstance(pins, dict) or set(pins) != set(LEAF_SOURCE_FILES):
        raise GateError('HOLD_NATIVE_LEAF_SOURCE_PINS')
    for name, expected in pins.items():
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise GateError('HOLD_NATIVE_LEAF_SOURCE_PINS')
        if digest(read(Path(__file__).parent/name)) != expected:
            raise GateError('HOLD_NATIVE_LEAF_SOURCE_CHANGED')


def _local_json(port, path):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise GateError('HOLD_NATIVE_LEAF_REDIRECT')
    start = time.monotonic()
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(
            'http://127.0.0.1:'+str(port)+path, timeout=4) as response:
        raw = response.read(262145)
        if response.status != 200 or len(raw) > 262144:
            raise GateError('HOLD_NATIVE_LEAF_HTTP_SCOPE')
        value = json.loads(raw)
    return value, round((time.monotonic()-start)*1000, 3)


def execute_native_leaf(item):
    """Fixed reviewed read/check operations; no model text, shell or code input."""
    context = item.get('_native_leaf_context')
    required = {'operation', 'parent_task_id', 'queue_id', 'claim', 'source_sha256', 'source_pins'}
    if (not isinstance(context, dict) or set(context) != required
            or context.get('operation') not in LEAF_OPERATIONS
            or not CLAIM.fullmatch(str(context.get('claim', '')))
            or not autonomy.ID.fullmatch(str(context.get('parent_task_id', '')))
            or context['source_sha256'] != digest(read(Path(__file__)))):
        raise GateError('HOLD_NATIVE_LEAF_CONTEXT')
    operation = context['operation']
    queue_id, scope = LEAF_OPERATIONS[operation]
    if context['queue_id'] != queue_id:
        raise GateError('HOLD_NATIVE_LEAF_QUEUE')
    _leaf_sources(context['source_pins'])
    started = time.time()
    if operation == 'chat_health':
        # Current native primary is 8098. The old 8081 teacher/review route is
        # deliberately not substituted for owner-chat identity or streaming.
        primary, latency = _local_json(8098, '/health')
        gateway, gateway_latency = _local_json(8080, '/health')
        primary_ok = isinstance(primary, dict) and primary.get('status') == 'ok'
        gateway_ok = isinstance(gateway, dict) and (gateway.get('ok') is True
                     or gateway.get('status') in ('ok', 'healthy', 'ready'))
        facts = {'primary_port':8098, 'primary_health_verified':primary_ok,
                 'gateway_port':8080, 'gateway_health_verified':gateway_ok,
                 'primary_latency_ms':latency, 'gateway_latency_ms':gateway_latency}
        passed = primary_ok and gateway_ok
        blockers = ['AUTHENTICATED_STREAM_AND_S03_E2E_REQUIRED']
        if not passed: blockers.append('HEALTH_SCHEMA_OR_STATUS_UNVERIFIED')
    elif operation == 'memory_schema':
        facts = observe('memory')
        status, latency = _local_json(8080, '/nox/s03/status')
        counts = status.get('counts') if isinstance(status, dict) else None
        safe_counts = counts if isinstance(counts, dict) else {}
        facts.update(status_counts={k:v for k,v in safe_counts.items()
                     if isinstance(v, (int, float, bool))}, status_latency_ms=latency)
        passed = bool(facts['status_counts'])
        blockers = ['SEGMENT_PERSONA_READ_WRITE_E2E_REQUIRED', 'INDEPENDENT_BACKUP_RESTORE_REQUIRED']
    elif operation == 'training_prerequisites':
        import owner_component_tasks as components
        import owner_task_plans as plans
        stack = components.training_stack()
        inventory = plans.checkpoint_inventory()
        facts = {'stack':stack, 'checkpoint_inventory':inventory,
                 'training_started':False, 'optimizer_step_executed':False}
        passed = stack.get('verified') is True
        blockers = ['REAL_FORWARD_BACKWARD_OPTIMIZER_SHA_REQUIRED']
    else:
        import io
        import unittest
        # Exact pinned, reviewed tests; fixed module names. The tests exercise
        # source logic only and cannot certify a server deployment or parent ID.
        suite = unittest.defaultTestLoader.loadTestsFromName('test_owner_four_queue')
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        if result.testsRun < 13:
            raise GateError('HOLD_NATIVE_LEAF_TEST_DISCOVERY')
        facts = {'tests_run':result.testsRun, 'failures':len(result.failures),
                 'errors':len(result.errors), 'skipped':len(result.skipped),
                 'test_module_sha256':context['source_pins']['test_owner_four_queue.py']}
        passed = result.wasSuccessful() and not result.skipped
        blockers = ['STOP_YIELD_RECONNECT_RESTORE_SEQUENCE_ACCEPTANCE_REQUIRED']
    evidence = {'operation':operation, 'queue_id':queue_id,
                'parent_task_id':context['parent_task_id'], 'original_task_accepted':False,
                'scope':scope, 'check_completed':True, 'check_passed':passed,
                'blockers':blockers, 'facts':facts, 'claim':context['claim'],
                'started_at':started, 'finished_at':time.time(),
                'worker':process_identity(os.getpid()), 'source_sha256':context['source_sha256'],
                'source_pins':context['source_pins'], 'model_called':False}
    return {'state':'NATIVE_LEAF_COMPLETED', 'leaf_evidence':evidence,
            'leaf_evidence_sha256':digest(encoded(evidence))}


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


def resource_wait_reason(snapshot):
    """A fresh local observation admits only this one pending IPC submit."""
    if (not isinstance(snapshot, dict) or snapshot.get('native_verified') is not True
            or snapshot.get('instance_id') != 60509551
            or snapshot.get('stop_active') is not False
            or snapshot.get('owner_scope_verified') is not True
            or snapshot.get('source_sha_verified') is not True):
        return 'HOLD_NATIVE_SUBAGENT_ADMISSION'
    values = [snapshot.get('cgroup_memory_ratio'), snapshot.get('cpu_pressure')]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
           for value in values):
        return 'HOLD_NATIVE_SUBAGENT_RESOURCE_METADATA'
    budget = snapshot.get('bounded_cpu_budget')
    if budget is not None:
        if snapshot.get('admission_class') not in ('BOUNDED_CPU_PROJECT_SOURCE', 'BOUNDED_CPU_READ_ONLY_LEAF'):
            return 'HOLD_BOUNDED_CPU_TASK_SCOPE'
        try:
            return autonomy.bounded_cpu_decision(budget, memory_ratio=values[0], cpu_pressure=values[1])['reason']
        except autonomy.AutoHold as exc:
            return str(exc)
    if values[0] >= .95 or values[1] >= 50:
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
        for key in ('historical_leaf_source_sha256', 'historical_project_source_sha256'):
            historical = self.config.get(key, [])
            if (not isinstance(historical, list) or len(historical) > 32
                    or any(not isinstance(pin, str) or not autonomy.SHA.fullmatch(pin) for pin in historical)
                    or len(historical) != len(set(historical))):
                raise GateError('HOLD_NATIVE_HISTORICAL_SOURCE_PINS')
        self.source = digest(read(Path(__file__)))
        pins = self.config.get('module_pins', {})
        for name in ('owner_subagent_processes.py', 'owner_autonomy_pool.py', 'owner_subagent_dispatcher.py'):
            if digest(read(Path(__file__).parent/name)) != pins.get(name):
                raise GateError('HOLD_SUBAGENT_INSTALLED_SOURCE')
        self.projects = None
        if self.config.get('execution_mode') == PROJECT_MODE:
            for name in ('owner_project_native.py', *project_executor.SOURCE_FILES):
                if digest(read(Path(__file__).parent/name)) != pins.get(name):
                    raise GateError('HOLD_PROJECT_NATIVE_SOURCE')
            from owner_project_native import ProjectBinding
            self.projects = ProjectBinding(self)
        self.catalog = self.config['catalog']
        if digest(encoded(self.catalog)) != self.config.get('catalog_sha256'):
            raise GateError('HOLD_SUBAGENT_CATALOG_CHANGED')
        self._validate_catalog(self.catalog)
        self.lock = threading.RLock()
        self.tick_lock = threading.Lock()
        self.pool = None
        self.state = None
        self.completed = {}
        self.interrupted = {}
        self.lease_fd = None
        self.last_tick = 0.0
        self.last_status = {'state': 'NOT_YET_ADMITTED', 'jobs_started': 0}
        self.last_resource_admission = None
        self.admissions = {}
        self.last_pool_started_at = None
        self.last_pool_closed_at = None
        self.last_pool_close_reason = None
        self._pool_workers = []
        self._pool_recovery = None
        self._pool_recovery_uncertain = False
        self._role_restart_attempts = {role:[] for role in ROLES}
        self._cold_start_attempts = []
        self._role_lifecycle = {}
        self._relay_bindings = {}
        self._relay_current_sha256 = None
        self._relay_manifest_cache = {}
        self.relay_status = {'state':'NOT_CONFIGURED'}

    def allowed_handlers(self):
        if self.config.get('execution_mode') == PROJECT_MODE:
            return {HANDLER, LEAF_HANDLER, PROJECT_HANDLER}
        return {HANDLER, LEAF_HANDLER} if self.config.get('execution_mode') == LEAF_MODE else {HANDLER}

    def _validate_catalog(self, catalog):
        rows = autonomy.validate_submission(catalog, allowed_handlers=self.allowed_handlers())['ordered']
        for row in rows:
            params = row['params']
            if row['handler'] == HANDLER:
                if (set(params) != {'role'} or params['role'] not in ROLES
                        or row['source_sha256'] != self.policy['sha256']):
                    raise GateError('HOLD_SUBAGENT_CATALOG_SCOPE')
            elif row['handler'] == PROJECT_HANDLER:
                self.projects.validate_row(row)
            else:
                operation, parent = params.get('operation'), params.get('parent_task_id')
                if (set(params) != {'operation', 'parent_task_id'}
                        or operation not in LEAF_OPERATIONS
                        or not isinstance(parent, str) or not autonomy.ID.fullmatch(parent)
                        or not row['id'].startswith(parent+'.')
                        or row['queue_id'] != LEAF_OPERATIONS[operation][0]
                        or row['source_sha256'] not in {self.source, *self.config.get('historical_leaf_source_sha256', [])}):
                    raise GateError('HOLD_NATIVE_LEAF_CATALOG_SCOPE')
        if any(row['handler'] == LEAF_HANDLER for row in rows):
            _leaf_sources(self.config.get('leaf_source_pins'))
        return rows

    def owner_allowed(self):
        return self.config.get('owner_authorized') is True and self.config.get('instance_id') == 60509551

    def receipt_source_allowed(self, task, receipt):
        source = receipt.get('source_sha256')
        if source == self.source:
            return True
        key = ('historical_project_source_sha256' if task.get('handler') == PROJECT_HANDLER else
               'historical_leaf_source_sha256' if task.get('handler') == LEAF_HANDLER else None)
        terminal = (('done', 'blocked', 'failed', 'cancelled') if task.get('handler') == PROJECT_HANDLER else ('done',))
        return (key is not None and source in self.config.get(key, [])
                and task.get('status') in terminal and (task.get('params') or {}).get('source_sha256') == source)

    def stop_active(self):
        path = ROOT/'state/STOP'
        return self.ns['owner_mentor'].stop_active() is not False or path.exists() or path.is_symlink()

    def writer_lease(self):
        with self.lock:
            path = plain(ROOT/'state/dispatcher/native_subagents.lock')
            if self.lease_fd is None:
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    return False
                self.lease_fd = fd
            # A replaced lock pathname must never authorize a second writer
            # while this director still holds the unlinked former inode.
            info, named = os.fstat(self.lease_fd), path.stat()
            return (stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                    and info.st_nlink == 1 and not info.st_mode & 0o077
                    and (info.st_dev,info.st_ino) == (named.st_dev,named.st_ino))

    def read_reviewed_catalog(self):
        load_policy(self.policy)
        latest = owner_config()
        if any(latest.get(key) != self.config.get(key) for key in (
                'schema', 'policy', 'policy_id', 'owner_request', 'owner_source_sha',
                'module_pins', 'instance_id', 'owner_authorized', 'mode', 'target',
                'execution_mode', 'leaf_source_pins', 'project_handoff',
                'project_executor', 'historical_leaf_source_sha256', 'historical_project_source_sha256')):
            raise GateError('HOLD_SUBAGENT_CONFIG_SCOPE_CHANGED')
        catalog = latest.get('catalog')
        if digest(encoded(catalog)) != latest.get('catalog_sha256'):
            raise GateError('HOLD_SUBAGENT_CATALOG_CHANGED')
        self._validate_catalog(catalog)
        self.catalog = catalog
        if latest.get('systemic_relay') is not None:
            self.catalog = self._refill_reviewed_catalog(latest['systemic_relay'], catalog)
        elif self.config.get('systemic_relay') is not None:
            raise GateError('HOLD_RELAY_CONFIG_REMOVED')
        return self.catalog

    def _relay_module(self):
        name = 'owner_systemic_refill.py'
        if digest(read(Path(__file__).parent/name)) != self.config['module_pins'].get(name):
            raise GateError('HOLD_RELAY_MODULE_PIN')
        import owner_systemic_refill
        return owner_systemic_refill

    def _relay_manifests(self, reference, module):
        if (not isinstance(reference, dict) or set(reference) != {'path','sha256'}
                or not SHA.fullmatch(str(reference.get('sha256','')))):
            raise GateError('HOLD_RELAY_MANIFEST_REFERENCE')
        directory = Path(self.projects.config['package_root'])/'relay'
        expected_path = directory/(reference['sha256']+'.json')
        if reference['path'] != str(expected_path):
            raise GateError('HOLD_RELAY_MANIFEST_PATH')
        manifests = {}
        pin = reference['sha256']
        while pin is not None:
            if not SHA.fullmatch(str(pin)) or pin in manifests or len(manifests) >= 64:
                raise GateError('HOLD_RELAY_MANIFEST_CHAIN')
            path = plain(directory/(pin+'.json'))
            before = path.stat()
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_nlink != 1 or before.st_mode & 0o022):
                raise GateError('HOLD_RELAY_MANIFEST_OWNER')
            identity = (before.st_dev,before.st_ino,before.st_size,
                        before.st_mtime_ns,before.st_ctime_ns)
            cached = self._relay_manifest_cache.get(pin)
            if cached and cached[0] == identity:
                value = cached[1]
            else:
                raw = read(path, 2*1024*1024)
                value = json.loads(raw)
                after = path.stat()
                if (digest(raw) != pin or encoded(value) != raw or identity !=
                        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
                    raise GateError('HOLD_RELAY_MANIFEST_PIN')
                module.validate_manifest(value)
                self._relay_manifest_cache[pin] = (identity,value)
            manifests[pin] = value
            pin = value['previous_manifest_sha256']
        if self._relay_current_sha256 not in (None, *manifests):
            raise GateError('HOLD_RELAY_MANIFEST_PREDECESSOR')
        return manifests

    def _relay_source_pins(self, module, manifest):
        requests = module.source_requests(manifest)
        roots = self.projects.config['roots']
        if not isinstance(requests, dict) or not requests.keys() <= roots.keys():
            raise GateError('HOLD_RELAY_SOURCE_ROOTS')
        result, total = {}, 0
        for root_id, paths in requests.items():
            root = roots[root_id]
            if not isinstance(paths, (list,tuple)) or len(paths) > 128 or len(set(paths)) != len(paths):
                raise GateError('HOLD_RELAY_SOURCE_PATHS')
            result[root_id] = {}
            with project_executor.tree(root['path']) as handle:
                for path in paths:
                    project_executor.relpath(path)
                    if (not project_executor._allowed(path, root['allowed_paths'])
                            or project_executor._allowed(path, root.get('deny_paths', []))):
                        raise GateError('HOLD_RELAY_SOURCE_SCOPE')
                    raw, _ = handle.get(path)
                    if raw is None:
                        raise GateError('HOLD_RELAY_SOURCE_MISSING')
                    total += len(raw)
                    if len(raw) > 512*1024 or total > 4*1024*1024:
                        raise GateError('HOLD_RELAY_SOURCE_BUDGET')
                    result[root_id][path] = digest(raw)
                handle.assert_current()
        return result

    def _refill_reviewed_catalog(self, reference, base):
        """Compile reviewed missions into the same catalog/claims; no new queue."""
        path = plain(ROOT/'state/owner_maintenance.lock')
        fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info, named = os.fstat(fd), path.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022
                    or (info.st_dev,info.st_ino) != (named.st_dev,named.st_ino)):
                raise GateError('HOLD_RELAY_MAINTENANCE_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:
                raise GateError('HOLD_RELAY_MAINTENANCE_BUSY') from None
            return self._refill_under_lease(reference, base)
        finally:
            os.close(fd)

    def _refill_under_lease(self, reference, base):
        if not self.projects or not self.owner_allowed() or self.stop_active() or not self.writer_lease():
            raise GateError('HOLD_RELAY_OWNER_GATE')
        module = self._relay_module()
        manifests = self._relay_manifests(reference, module)
        manifest = manifests[reference['sha256']]
        with self.ns['_qlock']:
            snapshot = json.loads(encoded({key:{field:value for field,value in row.items()
                if not field.startswith('_')} for key,row in (self.state or {}).get('tasks', {}).items()
                if isinstance(row, dict)}))
        rows = list(base['tasks'])
        ids = {row['id'] for row in rows}
        bindings = {}
        # Preserve the exact previous admission after restart, even when its
        # source has changed legitimately. Historical rows never execute twice.
        for task in snapshot.values():
            record = task.get('systemic_relay') if isinstance(task, dict) else None
            if record is None:
                continue
            if (not isinstance(record, dict) or set(record) !=
                    {'schema','manifest_sha256','binding','reviewed_row'}
                    or record.get('schema') != 'NOX_SYSTEMIC_RELAY_TASK_V1'
                    or record.get('manifest_sha256') not in manifests):
                raise GateError('HOLD_RELAY_DURABLE_BINDING')
            row = record['reviewed_row']
            if not isinstance(row, dict) or row.get('id') != task.get('id') or row['id'] in ids:
                raise GateError('HOLD_RELAY_DURABLE_IDENTITY')
            contract = project_executor.load_contract_metadata(
                {'contract_sha256':row['params']['contract_sha256']}, self.projects.config)
            if record.get('binding', {}).get('manifest_sha256') != record['manifest_sha256']:
                raise GateError('HOLD_RELAY_BINDING_MANIFEST_PIN')
            module.validate_binding(manifests[record['manifest_sha256']],
                record['binding'], row, contract)
            params = {key:value for key,value in task.get('params', {}).items()
                      if key not in ('job_id','source_sha256')}
            if (params != row['params'] or task.get('handler') != PROJECT_HANDLER
                    or task.get('queue_id') != row['queue_id']
                    or task.get('params', {}).get('source_sha256') != row['source_sha256']):
                raise GateError('HOLD_RELAY_DURABLE_CLAIM')
            rows.append(row)
            ids.add(row['id'])
            bindings[row['id']] = record
        self.catalog = {**base, 'tasks':rows}
        self._validate_catalog(self.catalog)
        runtime = self.read_resource_snapshot(leaf_only=True)
        reason = resource_wait_reason(runtime)
        inflight = sum(autonomy._in_flight(value.get('status'))
            and not (self.projects and self.projects.terminal_for_capacity(value))
            for value in snapshot.values() if isinstance(value, dict)
            and value.get('handler') in self.allowed_handlers())
        capacity = {**runtime, 'slots_available':max(0,3-inflight) if reason is None else 0,
                    'now':time.time(), 'callback_sha256':self.source,
                    'manifest_sha256':reference['sha256']}
        reservations = set()
        for task in snapshot.values():
            if task.get('handler') != PROJECT_HANDLER or not autonomy._in_flight(task.get('status')):
                continue
            if self.projects.terminal_for_capacity(task):
                continue
            reference_for_task = self.projects.reference(task.get('params', {}))
            spec = (project_executor.load_plan(reference_for_task, self.projects.config)
                    if 'plan_sha256' in reference_for_task else
                    project_executor.load_contract_metadata(reference_for_task, self.projects.config))
            paths = spec.get('editable_paths', [item['path'] for item in spec.get('files', [])])
            reservations.update((spec['root_id'], path) for path in paths)
            if task.get('status') in ('blocked','failed','cancelled'):
                task['status'] = 'unsettled'  # Projection only; durable queue is untouched.
        capacity['reserved_sources'] = [{'root_id':root,'path':path}
            for root,path in sorted(reservations)]
        pins = self._relay_source_pins(module, manifest)
        proposed = module.select_next(manifest, snapshot, pins, capacity)
        if (not isinstance(proposed, dict) or not isinstance(proposed.get('rows'), list)
                or len(proposed['rows']) > capacity['slots_available']
                or not isinstance(proposed.get('contracts'), dict)
                or not isinstance(proposed.get('bindings'), dict)):
            raise GateError('HOLD_RELAY_PROPOSAL_SHAPE')
        for row in proposed['rows']:
            if row['id'] in ids or row.get('source_sha256') != self.source:
                raise GateError('HOLD_RELAY_PROPOSAL_DUPLICATE')
            pin = row['params']['contract_sha256']
            contract = proposed['contracts'].get(pin)
            raw = encoded(contract)
            if not SHA.fullmatch(str(pin)) or digest(raw) != pin:
                raise GateError('HOLD_RELAY_CONTRACT_PIN')
            binding = proposed['bindings'].get(row['id'])
            if not isinstance(binding, dict) or binding.get('manifest_sha256') != reference['sha256']:
                raise GateError('HOLD_RELAY_BINDING_MANIFEST_PIN')
            module.validate_binding(manifest, binding, row, contract)
            # Content-addressed immutable package storage is the existing
            # executor mechanism. No command, test or scope comes from a model.
            path = Path(self.projects.config['package_root'])/'contracts'/(pin+'.json')
            if path.exists():
                if read(path) != raw:
                    raise GateError('HOLD_RELAY_CONTRACT_COLLISION')
            else:
                if self.stop_active() or not self.writer_lease():
                    raise GateError('HOLD_RELAY_OWNER_GATE')
                project_executor.write_atomic(path, raw)
                if read(path) != raw:
                    raise GateError('HOLD_RELAY_CONTRACT_READBACK')
            rows.append(row)
            ids.add(row['id'])
            bindings[row['id']] = {'schema':'NOX_SYSTEMIC_RELAY_TASK_V1',
                'manifest_sha256':reference['sha256'], 'binding':binding,
                'reviewed_row':row}
        result = {**base, 'tasks':rows}
        self._validate_catalog(result)
        self._relay_bindings = bindings
        self._relay_current_sha256 = reference['sha256']
        self.relay_status = {'state':reason or proposed.get('state'),
            'manifest_sha256':reference['sha256'], 'fingerprint':proposed.get('fingerprint'),
            'eligible_proposals':len(proposed['rows']), 'slots_available':capacity['slots_available'],
            'refill_request':proposed.get('refill_request'),
            'shared_queue':True, 'original_task_acceptance_added':0}
        return result

    def relay_binding(self, task):
        record = self._relay_bindings.get(task['id'])
        if record is not None and record.get('reviewed_row') != task:
            raise GateError('HOLD_RELAY_BINDING_CHANGED')
        return json.loads(encoded(record)) if record is not None else None

    def _leaf_only_work(self):
        if self.config.get('execution_mode') not in (LEAF_MODE, PROJECT_MODE):
            return False
        with self.ns['_qlock']:
            rows = (self.state or {}).get('tasks', {})
            return not any(not autonomy.bounded_cpu_task(task) and
                (rows.get(task['id']) or {}).get('status') not in ('done', 'failed', 'cancelled')
                for task in self.catalog['tasks'])

    def read_resource_snapshot(self, leaf_only=None):
        leaf_only = self._leaf_only_work() if leaf_only is None else leaf_only and self._leaf_only_work()
        projects = getattr(self, 'projects', None)
        if not leaf_only and chat_priority_active():
            raise autonomy.AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        if not leaf_only:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                    'http://127.0.0.1:8081/slots', timeout=1) as response:
                slots = json.loads(response.read(262145))
            if not isinstance(slots, list) or not slots or len(slots) > 128:
                raise autonomy.AutoHold('HOLD_NATIVE_MODEL_SLOTS_UNKNOWN')
            flags = [slot.get('is_processing', slot.get('processing')) for slot in slots if isinstance(slot, dict)]
            if len(flags) != len(slots) or any(type(flag) is not bool for flag in flags):
                raise autonomy.AutoHold('HOLD_NATIVE_MODEL_SLOTS_UNKNOWN')
            with self.lock:
                owned = len(self.pool.active) if self.pool is not None else 0
            if sum(flags) > owned:
                raise autonomy.AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        observed_at = time.time()
        current = int(Path('/sys/fs/cgroup/memory.current').read_text().strip())
        maximum = int(Path('/sys/fs/cgroup/memory.max').read_text().strip())
        pressure = Path('/sys/fs/cgroup/cpu.pressure').read_text()
        match = re.search(r'^some\s+avg10=([0-9.]+)', pressure, re.M)
        if not match or maximum <= 0:
            raise GateError('HOLD_SUBAGENT_RESOURCE_METADATA')
        admitted_memory = current
        bounded_budget = bounded_decision = None
        if leaf_only:
            # Count only measured reclaimable inactive file cache separately;
            # never exclude shmem,
            # anonymous/model allocations or measured pressure from this gate.
            stats = dict(line.split() for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines())
            inactive = int(stats['inactive_file'])
            file_bytes, shmem = int(stats['file']), int(stats['shmem'])
            if min(current, inactive, file_bytes, shmem) < 0 or shmem > file_bytes:
                raise GateError('HOLD_NATIVE_LEAF_MEMORY_METADATA')
            pressure_raw = Path('/sys/fs/cgroup/memory.pressure').read_text()
            psi = [float(value) for value in re.findall(r'^(?:some|full)\s+avg10=([0-9.]+)', pressure_raw, re.M)]
            if len(psi) != 2 or any(not math.isfinite(value) or value < 0 for value in psi):
                raise GateError('HOLD_NATIVE_LEAF_MEMORY_PRESSURE')
            # Project verification uses its configured hard address-space cap.
            # Reserve an additional 128 MiB per persistent planner/IPC worker;
            # none of the existing anonymous/model/shmem allocations is removed.
            bounded_budget = {'schema':autonomy.BOUNDED_CPU_SCHEMA, 'source':'cgroup_v2',
                'instance_id':60509551, 'observed_at':observed_at, 'worker_slots':3,
                'current_bytes':current, 'max_bytes':maximum, 'inactive_file_bytes':inactive,
                'file_bytes':file_bytes, 'shmem_bytes':shmem,
                'sandbox_limit_bytes':(projects.config['sandbox']['memory_mb'] if projects else 256)*autonomy.MIB,
                'planner_reserve_bytes':128*autonomy.MIB,
                'minimum_headroom_bytes':autonomy.BOUNDED_CPU_HEADROOM,
                'memory_psi_some_avg10':psi[0], 'memory_psi_full_avg10':psi[1],
                'cpu_pressure':float(match[1])}
            bounded_decision = autonomy.bounded_cpu_decision(bounded_budget)
            admitted_memory = bounded_decision['projected_bytes']
        with self.ns['_qlock']:
            catalog_ids = {task['id'] for task in self.catalog['tasks']}
            relevant = {key:value for key,value in self.state['tasks'].items()
                        if key in catalog_ids and value.get('handler') in (HANDLER, LEAF_HANDLER, PROJECT_HANDLER)}
            status = {key:('failed' if projects and value.get('handler') == PROJECT_HANDLER
                           and projects.terminal_for_capacity(value) else value.get('status'))
                      for key,value in relevant.items()}
            sequenced = [value for value in relevant.values()
                         if type(value.get('native_queue_sequence')) is int
                         and value.get('queue_id') in autonomy.QUEUE_IDS]
            last = max(sequenced, key=lambda row:row['native_queue_sequence'], default=None)
            cursor = (autonomy.QUEUE_IDS.index(last['queue_id'])+1)%4 if last else 0
        snapshot = {'native_verified': True, 'instance_id': 60509551,
                'stop_active': self.stop_active(), 'source_sha_verified': True,
                'owner_scope_verified': self.owner_allowed(), 'task_status': status,
                'cgroup_memory_ratio': admitted_memory/maximum, 'raw_cgroup_memory_ratio':current/maximum,
                'cpu_pressure': float(match[1]), 'queue_cursor':cursor,
                'admission_class':('BOUNDED_CPU_PROJECT_SOURCE' if projects else 'BOUNDED_CPU_READ_ONLY_LEAF')
                                  if leaf_only else 'EXISTING_MODEL_REVIEW',
                'gpu_available': False}
        if bounded_budget is not None:
            snapshot.update(bounded_cpu_budget=bounded_budget, bounded_cpu_decision=bounded_decision,
                effective_cgroup_memory_ratio=bounded_decision['effective_memory_ratio'],
                projected_cgroup_memory_ratio=bounded_decision['projected_memory_ratio'])
        self.last_resource_admission = {key:value for key,value in snapshot.items() if key != 'task_status'}
        return snapshot

    def _fresh_admission_reason(self, leaf_only=False):
        # read_resource_snapshot also checks the real local chat/slot gate.
        # A previously created pool is never permission to reuse a stale check.
        if self._pool_recovery_uncertain:
            return 'HOLD_NATIVE_POOL_RECOVERY_UNCERTAIN'
        try:
            return resource_wait_reason(self.read_resource_snapshot(leaf_only=leaf_only))
        except (OSError, ValueError, TypeError, KeyError, GateError):
            return 'HOLD_NATIVE_SUBAGENT_ADMISSION'

    def review_status(self):
        """Counts of the reviewed catalog only; no model prose becomes status."""
        ids = {row['id'] for row in self.catalog['tasks'] if row['handler'] == HANDLER}
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

    def catalog_progress(self):
        """Explain work demand from the existing reviewed catalog and queue.

        Catalog exhaustion is not original-project completion. This projection
        cannot reset a claim, approve a plan, or convert a failed attempt into
        a retry; the next catalog must still pass read_reviewed_catalog().
        """
        names = ('not_admitted', 'pending', 'running', 'done', 'blocked',
                 'failed', 'cancelled', 'unknown')
        handlers = (HANDLER, LEAF_HANDLER, PROJECT_HANDLER)
        counts = {handler:dict.fromkeys(names, 0) for handler in handlers}
        ready, waiting, parents = [], [], set()
        with self.ns['_qlock']:
            tasks = (self.state or {}).get('tasks', {})
            for row in self.catalog['tasks']:
                handler, task_id = row['handler'], row['id']
                value = tasks.get(task_id)
                status = ('not_admitted' if task_id not in tasks else
                          value.get('status') if isinstance(value, dict) else None)
                counts[handler][status if status in names else 'unknown'] += 1
                if handler == PROJECT_HANDLER:
                    parents.add(row['params']['parent_task_id'])
                if status == 'not_admitted':
                    deps = row.get('deps', [])
                    blocked = [dep for dep in deps if not isinstance(tasks.get(dep), dict)
                               or tasks[dep].get('status') not in ('done', 'completed')]
                    (waiting if blocked else ready).append(task_id)
        absent = sum(value['not_admitted'] for value in counts.values())
        return {'schema':'NOX_REVIEWED_CATALOG_PROGRESS_V1',
                'scope':'CATALOG_COVERAGE_NOT_ORIGINAL_TASK_ACCEPTANCE',
                'catalog_sha256':digest(encoded(self.catalog)),
                'catalog_tasks':len(self.catalog['tasks']), 'counts':counts,
                'project_parent_ids':sorted(parents),
                'not_admitted':absent, 'dependency_ready':len(ready),
                'dependency_waiting':len(waiting),
                'dependency_ready_sample':sorted(ready)[:3],
                'dependency_waiting_sample':sorted(waiting)[:3],
                'next_action':('ADMIT_NEXT_REVIEWED_TASK' if ready else
                    'RESOLVE_REVIEWED_DEPENDENCIES' if waiting else
                    'REFILL_REVIEWED_CATALOG_AFTER_CLAIMS_SETTLE'),
                'refill_requires_reviewed_contracts':True,
                'automatic_replay_allowed':False}

    def _explain_idle(self, admission):
        # Enrich only a successful native idle census. STOP, resource pressure,
        # unknown claims and all other admission outcomes remain authoritative.
        if admission.get('state') != 'NATIVE_QUEUE_IDLE' or not self.projects:
            return admission
        progress = self.catalog_progress()
        if progress['not_admitted'] == 0:
            state, action = ('NATIVE_QUEUE_REVIEWED_CATALOG_EXHAUSTED',
                             'REFILL_REVIEWED_CATALOG')
        elif progress['dependency_ready'] == 0:
            state, action = ('NATIVE_QUEUE_DEPENDENCY_WAIT',
                             'RESOLVE_REVIEWED_DEPENDENCIES')
        else:
            state, action = ('NATIVE_QUEUE_ADMISSION_WAIT',
                             'RECHECK_NATIVE_ADMISSION')
        return {**admission, 'state':state, 'next_action':action,
                'catalog_progress':progress, 'original_completion_proven':False}

    def project_status(self):
        pins = self.config.get('project_handoff')
        if not isinstance(pins, dict) or set(pins) != set(PROJECT_FILES):
            return {'state':'PROJECT_HANDOFF_NOT_CONFIGURED', 'received_unique_tasks':0}
        documents = {}
        for key, path in PROJECT_FILES.items():
            raw = read(path, 16*1024*1024)
            if digest(raw) != pins[key]:
                raise GateError('HOLD_PROJECT_HANDOFF_SHA')
            documents[key] = json.loads(raw)
        routing = documents['routing_sha256']
        rows = routing.get('tasks') if isinstance(routing, dict) else None
        if (not isinstance(rows, list) or len(rows) != 295
                or len({row.get('task_id') for row in rows if isinstance(row, dict)}) != 295
                or any(row.get('queue_id') not in autonomy.QUEUE_IDS for row in rows)
                or routing.get('dispatch_cap') != 3):
            raise GateError('HOLD_PROJECT_FOUR_QUEUE_ROUTING')
        if (len(documents['work_tasks_sha256'].get('tasks', [])) != 230
                or len(documents['work_ideas_sha256'].get('ideas', [])) != 65):
            raise GateError('HOLD_PROJECT_REGISTRY_COVERAGE')
        leaves = [row for row in self.catalog['tasks'] if row['handler'] == LEAF_HANDLER]
        projects = [row for row in self.catalog['tasks'] if row['handler'] == PROJECT_HANDLER]
        progress = self.catalog_progress()
        original_ids = {row['task_id'] for row in rows}
        represented = original_ids & set(progress['project_parent_ids'])
        progress.update(original_ids_with_current_project_plan=len(represented),
            original_ids_without_current_project_plan=len(original_ids-represented),
            original_acceptance_known=False)
        return {'state':'HANDOFF_RECEIVED_PROJECT_EXECUTION_BOUND' if self.projects else 'HANDOFF_RECEIVED_LEAF_EXECUTION_BOUND',
                'received_unique_tasks':295,
                'dispatch_cap':3, 'queues':{qid:sum(row['queue_id'] == qid for row in rows)
                                           for qid in autonomy.QUEUE_IDS},
                'bound_leaf_subtasks':len(leaves), 'leaf_status':progress['counts'][LEAF_HANDLER],
                'bound_project_subtasks':len(projects), 'project_status':progress['counts'][PROJECT_HANDLER],
                'catalog_progress':progress,
                'original_task_acceptance_added':0,
                'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED',
                'source_sha256':pins}

    def _recovery_fence(self):
        if (self._pool_recovery_uncertain or self.owner_allowed() is not True
                or self.stop_active() is not False or self.writer_lease() is not True):
            raise GateError('HOLD_NATIVE_POOL_RECOVERY_OWNER_OR_UNKNOWN')
        self.read_reviewed_catalog()
        for name, expected in self.config['module_pins'].items():
            if digest(read(Path(__file__).parent/name)) != expected:
                raise GateError('HOLD_NATIVE_POOL_RECOVERY_SOURCE')
        reason = self._fresh_admission_reason(leaf_only=self._leaf_only_work())
        if reason:
            raise GateError(reason)

    def _worker_recovery_gate(self):
        if (self.owner_allowed() is not True or self.stop_active() is not False
                or self.writer_lease() is not True):
            raise GateError('HOLD_NATIVE_WORKER_RECOVERY_GATE')
        for name, expected in self.config['module_pins'].items():
            if digest(read(Path(__file__).parent/name)) != expected:
                raise GateError('HOLD_NATIVE_WORKER_RECOVERY_SOURCE')
        return True

    def maintain_worker_pool(self):
        """Wake work in place; replace only a failed, unreserved role."""
        if self.config.get('systemic_relay') is None:
            return
        with self.lock:
            if self.pool is None:
                # An owner-enabled continuous pool remains three processes
                # even while a new reviewed manifest is being produced.
                if not self.ensure_processes(3):
                    raise GateError('HOLD_NATIVE_CONTINUOUS_POOL_START')
                return
            known = {row['role']:row for row in self._pool_workers}
            if set(known) != set(ROLES) or set(self.pool.processes) != set(ROLES):
                raise GateError('HOLD_NATIVE_WORKER_CENSUS')
            for role in ROLES:
                reason = self.pool.health_reason(role)
                if reason is None or role in self.pool.active or role in self.pool.started:
                    continue
                # A result awaits parent verification/S03. Its process slot
                # is not free merely because child.active has been cleared.
                if any(event.get('role') == role for event in self.completed.values()):
                    continue
                with self.ns['_qlock']:
                    unhandled = any(isinstance(row, dict)
                        and (row.get('native_worker_lease') or {}).get('role') == role
                        and (row.get('native_worker_lease') or {}).get('phase') != 'SETTLED'
                        and (row.get('native_worker_lease') or {}).get('director') == process_identity(os.getpid())
                        for row in (self.state or {}).get('tasks', {}).values())
                if unhandled:
                    self._role_lifecycle[role] = {'state':'HOLD_WORKER_CLAIM_UNSETTLED'}
                    continue
                now = time.monotonic()
                attempts = [at for at in self._role_restart_attempts[role] if now-at < 600]
                self._role_restart_attempts[role] = attempts
                if len(attempts) >= 3 or attempts and now-attempts[-1] < 30:
                    self._role_lifecycle[role] = {'state':'WAIT_WORKER_RESTART_BACKOFF',
                        'attempts_in_10min':len(attempts)}
                    continue
                expected = {key:known[role][key] for key in ('pid','ppid','process_starttime')}
                if self.pool.identities.get(role) != expected:
                    raise GateError('HOLD_NATIVE_WORKER_RECOVERY_LIFETIME')
                fd = os.open(plain(ROOT/'state/owner_maintenance.lock'), os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH|fcntl.LOCK_NB)
                    self._worker_recovery_gate()
                    admission = self._fresh_admission_reason(leaf_only=True)
                    if admission:
                        self._role_lifecycle[role] = {'state':admission}
                        continue
                    attempts.append(now)
                    try:
                        proof = self.pool.restart_idle(role, expected,
                            gate=self._worker_recovery_gate)
                    except Exception:
                        # A failed replacement is still an owned lifetime. Do
                        # not lose its identity or restart healthy colleagues.
                        current = self.pool.identities.get(role)
                        if (isinstance(current, dict) and current.get('ppid') == os.getpid()
                                and current.get('pid') == self.pool.processes[role].pid):
                            known[role] = {'role':role, **current}
                            self._pool_workers = [known[name] for name in ROLES]
                        self._role_lifecycle[role] = {'state':'HOLD_WORKER_RESTART_FAILED'}
                        raise
                    known[role] = {'role':role, **proof['replacement']}
                    self._pool_workers = [known[name] for name in ROLES]
                    self._role_lifecycle[role] = {'state':'WORKER_REPLACED',
                        'reason':reason, **proof}
                finally:
                    os.close(fd)

    def _recovery_save(self, anchor, marker):
        # Existing queue writer and task metadata only: no second journal/queue.
        self.state['tasks'][anchor]['native_pool_recovery'] = marker
        try:
            self.ns['save_state'](self.state)
            saved = document(self.ns['STATE'], 16*1024*1024)
            if saved['tasks'][anchor].get('native_pool_recovery') != marker:
                raise GateError('HOLD_NATIVE_POOL_RECOVERY_READBACK')
        except Exception:
            self._pool_recovery_uncertain = True
            raise GateError('HOLD_NATIVE_POOL_RECOVERY_READBACK') from None

    def _settled_project_failure(self, row):
        """A failed attempt settles only with its exact inactive/S03 proof."""
        projects = getattr(self, 'projects', None)
        if not projects or row.get('handler') != PROJECT_HANDLER:
            return False
        evidence = row.get('result')
        if not isinstance(evidence, dict) or evidence != row.get('native_project_terminal'):
            return False
        receipt = evidence.get('receipt') or {}
        return (self.receipt_source_allowed(row, receipt)
                and receipt.get('claim') == row.get('owner_claim')
                and projects.terminal_for_capacity(row))

    def reconcile_worker_claims(self):
        """Retire only this idle, owned generation after durable claim proof.

        Death, timeout or a terminal label alone never settles an execution.
        The existing result/S03 contract supplies progress; an acknowledged
        replacement can subsequently recover while idle without replaying it.
        """
        fd = None
        with self.lock:
            pool = self.pool
            if self._pool_recovery_uncertain or pool is None:
                return False
            if set(pool.processes) != set(ROLES):
                raise GateError('HOLD_NATIVE_POOL_RECOVERY_WORKERS')
            dead = [child for child in pool.processes.values() if not child.is_alive()]
            if not dead:
                return False
            if (pool.active or pool.started or self.completed or self.interrupted
                    or any(type(child.exitcode) is not int for child in dead)):
                raise GateError('HOLD_NATIVE_POOL_RECOVERY_BUSY_OR_UNKNOWN')
            known = {row['role']: row for row in self._pool_workers}
            if set(known) != set(ROLES) or len({row['pid'] for row in known.values()}) != 3:
                raise GateError('HOLD_NATIVE_POOL_RECOVERY_WORKERS')
            for role, child in pool.processes.items():
                if child.pid != known[role]['pid']:
                    raise GateError('HOLD_NATIVE_POOL_RECOVERY_LIFETIME')
                if child.is_alive() and process_identity(child.pid) != {
                        key: known[role][key] for key in ('pid', 'ppid', 'process_starttime')}:
                    raise GateError('HOLD_NATIVE_POOL_RECOVERY_LIFETIME')
            try:
                fd = os.open(plain(ROOT/'state/owner_maintenance.lock'), os.O_RDONLY | os.O_NOFOLLOW)
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                self._recovery_fence()
                with self.ns['_qlock']:
                    saved = document(self.ns['STATE'], 16*1024*1024)['tasks']
                    current = self.state['tasks']
                    if len(current) > 20000 or len(saved) > 20000:
                        raise GateError('HOLD_NATIVE_POOL_RECOVERY_STATE')
                    candidates = []
                    for task_id in set(current) | set(saved):
                        row, durable = current.get(task_id), saved.get(task_id)
                        if not any(isinstance(value, dict) and value.get('handler') in
                                   self.allowed_handlers() for value in (row, durable)):
                            continue
                        project_failure_settled = isinstance(row, dict) and self._settled_project_failure(row)
                        if (not isinstance(row, dict) or not isinstance(durable, dict)
                                or durable != {key: value for key, value in row.items() if not key.startswith('_')}
                                or row.get('_held_locks') or (autonomy._in_flight(row.get('status'))
                                                            and not project_failure_settled)):
                            raise GateError('HOLD_NATIVE_POOL_RECOVERY_CLAIM_UNSETTLED')
                        prior = row.get('native_pool_recovery')
                        if prior is not None and (not isinstance(prior, dict)
                                or prior.get('schema') != 'NOX_NATIVE_POOL_RECOVERY_V1'
                                or prior.get('phase') != 'ACTIVE'):
                            raise GateError('HOLD_NATIVE_POOL_RECOVERY_UNCERTAIN')
                        evidence = row.get('result')
                        receipt = evidence.get('receipt', {}) if isinstance(evidence, dict) else {}
                        if ((row.get('status') != 'done' and not project_failure_settled)
                                or not self.receipt_source_allowed(row, receipt)):
                            continue  # Unapproved sources never establish a settled claim.
                        if not project_failure_settled and not self.verify(row, evidence):
                            raise GateError('HOLD_NATIVE_POOL_RECOVERY_RESULT_UNKNOWN')
                        result = receipt.get('worker_result') or {}
                        worker = (result.get('leaf_evidence') or result.get('native_observation')
                                  or result.get('project_evidence') or {}).get('worker') or {}
                        same_worker = any(worker.get('pid') == item['pid'] and
                            worker.get('process_starttime') == item['process_starttime'] for item in known.values())
                        same_replacement = (isinstance(prior, dict) and prior.get('director') == process_identity(os.getpid())
                            and prior.get('replacement_workers') == self._pool_workers
                            and prior.get('claim_sha256') == digest(encoded(row.get('owner_claim')))
                            and prior.get('result_sha256') == evidence.get('receipt_sha256'))
                        if ((row.get('owner_claim') or {}).get('pid') == os.getpid()
                                and (same_worker or same_replacement)):
                            candidates.append(task_id)
                    if not candidates:
                        raise GateError('HOLD_NATIVE_POOL_RECOVERY_NO_SETTLED_PROGRESS')
                    anchor = sorted(candidates)[-1]
                    row = current[anchor]
                    prior = row.get('native_pool_recovery')
                    marker = {'schema':'NOX_NATIVE_POOL_RECOVERY_V1', 'phase':'INTENT',
                        'task_id':anchor, 'director':process_identity(os.getpid()),
                        'claim_sha256':digest(encoded(row['owner_claim'])),
                        'result_sha256':row['result']['receipt_sha256'],
                        'workers':list(self._pool_workers), 'replacement_workers':[],
                        'previous_receipt_sha256':digest(encoded(prior)) if prior else None,
                        'created_at':time.time(), 'tasks_replayed':0}
                    self._recovery_save(anchor, marker)
                    self._pool_recovery = anchor
                    self._recovery_fence()
                    pool.__exit__(None, None, None)  # Existing owned Process objects only.
                    if any(child.is_alive() or type(child.exitcode) is not int for child in pool.processes.values()):
                        raise GateError('HOLD_NATIVE_POOL_RECOVERY_RETIREMENT_UNKNOWN')
                    self.pool = None
                    marker = {**marker, 'phase':'RETIRED', 'retired_at':time.time()}
                    self._recovery_save(anchor, marker)
                    return True
            except Exception:
                # A persisted intent is never a licence to repeat an ambiguous close.
                if self._pool_recovery is not None:
                    self._pool_recovery_uncertain = True
                raise
            finally:
                if fd is not None:
                    os.close(fd)

    def ensure_processes(self, count):
        if count != 3 or self.stop_active():
            return False
        with self.lock, contextlib.ExitStack() as cleanup:
            if self.pool is None:
                now = time.monotonic()
                self._cold_start_attempts = [at for at in self._cold_start_attempts if now-at < 600]
                if (len(self._cold_start_attempts) >= 3 or self._cold_start_attempts
                        and now-self._cold_start_attempts[-1] < 30):
                    raise GateError('WAIT_NATIVE_POOL_START_BACKOFF')
                fd = os.open(plain(ROOT/'state/owner_maintenance.lock'), os.O_RDONLY | os.O_NOFOLLOW)
                cleanup.callback(os.close, fd)
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                self._recovery_fence()
                with self.ns['_qlock']:
                    saved = document(self.ns['STATE'], 16*1024*1024)['tasks']
                    for task_id, row in saved.items():
                        marker = row.get('native_pool_recovery') if isinstance(row, dict) else None
                        if marker is not None and (not isinstance(marker, dict) or
                                marker.get('phase') != 'ACTIVE') and task_id != self._pool_recovery:
                            raise GateError('HOLD_NATIVE_POOL_RECOVERY_UNCERTAIN')
                    anchor = self._pool_recovery
                    marker = saved.get(anchor, {}).get('native_pool_recovery') if anchor else None
                    if anchor:
                        if (not isinstance(marker, dict) or marker.get('phase') != 'RETIRED'
                                or marker.get('director') != process_identity(os.getpid())
                                or marker != self.state['tasks'][anchor].get('native_pool_recovery')
                                or (saved[anchor].get('status') != 'done'
                                    and not self._settled_project_failure(saved[anchor]))
                                or marker.get('claim_sha256') != digest(encoded(saved[anchor].get('owner_claim')))
                                or marker.get('result_sha256') != (saved[anchor].get('result') or {}).get('receipt_sha256')):
                            raise GateError('HOLD_NATIVE_POOL_RECOVERY_REPLACEMENT_UNKNOWN')
                        marker = {**marker, 'phase':'REPLACEMENT_INTENT'}
                        self._recovery_save(anchor, marker)
                    try:
                        self._recovery_fence()
                        # Cold start still requires a real ready job. Only a
                        # verified retirement permits an idle replacement.
                        self._cold_start_attempts.append(now)
                        # Retain the object before starting children. If startup
                        # cannot prove all exits, no later tick may spawn over it.
                        self.pool = Subagents(list(ROLES), timeout=180 if self.projects else 60)
                        self.pool.__enter__()
                        self.last_pool_started_at = time.time()
                        rows = self.process_readback()
                        autonomy.verify_distinct_native_processes(rows, requested=3, instance_id=60509551)
                        self._pool_workers = [{key: row[key] for key in
                            ('role', 'pid', 'ppid', 'process_starttime')} for row in rows]
                        if anchor:
                            self._recovery_save(anchor, {**marker, 'phase':'ACTIVE',
                                'replacement_workers':list(self._pool_workers), 'activated_at':time.time()})
                            self._pool_recovery = None
                    except Exception:
                        if self.pool is not None:
                            if all(not child.is_alive() and child.exitcode is not None
                                   for child in self.pool.processes.values()):
                                self.pool = None
                            else:
                                self._pool_recovery_uncertain = True
                        if anchor:
                            self._pool_recovery_uncertain = True
                        raise
            return len(self.process_readback()) == 3

    def process_readback(self):
        with self.lock:
            if self.pool is None:
                return []
            rows = []
            for role, child in self.pool.processes.items():
                identity = process_identity(child.pid)
                if identity and child.is_alive() and identity['ppid'] == os.getpid():
                    rows.append({**identity, 'role': role, 'native_pid_verified': True,
                        'state': 'RUNNING', 'instance_id': 60509551, 'origin': 'existing_onehost',
                        'heartbeat_at': self.pool.heartbeats.get(role),
                        'health_reason':self.pool.health_reason(role),
                        'current_task': self.pool.active.get(role)})
            return rows

    def native_duplicate_check(self, task_id):
        with self.ns['_qlock']:
            return task_id in self.state['tasks']

    def native_queue_claim(self, task, owner_pids):
        if task.get('handler') in (PROJECT_HANDLER, LEAF_HANDLER):
            if task.get('source_sha256') != self.source:
                raise GateError('HOLD_HISTORICAL_SOURCE_VERIFY_ONLY')
            reason = self._fresh_admission_reason(leaf_only=True)
            if reason:
                raise GateError(reason)
        if task.get('handler') == PROJECT_HANDLER:
            return self.projects.claim(task, owner_pids)
        if task.get('handler') == LEAF_HANDLER:
            if task.get('source_sha256') != self.source:
                raise GateError('HOLD_HISTORICAL_LEAF_VERIFY_ONLY')
            return self._native_leaf_queue_claim(task, owner_pids)
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

    def _native_leaf_queue_claim(self, task, owner_pids):
        self._validate_catalog({'schema':autonomy.SCHEMA, 'tasks':[task]})
        if sorted(owner_pids) != sorted(row['pid'] for row in self.process_readback()):
            raise GateError('HOLD_SUBAGENT_POOL_IDENTITY_CHANGED')
        job_id = 'nox-leaf-'+digest(encoded({'task':task['id'], 'source':self.source}))[:24]
        admission = {'schema':RECEIPT, 'phase':'QUEUE_ADMITTED_NOT_EXECUTED',
                     'task_id':task['id'], 'job_id':job_id, 'source_sha256':self.source,
                     'parent_task_id':task['params']['parent_task_id'],
                     'queue_id':task['queue_id'], 'original_task_accepted':False}
        row = {'id':task['id'], 'handler':LEAF_HANDLER, 'class':'owner_order', 'lane':'owner_order',
               'queue_id':task['queue_id'], 'parent_task_id':task['params']['parent_task_id'],
               'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED', 'original_task_accepted':False,
               'priority':autonomy.PRIORITIES[task['priority']], 'status':'blocked', 'deps':task['deps'],
               'locks':[], 'retries':0, 'max_retries':1, 'timeout_sec':90, 'title':task['title'],
               'source':SCHEMA, 'params':{**task['params'], 'source_sha256':self.source, 'job_id':job_id},
               'native_admission':admission, 'note':'WAIT_S03_ADMISSION_READBACK'}
        # Match _handle_leaf/read_resource_snapshot ordering: pool lock first,
        # then the sole queue writer lock. Never invert these across workers.
        with self.lock, self.ns['_qlock']:
            if self.stop_active() or not self.owner_allowed() or not self.writer_lease():
                raise GateError('HOLD_OWNER_STOP_OR_WRITER_LEASE')
            if task['id'] in self.state['tasks']:
                raise GateError('HOLD_SUBAGENT_DUPLICATE_TASK')
            existing = [value for value in self.state['tasks'].values()
                        if value.get('handler') in self.allowed_handlers()]
            active = sum(value.get('status') in ('pending', 'running')
                         or value.get('note') == 'WAIT_S03_ADMISSION_READBACK' for value in existing)
            if active >= 3:
                raise GateError('HOLD_NATIVE_GLOBAL_WORKER_CAP')
            row['native_queue_sequence'] = 1 + max((value.get('native_queue_sequence', 0)
                for value in existing if type(value.get('native_queue_sequence', 0)) is int), default=0)
            # Sequence, queue_id and claim are committed in one existing state
            # row under the sole dispatcher's lock. No independent cursor store.
            self.state['tasks'][task['id']] = row
            self.ns['save_state'](self.state)
        proof = remember(admission)
        with self.ns['_qlock']:
            row.update(status='pending', note='ADMITTED_NOT_EXECUTED', native_admission_s03=proof)
            self.ns['save_state'](self.state)
        self.admissions[task['id']] = admission
        return {'job_id':job_id}

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
        if task.get('handler') == PROJECT_HANDLER:
            return self.projects.handle(task)
        if task.get('handler') == LEAF_HANDLER:
            return self._handle_leaf(task)
        params = task.get('params') or {}
        role = params.get('role')
        approved = next((row for row in self.catalog['tasks'] if row['id'] == task.get('id')), None)
        if (approved is None or role not in ROLES or role != approved['params'].get('role')
                or set(params) != {'role', 'policy_sha256', 'job_id'}
                or params.get('policy_sha256') != self.policy['sha256']
                or not self._claim_current(task, durable=True)):
            return False, 'HOLD_SUBAGENT_NATIVE_CLAIM'
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
                # Recheck immediately before EACH submit, including an existing
                # pool and the time spent creating a new one. Keep idle workers
                # intact on pressure; the original queue retains the pending job.
                reason = self._fresh_admission_reason()
                if reason:
                    return 'wait', reason
                self.interrupted.pop(task['id'], None)
                self.pool.submit({'id': task['id'], 'subagent': role, 'task': task['title'], 'depends_on': [],
                    '_native_context': {'policy': self.policy, 'operation': role,
                                        'claim': task['owner_claim']['nonce']}})
            deadline = time.monotonic()+70
            event = None
            while time.monotonic() < deadline:
                if not self._claim_current(task):
                    self.close_pool()
                    raise GateError('HOLD_NATIVE_OWNER_CLAIM_CHANGED')
                if self.stop_active() or chat_priority_active():
                    self.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
                    return 'wait', 'WAIT_OWNER_STOP_OR_CHAT_PRIORITY'
                with self.lock:
                    reason = self.interrupted.pop(task['id'], None)
                    if reason:
                        return 'wait', reason
                    self._drain()
                    event = self.completed.pop(task['id'], None)
                if event is not None:
                    break
                time.sleep(0.1)
            if event is None:
                self.close_pool()
                raise GateError('HOLD_SUBAGENT_RESULT_TIMEOUT')
            if event.get('state') != 'CANDIDATE_NOT_APPLIED':
                raise GateError(event.get('state', 'HOLD_SUBAGENT_RESULT'))
            # The original queue redacts every result with this same function.
            # Hash/store its stable public form so later S03 verification does
            # not compare an unredacted object with a transformed queue value.
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
            if self.stop_active() or chat_priority_active():
                return 'wait', 'WAIT_OWNER_STOP_OR_CHAT_PRIORITY'
            proof = remember(result)
            return True, {'schema': RECEIPT, 'verified': True, 'scope': 'NATIVE_REVIEW_AND_S03_RECEIPT',
                          'receipt': result, 's03': proof, 'receipt_sha256': digest(encoded(result)),
                          'candidate_applied': False}
        except (OSError, ValueError, sqlite3.Error, GateError) as exc:
            return False, str(exc) if isinstance(exc, GateError) else 'HOLD_SUBAGENT_NATIVE_IO'

    def _handle_leaf(self, task):
        params = task.get('params') or {}
        approved = next((row for row in self.catalog['tasks'] if row['id'] == task.get('id')), None)
        if (approved is None or approved.get('handler') != LEAF_HANDLER
                or set(params) != {'operation', 'parent_task_id', 'source_sha256', 'job_id'}
                or any(params.get(key) != approved['params'].get(key) for key in ('operation', 'parent_task_id'))
                or params.get('source_sha256') != self.source
                or task.get('queue_id') != approved['queue_id']
                or not self._claim_current(task, durable=True)):
            return False, 'HOLD_NATIVE_LEAF_CLAIM'
        try:
            if self.stop_active() or not self.writer_lease() or not self.owner_allowed():
                return 'wait', 'HOLD_OWNER_STOP_OR_WRITER_LEASE'
            with self.lock:
                reason = self._fresh_admission_reason(leaf_only=True)
                if reason:
                    return 'wait', reason
                if self.pool is None and not self.ensure_processes(3):
                    return 'wait', 'HOLD_SUBAGENT_POOL_NOT_READY'
                # The three existing OS slots are universal for leaf operations.
                # The queue_id belongs to the task, never permanently to a PID.
                role = next((role for role in ROLES if role not in self.pool.active), None)
                if role is None:
                    return 'wait', 'WAIT_NATIVE_LEAF_WORKER'
                self.interrupted.pop(task['id'], None)
                identity = next((row for row in self.process_readback() if row['role'] == role), None)
                if identity is None:
                    return 'wait', 'HOLD_NATIVE_LEAF_WORKER_IDENTITY'
                self.pool.submit({'id':task['id'], 'subagent':role, 'task':task['title'], 'depends_on':[],
                    '_native_leaf_context':{'operation':params['operation'],
                        'parent_task_id':params['parent_task_id'], 'queue_id':task['queue_id'],
                        'claim':task['owner_claim']['nonce'], 'source_sha256':self.source,
                        'source_pins':self.config['leaf_source_pins']}})
            deadline = time.monotonic()+70
            event = None
            while time.monotonic() < deadline:
                if not self._claim_current(task) or self.stop_active() or not self.writer_lease():
                    self.close_pool('WAIT_OWNER_STOP_OR_CLAIM_CHANGED')
                    return 'wait', 'WAIT_OWNER_STOP_OR_CLAIM_CHANGED'
                with self.lock:
                    reason = self.interrupted.pop(task['id'], None)
                    if reason:
                        return 'wait', reason
                    self._drain()
                    event = self.completed.pop(task['id'], None)
                if event is not None:
                    break
                time.sleep(.05)
            if event is None:
                self.close_pool('HOLD_NATIVE_LEAF_TIMEOUT')
                raise GateError('HOLD_NATIVE_LEAF_TIMEOUT')
            leaf = event.get('leaf_evidence') or {}
            worker = leaf.get('worker') or {}
            if (event.get('state') != 'NATIVE_LEAF_COMPLETED'
                    or leaf.get('check_completed') is not True
                    or type(leaf.get('check_passed')) is not bool
                    or leaf.get('original_task_accepted') is not False
                    or leaf.get('model_called') is not False
                    or leaf.get('claim') != task['owner_claim']['nonce']
                    or leaf.get('operation') != params['operation']
                    or leaf.get('parent_task_id') != params['parent_task_id']
                    or leaf.get('queue_id') != task['queue_id']
                    or leaf.get('source_sha256') != self.source
                    or worker.get('pid') != identity['pid'] or event.get('pid') != identity['pid']
                    or worker.get('process_starttime') != identity['process_starttime']
                    or leaf.get('source_pins') != self.config['leaf_source_pins']
                    or event.get('leaf_evidence_sha256') != digest(encoded(leaf))):
                raise GateError('HOLD_NATIVE_LEAF_RESULT_PROOF')
            # Native worker identity is checked above on the original IPC
            # evidence. Store the same stable public form that run_one keeps,
            # so redaction cannot invalidate the durable S03/queue digest.
            event = self.ns['owner_mentor'].clean(event)
            leaf = event.get('leaf_evidence') if isinstance(event, dict) else None
            if not isinstance(leaf, dict):
                raise GateError('HOLD_NATIVE_LEAF_PUBLIC_EVIDENCE')
            event['leaf_evidence_sha256'] = digest(encoded(leaf))
            result = {'schema':RECEIPT, 'phase':'NATIVE_LEAF_COMPLETED_ORIGINAL_NOT_ACCEPTED',
                      'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED',
                      'task_id':task['id'], 'job_id':params['job_id'], 'claim':task['owner_claim'],
                      'parent_task_id':params['parent_task_id'], 'queue_id':task['queue_id'],
                      'source_sha256':self.source, 'worker_result':event, 'finished_at':time.time(),
                      'original_task_accepted':False, 'training_started':False,
                      'optimizer_steps_verified':False, 'service_or_weights_changed':False}
            if not self._claim_current(task, durable=True) or self.stop_active() or not self.writer_lease():
                return 'wait', 'HOLD_NATIVE_LEAF_FINAL_CLAIM'
            proof = remember(result)
            # Only the explicitly named read/check subtask is completed. A
            # failed check remains check_passed=False, with its blockers; the
            # original project task is never accepted or rewritten here.
            return True, {'schema':RECEIPT, 'verified':True,
                'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED', 'receipt':result,
                's03':proof, 'receipt_sha256':digest(encoded(result)),
                'original_task_accepted':False, 'check_passed':leaf['check_passed']}
        except (OSError, ValueError, sqlite3.Error, GateError) as exc:
            return False, str(exc) if isinstance(exc, GateError) else 'HOLD_NATIVE_LEAF_IO'

    def verify(self, task, evidence):
        if task.get('handler') == PROJECT_HANDLER:
            return self.projects.verify(task, evidence)
        if task.get('handler') == LEAF_HANDLER:
            return self._verify_leaf(task, evidence)
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

    def _verify_leaf(self, task, evidence):
        if not isinstance(evidence, dict):
            return None
        receipt = evidence.get('receipt')
        if (not isinstance(receipt, dict) or receipt.get('task_id') != task.get('id')
                or receipt.get('phase') != 'NATIVE_LEAF_COMPLETED_ORIGINAL_NOT_ACCEPTED'
                or receipt.get('claim') != task.get('owner_claim')
                or receipt.get('parent_task_id') != task.get('parent_task_id')
                or receipt.get('queue_id') != task.get('queue_id')
                or receipt.get('original_task_accepted') is not False
                or not self.receipt_source_allowed(task, receipt)
                or digest(encoded(receipt)) != evidence.get('receipt_sha256')):
            return None
        proof = s03_readback(receipt)
        if proof:
            return {'kind':'bounded_native_component_check', 'task_id':task['id'],
                    'parent_task_id':task['parent_task_id'],
                    'scope':'SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED',
                    'receipt_sha256':proof['receipt_sha256'], 'source_sha256':receipt['source_sha256'],
                    's03_item_id':proof['s03_item_id'], 'original_task_accepted':False,
                    'blockers':receipt['worker_result']['leaf_evidence']['blockers']}
        return None

    def close_pool(self, reason=None):
        with self.lock:
            if self.pool is not None:
                self.last_pool_closed_at = time.time()
                self.last_pool_close_reason = reason or 'EXPLICIT_NATIVE_POOL_CLOSE'
                if reason is not None:
                    for task_id in set(self.pool.active.values()) | set(self.completed):
                        self.interrupted[task_id] = reason
                    self.completed.clear()
                self.pool.__exit__(None, None, None)
                self.pool = None

    def close(self):
        self.close_pool('DIRECTOR_SHUTDOWN')
        if self.lease_fd is not None:
            os.close(self.lease_fd)
            self.lease_fd = None

    def _maintenance_idle_pool(self):
        """Retain owned idle IPC children during EX maintenance; admit nothing."""
        if (self.pool is None or self._pool_recovery_uncertain or self.pool.active
                or self.pool.started or self.completed or self.interrupted):
            return False
        flags = ('STOP','STOP.flag','stop.flag','.stop','program/STOP',
                 'state/STOP','state/STOP.flag','state/OWNER_MAINTENANCE.flag')
        try:
            if any(p.exists() or p.is_symlink() for p in
                   [*(ROOT/name for name in flags), Path('/workspace/NOX_STOP')]):
                return False
            known = {row['role']:row for row in self._pool_workers}
            if set(known) != set(ROLES) or set(self.pool.processes) != set(ROLES):
                return False
            for role,child in self.pool.processes.items():
                if child.pid != known[role]['pid']:
                    return False
                if child.is_alive():
                    if process_identity(child.pid) != {key:known[role][key]
                            for key in ('pid','ppid','process_starttime')}:
                        return False
                elif type(child.exitcode) is not int:
                    return False
            path = plain(ROOT/'state/owner_maintenance.lock')
            fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                named = path.stat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_nlink != 1 or info.st_mode & 0o022
                        or (info.st_dev,info.st_ino) != (named.st_dev,named.st_ino)):
                    return False
                try:
                    fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
                except BlockingIOError:
                    return True  # Original stop_active remains true; no submit/ensure.
                return False
            finally:
                os.close(fd)
        except (OSError,ValueError,KeyError,GateError):
            return False

    def tick(self, state):
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            self.state = state
            if self.stop_active():
                with self.lock:
                    if self._maintenance_idle_pool():
                        self.last_status = {'state':'HOLD_MAINTENANCE_IDLE_POOL_RETAINED',
                            'jobs_started':0,'active_subexecutor_processes':len(self.process_readback())}
                        return
                self.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
                self.last_status = {'state': 'HOLD_OWNER_STOP_OR_MAINTENANCE', 'jobs_started': 0}
                return
            with self.lock:
                if self._pool_recovery_uncertain:
                    raise GateError('HOLD_NATIVE_POOL_RECOVERY_UNCERTAIN')
                self._drain()
                self.maintain_worker_pool()
                if (self.config.get('systemic_relay') is None and self.pool is not None
                        and any(not child.is_alive() for child in self.pool.processes.values())):
                    if not self.reconcile_worker_claims():
                        raise GateError('HOLD_OWNER_WORKER_RECONCILIATION_REQUIRED')
                    self.last_status = {'state':'WAIT_RECONCILED_POOL_FRESH_ADMISSION', 'jobs_started':0}
                    return
                if self.pool is None and self._pool_recovery is not None:
                    if not self.ensure_processes(3):
                        raise GateError('HOLD_NATIVE_PROCESS_START')
                    self.last_status = {'state':'NATIVE_IDLE_POOL_RECOVERED', 'jobs_started':0,
                        'active_subexecutor_processes':len(self.process_readback())}
                    return
            if self.projects:
                self.projects.reconcile()
            # Crash after a successful S03 admission is recoverable by exact
            # readback. A missing/ambiguous result is never blindly replayed.
            for task in list(state['tasks'].values()):
                if task.get('handler') in self.allowed_handlers() and task.get('note') == 'WAIT_S03_ADMISSION_READBACK':
                    proof = s03_readback(task['native_admission'])
                    if proof:
                        with self.ns['_qlock']:
                            task.update(status='pending', note='ADMITTED_NOT_EXECUTED', native_admission_s03=proof)
                            self.ns['save_state'](state)
            if time.monotonic()-self.last_tick < 5:
                return
            self.last_tick = time.monotonic()
            self.last_status = self._explain_idle(
                autonomy.tick_existing_dispatcher(self.ns, state, mode='NORMAL'))
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
            or any(not callable(namespace.get(name)) for name in ('save_state', 'write_status', 'write_agents_status', 'atomic_write', '_nox_owner_task_admitted'))
            or namespace.get('owner_mentor') is None or namespace.get('_owner_lifecycle_bound') is not True):
        raise GateError('HOLD_NATIVE_SUBAGENT_DISPATCHER_CONTRACT')
    native = Native(namespace)
    _BOUND = native
    namespace['_nox_owner_autonomy_native'] = native
    namespace['HANDLERS'][HANDLER] = native.handle
    namespace['HANDLERS'][LEAF_HANDLER] = native.handle
    if native.projects:
        namespace['HANDLERS'][PROJECT_HANDLER] = native.handle
    for role in ROLES:
        namespace['LOCKS']['native_subagent_'+role] = threading.Lock()
    old_verify = namespace['owner_mentor'].verify_success
    def verify(task, evidence=None):
        return native.verify(task, evidence) if task.get('handler') in native.allowed_handlers() else old_verify(task, evidence)
    namespace['owner_mentor'].verify_success = verify
    old_admission = namespace['_nox_owner_task_admitted']
    def admission(task):
        if task.get('handler') == HANDLER and (native.stop_active() or chat_priority_active()):
            return False  # Keep paused jobs pending until the original gate opens.
        if task.get('handler') == LEAF_HANDLER and native.stop_active():
            return False
        if task.get('handler') == PROJECT_HANDLER and (native.stop_active() or not native.projects.admitted(task)):
            return False
        return old_admission(task)
    namespace['_nox_owner_task_admitted'] = admission
    old_status, old_agents, old_atomic = (namespace[name] for name in
                                         ('write_status', 'write_agents_status', 'atomic_write'))
    publication = threading.local()
    def status(state):
        value = old_status(state)
        native.tick(state)  # Existing main/ticker only; no new scheduler thread.
        return value

    old_run_one = namespace.get('run_one')
    if callable(old_run_one):
        def run_one(state, task):
            try:
                return old_run_one(state, task)
            finally:
                if task.get('handler') in native.allowed_handlers():
                    # run_one has persisted its terminal state and released
                    # task locks. The same ticker can fill the freed slot now.
                    native.last_tick = 0
                    native.tick(state)
        namespace['run_one'] = run_one
    def agents():
        # The original writer used to publish a base-only JSON before this
        # wrapper read and rewrote it. Readers could observe NO_NATIVE_STATUS
        # while the same workers were alive. Enrich before its single atomic
        # publish. Collect before entering old_agents and its writer locks, so
        # adding the native lock/queue lock cannot invert their acquisition order.
        # A projection error becomes explicit unavailable observation metadata.
        try:
            snapshot = {'mode': 'NORMAL', 'target': 3,
                'director': process_identity(os.getpid()), 'observed_at': time.time(),
                'workers': native.process_readback(), 'last_admission': native.last_status,
                'resource_admission':native.last_resource_admission,
                'pool_lifecycle':{'last_started_at':native.last_pool_started_at,
                                  'last_closed_at':native.last_pool_closed_at,
                                  'last_close_reason':native.last_pool_close_reason,
                                  'roles':native._role_lifecycle},
                'systemic_relay':native.relay_status,
                'thread_runner_count':sum(thread.is_alive() and thread.name.startswith('steal')
                                          for thread in threading.enumerate()),
                'declared_worker_contract_slots':namespace['WORKERS'],
                'same_model_shared':True, 'leaf_model_calls_required':False,
                'review_status': native.review_status(), 'project_queues':native.project_status()}
            encoded(snapshot)  # Reject non-JSON or non-finite telemetry before writing.
        except Exception as exc:
            reason = str(exc) if isinstance(exc, GateError) and re.fullmatch(r'HOLD_[A-Z0-9_]+', str(exc)) else type(exc).__name__
            snapshot = {'state':'HOLD_NATIVE_STATUS_PROJECTION', 'reason':reason,
                'observed_at':time.time(), 'mode':'NORMAL', 'target':3,
                'worker_observation_valid':False, 'original_completion_proven':False}
        previous = getattr(publication, 'snapshot', None)
        publication.snapshot = snapshot
        try:
            return old_agents()
        finally:
            publication.snapshot = previous
    def atomic_with_native_status(path, row):
        if Path(path) != Path(namespace['AGENT_STATUS']):
            return old_atomic(path, row)
        if not isinstance(row, dict):
            raise GateError('HOLD_NATIVE_AGENT_STATUS_SCHEMA')
        snapshot = getattr(publication, 'snapshot', None)
        if snapshot is None:
            snapshot = {'state':'HOLD_NATIVE_STATUS_PUBLICATION_CONTEXT',
                'observed_at':time.time(), 'worker_observation_valid':False,
                'original_completion_proven':False}
        return old_atomic(path, {**row, 'native_subexecutors':snapshot})
    namespace['write_status'], namespace['write_agents_status'], namespace['atomic_write'] = status, agents, atomic_with_native_status
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
