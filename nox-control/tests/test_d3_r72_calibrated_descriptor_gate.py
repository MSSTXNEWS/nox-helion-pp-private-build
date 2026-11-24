"""One cross-source integration with synthetic inputs; no native acceptance."""
import copy
import json
import unittest
from test_d3_r70_owner_fd_review_ingress import DescriptorIntegration
from test_d3_r68_review_binding import raw, digest
from b2_r71_calibrated_rubric import build_preanswer_rubric
from d3_r72_calibrated_descriptor_gate import (
    prepare_calibrated_review, verify_calibrated_reviews,
)


class CalibratedComposition(unittest.TestCase):
    def test_open_close_and_fail_closed(self):
        fixture = DescriptorIntegration()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        args = fixture.args()
        previous = json.loads(args["rubric_raw"])
        plan = dict(dialog_id=args["dialog_id"], session_id=args["session_id"],
                    planned_turns=[dict(turn=t["turn"], prompt=t["prompt"],
                        locale=t["locale"], owner_reference="Synthetic reference only")
                        for t in previous["turns"]])
        args["rubric_raw"], args["rubric_pin"] = build_preanswer_rubric(**plan)
        plan_bytes = raw(plan)
        args.update(plan_raw=plan_bytes, plan_pin=digest(plan_bytes))
        result = prepare_calibrated_review(**args)
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        submissions = {}
        for side in ("a", "b"):
            doc = copy.deepcopy(result["review_packet"]["submission"])
            doc["reviewer_id"] = "fixture-" + side
            for row in doc["decisions"]:
                row.update(verdict="correct", reason="Synthetic reference only")
            data = raw(doc)
            submissions.update({f"submission_{side}_raw": data,
                                f"submission_{side}_pin": digest(data)})
        final = verify_calibrated_reviews(**args, **submissions)
        self.assertEqual(final["review_summary"]["decisions_bound"], 4)
        self.assertFalse(final["review_summary"]["reviewer_identity_verified"])
        self.assertTrue(final["native_acceptance"].startswith("HOLD"))
        with self.assertRaisesRegex(ValueError, "PLAN_PIN"):
            prepare_calibrated_review(**dict(args, plan_pin="0"*64))
        changed = copy.deepcopy(plan)
        changed["planned_turns"][0]["owner_reference"] = "Different reference"
        changed_raw = raw(changed)
        with self.assertRaisesRegex(ValueError, "RUBRIC_MISMATCH"):
            verify_calibrated_reviews(**dict(args, plan_raw=changed_raw,
                                       plan_pin=digest(changed_raw)), **submissions)
        forged = raw(previous)
        with self.assertRaisesRegex(ValueError, "RUBRIC_MISMATCH"):
            prepare_calibrated_review(**dict(args, rubric_raw=forged,
                                             rubric_pin=digest(forged)))


if __name__ == "__main__":
    unittest.main(defaultTest="CalibratedComposition", verbosity=2)
