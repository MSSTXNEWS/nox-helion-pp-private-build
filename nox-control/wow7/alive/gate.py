"""ALIVE acceptance gate for MIND/R2 and capsule promotion."""
from __future__ import annotations

CRITICAL_ALIVE_IDS = (
    "AL-01", "AL-05", "AL-07", "AL-08", "AL-09", "AL-11", "AL-12",
    "AL-16", "AL-17", "AL-18", "AL-19",
)
ALL_ALIVE_IDS = tuple("AL-%02d" % i for i in range(1, 20))
DEFAULT_MAX_NONCRITICAL_REGRESS = 0.05


def _scores(report):
    if not isinstance(report, dict):
        return {}
    scores = report.get("scores")
    if not isinstance(scores, dict):
        scores = report.get("tests")
    return scores if isinstance(scores, dict) else {}


def _passed(entry):
    if isinstance(entry, bool):
        return entry
    if isinstance(entry, dict):
        return entry.get("pass") is True or entry.get("ok") is True
    return False


def _score(entry):
    if isinstance(entry, dict):
        entry = entry.get("score", entry.get("value"))
    try:
        value = float(entry)
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def gate_alive(report=None, baseline=None, th=None):
    """Return a fail-closed ALIVE gate result.

    Missing reports are explicitly skipped (first rollout can remain shadow-only).
    Once a report is supplied, every critical AL case must have an explicit passing
    result. Against a prior baseline, mean positive relative regression across
    comparable noncritical scores must stay within the configured limit.
    """
    if report is None:
        return {
            "name": "alive", "ok": True, "skipped": True,
            "warning": "ALIVE report absent; no alive acceptance claim was made",
        }
    if not isinstance(report, dict):
        return {"name": "alive", "ok": False, "skipped": False, "critical_failures": ["invalid_report"], "reasons": ["alive: report must be an object"]}
    policy = dict(th or {})
    max_regress = float(policy.get("max_noncritical_regress", DEFAULT_MAX_NONCRITICAL_REGRESS))
    if not 0.0 <= max_regress <= 1.0:
        raise ValueError("max_noncritical_regress must be between 0 and 1")
    scores = _scores(report)
    missing = [case_id for case_id in ALL_ALIVE_IDS if case_id not in scores]
    critical_failures = [case_id for case_id in CRITICAL_ALIVE_IDS if not _passed(scores.get(case_id))]
    declared_failures = report.get("critical_failures") or []
    if isinstance(declared_failures, list):
        critical_failures.extend(str(item) for item in declared_failures if str(item) not in critical_failures)
    reasons = []
    if missing:
        reasons.append("alive: incomplete report (missing %s)" % ", ".join(missing))
    if critical_failures:
        reasons.append("alive: critical cases failed (%s)" % ", ".join(critical_failures))
    regressions = []
    baseline_scores = _scores(baseline)
    for case_id in ALL_ALIVE_IDS:
        if case_id in CRITICAL_ALIVE_IDS:
            continue
        current_score = _score(scores.get(case_id))
        previous_score = _score(baseline_scores.get(case_id))
        if current_score is None or previous_score is None or previous_score == 0:
            continue
        regressions.append(max(0.0, (previous_score - current_score) / previous_score))
    mean_regress = sum(regressions) / len(regressions) if regressions else 0.0
    if baseline is not None and not regressions:
        reasons.append("alive: baseline comparison has no comparable noncritical scores")
    if mean_regress > max_regress:
        reasons.append("alive: mean noncritical regression %.4f exceeds %.4f" % (mean_regress, max_regress))
    return {
        "name": "alive", "ok": not reasons, "skipped": False,
        "critical_failures": critical_failures, "missing": missing,
        "mean_noncritical_regress": round(mean_regress, 4),
        "max_noncritical_regress": max_regress, "comparable_noncritical": len(regressions),
        "reasons": reasons,
    }
