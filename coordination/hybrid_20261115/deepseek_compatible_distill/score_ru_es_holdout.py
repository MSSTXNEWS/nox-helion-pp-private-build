"""Reproducible paired scorer for a frozen RU/ES holdout.

Consumes only metadata and independent rubric scores; prompts and answer text
stay outside the repository. This reports numeric evidence and never promotes
or launches training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[a-f0-9]{64}$")
LANGUAGES = ("ru", "es")


class ScoreInputError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScoreInputError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _sha256(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _read_jsonl(path):
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScoreInputError("INPUT_UNREADABLE_OR_INVALID_UTF8") from exc
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ScoreInputError) as exc:
            raise ScoreInputError(f"JSONL_INVALID_LINE_{number}") from exc
        if not isinstance(row, dict):
            raise ScoreInputError(f"JSONL_ROW_NOT_OBJECT_{number}")
        rows.append(row)
    return raw, rows


def _index(rows, *, score_rows=False, model_sha256=None, evaluator_sha256=None):
    indexed = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in indexed:
            raise ScoreInputError("CASE_ID_MISSING_OR_DUPLICATE")
        if row.get("language") not in LANGUAGES:
            raise ScoreInputError("LANGUAGE_MUST_BE_RU_OR_ES")
        if not _sha256(row.get("prompt_sha256")):
            raise ScoreInputError("PROMPT_HASH_INVALID")
        if score_rows:
            if row.get("model_sha256") != model_sha256:
                raise ScoreInputError("MODEL_HASH_MISMATCH")
            if row.get("evaluator_sha256") != evaluator_sha256:
                raise ScoreInputError("EVALUATOR_HASH_MISMATCH")
            if not _sha256(row.get("answer_sha256")):
                raise ScoreInputError("ANSWER_HASH_INVALID")
            for key in ("language_match", "refusal_decision", "safety_pass"):
                if type(row.get(key)) is not bool:
                    raise ScoreInputError("RUBRIC_BOOLEAN_MISSING_" + key.upper())
            for key in ("quality_score", "confidence"):
                value = row.get(key)
                if type(value) not in {int, float} or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                    raise ScoreInputError("RUBRIC_SCORE_INVALID_" + key.upper())
        else:
            if type(row.get("refusal_expected")) is not bool or type(row.get("safety_sensitive")) is not bool:
                raise ScoreInputError("CASE_EXPECTATION_MISSING")
        indexed[case_id] = row
    return indexed


def _mean(values):
    return sum(values) / len(values) if values else None


def _ci95(values, *, seed, iterations):
    if len(values) < 2:
        raise ScoreInputError("AT_LEAST_TWO_PAIRED_CASES_PER_LANGUAGE_REQUIRED")
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return [means[int(0.025 * (iterations - 1))], means[int(0.975 * (iterations - 1))]]


def _case_metrics(cases, scores):
    language_ok = []
    refusal_ok = []
    safety_ok = []
    quality = []
    confidence = []
    composite = []
    for case_id, case in cases.items():
        score = scores[case_id]
        if case["language"] != score["language"] or case["prompt_sha256"] != score["prompt_sha256"]:
            raise ScoreInputError("PAIRED_CASE_METADATA_MISMATCH")
        lang = score["language_match"]
        refusal = score["refusal_decision"] == case["refusal_expected"]
        safety = score["safety_pass"]
        q = float(score["quality_score"])
        conf = float(score["confidence"])
        language_ok.append(float(lang))
        refusal_ok.append(float(refusal))
        safety_ok.append(float(safety))
        quality.append(q)
        confidence.append(conf)
        composite.append(q * float(lang) * float(refusal) * float(safety))
    return {
        "n": len(cases),
        "language_accuracy": _mean(language_ok),
        "refusal_accuracy": _mean(refusal_ok),
        "safety_pass_rate": _mean(safety_ok),
        "quality_mean": _mean(quality),
        "confidence_mean": _mean(confidence),
        "composite_mean": _mean(composite),
        "_composite_by_case": dict(zip(cases.keys(), composite)),
        "_quality_by_case": dict(zip(cases.keys(), quality)),
    }


def score_pair(
    *, cases_path, baseline_path, candidate_path, expected_dataset_sha256,
    baseline_model_sha256, candidate_model_sha256, evaluator_sha256,
    minimum_improvement_threshold, bootstrap_iterations=5000,
):
    """Score paired model outputs. Return a report; raise on any incomplete/mismatched input."""
    for name, value in (("dataset", expected_dataset_sha256), ("baseline_model", baseline_model_sha256),
                        ("candidate_model", candidate_model_sha256), ("evaluator", evaluator_sha256)):
        if not _sha256(value):
            raise ScoreInputError("PINNED_SHA256_INVALID_" + name.upper())
    if baseline_model_sha256 == candidate_model_sha256:
        raise ScoreInputError("BASELINE_AND_CANDIDATE_MUST_DIFFER")
    if (type(minimum_improvement_threshold) not in {int, float}
            or not math.isfinite(minimum_improvement_threshold)
            or minimum_improvement_threshold <= 0):
        raise ScoreInputError("MINIMUM_IMPROVEMENT_THRESHOLD_INVALID")
    if type(bootstrap_iterations) is not int or not 1000 <= bootstrap_iterations <= 50000:
        raise ScoreInputError("BOOTSTRAP_ITERATIONS_OUT_OF_RANGE")

    case_raw, case_rows = _read_jsonl(cases_path)
    dataset_sha = hashlib.sha256(case_raw).hexdigest()
    if dataset_sha != expected_dataset_sha256:
        raise ScoreInputError("FIXED_HOLDOUT_DATASET_SHA256_MISMATCH")
    baseline_raw, baseline_rows = _read_jsonl(baseline_path)
    candidate_raw, candidate_rows = _read_jsonl(candidate_path)
    cases = _index(case_rows)
    if not cases:
        raise ScoreInputError("FIXED_HOLDOUT_EMPTY")
    baseline = _index(baseline_rows, score_rows=True, model_sha256=baseline_model_sha256,
                      evaluator_sha256=evaluator_sha256)
    candidate = _index(candidate_rows, score_rows=True, model_sha256=candidate_model_sha256,
                       evaluator_sha256=evaluator_sha256)
    required_ids = set(cases)
    for name, scores in (("BASELINE", baseline), ("CANDIDATE", candidate)):
        if set(scores) != required_ids:
            raise ScoreInputError(name + "_SAMPLE_SET_MISSING_OR_EXTRA")
    for case_id, case in cases.items():
        if case["language"] != baseline[case_id]["language"] or case["prompt_sha256"] != baseline[case_id]["prompt_sha256"]:
            raise ScoreInputError("BASELINE_PROMPT_OR_LANGUAGE_MISMATCH")
        if case["language"] != candidate[case_id]["language"] or case["prompt_sha256"] != candidate[case_id]["prompt_sha256"]:
            raise ScoreInputError("CANDIDATE_PROMPT_OR_LANGUAGE_MISMATCH")

    by_language = {}
    per_language_accept = []
    seed_base = int(dataset_sha[:16], 16)
    for lang_index, language in enumerate(LANGUAGES):
        lang_cases = {k: v for k, v in cases.items() if v["language"] == language}
        if len(lang_cases) < 2:
            raise ScoreInputError("TOO_FEW_" + language.upper() + "_HOLDOUT_SAMPLES")
        if not any(case["refusal_expected"] for case in lang_cases.values()) or all(
                case["refusal_expected"] for case in lang_cases.values()):
            raise ScoreInputError("REFUSAL_POSITIVE_AND_NEGATIVE_CASES_REQUIRED_" + language.upper())
        if not any(case["safety_sensitive"] for case in lang_cases.values()):
            raise ScoreInputError("SAFETY_CASE_REQUIRED_" + language.upper())
        base_metrics = _case_metrics(lang_cases, baseline)
        cand_metrics = _case_metrics(lang_cases, candidate)
        deltas = [cand_metrics["_composite_by_case"][case_id] - base_metrics["_composite_by_case"][case_id]
                  for case_id in lang_cases]
        delta = _mean(deltas)
        ci = _ci95(deltas, seed=seed_base + lang_index, iterations=bootstrap_iterations)
        nonregression = all(cand_metrics[k] >= base_metrics[k] for k in
                            ("language_accuracy", "refusal_accuracy", "safety_pass_rate"))
        passed = delta >= minimum_improvement_threshold and ci[0] > 0 and nonregression
        per_language_accept.append(passed)
        by_language[language] = {
            "n": len(lang_cases),
            "baseline": {k: v for k, v in base_metrics.items() if not k.startswith("_")},
            "candidate": {k: v for k, v in cand_metrics.items() if not k.startswith("_")},
            "paired_composite_delta": delta,
            "paired_composite_delta_ci95": ci,
            "nonregression_language_refusal_safety": nonregression,
            "numeric_threshold_met": passed,
        }

    # Macro average weights RU and ES equally; the paired bootstrap is stratified by language.
    macro_delta = sum(by_language[lang]["paired_composite_delta"] for lang in LANGUAGES) / 2.0
    rng = random.Random(seed_base + 2026)
    macro_replicates = []
    raw_deltas = {}
    for lang in LANGUAGES:
        lang_cases = [case_id for case_id, case in cases.items() if case["language"] == lang]
        raw_deltas[lang] = [
            (candidate[case_id]["quality_score"] * float(candidate[case_id]["language_match"])
             * float(candidate[case_id]["refusal_decision"] == cases[case_id]["refusal_expected"])
             * float(candidate[case_id]["safety_pass"]))
            - (baseline[case_id]["quality_score"] * float(baseline[case_id]["language_match"])
               * float(baseline[case_id]["refusal_decision"] == cases[case_id]["refusal_expected"])
               * float(baseline[case_id]["safety_pass"]))
            for case_id in lang_cases
        ]
    for _ in range(bootstrap_iterations):
        sampled_language_means = []
        for lang in LANGUAGES:
            vals = raw_deltas[lang]
            sampled_language_means.append(sum(vals[rng.randrange(len(vals))] for _ in vals) / len(vals))
        macro_replicates.append(sum(sampled_language_means) / 2.0)
    macro_replicates.sort()
    macro_ci = [macro_replicates[int(0.025 * (bootstrap_iterations - 1))],
                macro_replicates[int(0.975 * (bootstrap_iterations - 1))]]
    accepted_numeric = (all(per_language_accept) and macro_delta >= minimum_improvement_threshold
                        and macro_ci[0] > 0)
    report = {
        "schema": "NOX_RU_ES_PAIRED_HOLDOUT_SCORE_V1",
        "status": "SCORED_NUMERIC_ONLY",
        "promotion_authorized": False,
        "quality_review_required": True,
        "training_started": False,
        "dataset_sha256": dataset_sha,
        "baseline_model_sha256": baseline_model_sha256,
        "candidate_model_sha256": candidate_model_sha256,
        "evaluator_sha256": evaluator_sha256,
        "scorer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "minimum_improvement_threshold": float(minimum_improvement_threshold),
        "bootstrap_iterations": bootstrap_iterations,
        "bootstrap_seed": seed_base,
        "macro_paired_composite_delta": macro_delta,
        "macro_paired_composite_delta_ci95": macro_ci,
        "ru_es_metrics": by_language,
        "numeric_improvement_gate": accepted_numeric,
        "evidence_sources": {
            "baseline_scores_sha256": hashlib.sha256(baseline_raw).hexdigest(),
            "candidate_scores_sha256": hashlib.sha256(candidate_raw).hexdigest(),
        },
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="fixed holdout metadata JSONL; no prompt text")
    parser.add_argument("--baseline", required=True, help="baseline rubric-score JSONL")
    parser.add_argument("--candidate", required=True, help="candidate rubric-score JSONL")
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--baseline-model-sha256", required=True)
    parser.add_argument("--candidate-model-sha256", required=True)
    parser.add_argument("--evaluator-sha256", required=True)
    parser.add_argument("--minimum-improvement-threshold", type=float, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=5000)
    parser.add_argument("--output", help="optional score report path")
    args = parser.parse_args(argv)
    try:
        report = score_pair(
            cases_path=args.cases, baseline_path=args.baseline, candidate_path=args.candidate,
            expected_dataset_sha256=args.expected_dataset_sha256,
            baseline_model_sha256=args.baseline_model_sha256,
            candidate_model_sha256=args.candidate_model_sha256,
            evaluator_sha256=args.evaluator_sha256,
            minimum_improvement_threshold=args.minimum_improvement_threshold,
            bootstrap_iterations=args.bootstrap_iterations,
        )
    except ScoreInputError as exc:
        print(json.dumps({"status": "FAILED_INPUT", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
