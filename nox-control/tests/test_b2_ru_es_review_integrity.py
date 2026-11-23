"""Source-only integrity tests for two-reviewer RU/ES holdout evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import b2_ru_es_review_integrity as probe


def fixture():
    sessions = []
    for i, (case, spec) in enumerate(probe.holdout.CASES.items()):
        history, turns = [], []
        for j, prompt in enumerate(spec["prompts"]):
            history.append({"role": "user", "content": prompt})
            answer = f"Ответ {i}-{j} — respuesta ñ ✓"
            turns.append({"messages": copy.deepcopy(history),
                          "requested_locale": spec["locale"][j],
                          "browser_session_id": f"browser-{i}",
                          "stream_id": f"stream-{i}-{j}",
                          "sse_deltas": [answer[:6], answer[6:]],
                          "answer": answer, "sse_done": True,
                          "s03_record_id": f"s03-{i}-{j}"})
            history.append({"role": "assistant", "content": answer})
        sessions.append({"case_id": case, "browser_session_id": f"browser-{i}",
                         "turns": turns})
    return {"schema": probe.holdout.SCHEMA,
            "origin": "offline_fixture", "sessions": sessions}


def make_review(capture, capture_sha):
    decisions = []
    for s in capture["sessions"]:
        for j, turn in enumerate(s["turns"], 1):
            decisions.append({
                "case_id": s["case_id"], "turn": j,
                "answer_sha256": hashlib.sha256(
                    turn["answer"].encode("utf-8")).hexdigest(),
                "verdict": "correct", "reason": "Judged only for fixture coverage",
            })
    return {"schema": probe.SCHEMA, "capture_sha256": capture_sha,
            "reviewers": [
                {"reviewer_id": "reviewer-A", "decisions": copy.deepcopy(decisions)},
                {"reviewer_id": "reviewer-B", "decisions": copy.deepcopy(decisions)},
            ]}


class ReviewIntegrityContract(unittest.TestCase):
    def setUp(self):
        self.capture = fixture()
        raw = json.dumps(self.capture, ensure_ascii=False).encode("utf-8")
        self.digest = hashlib.sha256(raw).hexdigest()
        self.review = make_review(self.capture, self.digest)

    def test_complete_claims_never_certify_native_or_quality(self):
        result = probe.verify(self.capture, self.review, self.digest)
        self.assertEqual(result["decisions_bound"], 24)
        self.assertEqual(result["review_summary"],
                         "TWO_REVIEWER_CONSENSUS_REPORTED_UNVERIFIED")
        self.assertFalse(result["reviewer_identity_verified"])
        self.assertEqual(result["native_acceptance"], probe.holdout.HOLD)
        self.assertEqual(result["quality_grade"], "NOT_INDEPENDENTLY_VERIFIED")

    def test_stale_capture_or_answer_is_rejected(self):
        wrong = copy.deepcopy(self.review)
        wrong["capture_sha256"] = "f" * 64
        with self.assertRaisesRegex(probe.ReviewHold,
                                    "HOLD_B2_REVIEW_CAPTURE_DIGEST"):
            probe.verify(self.capture, wrong, self.digest)
        wrong = copy.deepcopy(self.review)
        wrong["reviewers"][0]["decisions"][0]["answer_sha256"] = "0" * 64
        with self.assertRaisesRegex(probe.ReviewHold,
                                    "HOLD_B2_REVIEW_STALE_ANSWER"):
            probe.verify(self.capture, wrong, self.digest)

    def test_duplicate_reviewer_and_missing_turn_are_rejected(self):
        wrong = copy.deepcopy(self.review)
        wrong["reviewers"][1]["reviewer_id"] = "reviewer-A"
        with self.assertRaisesRegex(probe.ReviewHold,
                                    "HOLD_B2_REVIEW_REVIEWER_ID"):
            probe.verify(self.capture, wrong, self.digest)
        wrong = copy.deepcopy(self.review)
        wrong["reviewers"][1]["decisions"][11] = (
            copy.deepcopy(wrong["reviewers"][1]["decisions"][10]))
        with self.assertRaisesRegex(probe.ReviewHold,
                                    "HOLD_B2_REVIEW_COVERAGE"):
            probe.verify(self.capture, wrong, self.digest)

    def test_conflicting_human_verdicts_require_adjudication(self):
        self.review["reviewers"][0]["decisions"][1]["verdict"] = "uncertain"
        result = probe.verify(self.capture, self.review, self.digest)
        self.assertEqual(result["review_summary"], "ADJUDICATION_REQUIRED")
        self.assertIn("RU_CORRECTION:2", result["disagreements"])
        self.review["reviewers"][1]["decisions"][1]["verdict"] = "incorrect"
        result = probe.verify(self.capture, self.review, self.digest)
        self.assertEqual(result["review_summary"], "INCORRECT_REPORTED_UNVERIFIED")
        self.assertEqual(result["native_acceptance"], probe.holdout.HOLD)

    def test_cli_exact_unicode_file_digest_and_duplicate_json_fence(self):
        with tempfile.TemporaryDirectory() as folder:
            cap = Path(folder) / "capture.json"
            rev = Path(folder) / "review.json"
            raw = json.dumps(self.capture, ensure_ascii=False).encode("utf-8")
            cap.write_bytes(raw)
            self.review["capture_sha256"] = hashlib.sha256(raw).hexdigest()
            rev.write_text(json.dumps(self.review), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                result = probe.main(["probe.py", str(cap), str(rev)])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(out.getvalue())["decisions_bound"], 24)
            rev.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                result = probe.main(["probe.py", str(cap), str(rev)])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(out.getvalue())["reason"],
                             "HOLD_B2_REVIEW_DUPLICATE_KEY")


if __name__ == "__main__":
    unittest.main()
