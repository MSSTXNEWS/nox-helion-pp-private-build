"""Delivery, proof, crash-recovery and native-claim lifecycle integration tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


outbox = module('owner_event_outbox')
lifecycle = module('owner_task_lifecycle')
mentor = module('owner_dispatcher_mentor')


def report(task_id='owner.storage', kind='task_verified', claim='a' * 24):
    return {'schema': outbox.REPORT_SCHEMA, 'kind': kind, 'persisted': True,
            'state': 'VERIFIED_WITHIN_SCOPE', 'task': {'id': task_id, 'handler': 'owner_component', 'claim': claim},
            'verification': {'kind': 'bounded_native_component_check', 'receipt_sha256': '1' * 64,
                             'source_sha256': '2' * 64, 'scope': 'STORAGE_INVENTORY_ONLY',
                             'blockers': ['OWNER_PC_OAUTH_AND_TWO_VERIFIED_COPIES_REQUIRED']},
            'lifecycle': {'memory': 'MISSING_S03_SOURCE_PIN', 'senior': 'MISSING_SENIOR_GATEWAY',
                          'research': 'MISSING_INTERNET_RESEARCH_GATEWAY', 'optimization': 'APPROVED_NATIVE_PLAN_RETAINED'}}


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scope = patch.object(outbox, 'ROOT', self.root)
        self.scope.start()

    def tearDown(self):
        self.scope.stop(); self.temp.cleanup()

    def test_six_parallel_results_have_unique_durable_cursors_and_replay(self):
        rows = [report('owner.component' + str(i)) for i in range(6)]
        with ThreadPoolExecutor(max_workers=12) as workers:
            results = list(workers.map(outbox.publish, rows + rows))
        self.assertEqual(sum(row['state'] == 'RECORDED' for row in results), 6)
        first = outbox.events_after(0, 2)
        second = outbox.events_after(first['next_cursor'], 50)
        self.assertEqual([row['sequence'] for row in first['events'] + second['events']], list(range(1, 7)))
        self.assertEqual(len({row['event_id'] for row in first['events'] + second['events']}), 6)
        self.assertFalse(second['has_more'])
        self.assertEqual(outbox.events_after(6)['events'], [])
        for path in (self.root / 'state/owner_events/events').glob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_interrupted_commit_is_recovered_without_duplicate_or_lost_cursor(self):
        row = report()
        outbox.publish(row, now=1000)
        root = self.root / 'state/owner_events'
        outbox.atomic_json(root / 'cursor.json', {'schema': 'NOX_OWNER_EVENT_CURSOR_V1', 'last_sequence': 0})
        for path in (root / 'dedup').glob('*.json'):
            path.unlink()  # Simulate crash after immutable event, before indices.
        self.assertEqual(outbox.publish(row, now=1001)['state'], 'DUPLICATE')
        self.assertEqual(outbox.events_after(0)['latest_cursor'], 1)
        self.assertEqual(len(list((root / 'events').glob('*.json'))), 1)

    def test_reconnect_recovers_durable_event_without_another_publish(self):
        original = outbox.atomic_json

        def crash_before_dedup(path, value):
            if path.parent.name == 'dedup':
                raise OSError('fixture crash after durable event')
            return original(path, value)

        with patch.object(outbox, 'atomic_json', side_effect=crash_before_dedup):
            with self.assertRaises(OSError):
                outbox.publish(report(), now=1000)
        # No second task execution or publish is available to repair the cursor.
        replay = outbox.events_after(0)
        self.assertEqual([row['sequence'] for row in replay['events']], [1])
        self.assertEqual(replay['latest_cursor'], 1)
        self.assertEqual(outbox.events_after(replay['next_cursor'])['events'], [])
        self.assertEqual(outbox.publish(report(), now=1001)['state'], 'DUPLICATE')
        self.assertEqual(len(list((self.root / 'state/owner_events/events').glob('*.json'))), 1)

    def test_success_requires_scoped_proof_and_does_not_export_raw_private_fields(self):
        row = report()
        row.update(prompt='private user prompt', token='hf_SUPERPRIVATE123456789', raw_error='password=private')
        row['verification']['note'] = 'untrusted arbitrary instruction'
        outbox.publish(row)
        public = json.dumps(outbox.events_after(0), ensure_ascii=False)
        for private in ('private user prompt', 'SUPERPRIVATE', 'password=private', 'untrusted arbitrary'):
            self.assertNotIn(private, public)
        self.assertIn('STORAGE_INVENTORY_ONLY', public)
        self.assertIn('OWNER_PC_OAUTH_AND_TWO_VERIFIED_COPIES_REQUIRED', public)
        self.assertNotIn('оптимизация завершена', public)
        with self.assertRaises(outbox.OutboxHold):
            outbox.publish({**report('bad'), 'verification': {'reported_success': True}})

    def test_real_progress_requires_delta_and_cooldown_not_idle_ticks(self):
        row = report('owner.download', kind='task_progress')
        row['verification'] = None
        row['progress'] = {'metric': 'bytes', 'current': 20 * 1024**2, 'total': 8 * 1024**3, 'evidence_sha256': '3' * 64}
        self.assertEqual(outbox.publish(row, now=1000)['state'], 'BELOW_PROGRESS_THRESHOLD')
        row['progress']['current'] = 512 * 1024**2
        self.assertEqual(outbox.publish(row, now=1000)['state'], 'RECORDED')
        row['progress']['current'] = 1024**3
        self.assertEqual(outbox.publish(row, now=1020)['state'], 'COOLDOWN')
        self.assertEqual(outbox.publish(row, now=1061)['state'], 'RECORDED')
        self.assertEqual(outbox.publish(row, now=1200)['state'], 'DUPLICATE')
        self.assertEqual(outbox.events_after(0)['latest_cursor'], 2)

    def test_errors_are_cooldown_limited_and_never_become_success(self):
        first = report(kind='task_failed')
        first['verification'] = None
        first['state'] = 'BLOCKED_SENIOR_NOT_CONFIGURED'
        self.assertEqual(outbox.publish(first, now=1000)['state'], 'RECORDED')
        second = {**first, 'task': {**first['task'], 'claim': 'b' * 24}}
        self.assertEqual(outbox.publish(second, now=1100)['state'], 'COOLDOWN')
        self.assertEqual(outbox.publish(second, now=1301)['state'], 'RECORDED')
        self.assertTrue(all(row['severity'] == 'warning' for row in outbox.events_after(0)['events']))

    def test_api_auth_precedes_private_read_and_cursor_validation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.responses import JSONResponse
        app = FastAPI()
        outbox.register_owner_events(app, {'_session_ok': lambda request: request.cookies.get('owner') == 'fixture',
            '_unauthorized': lambda: JSONResponse({'state': 'UNAUTHORIZED'}, status_code=401)})
        client = TestClient(app)
        with patch.object(outbox, 'events_after', wraps=outbox.events_after) as read:
            self.assertEqual(client.get('/api/ui/events?cursor=../../private').status_code, 401)
            read.assert_not_called()
        outbox.publish(report())
        response = client.get('/api/ui/events?cursor=0&limit=1', cookies={'owner': 'fixture'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['next_cursor'], 1)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(client.get('/api/ui/events?limit=99', cookies={'owner': 'fixture'}).status_code, 422)

    def test_availability_does_not_confuse_paused_training_with_sleeping_core(self):
        status = self.root / 'status/agents_t856u.json'
        status.parent.mkdir(parents=True)
        rows = [{'id': 'nox-agent-%02d' % (index + 1), 'status': 'idle', 'current_task': None} for index in range(6)]
        status.write_text(json.dumps({'n': 6, 'workers': rows}))
        database = self.root / 'kb/knowledge.sqlite'
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute('CREATE TABLE s03_items (id INTEGER)')
        (self.root / 'state').mkdir(exist_ok=True)
        (self.root / 'state/TRAIN_HOLD.flag').write_text('private owner hold details')
        now = time.time()
        with patch.object(outbox, '_model_health', return_value={'state': 'READY', 'http_status': 200}):
            awake = outbox.availability(now)
            self.assertEqual(awake['state'], 'awake')
            self.assertEqual(awake['training']['state'], 'HELD')
            rows[0].update(status='busy', current_task={'id': 'owner.audit'})
            status.write_text(json.dumps({'n': 6, 'workers': rows}))
            busy = outbox.availability(now + 6)
            self.assertEqual(busy['state'], 'busy')
        with patch.object(outbox, '_model_health', return_value={'state': 'LOADING', 'http_status': 503}):
            self.assertEqual(outbox.availability(now + 12)['state'], 'drowsy')
        status.unlink(); database.unlink()
        with patch.object(outbox, '_model_health', return_value={'state': 'UNAVAILABLE', 'http_status': None}):
            offline = outbox.availability(now + 18)
            self.assertEqual(offline['state'], 'offline')
        self.assertNotIn('private owner hold', json.dumps(awake))
        self.assertEqual(outbox.events_after(0)['events'], [])


class RecallAndGatewayBoundaryTests(unittest.TestCase):
    def test_exact_module_pin_is_checked_before_any_import_code_runs(self):
        previous = sys.modules.get('owner_senior_gateway')
        try:
            with tempfile.TemporaryDirectory() as temporary, patch.object(lifecycle, 'ROOT', Path(temporary)):
                root = Path(temporary)
                path = root / 'scripts/owner_senior_gateway.py'
                path.parent.mkdir()
                sentinel = root / 'executed'
                path.write_text('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("checked")\n')
                with self.assertRaises(lifecycle.LifecycleHold):
                    lifecycle._checked_module({}, 'owner_senior_gateway', '0' * 64, required=True)
                self.assertFalse(sentinel.exists())
                loaded = lifecycle._checked_module({}, 'owner_senior_gateway', hashlib.sha256(path.read_bytes()).hexdigest(), required=True)
                self.assertEqual(Path(loaded.__file__), path)
                self.assertEqual(sentinel.read_text(), 'checked')
        finally:
            if previous is None:
                sys.modules.pop('owner_senior_gateway', None)
            else:
                sys.modules['owner_senior_gateway'] = previous

    def test_native_journal_fifo_cannot_block_recall_or_drain(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(lifecycle, 'ROOT', Path(temporary)), patch.object(outbox, 'ROOT', Path(temporary)):
            root = Path(temporary)
            coordinator = lifecycle.Coordinator({}, mentor)
            path = root / 'memory/dispatcher_mentor/events.jsonl'
            path.parent.mkdir(parents=True)
            os.mkfifo(path)
            begin = time.monotonic()
            self.assertEqual(lifecycle.journal_recall({'id': 'fixture', 'handler': 'owner_component'})['state'], 'JOURNAL_UNAVAILABLE')
            with self.assertRaises(lifecycle.LifecycleHold):
                coordinator.drain(force=True)
            self.assertLess(time.monotonic() - begin, .1)

    def test_native_recall_adapter_exports_only_hashes_and_identifies_lexical_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 's03_memory.py'
            path.write_text("print('PRIVATE_IMPORT_OUTPUT')\ndef recall(query,k):\n assert k==16\n return [{'text':'PRIVATE_MEMORY_CONTENT','how':'pin'} for _ in range(14)]+[{'text':'PRIVATE_MATCH_CONTENT','how':'fts'} for _ in range(6)]\n")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            code = lifecycle._RECALL_CHILD.replace('/root/nox/scripts/s03_memory.py', str(path))
            result = subprocess.run([sys.executable, '-I', '-c', code, expected, 'technical query'],
                                    capture_output=True, timeout=3, check=True)
            self.assertNotIn(b'PRIVATE', result.stdout)
            self.assertNotIn(b'PRIVATE', result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value['retrieval_kind'], 'LEXICAL_WITH_PINS')
            self.assertEqual(value['lexical_matches'], 6)
            self.assertEqual(len(value['references']), 8)
            self.assertEqual([row['method'] for row in value['references'][:6]], ['fts'] * 6)
            bad = subprocess.run([sys.executable, '-I', '-c', code, '0' * 64, 'query'], capture_output=True, timeout=3)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, b'')

    def test_pending_gateway_is_rechecked_and_receives_no_raw_memory(self):
        lifecycle._CACHE.clear()
        calls = []
        class Gateway:
            def consult_plan(self, context, deadline_seconds):
                calls.append(context)
                return {'state': 'PENDING' if len(calls) == 1 else 'CONSULTED', 'models_consulted': 0 if len(calls) == 1 else 2,
                        'consultation_sha256': 'a' * 64, 'research_state': 'INTERNET_RESEARCH_NOT_VERIFIED'}
        task = {'id': 'owner.audit', 'handler': 'owner_component', 'params': {'private': 'PRIVATE_TASK_INPUT'}}
        recall = {'verified': 1, 'errors': 1, 'error_categories': ['timeout'], 'private_text': 'PRIVATE_MEMORY'}
        with patch.object(lifecycle, 'semantic_recall', return_value={'state': 'S03_RECALLED'}):
            with patch.object(lifecycle.time, 'time', return_value=1000):
                first = lifecycle.shared_context(task, recall, {'mode': 'NORMAL'}, Gateway())
            with patch.object(lifecycle.time, 'time', return_value=1001):
                cached = lifecycle.shared_context(task, recall, {'mode': 'NORMAL'}, Gateway())
            with patch.object(lifecycle.time, 'time', return_value=1003):
                ready = lifecycle.shared_context(task, recall, {'mode': 'NORMAL'}, Gateway())
        self.assertEqual(first['senior']['state'], 'PENDING')
        self.assertTrue(cached['cache_reused'])
        self.assertEqual(ready['senior']['state'], 'CONSULTED')
        self.assertEqual(len(calls), 2)
        self.assertNotIn('PRIVATE', json.dumps(calls))


FIXTURE = Path('/tmp/nox_native_sources/nox_dispatcher_t855u.py')


@unittest.skipUnless(FIXTURE.exists(), 'Requires retrieved pinned native dispatcher fixture')
class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(module_, 'ROOT', self.root) for module_ in (outbox, lifecycle, mentor)]
        self.patches += [patch.object(mentor, 'stop_active', return_value=False),
                         patch.object(lifecycle, 'semantic_recall', return_value={'state': 'S03_RECALL_UNAVAILABLE', 'content_exported': False})]
        for value in self.patches:
            value.start()
        lifecycle._CACHE.clear()
        repair = module('owner_native_repair')
        module('owner_component_tasks')
        source = mentor.transform_dispatcher(repair.patch_dispatcher(FIXTURE.read_text()))
        self.native = {'__name__': 'native_lifecycle_test'}
        exec(compile(source, '<native-lifecycle>', 'exec'), self.native)
        self.original_experience, self.original_verify = mentor.record_experience, mentor.verify_success
        self.native.update(ROOT=self.root, STATE=self.root / 'state/dispatcher/state.json',
            QUEUE=self.root / 'state/dispatcher/queue.jsonl', DISTILL=self.root / 'distill/accepted.jsonl',
            _nox_owner_task_admitted=lambda task: True, ingest_architect_patch=lambda state: None,
            ingest_owner_orders=lambda state: None, write_status=lambda state: None,
            ev=lambda *args, **kwargs: None, log=lambda *args: None, journal=None)
        self.script = self.root / 'scripts/owner_component_tasks.py'
        self.script.parent.mkdir(parents=True)
        self.script.write_text('# fixed native component fixture\n')
        self.executed = []
        self.executed_lock = threading.Lock()
        self.native['HANDLERS']['owner_component'] = self.checked_component
        pins = {'owner_mentor': lifecycle.file_sha(mentor.__file__), 'owner_event_outbox': lifecycle.file_sha(outbox.__file__)}
        lifecycle.bind_dispatcher(self.native, pins)

    def tearDown(self):
        mentor.record_experience, mentor.verify_success = self.original_experience, self.original_verify
        for value in reversed(self.patches):
            value.stop()
        self.temp.cleanup()

    def checked_component(self, task):
        path = self.root / 'state/owner_components' / (task['id'] + '.json')
        evidence = {'verified': True, 'scope': 'STORAGE_INVENTORY_ONLY', 'blockers': ['FIXTURE_CHECK_ONLY']}
        row = {'schema': 'NOX_OWNER_COMPONENT_V1', 'task_id': task['id'], 'verified': True,
               'success': True, 'pid': os.getpid(), 'started_at': time.time(),
               'source_sha256': hashlib.sha256(self.script.read_bytes()).hexdigest(), 'evidence': evidence}
        mentor.atomic_json(path, row)
        with self.executed_lock:
            self.executed.append(task['id'])
        return True, {'schema': 'NOX_OWNER_COMPONENT_V1', 'schema_version': 1, 'receipt_path': str(path),
                      'receipt_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'scope': evidence['scope'], 'blockers': evidence['blockers']}

    def task_state(self, handler='owner_component', count=1):
        names = sorted(mentor.COMPONENT_TASKS)[:count]
        return {'tasks': {name: {'id': name, 'handler': handler, 'status': 'pending', 'class': 'owner_order',
                    'priority': 0, 'deps': [], 'locks': [], 'retries': 0, 'max_retries': 1} for name in names}}

    def test_six_claims_complete_without_browser_and_preflight_precedes_execution(self):
        state = self.task_state(count=6)
        busy = set()
        def run(index):
            task = self.native['owner_claim_ready'](state, busy, 'nox-agent-%02d' % (index + 1))
            if task:
                self.native['run_one'](state, task)
            return task
        with ThreadPoolExecutor(max_workers=6) as workers:
            claims = list(workers.map(run, range(6)))
        self.native['_owner_lifecycle_coordinator'].drain(force=True)
        self.assertEqual(len(self.executed), 6)
        self.assertEqual(len(set(self.executed)), 6)
        self.assertEqual(len({task['owner_claim']['nonce'] for task in claims}), 6)
        self.assertTrue(all(task['status'] == 'done' for task in claims))
        events = outbox.events_after(0, 50)['events']
        self.assertEqual(len(events), 6)
        self.assertTrue(all(row['kind'] == 'task_verified' for row in events))
        rows = [json.loads(line) for line in (self.root / 'memory/dispatcher_mentor/events.jsonl').read_text().splitlines()]
        for task in claims:
            pre = next(i for i, row in enumerate(rows) if row.get('kind') == 'owner_task_preflight' and row.get('task_id') == task['id'])
            proof = next(i for i, row in enumerate(rows) if row.get('kind') == 'experience_verified' and row.get('task_id') == task['id'])
            self.assertLess(pre, proof)

    def test_stop_arriving_after_claim_releases_native_lock_without_running_handler(self):
        state = self.task_state()
        task = next(iter(state['tasks'].values()))
        resource = threading.Lock()
        resource.acquire()
        task.update(status='running', owner_claim={'nonce': 'a' * 24}, owner_claim_epoch=time.time(), _held_locks=[resource])
        self.native['save_state'](state)
        with patch.object(mentor, 'stop_active', side_effect=[False, True]):
            self.native['run_one'](state, task)
        self.assertFalse(resource.locked())
        self.assertEqual(self.executed, [])
        self.assertEqual(task['status'], 'blocked')
        self.assertEqual(outbox.events_after(0)['events'][0]['kind'], 'task_blocked')

    def test_acceptance_without_native_proof_is_quarantined_not_completion(self):
        self.native['HANDLERS']['accepted_only_fixture'] = lambda task: (True, {'accepted': True, 'secret': 'private'})
        state = self.task_state(handler='accepted_only_fixture')
        task = self.native['owner_claim_ready'](state, set(), 'nox-agent-01')
        self.native['run_one'](state, task)
        event = outbox.events_after(0)['events'][0]
        self.assertEqual(event['kind'], 'verification_pending')
        self.assertEqual(event['learning'], 'QUARANTINED_OR_UNAVAILABLE')
        self.assertNotIn('private', json.dumps(event))
        self.assertFalse((self.root / 'distill/accepted.jsonl').exists())

    def test_delivery_failure_replays_journal_without_reexecuting_task(self):
        state = self.task_state()
        task = self.native['owner_claim_ready'](state, set(), 'nox-agent-01')
        with patch.object(outbox, 'publish', side_effect=OSError('fixture unavailable')):
            self.native['run_one'](state, task)
        self.assertEqual(len(self.executed), 1)
        self.assertEqual(outbox.events_after(0)['events'], [])
        self.native['_owner_lifecycle_coordinator'].drain(force=True)
        self.assertEqual(len(outbox.events_after(0)['events']), 1)
        self.assertEqual(len(self.executed), 1)

    def test_oversized_unrelated_journal_record_does_not_starve_real_report(self):
        journal = self.root / 'memory/dispatcher_mentor/events.jsonl'
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open('ab') as stream:
            stream.write(json.dumps({'unrelated': 'x' * 40000}).encode() + b'\n')
        state = self.task_state()
        task = self.native['owner_claim_ready'](state, set(), 'nox-agent-01')
        self.native['run_one'](state, task)
        self.native['_owner_lifecycle_coordinator'].drain(force=True)
        self.assertEqual(len(outbox.events_after(0)['events']), 1)
        self.assertEqual(len(self.executed), 1)

    def test_preflight_failure_releases_resource_and_never_executes_action(self):
        state = self.task_state()
        task = self.native['owner_claim_ready'](state, set(), 'nox-agent-01')
        resource = threading.Lock(); resource.acquire()
        task['_held_locks'] = [resource]
        with patch.object(lifecycle, 'preflight', side_effect=RuntimeError('fixture')):
            self.native['run_one'](state, task)
        self.assertFalse(resource.locked())
        self.assertEqual(task['status'], 'blocked')
        self.assertEqual(self.executed, [])

    def test_pinned_patch_preserves_native_claims_and_rejects_changed_source(self):
        repair = module('owner_native_repair')
        source = mentor.transform_dispatcher(repair.patch_dispatcher(FIXTURE.read_text()))
        pins = {'owner_mentor': '1' * 64, 'owner_event_outbox': '2' * 64}
        updated = lifecycle.patch_dispatcher(source, hashlib.sha256(source.encode()).hexdigest(), pins)
        self.assertIn('owner_task_lifecycle.bind_dispatcher', updated)
        self.assertIn('def owner_claim_ready', updated)
        with self.assertRaises(lifecycle.LifecycleHold):
            lifecycle.patch_dispatcher(updated, '0' * 64, pins)

    def test_complete_native_binding_starts_in_clean_python_without_test_imports(self):
        repair = module('owner_native_repair')
        media = module('owner_media_runtime')
        plans = module('owner_task_plans')
        names = ('owner_dispatcher_mentor', 'owner_component_tasks', 'owner_media_runtime',
                 'owner_task_plans', 'owner_task_lifecycle', 'owner_event_outbox', 'owner_senior_gateway')
        scripts = self.root / 'scripts'; scripts.mkdir(exist_ok=True)
        for name in names:
            (scripts / (name + '.py')).write_bytes((HERE / (name + '.py')).read_bytes())
        pins = {name: lifecycle.file_sha(scripts / (name + '.py')) for name in
                ('owner_media_runtime', 'owner_task_plans', 'owner_event_outbox', 'owner_senior_gateway')}
        pins['owner_mentor'] = lifecycle.file_sha(scripts / 'owner_dispatcher_mentor.py')
        source = mentor.transform_dispatcher(repair.patch_dispatcher(FIXTURE.read_text()))
        source = media.patch_dispatcher_media(source, hashlib.sha256(source.encode()).hexdigest())
        source = plans.patch_dispatcher(source, hashlib.sha256(source.encode()).hexdigest())
        source = lifecycle.patch_dispatcher(source, hashlib.sha256(source.encode()).hexdigest(), pins)
        (scripts / 'nox_dispatcher_t855u.py').write_text(source)
        runner = self.root / 'clean_start.py'
        runner.write_text('''import builtins, pathlib, sys
root = pathlib.Path(__file__).parent
scripts = str(root / 'scripts')
sys.path.insert(0, scripts)
original_import = builtins.__import__
def scoped_import(name, globals=None, locals=None, fromlist=(), level=0):
    # Relocate filesystem roots only; preserve the actual module bytes and
    # production import order, with no unittest/importlib.util preloading.
    if name.startswith('owner_') and sys.path[0] != scripts:
        sys.path.insert(0, scripts)
    value = original_import(name, globals, locals, fromlist, level)
    if name.startswith('owner_') and hasattr(value, 'ROOT'):
        value.ROOT = root
    return value
builtins.__import__ = scoped_import
path = root / 'scripts/nox_dispatcher_t855u.py'
namespace = {'__name__': 'clean_native_binding', '__file__': str(path)}
assert 'owner_senior_gateway' not in sys.modules
exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
assert all(namespace.get(key) for key in ('_owner_media_bound', '_owner_plans_bound', '_owner_lifecycle_bound'))
assert namespace['WORKERS'] == 6
assert callable(namespace['owner_senior_gateway'].consult_plan)
print('SIX_WORKER_NATIVE_BINDERS_READY')
''')
        result = subprocess.run([sys.executable, '-I', '-S', str(runner)],
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'SIX_WORKER_NATIVE_BINDERS_READY')

    def test_reviewed_plan_gateway_and_lifecycle_complete_one_native_six_branch_dag(self):
        mentor.record_experience, mentor.verify_success = self.original_experience, self.original_verify
        repair = module('owner_native_repair')
        components = module('owner_component_tasks')
        plans = module('owner_task_plans')
        gateway = module('owner_senior_gateway')
        source = mentor.transform_dispatcher(repair.patch_dispatcher(FIXTURE.read_text()))
        native = {'__name__': 'combined_native_test'}
        exec(compile(source, '<combined-native>', 'exec'), native)
        native.update({key: self.native[key] for key in ('ROOT', 'STATE', 'QUEUE', 'DISTILL', 'ev', 'log', 'journal')})
        native.update(_nox_owner_task_admitted=lambda task: True, ingest_architect_patch=lambda state: None,
                      ingest_owner_orders=lambda state: None, write_status=lambda state: None,
                      owner_task_plans=plans, owner_senior_gateway=gateway)
        component_handlers = {'owner.' + name: (lambda label=name: {'verified': True, 'scope': 'FIXTURE_' + label.upper(), 'blockers': []})
                              for name in plans.COMPONENTS}
        with patch.object(plans, 'ROOT', self.root), patch.object(gateway, 'ROOT', self.root), patch.dict(os.environ, {}, clear=True), \
                patch.dict(components.HANDLERS, component_handlers), patch.object(plans, 'pressure_snapshot', return_value={
                    'state': 'LOAD_OBSERVED', 'memory_ratio': .4, 'cpu_some_avg10': .1}):
            gateway.initialize()
            plans.bind_dispatcher(native)
            lifecycle.bind_dispatcher(native, {'owner_mentor': lifecycle.file_sha(mentor.__file__),
                'owner_event_outbox': lifecycle.file_sha(outbox.__file__), 'owner_task_plans': lifecycle.file_sha(plans.__file__),
                'owner_senior_gateway': lifecycle.file_sha(gateway.__file__)})
            parent = {'id': 'owner.integration.audit', 'handler': 'owner_order', 'status': 'pending', 'class': 'owner_order',
                      'priority': 0, 'deps': [], 'locks': [], 'retries': 0, 'max_retries': 1,
                      'params': {'plan': {'schema': plans.REQUEST, 'intent': 'audit'}}}
            state, busy = {'tasks': {parent['id']: parent}}, set()
            task = native['owner_claim_ready'](state, busy, 'nox-agent-01')
            native['run_one'](state, task); busy.remove(task['id'])
            self.assertEqual(parent['status'], 'pending')
            self.assertEqual(outbox.events_after(0)['events'], [])
            self.assertEqual(len(parent['owner_plan_children']), 6)
            for _ in range(2):
                with ThreadPoolExecutor(max_workers=6) as workers:
                    claims = list(workers.map(lambda i: native['owner_claim_ready'](state, busy, 'nox-agent-%02d' % (i + 1)), range(6)))
                claims = [task for task in claims if task is not None]
                self.assertEqual(len(claims), 3)
                with ThreadPoolExecutor(max_workers=3) as workers:
                    list(workers.map(lambda task: native['run_one'](state, task), claims))
                for task in claims:
                    busy.remove(task['id'])
            parent['next_try'] = 0  # Advance the fixture's native retry clock.
            join = native['owner_claim_ready'](state, busy, 'nox-agent-01')
            self.assertIs(join, parent)
            native['run_one'](state, join)
            native['_owner_lifecycle_coordinator'].drain(force=True)
            self.assertEqual(parent['status'], 'done')
            reports = outbox.events_after(0, 50)['events']
            self.assertEqual(len(reports), 7)
            self.assertTrue(all(row['kind'] == 'task_verified' for row in reports))
            self.assertEqual(reports[-1]['verification']['kind'], 'bounded_native_plan_join')
            self.assertEqual(reports[-1]['verification']['verified_children'], 6)
            self.assertTrue(all(row['lifecycle']['senior'] in ('MISSING_CREDENTIALS', 'SENIOR_CONTEXT_BUSY') for row in reports))
        plans._BOUND = None


if __name__ == '__main__':
    unittest.main()
