"""Regression: one actual PID per NOX subagent; no hard task count."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from owner_subagent_processes import SCHEMA, Subagents, GateError, validate


class StubModel(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path != '/v1/chat/completions' or req['model'] != 'nox':
                self.send_error(400)
                return
            text = req['messages'][1]['content']
            data = json.dumps({'choices': [{'message': {'content': 'CANDIDATE:' + text}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def log_message(self, *_):
        pass


def batch(n):
    roles = ['infra', 'brain', 'web']
    return {'schema': SCHEMA, 'subagents': roles,
            'tasks': [{'id': f'job-{i}', 'subagent': roles[i % 3],
                       'task': f'Проверь {i}',
                       'depends_on': [f'job-{i - 3}'] if i >= 3 else []}
                      for i in range(n)]}


class TestRealSubagentProcesses(unittest.TestCase):
    def test_unbounded_61_tasks_three_unique_real_pids(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), StubModel)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            with Subagents(['infra', 'brain', 'web'], model_url=url, timeout=4) as pool:
                out = pool.run(batch(61), stop_active=lambda: False,
                               authorize=lambda: True, lease_current=lambda: True)
                self.assertEqual(out['task_count'], 61)
                self.assertEqual(len(out['results']), 61)
                self.assertEqual(len(set(out['processes'].values())), 3)
                self.assertTrue(all(pid != os.getpid() for pid in out['processes'].values()))
                self.assertTrue(all(row['state'] == 'CANDIDATE_NOT_APPLIED'
                                    for row in out['results'].values()))
                self.assertFalse(out['live_onehost_deployed'])
        finally:
            server.shutdown()
            server.server_close()

    def test_stop_and_cycle(self):
        b = batch(3)
        b['tasks'][0]['depends_on'] = ['job-2']
        b['tasks'][2]['depends_on'] = ['job-0']
        with self.assertRaisesRegex(GateError, 'HOLD_TASK_CYCLE'):
            validate(b)
        with Subagents(['infra', 'brain', 'web']) as pool:
            with self.assertRaisesRegex(GateError, 'HOLD_OWNER_STOP_OR_LEASE'):
                pool.run(batch(1), stop_active=lambda: True,
                         authorize=lambda: True, lease_current=lambda: True)

    def test_cross_worker_result_must_match_assigned_task_role(self):
        # Real pooled outboxes multiplex messages from independent processes.
        # A valid PID/role must NOT be allowed to attest another role's job ID.
        from types import SimpleNamespace
        from queue import Queue
        candidate = Subagents.__new__(Subagents)  # no new OS process or model
        candidate.roles = ['infra', 'brain', 'web']
        candidate.timeout = 1
        candidate.inboxes = {role: Queue() for role in candidate.roles}
        candidate.outbox = Queue()
        candidate.processes = {
            role: SimpleNamespace(pid=800 + i)
            for i, role in enumerate(candidate.roles)
        }
        # Both job IDs exist and both reported PIDs belong to the pool,
        # but each worker attempts to attribute its event to the other job.
        candidate.outbox.put({'kind': 'RESULT', 'role': 'brain', 'pid': 801,
                              'id': 'job-0', 'state': 'CANDIDATE_NOT_APPLIED'})
        candidate.outbox.put({'kind': 'RESULT', 'role': 'infra', 'pid': 800,
                              'id': 'job-1', 'state': 'CANDIDATE_NOT_APPLIED'})
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_IDENTITY'):
            candidate.run(batch(2), stop_active=lambda: False,
                          authorize=lambda: True, lease_current=lambda: True)

    def test_owner_stop_during_pending_result_is_observed(self):
        # No new native processes: inspect only the existing run's wait loop.
        from types import SimpleNamespace
        from queue import Queue
        candidate = Subagents.__new__(Subagents)
        candidate.roles = ['infra', 'brain', 'web']
        candidate.timeout = 1
        candidate.inboxes = {role: Queue() for role in candidate.roles}
        candidate.outbox = Queue()
        candidate.processes = {
            role: SimpleNamespace(pid=900+i) for i, role in enumerate(candidate.roles)
        }
        observations = [False, False, True]
        def owner_stop():
            return observations.pop(0) if observations else True
        with self.assertRaisesRegex(GateError, 'HOLD_OWNER_GATE_CHANGED'):
            candidate.run(batch(1), stop_active=owner_stop,
                          authorize=lambda: True, lease_current=lambda: True)
        self.assertEqual(observations, [])

    def test_lease_revoked_between_result_read_and_acceptance(self):
        from types import SimpleNamespace
        from queue import Queue
        candidate = Subagents.__new__(Subagents)
        candidate.roles = ['infra', 'brain', 'web']
        candidate.timeout = 1
        candidate.inboxes = {role: Queue() for role in candidate.roles}
        candidate.outbox = Queue()
        candidate.processes = {
            role: SimpleNamespace(pid=900+i) for i, role in enumerate(candidate.roles)
        }
        candidate.outbox.put({'kind':'RESULT', 'role':'infra', 'pid':900,
                              'id':'job-0', 'state':'CANDIDATE_NOT_APPLIED'})
        leases = [True, True, False]
        def lease():
            return leases.pop(0) if leases else False
        with self.assertRaisesRegex(GateError, 'HOLD_OWNER_GATE_CHANGED'):
            candidate.run(batch(1), stop_active=lambda: False,
                          authorize=lambda: True, lease_current=lease)
        self.assertEqual(leases, [])

    def test_inflight_deadline_cannot_be_extended_by_other_worker_results(self):
        # Pure in-memory regression: a fast result cannot mask a stale job.
        from types import SimpleNamespace
        from queue import Queue
        from unittest.mock import patch
        import owner_subagent_processes as module

        class Clock:
            t = 0.0
            def monotonic(self):
                return self.t

        clock = Clock()

        class ScriptedOutbox:
            calls = 0
            def get(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    clock.t = 5.0
                    return {'kind': 'RESULT', 'role': 'infra', 'pid': 810,
                            'id': 'job-0', 'state': 'CANDIDATE_NOT_APPLIED',
                            'elapsed_ms': 5000, 'answer': 'candidate'}
                clock.t = 8.0
                return {'kind': 'RESULT', 'role': 'brain', 'pid': 811,
                        'id': 'job-1', 'state': 'CANDIDATE_NOT_APPLIED',
                        'elapsed_ms': 8000, 'answer': 'candidate'}

        candidate = Subagents.__new__(Subagents)
        candidate.roles = ['infra', 'brain', 'web']
        candidate.timeout = 1
        candidate.inboxes = {role: Queue() for role in candidate.roles}
        candidate.outbox = ScriptedOutbox()
        candidate.processes = {role: SimpleNamespace(pid=810+i)
                               for i, role in enumerate(candidate.roles)}
        with patch.object(module.time, 'monotonic', clock.monotonic):
            with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_TIMEOUT'):
                candidate.run(batch(2), stop_active=lambda: False,
                              authorize=lambda: True, lease_current=lambda: True)

    def test_worker_result_cannot_forge_live_or_done(self):
        # IPC is not a production receipt. These are pure in-memory tests,
        # with no native OneHost worker or second model invocation.
        from types import SimpleNamespace
        from queue import Queue

        base = {'kind': 'RESULT', 'role': 'infra', 'pid': 920,
                'id': 'job-0', 'elapsed_ms': 1,
                'state': 'CANDIDATE_NOT_APPLIED', 'answer': 'candidate'}
        forged = [
            {**base, 'state': 'LIVE_VERIFIED'},
            {**base, 'state': 'DONE'},
            {k: v for k, v in base.items() if k != 'answer'},
            {**base, 'live_onehost_deployed': True},
            {**base, 'elapsed_ms': -1},
            {**base, 'state': 'HOLD_MODEL_UNAVAILABLE'},
        ]
        for event in [base, *forged]:
            with self.subTest(event=event):
                pool = Subagents.__new__(Subagents)
                pool.roles = ['infra', 'brain', 'web']
                pool.timeout = 1
                pool.inboxes = {role: Queue() for role in pool.roles}
                pool.outbox = Queue()
                pool.processes = {role: SimpleNamespace(pid=920 + i)
                                  for i, role in enumerate(pool.roles)}
                pool.outbox.put(event)
                if event is base:
                    result = pool.run(batch(1), stop_active=lambda: False,
                                      authorize=lambda: True,
                                      lease_current=lambda: True)
                    self.assertEqual(result['results']['job-0']['state'],
                                     'CANDIDATE_NOT_APPLIED')
                    self.assertFalse(result['live_onehost_deployed'])
                else:
                    with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_SCHEMA'):
                        pool.run(batch(1), stop_active=lambda: False,
                                 authorize=lambda: True,
                                 lease_current=lambda: True)

    def test_failed_long_batch_cannot_replay_stale_result_on_same_pool(self):
        # A revoked owner STOP can leave an old worker RESULT in the outbox.
        # Even a matching PID + role + TaskID must never be reused for a new
        # request. Pure in-memory check; no new NOX model/process is launched.
        from types import SimpleNamespace
        from queue import Queue
        pool = Subagents.__new__(Subagents)
        pool.roles = ['infra', 'brain', 'web']
        pool.timeout = 1
        pool.inboxes = {role: Queue() for role in pool.roles}
        pool.outbox = Queue()
        pool.processes = {role: SimpleNamespace(pid=930 + i)
                          for i, role in enumerate(pool.roles)}
        observed = iter([False, False, True])
        with self.assertRaisesRegex(GateError, 'HOLD_OWNER_GATE_CHANGED'):
            pool.run(batch(1), stop_active=lambda: next(observed, True),
                     authorize=lambda: True, lease_current=lambda: True)
        self.assertTrue(pool._batch_used)
        self.assertEqual(pool.inboxes['infra'].qsize(), 1)
        # This stale worker result would otherwise look valid on the next
        # run if TaskID, role and PID were reused in the same pool.
        pool.outbox.put({'kind': 'RESULT', 'role': 'infra', 'pid': 930,
                         'id': 'job-0', 'elapsed_ms': 1,
                         'state': 'CANDIDATE_NOT_APPLIED', 'answer': 'STALE'})
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_POOL_REUSE'):
            pool.run(batch(1), stop_active=lambda: False,
                     authorize=lambda: True, lease_current=lambda: True)
        self.assertEqual(pool.inboxes['infra'].qsize(), 1)
        self.assertEqual(pool.outbox.qsize(), 1)

    def test_external_model_url_rejected(self):
        from owner_subagent_processes import _model_reply
        with self.assertRaisesRegex(GateError, 'HOLD_NONLOCAL'):
            _model_reply({'task': 'x'}, 'https://example.com/v1/chat/completions', 1)

    def test_dispatcher_submit_poll_is_task_bound_and_never_replays(self):
        # Exercise only the new persistent ABI with in-memory IPC; no model or
        # child process is started by this focused contract check.
        from collections import deque
        from queue import Queue
        from types import SimpleNamespace
        import time

        def worker_input(item):
            raise AssertionError('worker_prepare belongs in the child')
        worker_input.__module__ = 'owner_subagent_dispatcher'
        claim = 'a' * 24
        policy_sha = 'b' * 64
        pid = 940
        process = SimpleNamespace(pid=pid, alive=True)
        process.is_alive = lambda: process.alive
        pool = Subagents.__new__(Subagents)
        pool.roles = ['runtime']
        pool.timeout = 1
        pool.worker_prepare = worker_input
        pool._persistent = True
        pool._abi_lock = threading.RLock()
        pool.active = {}
        pool.heartbeats = {}
        pool._active_started = {}
        pool._active_context = {}
        pool._submitted_ids = set()
        pool._terminal_ids = set()
        pool._pending_events = deque()
        pool.inboxes = {'runtime': Queue()}
        pool.outbox = Queue()
        pool.processes = {'runtime': process}
        task = {'id': 'native-1', 'subagent': 'runtime', 'task': 'review',
                'depends_on': [],
                '_native_context': {'policy': {'path': '/owner/policy.md',
                                               'sha256': policy_sha},
                                    'operation': 'runtime', 'claim': claim}}
        self.assertTrue(pool.submit(task))
        self.assertEqual(pool.active, {'runtime': 'native-1'})
        self.assertEqual(pool.inboxes['runtime'].get_nowait()['id'], 'native-1')
        pool.outbox.put({'kind': 'HEARTBEAT', 'role': 'runtime', 'pid': pid,
                         'at': time.time()})
        observation = {'claim': claim,
                       'policy_ack': {'sha256': policy_sha, 'full_file_read': True},
                       'worker': {'pid': pid}}
        pool.outbox.put({'kind': 'RESULT', 'role': 'runtime', 'pid': pid,
                         'id': 'native-1', 'elapsed_ms': 4,
                         'state': 'CANDIDATE_NOT_APPLIED', 'answer': 'candidate',
                         'native_observation': observation})
        event = pool.poll(timeout=0)
        self.assertEqual(event['id'], 'native-1')
        self.assertEqual(event['native_observation'], observation)
        self.assertEqual(pool.active, {})
        self.assertGreater(pool.heartbeats['runtime'], 0)
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_TASK_REUSE'):
            pool.submit(task)

        task2 = {**task, 'id': 'native-2'}
        self.assertTrue(pool.submit(task2))
        self.assertEqual(pool.active, {'runtime': 'native-2'})
        process.alive = False
        failed = pool.poll(timeout=0)
        self.assertEqual((failed['id'], failed['state']),
                         ('native-2', 'HOLD_SUBAGENT_PROCESS_EXIT'))
        self.assertEqual(pool.active, {})
        self.assertIsNone(pool.poll(timeout=0))
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_TASK_REUSE'):
            pool.submit(task2)


    def test_isolated_replacement_preserves_healthy_pids_and_fenced_task(self):
        from collections import deque
        from queue import Queue
        import time

        class Channel(Queue):
            def __init__(self):
                super().__init__()
                self.closed = False
            def close(self):
                self.closed = True

        class Child:
            def __init__(self, pid, alive=True, role=None, outbox=None):
                self.pid, self.alive = pid, alive
                self.role, self.outbox = role, outbox
                self.joins = self.terminations = 0
            def is_alive(self):
                return self.alive
            def join(self, timeout=None):
                self.joins += 1
            def terminate(self):
                self.terminations += 1
                self.alive = False
            def start(self):
                self.alive = True
                self.outbox.put({'kind': 'READY', 'role': self.role,
                                 'pid': self.pid, 'heartbeat_at': time.time()})

        class Context:
            def __init__(self):
                self.spawned = []
            def Queue(self):
                return Channel()
            def Process(self, *, target, args, name):
                self.spawned.append((args[0], target, name))
                self.last = Child(9913 + len(self.spawned), False, args[0], args[2])
                return self.last

        ctx = Context()
        pool = Subagents.__new__(Subagents)
        pool.roles = ['runtime', 'memory', 'weights']
        pool.ctx = ctx
        pool.url = 'http://127.0.0.1:8081/v1/chat/completions'
        pool.timeout = 1
        pool.worker_prepare = None
        pool._abi_lock = threading.RLock()
        pool._persistent = True
        pool._shutdown_complete = False
        pool._submitted_ids = {'native-old'}
        pool._terminal_ids = set()
        pool._pending_events = deque()
        pool.active = {'memory': 'native-old'}
        pool._active_started = {'memory': time.monotonic()}
        pool._active_context = {'memory': {'claim': 'a'*24}}
        pool.heartbeats = {}
        pool.inboxes = {r: Channel() for r in pool.roles}
        pool.outbox = Channel()
        live_runtime, lost, live_weights = Child(9911), Child(9912, False), Child(9913)
        pool.processes = {'runtime': live_runtime, 'memory': lost,
                          'weights': live_weights}
        old_memory_inbox = pool.inboxes['memory']
        live_runtime_inbox, live_weights_inbox = pool.inboxes['runtime'], pool.inboxes['weights']

        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_POOL_NOT_READY'):
            pool._replace_idle_dead_pool()
        event = pool._pending_events.popleft()
        self.assertEqual((event['id'], event['state']),
                         ('native-old', 'HOLD_SUBAGENT_PROCESS_EXIT'))
        self.assertIn('native-old', pool._terminal_ids)
        self.assertEqual(ctx.spawned, [])  # The owner must read the HOLD first.

        pool._replace_idle_dead_pool()
        self.assertEqual([role for role, _, _ in ctx.spawned], ['memory'])
        self.assertEqual(pool.processes['memory'].pid, 9914)
        self.assertIs(pool.processes['runtime'], live_runtime)
        self.assertIs(pool.processes['weights'], live_weights)
        self.assertIs(pool.inboxes['runtime'], live_runtime_inbox)
        self.assertIs(pool.inboxes['weights'], live_weights_inbox)
        self.assertEqual((live_runtime.joins, live_weights.joins), (0, 0))
        self.assertEqual((live_runtime.terminations, live_weights.terminations), (0, 0))
        self.assertTrue(old_memory_inbox.closed)
        self.assertFalse(live_runtime_inbox.closed or live_weights_inbox.closed)
        self.assertFalse(pool.outbox.closed)
        self.assertEqual(pool.active, {})
        self.assertIn('native-old', pool._submitted_ids)

        # Admission may flip after the replacement sends READY. Never publish
        # that child as the active process; two existing healthy peers survive.
        just_replaced = pool.processes['memory']
        just_replaced.alive = False
        admission_checks = []
        def allow_until_ready():
            admission_checks.append(True)
            return len(admission_checks) < 4
        with self.assertRaisesRegex(GateError, 'HOLD_OWNER_STOP_OR_CHAT_PRIORITY'):
            pool._replace_idle_dead_pool(allow_replacement=allow_until_ready)
        self.assertEqual(len(admission_checks), 4)
        self.assertIs(pool.processes['memory'], just_replaced)
        self.assertIs(pool.processes['runtime'], live_runtime)
        self.assertIs(pool.processes['weights'], live_weights)
        self.assertFalse(ctx.last.is_alive())
        self.assertEqual(ctx.last.terminations, 1)
        self.assertEqual((live_runtime.terminations, live_weights.terminations), (0, 0))

    def test_shutdown_and_drain_keeps_joined_result_and_holds_missing_result(self):
        from collections import deque
        from queue import Queue
        import time
        from owner_subagent_processes import Subagents

        claim = 'a' * 24
        policy_sha = 'b' * 64

        class Channel(Queue):
            def __init__(self):
                super().__init__()
                self.closed = False
            def close(self):
                self.closed = True

        class Child:
            def __init__(self, pid, outbox, event=None):
                self.pid = pid
                self.outbox = outbox
                self.event = event
                self.alive = True
                self.exitcode = None
                self.joined = False
            def is_alive(self):
                return self.alive
            def join(self, timeout=None):
                self.joined = True
                if self.outbox.closed:
                    raise AssertionError('outbox closed before worker join')
                if self.event is not None:
                    self.outbox.put(self.event)
                self.alive = False
                self.exitcode = 0
            def terminate(self):
                self.alive = False
                self.exitcode = -15
            def kill(self):
                self.alive = False
                self.exitcode = -9

        def make_pool(with_result):
            inbox, outbox = Channel(), Channel()
            observation = {'claim': claim,
                           'policy_ack': {'sha256': policy_sha, 'full_file_read': True},
                           'worker': {'pid': 940}}
            event = ({'kind': 'RESULT', 'role': 'runtime', 'pid': 940,
                      'id': 'native-1', 'elapsed_ms': 4,
                      'state': 'CANDIDATE_NOT_APPLIED', 'answer': 'candidate',
                      'native_observation': observation} if with_result else None)
            child = Child(940, outbox, event)
            pool = Subagents.__new__(Subagents)
            pool._persistent = True
            pool.roles = ['runtime']
            pool.timeout = 1
            pool._abi_lock = threading.RLock()
            pool.active = {'runtime': 'native-1'}
            pool.heartbeats = {}
            pool._active_started = {'runtime': time.monotonic()}
            pool._active_context = {'runtime': {'claim': claim,
                'policy': {'sha256': policy_sha}}}
            pool._submitted_ids = {'native-1'}
            pool._terminal_ids = set()
            pool._pending_events = deque()
            pool._pending_checkpoint_events = deque()
            pool.inboxes = {'runtime': inbox}
            pool.outbox = outbox
            pool.processes = {'runtime': child}
            pool._shutdown_complete = False
            return pool, child, inbox, outbox

        task = {'id': 'native-1', 'subagent': 'runtime', 'task': 'review',
                'depends_on': [],
                '_native_context': {'policy': {'path': '/owner/policy.md',
                                               'sha256': policy_sha},
                                    'operation': 'runtime', 'claim': claim}}
        pool, child, inbox, outbox = make_pool(True)
        outbox.put(child.event)
        child.event = None
        poll_callbacks = []
        poll_returned = False
        def poll_checkpoint(event):
            self.assertFalse(poll_returned)
            self.assertFalse(inbox.closed)
            self.assertFalse(outbox.closed)
            poll_callbacks.append(event['id'])
        polled = pool.poll(timeout=0, on_validated_result=poll_checkpoint)
        poll_returned = True
        self.assertEqual(poll_callbacks, ['native-1'])
        self.assertEqual(polled['id'], 'native-1')
        pool.shutdown_and_drain()

        pool, child, inbox, outbox = make_pool(True)
        outbox.put(child.event)
        child.event = None
        def fail_poll_checkpoint(_event):
            raise OSError('checkpoint unavailable')
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_CHECKPOINT'):
            pool.poll(timeout=0, on_validated_result=fail_poll_checkpoint)
        self.assertFalse(inbox.closed)
        self.assertFalse(outbox.closed)
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_CHECKPOINT_REQUIRED'):
            pool.poll(timeout=0)
        retried_poll = []
        polled = pool.poll(timeout=0,
            on_validated_result=lambda event: retried_poll.append(event['id']))
        self.assertEqual(retried_poll, ['native-1'])
        self.assertEqual(polled['id'], 'native-1')
        pool.shutdown_and_drain()

        pool, child, inbox, outbox = make_pool(True)
        callback_events = []
        def checkpoint(event):
            self.assertTrue(child.joined)
            self.assertFalse(inbox.closed)
            self.assertFalse(outbox.closed)
            callback_events.append(event['id'])
        events = pool.shutdown_and_drain(on_validated_result=checkpoint)
        self.assertEqual(callback_events, ['native-1'])
        self.assertTrue(child.joined)
        self.assertEqual(inbox.get_nowait(), None)
        self.assertEqual([row['id'] for row in events], ['native-1'])
        self.assertEqual(events[0]['state'], 'CANDIDATE_NOT_APPLIED')
        self.assertTrue(inbox.closed)
        self.assertTrue(outbox.closed)
        self.assertIn('native-1', pool._terminal_ids)
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_TASK_REUSE'):
            pool.submit(task)

        pool, child, inbox, outbox = make_pool(True)
        def fail_checkpoint(_event):
            raise OSError('checkpoint unavailable')
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_CHECKPOINT'):
            pool.shutdown_and_drain(on_validated_result=fail_checkpoint)
        self.assertFalse(inbox.closed)
        self.assertFalse(outbox.closed)
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_RESULT_CHECKPOINT_REQUIRED'):
            pool.__exit__(None, None, None)
        self.assertFalse(inbox.closed)
        self.assertFalse(outbox.closed)
        retried = []
        recovered = pool.shutdown_and_drain(
            on_validated_result=lambda event: retried.append(event['id']))
        self.assertEqual(retried, ['native-1'])
        self.assertEqual([row['id'] for row in recovered], ['native-1'])
        self.assertTrue(inbox.closed)
        self.assertTrue(outbox.closed)

        pool, child, inbox, outbox = make_pool(False)
        events = pool.shutdown_and_drain()
        self.assertEqual([(row['id'], row['state']) for row in events],
                         [('native-1', 'HOLD_SUBAGENT_PROCESS_EXIT')])
        self.assertTrue(inbox.closed)
        self.assertTrue(outbox.closed)
        with self.assertRaisesRegex(GateError, 'HOLD_SUBAGENT_TASK_REUSE'):
            pool.submit(task)


if __name__ == '__main__':
    unittest.main(verbosity=2)

