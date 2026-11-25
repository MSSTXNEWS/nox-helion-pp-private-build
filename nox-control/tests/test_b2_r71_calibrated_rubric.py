import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from b2_r71_calibrated_rubric import build_preanswer_rubric, RULE
from b2_existing_dialog_review import prepare_existing_review, digest

class RubricTests(unittest.TestCase):
    def setUp(self):
        self.dialog, self.session = "a"*32, "ru-es-session"
        self.plans = [
            dict(turn=2, prompt="Исправление: три по 7. Сколько?",
                 locale="ru", owner_reference="Три по 7 = 21; прежнее число книг отменено."),
            dict(turn=3, prompt="En español, ¿total y fecha de entrega?",
                 locale="es", owner_reference="Total 21 euros; fecha no proporcionada, no inventar.")]
    def build(self, plans=None):
        return build_preanswer_rubric(dialog_id=self.dialog, session_id=self.session,
                                      planned_turns=self.plans if plans is None else plans)
    def test_deterministic_exact_preanswer_contract(self):
        raw, pin = self.build()
        self.assertEqual(pin, digest(raw))
        self.assertEqual((raw, pin), self.build())
        doc = json.loads(raw)
        self.assertEqual([t["prompt"] for t in doc["turns"]], [p["prompt"] for p in self.plans])
        for row in doc["turns"]:
            self.assertIn(RULE, row["criteria"])
            self.assertLessEqual(len(row["criteria"]), 1000)
        self.assertNotIn("verdict", doc)
    def test_reject_answer_injection_missing_scope_and_wrong_language(self):
        for patch in ({"answer":"fabricated"}, {"turn":True}, {"locale":"es"},
                      {"owner_reference":""}, {"prompt":""}):
            bad = copy.deepcopy(self.plans)
            bad[0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.build(bad)
    def test_actual_b2_packet_compatibility_and_prompt_binding(self):
        raw, pin = self.build()
        rows = []
        for i, content in enumerate(("Четыре по 7?", "28 евро",
             self.plans[0]["prompt"], "21 евро.", self.plans[1]["prompt"],
             "21 euros; no conozco la fecha.")):
            rows.append(dict(role="user" if i%2==0 else "assistant", content=content,
                             message_id=f"row-{i}", dialog_id=self.dialog, session_id=self.session))
        args = dict(rubric_raw=raw, rubric_pin=pin)
        for n in (2,3):
            doc = dict(source="canonical_s03", independent=True, sequence=n,
                       dialog_id=self.dialog, session_id=self.session, event_id=f"event-{n}",
                       turn_id=f"turn-{n}", messages=rows[:2*n],
                       full_answer_sha256=digest(rows[2*n-1]["content"].encode()))
            wire = json.dumps(doc, ensure_ascii=False).encode()
            args.update({f"turn{n}_raw":wire, f"turn{n}_pin":digest(wire)})
        packet = prepare_existing_review(**args)
        self.assertEqual([x["requested_locale"] for x in packet["evidence"]], ["ru","es"])
        self.assertTrue(all(x["verdict"] is None for x in packet["submission"]["decisions"]))
        self.assertEqual(packet["quality_grade"], "NOT_MEASURED")
        self.assertTrue(packet["native_acceptance"].startswith("HOLD"))
        bad = copy.deepcopy(self.plans)
        bad[1]["prompt"] += "!"
        args["rubric_raw"], args["rubric_pin"] = self.build(bad)
        with self.assertRaisesRegex(ValueError, "RUBRIC"):
            prepare_existing_review(**args)

if __name__ == "__main__":
    unittest.main()
