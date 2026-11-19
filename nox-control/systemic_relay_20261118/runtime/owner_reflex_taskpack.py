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
MAX_OBSERVED = 64  # Bound investigation, not just selected executable drafts.


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
    if len(candidates) > MAX_OBSERVED:
        raise ValueError("HOLD_REFLEX_CANDIDATE_BOUND")
    selected, decisions, seen, selected_missions = [], [], set(), set()
    for candidate in candidates:
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
        identity = (mission["root_id"], mission["parent_task_id"], mission["mission_id"])
        if identity in selected_missions:
            decisions.append({"fingerprint": fingerprint,
                              "state": "HOLD_DUPLICATE_MISSION_CANDIDATE"})
            continue
        if len(selected) >= MAX:
            decisions.append({"fingerprint": fingerprint, "state": "DRAFT_CAPACITY_WAIT"})
            continue
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
        editable = mission.get("editable_paths")
        if (not isinstance(editable, list) or not editable or
                len(set(editable)) != len(editable)):
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_EDITABLE_SCOPE"})
            continue
        changed_paths = {row["path"] for old, row in zip(old_rows, new_context)
                         if old["sha256"] != row["sha256"]}
        if not changed_paths or not changed_paths.issubset(editable):
            # Tests and immutable context pins are never silently rebased.
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_UNREVIEWED_CONTEXT_DRIFT"})
            continue
        if not any(r.get("path") in changed_paths for r in observed_in_candidate):
            decisions.append({"fingerprint": fingerprint, "state": "HOLD_OBSERVATION_MISSING_CHANGED_SOURCE"})
            continue
        next_revision = mission.get("revision")
        if type(next_revision) is not int or not 1 <= next_revision < 10**9:
            raise ValueError("HOLD_REFLEX_REVISION")
        proposal = deepcopy(mission)
        proposal["revision"] = next_revision + 1
        proposal["context"] = new_context
        defect = proposal.get("defect")
        if isinstance(defect, dict):
            prior = defect.get("observed_source_sha256")
            match = [row["path"] for row in old_rows
                     if row["sha256"] == prior and row["path"] in editable]
            if len(match) != 1:
                decisions.append({"fingerprint": fingerprint, "state": "HOLD_DEFECT_SOURCE_NOT_EDITABLE"})
                continue
            next_pin = next(row["sha256"] for row in new_context
                           if row["path"] == match[0])
            defect["observed_source_sha256"] = next_pin
        selected.append(proposal)
        selected_missions.add(identity)
        decisions.append({"fingerprint": fingerprint, "state": "DRAFT_REQUIRES_OWNER_REVIEW",
                          "mission_id": mission["mission_id"],
                          "source_pins_sha256": _digest(new_context)})
    base_sha = _digest(manifest)
    draft = deepcopy(manifest)
    revision = draft.get("revision")
    if type(revision) is int and 1 <= revision < 10**9:
        draft["revision"] = revision + 1
        draft["previous_manifest_sha256"] = base_sha
        for proposal in selected:
            replaced = False
            for index, mission in enumerate(draft["missions"]):
                if (mission.get("mission_id") == proposal["mission_id"]
                        and mission.get("parent_task_id") == proposal["parent_task_id"]):
                    draft["missions"][index] = proposal
                    replaced = True
                    break
            if not replaced:
                raise ValueError("HOLD_REFLEX_DRAFT_IDENTITY")
        draft["review_origin"] = "UNREVIEWED_REFLEX_DRAFT"
        draft["acceptance_scope"] = "DRAFT_ONLY"
        draft["original_task_accepted"] = False
    else:
        draft = None
    return {"schema": "NOX_NATIVE_REFLEX_DRAFT_TASKPACK_V1",
            "authority": "PROPOSAL_ONLY",
            "draft_manifest": draft,
            "draft_manifest_sha256": _digest(draft) if draft is not None else None,
            "review_origin": "UNREVIEWED_REFLEX_DRAFT",
            "automatic_owner_approval": False,
            "native_jobs_created": 0,
            "base_manifest_sha256": _digest(manifest),
            "monitor_observation_sha256": monitor.get("observation_sha256"),
            "draft_missions": selected,
            "decisions": decisions,
            "required_next_step": "INDEPENDENT_REVIEW_AND_OWNER_PINNED_MANIFEST_CAS"}

def finalize_after_owner_review(taskpack, reviewed_draft_sha256, validate_manifest):
    """Owner-authenticated CAS transport alone may call this with its pinned SHA.

    Never call with a model-generated approval. This is a pure conversion,
    not an attestation/signature, file write or live queue admission.
    """
    if not isinstance(taskpack, dict) or taskpack.get("authority") != "PROPOSAL_ONLY":
        raise ValueError("HOLD_REFLEX_OWNER_REVIEW")
    proposal = taskpack.get("draft_manifest")
    if not isinstance(proposal, dict) or not taskpack.get("draft_missions"):
        raise ValueError("HOLD_REFLEX_EMPTY_REVIEW")
    candidate_pin = taskpack.get("draft_manifest_sha256")
    if (not isinstance(reviewed_draft_sha256, str)
            or not SHA.fullmatch(reviewed_draft_sha256)
            or candidate_pin != reviewed_draft_sha256
            or _digest(proposal) != reviewed_draft_sha256):
        raise ValueError("HOLD_REFLEX_REVIEWED_DRAFT_PIN")
    if (proposal.get("review_origin") != "UNREVIEWED_REFLEX_DRAFT"
            or proposal.get("acceptance_scope") != "DRAFT_ONLY"
            or proposal.get("original_task_accepted") is not False
            or proposal.get("previous_manifest_sha256") != taskpack.get("base_manifest_sha256")):
        raise ValueError("HOLD_REFLEX_REVIEWED_SCOPE")
    reviewed = deepcopy(proposal)
    reviewed["review_origin"] = "OWNER_REVIEWED"
    reviewed["acceptance_scope"] = "SOURCE_PATCH_TESTED"
    validate_manifest(reviewed)
    return {"schema": "NOX_NATIVE_REFLEX_REVIEWED_SUCCESSOR_V1",
            "reviewed_source_draft_sha256": reviewed_draft_sha256,
            "reviewed_manifest_sha256": _digest(reviewed),
            "manifest": reviewed,
            "original_task_accepted": False,
            "persistence": "REQUIRES_EXISTING_OWNER_PINNED_MANIFEST_CAS"}
