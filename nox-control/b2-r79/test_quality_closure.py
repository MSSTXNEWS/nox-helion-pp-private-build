"""Exact R78 comparison: mutation after review, not during loader."""
import os
import unittest
from unittest.mock import patch
from test_joint_rues import JointBilingual
import retained_snapshot_review as r78
import quality_closure as candidate

class QualityClosure(unittest.TestCase):
    def test_final_review_drift(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args, _ = fixture.build(("30 евро на покупку.", "No se sabe el saldo exacto."))
        packet = candidate.prepare_joint_review(**args)
        reviews = fixture.submissions(packet, (("correct","correct"),("correct","correct")))
        clean = candidate.verify_joint_reviews(**args, **reviews)
        self.assertEqual(clean["review_summary"]["decisions_bound"], 4)
        self.assertTrue(clean["native_acceptance"].startswith("HOLD"))
        original = r78.verify_strict_reviews

        def mutation_for(inputs):
            def drift(**kwargs):
                result = original(**kwargs)
                os.pwrite(inputs["descriptor_sets"][0][0], b"X", 0)
                return result
            return drift

        with patch.object(r78, "verify_strict_reviews", side_effect=mutation_for(args)):
            stale = r78.verify_joint_reviews(**args, **reviews)
            self.assertEqual(stale["review_summary"]["decisions_bound"], 4)
        fresh, _ = fixture.build(("30 евро на покупку.", "No se sabe el saldo exacto."))
        fresh_packet = candidate.prepare_joint_review(**fresh)
        fresh_reviews = fixture.submissions(fresh_packet, (("correct","correct"),("correct","correct")))
        with patch.object(r78, "verify_strict_reviews", side_effect=mutation_for(fresh)):
            with self.assertRaisesRegex(ValueError, "HOLD_B2_QUALITY_CLOSURE_DRIFT"):
                candidate.verify_joint_reviews(**fresh, **fresh_reviews)

if __name__ == "__main__":
    unittest.main(verbosity=2)
