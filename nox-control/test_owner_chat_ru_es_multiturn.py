"""B5 focused source contract: RU first-turn / Spanish follow-up, same S03 dialog.

No browser, native POST, live S03 or production host mutation. The historical
multiturn canonical-S03 HOLD remains mandatory until real writer/readback wiring.
"""
import hashlib
import unittest

from owner_chat_browser_qa import (
    allowed_qa_request,
    canonical_s03_proof_valid,
    multiturn_followup_prompt,
    multiturn_history_valid,
)

TOKEN = "gmnop"
DIALOG = "synthetic-owner-dialog"
RU = f"[NOX UI QA {TOKEN}] Напиши числа от одного до десяти через запятую. Без пояснений и без других слов."
FIRST = "1,2,3,4,5,6,7,8,9,10"
LAST = "10,9,8,7,6,5,4,3,2,1"


def rows(spanish_prompt):
    return [
        {"role": "user", "content": RU},
        {"role": "assistant", "content": FIRST},
        {"role": "user", "content": spanish_prompt},
        {"role": "assistant", "content": LAST},
    ]


def s03_proof(transcript):
    writer = {
        "source": "canonical_s03", "verified": True, "durable": True,
        "event_id": "evt-02", "turn_id": "turn-02", "sequence": 2,
        "dialog_id": DIALOG,
    }
    readback = {
        "source": "canonical_s03", "independent": True,
        "event_id": "evt-02", "turn_id": "turn-02", "sequence": 2,
        "dialog_id": DIALOG, "messages": transcript,
        "full_answer_sha256": hashlib.sha256(LAST.encode("utf-8")).hexdigest(),
    }
    return writer, readback


class OwnerRuEsContinuity(unittest.TestCase):
    def test_default_russian_prompt_byte_equivalent(self):
        self.assertEqual(
            multiturn_followup_prompt(TOKEN, "multiturn"),
            f"[NOX UI QA {TOKEN}] Используя предыдущий ответ, перечисли "
            "те же числа в обратном порядке через запятую. Без пояснений.",
        )

    def test_spanish_opt_in_preserves_token_and_requests_previous_ru_answer(self):
        text = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        self.assertTrue(text.startswith(f"[NOX UI QA {TOKEN}] "))
        self.assertIn("respuesta anterior en ruso", text)
        self.assertIn("números del diez al uno", text)
        self.assertNotEqual(text, multiturn_followup_prompt(TOKEN, "multiturn"))
        with self.assertRaisesRegex(RuntimeError, "HOLD_QA_LANGUAGE_MODE"):
            multiturn_followup_prompt(TOKEN, "es_es")

    def test_exact_spanish_followup_keeps_same_dialog_and_one_shot_gate(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        good = {"message": es, "dialog_id": DIALOG}
        self.assertTrue(allowed_qa_request(1, True, RU, es, good, DIALOG))
        self.assertFalse(allowed_qa_request(1, False, RU, es, good, DIALOG))
        self.assertFalse(allowed_qa_request(2, True, RU, es, good, DIALOG))
        self.assertFalse(allowed_qa_request(1, True, RU, es, good, "different-dialog"))
        self.assertFalse(allowed_qa_request(1, True, RU, es, dict(good, message=es[:-1]), DIALOG))

    def test_ru_es_four_turn_history_needs_independent_canonical_s03(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        transcript = rows(es)
        self.assertTrue(multiturn_history_valid(transcript, RU, FIRST, es, LAST))
        self.assertFalse(canonical_s03_proof_valid(None, None, DIALOG, transcript))
        writer, proof = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, proof, DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(writer, proof, "different-dialog", transcript))
        self.assertFalse(canonical_s03_proof_valid(writer, dict(proof, independent=False), DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(writer, dict(proof, full_answer_sha256="0"*64), DIALOG, transcript))
        altered = rows(es)
        altered[2]["content"] = altered[2]["content"].replace("números", "numeros")
        self.assertFalse(multiturn_history_valid(altered, RU, FIRST, es, LAST))
        self.assertFalse(canonical_s03_proof_valid(writer, proof, DIALOG, altered))
        self.assertFalse(multiturn_history_valid(transcript[:2], RU, FIRST, es, LAST))


if __name__ == "__main__":
    unittest.main()
