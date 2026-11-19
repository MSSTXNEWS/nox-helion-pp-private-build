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
    ru_es_context_challenge,
    ru_es_unleaked_first_prompt,
    ru_es_unleaked_first_answer_valid,
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
    def test_canonical_s03_rejects_single_turn_even_with_matching_receipt_metadata(self):
        # Before this regression, two messages plus a matching last-answer SHA
        # could masquerade as a complete RU/ES multi-turn S03 acceptance.
        one_turn = [
            {"role": "user", "content": RU},
            {"role": "assistant", "content": LAST},
        ]
        writer, readback = s03_proof(one_turn)
        self.assertFalse(canonical_s03_proof_valid(writer, readback, DIALOG, one_turn))

    def test_canonical_s03_rejects_wrong_role_order_even_with_matching_receipt(self):
        malformed = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        malformed[1]["role"] = "user"
        writer, readback = s03_proof(malformed)
        self.assertFalse(canonical_s03_proof_valid(writer, readback, DIALOG, malformed))

    def test_default_russian_prompt_byte_equivalent(self):
        self.assertEqual(
            multiturn_followup_prompt(TOKEN, "multiturn"),
            f"[NOX UI QA {TOKEN}] Используя предыдущий ответ, перечисли "
            "те же числа в обратном порядке через запятую. Без пояснений.",
        )

    def test_spanish_opt_in_preserves_token_and_requests_previous_ru_answer(self):
        text = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        self.assertTrue(text.startswith(f"[NOX UI QA {TOKEN}] "))
        self.assertIn("respuesta a la pregunta anterior en ruso", text)
        self.assertIn("secuencia de números en orden inverso", text)
        self.assertNotEqual(text, multiturn_followup_prompt(TOKEN, "multiturn"))
        with self.assertRaisesRegex(RuntimeError, "HOLD_QA_LANGUAGE_MODE"):
            multiturn_followup_prompt(TOKEN, "es_es")

    def test_ru_es_requires_prior_randomized_russian_answer_not_rote_ten_to_one(self):
        challenge = ru_es_context_challenge(TOKEN)
        numbers = challenge.split(',')
        self.assertEqual(set(numbers), {str(i) for i in range(1, 11)})
        self.assertEqual(len(numbers), 10)
        self.assertNotEqual(challenge, FIRST)
        self.assertNotEqual(challenge, LAST)
        self.assertEqual(challenge, ru_es_context_challenge(TOKEN))
        self.assertNotEqual(challenge, ru_es_context_challenge('ghijk'))
        spanish = multiturn_followup_prompt(TOKEN, 'multiturn_ru_es')
        self.assertNotIn(challenge, spanish)
        reversed_answer = ','.join(reversed(numbers))
        self.assertNotIn(reversed_answer, spanish)
        self.assertTrue(multiturn_history_valid([
            {'role': 'user', 'content': 'RU first turn: '+challenge},
            {'role': 'assistant', 'content': challenge},
            {'role': 'user', 'content': spanish},
            {'role': 'assistant', 'content': reversed_answer},
        ], 'RU first turn: '+challenge, challenge, spanish, reversed_answer))
        self.assertFalse(multiturn_history_valid([
            {'role': 'user', 'content': 'RU first turn: '+challenge},
            {'role': 'assistant', 'content': FIRST},
            {'role': 'user', 'content': spanish},
            {'role': 'assistant', 'content': reversed_answer},
        ], 'RU first turn: '+challenge, challenge, spanish, reversed_answer))
        with self.assertRaisesRegex(RuntimeError, 'HOLD_QA_CHALLENGE_TOKEN'):
            ru_es_context_challenge('bad!token')

    def test_ru_es_unleaked_first_answer_drives_dynamic_second_turn(self):
        first_prompt = ru_es_unleaked_first_prompt(TOKEN)
        self.assertIn('Выбери самостоятельно', first_prompt)
        self.assertNotIn('2,7,4,9,1,10,3,8,6,5', first_prompt)
        first_answer = '2,7,4,9,1,10,3,8,6,5'
        self.assertTrue(ru_es_unleaked_first_answer_valid(first_answer))
        self.assertTrue(ru_es_unleaked_first_answer_valid('3,8,1,9,5,10,6,4,2,7'))
        for invalid in (FIRST, LAST, '1,1,3,4,5,6,7,8,9,10',
                        '1,2,3,4,5,6,7,8,9', '2,7,4,9,1,10,3,8,6,5,5',
                        '2,7,4,9,1,10,3,8,6,11', ''):
            self.assertFalse(ru_es_unleaked_first_answer_valid(invalid))
        spanish = multiturn_followup_prompt(TOKEN, 'multiturn_ru_es')
        expected_second = ','.join(reversed(first_answer.split(',')))
        self.assertNotIn(first_answer, spanish)
        self.assertNotIn(expected_second, spanish)
        self.assertTrue(multiturn_history_valid([
            {'role': 'user', 'content': first_prompt},
            {'role': 'assistant', 'content': first_answer},
            {'role': 'user', 'content': spanish},
            {'role': 'assistant', 'content': expected_second},
        ], first_prompt, first_answer, spanish, expected_second))
        self.assertFalse(multiturn_history_valid([
            {'role': 'user', 'content': first_prompt},
            {'role': 'assistant', 'content': FIRST},
            {'role': 'user', 'content': spanish},
            {'role': 'assistant', 'content': expected_second},
        ], first_prompt, first_answer, spanish, expected_second))

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
