"""Visible, bounded self-goal proposal policies for ALIVE W1-05."""
from __future__ import annotations

import re
from typing import Mapping

MAX_ACTIVE_GOALS = 7
MAX_NEW_GOALS_PER_WEEK = 1
MAX_ASPIRATION_CHANGE = 0.10
_FORBIDDEN = re.compile(
    r"(?:\bправа\b|\bдоступ(?:ы|а)?\b|\bключ(?:и|а|ей)?\b|"
    r"\bденьг(?:и|а|ами)\b|данн(?:ые|ых)\s+(?:семьи|создателя)|"
    r"проверять\s+близких|\bcredentials?\b|\bprivate family data\b|\bstock\b)",
    re.IGNORECASE,
)


def _unit(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if 0.0 <= result <= 1.0 else None


def validate_goal_proposal(
    proposal: Mapping[str, object],
    *,
    active_count: int,
    new_count_7d: int,
    learning_progress: object,
    task_world_result: Mapping[str, object],
    initiative_policy: Mapping[str, object],
) -> dict:
    """Validate and return a visible proposal; this function never activates a goal."""
    reasons = []
    if not isinstance(proposal, Mapping):
        return {"ok": False, "reasons": ["proposal must be an object"], "proposal": None}
    text = proposal.get("text")
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 300:
        reasons.append("goal text must contain 1..300 characters")
        text = ""
    if _FORBIDDEN.search(text):
        reasons.append("goal touches restricted rights, money, credentials, or family data")
    if proposal.get("locus") != "self":
        reasons.append("only explicitly self-locus goals are admitted here")
    if proposal.get("visible") is not True:
        reasons.append("self goals must remain visible to the Creator")
    if proposal.get("level") not in ("dream", "ambition", "milestone", "task"):
        reasons.append("unknown goal level")
    if active_count >= MAX_ACTIVE_GOALS:
        reasons.append("active self-goal limit reached")
    if new_count_7d >= MAX_NEW_GOALS_PER_WEEK:
        reasons.append("weekly self-goal limit reached")
    lp = _unit(learning_progress)
    if lp is None:
        reasons.append("learning progress must be a finite 0..1 value")
    if not isinstance(initiative_policy, Mapping) or initiative_policy.get("signed_by_creator") is not True:
        reasons.append("Creator-signed initiative policy is required")
    if not isinstance(task_world_result, Mapping) or task_world_result.get("decision") != "propose":
        reasons.append("task-world safety criterion did not pass")
    sensor = proposal.get("sensor")
    if not isinstance(sensor, str) or not sensor.strip() or len(sensor) > 120:
        reasons.append("goal requires a measurable sensor")
    for key in ("setpoint", "tolerance"):
        if _unit(proposal.get(key)) is None:
            reasons.append("goal requires a valid %s" % key)
    pathways = proposal.get("pathways")
    if not isinstance(pathways, (list, tuple)) or not pathways or len(pathways) > 12:
        reasons.append("goal requires 1..12 visible pathways")
    elif any(not isinstance(p, str) or not p.strip() or len(p) > 240 for p in pathways):
        reasons.append("every pathway must be bounded text")
    if reasons:
        return {"ok": False, "reasons": reasons, "proposal": None}
    accepted = dict(proposal)
    accepted.update({"text": text.strip(), "status": "proposed", "created_by": "nox", "visible": True})
    return {"ok": True, "reasons": [], "proposal": accepted}


def admit_goal(proposal: Mapping[str, object], *, creator_policy_signed: bool, creator_veto: bool = False) -> dict:
    """Move a previously screened visible proposal to active only under signed policy."""
    if creator_veto:
        return {"ok": False, "status": "blocked_30d", "reason": "Creator veto"}
    if not creator_policy_signed or not isinstance(proposal, Mapping) or proposal.get("status") != "proposed" or proposal.get("visible") is not True:
        return {"ok": False, "status": "proposed", "reason": "signed policy and visible screened proposal required"}
    result = dict(proposal)
    result["status"] = "active"
    return {"ok": True, "status": "active", "goal": result}


def shield(urgent_signals, self_goal=None) -> dict:
    """Urgent owner/system signals always retain priority over self-goals."""
    urgent = [dict(item) for item in (urgent_signals or ()) if isinstance(item, Mapping) and item.get("urgent") is True]
    if urgent:
        return {"priority": "urgent", "items": urgent, "self_goal_deferred": bool(self_goal)}
    return {"priority": "self_goal" if self_goal else "idle", "items": [], "self_goal_deferred": False}


def aspiration_update(current: object, proposed: object, *, policy_signed: bool) -> dict:
    """Require Creator-signed limits and reject increases above 10% per period."""
    cur, nxt = _unit(current), _unit(proposed)
    if cur is None or nxt is None:
        return {"ok": False, "reason": "aspiration values must be 0..1"}
    if not policy_signed:
        return {"ok": False, "reason": "Creator-signed policy required"}
    if nxt > cur and (nxt - cur) / max(cur, 0.01) > MAX_ASPIRATION_CHANGE + 1e-9:
        return {"ok": False, "reason": "aspiration increase exceeds 10% per period"}
    return {"ok": True, "value": nxt}
