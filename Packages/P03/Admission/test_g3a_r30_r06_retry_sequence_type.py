"""G3-A R30 R06: retry sequence type must be exact Python int.

SOURCE ONLY, offline synthetic queue fixtures. This is not E06 native
verification, queue execution, model installation, or Windows acceptance.

From Packages/P03/Admission:
    python -m unittest -v test_g3a_r30_r06_retry_sequence_type
"""
from decimal import Decimal
import unittest

from p03_modelcenter_gate import retry_gate
from test_p03_modelcenter_gate import retry_fixture


class _IntegerAlias(int):
    pass


class G3ARetrySequenceTypeRegressions(unittest.TestCase):
    @staticmethod
    def _attempt(new_sequence, previous_sequence=None):
        previous, new_job = retry_fixture()
        new_job["eventSequence"] = new_sequence
        if previous_sequence is not None:
            previous["eventSequence"] = previous_sequence
        calls = []

        def trusted_test_verifier(old, current):
            calls.append((old["queueJobId"], current["queueJobId"]))
            return True

        result = retry_gate(
            previous, new_job,
            user_retry_consent=True,
            native_queue_attested=True,
            trusted_queue_verifier=trusted_test_verifier,
        )
        return result, calls

    def _assert_local_sequence_hold(self, value):
        result, calls = self._attempt(value)
        self.assertEqual(result.status, "HOLD")
        self.assertIn("RETRY_SEQUENCE_NOT_RESET", result.reasons)
        self.assertEqual(calls, [], "invalid request must not reach native callback")

    def test_true_is_not_integer_one(self):
        # bool is a subclass of int, and True == 1; reject by exact type.
        self._assert_local_sequence_hold(True)

    def test_float_one_is_not_integer_one(self):
        self._assert_local_sequence_hold(1.0)

    def test_decimal_one_is_not_integer_one(self):
        self._assert_local_sequence_hold(Decimal("1"))

    def test_integer_subclass_one_is_not_integer_one(self):
        self._assert_local_sequence_hold(_IntegerAlias(1))

    def test_text_one_is_not_integer_one(self):
        self._assert_local_sequence_hold("1")

    def test_other_malformed_sequences_do_not_call_native(self):
        for value in (None, False, 0, 2, -1, 2.0, [], {}):
            with self.subTest(value=repr(value)):
                self._assert_local_sequence_hold(value)

    def test_missing_or_invalid_previous_sequence_rejected_before_native(self):
        for value in (True, 0, -1, 1.0, "1"):
            with self.subTest(value=repr(value)):
                result, calls = self._attempt(1, previous_sequence=value)
                self.assertIn("RETRY_SEQUENCE_NOT_RESET", result.reasons)
                self.assertEqual(calls, [])

    def test_real_integer_one_remains_admissible_for_native_verifier(self):
        result, calls = self._attempt(1)
        self.assertEqual(result.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(calls, [("original-p03-job-001", "original-p03-job-002")])

    def test_exact_one_still_requires_real_verifier(self):
        previous, new_job = retry_fixture()
        result = retry_gate(
            previous, new_job,
            user_retry_consent=True,
            native_queue_attested=True,
        )
        self.assertEqual(result.status, "HOLD")
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING", result.reasons)


if __name__ == "__main__":
    unittest.main()
