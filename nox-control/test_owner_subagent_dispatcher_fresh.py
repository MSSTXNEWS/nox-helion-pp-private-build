"""Local tests of per-submit admission; no model, native files or worker spawn."""
from pathlib import Path
import importlib.util
import json
import tempfile
import threading
import time
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
            'cgroup_memory_ratio': .50, 'cpu_pressure': 1.0, 'io_pressure': 1.0,
            'disk_free_ratio': .25, 'disk_free_bytes': 16 * 1024**3, **changes}


def native_with_pool():
    native = binding.Native.__new__(binding.Native)
    native.lock = threading.RLock()
    native.policy = {'sha256': 'a' * 64}
    native.catalog = {'tasks': [{'id': 'review.runtime', 'params': {'role': 'runtime'}}]}
    native._test_events = []
    native._test_tmpdir = tempfile.TemporaryDirectory()
    state_path = Path(native._test_tmpdir.name) / 'state.json'
    task = {'id': 'review.runtime', 'status': 'running', 'title': 'Review resources',
            'owner_claim': {'nonce': 'a' * 24},
            'params': {'role': 'runtime', 'policy_sha256': 'a' * 64, 'job_id': 'review-job'}}
    row = {'id': task['id'], 'status': 'running', 'owner_claim': task['owner_claim'],
           'params': task['params']}
    native.state = {'tasks': {task['id']: row}}
    def save_state(state):
        native._test_events.append('save_state')
        state_path.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')
    native.ns = {'_qlock': threading.RLock(), 'STATE': state_path, 'save_state': save_state}
    save_state(native.state)
    native._test_events.clear()
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
    return native, task


class PoolLifecycleTests(unittest.TestCase):
    class Child:
        def __init__(self, pid, alive=True):
            self.pid, self.alive = pid, alive
        def is_alive(self):
            return self.alive

    def native(self, active=None, heartbeats=None):
        value = binding.Native.__new__(binding.Native)
        value.lock = threading.RLock()
        value.stop_active = Mock(return_value=False)
        value.completed = {'kept': {'id': 'kept', 'state': 'CANDIDATE_NOT_APPLIED'}}
        value.interrupted = {}
        children = {role: self.Child(100+i) for i, role in enumerate(binding.ROLES)}
        value.pool = Mock()
        value.pool.processes = children
        value.pool.active = active or {}
        value.pool.heartbeats = heartbeats or {role: time.time() for role in binding.ROLES}
        value.pool.poll.return_value = None
        value.pool.__exit__ = Mock()
        return value, children

    def test_process_readback_reports_fresh_heartbeat_proof(self):
        native, children = self.native()
        identities = {child.pid: {'pid': child.pid, 'ppid': 999, 'process_starttime': child.pid+1}
                      for child in children.values()}
        with patch.object(binding, 'process_identity', side_effect=lambda pid: identities[pid]), \
             patch.object(binding.os, 'getpid', return_value=999):
            rows = native.process_readback()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['native_heartbeat_verified'] is True for row in rows))
        self.assertTrue(all(0 <= row['heartbeat_age_seconds'] <= 600 for row in rows))

    def test_idle_failed_worker_restarts_pool_and_preserves_parent_results(self):
        native, children = self.native()
        children['runtime'].alive = False
        native.close_pool = binding.Native.close_pool.__get__(native, binding.Native)
        new = Mock()
        new.processes = {role: self.Child(200+i) for i, role in enumerate(binding.ROLES)}
        new.active = {}
        new.heartbeats = {role: time.time() for role in binding.ROLES}
        new.poll.return_value = None
        identities = {child.pid: {'pid': child.pid, 'ppid': 999, 'process_starttime': child.pid+1}
                      for child in new.processes.values()}
        with patch.object(binding, 'process_identity', side_effect=lambda pid: identities.get(pid.pid if hasattr(pid, 'pid') else pid)), \
             patch.object(binding.os, 'getpid', return_value=999), \
             patch.object(binding, 'Subagents') as ctor:
            ctor.return_value.__enter__.return_value = new
            self.assertTrue(native.ensure_processes(3))
        ctor.assert_called_once_with(list(binding.ROLES), timeout=60, worker_prepare=binding.worker_input)
        self.assertEqual(native.completed['kept']['id'], 'kept')

    def test_active_worker_failure_holds_without_pool_replacement(self):
        native, children = self.native(active={'runtime': 'job-1'})
        children['runtime'].alive = False
        with patch.object(binding, 'process_identity', return_value=None), \
             patch.object(binding.os, 'getpid', return_value=999), \
             patch.object(binding, 'Subagents') as ctor:
            self.assertFalse(native.ensure_processes(3))
        ctor.assert_not_called()
        self.assertIn('runtime', native.pool.processes)


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

    def test_existing_pool_does_not_bypass_new_io_pressure(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.return_value = snapshot(io_pressure=50)
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'))
        native.pool.submit.assert_not_called()

    def test_existing_pool_does_not_bypass_low_disk_headroom(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.return_value = snapshot(
            disk_free_ratio=.04, disk_free_bytes=4 * 1024**3)
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_RESOURCE_PRESSURE'))
        native.pool.submit.assert_not_called()

    def test_reclaimable_file_cache_is_not_counted_as_working_set(self):
        working, inactive, ratio = binding.cgroup_memory_working_set(
            194_034_532_352, 194_065_203_200,
            'anon 3000000000\ninactive_file 190000000000\n')
        self.assertEqual(inactive, 190_000_000_000)
        self.assertEqual(working, 4_034_532_352)
        self.assertLess(ratio, .05)
        self.assertIsNone(binding.resource_wait_reason(snapshot(cgroup_memory_ratio=ratio)))

    def test_existing_pool_does_not_bypass_chat_or_slot_hold(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.side_effect = AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_ADMISSION'))
        native.pool.submit.assert_not_called()

    def test_stop_after_submit_persists_one_shot_intent_and_prevents_replay(self):
        native, task = native_with_pool()
        events = native._test_events
        native.read_resource_snapshot.side_effect = lambda: events.append('snapshot') or snapshot()
        native.stop_active.side_effect = [False, True]
        native.pool.submit.side_effect = lambda _: events.append('submit')
        native.pool.poll.return_value = None
        native.close_pool = Mock()
        with patch.object(binding, 'chat_priority_active', return_value=False):
            self.assertEqual(native._handle(task),
                             (False, 'HOLD_SUBAGENT_SUBMIT_OUTCOME_UNRESOLVED'))
        self.assertEqual(events, ['snapshot', 'save_state', 'submit'])
        native.pool.submit.assert_called_once()
        native.ensure_processes.assert_not_called()
        intent = native.state['tasks'][task['id']]['native_submit_intent']
        self.assertEqual(intent, {'task_id': task['id'], 'claim_nonce': 'a' * 24,
                                  'role': 'runtime', 'policy_sha': 'a' * 64,
                                  'job_id': 'review-job', 'state': 'UNCERTAIN'})
        # Simulate the original queue claiming the same task again with a new nonce.
        new_claim = {'nonce': 'b' * 24}
        task['owner_claim'] = new_claim
        native.state['tasks'][task['id']]['owner_claim'] = new_claim
        native.ns['save_state'](native.state)
        calls_before_retry = native.pool.submit.call_count
        with patch.object(binding, 'chat_priority_active', return_value=False):
            self.assertEqual(native._handle(task),
                             (False, 'HOLD_SUBAGENT_SUBMIT_INTENT_MISMATCH'))
        self.assertEqual(native.pool.submit.call_count, calls_before_retry)

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
