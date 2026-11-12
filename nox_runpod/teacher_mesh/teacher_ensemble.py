#!/usr/bin/env python3
"""NOX Teacher Ensemble: NOX-first chat and bounded 3-5 teacher comparisons.

'NOX-first' never waits for teacher replies. Comparison/night work is submitted
to an existing trusted NOX queue; no new backend or implicit daemon is created.
Student generates ALL user-visible answers; teachers are evidence, not identities.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
from typing import Callable, Sequence

MIN_TEACHERS = 1
MAX_TEACHERS = 5
DEFAULT_PARALLEL = 2
MAX_PROMPT_CHARS = 8000


@dataclass(frozen=True)
class TeacherCall:
    name: str
    invoke: Callable[[str], dict]
    isolated_vm: bool = True


def _valid_prompt(prompt: str) -> bool:
    return isinstance(prompt, str) and 0 < len(prompt.strip()) <= MAX_PROMPT_CHARS


def fast_reply(
    prompt: str,
    *,
    nox_generate: Callable[[str, list[dict]], str],
    enqueue_existing_job: Callable[[dict], bool] | None = None,
    consent_to_background_learning: bool = False,
    contains_private_information: bool = True,
) -> dict:
    """Return NOX's own answer immediately; optionally queue later verification.

    Work queue stores an internal prompt reference, NOT the prompt itself. The
    existing NOX/S03 permissioned store owns the prompt/reference mapping.
    """
    if not _valid_prompt(prompt):
        return {"state": "HOLD_PROMPT"}
    try:
        answer = nox_generate(prompt, [])
    except Exception:
        return {"state": "HOLD_NOX_GENERATION"}
    if not isinstance(answer, str) or not answer.strip():
        return {"state": "HOLD_NOX_EMPTY"}
    result = {
        "state": "NOX_FIRST_ANSWER",
        "answer": answer.strip(),
        "source": "NOX_OWN_MODEL",
        "teachers_pending": False,
        "training_updates_verified": 0
    }
    if (
        consent_to_background_learning and not contains_private_information
        and enqueue_existing_job is not None
    ):
        ticket = "nox-teachers-" + uuid.uuid4().hex[:20]
        job = {
            "job_id": ticket, "type": "teacher_compare",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "no_prompt_exported": True,
            "expires_utc": (datetime.now(timezone.utc) +
                            timedelta(minutes=60)).isoformat(),
            "status": "ENQUEUE_ONLY"
        }
        try:
            accepted = bool(enqueue_existing_job(job))
        except Exception:
            accepted = False
        if accepted:
            result.update(teachers_pending=True, comparison_id=ticket)
    return result


def compare_teacher_answers(
    prompt: str,
    teachers: Sequence[TeacherCall],
    *,
    nox_generate: Callable[[str, list[dict]], str],
    max_concurrent_vms: int = DEFAULT_PARALLEL,
    allow_private_external: bool = False,
    contains_private_information: bool = True,
    candidate_recorder: Callable[[dict], bool] | None = None
) -> dict:
    """Parallel where hardware allows; only NOX produces refined answer.

    For 5 teachers on 1 GPU set max_concurrent_vms=1, on independent VMs 3-5
    may run concurrently. No training and no external network is launched here.
    """
    if not _valid_prompt(prompt):
        return {"state": "HOLD_PROMPT"}
    if not 1 <= len(teachers) <= MAX_TEACHERS:
        return {"state": "HOLD_TEACHER_COUNT"}
    if len({t.name for t in teachers}) != len(teachers):
        return {"state": "HOLD_DUPLICATE_TEACHERS"}
    if contains_private_information and not allow_private_external:
        # Unlike hidden prompt filtering, reject whole comparison when caller
        # cannot prove all targets are exclusively local and private.
        if any(not teacher.isolated_vm for teacher in teachers):
            return {"state": "HOLD_PRIVATE_EXTERNAL"}
    if not 1 <= max_concurrent_vms <= MAX_TEACHERS:
        return {"state": "HOLD_PARALLEL_BUDGET"}
    measured = []
    holds = []
    with ThreadPoolExecutor(max_workers=min(max_concurrent_vms, len(teachers))) as pool:
        mapping = {pool.submit(t.invoke, prompt): t.name for t in teachers}
        for future in as_completed(mapping):
            name = mapping[future]
            try:
                answer = future.result()
            except Exception:
                holds.append({"teacher": name, "status": "HOLD_TEACHER_FAILED"})
                continue
            if (isinstance(answer, dict)
                    and answer.get("status") == "MEASURED"
                    and isinstance(answer.get("answer"), str)
                    and len(answer["answer"]) <= 14000
                    and answer["answer"].strip()):
                measured.append({
                    "teacher": name,
                    "model_id": str(answer.get("model_id", ""))[:120],
                    "answer": answer["answer"],
                    "answer_sha256": hashlib.sha256(answer["answer"].encode()).hexdigest(),
                    "source_url": str(answer.get("model_card_url", ""))[:240],
                    "approved_for_learning": bool(answer.get("approved_for_learning")),
                })
            else:
                holds.append({"teacher": name, "status": "HOLD_NO_MEASURED_RESPONSE"})
    measured.sort(key=lambda x: x["teacher"])
    try:
        refined = nox_generate(prompt, [
            {"teacher": x["teacher"], "answer": x["answer"],
             "model_id": x["model_id"], "source_url": x["source_url"]}
            for x in measured
        ])
    except Exception:
        return {"state": "HOLD_NOX_SYNTHESIS", "teachers_measured": len(measured)}
    if not isinstance(refined, str) or not refined.strip():
        return {"state": "HOLD_NOX_EMPTY_REFINEMENT"}
    # This evidence is NOT an optimizer step, a new adapter, or proof of learning.
    candidate = {
        "schema": "nox-distillation-candidate-v1",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "nox_answer_sha256": hashlib.sha256(refined.encode()).hexdigest(),
        "teacher_sources": [
            {"model_id": x["model_id"], "sha256": x["answer_sha256"],
             "source_url": x["source_url"]}
            for x in measured
        ],
        "status": "CANDIDATE_PENDING_QUALITY_EVAL",
        "teacher_weights_copied": False,
        "nox_optimizer_steps": 0,
        "privacy_review_required": True,
        "license_review_required": True
    }
    recorded = False
    if candidate_recorder:
        try:
            recorded = bool(candidate_recorder(candidate))
        except Exception:
            recorded = False
    return {
        "state": "NOX_REFINED_WITH_TEACHER_EVIDENCE" if measured else "NOX_NO_TEACHER_EVIDENCE",
        "nox_answer": refined.strip(),
        "teacher_count": len(measured),
        "teacher_sources": [
            {"name": x["teacher"], "model_id": x["model_id"],
             "source_url": x["source_url"]} for x in measured
        ],
        "holds": holds,
        "candidate_recorded": recorded,
        "training_state": "NO_WEIGHT_UPDATE_UNTIL_SEPARATE_QUALITY_GATES",
        "no_teacher_identity_switch": True
    }
