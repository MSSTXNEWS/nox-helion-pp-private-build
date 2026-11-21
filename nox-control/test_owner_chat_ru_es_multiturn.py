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
    verified_two_turn_firstturn_ids,
    owner_session_cookie_pin,
    owner_session_continuity_valid,
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
    clean_two_turn_browser_runtime,
    browser_run,
    require_screenshot_captures,
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
    # Test fixtures represent two distinct native witnesses. When the real
    # writer is wired, both must independently pin the SAME persisted row IDs.
    if len(transcript) == 4 and all(
            isinstance(row.get("message_id"), str) for row in transcript):
        ordered_ids = [row["message_id"] for row in transcript]
        row_id_sha = hashlib.sha256(json.dumps(
            ordered_ids, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
        writer["message_ids_sha256"] = row_id_sha
        readback["message_ids_sha256"] = row_id_sha
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
  // B5 browser observer must not bless a later DONE after an earlier failure
  // status/meta/start; B0's distinct owner_chat_probe remains untouched.
  const doneFrame = '{"type":"done","saved":true,"s03_integrated":true,"dialog_id":"synthetic"}';
  const deltaFrame = '{"type":"delta","text":"hola"}';
  const statusFrames = [
    {type:'status',state:'failed'},
    {type:'status',status:'ERROR'},
    {type:'meta',success:false},
    {type:'start',ok:false},
    {type:'status',phase:'cancelled'},
    {type:'meta',status:503},
    {type:'meta',error:{code:'failure'}},
    {type:'done',saved:true,s03_integrated:true,dialog_id:'synthetic',success:false},
    // A failing delta or extension frame cannot be rescued by later DONE.
    {type:'delta',text:'hola',state:'failed'},
    {type:'delta',text:'hola',status:503},
    {type:'delta',text:'hola',error:{code:'upstream_failed'}},
    {type:'extension',status:'cancelled'},
    // Provider status codes may be strings, and state strings can be padded.
    {type:'status',state:' FAILED '},
    {type:'delta',status:'503',text:'hola'},
    {type:'meta',status:' 429 '},
    {type:'extension',phase:' Cancelled '},
    {type:'done',status:'504',saved:true,s03_integrated:true,dialog_id:'synthetic'},
    // Structured HTTP failures must never be cleared by a later DONE.
    {type:'meta',code:503},
    {type:'delta',text:'hola',status_code:' 503 '},
    {type:'status',status:{code:502}},
    {type:'extension',httpStatus:429},
    {type:'meta',status:{statusCode:' 504 '}},
    {type:'done',statusCode:503,saved:true,s03_integrated:true,dialog_id:'synthetic'},
  ];
  for (const poison of statusFrames) {
    const payload = Buffer.from([deltaFrame,JSON.stringify(poison),doneFrame].join('\n')+'\n','utf8');
    const rejected = await check([payload]);
    assert.equal(rejected.nativeStreamComplete,false,'failed status cannot be accepted');
    assert.equal(rejected.error,'HOLD_QA_PRETERMINAL_FAILURE_STATUS');
  }
  const cleanStatus = Buffer.from([
    deltaFrame, '{"type":"delta","text":"mundo","state":"running"}',
    '{"type":"status","state":"running","status":{"code":200}}',
    '{"type":"delta","text":"bien","status_code":"200"}',doneFrame
  ].join('\n')+'\n','utf8');
  const permitted = await check([cleanStatus]);
  assert.equal(permitted.nativeStreamComplete,true,'running status remains compatible');
  assert.equal(permitted.error,null);
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

    def test_second_ru_es_post_needs_two_persisted_firstturn_identities(self):
        # Matching role/text without two durable identities cannot admit POST 2.
        first = [
            {"role": "user", "content": RU, "message_id": "s03-row-01"},
            {"role": "assistant", "content": FIRST, "message_id": "s03-row-02"},
        ]
        self.assertEqual(verified_two_turn_firstturn_ids(first),
                         ("s03-row-01", "s03-row-02"))
        for invalid in (
            [{k: v for k, v in item.items() if k != "message_id"} for item in first],
            [dict(first[0]), dict(first[1], message_id="s03-row-01")],
            [dict(first[0]), dict(first[1], message_id=" s03-row-01 ")],
            [dict(first[0]), dict(first[1], message_id="s03-row-02 ")],
            [dict(first[0]), dict(first[1], message_id="")],
            [dict(first[0]), dict(first[1], message_id=None)],
            [dict(first[0]), dict(first[1], message_id=123)],
            first[:1],
            None,
        ):
            with self.subTest(rows=repr(invalid)):
                self.assertIsNone(verified_two_turn_firstturn_ids(invalid))
        caller = inspect.getsource(browser_run)
        self.assertIn('firstturn_id_snapshot=verified_two_turn_firstturn_ids(rows)', caller)
        self.assertIn('HOLD_MULTITURN_FIRSTTURN_IDS_NOT_PERSISTED', caller)
        self.assertLess(
            caller.index('firstturn_id_snapshot=verified_two_turn_firstturn_ids(rows)'),
            caller.index('second_permitted=True'))

    def test_presecond_owner_session_cookie_pin_rejects_rotation(self):
        # Login 200 is insufficient if a different authenticated browser
        # session replaces the first-turn cookie before the Spanish POST.
        original = [dict(name='nox_owner', domain='owner.example', path='/',
                         value='signed-session-1', httpOnly=True)]
        pin = owner_session_cookie_pin(original)
        self.assertIsInstance(pin, str)
        self.assertEqual(len(pin), 64)
        ui = dict(name='theme', domain='owner.example', path='/',
                  value='dark', httpOnly=False)
        self.assertEqual(owner_session_cookie_pin([ui, *original]), pin)
        for changed in (
            [],
            [dict(original[0], value='signed-session-2')],
            [dict(original[0], name='other-owner')],
            [dict(original[0], path='/other')],
            [dict(original[0], value='')],
            [dict(original[0]), dict(original[0])],
        ):
            with self.subTest(case=repr(changed)[:60]):
                self.assertNotEqual(owner_session_cookie_pin(changed), pin)
        self.assertIsNone(owner_session_cookie_pin([]))
        self.assertIsNone(owner_session_cookie_pin(None))
        caller = inspect.getsource(browser_run)
        self.assertIn("signed_again=await context.request.get(", caller)
        self.assertIn("HOLD_MULTITURN_OWNER_SESSION_CHANGED", caller)
        self.assertLess(caller.index("owner_session_pin=owner_session_cookie_pin("),
                        caller.index("firstturn_id_snapshot=verified_two_turn_firstturn_ids(rows)"))
        self.assertLess(caller.index("HOLD_MULTITURN_OWNER_SESSION_CHANGED"),
                        caller.index("second_permitted=True"))

    def test_postsecond_owner_session_pin_precedes_four_row_history_readback(self):
        owner = [dict(name='nox_owner', domain='owner.example', path='/',
                      value='original-signed-session', httpOnly=True)]
        pin = owner_session_cookie_pin(owner)
        self.assertTrue(owner_session_continuity_valid(200, owner, pin))
        for status, cookies in (
            (401, owner), (302, owner), (True, owner), (None, owner),
            (200, []), (200, [dict(owner[0], value='new-owner-session')]),
            (200, [dict(owner[0], path='/another')]),
        ):
            with self.subTest(status=status, cookies=repr(cookies)[:30]):
                self.assertFalse(owner_session_continuity_valid(status, cookies, pin))
        self.assertFalse(owner_session_continuity_valid(200, owner, None))
        caller = inspect.getsource(browser_run)
        self.assertEqual(caller.count('owner_session_continuity_valid('), 3)
        self.assertIn("signed_after_second=await context.request.get(", caller)
        self.assertIn("multiturn_postsecond_owner_session_verified", caller)
        self.assertLess(caller.index("signed_after_second=await context.request.get("),
                        caller.index("second_history=await json_response("))
        self.assertLess(caller.index("multiturn_postsecond_owner_session_verified"),
                        caller.index("second_history=await json_response("))
        self.assertLess(caller.index("signed_after_second=await context.request.get("),
                        caller.index("multiturn_browser_acceptance_verified"))

    def test_preacceptance_ru_es_owner_session_after_second_screenshot(self):
        # A 200 identity check before history cannot pin the owner through
        # potentially slow private screenshot capture.
        original = [dict(name='nox_owner', domain='owner.example', path='/',
                         value='signed-before-screenshot', httpOnly=True)]
        pin = owner_session_cookie_pin(original)
        self.assertTrue(owner_session_continuity_valid(200, original, pin))
        for status, cookies in (
            (401, original), (302, original),
            (200, [dict(original[0], value='rotated-during-screenshot')]),
            (200, [dict(original[0], path='/changed')]),
        ):
            with self.subTest(status=status):
                self.assertFalse(owner_session_continuity_valid(status, cookies, pin))
        caller = inspect.getsource(browser_run)
        self.assertIn("signed_precert=await context.request.get(", caller)
        self.assertIn("multiturn_precert_owner_session_verified", caller)
        self.assertIn("HOLD_MULTITURN_OWNER_SESSION_CHANGED_BEFORE_ACCEPTANCE", caller)
        screenshot = caller.index("second_capture=await capture_private_screenshot(")
        session = caller.index("signed_precert=await context.request.get(")
        runtime = caller.index("if not clean_two_turn_browser_runtime(")
        accepted = caller.index("report['multiturn_browser_acceptance_verified']=True")
        self.assertLess(screenshot, session)
        self.assertLess(session, runtime)
        self.assertLess(runtime, accepted)

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
        transcript = [dict(row, message_id=f"s03-{i}") for i, row in enumerate(
            rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es")))]
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

    def test_strict_s03_requires_four_distinct_persisted_message_identities(self):
        # Exact four role/text bytes and full SHA pins still cannot certify that
        # S03 read four individually identified durable messages.
        transcript = rows(multiturn_followup_prompt(TOKEN, "multiturn_ru_es"))
        writer, readback = s03_proof(transcript)
        self.assertTrue(canonical_s03_proof_valid(writer, readback, DIALOG, transcript))
        self.assertFalse(canonical_s03_proof_valid(
            writer, readback, DIALOG, transcript, require_full_transcript_pin=True))

        identified = [dict(row, message_id=f"s03-{i}") for i, row in enumerate(transcript)]
        writer, readback = s03_proof(identified)
        self.assertTrue(canonical_s03_proof_valid(
            writer, readback, DIALOG, identified, require_full_transcript_pin=True))
        for invalid in (None, "", " ", 42, True):
            with self.subTest(missing_or_malformed=repr(invalid)):
                changed = [dict(row) for row in identified]
                changed[2]["message_id"] = invalid
                a, b = s03_proof(changed)
                self.assertFalse(canonical_s03_proof_valid(
                    a, b, DIALOG, changed, require_full_transcript_pin=True))
        for missing in range(4):
            changed = [dict(row) for row in identified]
            del changed[missing]["message_id"]
            a, b = s03_proof(changed)
            self.assertFalse(canonical_s03_proof_valid(
                a, b, DIALOG, changed, require_full_transcript_pin=True))
        whitespace_collision = [dict(row) for row in identified]
        whitespace_collision[1]["message_id"] = "s03-0 "
        a, b = s03_proof(whitespace_collision)
        self.assertFalse(canonical_s03_proof_valid(
            a, b, DIALOG, whitespace_collision, require_full_transcript_pin=True))

    def test_strict_s03_writer_and_reader_bind_ordered_persisted_row_ids(self):
        # Identical four message texts cannot prove the same four durable S03
        # rows: a later writer may have replaced rows without changing text.
        identified = [dict(row, message_id=f"durable-{i}")
                      for i, row in enumerate(rows(multiturn_followup_prompt(
                          TOKEN, "multiturn_ru_es")))]
        writer, readback = s03_proof(identified)
        self.assertTrue(canonical_s03_proof_valid(
            writer, readback, DIALOG, identified,
            require_full_transcript_pin=True))
        for missing_side in ("writer", "readback"):
            with self.subTest(side=missing_side):
                w, r = dict(writer), dict(readback)
                (w if missing_side == "writer" else r).pop("message_ids_sha256")
                self.assertFalse(canonical_s03_proof_valid(
                    w, r, DIALOG, identified,
                    require_full_transcript_pin=True))
        for invalid in (None, "", "0" * 64):
            with self.subTest(pin=repr(invalid)):
                self.assertFalse(canonical_s03_proof_valid(
                    dict(writer, message_ids_sha256=invalid),
                    readback, DIALOG, identified,
                    require_full_transcript_pin=True))
                self.assertFalse(canonical_s03_proof_valid(
                    writer, dict(readback, message_ids_sha256=invalid),
                    DIALOG, identified, require_full_transcript_pin=True))
        replaced = [dict(row) for row in identified]
        replaced[0]["message_id"] = "replacement-0"
        self.assertEqual(multiturn_transcript_sha256(replaced),
                         multiturn_transcript_sha256(identified))
        stale_writer_readback = dict(
            readback, messages=replaced, message_ids_sha256=hashlib.sha256(
                json.dumps([row["message_id"] for row in replaced],
                           ensure_ascii=False, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")).hexdigest())
        self.assertFalse(canonical_s03_proof_valid(
            writer, stale_writer_readback, DIALOG, replaced,
            require_full_transcript_pin=True))
        # The existing A1 helper intentionally keeps its legacy source contract.
        self.assertTrue(canonical_s03_proof_valid(
            writer, readback, DIALOG, identified))

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

    def test_encoded_earlier_chat_segments_cannot_escape_native_post_accounting(self):
        # urlsplit.path is still encoded; a reverse proxy can decode earlier
        # segments before routing. Such aliases must hit the abort path,
        # never bypass the exact one-POST-per-turn /api/nox/chat/stream gate.
        aliases = (
            '/api/nox/%63hat/stream',
            '/api/%6eox/chat/stream',
            '/%61pi/nox/chat/stream',
            '/%2Fapi/nox/chat/stream',
            '/api/nox/%2563hat/stream',
            '/api/nox/chat%2Fstream',
            '/api/nox/%63hat/completions',
        )
        for path in aliases:
            with self.subTest(path=path):
                self.assertTrue(native_chat_route_candidate(path))
                self.assertNotEqual(path, '/api/nox/chat/stream')
        for ordinary in ('/api/nox/%63hatter', '/api/%6eox/status',
                         '/api/ui/memory/dialogs/history',
                         '/nox-web-v29/pc/owner-chat-ui.js'):
            with self.subTest(ordinary=ordinary):
                self.assertFalse(native_chat_route_candidate(ordinary))
        guard = inspect.getsource(browser_run)
        self.assertIn('if native_chat_route_candidate(url.path):', guard)
        self.assertIn("if url.path != '/api/nox/chat/stream':", guard)
        self.assertIn("blocked['alternate_native_chat_route']+=1", guard)

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

    def test_two_turn_browser_receipt_separate_from_unwired_s03(self):
        """A three-shot browser witness must not imply native S03 acceptance."""
        captures = [{"stage": "empty", "state": "CAPTURED"},
                    {"stage": "completed", "state": "CAPTURED"}]
        single = {"two_turn_mode": False, "screenshot_captures": list(captures)}
        require_screenshot_captures(single)
        self.assertTrue(single["screenshot_capture_verified"])
        incomplete = {"two_turn_mode": True, "screenshot_captures": list(captures)}
        with self.assertRaisesRegex(RuntimeError, "HOLD_SCREENSHOT_CAPTURE_PENDING"):
            require_screenshot_captures(incomplete)
        self.assertFalse(incomplete["screenshot_capture_verified"])
        for extra in ({"stage": "second_turn", "state": "CAPTURE_TIMEOUT"},
                      {"stage": "completed", "state": "CAPTURED"}):
            invalid = {"two_turn_mode": True, "screenshot_captures": captures + [extra]}
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(RuntimeError, "HOLD_SCREENSHOT_CAPTURE_PENDING"):
                    require_screenshot_captures(invalid)
        complete = {"two_turn_mode": True, "screenshot_captures": captures + [
            {"stage": "second_turn", "state": "CAPTURED"}]}
        require_screenshot_captures(complete)
        self.assertTrue(complete["screenshot_capture_verified"])
        source = inspect.getsource(browser_run)
        self.assertIn("QA_SECOND_TURN_PRIVATE_SCREENSHOT", source)
        self.assertIn("HOLD_MULTITURN_SCREENSHOT_CAPTURE_PENDING", source)
        self.assertLess(source.index("HOLD_MULTITURN_BROWSER"),
                        source.index("QA_SECOND_TURN_PRIVATE_SCREENSHOT"))
        self.assertLess(source.index("QA_SECOND_TURN_PRIVATE_SCREENSHOT"),
                        source.index("multiturn_browser_acceptance_verified"))
        self.assertLess(source.index("require_screenshot_captures(report)"),
                        source.index("multiturn_browser_acceptance_verified"))
        self.assertLess(source.index("multiturn_browser_acceptance_verified"),
                        source.index("HOLD_CANONICAL_S03_RECEIPT_AND_INDEPENDENT_READBACK"))
        self.assertIn("canonical_s03_verified=False", source)

    def test_ru_es_browser_pass_fences_js_and_critical_static_failures_before_s03_hold(self):
        """Partial two-turn browser PASS is not valid with JS or failed JS/CSS."""
        healthy = [{'path': '/nox.js', 'status': 200, 'resource_type': 'script'},
                   {'path': '/nox.css', 'status': 304, 'resource_type': 'stylesheet'},
                   {'path': '/missing-image', 'status': 404, 'resource_type': 'image'}]
        self.assertTrue(clean_two_turn_browser_runtime([], healthy))
        self.assertTrue(clean_two_turn_browser_runtime([], []))
        rejected = [
            ([{'category': 'TypeError'}], healthy),
            ([], healthy + [{'status': 404, 'resource_type': 'script'}]),
            ([], healthy + [{'status': 503, 'resource_type': 'stylesheet'}]),
            ([], healthy + [{'status': None, 'resource_type': 'script'}]),
            ([], healthy + [{'status': True, 'resource_type': 'script'}]),
            (None, healthy), ([], None), ([], [None])
        ]
        for page_errors, network in rejected:
            with self.subTest(page_errors=page_errors, network=network):
                self.assertFalse(clean_two_turn_browser_runtime(page_errors, network))
        caller = inspect.getsource(browser_run)
        fence = "if not clean_two_turn_browser_runtime("
        self.assertIn(fence, caller)
        self.assertIn("page_errors, network, report[\'network_response_overflow_count\']", caller)
        self.assertIn("report['critical_requestfailed_count']", caller)
        self.assertLess(caller.index(fence),
                        caller.index("report['multiturn_browser_acceptance_verified']=True"))
        self.assertLess(caller.index(fence),
                        caller.index("HOLD_CANONICAL_S03_RECEIPT_AND_INDEPENDENT_READBACK"))

    def test_ru_es_network_observation_overflow_cannot_certify_browser_pass(self):
        """A bounded network log cannot certify responses it silently omitted."""
        seen = [{'path': '/nox.js', 'status': 200, 'resource_type': 'script'}]
        self.assertTrue(clean_two_turn_browser_runtime([], seen, 0))
        for dropped in (1, 250, -1, None, True, False, "0", 0.0):
            with self.subTest(dropped=repr(dropped)):
                self.assertFalse(clean_two_turn_browser_runtime([], seen, dropped))
        # Keep reports bounded, but count every omitted response and invalidate
        # narrow browser-only PASS before the mandatory canonical-S03 HOLD.
        caller = inspect.getsource(browser_run)
        self.assertIn("report['network_response_overflow_count']=0", caller)
        self.assertIn("report['network_response_overflow_count']+=1", caller)
        self.assertIn("page_errors, network, report['network_response_overflow_count']", caller)
        self.assertLess(caller.index("network_response_overflow_count']+=1"),
                        caller.index("multiturn_browser_acceptance_verified"))

    def test_ru_es_requestfailed_critical_resources_cannot_certify_browser_pass(self):
        """Critical script/css transport errors can have no HTTP response event."""
        healthy = [{'status': 200, 'resource_type': 'script'},
                   {'status': 304, 'resource_type': 'stylesheet'},
                   {'status': 404, 'resource_type': 'image'}]
        self.assertTrue(clean_two_turn_browser_runtime([], healthy, 0, 0))
        self.assertTrue(clean_two_turn_browser_runtime([], [], 0, 0))
        for count in (1, 2, -1, None, True, False, "0", 0.0):
            with self.subTest(critical_requestfailed_count=repr(count)):
                self.assertFalse(clean_two_turn_browser_runtime([], healthy, 0, count))
        caller = inspect.getsource(browser_run)
        self.assertIn("page.on('requestfailed',on_request_failed)", caller)
        self.assertIn("request.resource_type in ('script', 'stylesheet')", caller)
        self.assertIn("report['critical_requestfailed_count']+=1", caller)
        self.assertIn("report['critical_requestfailed_count']=0", caller)
        self.assertLess(caller.index("page.on('requestfailed',on_request_failed)"),
                        caller.index("multiturn_browser_acceptance_verified"))
        self.assertLess(caller.index("report['critical_requestfailed_count']+=1"),
                        caller.index("multiturn_browser_acceptance_verified"))
        self.assertLess(caller.index("report['critical_requestfailed_count'],"),
                        caller.index("multiturn_browser_acceptance_verified"))

    def test_ru_es_extra_blocked_native_posts_invalidate_browser_acceptance(self):
        """Two admitted POSTs alone cannot hide a third/alternate blocked attempt."""
        healthy = [{'status': 200, 'resource_type': 'script'},
                   {'status': 404, 'resource_type': 'image'}]
        self.assertTrue(clean_two_turn_browser_runtime([], healthy, 0, 0, 0))
        for count in (1, 2, -1, None, True, False, "0", 0.0):
            with self.subTest(blocked_native_attempts=repr(count)):
                self.assertFalse(clean_two_turn_browser_runtime([], healthy, 0, 0, count))
        caller = inspect.getsource(browser_run)
        self.assertIn("blocked['non_qa_generation'] + blocked['alternate_native_chat_route']", caller)
        self.assertIn("blocked['non_qa_generation']+=1", caller)
        self.assertIn("blocked['alternate_native_chat_route']+=1", caller)
        self.assertLess(
            caller.index("blocked['non_qa_generation'] + blocked['alternate_native_chat_route']"),
            caller.index("report['multiturn_browser_acceptance_verified']=True"))
        # External assets and blocked legacy/unscoped history are separate
        # privacy counters, not themselves proof of extra native POSTs.
        self.assertNotIn("blocked['external_origin'] +", caller)
        self.assertNotIn("blocked['legacy_unscoped_history'] +", caller)

    def test_ru_es_second_turn_bounded_quiescence_before_browser_only_pass(self):
        """A delayed third POST or changed stream after screenshot is HOLD."""
        from owner_chat_browser_qa import stable_second_turn_quiescence
        snapshot = {
            'native_calls': 2, 'native_stream_complete': True,
            'native_terminal_count': 1, 'error': None,
            'done': {'saved': True, 's03_integrated': True,
                     'dialog_matches': True},
            'dom_answer_matches_native': True, 'answer_characters': 19,
            'answer_sha256': 'a' * 64,
            'native_delta_count': 4, 'native_bytes': 180,
            'native_done_ms': 120.5,
        }
        self.assertTrue(stable_second_turn_quiescence(
            snapshot, dict(snapshot), 2, True))
        for changed in (
            {'native_calls': 3}, {'native_terminal_count': 2},
            {'native_stream_complete': False}, {'answer_characters': 20},
            {'native_delta_count': 5}, {'native_done_ms': 125.5},
            {'dom_answer_matches_native': False},
            {'done': dict(snapshot['done'], saved=False)},
            {'error': 'HOLD_LATE_FAILURE'},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(stable_second_turn_quiescence(
                    snapshot, dict(snapshot, **changed), 2, True))
        self.assertFalse(stable_second_turn_quiescence(
            snapshot, dict(snapshot), 3, True))
        self.assertFalse(stable_second_turn_quiescence(
            snapshot, dict(snapshot), 2, False))
        caller = inspect.getsource(browser_run)
        screenshot = caller.index("second_capture=await capture_private_screenshot(")
        quiet = caller.index("quiet_snapshot=await page.evaluate(SNAPSHOT_JS)")
        session = caller.index("signed_precert=await context.request.get(")
        runtime = caller.index("if not clean_two_turn_browser_runtime(")
        accepted = caller.index("report['multiturn_browser_acceptance_verified']=True")
        self.assertIn("await page.wait_for_timeout(500)", caller)
        self.assertIn("HOLD_MULTITURN_POSTTERMINAL_QUIESCENCE", caller)
        self.assertLess(screenshot, quiet)
        self.assertLess(quiet, session)
        self.assertLess(session, runtime)
        self.assertLess(runtime, accepted)

    def test_ru_es_postquiet_history_fourrow_identity_and_digest_fence(self):
        """A clean stream may conceal a rewritten or replaced persisted row."""
        from owner_chat_browser_qa import postquiet_fourrow_history_stable
        es = multiturn_followup_prompt(TOKEN, "multiturn_ru_es")
        before = {'dialog_id': DIALOG, 'messages': [
            dict(row, message_id=f'row-{index}', dialog_id=DIALOG)
            for index, row in enumerate(rows(es), 1)]}
        pin = multiturn_transcript_sha256(before['messages'])
        first_ids = ('row-1', 'row-2')
        self.assertTrue(postquiet_fourrow_history_stable(
            before, json.loads(json.dumps(before)), DIALOG, pin, first_ids))
        for label, mutate in (
            ('changed_es_answer', lambda h: h['messages'][3].update(content='9,8,7')),
            ('replaced_last_id', lambda h: h['messages'][3].update(message_id='new-row')),
            ('replaced_first_id', lambda h: h['messages'][0].update(message_id='new-row')),
            ('duplicate_id', lambda h: h['messages'][2].update(message_id='row-1')),
            ('missing_id', lambda h: h['messages'][2].pop('message_id')),
            ('bad_row_scope', lambda h: h['messages'][1].update(dialog_id='other-dialog')),
            ('bad_root_scope', lambda h: h.update(dialog_id='other-dialog')),
            ('dropped_message', lambda h: h['messages'].pop()),
            ('extra_message', lambda h: h['messages'].append(dict(h['messages'][3]))),
        ):
            with self.subTest(mutation=label):
                later = json.loads(json.dumps(before))
                mutate(later)
                self.assertFalse(postquiet_fourrow_history_stable(
                    before, later, DIALOG, pin, first_ids))
        self.assertFalse(postquiet_fourrow_history_stable(
            before, before, DIALOG, '0' * 64, first_ids))
        self.assertFalse(postquiet_fourrow_history_stable(
            before, before, DIALOG, pin, ('wrong-1', 'row-2')))
        self.assertFalse(postquiet_fourrow_history_stable(
            before, before, DIALOG, pin, first_ids[:1]))
        caller = inspect.getsource(browser_run)
        self.assertLess(caller.index("quiet_snapshot=await page.evaluate(SNAPSHOT_JS)"),
                        caller.index("QA_POSTQUIET_PERSISTED_HISTORY"))
        self.assertLess(caller.index("QA_POSTQUIET_PERSISTED_HISTORY"),
                        caller.index("signed_precert=await context.request.get("))
        self.assertLess(caller.index("postquiet_fourrow_history_stable("),
                        caller.index("multiturn_browser_acceptance_verified']=True"))
        self.assertIn('HOLD_MULTITURN_POSTQUIET_HISTORY_CHANGED', caller)
        self.assertIn("base+'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6'", caller)
        self.assertIn('canonical_s03_verified=False', caller)


    def test_ru_es_postread_final_stream_fence_after_history_and_session(self):
        """A late SSE mutation during read-only history/session GET is HOLD."""
        from owner_chat_browser_qa import stable_second_turn_quiescence
        quiet = {
            'native_calls': 2, 'native_stream_complete': True,
            'native_terminal_count': 1, 'error': None,
            'done': {'saved': True, 's03_integrated': True,
                     'dialog_matches': True},
            'dom_answer_matches_native': True, 'answer_characters': 19,
            'answer_sha256': 'a' * 64,
            'native_delta_count': 4, 'native_bytes': 180,
            'native_done_ms': 120.5,
        }
        self.assertTrue(stable_second_turn_quiescence(
            quiet, dict(quiet), 2, True))
        for late in (
            {'native_calls': 3}, {'native_terminal_count': 2},
            {'native_delta_count': 5}, {'native_bytes': 181},
            {'native_done_ms': 130.5}, {'error': 'HOLD_LATE_ERROR'},
            {'dom_answer_matches_native': False},
        ):
            with self.subTest(late=late):
                self.assertFalse(stable_second_turn_quiescence(
                    quiet, dict(quiet, **late), 2, True))
        self.assertFalse(stable_second_turn_quiescence(
            quiet, dict(quiet), 2, False))
        caller = inspect.getsource(browser_run)
        history = caller.index("postquiet_history=await json_response(")
        session = caller.index("signed_precert=await context.request.get(")
        runtime = caller.index("if not clean_two_turn_browser_runtime(")
        final = caller.index("postread_snapshot=await page.evaluate(SNAPSHOT_JS)")
        passed = caller.index("report['multiturn_browser_acceptance_verified']=True")
        self.assertLess(history, session)
        self.assertLess(session, runtime)
        self.assertLess(runtime, final)
        self.assertLess(final, passed)
        self.assertIn("quiet_snapshot, postread_snapshot, stream_admitted, postread_native_equal", caller)
        self.assertIn('HOLD_MULTITURN_POSTREAD_STREAM_CHANGED', caller)
        self.assertNotIn("context.request.post(", caller[history:passed])
        self.assertIn('canonical_s03_verified=False', caller)

    def test_ru_es_equal_length_second_answer_mutation_must_hold(self):
        """Same-length changed SSE answer must fail even if counters do not move."""
        from owner_chat_browser_qa import SNAPSHOT_JS, stable_second_turn_quiescence
        snapshot = {
            'native_calls': 2, 'native_stream_complete': True,
            'native_terminal_count': 1, 'error': None,
            'done': {'saved': True, 's03_integrated': True,
                     'dialog_matches': True},
            'dom_answer_matches_native': True, 'answer_characters': 19,
            'answer_sha256': 'a' * 64,
            'native_delta_count': 4, 'native_bytes': 180,
            'native_done_ms': 120.5,
        }
        self.assertTrue(stable_second_turn_quiescence(
            snapshot, dict(snapshot), 2, True))
        # Same byte/character lengths, terminal timestamp and delta count:
        # only the stable salted answer digest distinguishes the mutation.
        self.assertFalse(stable_second_turn_quiescence(
            snapshot, dict(snapshot, answer_sha256='b' * 64), 2, True))
        for malformed in (None, '', 'a' * 63, 'Z' * 64, 123, True):
            with self.subTest(malformed=malformed):
                self.assertFalse(stable_second_turn_quiescence(
                    dict(snapshot, answer_sha256=malformed),
                    dict(snapshot, answer_sha256=malformed), 2, True))
        self.assertIn("SNAPSHOT_JS = r\"\"\"async () =>", inspect.getsource(
            __import__('owner_chat_browser_qa')))
        self.assertIn("crypto.getRandomValues(salt)", SNAPSHOT_JS)
        self.assertIn("crypto.subtle.digest('SHA-256',salted)", SNAPSHOT_JS)
        self.assertIn("answer_sha256:answerDigest", SNAPSHOT_JS)
        # Never expose raw answer or secret salt in any report snapshot.
        self.assertNotIn("answer_text:", SNAPSHOT_JS)
        self.assertNotIn("qaDigestSalt:", SNAPSHOT_JS)

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



    def test_ru_es_snapshot_webcrypto_real_chromium(self):
        """Real isolated Chromium evaluates the production async snapshot JS.

        Browser-only evidence: no native inference, cookies, or canonical S03.
        """
        from playwright.sync_api import sync_playwright
        from owner_chat_browser_qa import SNAPSHOT_JS, stable_second_turn_quiescence

        with sync_playwright() as runner:
            browser = runner.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("**/b5-crypto-snapshot", lambda route: route.fulfill(
                    status=200, content_type="text/html",
                    body='<html><body><div id="messages"><div id="answer">10,9,8</div></div></body></html>'))
                page.goto("http://127.0.0.1:8765/b5-crypto-snapshot")
                self.assertTrue(page.evaluate("window.isSecureContext"))
                self.assertEqual(page.evaluate("typeof crypto.subtle"), "object")
                page.evaluate("""() => {
                    window.__NOX_BROWSER_QA={
                        answer:'10,9,8',uiBody:document.getElementById('answer'),
                        contexts:[],nativeFirst:10,nativeDone:100,nativeDeltas:4,
                        nativeBytes:120,nativeCalls:2,nativeTerminalCount:1,
                        nativeStreamComplete:true,done:{saved:true,s03_integrated:true,dialog_matches:true},
                        error:null,draws:0
                    };
                }""")
                first = page.evaluate(SNAPSHOT_JS)
                second = page.evaluate(SNAPSHOT_JS)
                self.assertRegex(first['answer_sha256'], r'^[0-9a-f]{64}    unittest.main()
)
                self.assertEqual(first['answer_sha256'], second['answer_sha256'])
                self.assertTrue(first['dom_answer_matches_native'])
                self.assertTrue(stable_second_turn_quiescence(first, second, 2, True))
                self.assertNotIn('qaDigestSalt', first)
                self.assertNotIn('10,9,8', str(first))
                # The mutation preserves all network counters and character length.
                page.evaluate("""() => {
                    window.__NOX_BROWSER_QA.answer='10,9,7';
                    document.getElementById('answer').innerText='10,9,7';
                }""")
                changed = page.evaluate(SNAPSHOT_JS)
                self.assertEqual(first['answer_characters'], changed['answer_characters'])
                for field in ('native_calls','native_delta_count','native_bytes','native_done_ms'):
                    self.assertEqual(first[field], changed[field])
                self.assertNotEqual(first['answer_sha256'], changed['answer_sha256'])
                self.assertTrue(changed['dom_answer_matches_native'])
                self.assertFalse(stable_second_turn_quiescence(first, changed, 2, True))
                # Within one browser context the per-browser salt must remain stable.
                page.evaluate("""() => {
                    window.__NOX_BROWSER_QA.answer='10,9,8';
                    document.getElementById('answer').innerText='10,9,8';
                }""")
                restored = page.evaluate(SNAPSHOT_JS)
                self.assertEqual(first['answer_sha256'], restored['answer_sha256'])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
