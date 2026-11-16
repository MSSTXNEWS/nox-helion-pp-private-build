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
                            'id': 'job-0', 'state': 'CANDIDATE_NOT_APPLIED'}
                clock.t = 8.0
                return {'kind': 'RESULT', 'role': 'brain', 'pid': 811,
                        'id': 'job-1', 'state': 'CANDIDATE_NOT_APPLIED'}

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

    def test_external_model_url_rejected(self):
        from owner_subagent_processes import _model_reply
        with self.assertRaisesRegex(GateError, 'HOLD_NONLOCAL'):
            _model_reply({'task': 'x'}, 'https://example.com/v1/chat/completions', 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
