"""Original worker may persist Running->Cancelled for external token STOP.
Execute policy fixtures only; no C# worker, native receipt or network execution.
"""
import unittest
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import queue_fixture


class DirectNativeCancellation(unittest.TestCase):
    def pair(self, done=60, total=100):
        old, new = queue_fixture()
        old.update(state="RUNNING", completedBytes=done, totalBytes=total)
        new.update(state="CANCELLED", completedBytes=done, totalBytes=total,
                   nativeCancelAttested=True, cancelAckReceiptSha256="f" * 64)
        return old, new

    def test_original_worker_direct_cancel_with_native_ack(self):
        for done, total in [(60, 100), (None, None), (10, None)]:
            with self.subTest(done=done, total=total):
                old, new = self.pair(done, total)
                decision = g.progress_gate(old, new, lambda a, b: True)
                self.assertTrue(decision.allowed, decision.reasons)

    def test_direct_cancel_without_exact_native_ack_still_holds(self):
        for fields in ({"nativeCancelAttested": False}, {"nativeCancelAttested": 1},
                       {"cancelAckReceiptSha256": None}, {"cancelAckReceiptSha256": "0" * 64}):
            old, new = self.pair(); new.update(fields)
            decision = g.progress_gate(old, new, lambda a, b: True)
            self.assertFalse(decision.allowed)
            self.assertIn("CANCELLATION_ACK_NOT_ATTESTED", decision.reasons)

    def test_no_native_verifier_or_rejected_receipt_never_allows_cancel(self):
        old, new = self.pair()
        for verifier in (None, lambda a, b: False, lambda a, b: 1):
            self.assertFalse(g.progress_gate(old, new, verifier).allowed)

    def test_direct_cancel_preserves_job_identity_sequence_and_counters(self):
        for changes in ({"queueJobId": "foreign-job"}, {"queueOwnerSessionId": "foreign-session"},
                        {"manifestSha256": "e" * 64}, {"eventSequence": 10},
                        {"completedBytes": 10}, {"totalBytes": None}, {"completedBytes": 101}):
            old, new = self.pair(); new.update(changes)
            self.assertFalse(g.progress_gate(old, new, lambda a, b: True).allowed, changes)

    def test_stop_intent_is_not_native_cancel_confirmation(self):
        for state in ("STOP", "CANCEL_REQUESTED", "CANCELLING"):
            old, new = self.pair(); new["state"] = state
            decision = g.progress_gate(old, new, lambda a, b: True)
            self.assertFalse(decision.allowed)
            self.assertIn("STOP_REQUESTED_NOT_SERVER_CONFIRMED", decision.reasons)

    def test_cancelled_job_cannot_resume_or_complete(self):
        _, cancelled = self.pair()
        for state in ("QUEUED", "RUNNING", "COMPLETED"):
            update = dict(cancelled, state=state, eventSequence=12)
            decision = g.progress_gate(cancelled, update, lambda a, b: True)
            self.assertIn("INVALID_OR_TERMINAL_QUEUE_TRANSITION", decision.reasons)

    def test_confirmed_direct_cancel_retries_only_as_new_job(self):
        old, cancelled = self.pair()
        self.assertTrue(g.progress_gate(old, cancelled, lambda a, b: True).allowed)
        retry = dict(cancelled, state="QUEUED", attemptId="attempt-002", queueJobId="native-retry-002",
                     queueJobReceiptSha256="e" * 64, eventSequence=1, completedBytes=None, totalBytes=None)
        decision = g.retry_gate(cancelled, retry, user_retry_consent=True,
            native_queue_attested=True, trusted_queue_verifier=lambda a, b: True)
        self.assertTrue(decision.allowed, decision.reasons)
        retry["queueJobId"] = cancelled["queueJobId"]
        self.assertFalse(g.retry_gate(cancelled, retry, user_retry_consent=True,
            native_queue_attested=True, trusted_queue_verifier=lambda a, b: True).allowed)


if __name__ == "__main__":
    unittest.main()
