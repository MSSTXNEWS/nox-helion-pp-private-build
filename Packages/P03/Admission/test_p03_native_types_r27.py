"""Native queue and GPU evidence cannot use Python truth/numeric aliases."""
import unittest
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import example, queue_fixture, retry_fixture


class NativeTypesR27(unittest.TestCase):
    def test_unhashable_previous_queue_states_hold(self):
        for state in ([], {}, ['RUNNING']):
            old, new = queue_fixture(); old['state'] = state
            with self.subTest(state=state):
                result = g.progress_gate(old, new, lambda *a: True)
                self.assertFalse(result.allowed)
                self.assertIn('UNKNOWN_PREVIOUS_QUEUE_STATE', result.reasons)

    def test_unhashable_previous_unknown_counter_state_holds(self):
        old, new = queue_fixture()
        old.update(state=[], totalBytes=None, completedBytes=None)
        self.assertFalse(g.progress_gate(old, new, lambda *a: True).allowed)

    def test_retry_sequence_requires_actual_integer_one(self):
        for sequence in (True, 1.0):
            old, new = retry_fixture(); new['eventSequence'] = sequence
            with self.subTest(sequence=sequence):
                result = g.retry_gate(old, new, user_retry_consent=True,
                    native_queue_attested=True, trusted_queue_verifier=lambda *a: True)
                self.assertFalse(result.allowed)
                self.assertIn('RETRY_SEQUENCE_NOT_RESET', result.reasons)

    def test_gpu_requirement_must_be_explicit_boolean(self):
        for flag in (None, 1, 0, 'true', 'false', []):
            e, c = example(); e['requiresGPU'] = flag
            c['nativeMeasuredHardware']['vramBytes'] = 1
            with self.subTest(flag=flag):
                self.assertFalse(g.admit_for_existing_downloader(e, c, lambda *a: True).allowed)

    def test_cpu_only_and_normal_retry_still_work(self):
        e, c = example(); e['requiresGPU'] = False
        c['nativeMeasuredHardware']['vramBytes'] = None
        self.assertTrue(g.admit_for_existing_downloader(e, c, lambda *a: True).allowed)
        old, new = retry_fixture()
        self.assertTrue(g.retry_gate(old, new, user_retry_consent=True,
            native_queue_attested=True, trusted_queue_verifier=lambda *a: True).allowed)


if __name__ == '__main__': unittest.main()
