#!/usr/bin/env python3
"""Real process contention for the existing bounded native model slot."""
from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
import owner_project_model_client as m
from owner_project_planner import PlannerHold, canonical


MESSAGES = [{'role': 'system', 'content': 'bounds'},
            {'role': 'user', 'content': '{}'}]


def reply(path, payload=None, timeout=15):
    return {'/v1/models': {'data': [{'id': 'pinned'}]},
            '/props': {'default_generation_settings': {'n_ctx': 4096}},
            '/slots': [{'is_processing': False}, {'is_processing': True}],
            '/apply-template': {'prompt': 'measured prompt'},
            '/tokenize': {'tokens': [1, 2, 3]},
            '/v1/chat/completions': {'choices': [{'message': {'content': '{"action":"test"}'},
                                                'finish_reason': 'stop'}]}}[path]


def worker(path, number, events, first_release, active, heartbeats):
    m.MODEL_POLL_SECONDS = .01
    m.MODEL_WAIT_SECONDS = 8
    m.MODEL_TURN_SECONDS = 4
    turn = 0

    def beat():
        with heartbeats.get_lock():
            heartbeats[number] += 1

    def http(endpoint, payload=None, timeout=15):
        if endpoint == '/v1/chat/completions':
            with active.get_lock():
                if active.value:
                    raise AssertionError('overlapping model requests')
                active.value += 1
            events.put(('enter', number, turn, time.monotonic()))
            try:
                if number == 0 and turn == 0:
                    if not first_release.wait(3):
                        raise AssertionError('first holder was not released')
                time.sleep(.04)
            finally:
                with active.get_lock():
                    active.value -= 1
            events.put(('exit', number, turn, time.monotonic()))
        return reply(endpoint, payload, timeout)

    try:
        client = m.LocalModelClient(expected_model_id='pinned', stop_check=lambda: False,
            heartbeat=beat, http=http, lock_path=path)
        for turn in range(3):
            result = client(MESSAGES)
            if result['metadata']['slot_policy'] != 'BOUNDED_FIFO_THREE_NATIVE_WORKERS':
                raise AssertionError('missing scheduling provenance')
        events.put(('done', number))
    except BaseException as exc:
        events.put(('error', number, type(exc).__name__, str(exc)))


def hold_slot(path, events, release):
    client = m.LocalModelClient(expected_model_id='pinned', stop_check=lambda: False,
        http=reply, lock_path=path)
    fd, token, _ = client._slot_lock()
    events.put(m.process_identity(os.getpid()))
    release.wait(8)
    client._release_slot(fd, token)


class FairModelSlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'model.lock'
        self.ctx = multiprocessing.get_context('spawn')

    def client(self, **kwargs):
        defaults = dict(expected_model_id='pinned', stop_check=lambda: False,
                        http=reply, lock_path=self.path)
        defaults.update(kwargs)
        return m.LocalModelClient(**defaults)

    def state(self):
        return json.loads(self.path.read_bytes())

    def wait_for(self, predicate, timeout=4):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if predicate():
                return
            time.sleep(.01)
        self.fail('bounded condition was not reached')

    def cleanup_processes(self, processes):
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(2)

    def test_three_real_processes_yield_before_reacquiring_and_never_overlap(self):
        events, gate = self.ctx.Queue(), self.ctx.Event()
        active = self.ctx.Value('i', 0)
        heartbeats = self.ctx.Array('i', [0, 0, 0])
        processes = [self.ctx.Process(target=worker,
            args=(str(self.path), i, events, gate, active, heartbeats)) for i in range(3)]
        self.addCleanup(self.cleanup_processes, processes)
        processes[0].start()
        first = events.get(timeout=4)
        self.assertEqual(first[:3], ('enter', 0, 0))
        processes[1].start()
        processes[2].start()
        self.wait_for(lambda: len(self.state()['waiters']) == 3)
        gate.set()
        records = [first]
        until = time.monotonic() + 7
        while sum(row[0] == 'done' for row in records) < 3 and time.monotonic() < until:
            try:
                row = events.get(timeout=.5)
                records.append(row)
                self.assertNotEqual(row[0], 'error', row)
            except queue.Empty:
                pass
        for process in processes:
            process.join(1)
            self.assertEqual(process.exitcode, 0)
        enters = [row for row in records if row[0] == 'enter']
        self.assertEqual(len(enters), 9)
        # Both already waiting workers must run before the first holder's
        # immediate next turn; a delay-only workaround can starve one of them.
        self.assertEqual({row[1] for row in enters[:3]}, {0, 1, 2})
        self.assertTrue(all(row[2] == 0 for row in enters[:3]))
        self.assertEqual(sum(row[0] == 'done' for row in records), 3)
        self.assertEqual(active.value, 0)
        self.assertTrue(all(count >= 3 for count in heartbeats))
        self.assertEqual(self.state()['waiters'], [])

    def test_stopped_waiter_cleans_ticket_without_model_call(self):
        # A legacy holder uses only the original flock; metadata registration
        # and cooperative cancellation must still work while it owns the slot.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        beats = []
        http = mock.Mock(side_effect=AssertionError('STOP waiter inferred'))
        client = self.client(stop_check=lambda: len(beats) >= 4,
                             heartbeat=lambda: beats.append(True), http=http)
        with mock.patch.object(m, 'MODEL_POLL_SECONDS', .005):
            with self.assertRaisesRegex(PlannerHold, 'OWNER_STOP_OR_CLAIM_LOST'):
                client(MESSAGES)
        self.assertGreaterEqual(len(beats), 4)
        http.assert_not_called()
        self.assertEqual(self.state()['waiters'], [])

    def test_wait_timeout_is_bounded_and_cleans_ticket(self):
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        http = mock.Mock(side_effect=AssertionError('occupied slot inferred'))
        started = time.monotonic()
        with mock.patch.object(m, 'MODEL_WAIT_SECONDS', .12), mock.patch.object(m, 'MODEL_POLL_SECONDS', .01):
            with self.assertRaisesRegex(PlannerHold, 'MODEL_SLOT_BUSY'):
                self.client(http=http)(MESSAGES)
        self.assertLess(time.monotonic() - started, .6)
        http.assert_not_called()
        self.assertEqual(self.state()['waiters'], [])

    def test_dead_holder_and_reused_pid_ticket_cannot_block_successor(self):
        events, release = self.ctx.Queue(), self.ctx.Event()
        holder = self.ctx.Process(target=hold_slot, args=(str(self.path), events, release))
        self.addCleanup(self.cleanup_processes, [holder])
        holder.start()
        identity = events.get(timeout=4)
        self.assertEqual(identity['pid'], holder.pid)
        self.assertEqual(self.state()['waiters'][0]['pid'], holder.pid)
        holder.terminate()
        holder.join(2)
        state = self.state()
        live = m.process_identity(os.getpid())
        state['waiters'].append({**live, 'start_ticks': live['start_ticks'] + 1,
                                'token': 'f' * 32, 'expires': time.monotonic() + 30})
        self.path.write_bytes(canonical(state).ljust(m.TURN_PAGE_BYTES, b' '))
        result = self.client()(MESSAGES)
        self.assertEqual(result['content'], '{"action":"test"}')
        self.assertEqual(self.state()['waiters'], [])

    def test_replaced_named_lock_fails_closed_without_overwriting_foreign_bytes(self):
        client = self.client()
        fd, token, _ = client._slot_lock()
        self.path.unlink()
        self.path.write_bytes(b'foreign lock bytes')
        with self.assertRaisesRegex(PlannerHold, 'MODEL_LOCK_OWNER_OR_IDENTITY'):
            client._release_slot(fd, token)
        self.assertEqual(self.path.read_bytes(), b'foreign lock bytes')
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_common_turn_budget_caps_http_and_releases_after_overrun(self):
        timeouts = []
        def http(path, payload=None, timeout=15):
            timeouts.append((path, timeout))
            if path == '/v1/chat/completions':
                time.sleep(.09)
            return reply(path, payload, timeout)
        with mock.patch.object(m, 'MODEL_TURN_SECONDS', .06):
            with self.assertRaisesRegex(PlannerHold, 'MODEL_TURN_TIMEOUT'):
                self.client(http=http)(MESSAGES)
        self.assertTrue(all(0 < timeout <= .06 for _, timeout in timeouts))
        self.assertEqual(timeouts[-1][0], '/v1/chat/completions')
        self.assertEqual(self.state()['waiters'], [])
        self.assertEqual(self.client()(MESSAGES)['content'], '{"action":"test"}')

    def test_stop_after_acquisition_prevents_http_and_drops_ticket(self):
        client = self.client()
        original = client._slot_lock
        stopped = []
        def acquire():
            result = original()
            stopped.append(True)
            return result
        client.stop_check = lambda: bool(stopped)
        http = mock.Mock(side_effect=AssertionError('cancelled owner inferred'))
        client.http = http
        with mock.patch.object(client, '_slot_lock', side_effect=acquire):
            with self.assertRaisesRegex(PlannerHold, 'OWNER_STOP_OR_CLAIM_LOST'):
                client(MESSAGES)
        http.assert_not_called()
        self.assertEqual(self.state()['waiters'], [])


if __name__ == '__main__':
    unittest.main()
