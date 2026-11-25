"""One cross-source synthetic composition check, not native acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from d3_r68_review_binding import prepare_bound_review, verify_bound_reviews
from b2_existing_dialog_review import SCHEMA

DIALOG = "a" * 32
SESSION = "fixture-session"
TEXTS = ("Первый ответ", "Ответ на русском", "Respuesta en español")

def raw(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def fixture():
    rows = []
    evidence = {}
    specs = []
    for seq, answer in enumerate(TEXTS, 1):
        prompt = "Pregunta" if seq == 3 else "Вопрос " + str(seq)
        for role, content in (("user", prompt), ("assistant", answer)):
            rows.append(dict(role=role, content=content, dialog_id=DIALOG,
                             session_id=SESSION, message_id=f"message-{len(rows)}"))
        if seq > 1:
            spec = dict(turn=seq, prompt=prompt, locale="es" if seq == 3 else "ru",
                        criteria="Respond to the actual previous context.")
            specs.append(spec)
            doc = raw(dict(source="canonical_s03", independent=True, sequence=seq,
                           dialog_id=DIALOG, session_id=SESSION, event_id=f"event-{seq}",
                           turn_id=f"turn-{seq}", messages=list(rows),
                           full_answer_sha256=digest(answer.encode())))
            evidence[f"turn{seq}_raw"] = doc
            evidence[f"turn{seq}_pin"] = digest(doc)
    rubric = raw(dict(schema=SCHEMA, dialog_id=DIALOG, session_id=SESSION, turns=specs))
    evidence.update(rubric_raw=rubric, rubric_pin=digest(rubric))
    return evidence

def actual_b4_pair(answers=TEXTS[1:], dialog=DIALOG):
    turns, observed = [], []
    for i, answer in enumerate(answers, 2):
        e = dict(turn=i, exchange_id=f"exchange-{i}",
                 body_sha256=digest(f"synthetic-sse-{i}".encode()),
                 visible_text_sha256=digest(answer.encode()))
        turns.append(e)
        proof = dict(e, verified=True, timing_scope="browser-consumer",
                     dialog_id=dialog, browser_authenticated=False, native_verified=False,
                     canonical_s03_verified=False, model_tokens_per_second=None,
                     first_byte_ms=1, ttft_ms=2, sse_done_ms=3, completion_ms=4,
                     body_bytes=10)
        observed.append(dict(turn=i, browser_posts=i, admitted_posts=i, proof=proof))
    expected = dict(dialog_id=dialog, prior_exchange_id="exchange-1",
                    baseline_browser_posts=1, baseline_admitted_posts=1, turns=turns)
    runner = """import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
const {bindExistingTurnPair}=await import(pathToFileURL(process.argv[1]).href);
const {expected,observed}=JSON.parse(readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(bindExistingTurnPair(expected,observed)));
"""
    return subprocess.run(["node", "--input-type=module", "-e", runner,
                           os.environ["D3_B4_MODULE"]],
                          input=raw(dict(expected=expected, observed=observed)),
                          stdout=subprocess.PIPE, check=True, timeout=10).stdout

class Composition(unittest.TestCase):
    def test_exact_pair_then_review_closure(self):
        evidence = fixture()
        pair = actual_b4_pair()
        bound = prepare_bound_review(pair_raw=pair, pair_pin=digest(pair), **evidence)
        self.assertEqual(bound["native_acceptance"], "HOLD_EXTERNAL_OWNER_BROWSER_S03_REVIEW")
        self.assertEqual([x["answer"] for x in bound["review_packet"]["evidence"]],
                         list(TEXTS[1:]))
        submissions = {}
        for side in ("a", "b"):
            doc = json.loads(raw(bound["review_packet"]["submission"]))
            doc["reviewer_id"] = f"fixture-reviewer-{side}"
            for decision in doc["decisions"]:
                decision.update(verdict="correct", reason="Synthetic review only.")
            data = raw(doc)
            submissions[f"submission_{side}_raw"] = data
            submissions[f"submission_{side}_pin"] = digest(data)
        result = verify_bound_reviews(pair_raw=pair, pair_pin=digest(pair),
                                      **submissions, **evidence)
        self.assertEqual(result["review_summary"]["decisions_bound"], 4)
        self.assertFalse(result["review_summary"]["reviewer_identity_verified"])
        self.assertEqual(result["pair_sha256"], digest(pair))
        self.assertEqual(result["native_acceptance"], "HOLD_EXTERNAL_OWNER_BROWSER_S03_REVIEW")
        other = actual_b4_pair((TEXTS[1], "Wrong visible answer"))
        with self.assertRaisesRegex(ValueError, "BROWSER_S03_ANSWER_MISMATCH"):
            verify_bound_reviews(pair_raw=other, pair_pin=digest(other),
                                 **submissions, **evidence)

    def test_valid_b4_but_wrong_s03_text(self):
        pair = actual_b4_pair(("Wrong visible answer", TEXTS[2]))
        with self.assertRaisesRegex(ValueError, "BROWSER_S03_ANSWER_MISMATCH"):
            prepare_bound_review(pair_raw=pair, pair_pin=digest(pair), **fixture())

    def test_valid_b4_but_wrong_dialog(self):
        pair = actual_b4_pair(dialog="b" * 32)
        with self.assertRaisesRegex(ValueError, "PAIR_SCOPE"):
            prepare_bound_review(pair_raw=pair, pair_pin=digest(pair), **fixture())

    def test_wrong_external_pin(self):
        pair = actual_b4_pair()
        with self.assertRaisesRegex(ValueError, "HOLD_B2_RESUME_PIN"):
            prepare_bound_review(pair_raw=pair, pair_pin="0" * 64, **fixture())

    def test_reordered_pair(self):
        doc = json.loads(actual_b4_pair())
        doc["turns"].reverse()
        pair = raw(doc)
        with self.assertRaisesRegex(ValueError, "PAIR_SEQUENCE"):
            prepare_bound_review(pair_raw=pair, pair_pin=digest(pair), **fixture())

if __name__ == "__main__":
    unittest.main(verbosity=2)
