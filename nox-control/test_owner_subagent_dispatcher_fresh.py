"""Local tests of per-submit admission; no model, native files or worker spawn."""
from pathlib import Path
import importlib.util
import json
import threading
import types
import unittest
from unittest.mock import Mock, patch


class GateError(RuntimeError):
    pass


class AutoHold(ValueError):
    pass


autonomy = types.ModuleType('owner_autonomy_pool')
autonomy.AutoHold = AutoHold
processes = types.ModuleType('owner_subagent_processes')
processes.GateError = GateError
processes.Subagents = Mock(side_effect=AssertionError('No real worker may spawn in this test'))
spec = importlib.util.spec_from_file_location('fresh_subagent_test_target',
    Path(__file__).with_name('owner_subagent_dispatcher_fresh.py'))
binding = importlib.util.module_from_spec(spec)
with patch.dict('sys.modules', {'owner_autonomy_pool': autonomy,
                               'owner_subagent_processes': processes}):
    spec.loader.exec_module(binding)


def snapshot(**changes):
    return {'native_verified': True, 'instance_id': 60509551, 'stop_active': False,
            'source_sha_verified': True, 'owner_scope_verified': True,
            'cgroup_memory_ratio': .50, 'cpu_pressure': 1.0, **changes}


def native_with_pool():
    native = binding.Native.__new__(binding.Native)
    native.ns = {'_qlock': threading.RLock()}
    native.lock = threading.RLock()
    native.policy = {'sha256': 'a' * 64}
    native.catalog = {'tasks': [{'id': 'review.runtime', 'params': {'role': 'runtime'}}]}
    native.state = {'tasks': {}}
    native.pool = Mock()
    native.pool.active = {}
    native.pool.submit.side_effect = GateError('HOLD_TEST_AFTER_SUBMIT')
    native.interrupted = {}
    native.completed = {}
    native._claim_current = Mock(return_value=True)
    native.stop_active = Mock(return_value=False)
    native.writer_lease = Mock(return_value=True)
    native.read_resource_snapshot = Mock(return_value=snapshot())
    native.ensure_processes = Mock(side_effect=AssertionError('Existing pool must be retained'))
    native.close_pool = Mock(side_effect=AssertionError('Resource hold must not kill existing workers'))
    task = {'id': 'review.runtime', 'status': 'running', 'title': 'Review resources',
            'owner_claim': {'nonce': 'a' * 24},
            'params': {'role': 'runtime', 'policy_sha256': 'a' * 64, 'job_id': 'review-job'}}
    return native, task


class FreshSubmissionTests(unittest.TestCase):
    def test_existing_pool_does_not_bypass_new_memory_pressure(self):
        native, task = native_with_pool()
        pool = native.pool
        native.read_resource_snapshot.return_value = snapshot(cgroup_memory_ratio=.95)
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'))
        native.read_resource_snapshot.assert_called_once()
        pool.submit.assert_not_called()
        self.assertIs(native.pool, pool)
        native.close_pool.assert_not_called()

    def test_existing_pool_does_not_bypass_new_cpu_pressure(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.return_value = snapshot(cpu_pressure=50)
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'))
        native.pool.submit.assert_not_called()

    def test_existing_pool_does_not_bypass_chat_or_slot_hold(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.side_effect = AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_ADMISSION'))
        native.pool.submit.assert_not_called()

    def test_clear_existing_pool_checks_before_exactly_one_submit(self):
        native, task = native_with_pool()
        events = []
        native.read_resource_snapshot.side_effect = lambda: events.append('snapshot') or snapshot()
        def submit(_):
            events.append('submit')
            raise GateError('HOLD_TEST_AFTER_SUBMIT')
        native.pool.submit.side_effect = submit
        with patch.object(binding, 'chat_priority_active', return_value=False):
            self.assertEqual(native._handle(task), (False, 'HOLD_TEST_AFTER_SUBMIT'))
        self.assertEqual(events, ['snapshot', 'submit'])
        native.pool.submit.assert_called_once()
        native.ensure_processes.assert_not_called()

    def test_new_pool_rechecks_after_process_creation(self):
        native, task = native_with_pool()
        pool = native.pool
        native.pool = None
        native.read_resource_snapshot.side_effect = [snapshot(), snapshot(cpu_pressure=75)]
        def create(count):
            self.assertEqual(count, 3)
            native.pool = pool
            return True
        native.ensure_processes.side_effect = create
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'))
        self.assertEqual(native.read_resource_snapshot.call_count, 2)
        native.ensure_processes.assert_called_once_with(3)
        pool.submit.assert_not_called()

    def test_invalid_fresh_observations_never_admit(self):
        cases = [snapshot(cgroup_memory_ratio=float('nan')),
                 snapshot(cpu_pressure=float('inf')),
                 snapshot(cpu_pressure=True), snapshot(cgroup_memory_ratio=-1),
                 snapshot(stop_active=True), snapshot(owner_scope_verified=False),
                 snapshot(native_verified='true'), None]
        for value in cases:
            with self.subTest(value=value):
                native, task = native_with_pool()
                native.read_resource_snapshot.return_value = value
                self.assertEqual(native._handle(task)[0], 'wait')
                native.pool.submit.assert_not_called()

    def test_review_status_reports_only_catalog_counts_not_model_prose(self):
        native, _ = native_with_pool()
        native.catalog = {'tasks': [{'id': role} for role in ('runtime', 'memory', 'weights')]}
        native.state = {'tasks': {
            'runtime': {'status': 'done', 'result': {'answer': 'hallucinated prose'}},
            'memory': {'status': 'running'}, 'weights': {'status': 'blocked'},
            'unrelated-owner-task': {'status': 'done'}}}
        native.pool.active = {'memory': 'memory'}
        result = native.review_status()
        self.assertEqual(result['catalog_tasks'], 3)
        self.assertEqual(result['queue_counts']['done'], 1)
        self.assertEqual(result['queue_counts']['running'], 1)
        self.assertEqual(result['queue_counts']['blocked'], 1)
        self.assertEqual(result['owned_model_requests_active'], 1)
        for key in ('model_answers_authoritative', 'candidate_actions_applied',
                    'training_updates_verified', 'capacity_maximum_measured'):
            self.assertIs(result[key], False)
        self.assertNotIn('hallucinated prose', json.dumps(result))
        self.assertNotIn('unrelated-owner-task', json.dumps(result))

    def test_unadmitted_and_unknown_status_are_not_called_done(self):
        native, _ = native_with_pool()
        native.catalog = {'tasks': [{'id': 'a'}, {'id': 'b'}]}
        native.state = {'tasks': {'a': {'status': 'unexpected'}}}
        result = native.review_status()
        self.assertEqual(result['queue_counts']['unknown'], 1)
        self.assertEqual(result['queue_counts']['not_admitted'], 1)
        self.assertEqual(result['queue_counts']['done'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
