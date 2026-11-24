"""One new functional case: R77 fixture with R64 retained snapshot."""
import os
import unittest
from unittest.mock import patch
from test_joint_rues import JointBilingual
import retained_snapshot_review as r78

class RetainedSnapshotTest(unittest.TestCase):
    def test_single_snapshot_and_retained_tamper(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args, _ = fixture.build(("30 евро на покупку.", "No se sabe el saldo exacto."))
        with patch.object(r78, "load_retained_chain", wraps=r78.load_retained_chain) as load:
            packet = r78.prepare_joint_review(**args)
            self.assertEqual(load.call_count, 1)
            reviews = fixture.submissions(packet, (("correct","correct"),("correct","correct")))
            result = r78.verify_joint_reviews(**args, **reviews)
            self.assertEqual(load.call_count, 2)
            self.assertEqual(result["review_summary"]["decisions_bound"], 4)
            self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        # Corrupt the retained first checkpoint; no new review may be closed.
        fd = args["descriptor_sets"][0][0]
        os.pwrite(fd, b"X", 0)
        with self.assertRaises(ValueError):
            r78.verify_joint_reviews(**args, **reviews)

if __name__ == "__main__":
    unittest.main(verbosity=2)
