import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import b2_existing_dialog_review as probe


class ExistingReviewTests(unittest.TestCase):
    def setUp(self):
        self.dialog = "a" * 32
        self.session = "session-ru-es"
        self.rows = [dict(role="user" if i % 2 == 0 else "assistant",
                          content=content, message_id=f"row-{i}",
                          dialog_id=self.dialog, session_id=self.session)
                     for i, content in enumerate(("Четыре по 7?", "28 евро",
                         "Три по 7?", "21 евро", "En español, ¿total?",
                         "Son 21 euros. 🪐"))]
        self.docs = [dict(source="canonical_s03", independent=True, sequence=n,
                          dialog_id=self.dialog, session_id=self.session,
                          event_id=f"event-{n}", turn_id=f"turn-{n}",
                          messages=copy.deepcopy(self.rows[:2*n]),
                          full_answer_sha256=probe.digest(self.rows[2*n-1]["content"].encode()))
                     for n in (2, 3)]
        self.rubric = dict(schema=probe.SCHEMA, dialog_id=self.dialog,
                           session_id=self.session, turns=[
                             dict(turn=2, prompt=self.rows[2]["content"], locale="ru",
                                  criteria="Итог 21 евро, исправление учтено"),
                             dict(turn=3, prompt=self.rows[4]["content"], locale="es",
                                  criteria="Total 21 euros en español")])

    def invoke(self, **overrides):
        args = {}
        for key, obj in zip(("turn2", "turn3", "rubric"), (*self.docs, self.rubric)):
            raw = json.dumps(obj, ensure_ascii=False).encode()
            args[key+"_raw"] = raw
            args[key+"_pin"] = hashlib.sha256(raw).hexdigest()
        args.update(overrides)
        return probe.prepare_existing_review(**args)

    def test_existing_turns_only_blank_and_full_unicode(self):
        packet = self.invoke()
        self.assertEqual([x["turn"] for x in packet["evidence"]], [2, 3])
        self.assertEqual([len(x["history"]) for x in packet["evidence"]], [3, 5])
        self.assertEqual(packet["evidence"][-1]["answer"], self.rows[-1]["content"])
        self.assertTrue(all(x["verdict"] is None for x in packet["submission"]["decisions"]))
        self.assertEqual(packet["quality_grade"], "NOT_MEASURED")
        self.assertTrue(packet["native_acceptance"].startswith("HOLD"))

    def test_independent_pins_and_no_changed_prefix(self):
        with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_PIN"):
            self.invoke(turn3_pin="0"*64)
        self.docs[1]["messages"][1]["content"] = "подмена"
        with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_PREFIX_CHANGED"):
            self.invoke()

    def test_scope_rubric_and_event_reuse(self):
        for key, value, reason in (
            ("sequence", True, "READBACK_SCOPE"),
            ("session_id", "foreign", "READBACK_SCOPE"),
            ("event_id", "event-2", "EVENT_REUSE"),
            ("full_answer_sha256", "0"*64, "ANSWER_PIN")):
            old = self.docs[1][key]
            self.docs[1][key] = value
            with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_"+reason):
                self.invoke()
            self.docs[1][key] = old
        self.rubric["turns"][1]["prompt"] = "Different prompt"
        with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_RUBRIC"):
            self.invoke()

    def review_inputs(self):
        args = {}
        for key, obj in zip(("turn2", "turn3", "rubric"), (*self.docs, self.rubric)):
            raw = json.dumps(obj, ensure_ascii=False).encode()
            args[key+"_raw"] = raw
            args[key+"_pin"] = probe.digest(raw)
        template = probe.prepare_existing_review(**args)["submission"]
        a, b = copy.deepcopy(template), copy.deepcopy(template)
        for reviewer, doc in (("reviewer-A", a), ("reviewer-B", b)):
            doc["reviewer_id"] = reviewer
            for row in doc["decisions"]:
                row.update(verdict="correct", reason="Verified against full dialogue")
        return args, a, b

    def close_reviews(self, args, a, b):
        ar, br = (json.dumps(x, ensure_ascii=False).encode() for x in (a, b))
        return probe.verify_existing_reviews(
            **args, submission_a_raw=ar, submission_a_pin=probe.digest(ar),
            submission_b_raw=br, submission_b_pin=probe.digest(br))

    def test_two_review_closure_never_native_pass(self):
        args, a, b = self.review_inputs()
        result = self.close_reviews(args, a, b)
        self.assertEqual(result["decisions_bound"], 4)
        self.assertEqual(result["review_summary"],
                         "TWO_REVIEWER_CONSENSUS_REPORTED_UNVERIFIED")
        self.assertFalse(result["reviewer_identity_verified"])
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        b["decisions"][0]["verdict"] = "uncertain"
        result = self.close_reviews(args, a, b)
        self.assertEqual(result["review_summary"], "ADJUDICATION_REQUIRED")
        self.assertEqual(result["reported_uncertain"], [2])
        b["decisions"][1]["verdict"] = "incorrect"
        self.assertEqual(self.close_reviews(args, a, b)["reported_incorrect"], [3])

    def test_closure_rejects_foreign_duplicate_and_stale(self):
        args, a, original = self.review_inputs()
        for mutate, reason in (
            (lambda b: b.update(reviewer_id="REVIEWER-a"), "REVIEWER"),
            (lambda b: b.update(rubric_sha256="0"*64), "REVIEW_SCOPE"),
            (lambda b: b["decisions"][0].update(turn=3), "REVIEW_COVERAGE"),
            (lambda b: b["decisions"][1].update(answer_sha256="0"*64), "REVIEW_ANSWER"),
            (lambda b: b["decisions"][0].update(verdict=None), "REVIEW_VERDICT"),
            (lambda b: b["decisions"][0].update(reason=""), "REVIEW_REASON"),
        ):
            b = copy.deepcopy(original)
            mutate(b)
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.close_reviews(args, a, b)
        ar, br = (json.dumps(x).encode() for x in (a, original))
        with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_PIN"):
            probe.verify_existing_reviews(
                **args, submission_a_raw=ar, submission_a_pin="0"*64,
                submission_b_raw=br, submission_b_pin=probe.digest(br))


if __name__ == "__main__":
    unittest.main()
