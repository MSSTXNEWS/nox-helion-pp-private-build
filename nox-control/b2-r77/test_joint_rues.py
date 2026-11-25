"""B2 R77: synthetic, joint R76 RU/ES correction and stale-review regression.
No live model, owner admission or S03 write. Do not treat synthetic judgments as quality measurements.
"""
import copy
import hashlib
import unittest
from b0_resume_bridge import owner_prefix_sha
from b2_r71_calibrated_rubric import build_preanswer_rubric
from test_d3_r70_owner_fd_review_ingress import DescriptorIntegration
from test_b2_r69_strict_review_ingress import inputs, witness
from test_d3_r68_review_binding import raw, digest, actual_b4_pair
from joint_resume_review import prepare_joint_review, verify_joint_reviews

class JointBilingual(unittest.TestCase):
    def build(self, answers):
        base = inputs()
        rows = copy.deepcopy(base["turn3_rows"])
        texts = ("Три одинаковые покупки; бюджет 120 евро, доставка неизвестна.",
                 "Запомнил исходный бюджет и число покупок.",
                 "Исправление: бюджет 90 евро. Сколько на одну покупку без доставки?",
                 answers[0],
                 "En español: ¿cuál es el saldo tras pagar un envío de coste desconocido?",
                 answers[1])
        for row, content in zip(rows, texts):
            row["content"] = content
        for seq, name in enumerate(("prior", "turn2", "turn3"), 1):
            base[name+"_rows"] = rows[:2*seq]
            base[name+"_witnesses"] = witness(rows[:2*seq], seq)
        plan = dict(dialog_id=base["dialog_id"], session_id=base["session_id"],
                    planned_turns=[
                        dict(turn=2, prompt=texts[2], locale="ru", owner_reference="90 / 3 = 30 евро; не использовать старые 120 евро."),
                        dict(turn=3, prompt=texts[4], locale="es", owner_reference="90 menos el coste desconocido; no se puede dar una cifra exacta.")])
        base["rubric_raw"], base["rubric_pin"] = build_preanswer_rubric(**plan)
        base["pair_raw"] = actual_b4_pair(answers)
        base["pair_pin"] = digest(base["pair_raw"])
        fixture = DescriptorIntegration()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        args = fixture.args(base)
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
        return dict(args, observations=tuple(observations)), plan

    def submissions(self, packet, marks):
        result = {}
        for side, verdicts in zip(("a","b"), marks):
            doc = copy.deepcopy(packet["review_packet"]["submission"])
            doc["reviewer_id"] = "synthetic-"+side
            for row, verdict in zip(doc["decisions"], verdicts):
                row.update(verdict=verdict, reason="Synthetic fixture judgment, not a live model review.")
            data=raw(doc)
            result.update({f"submission_{side}_raw":data, f"submission_{side}_pin":digest(data)})
        return result

    def test_joint_stale_review_fences(self):
        args, plan = self.build(("30 евро на покупку.", "Quedan exactamente 90 euros."))
        packet = prepare_joint_review(**args)
        self.assertEqual(packet["resume_evidence"], "TURNS_2_3_MATCHED_OFFLINE")
        self.assertEqual([e["requested_locale"] for e in packet["review_packet"]["evidence"]], ["ru","es"])
        reviews = self.submissions(packet, (("correct","incorrect"),("correct","uncertain")))
        result = verify_joint_reviews(**args, **reviews)
        summary = result["review_summary"]
        self.assertEqual(summary["reported_incorrect"], [3])
        self.assertEqual(summary["reported_uncertain"], [3])
        self.assertEqual(summary["disagreements"], [3])
        self.assertFalse(summary["reviewer_identity_verified"])
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        # Coherent new rubric, independently re-pinned in this synthetic fixture.
        # Original reviews must NOT transfer to this changed rubric.
        plan["planned_turns"][1]["owner_reference"] += " Expresar la incertidumbre explícitamente."
        rr, rp = build_preanswer_rubric(**plan)
        changed = dict(args, rubric_raw=rr, rubric_pin=rp, plan_raw=raw(plan), plan_pin=digest(raw(plan)))
        prepare_joint_review(**changed)
        with self.assertRaisesRegex(ValueError, "REVIEW_SCOPE"):
            verify_joint_reviews(**changed, **reviews)
        # Coherent different answers and readback chain: old reviews cannot transfer.
        other, _ = self.build(("40 евро на покупку.", "No se sabe el saldo exacto."))
        other_packet = prepare_joint_review(**other)
        with self.assertRaisesRegex(ValueError, "REVIEW_SCOPE|REVIEW_ANSWER"):
            verify_joint_reviews(**other, **reviews)
        fresh = self.submissions(other_packet, (("incorrect","correct"),("incorrect","correct")))
        final = verify_joint_reviews(**other, **fresh)
        self.assertEqual(final["review_summary"]["reported_incorrect"], [2])
        self.assertTrue(final["native_acceptance"].startswith("HOLD"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
