"""Local tests of per-submit admission; no model, native files or worker spawn."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

JOB_ID = 'nox-native-' + 'd' * 24


class GateError(RuntimeError):
    pass


class AutoHold(ValueError):
    pass


autonomy = types.ModuleType('owner_autonomy_pool')
autonomy.AutoHold = AutoHold
autonomy.RESOURCE_ADMISSION_MAX_AGE_SECONDS = 5.0
autonomy.fingerprint = lambda value: hashlib.sha256(json.dumps(
    value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    allow_nan=False).encode()).hexdigest()
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
    value = {'native_verified': True, 'instance_id': 60509551, 'stop_active': False,
             'source_sha_verified': True, 'owner_scope_verified': True,
             'cgroup_memory_ratio': .50, 'cpu_pressure': 1.0, 'io_pressure': 1.0,
             'disk_free_ratio': .25, 'disk_free_bytes': 16 * 1024**3,
             'disk_total_bytes': 64 * 1024**3,
             'writer_lease': {'schema': 'NOX_SUBAGENT_WRITER_LEASE_V1',
                 'acquired': True, 'scope': 'EXCLUSIVE_NATIVE_SUBAGENT_WRITER',
                 'lock_path': '/root/nox/state/dispatcher/native_subagents.lock',
                 'device': 1, 'inode': 2, 'task_id': 'review.runtime',
                 'claim_nonce': 'a' * 24, 'lease_id': 'd' * 64,
                 'owner': binding.process_identity(os.getpid()),
                 'acquired_at': time.time(), 'source_sha256': 'c' * 64},
             **changes}
    value['resource_admission_allowed'] = True
    value['resource_admission_observed_at'] = time.time()
    value['resource_admission_snapshot_sha256'] = autonomy.fingerprint(value)
    return value


def native_with_pool():
    native = binding.Native.__new__(binding.Native)
    native.lock = threading.RLock()
    native.policy = {'sha256': 'a' * 64}
    native.source = 'c' * 64
    native.catalog = {'tasks': [{'id': 'review.runtime', 'params': {'role': 'runtime'}}]}
    native._test_events = []
    native._test_tmpdir = tempfile.TemporaryDirectory()
    state_path = Path(native._test_tmpdir.name) / 'state.json'
    task = {'id': 'review.runtime', 'status': 'running', 'title': 'Review resources',
            'owner_claim': {'nonce': 'a' * 24},
            'params': {'role': 'runtime', 'policy_sha256': 'a' * 64, 'job_id': JOB_ID}}
    row = {'id': task['id'], 'handler': binding.HANDLER, 'status': 'running',
           'owner_claim': task['owner_claim'], 'params': task['params']}
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
    native.pool.shutdown_and_drain = Mock(return_value=[])
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
        claim = {'nonce': 'a' * 24, 'pid': 999}
        params = {'role': 'runtime', 'policy_sha256': 'a' * 64,
                  'job_id': JOB_ID}
        intent = {'task_id': 'kept', 'claim_nonce': claim['nonce'], 'role': 'runtime',
                  'policy_sha': params['policy_sha256'], 'job_id': params['job_id'],
                  'state': 'UNCERTAIN'}
        row = {'id': 'kept', 'handler': binding.HANDLER, 'status': 'running',
               'owner_claim': claim, 'params': params, 'native_submit_intent': intent}
        value.policy = {'sha256': 'a' * 64}
        value.source = 'c' * 64
        value.state = {'tasks': {'kept': row}}
        value._test_tmpdir = tempfile.TemporaryDirectory()
        state_path = Path(value._test_tmpdir.name) / 'state.json'
        def save_state(state):
            state_path.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')
        value.ns = {'_qlock': threading.RLock(), 'STATE': state_path,
                    'save_state': save_state,
                    'owner_mentor': types.SimpleNamespace(clean=lambda item: item)}
        save_state(value.state)
        value.completed = {'kept': {'kind': 'RESULT', 'role': 'runtime', 'id': 'kept',
            'state': 'CANDIDATE_NOT_APPLIED', 'pid': 100, 'elapsed_ms': 1,
            'answer': 'bounded candidate',
            'native_observation': {'claim': claim['nonce'], 'operation': 'runtime',
                'policy_ack': {'sha256': params['policy_sha256'], 'full_file_read': True},
                'worker': {'pid': 100}}}}
        value.interrupted = {}
        children = {role: self.Child(100+i) for i, role in enumerate(binding.ROLES)}
        value.pool = Mock()
        value.pool.processes = children
        value.pool.active = active or {}
        value.pool.shutdown_and_drain = Mock(return_value=[])
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

    def test_idle_failed_worker_replaces_only_dead_role_after_result_reconciliation(self):
        native, children = self.native()
        pool = native.pool
        old_runtime, old_memory, old_weights = (
            children['runtime'], children['memory'], children['weights'])
        old_runtime.alive = False
        replacement = self.Child(999)
        identities = {
            child.pid: {'pid': child.pid, 'ppid': 999,
                        'process_starttime': child.pid + 1}
            for child in (*children.values(), replacement)
        }
        def replace_dead_only():
            children['runtime'] = replacement
            pool.heartbeats['runtime'] = time.time()
        pool._replace_idle_dead_pool.side_effect = replace_dead_only
        native.close_pool = Mock(side_effect=AssertionError('No full pool restart'))
        with patch.object(binding, 'process_identity',
                          side_effect=lambda pid: identities.get(pid)), \
             patch.object(binding.os, 'getpid', return_value=999), \
             patch.object(binding, 'Subagents') as ctor:
            self.assertFalse(native.ensure_processes(3))
            pool._replace_idle_dead_pool.assert_not_called()
            self.assertIn('kept', native.completed)
            native.completed.clear()  # Simulated owner readback/settlement.
            self.assertTrue(native.ensure_processes(3))
            ctor.assert_not_called()
        pool._replace_idle_dead_pool.assert_called_once_with()
        native.close_pool.assert_not_called()
        self.assertIs(children['runtime'], replacement)
        self.assertIs(children['memory'], old_memory)
        self.assertIs(children['weights'], old_weights)
        self.assertFalse(old_runtime.is_alive())

    def test_stale_heartbeat_without_proven_death_holds_existing_peers(self):
        native, children = self.native()
        native.completed.clear()
        native.pool.heartbeats['runtime'] = time.time() - 601
        identities = {
            child.pid: {'pid': child.pid, 'ppid': 999,
                        'process_starttime': child.pid + 1}
            for child in children.values()
        }
        with patch.object(binding, 'process_identity',
                          side_effect=lambda pid: identities.get(pid)), \
             patch.object(binding.os, 'getpid', return_value=999), \
             patch.object(binding, 'Subagents') as ctor:
            self.assertFalse(native.ensure_processes(3))
            ctor.assert_not_called()
        native.pool._replace_idle_dead_pool.assert_not_called()

    def test_replacement_hold_keeps_live_pool_intact(self):
        native, children = self.native()
        native.completed.clear()
        children['runtime'].alive = False
        healthy = (children['memory'], children['weights'])
        native.pool._replace_idle_dead_pool.side_effect = GateError(
            'HOLD_SUBAGENT_POOL_NOT_READY')
        native.close_pool = Mock(side_effect=AssertionError('No destructive fallback'))
        with patch.object(binding, 'process_identity', return_value=None), \
             patch.object(binding.os, 'getpid', return_value=999), \
             patch.object(binding, 'Subagents') as ctor:
            self.assertFalse(native.ensure_processes(3))
            ctor.assert_not_called()
        self.assertIs(native.pool.processes['memory'], healthy[0])
        self.assertIs(native.pool.processes['weights'], healthy[1])
        native.close_pool.assert_not_called()

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
            disk_free_ratio=.04, disk_free_bytes=4 * 1024**3,
            disk_total_bytes=100 * 1024**3)
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

    def test_writer_lease_receipt_binds_successful_flock_to_task_and_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'state/dispatcher').mkdir(parents=True)
            native = binding.Native.__new__(binding.Native)
            native.lock = threading.RLock()
            native.lease_fd = None
            native.lease_identity = None
            native.task_lease_receipt = None
            native.source = 'c' * 64
            with patch.object(binding, 'ROOT', root):
                self.assertTrue(native.writer_lease('review.runtime', 'a' * 24))
            lease = native.task_lease_receipt
            self.assertIsInstance(lease, dict)
            self.assertIs(lease['acquired'], True)
            self.assertEqual(lease['scope'], 'EXCLUSIVE_NATIVE_SUBAGENT_WRITER')
            self.assertEqual((lease['task_id'], lease['claim_nonce']),
                             ('review.runtime', 'a' * 24))
            self.assertEqual((lease['device'], lease['inode']),
                             (native.lease_identity['device'], native.lease_identity['inode']))
            self.assertEqual(lease['owner'], binding.process_identity(os.getpid()))
            self.assertEqual(lease['source_sha256'], native.source)
            os.close(native.lease_fd)

    def test_existing_pool_does_not_bypass_chat_or_slot_hold(self):
        native, task = native_with_pool()
        native.read_resource_snapshot.side_effect = AutoHold('HOLD_NATIVE_CHAT_PRIORITY')
        self.assertEqual(native._handle(task), ('wait', 'HOLD_NATIVE_SUBAGENT_ADMISSION'))
        native.pool.submit.assert_not_called()

    def test_stop_after_submit_persists_one_shot_intent_and_prevents_replay(self):
        native, task = native_with_pool()
        events = native._test_events
        sample = snapshot()
        native.read_resource_snapshot.side_effect = lambda *args, **kwargs: events.append('snapshot') or sample
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
        self.assertEqual({key: intent[key] for key in
                          ('task_id', 'claim_nonce', 'role', 'policy_sha', 'job_id', 'state')},
                         {'task_id': task['id'], 'claim_nonce': 'a' * 24,
                          'role': 'runtime', 'policy_sha': 'a' * 64,
                          'job_id': JOB_ID, 'state': 'UNCERTAIN'})
        self.assertEqual(intent['resource_admission'], sample)
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


    def test_stop_commits_result_from_final_close_pool_drain(self):
        native, task = native_with_pool()
        events = native._test_events
        sample = snapshot()
        native.read_resource_snapshot.side_effect = lambda *args, **kwargs: events.append('snapshot') or sample
        native.stop_active.side_effect = [False, True, True]
        result_event = {'kind': 'RESULT', 'role': 'runtime',
            'id': task['id'], 'state': 'CANDIDATE_NOT_APPLIED', 'pid': 1234,
            'elapsed_ms': 1, 'answer': 'bounded candidate',
            'native_observation': {'claim': 'a' * 24, 'operation': 'runtime',
                'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                'worker': {'pid': 1234}}}
        native.pool.submit.side_effect = lambda _: events.append('submit')
        native.pool.poll.side_effect = [None] * 64
        native.pool.active = {'runtime': task['id']}
        native.pool.shutdown_and_drain = Mock(return_value=[result_event])
        native.pool.__exit__ = Mock()
        native.close_pool = binding.Native.close_pool.__get__(native, binding.Native)
        native.ns['owner_mentor'] = types.SimpleNamespace(clean=lambda value: value)
        with patch.object(binding, 'chat_priority_active', return_value=False), \
             patch.object(binding, 'remember', side_effect=lambda receipt: {
                 'native_verified': True, 'task_id': task['id'], 'job_id': JOB_ID,
                 'receipt_sha256': binding.digest(binding.encoded(receipt))}):
            accepted, evidence = native._handle(task)
        self.assertTrue(accepted)
        self.assertEqual(evidence['receipt']['worker_result'], result_event)
        self.assertEqual(native.state['tasks'][task['id']]['native_submit_intent']['state'], 'S03_VERIFIED')
        self.assertIsNone(native.pool)

    def test_s03_attempt_marker_authorizes_only_one_poster(self):
        native, task = native_with_pool()
        claim = {'nonce': 'a' * 24}
        job_id = task['params']['job_id']
        task.update(handler=binding.HANDLER, owner_claim=claim)
        row = native.state['tasks'][task['id']]
        row['owner_claim'] = claim
        intent = {'task_id': task['id'], 'claim_nonce': claim['nonce'],
                  'role': 'runtime', 'policy_sha': 'a' * 64,
                  'job_id': job_id, 'state': 'UNCERTAIN',
                  'resource_admission': snapshot()}
        task['native_submit_intent'] = intent
        row['native_submit_intent'] = intent
        native.ns['save_state'](native.state)
        native.ns['owner_mentor'] = types.SimpleNamespace(clean=lambda value: value)
        event = {'kind': 'RESULT', 'role': 'runtime', 'id': task['id'],
                 'state': 'CANDIDATE_NOT_APPLIED', 'pid': 1234,
                 'elapsed_ms': 1, 'answer': 'bounded candidate',
                 'native_observation': {'claim': claim['nonce'], 'operation': 'runtime',
                     'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                     'worker': {'pid': 1234}}}
        checkpoint = native._checkpoint_pending_result(event)
        first, first_poster = native._mark_s03_write_attempted(task, checkpoint)
        second, second_poster = native._mark_s03_write_attempted(task, checkpoint)
        self.assertEqual(first['state'], 'S03_WRITE_ATTEMPTED')
        self.assertEqual(second, first)
        self.assertTrue(first_poster)
        self.assertFalse(second_poster)

    def test_same_parent_reconciles_checkpoint_after_pool_yield(self):
        native, task = native_with_pool()
        claim = {'nonce': 'a' * 24, 'pid': 4242}
        job_id = 'nox-native-' + 'd' * 24
        task.update(handler=binding.HANDLER, owner_claim=claim)
        task['params']['job_id'] = job_id
        intent = {'task_id': task['id'], 'claim_nonce': claim['nonce'],
                  'role': 'runtime', 'policy_sha': 'a' * 64,
                  'job_id': job_id, 'state': 'UNCERTAIN',
                  'resource_admission': snapshot()}
        task['native_submit_intent'] = intent
        native.state['tasks'][task['id']] = task
        native.ns['save_state'](native.state)
        native.ns['owner_mentor'] = types.SimpleNamespace(clean=lambda value: value)
        event = {'kind': 'RESULT', 'role': 'runtime', 'id': task['id'],
                 'state': 'CANDIDATE_NOT_APPLIED', 'pid': 1234,
                 'elapsed_ms': 1, 'answer': 'bounded candidate',
                 'native_observation': {'claim': claim['nonce'], 'operation': 'runtime',
                     'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                     'worker': {'pid': 1234}}}
        old_pool = native.pool
        old_pool.active = {'runtime': task['id']}
        old_pool.poll.return_value = None
        def shutdown_and_drain(*, on_validated_result):
            on_validated_result(event)
            return [event]
        old_pool.shutdown_and_drain.side_effect = shutdown_and_drain
        native.close_pool = binding.Native.close_pool.__get__(native, binding.Native)
        native.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
        self.assertIsNone(native.pool)
        persisted = json.loads(native.ns['STATE'].read_text(encoding='utf-8'))
        checkpointed = persisted['tasks'][task['id']]
        self.assertEqual(checkpointed['native_submit_intent']['state'], 'RESULT_CHECKPOINTED')
        self.assertEqual(checkpointed['native_pending_result']['event'], event)

        restarted = binding.Native.__new__(binding.Native)
        restarted.ns = dict(native.ns)
        restarted.ns['_qlock'] = threading.RLock()
        restarted.state = persisted
        restarted.lock = threading.RLock()
        restarted.policy = native.policy
        restarted.source = native.source
        restarted.pool = None
        restarted.completed = {}
        restarted.interrupted = {}
        restarted.owner_allowed = Mock(return_value=True)
        restarted.stop_active = Mock(return_value=False)
        restarted.writer_lease = Mock(return_value=True)
        restarted.verify = Mock(return_value={'kind': 'exact_s03_receipt'})
        root = Path(native._test_tmpdir.name) / 'root'
        (root / 'state').mkdir(parents=True)
        (root / 'state' / 'owner_maintenance.lock').touch()
        proof = {'native_verified': True, 'task_id': task['id'],
                 'job_id': job_id,
                 'receipt_sha256': binding.digest(binding.encoded(
                     checkpointed['native_pending_result']['receipt']))}
        def one_s03_write(receipt):
            disk = json.loads(native.ns['STATE'].read_text(encoding='utf-8'))
            self.assertEqual(disk['tasks'][task['id']]['native_submit_intent']['state'],
                             'S03_WRITE_ATTEMPTED')
            self.assertEqual(receipt, checkpointed['native_pending_result']['receipt'])
            return proof
        remember_once = Mock(side_effect=one_s03_write)
        with patch.object(binding.os, 'getpid', return_value=4242), \
             patch.object(binding, 'ROOT', root), \
             patch.object(binding, 'chat_priority_active', return_value=False), \
             patch.object(binding, 'remember', remember_once):
            self.assertEqual(restarted._reconcile_pending_result_queue(restarted.state), 1)
        row = restarted.state['tasks'][task['id']]
        self.assertEqual(row['native_submit_intent']['state'], 'S03_VERIFIED')
        self.assertNotIn('native_pending_result', row)
        remember_once.assert_called_once()
        old_pool.submit.assert_not_called()

    def test_uncertain_intent_with_exact_s03_receipt_completes_without_replay(self):
        native, task = native_with_pool()
        job_id = 'nox-native-' + 'd' * 24
        claim = {'nonce': 'a' * 24, 'pid': 4242}
        task.update(handler=binding.HANDLER, owner_claim=claim)
        task['params']['job_id'] = job_id
        intent = {'task_id': task['id'], 'claim_nonce': claim['nonce'],
                  'role': 'runtime', 'policy_sha': 'a' * 64,
                  'job_id': job_id, 'state': 'UNCERTAIN'}
        task['native_submit_intent'] = intent
        native.state['tasks'][task['id']] = task
        native.ns['save_state'](native.state)
        native._test_events.clear()
        native.owner_allowed = Mock(return_value=True)
        native.stop_active = Mock(return_value=False)
        native.writer_lease = Mock(return_value=True)
        native.pool.active = {}

        event = {'id': task['id'], 'state': 'CANDIDATE_NOT_APPLIED', 'pid': 1234,
                 'elapsed_ms': 1,
                 'native_observation': {'claim': claim['nonce'],
                     'operation': 'runtime',
                     'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                     'worker': {'pid': 1234}}}
        receipt = {'schema': binding.RECEIPT,
                   'phase': 'NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED',
                   'task_id': task['id'], 'job_id': job_id, 'claim': claim,
                   'source_sha256': native.source, 'policy_sha256': 'a' * 64,
                   'worker_result': event, 'finished_at': 1.0,
                   'training_started': False, 'optimizer_steps_verified': False,
                   'service_or_weights_changed': False}
        text_value = binding.memory_text(receipt)
        receipt_sha = binding.digest(binding.encoded(receipt))
        item = (77, text_value, json.dumps({'receipt': receipt}),
                binding.digest(('M2|' + text_value).encode()))

        class Rows:
            def fetchall(self):
                return [item]

        class Connection:
            def execute(self, *args):
                return Rows()

        class ConnectionContext:
            def __enter__(self):
                return Connection()
            def __exit__(self, *args):
                return False

        state_root = Path(native._test_tmpdir.name) / 'root'
        lock_path = state_root / 'state' / 'owner_maintenance.lock'
        lock_path.parent.mkdir(parents=True)
        lock_path.touch()
        with patch.object(binding, 'ROOT', state_root):
            with patch.object(binding, 's03_connection', return_value=ConnectionContext()):
                with patch.object(binding, 'chat_priority_active', return_value=False):
                    recovered = native._reconcile_s03_verified_queue(native.state)

        self.assertEqual(recovered, 1)
        row = native.state['tasks'][task['id']]
        self.assertEqual(row['status'], 'done')
        self.assertEqual(row['native_submit_intent'],
                         {**intent, 'state': 'S03_VERIFIED',
                          'result_sha256': receipt_sha,
                          's03_receipt_sha256': receipt_sha})
        self.assertEqual(row['note'], 'S03_VERIFIED_RECOVERED')
        native.pool.submit.assert_not_called()
        persisted = json.loads(native.ns['STATE'].read_text())
        self.assertEqual(persisted['tasks'][task['id']]['status'], 'done')


    def test_drain_checkpoints_polled_result_before_publishing_completed(self):
        native, task = native_with_pool()
        claim = {'nonce': 'a' * 24, 'pid': 4242}
        task.update(handler=binding.HANDLER, owner_claim=claim)
        row = native.state['tasks'][task['id']]
        row['owner_claim'] = claim
        intent = {'task_id': task['id'], 'claim_nonce': claim['nonce'],
                  'role': 'runtime', 'policy_sha': 'a' * 64,
                  'job_id': JOB_ID, 'state': 'UNCERTAIN',
                  'resource_admission': snapshot()}
        task['native_submit_intent'] = intent
        row['native_submit_intent'] = intent
        native.ns['save_state'](native.state)
        native.ns['owner_mentor'] = types.SimpleNamespace(clean=lambda value: value)
        event = {'kind': 'RESULT', 'role': 'runtime', 'id': task['id'],
                 'state': 'CANDIDATE_NOT_APPLIED', 'pid': 1234,
                 'elapsed_ms': 1, 'answer': 'bounded candidate',
                 'native_observation': {'claim': claim['nonce'], 'operation': 'runtime',
                     'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                     'worker': {'pid': 1234}}}
        native.pool.active = {'runtime': task['id']}
        def poll(*, timeout, on_validated_result):
            self.assertEqual(timeout, 0)
            checkpoint = on_validated_result(event)
            disk = json.loads(native.ns['STATE'].read_text(encoding='utf-8'))
            self.assertEqual(disk['tasks'][task['id']]['native_pending_result'], checkpoint)
            return event
        native.pool.poll.side_effect = poll
        binding.Native._drain(native)
        self.assertEqual(native.completed[task['id']], event)
        self.assertEqual(
            json.loads(native.ns['STATE'].read_text(encoding='utf-8'))
                ['tasks'][task['id']]['native_submit_intent']['state'],
            'RESULT_CHECKPOINTED')

    def test_shutdown_captures_result_published_after_pre_shutdown_drain(self):
        native, task = native_with_pool()
        event = {'id': task['id'], 'state': 'CANDIDATE_NOT_APPLIED',
                 'role': 'runtime', 'pid': 1234, 'elapsed_ms': 1,
                 'answer': 'candidate',
                 'native_observation': {'claim': 'a' * 24,
                     'policy_ack': {'sha256': 'a' * 64, 'full_file_read': True},
                     'worker': {'pid': 1234}}}
        native.pool.active = {'runtime': task['id']}
        native.pool.poll.return_value = None
        native.pool.shutdown_and_drain = Mock(return_value=[event])
        closed_pool = native.pool
        native.close_pool = binding.Native.close_pool.__get__(native, binding.Native)
        native.close_pool('WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
        self.assertEqual(native.completed[task['id']], event)
        self.assertEqual(native.interrupted[task['id']],
                         'WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
        closed_pool.shutdown_and_drain.assert_called_once()
        self.assertIsNone(native.pool)

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
        bad_nan = snapshot()
        bad_nan['cgroup_memory_ratio'] = float('nan')
        bad_inf = snapshot()
        bad_inf['cpu_pressure'] = float('inf')
        cases = [bad_nan, bad_inf, snapshot(cpu_pressure=True), snapshot(cgroup_memory_ratio=-1),
                 snapshot(stop_active=True), snapshot(owner_scope_verified=False),
                 snapshot(native_verified='true'), snapshot(disk_total_bytes=0),
                 snapshot(disk_total_bytes=32 * 1024**3), None]
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
