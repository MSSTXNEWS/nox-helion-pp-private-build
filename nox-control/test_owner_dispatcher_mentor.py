"""Native transform, unique claims, verified-learning and advice boundary tests."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
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

mentor = module('owner_dispatcher_mentor')
FIXTURE = Path('/tmp/nox_native_sources/nox_dispatcher_t855u.py')


class MentorTests(unittest.TestCase):
    def test_stop_active_fails_closed_on_state_aliases_and_dangling_flags(self):
        """Mirror canonical owner state STOP aliases; a broken symlink is still STOP."""
        with tempfile.TemporaryDirectory() as directory, patch.object(mentor, 'ROOT', Path(directory)):
            root = Path(directory)
            for name in ('state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with self.subTest(alias=name, kind='file'):
                    target.write_text('OWNER_MODEL_UPDATE')
                    self.assertTrue(mentor.stop_active())
                    target.unlink()
                with self.subTest(alias=name, kind='dangling_symlink'):
                    target.symlink_to(root / 'nonexistent_STOP_target')
                    self.assertTrue(mentor.stop_active())
                    target.unlink()

    def test_no_generated_commands_or_arbitrary_service_actions(self):
        for advice in ({'action': 'shell', 'reason_code': 'fix', 'service': None},
                       {'action': 'restart_service', 'reason_code': 'fix', 'service': 'nox-train-volta-t866u'},
                       {'action': 'escalate', 'reason_code': 'fix', 'service': None, 'command': 'anything'}):
            with self.assertRaises(RuntimeError):
                mentor.validate_advice(advice, ['nox-priority-scheduler'])

    def test_supervisor_status_rejects_error_multiline_or_bad_pid(self):
        from types import SimpleNamespace
        service = 'nox-priority-scheduler'
        cases = [
            (1, service + ' STOPPED Not started', 'UNKNOWN'),
            (0, service + ' STOPPED pid 123', 'UNKNOWN'),
            (0, service + ' RUNNING no-pid', 'UNKNOWN'),
            (0, service + ' STOPPED Not started' + chr(10) + service + ' RUNNING pid 123', 'UNKNOWN'),
            (0, service + ' STOPPED Not started', 'STOPPED'),
            (0, service + ' RUNNING pid 123 uptime 0:01', 'RUNNING'),
        ]
        for rc, output, wanted in cases:
            with self.subTest(rc=rc, output=output):
                completed = SimpleNamespace(returncode=rc, stdout=output)
                with patch.object(mentor.subprocess, 'run', return_value=completed):
                    self.assertEqual(mentor.service_state(service)['state'], wanted)

    def test_senior_recovery_refuses_fatal_even_when_suggested(self):
        config = {'model': 'senior', 'config_sha256': 'a' * 64}
        advice = {'action': 'restart_service', 'reason_code': 'failed',
                  'service': 'nox-priority-scheduler'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(mentor, 'ROOT', Path(directory)), patch.object(mentor, 'stop_active', return_value=False):
                with patch.object(mentor, 'discover_senior', return_value=config), patch.object(mentor, 'consult', return_value=advice):
                    with patch.object(mentor, 'service_state', return_value={'state': 'FATAL', 'pid': None}):
                        with patch.object(mentor.subprocess, 'run') as command:
                            task = {'id': 'mentor-fatal-gate', 'handler': 'ensure_scheduler', 'retries': 0}
                            result = mentor.on_failure(task, 'fatal')
                            self.assertEqual(result['state'], 'BLOCKED_SERVICE_STATE_NOT_REPAIRABLE')
                            self.assertEqual(task['status'], 'blocked')
                            command.assert_not_called()

    def test_senior_recovery_rechecks_stopped_identity_before_start(self):
        config = {'model': 'senior', 'config_sha256': 'a' * 64}
        advice = {'action': 'restart_service', 'reason_code': 'failed',
                  'service': 'nox-priority-scheduler'}
        stopped = {'state': 'STOPPED', 'pid': None}
        running = {'state': 'RUNNING', 'pid': 123}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(mentor, 'ROOT', Path(directory)), patch.object(mentor, 'stop_active', return_value=False):
                with patch.object(mentor, 'discover_senior', return_value=config), patch.object(mentor, 'consult', return_value=advice):
                    with patch.object(mentor, 'service_state', side_effect=[stopped, stopped, running]):
                        with patch.object(mentor.subprocess, 'run') as command:
                            task = {'id': 'mentor-race-gate', 'handler': 'ensure_scheduler', 'retries': 0}
                            result = mentor.on_failure(task, 'failed')
                            self.assertEqual(result['state'], 'BLOCKED_OWNER_STOP_OR_SERVICE_CHANGED')
                            self.assertEqual(task['status'], 'blocked')
                            command.assert_not_called()

    def test_recovery_budget_corrupt_existing_ledger_fails_closed(self):
        incident = 'a' * 64
        with tempfile.TemporaryDirectory() as directory, patch.object(mentor, 'ROOT', Path(directory)):
            path = Path(directory) / 'memory/dispatcher_mentor/incidents' / (incident + '.json')
            path.parent.mkdir(parents=True)
            corrupted = [
                '{incomplete',
                '[]',
                json.dumps({'incident': incident, 'attempts': -1, 'last_attempt': 0}),
                json.dumps({'incident': 'b' * 64, 'attempts': 0, 'last_attempt': 0}),
                json.dumps({'incident': incident, 'attempts': 0, 'last_attempt': 'oops'}),
                json.dumps({'incident': incident, 'attempts': 0, 'last_attempt': float('nan')}),
            ]
            for content in corrupted:
                with self.subTest(content=content):
                    path.write_text(content)
                    self.assertFalse(mentor.reserve_incident(incident))
                    self.assertEqual(path.read_text(), content)
            path.unlink()
            self.assertTrue(mentor.reserve_incident(incident))
            self.assertFalse(mentor.reserve_incident(incident))

    def test_no_senior_config_means_explicit_block_and_no_fake_consult(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)), patch.object(mentor, 'consult') as call:
            task = {'id': 'fixture', 'handler': 'verify_q4', 'retries': 1, 'max_retries': 3}
            result = mentor.on_failure(task, 'file missing')
            self.assertEqual(result['state'], 'BLOCKED_SENIOR_NOT_CONFIGURED_OR_UNSAFE')
            self.assertEqual(task['status'], 'blocked')
            self.assertTrue(result['needs_owner_input'])
            self.assertEqual(result['owner_question_code'], 'missing_file')
            self.assertTrue(result['owner_question'])
            call.assert_not_called()
            self.assertTrue((Path(root) / 'memory/dispatcher_mentor/events.jsonl').exists())

    def test_no_senior_transient_readonly_is_retried_once_with_durable_budget(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)):
            with patch.object(mentor, 'stop_active', return_value=False), patch.object(mentor, 'discover_senior', return_value=None):
                task = {'id': 'read-only-status', 'handler': 'verify_q4', 'retries': 0, 'max_retries': 3}
                first = mentor.on_failure(task, 'connection timed out')
                self.assertEqual(first['state'], 'BOUNDED_READ_ONLY_RETRY_NO_SENIOR')
                self.assertEqual(task['status'], 'pending')
                self.assertGreater(task['next_try'], time.time())
                second = mentor.on_failure(task, 'connection timed out')
                self.assertEqual(second['state'], 'BLOCKED_SENIOR_NOT_CONFIGURED_OR_UNSAFE')
                self.assertEqual(task['status'], 'blocked')
                ledger = list((Path(root) / 'memory/dispatcher_mentor/incidents').glob('*.json'))
                self.assertEqual(len(ledger), 1)
                self.assertEqual(json.loads(ledger[0].read_text())['attempts'], 1)

    def test_no_senior_never_autoretries_mutating_work_or_active_stop(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)), patch.object(mentor, 'discover_senior', return_value=None):
            for handler, stopping in (('exec_plan', False), ('start_qlora', False), ('new_gguf', False), ('verify_q4', True)):
                with self.subTest(handler=handler, stop=stopping), patch.object(mentor, 'stop_active', return_value=stopping):
                    task = {'id': 'unsafe-' + handler, 'handler': handler, 'retries': 0}
                    result = mentor.on_failure(task, 'connection timed out')
                    self.assertEqual(task['status'], 'blocked')
                    self.assertFalse(result.get('auto_retry', False))

    def test_existing_dispatcher_periodic_reciprocal_task_never_duplicates_or_replays_hold(self):
        import inspect
        import threading
        from types import SimpleNamespace
        transform = ast.parse(inspect.getsource(mentor.transform_dispatcher))
        replacements = [n for n in ast.walk(transform) if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name) and n.func.id == 'replace_function'
                        and len(n.args) >= 3 and isinstance(n.args[1], ast.Constant)
                        and n.args[1].value == 'ensure_watchdog_task']
        self.assertEqual(len(replacements), 1)
        source = replacements[0].args[2].value
        compile(source, '<owner-periodic-watchdog>', 'exec')
        clock = [1000.0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'scripts/owner_dispatcher_reciprocal_health.py').write_text('# approved native fixture')
            namespace = {'owner_mentor': SimpleNamespace(ROOT=root, service_state=lambda name: {'state':'RUNNING'}),
                         '_qlock': threading.RLock(), 'time': SimpleNamespace(time=lambda: clock[0])}
            exec(compile(source, '<owner-periodic-watchdog>', 'exec'), namespace)
            tasks = {'tasks': {}}
            namespace['ensure_watchdog_task'](tasks)
            rid = 'owner.dispatcher_reciprocal_health'
            self.assertEqual(tasks['tasks'][rid]['status'], 'pending')
            self.assertEqual(tasks['tasks'][rid]['handler'], 'owner_component_validate')
            self.assertEqual(tasks['tasks'][rid]['params']['component'], 'dispatcher_reciprocal_health')
            tasks['tasks'][rid]['status'] = 'done'
            clock[0] += 299
            namespace['ensure_watchdog_task'](tasks)
            self.assertEqual(tasks['tasks'][rid]['status'], 'done')
            clock[0] += 2
            namespace['ensure_watchdog_task'](tasks)
            self.assertEqual(tasks['tasks'][rid]['status'], 'pending')
            tasks['tasks'][rid]['status'] = 'blocked'
            clock[0] += 600
            namespace['ensure_watchdog_task'](tasks)
            self.assertEqual(tasks['tasks'][rid]['status'], 'blocked')
            tasks['tasks'][rid].update(status='done', last_rearm_epoch='bad')
            namespace['ensure_watchdog_task'](tasks)
            self.assertEqual(tasks['tasks'][rid]['status'], 'blocked')
            self.assertEqual(tasks['tasks'][rid]['note'], 'HOLD_RECIPROCAL_REARM_EPOCH_INVALID')
            self.assertEqual(sum(tid == rid for tid in tasks['tasks']), 1)

    def test_nox_chat_is_never_substituted_for_senior(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)):
            path = Path(root) / 'config/senior_model.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'enabled': True, 'role': 'senior', 'base_url': 'http://127.0.0.1:8081/v1', 'model': 'pretend-senior'}))
            self.assertIsNone(mentor.discover_senior())

    def test_repeated_incident_calls_senior_only_once_and_never_replays_exec(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)), patch.object(mentor, 'discover_senior', return_value={'model': 'configured-senior', 'config_sha256': 'a' * 64}), patch.object(mentor, 'consult', return_value={'action': 'retry_task', 'reason_code': 'transient', 'service': None}) as call:
            task = {'id': 'fixture', 'handler': 'exec_plan', 'retries': 1, 'max_retries': 3}
            self.assertEqual(mentor.on_failure(task, 'timeout')['state'], 'BLOCKED_ESCALATED')
            self.assertEqual(mentor.on_failure(task, 'timeout')['state'], 'BLOCKED_DUPLICATE_OR_CONSULT_BUDGET')
            self.assertEqual(call.call_count, 1)
            context = call.call_args.args[1]
            self.assertNotIn('error_text', context)

    def test_failure_and_unverified_success_never_enter_training(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)):
            accepted = Path(root) / 'accepted.jsonl'
            for ok in (False, True):
                row = mentor.record_experience(ok, {'id': 'fixture', 'handler': 'track'}, 'work', {'guess': True}, 'unverified suggestion', accepted)
                self.assertFalse(row['accepted'])
                self.assertEqual(row['partition'], 'quarantine')
            self.assertFalse(accepted.exists())

    def test_component_receipt_preserves_scope_and_blockers_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as root, patch.object(mentor, 'ROOT', Path(root)):
            base = Path(root)
            script = base / 'scripts/owner_component_tasks.py'
            script.parent.mkdir()
            script.write_text('# native fixture\n')
            task = {'id': 'owner.storage', 'handler': 'owner_component', 'owner_claim_epoch': time.time() - 1}
            receipt = base / 'state/owner_components/owner.storage.json'
            receipt.parent.mkdir(parents=True)
            doc = {'schema': 'NOX_OWNER_COMPONENT_V1', 'schema_version': 1, 'task_id': task['id'],
                   'success': True, 'verified': True, 'started_at': time.time(), 'pid': os.getpid(),
                   'source_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
                   'evidence': {'verified': True, 'scope': 'STORAGE_INVENTORY_ONLY', 'blockers': ['OAUTH_REQUIRED']}}
            receipt.write_text(json.dumps(doc))
            evidence = {'schema': 'NOX_OWNER_COMPONENT_V1', 'schema_version': 1,
                        'receipt_path': str(receipt), 'receipt_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(),
                        'scope': 'STORAGE_INVENTORY_ONLY', 'blockers': ['OAUTH_REQUIRED']}
            row = mentor.record_experience(True, task, 'storage check', evidence, accepted_path=base / 'accepted.jsonl')
            self.assertEqual(row['verification']['scope'], 'STORAGE_INVENTORY_ONLY')
            self.assertEqual(row['verification']['blockers'], ['OAUTH_REQUIRED'])
            again = mentor.record_experience(True, task, 'storage check', evidence, accepted_path=base / 'accepted.jsonl')
            self.assertTrue(again['duplicate'])
            receipt.write_text('{}')
            self.assertIsNone(mentor.verify_success(task, evidence))

    def test_worker_count_config_is_not_six_native_pids(self):
        """Configured concurrency is not evidence of OS process identity."""
        task = {'id': 'owner.dispatcher', 'handler': 'owner_component_validate',
                'params': {'component': 'dispatcher_workers'}}
        with patch.object(mentor, 'read_json', return_value={
                'workers': 6, 'min_workers': 6, 'max_workers': 6}):
            outcome = mentor.component_validation(task)
            self.assertIsNone(outcome['verification'])
            self.assertEqual(outcome['state'], 'HOLD_WORKERS_PID_STARTTICKS_UNVERIFIED')
            verified, result = mentor.handle_component_validation(task)
            self.assertFalse(verified)
            self.assertEqual(result, 'HOLD_WORKERS_PID_STARTTICKS_UNVERIFIED')
            self.assertIsNone(mentor.verify_success(task))

    def test_historical_step_receipt_is_not_live_optimizer_update(self):
        """Do not publish previous global_step as new successful training."""
        task = {'id': 'owner.training_stack', 'handler': 'owner_component_validate',
                'params': {'component': 'training_checkpoint'}}
        old_receipt = {'state': 'VERIFIED_BOUNDED_ADAPTER_UPDATE',
                       'adapter_delta_verified': True, 'global_step': 25}
        with patch.object(mentor, 'read_json', return_value=old_receipt):
            outcome = mentor.component_validation(task)
            self.assertIsNone(outcome['verification'])
            self.assertEqual(outcome['state'], 'HOLD_FRESH_OPTIMIZER_RESTORE_UNVERIFIED')
            verified, result = mentor.handle_component_validation(task)
            self.assertFalse(verified)
            self.assertEqual(result, 'HOLD_FRESH_OPTIMIZER_RESTORE_UNVERIFIED')
            self.assertIsNone(mentor.verify_success(task))

    def test_secret_redaction_is_not_the_broken_native_capture_group(self):
        output = mentor.redact('api_key="example-secret-value" Bearer abcdef123456 hf_abcdefghijklmnop')
        self.assertNotIn('example-secret-value', output)
        self.assertNotIn('abcdef123456', output)
        self.assertNotIn('hf_abcdefghijklmnop', output)


class VerifiedJournalRecallV14Tests(unittest.TestCase):
    def test_reusable_repair_requires_exact_task_accepted_native_receipt(self):
        lifecycle = module('owner_task_lifecycle')
        schema = 'NOX_DISPATCHER_MENTOR_V1'
        verified = {'kind': 'native_supervisor_running', 'service': 'nox-priority-scheduler'}
        def event(kind, **fields):
            return {'schema': schema, 'kind': kind, **fields}
        with tempfile.TemporaryDirectory() as directory, patch.object(lifecycle, 'ROOT', Path(directory)):
            path = Path(directory) / 'memory/dispatcher_mentor/events.jsonl'
            path.parent.mkdir(parents=True)
            rows = [
                event('experience_verified', task_id='current', partition='train',
                      accepted=True, verification=verified, dedup_sha256='a' * 64),
                event('experience_verified', task_id='current', partition='holdout',
                      accepted=False, verification=verified, dedup_sha256='b' * 64),
                event('experience_verified', task_id='current', partition='train',
                      accepted=False, verification=verified, dedup_sha256='c' * 64),
                event('experience_verified', task_id='other', handler='shared',
                      partition='train', accepted=True, verification=verified,
                      dedup_sha256='d' * 64),
                event('experience_verified', task_id='current', partition='train',
                      accepted=True, verification={'kind': 'model_claim'},
                      dedup_sha256='e' * 64),
                event('experience_verified', task_id='current', partition='train',
                      accepted=True, verification=verified, dedup_sha256='invalid'),
                event('error_observed', task_id='other', handler='shared',
                      category='timeout', accepted=False),
                event('experience_quarantined', task_id='current', accepted=False),
            ]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = lifecycle.journal_recall({'id': 'current', 'handler': 'shared'})
            self.assertEqual(result['state'], 'JOURNAL_RECALLED')
            self.assertEqual(result['verified'], 1)
            self.assertEqual(result['errors'], 1)
            self.assertEqual(result['quarantined'], 1)
            self.assertEqual(result['error_categories'], ['timeout'])
            self.assertEqual(len(result['references_sha256']), 3)


class SharedOptimizationCacheV14Tests(unittest.TestCase):
    def test_sibling_context_cache_respects_handler_params_and_failure(self):
        """A parent claim cannot lend its optimization advice to a different task."""
        lifecycle = module('owner_task_lifecycle')

        class Gateway:
            def __init__(self):
                self.calls = []

            def consult_plan(self, technical, deadline_seconds=2.0):
                self.calls.append(technical.copy())
                return {'state': 'CONSULTED', 'models_consulted': 1}

        local = {'verified': 0, 'errors': 0, 'error_categories': []}
        plan = {'mode': 'NORMAL'}
        base = {'id': 'child-a', 'owner_parent_id': 'parent-123',
                'owner_plan_id': 'plan-123', 'handler': 'verify_q4',
                'params': {'operation': 'worker_verify'}, 'note': ''}
        gateway = Gateway()
        with patch.object(lifecycle, 'semantic_recall', return_value={'state': 'HOLD_NATIVE'}), \
             patch.object(lifecycle, 'technical_details',
                          side_effect=lambda task, *_: {
                              'task_intent': task['handler'],
                              'operation': task['params']['operation'],
                              'error_note': task.get('note', '')}):
            lifecycle._CACHE.clear()
            try:
                first = lifecycle.shared_context(base, local, plan, gateway)
                sibling = {**base, 'id': 'child-b'}
                repeated = lifecycle.shared_context(sibling, local, plan, gateway)
                self.assertTrue(repeated['cache_reused'])
                self.assertEqual(first['context_sha256'], repeated['context_sha256'])
                self.assertEqual(len(gateway.calls), 1)

                variations = [
                    {**base, 'handler': 'ensure_downloads'},
                    {**base, 'params': {'operation': 'component:memory'}},
                    {**base, 'note': 'CUDA out of memory'},
                ]
                for task in variations:
                    result = lifecycle.shared_context(task, local, plan, gateway)
                    self.assertFalse(result['cache_reused'])
                    self.assertNotEqual(result['context_sha256'], first['context_sha256'])
                    self.assertEqual(result['technical_context']['task_intent'], task['handler'])
                    self.assertEqual(result['technical_context']['operation'],
                                     task['params']['operation'])
                    self.assertEqual(result['technical_context']['error_note'],
                                     task.get('note', ''))
                self.assertEqual(len(gateway.calls), 4)
            finally:
                lifecycle._CACHE.clear()


@unittest.skipUnless(FIXTURE.exists(), 'Requires retrieved pinned native dispatcher fixture')
class NativeTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repair = module('owner_native_repair')
        module('owner_component_tasks')
        original = FIXTURE.read_text()
        cls.source = mentor.transform_dispatcher(repair.patch_dispatcher(original))
        cls.native = {'__name__': 'native_test'}
        exec(compile(cls.source, '<native-transform>', 'exec'), cls.native)

    def test_transform_is_idempotent_and_worker_count_is_real_six(self):
        self.assertEqual(mentor.transform_dispatcher(self.source), self.source)
        self.assertEqual(self.native['WORKERS'], 6)
        self.assertEqual(len(self.native['_wstate']), 6)
        self.assertEqual(mentor.worker_config({'workers': 32})['min_workers'], 6)

    def test_all_backoffs_and_zero_priority_are_respected(self):
        tasks = {name: {'id': name, 'status': 'pending', 'class': 'owner_order', 'priority': priority, 'deps': [], 'next_try': after}
                 for name, priority, after in (('a-delayed', 0, time.time() + 200), ('b-delayed', 0, time.time() + 200), ('c-one', 1, 0), ('z-zero', 0, 0))}
        with patch.dict(self.native, {'_nox_owner_task_admitted': lambda task: True}):
            self.assertEqual(self.native['pick_ready']({'tasks': tasks}, set())['id'], 'z-zero')

    def test_concurrent_claims_are_unique_and_saved_before_return(self):
        tasks = {str(i): {'id': str(i), 'status': 'pending', 'class': 'owner_order', 'priority': 0, 'deps': [], 'locks': []} for i in range(6)}
        state = {'tasks': tasks}
        busy = set()
        saved = []
        def save(st):
            saved.append(sum(task['status'] == 'running' for task in st['tasks'].values()))
        with patch.dict(self.native, {'_nox_owner_task_admitted': lambda task: True,
              'ingest_architect_patch': lambda st: None, 'ingest_owner_orders': lambda st: None, 'save_state': save}):
            with ThreadPoolExecutor(max_workers=12) as pool:
                claims = list(pool.map(lambda i: self.native['owner_claim_ready'](state, busy, 'test-' + str(i)), range(12)))
        claims = [task for task in claims if task]
        self.assertEqual(len(claims), 6)
        self.assertEqual(len({task['id'] for task in claims}), 6)
        self.assertEqual(len({task['owner_claim']['nonce'] for task in claims}), 6)
        self.assertEqual(saved, [1, 2, 3, 4, 5, 6])

    def test_cold_restart_does_not_replay_an_unverified_child(self):
        main = next(node for node in ast.parse(self.source).body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        recovery = next(node for node in main.body if isinstance(node, ast.For))
        state = {'tasks': {'old': {'id': 'old', 'status': 'running'}}}
        namespace = {**self.native, 'st': state}
        exec(compile(ast.Module(body=[recovery], type_ignores=[]), '<recovery>', 'exec'), namespace)
        self.assertEqual(state['tasks']['old']['status'], 'blocked')
        self.native['upsert'](state, {'id': 'old', 'status': 'pending'})
        self.assertEqual(state['tasks']['old']['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
