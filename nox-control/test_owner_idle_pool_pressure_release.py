"""Regression tests for owner-only idle-pool memory pressure recovery."""
from pathlib import Path
import importlib.util
import re
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent
PROCESS_PATH = ROOT / 'systemic_relay_20261118' / 'runtime' / 'owner_subagent_processes.py'
DISPATCHER_PATH = ROOT / 'systemic_relay_20261118' / 'runtime' / 'owner_subagent_dispatcher.py'


def load_module(name, path, stubs=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if stubs:
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
    else:
        spec.loader.exec_module(module)
    return module


processes = load_module('idle_pressure_processes', PROCESS_PATH)


class FakeFlag:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class FakeQueue:
    def __init__(self, empty=True):
        self._empty = empty
        self.closed = False
        self.cancelled = False

    def empty(self):
        return self._empty

    def cancel_join_thread(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class FakePipe:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, pid=123, exits=True, exitcode=0):
        self.pid = pid
        self.exits = exits
        self.result_exitcode = exitcode
        self.alive = True
        self.exitcode = None
        self.join_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0

    def join(self, timeout=None):
        self.join_calls += 1
        if self.exits:
            self.alive = False
            self.exitcode = self.result_exitcode

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminate_calls += 1
        self.alive = False

    def kill(self):
        self.kill_calls += 1
        self.alive = False


def idle_subagents(exits=True, queue_empty=True, exitcode=0):
    instance = processes.Subagents.__new__(processes.Subagents)
    process = FakeProcess(exits=exits, exitcode=exitcode)
    instance.active = {}
    instance.started = {}
    instance.deadlines = {'worker': 1}
    instance.cancellations = {'worker': FakeFlag()}
    instance.inboxes = {'worker': FakeQueue(queue_empty)}
    instance.outboxes = {'worker': FakePipe()}
    instance.senders = {'worker': types.SimpleNamespace(connection=FakePipe())}
    instance.processes = {'worker': process}
    return instance, process


class GracefulShutdownTests(unittest.TestCase):
    def test_idle_generation_stops_cooperatively_without_forced_signals(self):
        instance, process = idle_subagents()
        result = instance.close_idle(timeout=2)
        self.assertEqual(result['state'], 'IDLE_POOL_GRACEFULLY_STOPPED')
        self.assertEqual(result['forced_signals'], 0)
        self.assertTrue(instance.cancellations['worker'].was_set)
        self.assertEqual(process.terminate_calls, 0)
        self.assertEqual(process.kill_calls, 0)
        self.assertTrue(instance.inboxes['worker'].closed)
        self.assertTrue(instance.outboxes['worker'].closed)
        self.assertTrue(instance.senders['worker'].connection.closed)
        self.assertEqual(instance.deadlines, {})

    def test_active_or_started_pool_is_untouched(self):
        for field in ('active', 'started'):
            with self.subTest(field=field):
                instance, process = idle_subagents()
                setattr(instance, field, {'worker': 'task-1'})
                with self.assertRaisesRegex(processes.GateError, 'HOLD_SUBAGENT_IDLE_CLOSE_STATE'):
                    instance.close_idle()
                self.assertFalse(instance.cancellations['worker'].was_set)
                self.assertEqual(process.join_calls, 0)
                self.assertEqual(process.terminate_calls + process.kill_calls, 0)

    def test_queued_or_unknown_work_is_untouched(self):
        instance, process = idle_subagents(queue_empty=False)
        with self.assertRaisesRegex(processes.GateError, 'HOLD_SUBAGENT_IDLE_QUEUE_NOT_EMPTY'):
            instance.close_idle()
        self.assertFalse(instance.cancellations['worker'].was_set)
        self.assertEqual(process.join_calls, 0)
        self.assertEqual(process.terminate_calls + process.kill_calls, 0)

    def test_unresponsive_worker_is_retained_without_terminate_or_kill(self):
        instance, process = idle_subagents(exits=False)
        with self.assertRaisesRegex(processes.GateError, 'HOLD_SUBAGENT_GRACEFUL_SHUTDOWN_UNKNOWN'):
            instance.close_idle(timeout=0.1)
        self.assertTrue(instance.cancellations['worker'].was_set)
        self.assertTrue(process.alive)
        self.assertEqual(process.terminate_calls, 0)
        self.assertEqual(process.kill_calls, 0)
        self.assertFalse(instance.inboxes['worker'].closed)

    def test_nonzero_exit_is_not_reported_as_graceful_release(self):
        instance, process = idle_subagents(exitcode=1)
        with self.assertRaisesRegex(processes.GateError, 'HOLD_SUBAGENT_GRACEFUL_SHUTDOWN_UNKNOWN'):
            instance.close_idle(timeout=0.1)
        self.assertFalse(process.alive)
        self.assertEqual(process.exitcode, 1)
        self.assertEqual(process.terminate_calls + process.kill_calls, 0)
        self.assertFalse(instance.inboxes['worker'].closed)
        self.assertEqual(instance.processes['worker'], process)


def load_dispatcher():
    autonomy = types.ModuleType('owner_autonomy_pool')
    autonomy.AutoHold = type('AutoHold', (ValueError,), {})
    autonomy.SHA = re.compile(r'^[a-f0-9]{64}$')
    project_executor = types.ModuleType('owner_project_executor')
    project_executor.PROJECT_HANDLER = 'owner_project'
    project_executor.PROJECT_MODE = 'PROJECT_MODE'
    process_stub = types.ModuleType('owner_subagent_processes')
    process_stub.GateError = processes.GateError
    process_stub.Subagents = processes.Subagents
    return load_module('idle_pressure_dispatcher', DISPATCHER_PATH, {
        'owner_autonomy_pool': autonomy,
        'owner_project_executor': project_executor,
        'owner_subagent_processes': process_stub,
    })


class ReleaseGateTests(unittest.TestCase):
    def test_outer_pending_task_stays_durable_and_unclaimed_during_pause(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)

        class QueueLock:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        task = {'handler':dispatcher.HANDLER, 'status':'pending',
                'owner_claim':None, 'native_worker_lease':None,
                'native_pool_recovery':None}
        tasks = {'task-1':task}
        native.ns = {'_qlock':QueueLock()}
        native.state = {'tasks':tasks}
        native.allowed_handlers = lambda: {dispatcher.HANDLER}

        before = dict(task)
        self.assertTrue(native._native_claims_settled())
        self.assertEqual(tasks['task-1'], before)
        self.assertEqual(tasks['task-1']['status'], 'pending')
        self.assertIsNone(tasks['task-1']['owner_claim'])
        self.assertIsNone(tasks['task-1']['native_worker_lease'])

    def test_release_gate_requires_validated_memory_pressure_and_idle_owned_pool(self):
        dispatcher = load_dispatcher()
        snapshot = {'native_verified': True, 'instance_id': 60509551,
                    'stop_active': False, 'owner_scope_verified': True,
                    'source_sha_verified': True}
        base = {'owner_authorized': True, 'stop_clear': True, 'writer_lease': True,
                'maintenance_shared': True, 'pool_present': True, 'active': False,
                'started': False, 'completed': False, 'interrupted': False,
                'recovery_uncertain': False, 'worker_identity_valid': True,
                'claims_settled': True}
        self.assertTrue(dispatcher.idle_pool_release_gate(
            snapshot, 'HOLD_BOUNDED_CPU_HEADROOM', **base))
        for field, value in (('owner_authorized', False), ('stop_clear', False),
                             ('writer_lease', False), ('maintenance_shared', False),
                             ('pool_present', False), ('active', True), ('started', True),
                             ('completed', True), ('interrupted', True),
                             ('recovery_uncertain', True),
                             ('worker_identity_valid', False), ('claims_settled', False)):
            with self.subTest(field=field):
                changed = {**base, field: value}
                self.assertFalse(dispatcher.idle_pool_release_gate(
                    snapshot, 'HOLD_BOUNDED_CPU_HEADROOM', **changed))
        self.assertFalse(dispatcher.idle_pool_release_gate(
            snapshot, 'HOLD_NATIVE_CHAT_PRIORITY', **base))
        self.assertFalse(dispatcher.idle_pool_release_gate(
            {**snapshot, 'stop_active': True}, 'HOLD_BOUNDED_CPU_HEADROOM', **base))


    def test_recovery_requires_three_separated_fresh_clean_snapshots(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)
        native._resource_pressure_paused = True
        native._resource_recovery_samples = 0
        native._resource_recovery_last_at = 0.0
        native._resource_pressure_release = None
        observed = [100.0, 102.0, 105.0, 110.0]
        with patch.object(dispatcher.time, 'time', side_effect=observed):
            results = [native._resource_recovery_observation(
                {'observed_at': stamp}, None) for stamp in observed]
        self.assertEqual(results, [False, False, False, True])
        self.assertFalse(native._resource_pressure_paused)
        self.assertEqual(native._resource_pressure_release['state'],
                         'RESOURCE_RECOVERY_STABLE')

    def test_recovery_pressure_or_unknown_resets_stability_counter(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)
        native._resource_pressure_paused = True
        native._resource_recovery_samples = 2
        native._resource_recovery_last_at = 95.0
        native._resource_pressure_release = None
        with patch.object(dispatcher.time, 'time', return_value=100.0):
            self.assertFalse(native._resource_recovery_observation(
                {'observed_at': 100.0}, 'HOLD_BOUNDED_CPU_HEADROOM'))
        self.assertEqual(native._resource_recovery_samples, 0)
        self.assertTrue(native._resource_pressure_paused)


if __name__ == '__main__':
    unittest.main(verbosity=2)
