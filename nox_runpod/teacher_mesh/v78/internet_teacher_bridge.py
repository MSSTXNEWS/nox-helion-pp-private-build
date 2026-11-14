"""NOX V78 internet teacher bridge for EXISTING OneHost, not a second chatbot.
Discovery is metadata-only. No private dialogue is sent without scoped owner consent.
S03 learning != neural weight update; full-weight distillation remains V39/FORGE gated.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable, Mapping
import hashlib
import json
import re

MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REVISION = re.compile(r"^[0-9a-f]{40}$")

@dataclass(frozen=True)
class TeacherPorts:
    discover_metadata: Callable[[str], Mapping]
    consent_for_external_prompt: Callable[[str, str], bool]
    safe_to_use_teacher: Callable[[str], bool]
    native_teacher_infer: Callable[[str, str], Mapping]
    independently_check: Callable[[str, str, str], Mapping]
    s03_write: Callable[[Mapping], Mapping]
    s03_verify: Callable[[Mapping, Mapping], bool]


def discover_candidate(model_id: str, *, metadata: Mapping, allowed_licenses=frozenset(("apache-2.0", "mit", "bsd-3-clause"))):
    """Review Hub metadata; never download weights or trust remote code."""
    if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
        return {"state": "HOLD_MODEL_ID"}
    if not isinstance(metadata, Mapping) or metadata.get("id") != model_id:
        return {"state": "HOLD_METADATA"}
    revision = metadata.get("sha")
    license_name = str(metadata.get("license", "")).lower()
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        return {"state": "HOLD_UNPINNED_REVISION"}
    if license_name not in allowed_licenses or metadata.get("gated") is not False:
        return {"state": "HOLD_LICENSE_OR_GATED"}
    if metadata.get("trust_remote_code") is True:
        return {"state": "HOLD_REMOTE_CODE"}
    return {"state": "CANDIDATE_REVIEWED_NOT_INSTALLED",
            "model_id": model_id, "revision": revision, "license": license_name,
            "downloaded": False, "loaded": False, "training_started": False}


def consult_teacher(*, model_id: str, question: str, conversation_scope: str,
                    ports: TeacherPorts, owner_approved: bool = False,
                    prompt_contains_private_s03: bool = False):
    """Bounded consult: one external response, independent check, S03 receipt."""
    if not isinstance(question, str) or not 1 <= len(question) <= 12000:
        return {"state": "HOLD_QUESTION"}
    if not isinstance(conversation_scope, str) or not 3 <= len(conversation_scope) <= 128:
        return {"state": "HOLD_SCOPE"}
    if prompt_contains_private_s03 or owner_approved is not True:
        return {"state": "HOLD_PRIVACY_OR_OWNER_APPROVAL"}
    if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
        return {"state": "HOLD_MODEL_ID"}
    try:
        if ports.safe_to_use_teacher(model_id) is not True:
            return {"state": "HOLD_NATIVE_RESOURCE_OR_STOP"}
        if ports.consent_for_external_prompt(conversation_scope, model_id) is not True:
            return {"state": "HOLD_SCOPED_CONSENT"}
        response = ports.native_teacher_infer(model_id, question)
        answer = response.get("answer") if isinstance(response, Mapping) else None
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000:
            return {"state": "HOLD_TEACHER_RESPONSE"}
        evidence = ports.independently_check(question, answer, model_id)
        if not isinstance(evidence, Mapping) or evidence.get("verified") is not True:
            return {"state": "HOLD_TEACHER_UNVERIFIED"}
        score = evidence.get("score")
        if isinstance(score, bool) or not isinstance(score, (float, int)) or not 0 <= score <= 1:
            return {"state": "HOLD_EVALUATION"}
        source = evidence.get("source_uri")
        if not isinstance(source, str) or not source.startswith("https://"):
            return {"state": "HOLD_SOURCE_PROVENANCE"}
        record = {"schema": "NOX_V78_TEACHER_EXPERIENCE",
                  "scope": conversation_scope, "teacher": model_id,
                  "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                  "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                  "evidence_source": source, "score": float(score),
                  "neural_weights_changed": False,
                  "requires_independent_holdout_before_forge": True}
        receipt = ports.s03_write(record)
        if not isinstance(receipt, Mapping) or ports.s03_verify(receipt, record) is not True:
            return {"state": "HOLD_S03_NOT_DURABLE", "teacher_answer_verified": True}
        return {"state": "TEACHER_HELP_AND_S03_VERIFIED", "answer": answer,
                "teacher": model_id, "source": source,
                "s03_receipt": str(receipt.get("id", ""))[:100],
                "neural_weights_changed": False}
    except Exception:
        return {"state": "HOLD_NATIVE_TEACHER_ERROR"}


def discovery_via_existing_native_port(model_id: str, metadata_callback: Callable[[str], Mapping]):
    """Owner-managed HF metadata callback; caller enforces network allowlist and timeouts."""
    if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
        return {"state": "HOLD_MODEL_ID"}
    try:
        return discover_candidate(model_id, metadata=metadata_callback(model_id))
    except Exception:
        return {"state": "HOLD_NETWORK_OR_METADATA"}
