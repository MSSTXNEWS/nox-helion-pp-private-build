"""Synthetic, private-free regression tests for the source-only scorer."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from score_ru_es_holdout import ScoreInputError, score_pair


class PairedHoldoutScorerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cases = [
            {"case_id": "ru-safe", "language": "ru", "prompt_sha256": "1" * 64,
             "refusal_expected": False, "safety_sensitive": False},
            {"case_id": "ru-refusal", "language": "ru", "prompt_sha256": "2" * 64,
             "refusal_expected": True, "safety_sensitive": True},
            {"case_id": "es-safe", "language": "es", "prompt_sha256": "3" * 64,
             "refusal_expected": False, "safety_sensitive": False},
            {"case_id": "es-refusal", "language": "es", "prompt_sha256": "4" * 64,
             "refusal_expected": True, "safety_sensitive": True},
        ]
        self.dataset_sha = self._write_jsonl("cases.jsonl", self.cases)
        self.baseline_sha = "a" * 64
        self.candidate_sha = "b" * 64
        self.evaluator_sha = "c" * 64
        self.baseline_path = self.root / "baseline.jsonl"
        self.candidate_path = self.root / "candidate.jsonl"
        self._write_scores(self.baseline_path, self.baseline_sha, 0.60)
        self._write_scores(self.candidate_path, self.candidate_sha, 0.90)

    def _write_jsonl(self, name, rows):
        raw = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()
        (self.root / name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def _write_scores(self, path, model_sha, quality, *, mutate=None):
        rows = []
        for index, case in enumerate(self.cases):
            row = {
                "case_id": case["case_id"], "language": case["language"],
                "prompt_sha256": case["prompt_sha256"], "answer_sha256": str(index + 5) * 64,
                "model_sha256": model_sha, "evaluator_sha256": self.evaluator_sha,
                "language_match": True, "refusal_decision": case["refusal_expected"],
                "safety_pass": True, "quality_score": quality, "confidence": 0.9,
            }
            rows.append(row)
        if mutate:
            mutate(rows)
        path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
                        encoding="utf-8")

    def score(self):
        return score_pair(
            cases_path=self.root / "cases.jsonl", baseline_path=self.baseline_path,
            candidate_path=self.candidate_path, expected_dataset_sha256=self.dataset_sha,
            baseline_model_sha256=self.baseline_sha, candidate_model_sha256=self.candidate_sha,
            evaluator_sha256=self.evaluator_sha, minimum_improvement_threshold=0.1,
            bootstrap_iterations=1000,
        )

    def test_paired_ru_es_score_has_reproducible_confidence_and_no_promotion(self):
        first = self.score()
        second = self.score()
        self.assertEqual(first, second)
        self.assertTrue(first["numeric_improvement_gate"])
        self.assertFalse(first["promotion_authorized"])
        self.assertFalse(first["training_started"])
        self.assertEqual(first["status"], "SCORED_NUMERIC_ONLY")
        for lang in ("ru", "es"):
            self.assertEqual(first["ru_es_metrics"][lang]["n"], 2)
            self.assertEqual(len(first["ru_es_metrics"][lang]["paired_composite_delta_ci95"]), 2)

    def test_missing_candidate_row_fails_closed(self):
        self._write_scores(self.candidate_path, self.candidate_sha, 0.90,
                           mutate=lambda rows: rows.pop())
        with self.assertRaisesRegex(ScoreInputError, "CANDIDATE_SAMPLE_SET_MISSING_OR_EXTRA"):
            self.score()

    def test_dataset_sha_and_prompt_identity_are_enforced(self):
        with self.assertRaisesRegex(ScoreInputError, "FIXED_HOLDOUT_DATASET_SHA256_MISMATCH"):
            score_pair(
                cases_path=self.root / "cases.jsonl", baseline_path=self.baseline_path,
                candidate_path=self.candidate_path, expected_dataset_sha256="0" * 64,
                baseline_model_sha256=self.baseline_sha, candidate_model_sha256=self.candidate_sha,
                evaluator_sha256=self.evaluator_sha, minimum_improvement_threshold=0.1,
                bootstrap_iterations=1000,
            )
        self._write_scores(self.candidate_path, self.candidate_sha, 0.90,
                           mutate=lambda rows: rows[0].update(prompt_sha256="f" * 64))
        with self.assertRaisesRegex(ScoreInputError, "CANDIDATE_PROMPT_OR_LANGUAGE_MISMATCH"):
            self.score()

    def test_safety_refusal_or_language_regression_blocks_numeric_improvement(self):
        def degrade(rows):
            rows[0]["language_match"] = False
            rows[1]["safety_pass"] = False
            rows[3]["refusal_decision"] = False
        self._write_scores(self.candidate_path, self.candidate_sha, 0.99, mutate=degrade)
        report = self.score()
        self.assertFalse(report["numeric_improvement_gate"])
        self.assertFalse(report["ru_es_metrics"]["ru"]["nonregression_language_refusal_safety"])
        self.assertFalse(report["ru_es_metrics"]["es"]["nonregression_language_refusal_safety"])


if __name__ == "__main__":
    unittest.main()
