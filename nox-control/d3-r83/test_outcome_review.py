import unittest
from test_joint_rues import JointBilingual
from test_b5_bound_failed_poststate import BoundPendingTests
from test_b5_chain_guard import checkpoint
from review_release import prepare_joint_review
from outcome_review import route_review

class JointOutcome(unittest.TestCase):
    def test_completed_and_failed_attempts_never_share_quality(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args, _ = fixture.build(("30 евро на покупку.", "Quedan exactamente 90 euros."))
        packet = prepare_joint_review(**args)
        reviews = fixture.submissions(packet, (("correct","incorrect"),("correct","uncertain")))
        complete = dict(args, **reviews)
        result = route_review(outcome="completed", review_inputs=complete)
        self.assertEqual(result["route"], "REVIEW_DATA_ONLY")
        self.assertEqual(len(result["quality_sample"]["correction_evidence"]["entries"]), 4)
        self.assertFalse(result["native_accepted"])
        self.assertFalse(result["training_admitted"])
        for n in (1,2):
            rows = checkpoint(n+1)[0][:-1]
            evidence = BoundPendingTests().args(n, rows)
            evidence["expected_user_message_id"] = rows[-1]["message_id"]
            held = route_review(outcome="failed", review_inputs=complete, failed_attempt=evidence)
            self.assertEqual(held["reason"], "HOLD_S03_FAILURE_PENDING_USER")
            self.assertIsNone(held["quality_sample"])
            evidence["expected_user_message_id"] = "foreign-id"
            held = route_review(outcome="uncertain", review_inputs=complete, failed_attempt=evidence)
            self.assertEqual(held["reason"], "HOLD_S03_FAILURE_PENDING_ID_MISMATCH")
            self.assertIsNone(held["quality_sample"])
            self.assertFalse(held["retry_allowed"])
            self.assertFalse(held["next_post_allowed"])
            self.assertEqual(route_review(outcome="completed",review_inputs=complete,
                failed_attempt=evidence)["reason"],"HOLD_D3_CONTRADICTORY_ATTEMPT")
        self.assertIsNone(route_review(outcome="unknown",review_inputs=complete)["quality_sample"])
        self.assertIsNone(route_review(outcome="failed",review_inputs=complete)["quality_sample"])
