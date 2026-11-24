import unittest
from test_joint_rues import JointBilingual
import review_release as r80
from review_feedback import verify_with_feedback

class ReviewFeedback(unittest.TestCase):
    def test_preserve_reasons_without_promoting_verdicts(self):
        fixture = JointBilingual()
        self.addCleanup(fixture.doCleanups)
        args, _ = fixture.build(("30 евро на покупку.", "Quedan exactamente 90 euros."))
        packet = r80.prepare_joint_review(**args)
        reviews = fixture.submissions(packet, (("correct","incorrect"),("correct","uncertain")))
        result = verify_with_feedback(**args, **reviews)
        self.assertEqual(result["review_summary"]["reported_incorrect"], [3])
        self.assertEqual(result["review_summary"]["disagreements"], [3])
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        data = result["correction_evidence"]
        self.assertFalse(data["reviewer_identity_verified"])
        self.assertFalse(data["model_instruction"])
        self.assertFalse(data["training_admitted"])
        from b2_existing_dialog_review import read_pinned
        expected = []
        for side in ("a", "b"):
            pin = reviews["submission_" + side + "_pin"]
            doc = read_pinned(reviews["submission_" + side + "_raw"], pin)
            for d in doc["decisions"]:
                expected.append(dict(turn=d["turn"], answer_sha256=d["answer_sha256"],
                    verdict=d["verdict"], reason=d["reason"], submission_sha256=pin, reviewer_slot=side))
        self.assertEqual(data["entries"], expected)
        bad = dict(reviews, submission_a_pin="0"*64)
        with self.assertRaises(ValueError):
            verify_with_feedback(**args, **bad)
