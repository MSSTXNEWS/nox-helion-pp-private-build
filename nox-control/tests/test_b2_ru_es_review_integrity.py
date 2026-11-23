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


    def test_blank_independent_review_packet_cli_and_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            cap = Path(folder) / "capture.json"
            raw = json.dumps(self.capture, ensure_ascii=False).encode("utf-8")
            cap.write_bytes(raw)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(probe.main(["probe.py", "--prepare-review", str(cap)]), 0)
            packet = json.loads(out.getvalue())
            self.assertEqual(packet["native_acceptance"], probe.holdout.HOLD)
            self.assertEqual(packet["quality_grade"], "NOT_INDEPENDENTLY_VERIFIED")
            submission = packet["submission"]
            self.assertEqual(submission["capture_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(len(submission["reviewers"]), 1)
            self.assertIsNone(submission["reviewers"][0]["reviewer_id"])
            self.assertEqual(len(packet["evidence"]), 12)
            decisions = submission["reviewers"][0]["decisions"]
            self.assertEqual(len(decisions), 12)
            for row, decision in zip(packet["evidence"], decisions):
                self.assertIsNone(decision["verdict"])
                self.assertEqual(decision["reason"], "")
                self.assertEqual(decision["answer_sha256"], hashlib.sha256(
                    row["answer"].encode("utf-8")).hexdigest())
                self.assertEqual((row["case_id"], row["turn"]),
                                 (decision["case_id"], decision["turn"]))
                self.assertEqual(len(row["history"]), row["turn"] * 2 - 1)
            self.assertIn("21 euros", packet["evidence"][2]["criteria"])
            self.assertIn("36 евро", packet["evidence"][5]["criteria"])
            self.assertIn("no inventar", packet["evidence"][8]["criteria"])
            with self.assertRaisesRegex(probe.ReviewHold, "HOLD_B2_REVIEW_TWO_REVIEWERS"):
                probe.verify(self.capture, submission, self.digest)
            # Simulate two completed independent sheets only for interface testing.
            combined = copy.deepcopy(submission)
            combined["reviewers"].append(copy.deepcopy(combined["reviewers"][0]))
            for idx, reviewer in enumerate(combined["reviewers"]):
                reviewer["reviewer_id"] = f"fixture-{idx}"
                for decision in reviewer["decisions"]:
                    decision.update(verdict="uncertain", reason="Fixture interface check")
            result = probe.verify(self.capture, combined, self.digest)
            self.assertEqual(result["decisions_bound"], 24)
            self.assertEqual(result["review_summary"], "ADJUDICATION_REQUIRED")
            self.assertEqual(result["native_acceptance"], probe.holdout.HOLD)
            self.assertEqual(cap.read_bytes(), raw)


    def test_combine_independent_submissions_preserves_hashes_and_rejects_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            cap, a, b = (Path(folder) / name for name in ("cap.json", "a.json", "b.json"))
            raw = json.dumps(self.capture, ensure_ascii=False).encode("utf-8")
            cap.write_bytes(raw)
            sheets = [{"schema": probe.SCHEMA, "capture_sha256": self.digest,
                       "reviewers": [copy.deepcopy(row)]}
                      for row in self.review["reviewers"]]
            sheets[1]["reviewers"][0]["decisions"][0]["verdict"] = "uncertain"
            sheets[1]["reviewers"][0]["decisions"][0]["reason"] = "Revisión independiente ñ"
            def write():
                for path, sheet in zip((a, b), sheets):
                    path.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
            def invoke():
                out = io.StringIO()
                with redirect_stdout(out):
                    code = probe.main(["probe.py", "--combine-reviews", str(cap), str(a), str(b)])
                return code, json.loads(out.getvalue())
            write()
            code, result = invoke()
            self.assertEqual(code, 0)
            self.assertEqual(result["reviewers"], [row["reviewers"][0] for row in sheets])
            self.assertEqual(result["submission_sha256"],
                             [hashlib.sha256(path.read_bytes()).hexdigest() for path in (a, b)])
            self.assertEqual(probe.verify(self.capture, result, self.digest)["review_summary"],
                             "ADJUDICATION_REQUIRED")
            self.assertEqual(cap.read_bytes(), raw)
            sheets[1]["capture_sha256"] = "f" * 64
            write()
            self.assertEqual(invoke(), (2, {"review_summary": "HOLD",
                                            "reason": "HOLD_B2_REVIEW_CAPTURE_DIGEST"}))
            sheets[1]["capture_sha256"] = self.digest
            sheets[1]["reviewers"] = copy.deepcopy(self.review["reviewers"])
            write()
            self.assertEqual(invoke(), (2, {"review_summary": "HOLD",
                                            "reason": "HOLD_B2_REVIEW_SINGLE_SUBMISSION"}))
            sheets[1]["reviewers"] = copy.deepcopy(sheets[0]["reviewers"])
            write()
            self.assertEqual(invoke(), (2, {"review_summary": "HOLD",
                                            "reason": "HOLD_B2_REVIEW_SUBMISSION_DIGEST"}))


if __name__ == "__main__":
    unittest.main()
