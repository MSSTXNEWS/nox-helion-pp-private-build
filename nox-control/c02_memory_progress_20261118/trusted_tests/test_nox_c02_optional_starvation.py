"""C02 must retain execution capacity across successive real chat requests.

Optional host callbacks may finish after a pulse deadline. Their outstanding
work must not consume every existing worker or prevent the next S03 recall.
"""
import json
import threading
import unittest

from nox_runpod.teacher_mesh.v38.synaptic_brain import (
    CORE_NAMES, NativePorts, PulseConfig, Session, SynapticBrain,
)


SESSION = Session(tenant='nox', principal='owner', chat_id='c02-progress')


def memory_record(session=SESSION):
    return {'verified': True, 'tenant': session.tenant, 'principal': session.principal,
            'chat_id': session.chat_id, 'segment': 'M7',
            'source_uri': 's03://owner/progress', 'content': 'Verified previous work'}


class MemoryCapacityTests(unittest.TestCase):
    def brain(self, *, workers=2, recall=None, **callbacks):
        native = dict(authorize=lambda session: True, stop=lambda: False,
                      s03_recall=recall or (lambda *args: [memory_record()]))
        native.update(callbacks)
        result = SynapticBrain(NativePorts(**native), PulseConfig(
            fast_deadline_ms=50, deep_deadline_ms=100, memory_deadline_ms=200,
            max_workers=workers, max_inflight=max(4, workers)))
        self.addCleanup(result.close)
        return result

    def test_next_request_recalls_memory_while_previous_optional_callbacks_remain_blocked(self):
        release = threading.Event()
        optional_started = threading.Event()
        lock = threading.Lock()
        recalls = []
        active = [0]
        peak = [0]

        def optional(*args):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            optional_started.set()
            try:
                if not release.wait(5):
                    raise AssertionError('fixture optional callback was not released')
                return {}
            finally:
                with lock:
                    active[0] -= 1

        def recall(session, prompt, limit):
            # The first memory job overlaps at least one optional callback.
            # Both are released through events, not an assumed scheduling sleep.
            if prompt == 'first':
                if not optional_started.wait(2):
                    raise AssertionError('fixture optional callback never started')
            with lock:
                recalls.append(prompt)
                peak[0] = max(peak[0], active[0] + 1)
            return [memory_record(session)]

        brain = self.brain(recall=recall, sensors=optional, self_receipts=optional,
                           affect=optional, available_skills=optional, queue_status=optional)
        try:
            first = brain.pulse(SESSION, 'first')
            self.assertEqual(first['state'], 'READY_FOR_ONE_NOX_MODEL')
            self.assertTrue(optional_started.is_set())
            self.assertFalse(release.is_set())
            second = brain.pulse(SESSION, 'second')
            self.assertEqual(second['state'], 'READY_FOR_ONE_NOX_MODEL')
            self.assertEqual(recalls, ['first', 'second'])
            self.assertEqual(second['cores']['C02']['hit_count'], 1)
            self.assertIn('s03://owner/progress', second['context_json'])
            self.assertLessEqual(peak[0], brain.cfg.max_workers)
        finally:
            release.set()

    def test_one_worker_remains_reserved_for_memory_instead_of_optional_callbacks(self):
        calls = []
        release = threading.Event()

        def optional(*args):
            calls.append('optional')
            release.wait(5)
            return {}

        brain = self.brain(workers=1, sensors=optional, self_receipts=optional)
        try:
            for prompt in ('first', 'second', 'third'):
                value = brain.pulse(SESSION, prompt)
                self.assertEqual(value['state'], 'READY_FOR_ONE_NOX_MODEL')
                self.assertEqual(value['cores']['C02']['hit_count'], 1)
            self.assertEqual(calls, [])
        finally:
            release.set()

    def test_all_eight_fast_cores_still_run_with_the_existing_eight_worker_budget(self):
        brain = self.brain(workers=8, sensors=lambda _: {}, self_receipts=lambda _: [],
            affect=lambda *_: {}, preferences=lambda _: {},
            available_skills=lambda _: {}, queue_status=lambda _: {})
        value = brain.pulse(SESSION, 'fast request')
        self.assertEqual(value['state'], 'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(set(value['cores']), set(CORE_NAMES))
        self.assertTrue(all(row['state'] == 'OBSERVED' for row in value['cores'].values()))
        self.assertEqual(json.loads(value['context_json'])['C02']['signals']['hit_count'], 1)

    def test_optional_failure_releases_capacity_for_later_requests(self):
        calls = []

        def broken_sensor(*args):
            calls.append('sensor')
            raise OSError('fixture unavailable sensor')

        brain = self.brain(workers=2, sensors=broken_sensor)
        for number in range(12):
            value = brain.pulse(SESSION, 'request ' + str(number))
            self.assertEqual(value['state'], 'READY_FOR_ONE_NOX_MODEL')
            self.assertEqual(value['cores']['C02']['hit_count'], 1)
        self.assertEqual(len(calls), 12)

    def test_memory_failure_still_blocks_generation(self):
        calls = []

        def failed_memory(*args):
            raise OSError('fixture S03 unavailable')

        brain = self.brain(recall=failed_memory)
        events = list(brain.stream(SESSION, 'remember',
            lambda *_: calls.append('model') or iter(['unverified answer'])))
        self.assertEqual(events[-1]['state'], 'HOLD_MEMORY_NOT_READY')
        self.assertEqual(calls, [])

    def test_owner_stop_and_close_do_not_start_any_callback(self):
        calls = []
        brain = self.brain(stop=lambda: True, recall=lambda *_: calls.append('memory') or [],
                           sensors=lambda _: calls.append('sensor') or {})
        self.assertEqual(brain.pulse(SESSION, 'stop')['state'], 'HOLD_OWNER_SCOPE_OR_STOP')
        brain.close()
        self.assertEqual(brain.pulse(SESSION, 'closed')['state'], 'HOLD_OWNER_SCOPE_OR_STOP')
        self.assertEqual(calls, [])

    def test_scope_revocation_during_memory_read_still_prevents_generation(self):
        stopped = [False]
        model_calls = []

        def revoke_then_read(*args):
            stopped[0] = True
            return [memory_record()]

        brain = self.brain(stop=lambda: stopped[0], recall=revoke_then_read)
        events = list(brain.stream(SESSION, 'remember',
            lambda *_: model_calls.append(True) or iter(['unverified answer'])))
        self.assertEqual(events[-1]['state'], 'HOLD_SCOPE_REVOKED')
        self.assertEqual(model_calls, [])

    def test_foreign_memory_remains_excluded(self):
        wrong = memory_record(Session(tenant='other', principal='owner', chat_id='foreign'))
        brain = self.brain(recall=lambda *_: [wrong, memory_record()])
        value = brain.pulse(SESSION, 'remember')
        self.assertEqual(value['state'], 'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(value['cores']['C02']['hit_count'], 1)
        self.assertEqual(value['cores']['C02']['hits'][0]['source'], 's03://owner/progress')


if __name__ == '__main__':
    unittest.main()
