"""G3-A R30 R05: SOURCE-ONLY queue verifier reentrancy boundaries.

Offline Python tests; synthetic callbacks are NOT native owner receipts.
Run from Packages/P03/Admission:
  python -m unittest -v test_g3a_r30_r05_queue_verifier_boundary
Do not run installers, model pulls or external services.
"""
import unittest

from p03_modelcenter_gate import progress_gate, retry_gate
from test_p03_modelcenter_gate import queue_fixture, retry_fixture


class G3AQueueVerifierBoundary(unittest.TestCase):
    def test_progress_valid_pair_calls_verifier_once(self):
        previous, update = queue_fixture()
        seen = []
        def verifier(a, b):
            seen.append((a["queueJobId"], b["completedBytes"]))
            return True
        self.assertEqual(progress_gate(previous, update, verifier).status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(seen, [("original-p03-job-001", 80)])

    def test_retry_valid_pair_calls_verifier_once(self):
        previous, update = retry_fixture()
        seen = []
        def verifier(a, b):
            seen.append((a["attemptId"], b["attemptId"]))
            return True
        answer = retry_gate(previous, update, user_retry_consent=True,
                            native_queue_attested=True, trusted_queue_verifier=verifier)
        self.assertEqual(answer.status, "PASS_FOR_EXISTING_QUEUE")
        self.assertEqual(seen, [("attempt-001", "attempt-002")])

    def test_progress_identity_mismatch_never_calls_native(self):
        previous, update = queue_fixture()
        update["queueJobId"] = "different-job"
        calls = []
        answer = progress_gate(previous, update, lambda a, b: calls.append(1) or True)
        self.assertEqual(answer.status, "HOLD")
        self.assertIn("QUEUE_JOB_ID_DRIFT_OR_MISSING", answer.reasons)
        self.assertEqual(calls, [])

    def test_progress_invalid_terminal_transition_never_calls_native(self):
        previous, update = queue_fixture()
        previous["state"] = "FAILED"
        calls = []
        answer = progress_gate(previous, update, lambda a, b: calls.append(1) or True)
        self.assertIn("INVALID_OR_TERMINAL_QUEUE_TRANSITION", answer.reasons)
        self.assertEqual(calls, [])

    def test_progress_mutation_after_native_check_is_hold(self):
        previous, update = queue_fixture()
        def mutating_verifier(a, b):
            b["completedBytes"] = 99
            return True
        answer = progress_gate(previous, update, mutating_verifier)
        self.assertEqual(answer.status, "HOLD")
        self.assertIn("NATIVE_QUEUE_VERIFIER_EVIDENCE_CHANGED", answer.reasons)

    def test_progress_added_nested_evidence_after_check_is_hold(self):
        previous, update = queue_fixture()
        def mutating_verifier(a, b):
            b["nativeReceiptEvidence"] = {"artifact": {"bytes": 8}}
            return True
        answer = progress_gate(previous, update, mutating_verifier)
        self.assertIn("NATIVE_QUEUE_VERIFIER_EVIDENCE_CHANGED", answer.reasons)

    def test_progress_invalid_unserializable_extra_evidence_is_hold(self):
        previous, update = queue_fixture()
        update["nativeReceiptEvidence"] = object()
        calls = []
        answer = progress_gate(previous, update, lambda a, b: calls.append(1) or True)
        self.assertIn("NATIVE_QUEUE_EVIDENCE_INVALID", answer.reasons)
        self.assertEqual(calls, [])

    def test_retry_lacking_consent_never_calls_native(self):
        previous, update = retry_fixture()
        calls = []
        answer = retry_gate(previous, update, user_retry_consent=False,
                            native_queue_attested=True,
                            trusted_queue_verifier=lambda a, b: calls.append(1) or True)
        self.assertIn("RETRY_USER_CONSENT_REQUIRED", answer.reasons)
        self.assertEqual(calls, [])

    def test_retry_same_attempt_never_calls_native(self):
        previous, update = retry_fixture()
        update["attemptId"] = previous["attemptId"]
        calls = []
        answer = retry_gate(previous, update, user_retry_consent=True,
                            native_queue_attested=True,
                            trusted_queue_verifier=lambda a, b: calls.append(1) or True)
        self.assertIn("RETRY_ATTEMPT_NOT_UNIQUE", answer.reasons)
        self.assertEqual(calls, [])

    def test_retry_verifier_mutating_host_session_is_hold(self):
        previous, update = retry_fixture()
        def mutating_verifier(a, b):
            b["queueOwnerSessionId"] = "forged-session"
            return True
        answer = retry_gate(previous, update, user_retry_consent=True,
                            native_queue_attested=True,
                            trusted_queue_verifier=mutating_verifier)
        self.assertIn("NATIVE_QUEUE_VERIFIER_EVIDENCE_CHANGED", answer.reasons)

    def test_retry_mutating_new_job_receipt_is_hold(self):
        previous, update = retry_fixture()
        def mutating_verifier(a, b):
            b["queueJobReceiptSha256"] = "f" * 64
            return True
        answer = retry_gate(previous, update, user_retry_consent=True,
                            native_queue_attested=True,
                            trusted_queue_verifier=mutating_verifier)
        self.assertIn("NATIVE_QUEUE_VERIFIER_EVIDENCE_CHANGED", answer.reasons)

    def test_progress_verifier_denial_is_hold(self):
        previous, update = queue_fixture()
        answer = progress_gate(previous, update, lambda a, b: False)
        self.assertIn("NATIVE_QUEUE_RECEIPT_REJECTED", answer.reasons)

    def test_retry_verifier_missing_is_hold(self):
        previous, update = retry_fixture()
        answer = retry_gate(previous, update, user_retry_consent=True,
                            native_queue_attested=True)
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING", answer.reasons)


if __name__ == "__main__":
    unittest.main()
