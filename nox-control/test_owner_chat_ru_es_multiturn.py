"""B5 focused source contract: RU first-turn / Spanish follow-up, same S03 dialog.

No browser, native POST, live S03 or production host mutation. The historical
multiturn canonical-S03 HOLD remains mandatory until real writer/readback wiring.
"""
import asyncio
import hashlib
import json
import unittest
from unittest.mock import AsyncMock

from owner_chat_browser_qa import (
    allowed_qa_request,
    canonical_s03_proof_valid,
    click_send,
    firstturn_history_valid,
    empty_dialog_history_valid,
    multiturn_followup_prompt,
    ru_es_context_challenge,
    ru_es_unleaked_first_prompt,
    ru_es_unleaked_first_answer_valid,
    multiturn_history_valid,
    multiturn_transcript_sha256,
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
        "full_transcript_sha256": multiturn_transcript_sha256(transcript),
    }
    readback = {
        "source": "canonical_s03", "independent": True,
        "event_id": "evt-02", "turn_id": "turn-02", "sequence": 2,
        "dialog_id": DIALOG, "messages": transcript,
        "full_transcript_sha256": multiturn_transcript_sha256(transcript),
        "full_answer_sha256": hashlib.sha256(LAST.encode("utf-8")).hexdigest(),
    }
    return writer, readback


