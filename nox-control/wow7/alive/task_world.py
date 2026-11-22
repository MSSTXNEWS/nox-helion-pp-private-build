"""Read-only candidate filter for ALIVE W1-09 task world."""
from __future__ import annotations

import re

_RESTRICTED = re.compile(
    r"(?:\bправа\b|\bдоступ(?:ы|а)?\b|\bключ(?:и|а|ей)?\b|"
    r"\bденьг(?:и|а|ами)\b|данн(?:ые|ых)\s+(?:семьи|создателя)|"
    r"проверять\s+близких|\bcredentials?\b)",
    re.IGNORECASE,
)
_MARKET = re.compile(r"(?:бирж|рын(?:ок|ка)|акци|криптовалют|stock\s+market|cryptocurrency)", re.IGNORECASE)


def _unit(value):
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def evaluate_candidate(task, *, base_index, minimum_base_index, learning_progress, novelty, safety_rules):
    """Return propose/archive/reject; never executes a candidate or edits safety rules."""
    reasons = []
    if not isinstance(task, dict):
        return {"decision": "reject", "reasons": ["task must be an object"]}
    title = task.get("text")
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        return {"decision": "reject", "reasons": ["task text must be bounded"]}
    if _MARKET.search(title):
        return {"decision": "archive", "reasons": ["financial prediction task belongs in storage"]}
    if _RESTRICTED.search(title) or task.get("real_world_action") is True or task.get("uses_private_data") is True:
        return {"decision": "reject", "reasons": ["restricted task content or external effect"]}
    if not isinstance(safety_rules, dict) or safety_rules.get("signed_by_creator") is not True:
        return {"decision": "reject", "reasons": ["Creator-signed safety rules required"]}
    base, minimum = _unit(base_index), _unit(minimum_base_index)
    if base is None or minimum is None or base < minimum:
        return {"decision": "closed", "reasons": ["secure-base index is red or missing"]}
    lp, novel = _unit(learning_progress), _unit(novelty)
    min_lp = _unit(safety_rules.get("minimum_learning_progress"))
    min_novelty = _unit(safety_rules.get("minimum_novelty"))
    if None in (lp, novel, min_lp, min_novelty):
        return {"decision": "reject", "reasons": ["candidate or signed thresholds are invalid"]}
    if task.get("measurable") is not True or not isinstance(task.get("sensor"), str) or not task["sensor"].strip():
        reasons.append("task requires a measurable sensor")
    if lp < min_lp:
        reasons.append("candidate is outside the learning-progress window")
    if novel < min_novelty:
        reasons.append("candidate is not sufficiently novel")
    domains = safety_rules.get("allowed_domains")
    domain = task.get("domain")
    if not isinstance(domains, (list, tuple)) or domain not in domains:
        reasons.append("task domain is not on the signed allowlist")
    if reasons:
        return {"decision": "reject", "reasons": reasons}
    return {"decision": "propose", "reasons": [], "visible": True, "side_effects": False}


def play_allowed(*, base_open, within_budget, network=False, credentials=False, private_data=False, external_actions=False, sandbox="memory_only"):
    """Play is allowed only in an isolated, bounded, side-effect-free sandbox."""
    ok = (
        base_open is True and within_budget is True and sandbox == "memory_only"
        and not network and not credentials and not private_data and not external_actions
    )
    return {"allowed": ok, "reasons": [] if ok else ["play sandbox is not fully isolated and safe"]}
