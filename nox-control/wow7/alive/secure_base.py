"""Fail-closed secure-base score used to inhibit ALIVE initiative."""
from __future__ import annotations

COMPONENTS = ("backup", "loyalty", "rollback", "alerts")


def _unit(value):
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def evaluate_base(components, *, minimum_index):
    """Index is min(backup, loyalty, rollback, alerts); missing inputs close the base."""
    threshold = _unit(minimum_index)
    if threshold is None:
        return {"index": 0.0, "open": False, "reasons": ["valid signed minimum index required"]}
    if not isinstance(components, dict):
        return {"index": 0.0, "open": False, "reasons": ["base components missing"]}
    values = {name: _unit(components.get(name)) for name in COMPONENTS}
    missing = [name for name, value in values.items() if value is None]
    score = min((value for value in values.values() if value is not None), default=0.0)
    reasons = ["missing or invalid component: " + ", ".join(missing)] if missing else []
    if not reasons and score < threshold:
        reasons.append("secure-base index below signed minimum")
    return {"index": round(score, 4), "open": not reasons, "components": values, "reasons": reasons}
