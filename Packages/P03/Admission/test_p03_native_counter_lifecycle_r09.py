"""R09 source-only regressions against pinned original P03 native queue lifecycle.
No network, weights, filesystem model import or actual native attestor.
"""
import unittest
import p03_modelcenter_gate as g
from test_p03_modelcenter_gate import (queue_fixture, retry_fixture, TEST_ONLY_NATIVE_RECEIPT_VERIFIER)


class R09NativeQueueCounterLifecycle(unittest.TestCase):
    """P03 donor ModelDownloadQueueStore.cs: queued/RetryAsync bytes are null;
    CancelQueuedAsync moves QUEUED directly to CANCELLED. Fixtures are synthetic;
    E06 must still provide the REAL trusted native verifier and receipts.
    """
    def run_progress(self, old, new, verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER):
        return g.progress_gate(old, new, verifier)

    def run_retry(self, old, new, verifier=TEST_ONLY_NATIVE_RECEIPT_VERIFIER):
        return g.retry_gate(old, new, user_retry_consent=True,
                            native_queue_attested=True, trusted_queue_verifier=verifier)

    def test_135_first_native_measured_bytes_from_unknown_queued(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=100,completedBytes=10)
        self.assertTrue(self.run_progress(old,new).allowed)

    def test_136_native_queued_before_start_has_no_fabricated_percent(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="QUEUED",totalBytes=None,completedBytes=None)
        self.assertTrue(self.run_progress(old,new).allowed)

    def test_137_native_direct_cancel_queued_requires_ack(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="CANCELLED",totalBytes=None,completedBytes=None,
                   nativeCancelAttested=True,cancelAckReceiptSha256="f"*64)
        self.assertTrue(self.run_progress(old,new).allowed)

    def test_138_native_direct_cancel_without_ack_hold(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="CANCELLED",totalBytes=None,completedBytes=None)
        self.assertIn("CANCELLATION_ACK_NOT_ATTESTED",self.run_progress(old,new).reasons)

    def test_139_native_direct_cancel_without_trusted_verifier_hold(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="CANCELLED",totalBytes=None,completedBytes=None,
                   nativeCancelAttested=True,cancelAckReceiptSha256="f"*64)
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING",self.run_progress(old,new,None).reasons)

    def test_140_unknown_bytes_cannot_claim_completed(self):
        old,new=queue_fixture();old.update(state="RUNNING",totalBytes=None,completedBytes=None)
        new.update(state="COMPLETED",totalBytes=None,completedBytes=None,
                   nativeCompletionAttested=True,completedReceiptSha256="f"*64,
                   observedArtifactSha256="d"*64)
        got=self.run_progress(old,new)
        self.assertFalse(got.allowed)
        self.assertIn("COMPLETION_RECEIPT_OR_BYTES_MISSING",got.reasons)

    def test_141_native_indeterminate_running_state(self):
        old,new=queue_fixture();old.update(state="RUNNING",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=None,completedBytes=None)
        self.assertTrue(self.run_progress(old,new).allowed)

    def test_142_known_bytes_cannot_regress_to_unknown(self):
        old,new=queue_fixture();new.update(state="RUNNING",totalBytes=None,completedBytes=None)
        self.assertIn("NON_MONOTONIC_OR_INVALID_PROGRESS",self.run_progress(old,new).reasons)

    def test_143_first_measured_bytes_cannot_overrun(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=100,completedBytes=101)
        self.assertIn("NON_MONOTONIC_OR_INVALID_PROGRESS",self.run_progress(old,new).reasons)

    def test_144_first_measured_bytes_reject_boolean(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=100,completedBytes=True)
        self.assertIn("NON_MONOTONIC_OR_INVALID_PROGRESS",self.run_progress(old,new).reasons)

    def test_145_retry_new_job_counters_unknown_by_original_design(self):
        old,new=retry_fixture();new.update(totalBytes=None,completedBytes=None)
        self.assertTrue(self.run_retry(old,new).allowed)

    def test_146_cancelled_before_start_retry_unknown_counters(self):
        old,new=retry_fixture();old.update(state="CANCELLED",totalBytes=None,completedBytes=None,
                                           cancelAckReceiptSha256="f"*64,nativeCancelAttested=True)
        new.update(totalBytes=None,completedBytes=None)
        self.assertTrue(self.run_retry(old,new).allowed)

    def test_147_retry_not_allowed_to_carry_stale_measured_bytes(self):
        old,new=retry_fixture();new.update(totalBytes=100,completedBytes=60)
        self.assertIn("RETRY_BYTES_INVALID",self.run_retry(old,new).reasons)

    def test_148_retry_unknown_counters_still_need_trusted_verifier(self):
        old,new=retry_fixture();new.update(totalBytes=None,completedBytes=None)
        self.assertIn("NATIVE_QUEUE_VERIFIER_MISSING",self.run_retry(old,new,None).reasons)

    def test_149_first_bytes_without_native_proof_hold(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=100,completedBytes=10)
        self.assertIn("NATIVE_QUEUE_RECEIPT_REJECTED",self.run_progress(old,new,lambda _o,_n:False).reasons)

    def test_150_first_measured_bytes_must_have_real_total(self):
        old,new=queue_fixture();old.update(state="QUEUED",totalBytes=None,completedBytes=None)
        new.update(state="RUNNING",totalBytes=0,completedBytes=0)
        self.assertIn("TOTAL_BYTES_UNVERIFIED_OR_CHANGED",self.run_progress(old,new).reasons)

