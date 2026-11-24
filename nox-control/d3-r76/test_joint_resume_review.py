"""One joint staged functional scenario. Synthetic observations only."""
import copy
import hashlib
import json
import unittest
from b0_resume_bridge import owner_prefix_sha
from b2_r71_calibrated_rubric import build_preanswer_rubric
from test_d3_r70_owner_fd_review_ingress import DescriptorIntegration
from test_b2_r69_strict_review_ingress import inputs
from test_d3_r68_review_binding import raw, digest
from joint_resume_review import prepare_joint_review, verify_joint_reviews

class JointTest(unittest.TestCase):
    def test_joint_resume_and_review(self):
        base = inputs()
        fixture = DescriptorIntegration()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        args = fixture.args(base)
        previous = json.loads(args["rubric_raw"])
        plan = dict(dialog_id=args["dialog_id"], session_id=args["session_id"],
                    planned_turns=[dict(turn=t["turn"], prompt=t["prompt"], locale=t["locale"],
                    owner_reference="Synthetic reference") for t in previous["turns"]])
        args["rubric_raw"], args["rubric_pin"] = build_preanswer_rubric(**plan)
        args.update(plan_raw=raw(plan), plan_pin=digest(raw(plan)))
        observations = []
        for i, (before, after) in enumerate((("prior","turn2"),("turn2","turn3"))):
            old, new = base[before+"_rows"], base[after+"_rows"]
            owner = copy.deepcopy(old)
            pin = owner_prefix_sha(args["dialog_id"], owner)
            preflight = dict(prefix_rows=len(old), scope="EXISTING_OWNER_DIALOG_PREFIX_ONLY_NOT_INDEPENDENT_S03",
                prefix_pin_matched=True, prefix_sha256=pin,
                dialog_id_sha256=hashlib.sha256(args["dialog_id"].encode("ascii")).hexdigest(),
                **{k:False for k in ("model_post_issued","dialog_created","browser_multiturn_accepted",
                     "native_s03_independently_verified","production_accepted")})
            observations.append(dict(preflight=preflight, expected_owner_sha=pin, owner_rows=owner,
                browser_before=copy.deepcopy(old), browser_after=copy.deepcopy(new),
                calls_before=i, calls_after=i+1, admitted_before=i, admitted_after=i+1,
                prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                terminal_saved=True, dom_matches=True))
        packet=prepare_joint_review(observations=tuple(observations), **args)
        self.assertEqual(packet["resume_evidence"], "TURNS_2_3_MATCHED_OFFLINE")
        self.assertTrue(packet["native_acceptance"].startswith("HOLD"))
        submissions={}
        for side in ("a","b"):
            doc=copy.deepcopy(packet["review_packet"]["submission"])
            doc["reviewer_id"]="synthetic-"+side
            for row in doc["decisions"]:
                row.update(verdict="correct", reason="Synthetic only")
            data=raw(doc)
            submissions.update({f"submission_{side}_raw":data,f"submission_{side}_pin":digest(data)})
        final=verify_joint_reviews(observations=tuple(observations), **args, **submissions)
        self.assertEqual(final["review_summary"]["decisions_bound"],4)
        self.assertTrue(final["native_acceptance"].startswith("HOLD"))
        bad=copy.deepcopy(observations)
        bad[1]["calls_before"]=9
        with self.assertRaisesRegex(ValueError,"CONTINUITY"):
            prepare_joint_review(observations=tuple(bad),**args)
        bad=copy.deepcopy(observations)
        bad[1]["browser_after"][-1]["content"]="wrong visible answer"
        with self.assertRaisesRegex(ValueError,"BROWSER_TRANSCRIPT"):
            verify_joint_reviews(observations=tuple(bad),**args,**submissions)

if __name__=="__main__":
    unittest.main(verbosity=2)
