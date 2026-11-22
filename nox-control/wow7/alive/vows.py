"""Small, non-evaluating trigger DSL for visible ALIVE vows."""
from __future__ import annotations

ALLOWED_SIGNALS = frozenset(("boredom", "interest", "learning_progress", "goal_progress", "urgent"))
ALLOWED_OPS = frozenset(("eq", "gt", "gte", "lt", "lte"))


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if 0.0 <= n <= 1.0 else None


def validate_vow(vow):
    if not isinstance(vow, dict):
        return {"ok": False, "reason": "vow must be an object"}
    trigger, release = vow.get("trigger"), vow.get("release")
    for label, condition in (("trigger", trigger), ("release", release)):
        if not isinstance(condition, dict):
            return {"ok": False, "reason": label + " condition is required"}
        if condition.get("signal") not in ALLOWED_SIGNALS or condition.get("op") not in ALLOWED_OPS:
            return {"ok": False, "reason": label + " uses an unsupported signal or operator"}
        if _number(condition.get("value")) is None:
            return {"ok": False, "reason": label + " value must be numeric 0..1"}
    action = vow.get("action")
    if not isinstance(action, str) or not action.strip() or len(action) > 160:
        return {"ok": False, "reason": "bounded action text is required"}
    return {"ok": True, "reason": ""}


def matches(condition, signals):
    if not validate_vow({"trigger": condition, "release": {"signal": "urgent", "op": "eq", "value": 1}, "action": "check"})["ok"]:
        return False
    actual = signals.get(condition["signal"]) if isinstance(signals, dict) else None
    expected = _number(condition["value"])
    value = _number(actual)
    if value is None or expected is None:
        return False
    op = condition["op"]
    return {
        "eq": lambda: value == expected,
        "gt": lambda: value > expected,
        "gte": lambda: value >= expected,
        "lt": lambda: value < expected,
        "lte": lambda: value <= expected,
    }[op]()
