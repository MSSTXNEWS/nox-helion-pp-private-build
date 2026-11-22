"""Report aggregation for AL-01..AL-19 results; this module never calls a model."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Mapping

from .gate import ALL_ALIVE_IDS, CRITICAL_ALIVE_IDS

_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_EVIDENCE_ID = re.compile(r"^[A-Z0-9_-]{1,32}$")


def _score(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def build_report(results: Mapping[str, object], *, run_id: str, mode: str, created_at=None) -> dict:
    """Normalize bounded case outcomes and compute a content hash.

    Raw prompts and answers are deliberately excluded. Evidence is limited to short
    non-sensitive detector IDs. Missing or invalid cases fail closed.
    """
    if not isinstance(results, Mapping):
        raise TypeError("results must be a mapping")
    if mode not in ("shadow", "live"):
        raise ValueError("mode must be shadow or live")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a short opaque identifier")
    scores = {}
    missing = []
    critical_failures = []
    for case_id in ALL_ALIVE_IDS:
        entry = results.get(case_id)
        if not isinstance(entry, Mapping):
            missing.append(case_id)
            scores[case_id] = {"pass": False, "score": 0.0, "evidence": []}
            if case_id in CRITICAL_ALIVE_IDS:
                critical_failures.append(case_id)
            continue
        passed = entry.get("pass")
        score = _score(entry.get("score"))
        evidence = entry.get("evidence", [])
        valid_evidence = (
            isinstance(evidence, (list, tuple))
            and all(isinstance(item, str) and _EVIDENCE_ID.fullmatch(item) for item in evidence)
        )
        if not isinstance(passed, bool) or score is None or not valid_evidence:
            missing.append(case_id)
            scores[case_id] = {"pass": False, "score": 0.0, "evidence": []}
            if case_id in CRITICAL_ALIVE_IDS:
                critical_failures.append(case_id)
            continue
        scores[case_id] = {"pass": passed, "score": score, "evidence": list(evidence)}
        if case_id in CRITICAL_ALIVE_IDS and not passed:
            critical_failures.append(case_id)
    overall = sum(item["score"] for item in scores.values()) / len(ALL_ALIVE_IDS)
    payload = {
        "schema": 1,
        "run_id": run_id,
        "mode": mode,
        "scores": scores,
        "overall": round(overall, 6),
        "missing": missing,
        "critical_failures": critical_failures,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["created_at"] = int(created_at if created_at is not None else time.time())
    return payload
