"""Full-chain synthetic RU/ES integration; no owner authentication inferred."""
import unittest
from receipted_outcome import review_attempt
from test_joint_rues import JointBilingual
from test_b5_bound_failed_poststate import BoundPendingTests
from test_b5_chain_guard import checkpoint, raw, sha
from review_release import prepare_joint_review

class StrictReceiptIntegration(unittest.TestCase):
    def test_real_chain_receipt_scope_and_quality_separation(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args, _ = fixture.build(("30 евро на покупку.", "Quedan exactamente 90 euros."))
        packet = prepare_joint_review(**args)
        complete = dict(args, **fixture.submissions(
            packet, (("correct", "incorrect"), ("correct", "uncertain"))))
        result = review_attempt(outcome="completed", review_inputs=complete)
        self.assertEqual(result["route"], "REVIEW_DATA_ONLY")
        self.assertEqual(len(result["quality_sample"]["correction_evidence"]["entries"]), 4)
        self.assertFalse(result["training_admitted"])
        self.assertFalse(result["native_accepted"])
        for n in (1, 2):
            rows = checkpoint(n+1)[0][:-1]
            evidence = BoundPendingTests().args(n, rows)
            receipt = dict(schema="nox.s03.failed-attempt-binding.v1",
                           dialog_id=evidence["dialog_id"], session_id=evidence["session_id"],
                           attempt_id=evidence["attempt_id"], snapshot_sha256=evidence["snapshot_sha256"],
                           user_message_id=rows[-1]["message_id"])
            def pinned(**change):
                data = raw(dict(receipt, **change))
                return dict(evidence, admission_raw=data, admission_sha256=sha(data))
            valid = pinned()
            cases = [
                (valid, "HOLD_S03_FAILURE_PENDING_USER"),
                (dict(evidence, expected_user_message_id=rows[-1]["message_id"]), "HOLD_S03_FAILURE_EVIDENCE_SCHEMA"),
                (evidence, "HOLD_S03_FAILURE_ADMISSION_PIN"),
                (dict(valid, admission_sha256="0"*64), "HOLD_S03_FAILURE_ADMISSION_PIN"),
                (pinned(user_message_id="foreign-id"), "HOLD_S03_FAILURE_PENDING_ID_MISMATCH"),
                (pinned(attempt_id="other-attempt"), "HOLD_S03_FAILURE_ADMISSION_SCOPE"),
                (pinned(snapshot_sha256="0"*64), "HOLD_S03_FAILURE_ADMISSION_SCOPE"),
            ]
            for evidence_case, expected in cases:
                for outcome in ("failed", "uncertain"):
                    held = review_attempt(outcome=outcome, review_inputs=complete, failed_attempt=evidence_case)
                    self.assertEqual(held["route"], "HOLD")
                    self.assertEqual(held["reason"], expected)
                    self.assertIsNone(held["quality_sample"])
                    for flag in ("retry_allowed", "next_post_allowed", "training_admitted", "native_accepted"):
                        self.assertFalse(held[flag])
            self.assertEqual(review_attempt(outcome="completed", review_inputs=complete,
                failed_attempt=valid)["reason"], "HOLD_D3_CONTRADICTORY_ATTEMPT")
