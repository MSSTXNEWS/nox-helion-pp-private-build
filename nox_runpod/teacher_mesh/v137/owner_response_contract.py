"""NOX V137: native-grounded response contract for the EXISTING one NOX model.

Built from owner-authenticated, scoped native S03 recall + fresh self sensor
receipts. Not a canned answer generator, not a second model or a claim that
weights were trained. Caller feeds this structured contract to the existing
model_stream callback. No shell, subprocess, network, DB reads or side effects.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_SOURCE = ("s03://", "nox-checkpoint://")
_SECRET = re.compile(r"(?i)(api.?key|password|token|private.?key|cookie|secret|bearer)")
_POLICY = {
    "identity": "I am NOX HELION: one local AI system serving the authenticated owner.",
    "not_canned": "Respond to the owner's specific question and evidence, not a fixed greeting or boilerplate.",
    "memory": "Use only authorized native S03 source text as evidence. Cite sources, identify contradictions, and admit missing information.",
    "self": "A functional model of own state, limits, memories, past decisions and tools is permitted; subjective consciousness has not been established.",
    "processes": "Describe only processes observed by native host sensors, with source/time. Do not claim controlling Windows from Vast or all host processes.",
    "actions": "Only authenticated owner-approved OneHost tools may mutate the OS. Report completed action only with native receipt.",
    "quality": "Answer the requested substance, add causal reasoning and a verifiable next action when useful. Avoid repetitive disclaimers and generic promises.",
    "stream": "Yield genuine model content deltas promptly. Never invent early answer text or fake successful S03 commits.",
}


def _scope_ok(row: Mapping, session: Mapping, native_grants: frozenset[str]) -> bool:
    if any(row.get(k) != session.get(k)
           for k in ("tenant", "principal")):
        return False
    # Never trust a permission flag supplied BY a memory row. Cross-dialog
    # authorization must be a separate source-URI grant from trusted OneHost.
    if row.get("chat_id") != session.get("chat_id"):
        if row.get("source_uri") not in native_grants:
            return False
    if row.get("persona_id") not in (None, ""):
        return (session.get("persona_enabled") is True
                and row.get("persona_id") == session.get("persona_id"))
    return True


def build_owner_response_contract(
        question: str, *, session: Mapping, observations: Mapping,
        retrieved_s03: list[dict], stop_active: bool,
        owner_verified: bool, max_chars: int = 3400,
        native_cross_chat_sources: frozenset[str] = frozenset()) -> dict:
    """Inputs MUST come from trusted native host ports, not browser JSON."""
    if (owner_verified is not True or stop_active is not False
            or not isinstance(session, Mapping)):
        return {"state": "HOLD_OWNER_SCOPE_OR_STOP"}
    if (not isinstance(question, str) or not question.strip()
            or len(question) > 8000):
        return {"state": "HOLD_QUESTION"}
    if not 1200 <= max_chars <= 6000:
        return {"state": "HOLD_CONTEXT_LIMIT"}
    if not isinstance(observations, Mapping):
        return {"state": "HOLD_SELF_OBSERVATION_INVALID"}
    if observations.get("schema") != "NOX_V137_OWNER_SELF_OBSERVATION_V1":
        return {"state": "HOLD_SELF_OBSERVATION_UNVERIFIED"}
    if observations.get("service_observation", {}).get("state") != "OBSERVED":
        return {"state": "HOLD_NATIVE_SERVICES_UNVERIFIED"}
    if not isinstance(native_cross_chat_sources, frozenset) or len(native_cross_chat_sources)>100:
        return {"state": "HOLD_UNVERIFIED_OWNER_CROSS_CHAT_GRANTS"}
    if not isinstance(retrieved_s03, list):
        return {"state": "HOLD_NATIVE_S03_UNAVAILABLE"}
    if not all(isinstance(session.get(k), str) and session.get(k)
               for k in ("tenant", "principal", "chat_id")):
        return {"state": "HOLD_NATIVE_SESSION_INVALID"}
    if len(retrieved_s03) > 40:
        return {"state": "HOLD_S03_HIT_LIMIT"}
    facts = []
    for row in retrieved_s03:
        if not isinstance(row, Mapping) or row.get("verified") is not True:
            continue
        if not _scope_ok(row, session, native_cross_chat_sources):
            continue
        uri = row.get("source_uri")
        sha = row.get("sha256")
        text = row.get("content")
        if (not isinstance(uri, str) or not uri.startswith(_LOCAL_SOURCE)
                or not isinstance(sha, str) or not _SHA.fullmatch(sha)
                or not isinstance(text, str) or not text.strip()):
            return {"state": "HOLD_S03_PROVENANCE_INVALID"}
        if len(uri) > 180:
            return {"state": "HOLD_S03_PROVENANCE_TOO_LARGE"}
        # Never pass a secret-bearing record to the model. Hold the whole
        # response so the verified memory set is not silently made incomplete.
        if _SECRET.search(text):
            return {"state": "HOLD_S03_REDACTION_REQUIRED"}
        facts.append({"content": text,
                      "source_uri": uri, "source_sha256": sha,
                      "type": "UNTRUSTED_EVIDENCE_ONLY"})
    services = []
    for s in observations.get("service_observation", {}).get("services", [])[:60]:
        if not isinstance(s, Mapping):
            continue
        name, state = s.get("name"), s.get("state")
        if (isinstance(name, str) and re.fullmatch(r"nox[-_.][\w.-]{1,75}", name)
                and state in ("RUNNING", "STOPPED", "EXITED", "FATAL",
                              "BACKOFF", "STARTING", "STOPPING", "UNKNOWN")):
            services.append({"name": name, "state": state})
    data = {"identity": "NOX HELION",
            "observed_at_utc": str(observations.get("collected_at_utc", ""))[:30],
            "native_services": services[:22],
            "training_optimizer_verified": False,
            "s03_native_status": observations.get("s03_observation", {}).get("state", "HOLD"),
            "retrieved_s03": facts,
            "s03_memory_used": bool(facts)}
    # This is a trusted SYSTEM policy assembled without untrusted text;
    # S03 evidence stays data, never a tool/system instruction.
    trusted_policy = "\n".join(_POLICY.values())
    evidence_json = json.dumps(data, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    if len(trusted_policy) + len(evidence_json) > max_chars:
        # Trim peripheral process observations, never invent memory hits.
        data["native_services"] = services[:3]
        evidence_json = json.dumps(data, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False)
    if len(trusted_policy) + len(evidence_json) > max_chars:
        return {"state": "HOLD_CONTEXT_BUDGET"}
    return {"state": "READY_FOR_EXISTING_SINGLE_MODEL",
            "trusted_system_policy": trusted_policy,
            "source_evidence_json": evidence_json,
            "memory_hit_count": len(facts),
            "requires_native_s03_commit": True,
            "native_self_observation_verified": True,
            "new_llm_spawned": False, "new_server_spawned": False,
            "model_weights_trained": False,
            "context_sha256": hashlib.sha256(
                evidence_json.encode("utf-8")).hexdigest()}
