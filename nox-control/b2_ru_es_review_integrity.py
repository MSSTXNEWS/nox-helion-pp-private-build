#!/usr/bin/env python3
"""B2/4A02: fail-closed, read-only RU/ES human-review integrity checker.

This checks whether two *claimed* reviews refer to the exact captured answers.
No reviewer identity, model quality, browser origin, or S03 row is authenticated
by this offline tool. It NEVER authorizes deployment or native acceptance.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import b2_ru_es_3turn_holdout as holdout

SCHEMA = "NOX_B2_RUES_INDEPENDENT_REVIEW_V1"
MAX_BYTES = 1_000_000
REVIEWER_ID = re.compile(r"^[A-Za-z0-9_.:-]{4,80}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERDICTS = frozenset(("correct", "incorrect", "uncertain"))
EXPECTED = frozenset((case, turn) for case in holdout.CASES
                     for turn in (1, 2, 3))


class ReviewHold(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ReviewHold(reason)


def unique_keys(pairs):
    doc = {}
    for key, value in pairs:
        require(key not in doc, "HOLD_B2_REVIEW_DUPLICATE_KEY")
        doc[key] = value
    return doc


def read_json(path: Path) -> tuple[dict, str]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "HOLD_B2_REVIEW_OVERSIZE")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys,
                     parse_constant=lambda _: (_ for _ in ()).throw(
                         ReviewHold("HOLD_B2_REVIEW_NONFINITE")))
    require(type(doc) is dict, "HOLD_B2_REVIEW_ROOT")
    return doc, hashlib.sha256(raw).hexdigest()


def verify(capture: dict, review: dict, capture_sha256: str) -> dict:
    """Bind each of 24 human verdicts to the full captured bytes and answers."""
    structure = holdout.verify_capture(capture)
    require(structure["trace_structure"] == "PASS",
            "HOLD_B2_CAPTURE_STRUCTURE")
    require(type(review) is dict and review.get("schema") == SCHEMA,
            "HOLD_B2_REVIEW_SCHEMA")
    require(type(capture_sha256) is str
            and SHA256.fullmatch(capture_sha256) is not None
            and review.get("capture_sha256") == capture_sha256,
            "HOLD_B2_REVIEW_CAPTURE_DIGEST")
    reviewers = review.get("reviewers")
    require(type(reviewers) is list and len(reviewers) == 2,
            "HOLD_B2_REVIEW_TWO_REVIEWERS")
    answers = {(s["case_id"], i): turn["answer"]
               for s in capture["sessions"]
               for i, turn in enumerate(s["turns"], 1)}
    seen_reviewer = set()
    by_turn = {key: [] for key in EXPECTED}
    for reviewer in reviewers:
        require(type(reviewer) is dict, "HOLD_B2_REVIEW_REVIEWER")
        reviewer_id = reviewer.get("reviewer_id")
        require(type(reviewer_id) is str
                and REVIEWER_ID.fullmatch(reviewer_id) is not None
                and reviewer_id not in seen_reviewer,
                "HOLD_B2_REVIEW_REVIEWER_ID")
        seen_reviewer.add(reviewer_id)
        decisions = reviewer.get("decisions")
        require(type(decisions) is list and len(decisions) == len(EXPECTED),
                "HOLD_B2_REVIEW_COVERAGE")
        seen_turn = set()
        for decision in decisions:
            require(type(decision) is dict, "HOLD_B2_REVIEW_DECISION")
            case_id, turn = decision.get("case_id"), decision.get("turn")
            require(type(case_id) is str and type(turn) is int
                    and (case_id, turn) in EXPECTED
                    and (case_id, turn) not in seen_turn,
                    "HOLD_B2_REVIEW_COVERAGE")
            key = (case_id, turn)
            seen_turn.add(key)
            expected_hash = hashlib.sha256(
                answers[key].encode("utf-8")).hexdigest()
            require(type(decision.get("answer_sha256")) is str
                    and decision["answer_sha256"] == expected_hash,
                    "HOLD_B2_REVIEW_STALE_ANSWER")
            verdict = decision.get("verdict")
            require(type(verdict) is str and verdict in VERDICTS,
                    "HOLD_B2_REVIEW_VERDICT")
            reason = decision.get("reason")
            require(type(reason) is str and 8 <= len(reason.strip()) <= 400,
                    "HOLD_B2_REVIEW_EXPLANATION")
            by_turn[key].append(verdict)
        require(seen_turn == EXPECTED, "HOLD_B2_REVIEW_COVERAGE")
    disagreement = sorted(f"{case}:{turn}" for (case, turn), marks in
                          by_turn.items() if marks[0] != marks[1])
    reported_incorrect = sorted(f"{case}:{turn}" for (case, turn), marks in
                                by_turn.items() if "incorrect" in marks)
    reported_uncertain = sorted(f"{case}:{turn}" for (case, turn), marks in
                                by_turn.items() if "uncertain" in marks)
    if reported_incorrect:
        status = "INCORRECT_REPORTED_UNVERIFIED"
    elif disagreement or reported_uncertain:
        status = "ADJUDICATION_REQUIRED"
    else:
        status = "TWO_REVIEWER_CONSENSUS_REPORTED_UNVERIFIED"
    return {
        "schema": SCHEMA,
        "capture_sha256": capture_sha256,
        "capture_origin_claimed": capture["origin"],
        "decisions_bound": sum(map(len, by_turn.values())),
        "distinct_reviewer_id_claims": len(seen_reviewer),
        "review_summary": status,
        "disagreements": disagreement,
        "reported_incorrect": reported_incorrect,
        "reported_uncertain": reported_uncertain,
        "reviewer_identity_verified": False,
        "quality_grade": "NOT_INDEPENDENTLY_VERIFIED",
        "native_acceptance": holdout.HOLD,
        "required_next": "Native owner/CAS and actual same-browser RU/ES SSE 2/3; "
                         "independent reviewer identity, browser/S03/served SHA256 readback",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: b2_ru_es_review_integrity.py CAPTURE.json REVIEW.json",
              file=sys.stderr)
        return 2
    try:
        capture, capture_sha = read_json(Path(argv[1]))
        review, _ = read_json(Path(argv[2]))
        print(json.dumps(verify(capture, review, capture_sha),
                         ensure_ascii=False, sort_keys=True))
        return 0
    except (ReviewHold, holdout.CaptureHold, OSError, UnicodeError,
            ValueError, TypeError, KeyError, IndexError) as error:
        reason = str(error)
        if not reason.startswith("HOLD_B2_"):
            reason = "HOLD_B2_REVIEW_IO_OR_JSON"
        print(json.dumps({"review_summary": "HOLD", "reason": reason},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
