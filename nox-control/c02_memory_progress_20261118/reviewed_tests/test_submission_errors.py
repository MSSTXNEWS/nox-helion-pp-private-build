"""Independent reviewed-reserve regressions; immutable native tests stay intact."""
from concurrent.futures import Future
import unittest
from unittest import mock

from nox_runpod.teacher_mesh.v38.synaptic_brain import (
    NativePorts, PulseConfig, Session, SynapticBrain,
)


class SubmissionCredits(unittest.TestCase):
    def brain(self):
        session = Session(tenant='nox', principal='owner', chat_id='submit-errors')
        def recall(s, prompt, limit):
            return [{'verified': True, 'tenant': s.tenant, 'principal': s.principal,
                     'chat_id': s.chat_id, 'segment': 'M7',
                     'source_uri': 's03://owner/submit-errors', 'content': 'verified'}]
        brain = SynapticBrain(NativePorts(authorize=lambda _: True,
            stop=lambda: False, s03_recall=recall), PulseConfig(
                max_workers=2, max_inflight=2))
        self.addCleanup(brain.close)
        return brain, session

    def assert_all_credits_available(self, brain):
        for semaphore, expected in ((brain.inflight, 2),
                                    (brain.optional_inflight, 1)):
            taken = 0
            try:
                for _ in range(expected):
                    self.assertTrue(semaphore.acquire(blocking=False))
                    taken += 1
                self.assertFalse(semaphore.acquire(blocking=False))
            finally:
                for _ in range(taken):
                    semaphore.release()

    @staticmethod
    def synchronous_submit(fn, *args):
        result = Future()
        result.set_result(fn(*args))
        return result

    def test_unexpected_memory_submission_failure_returns_credit_and_propagates(self):
        for exception_type in (ValueError, MemoryError, KeyboardInterrupt):
            with self.subTest(exception_type=exception_type.__name__):
                brain, session = self.brain()
                original = exception_type('synthetic submission failure')
                with mock.patch.object(brain.pool, 'submit', side_effect=original):
                    with self.assertRaises(exception_type) as seen:
                        brain.pulse(session, 'memory submission')
                self.assertIs(seen.exception, original)
                self.assert_all_credits_available(brain)
                self.assertEqual(brain.pulse(session, 'next request')['state'],
                                 'READY_FOR_ONE_NOX_MODEL')

    def test_unexpected_optional_submission_failure_returns_both_credits(self):
        for exception_type in (ValueError, MemoryError, KeyboardInterrupt):
            with self.subTest(exception_type=exception_type.__name__):
                brain, session = self.brain()
                original = exception_type('synthetic optional submission failure')
                def submit(fn, name, *args):
                    if name == 'C01':
                        raise original
                    return self.synchronous_submit(fn, name, *args)
                with mock.patch.object(brain.pool, 'submit', side_effect=submit):
                    with self.assertRaises(exception_type) as seen:
                        brain.pulse(session, 'optional submission')
                self.assertIs(seen.exception, original)
                self.assert_all_credits_available(brain)
                self.assertEqual(brain.pulse(session, 'next request')['state'],
                                 'READY_FOR_ONE_NOX_MODEL')

    def test_expected_runtime_error_keeps_explicit_unavailable_behavior(self):
        brain, session = self.brain()
        def submit(fn, name, *args):
            if name != 'C02':
                raise RuntimeError('synthetic pool shutdown')
            return self.synchronous_submit(fn, name, *args)
        with mock.patch.object(brain.pool, 'submit', side_effect=submit):
            value = brain.pulse(session, 'pool shutdown')
        self.assertEqual(value['state'], 'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(value['cores']['C01']['state'], 'HOLD_QUEUE_SATURATED')
        self.assert_all_credits_available(brain)


if __name__ == '__main__':
    unittest.main()
