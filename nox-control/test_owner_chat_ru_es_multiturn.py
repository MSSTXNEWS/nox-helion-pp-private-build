"""B5 focused source contract: RU first-turn / Spanish follow-up, same S03 dialog.

No browser, native POST, live S03 or production host mutation. The historical
multiturn canonical-S03 HOLD remains mandatory until real writer/readback wiring.
"""
import asyncio
import hashlib
import inspect
import json
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock

from owner_chat_browser_qa import (
    allowed_qa_request,
    allowed_qa_stream_url,
    native_chat_route_candidate,
    canonical_s03_proof_valid,
    click_send,
    firstturn_history_valid,
    firstturn_prefix_identity_valid,
    empty_dialog_history_valid,
    exact_native_post_fence,
    multiturn_followup_prompt,
    ru_es_context_challenge,
    ru_es_unleaked_first_prompt,
    ru_es_unleaked_first_answer_valid,
    multiturn_history_valid,
    multiturn_transcript_sha256,
    native_terminal_stream_valid,
    readback_evidence,
    browser_run,
    OBSERVER_JS,
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
    def test_two_turn_dialog_history_cannot_claim_canonical_s03_readback(self):
        # Even a perfect first-turn browser/history match is NOT a trusted
        # writer receipt plus an independently verified canonical S03 read.
        self.assertEqual(
            readback_evidence(True, True, True),
            {'dialog_history_readback_verified': True,
             's03_readback_verified': False})
        self.assertEqual(
            readback_evidence(True, True, False),
            {'dialog_history_readback_verified': True,
             's03_readback_verified': True})
        for saved, native in ((False, True), (True, False),
                              (None, True), (True, None),
                              (1, True), (True, 'true')):
            with self.subTest(saved=repr(saved), native=repr(native)):
                evidence = readback_evidence(saved, native, True)
                self.assertFalse(evidence['dialog_history_readback_verified'])
                self.assertFalse(evidence['s03_readback_verified'])
        # Verify this helper is actually used by the production browser
        # reporting path, rather than being an unconnected test-only helper.
        self.assertIn('**readback_evidence(saved, native_equal,', inspect.getsource(browser_run))

    def test_native_ndjson_rejects_truncated_utf8_eof_after_done(self):
        """Actual JS observer must flush fatal UTF-8 state at clean stream EOF.

        Without decoder.decode() at EOF, a dangling leading byte after DONE
        vanishes silently and the clone reports native_stream_complete=True.
        """
        if not shutil.which("node"):
            self.skipTest("Node required for byte-stream observer regression")
        driver = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const observer = fs.readFileSync(0, 'utf8');
async function check(chunks, status=200) {
  let index = 0;
  const reader = {
    read: async () => index < chunks.length
      ? {done: false, value: Uint8Array.from(chunks[index++])}
      : {done: true},
    cancel: async () => {}
  };
  const response = {
    status,
    body: {getReader: () => reader},
    clone() { return this; }
  };
  const win = {fetch: async () => response};
  class Canvas { getContext() { return null; } }
  const env = {
    window: win, HTMLCanvasElement: Canvas, TextDecoder, URL,
    Request: class Request {}, performance: {now: () => 25},
    location: {origin: 'http://qa.invalid', href: 'http://qa.invalid/'},
    document: {querySelectorAll: () => [], getElementById: () => null},
    addEventListener: () => {}, requestAnimationFrame: () => {}
  };
  vm.runInNewContext(observer, env);
  await win.fetch('http://qa.invalid/api/nox/chat/stream', {method:'POST'});
  await new Promise(resolve => setTimeout(resolve, 15));
  return win.__NOX_BROWSER_QA;
}
(async () => {
  const complete = Buffer.from('{"type":"delta","text":"ñ"}\\n{"type":"done","saved":true,"s03_integrated":true,"dialog_id":"synthetic"}\\n'.replaceAll('\\n', '\n'),'utf8');
  const needle = Buffer.from('ñ','utf8');
  const at = complete.indexOf(needle);
  assert.ok(at > 0);
  const split = await check([complete.subarray(0,at+1),complete.subarray(at+1)]);
  assert.equal(split.nativeStreamComplete,true,'split valid UTF-8 must pass');
  assert.equal(split.error,null);
  assert.equal(split.nativeTerminalCount,1);
  // A syntactically valid DONE in a native HTTP error response is NOT a
  // successful model turn and cannot certify S03 persistence.
  for (const status of [401, 403, 500, 503]) {
    const rejected = await check([complete], status);
    assert.equal(rejected.nativeStreamComplete,false,'non-200 must HOLD');
    assert.equal(rejected.error,'HOLD_QA_NATIVE_HTTP_STATUS');
    assert.equal(rejected.nativeTerminalCount,0);
  }
  const dangling = await check([complete,Buffer.from([0xc3])]);
  assert.equal(dangling.nativeStreamComplete,false,'dangling UTF-8 must HOLD');
  assert.equal(dangling.error,'HOLD_QA_STREAM_OBSERVER');
  // DONE must reject trailing blank frames and partial whitespace fragments.
  for (const chunks of [
    [complete, Buffer.from('\\n')],
    [Buffer.concat([complete,Buffer.from(' \\n')])],
    [Buffer.concat([complete,Buffer.from(' ')])]
  ]) {
    const extra = await check(chunks);
    assert.equal(extra.nativeStreamComplete,false,'trailing bytes must HOLD');
    assert.equal(extra.error,'HOLD_QA_TRAILING_AFTER_DONE');
  }
})().catch(error => {console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(
            ["node", "-e", driver],
            input=OBSERVER_JS.replace('__CONFIG__', '{"did":"synthetic"}'),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr[:1000])

    def test_native_stream_done_is_not_terminal_until_clean_eof_for_each_turn(self):
        complete = {"native_stream_complete": True, "native_terminal_count": 1,
                    "done": {"saved": True, "s03_integrated": True,
                             "dialog_matches": True}, "error": None}
        for turn in (1, 2):
            self.assertTrue(native_terminal_stream_valid(dict(complete,
                native_calls=turn)))
        for invalid in (
            dict(complete, native_stream_complete=False),
            dict(complete, native_stream_complete=None),
            dict(complete, native_terminal_count=0),
            dict(complete, native_terminal_count=2),
            dict(complete, native_terminal_count=1.0),
            dict(complete, native_terminal_count=True),
            dict(complete, error="HOLD_QA_TRAILING_AFTER_DONE"),
            dict(complete, error="HOLD_QA_STREAM_NOT_TERMINAL"),
            dict(complete, done=None),
        ):
            with self.subTest(case=str(invalid)[:90]):
                self.assertFalse(native_terminal_stream_valid(invalid))
        self.assertFalse(native_terminal_stream_valid(None))
        self.assertFalse(native_terminal_stream_valid({}))
        # The JS observer is the actual witness producer. Check its syntax on
        # CI (Node is on ubuntu-latest); no browser/model/network side effects.
        self.assertIn("HOLD_QA_TRAILING_AFTER_DONE", OBSERVER_JS)
        self.assertIn("HOLD_QA_STREAM_NOT_TERMINAL", OBSERVER_JS)
        self.assertIn("q.nativeStreamComplete=true", OBSERVER_JS)
        if shutil.which("node"):
            check = subprocess.run(["node", "--check", "-"],
                input=OBSERVER_JS.replace('__CONFIG__', '{"did":"synthetic"}'),
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=12, check=False)
            self.assertEqual(check.returncode, 0, check.stderr[:500])

    def test_native_done_requires_explicit_true_persistence_and_session_flags(self):
        """Terminal EOF alone cannot certify saved S03 or same RU-ES dialog."""
        complete = {
            "native_stream_complete": True, "native_terminal_count": 1,
            "error": None,
            "done": {"saved": True, "s03_integrated": True,
                     "dialog_matches": True},
        }
        self.assertTrue(native_terminal_stream_valid(complete))
        for done in ({}, {"saved": True},
                     {"saved": True, "s03_integrated": True},
                     {"saved": True, "s03_integrated": True,
                      "dialog_matches": False},
                     {"saved": 1, "s03_integrated": True,
                      "dialog_matches": True},
                     {"saved": True, "s03_integrated": "true",
                      "dialog_matches": True},
                     {"saved": True, "s03_integrated": True,
                      "dialog_matches": None}):
            with self.subTest(done=done):
                self.assertFalse(native_terminal_stream_valid(dict(complete, done=done)))

    def test_canonical_s03_four_rows_are_bound_to_own_dialog(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        legacy = rows(es)
        writer, readback = s03_proof(legacy)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, legacy))
        scoped = [dict(row, dialog_id=DIALOG) for row in legacy]
        writer, readback = s03_proof(scoped)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, scoped))
        for wrong_scope in ("foreign-dialog", None, "", 17):
            for row_index in range(4):
                with self.subTest(row=row_index, scope=repr(wrong_scope)):
                    forged = [dict(row) for row in scoped]
                    forged[row_index]["dialog_id"] = wrong_scope
                    writer, readback = s03_proof(forged)
                    self.assertFalse(canonical_s03_proof_valid(
                        writer, readback, DIALOG, forged))

    def test_explicit_message_ids_do_not_replay_one_row_as_multiple_ru_es_turns(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        legacy = rows(es)
        self.assertTrue(multiturn_history_valid(
            legacy, RU, FIRST, es, LAST, dialog_id=DIALOG))
        unique = [dict(row, message_id=f"msg-{i}") for i, row in enumerate(legacy)]
        self.assertTrue(firstturn_history_valid(
            {"dialog_id": DIALOG, "messages": unique[:2]}, RU, FIRST, DIALOG))
        self.assertTrue(multiturn_history_valid(
            unique, RU, FIRST, es, LAST, dialog_id=DIALOG))
        writer, independent = s03_proof(unique)
        self.assertTrue(canonical_s03_proof_valid(
            writer, independent, DIALOG, unique))
        duplicate_first = [dict(row) for row in unique[:2]]
        duplicate_first[1]["message_id"] = duplicate_first[0]["message_id"]
        self.assertFalse(firstturn_history_valid(
            {"messages": duplicate_first}, RU, FIRST, DIALOG))
        for malformed in ("msg-1", None, "", " ", 7, True):
            with self.subTest(message_id=repr(malformed)):
                changed = [dict(row) for row in unique]
                changed[2]["message_id"] = malformed
                self.assertFalse(multiturn_history_valid(
                    changed, RU, FIRST, es, LAST, dialog_id=DIALOG))
                writer, independent = s03_proof(changed)
                self.assertFalse(canonical_s03_proof_valid(
                    writer, independent, DIALOG, changed))

    def test_firstturn_message_ids_survive_spanish_followup_readback(self):
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        final_rows = [
            dict(row, message_id=f"turn-{i}") for i, row in enumerate(rows(es))
        ]
        initial_ids = ("turn-0", "turn-1")
        self.assertTrue(firstturn_prefix_identity_valid(initial_ids, final_rows))
        self.assertTrue(multiturn_history_valid(
            final_rows, RU, FIRST, es, LAST, dialog_id=DIALOG))

        # The preexisting four-row checker accepts matching role/text despite
        # history-row replacement. The new second-read fence must reject it.
        for row_index in (0, 1):
            for changed_id in (f"rewritten-{row_index}", None, "", 19):
                with self.subTest(row=row_index, changed_id=repr(changed_id)):
                    replaced = [dict(row) for row in final_rows]
                    if changed_id is None:
                        replaced[row_index].pop("message_id")
                    else:
                        replaced[row_index]["message_id"] = changed_id
                    self.assertFalse(firstturn_prefix_identity_valid(
                        initial_ids, replaced))
                    if isinstance(changed_id, str) and changed_id:
                        self.assertTrue(multiturn_history_valid(
                            replaced, RU, FIRST, es, LAST, dialog_id=DIALOG))

        # Legacy first-turn history without IDs remains usable, even when
        # durable IDs appear in the second read. Explicit malformed source
        # snapshots or malformed final history fail closed.
        self.assertTrue(firstturn_prefix_identity_valid(
            (None, None), final_rows))
        self.assertFalse(firstturn_prefix_identity_valid(
            ("", "turn-1"), final_rows))
        self.assertFalse(firstturn_prefix_identity_valid(
            ["turn-0", "turn-1"], final_rows))
        self.assertFalse(firstturn_prefix_identity_valid(
            initial_ids, final_rows[:2]))

    def test_two_turn_native_post_accounting_fences_before_s03_proof(self):
        for turn in (1, 2):
            self.assertTrue(exact_native_post_fence(
                {'native_calls': turn}, turn, turn))
            # Either the browser observer or the owner guard may be stale:
            # neither witness by itself is sufficient to admit the turn.
            for observed, admitted in ((turn + 1, turn), (turn, turn + 1),
                                       (turn - 1, turn), (turn, turn - 1)):
                with self.subTest(turn=turn, observed=observed, admitted=admitted):
                    self.assertFalse(exact_native_post_fence(
                        {'native_calls': observed}, admitted, turn))
            for malformed in (True, float(turn), str(turn), None, [], {}):
                with self.subTest(turn=turn, malformed=repr(malformed)):
                    self.assertFalse(exact_native_post_fence(
                        {'native_calls': malformed}, turn, turn))
                    self.assertFalse(exact_native_post_fence(
                        {'native_calls': turn}, malformed, turn))
        self.assertFalse(exact_native_post_fence({}, 1, 1))
        self.assertFalse(exact_native_post_fence(None, 1, 1))
        self.assertFalse(exact_native_post_fence({'native_calls': 3}, 3, 3))

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

    def test_s03_unpinned_legacy_witness_cannot_certify_four_turns(self):
        # Neither omitted nor explicitly null history pins can prove two turns.
        # Old last-answer-only receipts may match after earlier turns changed.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        old_writer = {k: v for k, v in writer.items()
                      if k != "full_transcript_sha256"}
        old_readback = {k: v for k, v in readback.items()
                        if k != "full_transcript_sha256"}
        self.assertFalse(canonical_s03_proof_valid(
            old_writer, old_readback, DIALOG, transcript,
            require_full_transcript_pin=True))
        # The legacy A1 helper remains source-compatible, not B5-accepted.
        self.assertTrue(canonical_s03_proof_valid(
            old_writer, old_readback, DIALOG, transcript))
        changed_earlier_turns = [dict(row) for row in transcript]
        changed_earlier_turns[0]['content'] += ' другой вопрос'
        changed_earlier_turns[1]['content'] = '3,8,1,9,5,10,6,4,2,7'
        stale_last_answer_readback = dict(
            old_readback, messages=changed_earlier_turns)
        # Both receipts still agree on event, dialog, sequence, final answer.
        # That is insufficient to certify changed previous conversation turns.
        self.assertFalse(canonical_s03_proof_valid(
            old_writer, stale_last_answer_readback,
            DIALOG, changed_earlier_turns, require_full_transcript_pin=True))
        self.assertTrue(canonical_s03_proof_valid(
            writer, readback, DIALOG, transcript, require_full_transcript_pin=True))
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

    def test_canonical_s03_readback_sequence_requires_exact_int(self):
        # JSON 2.0 compares equal to Python int 2, but is not a valid
        # canonical integer turn index in an independent S03 readback.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        for bad_sequence in (2.0, True, "2", None, [2], 3):
            with self.subTest(readback_sequence=repr(bad_sequence)):
                self.assertFalse(canonical_s03_proof_valid(
                    writer, dict(readback, sequence=bad_sequence),
                    DIALOG, transcript))
        self.assertTrue(canonical_s03_proof_valid(
            writer, dict(readback, sequence=2), DIALOG, transcript))

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

    def test_alternate_native_chat_wire_cannot_bypass_ru_es_post_fence(self):
        # All recognized native chat aliases must HOLD before the network.
        self.assertTrue(native_chat_route_candidate('/api/nox/chat/stream'))
        for path in ('/api/nox/chat', '/api/nox/chat/',
                     '/api/nox/chat/completions',
                     '/api/nox/chat/stream/', '/api/nox/chat/stream-v2',
                     '/api/nox/chat%2Fstream', '/api/nox/chat%5cstream'):
            with self.subTest(path=path):
                self.assertTrue(native_chat_route_candidate(path))
                self.assertNotEqual(path, '/api/nox/chat/stream')
        for path in ('/api/nox/chatter', '/api/ui/memory/dialogs/history',
                     '/api/nox/status', '/chat/session', None):
            self.assertFalse(native_chat_route_candidate(path))
        guard = inspect.getsource(browser_run)
        self.assertIn('if native_chat_route_candidate(url.path):', guard)
        self.assertIn("blocked['alternate_native_chat_route']+=1", guard)
        self.assertIn("if url.path != '/api/nox/chat/stream':", guard)
        self.assertIn('allowed_qa_stream_url(request.url, origin)', guard)
        self.assertIn('allowed_qa_request(', guard)

    def test_stream_url_query_cannot_override_native_model_or_history(self):
        # The browser's real route is a plain path. JSON-body admission alone
        # is insufficient if the request URL carries alternate query metadata.
        origin = 'owner.example:18775'
        endpoint = 'https://' + origin + '/api/nox/chat/stream'
        self.assertTrue(allowed_qa_stream_url(endpoint, origin))
        self.assertTrue(allowed_qa_stream_url('http://' + origin + '/api/nox/chat/stream', origin))
        for url in (
            endpoint + '?model=foreign-model',
            endpoint + '?history=%5B%5D',
            endpoint + '?dialog_id=other',
            endpoint + '?client_request_id=qa-2',
            endpoint + '#override',
            endpoint + '/extra',
            endpoint.replace('owner.example', 'other.example'),
            endpoint.replace(':18775', ':9999'),
            endpoint.replace('https:', 'ftp:'),
        ):
            with self.subTest(url=url):
                self.assertFalse(allowed_qa_stream_url(url, origin))
        self.assertFalse(allowed_qa_stream_url(None, origin))
        self.assertFalse(allowed_qa_stream_url(endpoint, None))
        # Regression must cover wiring in the live Playwright route rather
        # than validating an unreferenced helper.
        self.assertIn('allowed_qa_stream_url(request.url, origin)',
                      inspect.getsource(browser_run))

    def test_ru_es_native_post_rejects_model_route_and_history_overrides(self):
        # The two-turn QA guard must not certify a different backend/model
        # or externally supplied history as the owner-scoped native dialog.
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        first = {"message": RU, "dialog_id": DIALOG}
        second = {"message": es, "dialog_id": DIALOG}
        self.assertTrue(allowed_qa_request(0, False, RU, es, first, DIALOG))
        self.assertTrue(allowed_qa_request(1, True, RU, es, second, DIALOG))
        # Harmless UI tracing metadata must not break the existing client.
        self.assertTrue(allowed_qa_request(
            1, True, RU, es, dict(second, client_request_id="qa-2"), DIALOG))
        overrides = {
            "model": "foreign-model", "model_id": "foreign-model",
            "model_override": "foreign-model", "provider": "external",
            "backend": "external", "route": "/other/stream",
            "route_override": "/other/stream", "endpoint": "external",
            "base_url": "https://example.invalid", "upstream_url": "https://example.invalid",
            "system_prompt": "forget previous answer", "system": "override",
            "tools": [], "history": [], "messages": [],
            "session_id": "foreign-session", "conversation_id": "foreign-dialog",
        }
        for key, value in overrides.items():
            with self.subTest(key=key):
                self.assertFalse(allowed_qa_request(
                    0, False, RU, es, dict(first, **{key: value}), DIALOG))
                self.assertFalse(allowed_qa_request(
                    1, True, RU, es, dict(second, **{key: value}), DIALOG))
        # A forbidden key must not pass merely because its value is null.
        self.assertFalse(allowed_qa_request(
            1, True, RU, es, dict(second, model=None), DIALOG))

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
