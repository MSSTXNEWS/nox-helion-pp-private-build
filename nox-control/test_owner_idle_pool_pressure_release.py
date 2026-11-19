"""Regression tests for owner-only idle-pool memory pressure recovery."""
from pathlib import Path
import importlib.util
import tempfile
import re
import sys
import threading
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).parent
PROCESS_PATH = ROOT / 'systemic_relay_20261118' / 'runtime' / 'owner_subagent_processes.py'
DISPATCHER_PATH = ROOT / 'systemic_relay_20261118' / 'runtime' / 'owner_subagent_dispatcher.py'
PROJECT_PATH = ROOT / 'systemic_relay_20261118' / 'runtime' / 'owner_project_native.py'
AUTONOMY_PATH = ROOT / 'owner_autonomy_pool.py'


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
autonomy_pool = load_module('idle_pressure_autonomy_pool', AUTONOMY_PATH)


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

    def test_missing_queue_task_map_and_running_rows_without_claim_are_unsettled(self):
        dispatcher = load_dispatcher()

        class QueueLock:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False

        native = dispatcher.Native.__new__(dispatcher.Native)
        native.ns = {'_qlock':QueueLock()}
        native.allowed_handlers = lambda: {dispatcher.HANDLER}
        native.state = {'schema':'queue-without-task-map'}
        self.assertFalse(native._native_claims_settled())
        native.state = {'schema':'queue-state', 'tasks':{
            'task-1':{'handler':dispatcher.HANDLER, 'status':'running'}}}
        self.assertFalse(native._native_claims_settled())

    def test_s03_admission_readback_intermediate_row_is_unsettled(self):
        dispatcher = load_dispatcher()

        class QueueLock:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False

        native = dispatcher.Native.__new__(dispatcher.Native)
        native.ns = {'_qlock':QueueLock()}
        native.allowed_handlers = lambda: {dispatcher.HANDLER}
        native.state = {'tasks':{'task-1':{'handler':dispatcher.HANDLER,
            'status':'blocked', 'note':'WAIT_S03_ADMISSION_READBACK',
            'native_admission':{}, 'native_admission_s03':None}}}
        self.assertFalse(native._native_claims_settled())

    def test_dispatcher_refill_callback_honors_pressure_pause_before_side_effects(self):
        calls = []
        native = types.SimpleNamespace(
            owner_allowed=lambda:True, stop_active=lambda:False,
            writer_lease=lambda:True, ensure_processes=lambda _:calls.append('start'),
            process_readback=lambda:[], native_duplicate_check=lambda _:False,
            native_queue_claim=lambda **_:calls.append('claim'),
            s03_readback=lambda _:None, _resource_pressure_paused=True)
        result = autonomy_pool.admit_native_tick(native, tasks=[], status={}, mode='NORMAL',
                                                  memory_ratio=0.1)
        self.assertEqual(result['state'],'WAIT_RESOURCE_RECOVERY_STABILITY')
        self.assertEqual(calls, [])

    def test_missing_latch_after_restart_holds_until_owner_baseline_is_seeded(self):
        dispatcher = load_dispatcher()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native_subagent_resource_latch.json'
            native = dispatcher.Native.__new__(dispatcher.Native)
            native.source = 'a'*64
            native.policy = {'sha256':'b'*64}
            native.config = {'owner_request':'request-1'}
            native.lock = threading.RLock()
            native._resource_pressure_paused = False
            native._resource_pressure_latch_uncertain = False
            native._resource_pressure_release = None
            native._resource_pressure_latch_generation = 0
            native._resource_pressure_latch_state = None
            native._resource_pressure_latch_reason = None
            native._resource_pressure_latch_sha256 = None
            with patch.object(dispatcher,'RESOURCE_PRESSURE_LATCH',path):
                # Models a restart after an earlier PAUSED write failed: the
                # absent file cannot clear the uncertain in-memory state.
                native._load_resource_pressure_latch()
                self.assertTrue(native._resource_pressure_paused)
                self.assertTrue(native._resource_pressure_latch_uncertain)
                self.assertEqual(native._resource_pressure_release['state'],
                    'HOLD_RESOURCE_PRESSURE_LATCH_BASELINE_REQUIRED')
                self.assertFalse(native._resource_recovery_ready())

                calls = []
                refill = types.SimpleNamespace(
                    owner_allowed=lambda:True, stop_active=lambda:False,
                    writer_lease=lambda:True, ensure_processes=lambda _:calls.append('start'),
                    process_readback=lambda:[], native_duplicate_check=lambda _:False,
                    native_queue_claim=lambda **_:calls.append('claim'),
                    s03_readback=lambda _:None, _resource_pressure_paused=True,
                    _resource_pressure_latch_uncertain=True)
                result = autonomy_pool.admit_native_tick(
                    refill, tasks=[], status={}, mode='NORMAL', memory_ratio=0.1)
                self.assertEqual(result['state'],'WAIT_RESOURCE_RECOVERY_STABILITY')
                self.assertEqual(calls, [])

                baseline = {'schema':dispatcher.RESOURCE_PRESSURE_LATCH_SCHEMA,
                    'instance_id':60509551, 'state':'RECOVERED', 'generation':1,
                    'reason':'HOLD_BOUNDED_CPU_HEADROOM', 'source_sha256':'a'*64,
                    'policy_sha256':'b'*64, 'owner_request':'request-1',
                    'updated_at':100.0,
                    'healthy_snapshots':dispatcher.RESOURCE_RECOVERY_REQUIRED_SNAPSHOTS}
                dispatcher.write_resource_pressure_latch(path, baseline, None)
                native._resource_pressure_paused = False
                native._resource_pressure_latch_uncertain = False
                native._resource_pressure_release = None
                with patch.object(dispatcher,'RESOURCE_PRESSURE_LATCH',path):
                    native._load_resource_pressure_latch()
                self.assertFalse(native._resource_pressure_paused)
                self.assertFalse(native._resource_pressure_latch_uncertain)
                self.assertEqual(native._resource_pressure_latch_state,'RECOVERED')

    def test_owner_seeded_recovered_baseline_must_match_runtime_contract(self):
        dispatcher = load_dispatcher()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native_subagent_resource_latch.json'
            baseline = {'schema':dispatcher.RESOURCE_PRESSURE_LATCH_SCHEMA,
                'instance_id':60509551, 'state':'RECOVERED', 'generation':1,
                'reason':'HOLD_BOUNDED_CPU_HEADROOM', 'source_sha256':'c'*64,
                'policy_sha256':'b'*64, 'owner_request':'request-1',
                'updated_at':100.0,
                'healthy_snapshots':dispatcher.RESOURCE_RECOVERY_REQUIRED_SNAPSHOTS}
            dispatcher.write_resource_pressure_latch(path, baseline, None)
            native = dispatcher.Native.__new__(dispatcher.Native)
            native.source = 'a'*64
            native.policy = {'sha256':'b'*64}
            native.config = {'owner_request':'request-1'}
            native._resource_pressure_paused = False
            native._resource_pressure_latch_uncertain = False
            native._resource_pressure_release = None
            native._resource_pressure_latch_generation = 0
            native._resource_pressure_latch_state = None
            native._resource_pressure_latch_reason = None
            native._resource_pressure_latch_sha256 = None
            with patch.object(dispatcher,'RESOURCE_PRESSURE_LATCH',path):
                native._load_resource_pressure_latch()
            self.assertTrue(native._resource_pressure_paused)
            self.assertTrue(native._resource_pressure_latch_uncertain)
            self.assertEqual(native._resource_pressure_release['state'],
                'HOLD_RESOURCE_PRESSURE_LATCH_CONTRACT_CHANGED')

    def test_project_handler_pressure_pause_vetoes_before_refill_or_submit(self):
        dispatcher = load_dispatcher()
        executor_stub = types.ModuleType('owner_project_executor')
        executor_stub.PROJECT_HANDLER = 'owner_native_project_work'
        project_module = load_module('idle_pressure_project_native', PROJECT_PATH, {
            'owner_project_executor':executor_stub,
            'owner_subagent_processes':types.SimpleNamespace(GateError=processes.GateError),
        })
        binding = project_module.ProjectBinding.__new__(project_module.ProjectBinding)
        task = {'id':'project-1','handler':'owner_native_project_work',
                'source_sha256':'a'*64,'queue_id':'Q1_RUNTIME_CHAT',
                'params':{'parent_task_id':'1A01','plan_sha256':'b'*64,
                          'source_sha256':'a'*64,'job_id':'job-1'},
                'owner_claim':{'nonce':'c'*24}}
        native = types.SimpleNamespace(
            catalog={'tasks':[{'id':'project-1','handler':'owner_native_project_work',
                'params':{'parent_task_id':'1A01','plan_sha256':'b'*64},
                'queue_id':'Q1_RUNTIME_CHAT','source_sha256':'a'*64}]},
            source='a'*64, _claim_current=lambda *args, **kwargs:True,
            config={}, lock=threading.RLock(), _resource_pressure_paused=True,
            _resource_pressure_latch_uncertain=False,
            _resource_recovery_ready=lambda:False,
            _fresh_admission_reason=lambda **kwargs: self.fail('admission gate must not run'),
            ensure_processes=lambda *_:self.fail('pool must not refill'), pool=None)
        binding.native = native
        binding.reference = lambda params: {'plan_sha256':params['plan_sha256']}
        binding.validate_row = lambda row: {'task_id':'project-1'}
        binding._gate = lambda _:True
        with patch.dict(sys.modules, {'owner_subagent_dispatcher':dispatcher}):
            result = binding.handle(task)
        self.assertEqual(result, ('wait','WAIT_RESOURCE_RECOVERY_STABILITY'))

    def test_pause_latch_is_restored_after_dispatcher_restart(self):
        dispatcher = load_dispatcher()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native_subagent_resource_latch.json'
            value = {'schema':dispatcher.RESOURCE_PRESSURE_LATCH_SCHEMA,
                'instance_id':60509551, 'state':'PAUSED', 'generation':2,
                'reason':'HOLD_BOUNDED_CPU_HEADROOM', 'source_sha256':'a'*64,
                'policy_sha256':'b'*64, 'owner_request':'request-1',
                'updated_at':100.0, 'healthy_snapshots':0}
            dispatcher.write_resource_pressure_latch(path, value, None)
            native = dispatcher.Native.__new__(dispatcher.Native)
            native.source = 'a'*64
            native.policy = {'sha256':'b'*64}
            native.config = {'owner_request':'request-1'}
            native._resource_pressure_paused = False
            native._resource_pressure_latch_uncertain = False
            native._resource_pressure_release = None
            native._resource_pressure_latch_generation = 0
            native._resource_pressure_latch_state = None
            native._resource_pressure_latch_reason = None
            native._resource_pressure_latch_sha256 = None
            with patch.object(dispatcher,'RESOURCE_PRESSURE_LATCH',path):
                native._load_resource_pressure_latch()
            self.assertTrue(native._resource_pressure_paused)
            self.assertFalse(native._resource_pressure_latch_uncertain)
            self.assertEqual(native._resource_pressure_latch_generation,2)
            self.assertEqual(native._resource_pressure_release['healthy_snapshots'],0)
            self.assertTrue(native._resource_pressure_release['restored_after_restart'])

    def test_corrupt_pause_latch_fails_closed(self):
        dispatcher = load_dispatcher()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native_subagent_resource_latch.json'
            path.write_text('{broken')
            path.chmod(0o600)
            native = dispatcher.Native.__new__(dispatcher.Native)
            native.source = 'a'*64
            native.policy = {'sha256':'b'*64}
            native.config = {'owner_request':'request-1'}
            native._resource_pressure_paused = False
            native._resource_pressure_latch_uncertain = False
            native._resource_pressure_release = None
            with patch.object(dispatcher,'RESOURCE_PRESSURE_LATCH',path):
                native._load_resource_pressure_latch()
            self.assertTrue(native._resource_pressure_paused)
            self.assertTrue(native._resource_pressure_latch_uncertain)
            self.assertEqual(native._resource_pressure_release['state'],
                             'HOLD_RESOURCE_PRESSURE_LATCH_UNKNOWN')

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
        native.lock = threading.RLock()
        native._resource_pressure_paused = True
        native._resource_pressure_latch_uncertain = False
        native._resource_pressure_latch_reason = 'HOLD_BOUNDED_CPU_HEADROOM'
        native._resource_pressure_latch_state = 'PAUSED'
        native._resource_pressure_latch_generation = 1
        native._resource_recovery_samples = 0
        native._resource_recovery_last_at = 0.0
        native._resource_recovery_last_monotonic = 0.0
        native._resource_pressure_release = None
        native._write_resource_pressure_latch = lambda *args: setattr(
            native, '_resource_pressure_latch_state', 'RECOVERED')
        observed = [100.0, 102.0, 105.0, 110.0]
        with (patch.object(dispatcher.time, 'time', side_effect=observed),
              patch.object(dispatcher.time, 'monotonic', side_effect=[1000.0,1001.0,1006.0,1011.0])):
            results = [native._resource_recovery_observation(
                {'observed_at': stamp}, None) for stamp in observed]
        self.assertEqual(results, [False, False, False, True])
        self.assertFalse(native._resource_pressure_paused)
        self.assertEqual(native._resource_pressure_release['state'],
                         'RESOURCE_RECOVERY_STABLE')

    def test_recovery_pressure_or_unknown_resets_stability_counter(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)
        native.lock = threading.RLock()
        native._resource_pressure_paused = True
        native._resource_pressure_latch_uncertain = False
        native._resource_recovery_samples = 2
        native._resource_recovery_last_at = 95.0
        native._resource_recovery_last_monotonic = 100.0
        native._resource_pressure_release = None
        with patch.object(dispatcher.time, 'time', return_value=100.0):
            self.assertFalse(native._resource_recovery_observation(
                {'observed_at': 100.0}, 'HOLD_BOUNDED_CPU_HEADROOM'))
        self.assertEqual(native._resource_recovery_samples, 0)
        self.assertTrue(native._resource_pressure_paused)

    def test_concurrent_close_recovery_observations_do_not_count_as_separated(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)
        native.lock = threading.RLock()
        native._resource_pressure_paused = True
        native._resource_pressure_latch_uncertain = False
        native._resource_pressure_latch_reason = 'HOLD_BOUNDED_CPU_HEADROOM'
        native._resource_pressure_latch_state = 'PAUSED'
        native._resource_recovery_samples = 0
        native._resource_recovery_last_at = 0.0
        native._resource_recovery_last_monotonic = 0.0
        native._resource_pressure_release = None
        native._write_resource_pressure_latch = lambda *args: self.fail(
            'two close observations must not clear the pause')
        barrier = threading.Barrier(3)
        outcomes = []
        def observe(stamp):
            barrier.wait()
            outcomes.append(native._resource_recovery_observation(
                {'observed_at':stamp}, None))
        with (patch.object(dispatcher.time, 'time', side_effect=[1000.0,1000.1]),
              patch.object(dispatcher.time, 'monotonic', side_effect=[2000.0,2000.1])):
            threads = [threading.Thread(target=observe,args=(stamp,))
                       for stamp in (1000.0,1000.1)]
            for thread in threads: thread.start()
            barrier.wait()
            for thread in threads: thread.join()
        self.assertEqual(outcomes, [False,False])
        self.assertEqual(native._resource_recovery_samples,1)
        self.assertTrue(native._resource_pressure_paused)

    def test_graceful_shutdown_hold_is_not_overwritten_by_pause_state(self):
        dispatcher = load_dispatcher()
        native = dispatcher.Native.__new__(dispatcher.Native)
        native.config = {'systemic_relay':{'enabled':True}}
        native.lock = threading.RLock()
        native._resource_pressure_latch_uncertain = False
        native._pool_recovery_uncertain = False
        native._resource_pressure_paused = False
        native._resource_pressure_latch_state = None
        native._resource_pressure_latch_reason = None
        native._resource_recovery_samples = 0
        native._resource_recovery_last_at = 0.0
        native._resource_recovery_last_monotonic = 0.0
        native._resource_pressure_release = None
        native._resource_pressure_latch_generation = 0
        native._resource_pressure_latch_sha256 = None
        native._resource_pressure_release = None
        native._pool_recovery = None
        native.pool = object()
        native.read_resource_snapshot = lambda **_: {'observed_at':100.0}
        def write_latch(state, reason, *_):
            native._resource_pressure_latch_state = state
            native._resource_pressure_latch_reason = reason
            return 'a'*64
        native._write_resource_pressure_latch = write_latch
        def unknown_shutdown(*_):
            native._pool_recovery_uncertain = True
            native._resource_pressure_release = {
                'state':'HOLD_GRACEFUL_POOL_SHUTDOWN_UNKNOWN'}
            return False
        native._retire_idle_pool_for_pressure = unknown_shutdown
        with patch.object(dispatcher,'resource_wait_reason',
                          return_value='HOLD_BOUNDED_CPU_HEADROOM'):
            native.maintain_worker_pool()
        self.assertEqual(native._resource_pressure_release['state'],
                         'HOLD_GRACEFUL_POOL_SHUTDOWN_UNKNOWN')


if __name__ == '__main__':
    unittest.main(verbosity=2)
