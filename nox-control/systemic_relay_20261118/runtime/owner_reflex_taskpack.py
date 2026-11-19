"""Deterministic, non-authoritative successor builder for native Reflex drift.

This module DOES NOT issue native jobs or create OWNER_REVIEWED manifests.
It prepares an exact, auditable draft; owner review and the existing fenced
manifest CAS remain the only routes to executable task admission.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX = 3


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()


def propose_successor(manifest, monitor, source_pins):
    """Build up to three source-drift mission revisions from observed pins.

    Never self-reviews: emitted object uses explicit PROPOSAL_ONLY authority,
    not the manifest's OWNER_REVIEWED acceptance fields.
    """
    if not isinstance(manifest, dict) or not isinstance(monitor, dict):
        raise ValueError("HOLD_REFLEX_INPUT")
    if not isinstance(source_pins, dict):
        raise ValueError("HOLD_REFLEX_SOURCE_PINS")
    if monitor.get("schema") != "NOX_NATIVE_REFLEX_MONITOR_V1":
        raise ValueError("HOLD_REFLEX_MONITOR_SCHEMA")
    candidates = monitor.get("staged_research_candidates", [])
    missions = manifest.get("missions", [])
    if not isinstance(candidates, list) or not isinstance(missions, list):
        raise ValueError("HOLD_REFLEX_CANDIDATES")
    selected, decisions, seen = [], [], set()
    for candidate in candidates[:MAX]:
        if not isinstance(candidate, dict):
            raise ValueError("HOLD_REFLEX_CANDIDATE")
        fingerprint = candidate.get("fingerprint")
        if (not isinstance(fingerprint, str) or not SHA.fullmatch(fingerprint)
                or fingerprint in seen):
            raise ValueError("HOLD_REFLEX_FINGERPRINT")
        seen.add(fingerprint)
        if candidate.get("authority") != "RESEARCH_PROPOSAL_ONLY":
            raise ValueError("HOLD_REFLEX_AUTHORITY")
        if candidate.get("hypothesis") != "REBASE_AGAINST_OBSERVED_SOURCE_DRIFT":
            decisions.append({"fingerprint": fingerprint, "state": "NEEDS_INVESTIGATION"})
            continue
        matches = [m for m in missions if isinstance(m, dict)
                   and m.get("mission_id") == candidate.get("mission_id")
                   and m.get("parent_task_id") == candidate.get("parent_task_id")
                   and m.get("root_id") == candidate.get("root_id")]
        if len(matches) != 1:
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_MISSION_BINDING"})
            continue
        mission = matches[0]
        root = mission["root_id"]
        observed = source_pins.get(root)
        if not isinstance(observed, dict):
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_SOURCE_ROOT"})
            continue
        old_rows = mission.get("context", [])
        if not isinstance(old_rows, list) or not old_rows:
            raise ValueError("HOLD_REFLEX_CONTEXT")
        new_context = []
        for row in old_rows:
            if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
                raise ValueError("HOLD_REFLEX_CONTEXT")
            pin = observed.get(row["path"])
            if not isinstance(pin, str) or not SHA.fullmatch(pin):
                break
            new_context.append({"path": row["path"], "sha256": pin})
        if len(new_context) != len(old_rows):
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_SOURCE_MISSING"})
            continue
        observed_in_candidate = candidate.get("observed_sources")
        if (not isinstance(observed_in_candidate, list)
                or any(not isinstance(r, dict)
                       or observed.get(r.get("path")) != r.get("observed_sha256")
                       for r in observed_in_candidate)):
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_OBSERVATION_STALE"})
            continue
        if new_context == old_rows:
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_NO_SOURCE_CHANGE"})
            continue
        next_revision = mission.get("revision")
        if type(next_revision) is not int or not 1 <= next_revision < 10**9:
            raise ValueError("HOLD_REFLEX_REVISION")
        proposal = deepcopy(mission)
        proposal["revision"] = next_revision + 1
        proposal["context"] = new_context
        selected.append(proposal)
        decisions.append({"fingerprint": fingerprint, "state": "DRAFT_REQUIRES_OWNER_REVIEW",
                          "mission_id": mission["mission_id"],
                          "source_pins_sha256": _digest(new_context)})
    return {"schema": "NOX_NATIVE_REFLEX_DRAFT_TASKPACK_V1",
            "authority": "PROPOSAL_ONLY",
            "automatic_owner_approval": False,
            "native_jobs_created": 0,
            "base_manifest_sha256": _digest(manifest),
            "monitor_observation_sha256": monitor.get("observation_sha256"),
            "draft_missions": selected,
            "decisions": decisions,
            "required_next_step": "INDEPENDENT_REVIEW_AND_OWNER_PINNED_MANIFEST_CAS"}
