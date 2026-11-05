"""NOX GROWTH FORGE: proactive learning, role ideas and module candidates.

This is an additive component for the EXISTING OneHost/P02/S03. Eight existing
Core roles propose skills, subroles, UI routes and modules. Findings remain
untrusted; the model cannot execute downloaded code, extend its own ACL or
install to the real host. A persisted native owner policy may allow automatic
knowledge ingestion and sandbox evaluation, not unreviewed production merges.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re

from .worms import ROLES, WormHold, plan_day, role_mood

KINDS = frozenset({"skill", "subrole", "menu_button", "module", "design",
                   "market", "benchmark", "learning_plan"})
OPEN_LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
                           "ISC", "CC0-1.0", "PUBLIC_DOMAIN"})
_SHA = re.compile(r"^[0-9a-f]{64}$")
_HEAD = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID = re.compile(r"^[a-z][a-z0-9._:-]{1,79}$")


def start_on_boot(now: datetime, *, source_head=None):
    """Immediately plan the work of all existing roles; never fake a fetch."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise WormHold("NOX_BOOT_CLOCK_REQUIRED")
    if source_head is not None and (not isinstance(source_head, str) or
                                    not _HEAD.fullmatch(source_head)):
        raise WormHold("NOX_EXACT_SOURCE_HEAD_REQUIRED")
    planned = plan_day(now.astimezone(timezone.utc))
    return {
        "schema": "NOX-GROWTH-STARTUP-v1",
        "state": "PLANNED_AWAITING_OWNER_POLICY_OR_NATIVE_CONNECTOR",
        "at_utc": now.astimezone(timezone.utc).isoformat(),
        "head": source_head,
        "planned_tasks": len(planned),
        "by_role": {role: sum(t.core_id == role for t in planned) for role in ROLES},
        "first_tasks": [
            {"task_id": t.task_id, "core_id": t.core_id, "topic": t.topic,
             "provider": t.provider} for t in planned[:8]
        ],
        "fetched_sources": 0, "weights_updated": False, "code_installed": False,
    }


