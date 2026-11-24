"""One composition case: the same release entrypoint fences both drift windows."""
import os
import unittest
from unittest.mock import patch
from test_joint_rues import JointBilingual
import review_release as release
import b5_retained_ingress as ingress
import retained_snapshot_review as r78

class ReleaseComposition(unittest.TestCase):
    def test_joint_review_both_drift_windows(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        def prepare():
            args, _ = fixture.build(("30 евро на покупку.", "No se sabe el saldo exacto."))
            packet = release.prepare_joint_review(**args)
            reviews = fixture.submissions(packet, (("correct","correct"),("correct","correct")))
            return args, reviews

        args, reviews = prepare()
        result = release.verify_joint_reviews(**args, **reviews)
        self.assertEqual(result["review_summary"]["decisions_bound"], 4)
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))

        args, reviews = prepare()
        original = ingress.verify_existing_chain
        def validation_drift(**kwargs):
            valid = original(**kwargs)
            self.assertTrue(valid)
            os.pwrite(args["descriptor_sets"][0][0], b"X", 0)
            return valid
        with patch.object(ingress, "verify_existing_chain", side_effect=validation_drift):
            with self.assertRaisesRegex(ValueError, "HOLD_RETAINED_CHAIN_CHANGED"):
                release.verify_joint_reviews(**args, **reviews)

        args, reviews = prepare()
        original_review = r78.verify_strict_reviews
        def review_drift(**kwargs):
            result = original_review(**kwargs)
            os.pwrite(args["descriptor_sets"][0][0], b"X", 0)
            return result
        with patch.object(r78, "verify_strict_reviews", side_effect=review_drift):
            with self.assertRaisesRegex(ValueError, "HOLD_B2_QUALITY_CLOSURE_DRIFT"):
                release.verify_joint_reviews(**args, **reviews)