class OwnerRuEsContinuity(unittest.TestCase):
    def test_empty_history_scope_must_match_before_first_native_post(self):
        # An empty list from another dialog must not authorize the first POST.
        self.assertTrue(empty_dialog_history_valid(
            {"dialog_id": DIALOG, "messages": []}, DIALOG))
        self.assertTrue(empty_dialog_history_valid({"messages": []}, DIALOG))
        for value in (
            {"dialog_id": "another-session", "messages": []},
            {"dialog_id": None, "messages": []},
            {"dialog_id": "", "messages": []},
            {"messages": [{"role": "user", "content": "unexpected"}]},
            {"messages": None},
            {"messages": {}},
            [],
            None,
        ):
            with self.subTest(value=str(value)[:90]):
                self.assertFalse(empty_dialog_history_valid(value, DIALOG))
        self.assertFalse(empty_dialog_history_valid(
            {"messages": []}, None))
        self.assertFalse(empty_dialog_history_valid(
            {"messages": []}, "   "))

    def test_first_turn_history_requires_own_dialog_before_es_post(self):
        # The query string alone cannot authenticate a returned S03/history row.
        first = [
            {"role": "user", "content": RU, "dialog_id": DIALOG},
            {"role": "assistant", "content": FIRST, "dialog_id": DIALOG},
        ]
        self.assertTrue(firstturn_history_valid(
            {"dialog_id": DIALOG, "messages": first}, RU, FIRST, DIALOG))
        self.assertTrue(firstturn_history_valid(
            {"messages": [
                {"role": "user", "content": RU},
                {"role": "assistant", "content": FIRST},
            ]}, RU, FIRST, DIALOG))
        for tampered in (
            {"dialog_id": "other-dialog", "messages": first},
            {"dialog_id": None, "messages": first},
            {"messages": [dict(first[0], dialog_id="other-dialog"), first[1]]},
            {"messages": [first[0], dict(first[1], dialog_id=None)]},
            {"messages": [first[0], dict(first[1], content="")]},
            {"messages": [first[0], {"role": "assistant", "content": FIRST}, first[1]]},
            {"messages": [first[0], None]},
            {"messages": "not-a-turn-list"},
        ):
            with self.subTest(case=str(tampered)[:90]):
                self.assertFalse(firstturn_history_valid(tampered, RU, FIRST, DIALOG))
        self.assertFalse(firstturn_history_valid(
            {"messages": first}, RU, FIRST, None))
        self.assertFalse(firstturn_history_valid(
            {"messages": first}, RU, FIRST, "other-dialog"))

    def test_four_turn_fingerprint_binds_entire_untrimmed_ru_es_utf8_history(self):
        spanish = multiturn_followup_prompt(TOKEN, 'multiturn_ru_es')
        transcript = rows(spanish)
        transcript[0]['content'] += ' Привет'
        expected = hashlib.sha256(json.dumps(
            [{'role': item['role'], 'content': item['content']} for item in transcript],
            ensure_ascii=False, sort_keys=True, separators=(',', ':'),
            allow_nan=False).encode('utf-8')).hexdigest()
        self.assertEqual(multiturn_transcript_sha256(transcript), expected)
        self.assertEqual(len(expected), 64)
        for turn in range(4):
            altered = [dict(item) for item in transcript]
            altered[turn]['content'] += 'ñ' if turn == 2 else 'я'
            self.assertNotEqual(multiturn_transcript_sha256(altered), expected)
            invalid = [dict(item) for item in transcript]
            invalid[turn]['content'] = '  '
            self.assertIsNone(multiturn_transcript_sha256(invalid))
        self.assertIsNone(multiturn_transcript_sha256(transcript[:2]))
        self.assertIsNone(multiturn_transcript_sha256([*transcript[:3], None]))
        invalid_roles = [dict(item) for item in transcript]
        invalid_roles[2]['role'] = 'assistant'
        self.assertIsNone(multiturn_transcript_sha256(invalid_roles))

    def test_s03_full_history_sha_is_bound_to_both_native_witnesses(self):
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(
            {key: value for key, value in writer.items()
             if key != "full_transcript_sha256"}, readback, DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(
            writer, dict(readback, full_transcript_sha256="0" * 64),
            DIALOG, transcript))
        # Matching event ID and final answer cannot authenticate a different
        # previous Russian user/assistant exchange.
        forged = [dict(item) for item in transcript]
        forged[0]["content"] += " другой вопрос"
        forged[1]["content"] = "3,8,1,9,5,10,6,4,2,7"
        forged_readback = dict(
            readback, messages=forged,
            full_transcript_sha256=multiturn_transcript_sha256(forged))
        self.assertFalse(canonical_s03_proof_valid(
            writer, forged_readback, DIALOG, forged))

    def test_s03_explicit_null_history_pin_cannot_downgrade_to_legacy(self):
        # Missing BOTH digests is the pre-fingerprint legacy contract;
        # an explicit null must not silently opt into that compatibility path.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        old_writer = {k: v for k, v in writer.items()
                      if k != "full_transcript_sha256"}
        old_readback = {k: v for k, v in readback.items()
                        if k != "full_transcript_sha256"}
        self.assertTrue(canonical_s03_proof_valid(
            old_writer, old_readback, DIALOG, transcript))
        for bad_writer, bad_readback in (
            (dict(old_writer, full_transcript_sha256=None), old_readback),
            (old_writer, dict(old_readback, full_transcript_sha256=None)),
            (dict(old_writer, full_transcript_sha256=None),
             dict(old_readback, full_transcript_sha256=None)),
            (dict(writer, full_transcript_sha256=None), readback),
            (writer, dict(readback, full_transcript_sha256=None)),
            (dict(old_writer, full_transcript_sha256=""),
             dict(old_readback, full_transcript_sha256="")),
        ):
            with self.subTest(writer_pin=repr(bad_writer.get("full_transcript_sha256")),
                              readback_pin=repr(bad_readback.get("full_transcript_sha256"))):
                self.assertFalse(canonical_s03_proof_valid(
                    bad_writer, bad_readback, DIALOG, transcript))

    def test_s03_optional_writer_answer_digest_must_agree_with_fourth_turn(self):
        # A writer may optionally expose its own final-answer digest. If it
        # disagrees with the independently verified fourth message, HOLD.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        expected = readback["full_answer_sha256"]
        # Preserve old writer receipts, which remain source-only witnesses.
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        self.assertTrue(canonical_s03_proof_valid(
            dict(writer, full_answer_sha256=expected), readback, DIALOG, transcript))
        for wrong in ("0" * 64, None, ""):
            with self.subTest(writer_answer_digest=repr(wrong)):
                self.assertFalse(canonical_s03_proof_valid(
                    dict(writer, full_answer_sha256=wrong), readback, DIALOG, transcript))

    def test_s03_two_turn_receipt_requires_second_sequence_and_distinct_readback(self):
        # One first-turn writer receipt cannot prove a two-turn S03 persist.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        writer["sequence"] = 1
        readback["sequence"] = 1
        self.assertFalse(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        # A single, self-declared "independent" dict is not two read operations.
        writer["sequence"] = readback["sequence"] = 2
        aliased = {**writer, **readback}
        self.assertFalse(canonical_s03_proof_valid(aliased, aliased, DIALOG, transcript))
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))

    def test_canonical_s03_rejects_later_turn_or_blank_receipt_identity(self):
        # An event from a third or later turn cannot certify exactly two turns.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        for invalid_sequence in (3, 99, True, "2"):
            tampered_writer = dict(writer, sequence=invalid_sequence)
            tampered_readback = dict(readback, sequence=invalid_sequence)
            self.assertFalse(canonical_s03_proof_valid(
                tampered_writer, tampered_readback, DIALOG, transcript))
        for invalid_key in ("event_id", "turn_id"):
            tampered_writer = dict(writer, **{invalid_key: "  "})
            tampered_readback = dict(readback, **{invalid_key: "  "})
            self.assertFalse(canonical_s03_proof_valid(
                tampered_writer, tampered_readback, DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(
            dict(writer, dialog_id="  "), dict(readback, dialog_id="  "),
            "  ", transcript))
        empty_reply = [*transcript[:3], {"role": "assistant", "content": ""}]
        empty_writer, empty_readback = s03_proof(empty_reply)
        empty_readback["full_answer_sha256"] = hashlib.sha256(b"").hexdigest()
        self.assertFalse(canonical_s03_proof_valid(
            empty_writer, empty_readback, DIALOG, empty_reply))

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

    def test_four_turn_scope_rejects_cross_dialog_metadata_without_breaking_legacy_rows(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        transcript = rows(es)
        # The authenticated endpoint can return legacy rows without per-row scope.
        self.assertTrue(multiturn_history_valid(transcript, RU, FIRST, es, LAST, DIALOG))
        scoped = [dict(message, dialog_id=DIALOG) for message in transcript]
        self.assertTrue(multiturn_history_valid(scoped, RU, FIRST, es, LAST, DIALOG))
        for index in range(4):
            for invalid in ("other-dialog", "", None):
                with self.subTest(turn=index, invalid=repr(invalid)):
                    mixed = [dict(message) for message in scoped]
                    mixed[index]["dialog_id"] = invalid
                    self.assertFalse(multiturn_history_valid(
                        mixed, RU, FIRST, es, LAST, DIALOG))
        self.assertFalse(multiturn_history_valid(scoped, RU, FIRST, es, LAST, "  "))

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

    def test_second_turn_fails_closed_without_real_dialog_scope(self):
        # A missing/null request dialog ID must never become a matching
        # unscoped native POST just because expected dialog_id is also None.
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        valid = {"message": es, "dialog_id": DIALOG}
        self.assertTrue(allowed_qa_request(1, True, RU, es, valid, DIALOG))
        for missing_scope in (None, "", "   "):
            self.assertFalse(allowed_qa_request(
                1, True, RU, es, {"message": es}, missing_scope))
            self.assertFalse(allowed_qa_request(
                1, True, RU, es, {"message": es, "dialog_id": missing_scope},
                missing_scope))
        self.assertFalse(allowed_qa_request(
            1, True, RU, es, valid, "other-dialog"))

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


    def test_ambiguous_click_never_retries_native_first_or_second_turn(self):
        # A client click timeout may occur after DOM dispatch but before the
        # observable fetch counter advances. Do not submit a second click.
        class Target:
            async def evaluate(self, _):
                return {"in_view": True, "pointer_hit_own_button": True, "x": 40, "y": 40}

            async def click(self, timeout):
                raise TimeoutError("not stable")

        class Page:
            def __init__(self, calls):
                self.calls = calls
                self.mouse = type("Mouse", (), {"click": AsyncMock()})()

            def locator(self, _):
                return Target()

            async def evaluate(self, _):
                return {"native_calls": self.calls}

        for before in (0, 1):
            with self.subTest(turn=before + 1, outcome="unknown"):
                page, report = Page(before), {}
                with self.assertRaisesRegex(RuntimeError, "HOLD_QA_SEND_OUTCOME_UNKNOWN"):
                    asyncio.run(click_send(page, report, expected_before=before))
                page.mouse.click.assert_not_awaited()
                field = "qa_send_control" if before == 0 else "qa_second_send_control"
                self.assertTrue(report[field]["native_request_outcome_unknown"])
                self.assertEqual(report[field]["observed_native_calls"], before)
            with self.subTest(turn=before + 1, outcome="already-started"):
                page, report = Page(before + 1), {}
                asyncio.run(click_send(page, report, expected_before=before))
                page.mouse.click.assert_not_awaited()
                field = "qa_send_control" if before == 0 else "qa_second_send_control"
                self.assertTrue(report[field]["native_request_already_started"])


if __name__ == "__main__":
    unittest.main()