def candidate_from_evidence(observation: dict, *, source_head: str, owner_core: str,
                            kind: str, target_id: str, description: str,
                            benefit: int, readiness: int, reuse: int, risk: int,
                            effort_minutes: int):
    """Ranking is advisory; only observed, provenance-tagged sources qualify."""
    if not isinstance(observation, dict) or observation.get("schema") != "NOX-WORM-SOURCE-OBSERVATION-v1":
        raise WormHold("GROWTH_WORM_RECEIPT_REQUIRED")
    if (observation.get("status") != "SOURCE_OBSERVED_REVIEW_REQUIRED" or
            observation.get("code_executed") is not False or
            observation.get("weights_updated") is not False):
        raise WormHold("GROWTH_UNTRUSTED_SOURCE")
    sha = observation.get("source_sha256")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise WormHold("GROWTH_SOURCE_HASH_REQUIRED")
    if (not isinstance(source_head, str) or not _HEAD.fullmatch(source_head) or
            owner_core not in ROLES or kind not in KINDS or
            not isinstance(target_id, str) or not _ID.fullmatch(target_id) or
            not isinstance(description, str) or not 15 <= len(description) <= 1200 or
            any(ord(c) < 32 or ord(c) == 127 for c in description)):
        raise WormHold("GROWTH_APPROVED_SCOPE_REQUIRED")
    if type(effort_minutes) is not int or not 1 <= effort_minutes <= 480:
        raise WormHold("GROWTH_EFFORT_OUT_OF_RANGE")
    for metric in (benefit, readiness, reuse, risk):
        if type(metric) is not int or not 0 <= metric <= 5:
            raise WormHold("GROWTH_SCORING_REQUIRED")
    signature = json.dumps([source_head, sha, owner_core, kind, target_id],
                           separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    license_type = observation.get("license")
    return {
        "schema": "NOX-GROWTH-CANDIDATE-v1",
        "candidate_id": digest[:32], "candidate_sha256": digest,
        "kind": kind, "target_id": target_id,
        "owner_core": owner_core, "source_head": source_head,
        "source_id": observation.get("source_id"),
        "url": observation.get("url"), "source_sha256": sha,
        "description": description,
        "score": benefit * 4 + readiness * 3 + reuse * 4 - risk * 5,
        "effort_minutes": effort_minutes,
        "license": license_type,
        "license_checked": license_type in OPEN_LICENSES,
        "state": "SANDBOX_CANDIDATE_REVIEW_REQUIRED",
        "requires_source_diff": kind in {"module", "menu_button", "skill", "subrole"},
        "source_executed": False, "host_modified": False,
        "new_core_id_created": False, "weights_updated": False,
        "native_owner_grant_required": True,
    }


def decide_candidate(candidate: dict, *, owner_policy: dict, checks: dict):
    """NOX decides autonomously within bounded *pre-approved* authority.

    Eligible read-only research facts may pass to S03 after consented, audited
    provenance checks; data-only proposals may enter a disposable sandbox.
    Live code/menus/weights/permissions never auto-merge or auto-install.
    """
    if not isinstance(candidate, dict) or candidate.get("schema") != "NOX-GROWTH-CANDIDATE-v1":
        raise WormHold("GROWTH_CANDIDATE_REQUIRED")
    if not isinstance(owner_policy, dict) or not isinstance(checks, dict):
        raise WormHold("GROWTH_NATIVE_POLICY_REQUIRED")
    sealed = owner_policy.get("native_signed") is True
    source_ok = checks.get("sha256") is True and checks.get("provenance") is True
    licence_ok = candidate.get("license_checked") is True and checks.get("license") is True
    # Research text is inert data: exact provenance + licence + native policy
    # permit automatic scoped S03 learning, without downloaded binaries.
    if not (sealed and source_ok and licence_ok):
        return {"decision": "HOLD", "reason": "SOURCE_LICENSE_OR_SECURITY_HOLD",
                "live_install": False, "training_started": False}
    if owner_policy.get("allow_research_memory") is True and candidate["kind"] in {"market", "benchmark", "learning_plan", "design"}:
        return {"decision": "AUTO_ADMIT_RESEARCH_TO_EXISTING_S03",
                "requires_native_s03_readback": True, "live_install": False,
                "training_started": False}
    # Source-code candidates need additional quarantine, Defender review,
    # isolated tests and explicit release-owner authority; not mere AV pass.
    if owner_policy.get("allow_disposable_sandbox") is True:
        if (checks.get("defender_reviewed") is True and
                checks.get("isolated_tests_passed") is True and
                checks.get("source_diff") is True):
            return {"decision": "AUTO_STAGE_SANDBOX_CANDIDATE",
                    "requires_owner_release_merge": True, "live_install": False,
                    "training_started": False}
    return {"decision": "OWNER_REVIEW_REQUIRED", "reason": "EXPLICIT_NATIVE_HOST_ACTION",
            "live_install": False, "training_started": False}


def learning_request(*, source_count: int, verified_examples: int, base_model_sha=None,
                     gpu_report=None, native_owner_policy=None):
    """Ask for actual missing prerequisites; never claim self-modified weights."""
    if any(type(v) is not int or v < 0 for v in (source_count, verified_examples)):
        raise WormHold("GROWTH_LEARNING_METRICS_INVALID")
    need = []
    if source_count == 0:
        need.append("VERIFIED_S03_SOURCES")
    if verified_examples < 20:
        need.append("TRAIN_VALIDATION_DATASET_AND_RIGHTS")
    if not isinstance(base_model_sha, str) or not _SHA.fullmatch(base_model_sha):
        need.append("APPROVED_BASE_MODEL_SHA")
    if not isinstance(gpu_report, dict) or gpu_report.get("status") != "HARDWARE_READY_ONLY":
        need.append("REAL_GPU_VRAM_CUDA_PREFLIGHT")
    if not isinstance(native_owner_policy, dict) or native_owner_policy.get("training_consent") is not True:
        need.append("OWNER_NATIVE_TRAINING_CONSENT")
    return {
        "schema": "NOX-GROWTH-TRAINING-REQUEST-v1",
        "state": "PROPOSED_AWAITING_PREREQUISITES" if need else "READY_TO_REQUEST_EXISTING_P04",
        "missing": need, "verified_examples": verified_examples,
        "training_engine": "Packages/P04/train_qlora.py",
        "weights_updated": False, "training_started": False,
        "request_native_P04_preflight": len(need) == 0,
    }


def persona_state(*, worm_status: dict, memories_count: int, wins: int):
    """Living expressive persona UI with real evidence, not a sentience claim."""
    if type(memories_count) is not int or type(wins) is not int or memories_count < 0 or wins < 0:
        raise WormHold("GROWTH_PERSONA_METRICS_INVALID")
    mood = role_mood(worm_status)
    return {**mood, "memory_facts": memories_count, "verified_improvements": wins,
            "self_awareness_claimed": False, "new_persona_identity": False}
