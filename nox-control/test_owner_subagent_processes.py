"""Regression: one actual PID per NOX subagent; no hard task count."""
import json
import os
import threading
import time
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
                following = batch(3)
                for task in following['tasks']:
                    task['id'] = 'following-'+task['id']
                again = pool.run(following, stop_active=lambda: False,
                                 authorize=lambda: True, lease_current=lambda: True)
                self.assertEqual(again['processes'], out['processes'])
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

    def test_external_model_url_rejected(self):
        from owner_subagent_processes import _model_reply
        with self.assertRaisesRegex(GateError, 'HOLD_NONLOCAL'):
            _model_reply({'task': 'x'}, 'https://example.com/v1/chat/completions', 1)

    def test_stop_interrupts_slow_model_wait_and_closes_owned_children(self):
        started = threading.Event()
        stop = threading.Event()
        class Slow(StubModel):
            def do_POST(self):
                started.set()
                stop.wait(5)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Slow)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request_stop():
            if started.wait(4):
                stop.set()
        trigger = threading.Thread(target=request_stop, daemon=True)
        trigger.start()
        try:
            begin = time.monotonic()
            with Subagents(['infra', 'brain', 'web'],
                           model_url=f'http://127.0.0.1:{server.server_port}/v1/chat/completions', timeout=15) as pool:
                children = list(pool.processes.values())
                with self.assertRaisesRegex(GateError, 'OWNER_GATE_CHANGED'):
                    pool.run(batch(1), stop_active=stop.is_set,
                             authorize=lambda: True, lease_current=lambda: True)
            self.assertLess(time.monotonic()-begin, 4)
            self.assertTrue(all(not child.is_alive() for child in children))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
