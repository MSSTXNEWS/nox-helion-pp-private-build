"""NOX V38: bounded parallel cognitive pulse for the EXISTING NOX chat route.

This module does not create another LLM, server, database, privileged shell, GPU
trainer, or claim consciousness. All native callbacks are supplied by OneHost.
Only the installed NOX model is permitted to generate user-visible answer text.
Untrusted model/teacher/memory text never gains tool authority here.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import threading
import time
from typing import Any

CORE_NAMES = {
    "C01": "PERCEPTION", "C02": "S03_MEMORY", "C03": "SELF_MODEL",
    "C04": "AFFECT", "C05": "PERSONA", "C06": "REASONING_ROUTER",
    "C07": "SKILLS_AND_TEACHERS", "C08": "ACTIONS_AND_WORMS",
}
MINI_KERNELS = {
    "C01": ("UTC_CLOCK", "LOCAL_TIME_IF_GRANTED", "LOCATION_IF_GRANTED", "GPU_SENSORS", "RAM_DISK", "ENVIRONMENT"),
    "C02": ("M0_WORKING", "M1_EPISODIC", "M2_KNOWLEDGE", "M3_TEMPORAL", "M4_SKILLS", "M5_PERSONAS", "M6_SIGNIFICANCE", "M7_AUTOBIOGRAPHY"),
    "C03": ("IDENTITY", "GENESIS", "CAPABILITIES", "LIMITS", "CONTINUITY", "GOALS"),
    "C04": ("USER_TONE", "EMPATHY", "INTEREST", "PREFERENCES", "UNCERTAINTY"),
    "C05": ("MASTER_PERSONA_SWITCH", "SELECTED_PERSONA", "VOICE_STYLE", "CONSISTENCY"),
    "C06": ("INTENT", "COMPLEXITY", "PLAN", "EVIDENCE", "RISK", "TIME_BUDGET"),
    "C07": ("TOOLS", "MODEL_CATALOG", "TEACHER_REGISTRY", "RAG", "EVALUATION"),
    "C08": ("STOP", "GPU_ADMISSION", "WORMS", "FORGE", "TASK_QUEUE", "CHECKPOINTS"),
}
MAX_INPUT = 8000
FORBIDDEN_KEYS = re.compile(r"(password|secret|token|api[_-]?key|private[_-]?key|authorization|cookie)", re.I)


@dataclass(frozen=True)
class Session:
    tenant: str
    principal: str
    chat_id: str
    language: str = "ru"
    persona_enabled: bool = False
    persona_id: str | None = None

    def validate(self) -> None:
        for v in (self.tenant, self.principal, self.chat_id):
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", v):
                raise ValueError("AUTHENTICATED_SESSION_REQUIRED")
        if self.language not in ("ru", "es", "en"):
            raise ValueError("LANGUAGE_NOT_ALLOWED")
        if self.persona_enabled and self.persona_id not in ("KV", "AM", "LA", "EV", "KW"):
            raise ValueError("PERSONA_CONFIG_MUST_COME_FROM_HOST")


@dataclass(frozen=True)
class NativePorts:
    """Trusted callbacks from existing OneHost, not from chat/memory content."""
    authorize: Callable[[Session], bool]
    stop: Callable[[], bool]
    sensors: Callable[[Session], Mapping[str, Any]] | None = None
    s03_recall: Callable[[Session, str, int], list[dict]] | None = None
    self_receipts: Callable[[Session], list[dict]] | None = None
    affect: Callable[[Session, str], Mapping[str, Any]] | None = None
    preferences: Callable[[Session], Mapping[str, Any]] | None = None
    available_skills: Callable[[Session], Mapping[str, Any]] | None = None
    queue_status: Callable[[Session], Mapping[str, Any]] | None = None
    memory_scope_authorize: Callable[[Session, Mapping[str, Any]], bool] | None = None


@dataclass(frozen=True)
class PulseConfig:
    fast_deadline_ms: int = 65
    deep_deadline_ms: int = 200
    max_workers: int = 4
    max_inflight: int = 12
    max_context_chars: int = 6400
    memory_hits: int = 8
    memory_deadline_ms: int = 650
    require_memory: bool = True

    def validate(self) -> None:
        if not 10 <= self.fast_deadline_ms <= 350 or not self.fast_deadline_ms <= self.deep_deadline_ms <= 2000:
            raise ValueError("BAD_DEADLINES")
        if not 1 <= self.max_workers <= 8 or not self.max_workers <= self.max_inflight <= 32:
            raise ValueError("BAD_PARALLEL_BOUNDS")
        if not 1000 <= self.max_context_chars <= 16000 or not 1 <= self.memory_hits <= 20:
            raise ValueError("BAD_CONTEXT_BOUNDS")
        if not self.fast_deadline_ms <= self.memory_deadline_ms <= 2500:
            raise ValueError("BAD_MEMORY_DEADLINE")


def _json_sanitize(value: Any, *, max_string: int = 500, depth: int = 0) -> Any:
    """Bounded context, no accidental secret fields or uncontrolled object repr."""
    if depth >= 5:
        return "DEPTH_LIMIT"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:max_string]
    if isinstance(value, Mapping):
        return {str(k)[:80]: _json_sanitize(v, max_string=max_string, depth=depth + 1)
                for k, v in list(value.items())[:40]
                if not FORBIDDEN_KEYS.search(str(k))}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(v, max_string=max_string, depth=depth + 1) for v in value[:40]]
    return "UNSUPPORTED_VALUE"


def _safe_call(fn: Callable | None, *args: Any) -> dict:
    if fn is None:
        return {"state": "NO_NATIVE_CALLBACK"}
    try:
        data = fn(*args)
    except Exception:
        return {"state": "NATIVE_CALLBACK_ERROR"}
    if not isinstance(data, Mapping):
        return {"state": "NATIVE_CALLBACK_INVALID"}
    return {"state": "OBSERVED", "data": _json_sanitize(data)}


class SynapticBrain:
    """One request travels through eight bounded groups in parallel.

    No trained model is loaded here; no independent OS processes are spawned.
    The executor is bounded. A failed/slow group gets a visible unavailable state
    instead of blocking generation indefinitely. Native writes are not in scope.
    """
    def __init__(self, ports: NativePorts, config: PulseConfig = PulseConfig()):
        config.validate()
        if not callable(ports.authorize) or not callable(ports.stop):
            raise TypeError("NATIVE_AUTH_AND_STOP_REQUIRED")
        self.ports = ports
        self.cfg = config
        self.pool = ThreadPoolExecutor(max_workers=config.max_workers,
                                       thread_name_prefix="nox-v38-cortex")
        self.inflight = threading.BoundedSemaphore(config.max_inflight)
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _gate(self, session: Session) -> bool:
        try:
            return self.ports.stop() is False and self.ports.authorize(session) is True
        except Exception:
            return False

    def _core(self, code: str, session: Session, prompt: str, timestamp: str) -> dict:
        p = self.ports
        if not self._gate(session):
            return {"state": "HOLD_OWNER_SCOPE_OR_STOP"}
        if code == "C01":
            return {"state": "OBSERVED", "utc": timestamp,
                    "sensors": _safe_call(p.sensors, session),
                    "location": "UNKNOWN_UNLESS_NATIVE_SENSOR_SUPPLIES_IT"}
        if code == "C02":
            if p.s03_recall is None:
                return {"state": "HOLD_S03_UNAVAILABLE"}
            try:
                records = p.s03_recall(session, prompt, self.cfg.memory_hits)
            except Exception:
                return {"state": "HOLD_S03_READ_ERROR"}
            if not isinstance(records, list):
                return {"state": "HOLD_S03_INVALID"}
            trusted = []
            scope = (session.tenant, session.principal, session.chat_id)
            for x in records[:min(4 * self.cfg.memory_hits, 50)]:
                if not isinstance(x, dict) or x.get("verified") is not True or x.get("superseded") is True:
                    continue
                record_scope = (x.get("tenant"), x.get("principal"), x.get("chat_id"))
                if record_scope[:2] != scope[:2]:
                    continue
                if record_scope[2] != scope[2]:
                    if p.memory_scope_authorize is None:
                        continue
                    try:
                        if p.memory_scope_authorize(session, x) is not True:
                            continue
                    except Exception:
                        continue
                # Persona-scoped events cannot leak into a different persona or
                # NOX's default identity. Owner-shared events have no PersonaID.
                persona = x.get("persona_id")
                if persona is not None and (not session.persona_enabled or persona != session.persona_id):
                    continue
                if x.get("segment") not in ("M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7"):
                    continue
                source = x.get("source_uri", "")
                if not isinstance(source, str) or not source.startswith(("s03://", "https://", "nox-checkpoint://")):
                    continue
                trusted.append({"segment": x["segment"], "text": str(x.get("content", ""))[:380],
                                "source": source[:260], "evidence_only": True})
                if len(trusted) >= self.cfg.memory_hits:
                    break
            return {"state": "OBSERVED", "hits": trusted, "hit_count": len(trusted)}
        if code == "C03":
            if p.self_receipts is None:
                return {"state": "NO_VERIFIED_SELF_RECEIPTS", "identity": "NOX HELION",
                        "consciousness_claim": "NOT_ESTABLISHED"}
            try:
                receipts = p.self_receipts(session)
            except Exception:
                return {"state": "SELF_LEDGER_UNAVAILABLE"}
            if not isinstance(receipts, list):
                return {"state": "SELF_LEDGER_INVALID"}
            valid = []
            for r in receipts[:30]:
                if not isinstance(r, dict) or r.get("native_verified") is not True:
                    continue
                if not re.fullmatch(r"[0-9a-fA-F]{64}", str(r.get("verified_sha256", ""))):
                    continue
                if r.get("kind") == "verified_birth" and not (r.get("optimizer_step_verified") and r.get("weights_reloaded")):
                    continue
                valid.append({"kind": str(r.get("kind", "event"))[:80],
                              "occurred_at": str(r.get("occurred_at", ""))[:45],
                              "sha256": r["verified_sha256"]})
            return {"state": "OBSERVED", "identity": "NOX HELION", "events": valid[:8],
                    "consciousness_claim": "NOT_ESTABLISHED"}
        if code == "C04":
            return {"state": "OBSERVED", "user_tone": _safe_call(p.affect, session, prompt),
                    "preferences": _safe_call(p.preferences, session),
                    "emotion_is_behavioral_signal": True}
        if code == "C05":
            return {"state": "OBSERVED", "master_persona_switch": session.persona_enabled,
                    "persona_id": session.persona_id if session.persona_enabled else None,
                    "unified_model": "NOX"}
        if code == "C06":
            x = prompt.casefold()
            intents = [name for name, patterns in (
                ("monitor", ("gpu", "гпу", "датчик", "статус", "состояни")),
                ("memory", ("вспомни", "помни", "память", "событи")),
                ("build", ("код", "патч", "внедри", "собери", "исправ")),
                ("reason", ("почему", "доказ", "сравни", "анализ")),
            ) if any(t in x for t in patterns)]
            return {"state": "OBSERVED", "intents": intents or ["conversation"],
                    "deep_mode_candidate": len(intents) >= 2 or len(prompt) > 1300,
                    "uncertainty": "ASK_MAIN_MODEL_TO_REPORT_UNVERIFIED_FACTS"}
        if code == "C07":
            return {"state": "OBSERVED", "skills": _safe_call(p.available_skills, session),
                    "teacher_policy": "ON_DEMAND_BACKGROUND_NO_UNAPPROVED_DOWNLOAD"}
        if code == "C08":
            return {"state": "OBSERVED", "stop": False,
                    "queue": _safe_call(p.queue_status, session),
                    "exec_from_chat": False, "owner_policy": "V37_NATIVE_ADMIN"}
        raise KeyError(code)

    def pulse(self, session: Session, prompt: str, *, deep: bool = False) -> dict:
        try:
            session.validate()
        except (ValueError, TypeError):
            return {"state": "HOLD_INVALID_SESSION"}
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= MAX_INPUT:
            return {"state": "HOLD_BAD_PROMPT"}
        if self._closed or not self._gate(session):
            return {"state": "HOLD_OWNER_SCOPE_OR_STOP"}
        started = time.perf_counter()
        deadline = (self.cfg.deep_deadline_ms if deep else self.cfg.fast_deadline_ms) / 1000
        utc = datetime.now(timezone.utc).isoformat()
        submitted = {}
        for name in CORE_NAMES:
            if not self.inflight.acquire(blocking=False):
                submitted[name] = None
                continue
            try:
                task = self.pool.submit(self._core, name, session, prompt, utc)
                task.add_done_callback(lambda _task: self.inflight.release())
                submitted[name] = task
            except RuntimeError:
                self.inflight.release()
                submitted[name] = None
        futures = [f for f in submitted.values() if f is not None]
        wait(futures, timeout=deadline)
        # C02 is a correctness dependency. Wait a bounded grace period for real
        # indexed native S03 retrieval; do not secretly skip memory to win TTFT.
        memory_future = submitted.get("C02")
        if (self.cfg.require_memory and memory_future is not None
                and not memory_future.done()):
            remaining = self.cfg.memory_deadline_ms / 1000 - (time.perf_counter() - started)
            if remaining > 0:
                wait([memory_future], timeout=remaining)
        results = {}
        for name, future in submitted.items():
            if future is None:
                results[name] = {"state": "HOLD_QUEUE_SATURATED"}
            elif future.done() and not future.cancelled():
                try:
                    results[name] = future.result()
                except Exception:
                    results[name] = {"state": "CORE_CALLBACK_ERROR"}
            else:
                future.cancel()
                results[name] = {"state": "DEADLINE_FALLBACK"}
        if not self._gate(session):
            return {"state": "HOLD_SCOPE_REVOKED"}
        if self.cfg.require_memory and results.get("C02", {}).get("state") != "OBSERVED":
            return {"state": "HOLD_MEMORY_NOT_READY", "memory_state": results.get("C02", {}).get("state"),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
        compact = {k: {"name": CORE_NAMES[k], "signals": results[k]} for k in CORE_NAMES}
        text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(text) > self.cfg.max_context_chars:
            # Preserve C02 memory and its provenance. Reduce peripheral signals
            # first; NEVER silently replace recalled memory by FALLBACK.
            for candidate in ("C07", "C04", "C08", "C01", "C06"):
                if len(text) <= self.cfg.max_context_chars:
                    break
                compact[candidate]["signals"] = {"state": "CONTEXT_BUDGET_FALLBACK"}
                text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
            # If needed, shorten long memories but retain actual verified events,
            # source URIs, M0–M7 labels, and exact per-persona scope.
            mem = compact["C02"]["signals"]
            if len(text) > self.cfg.max_context_chars and mem.get("state") == "OBSERVED":
                hits = mem.get("hits", [])
                for hit in hits:
                    hit["text"] = hit["text"][:160]
                text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                while len(text) > self.cfg.max_context_chars and len(hits) > 1:
                    hits.pop()
                    mem["hit_count"] = len(hits)
                    mem["context_trimmed"] = True
                    text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(text) > self.cfg.max_context_chars:
            return {"state": "HOLD_CONTEXT_TOO_LARGE"}
        return {"state": "READY_FOR_ONE_NOX_MODEL", "cores": results,
                "context_json": text,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "max_core_deadline_ms": int(deadline * 1000),
                "real_weight_updates": "NOT_MEASURED",
                "main_model_calls": 0}

    def stream(self, session: Session, prompt: str,
               model_stream: Callable[[str, dict], Iterator[str]],
               *, deep: bool = False) -> Iterator[dict]:
        """Forward REAL model deltas immediately, never fabricate a pre-answer.

        Host must supply existing NOX model.stream_generate, not a teacher model.
        The caller owns streaming/SSE and persistent S03 event receipts.
        """
        # UI can display a factual progress indicator immediately without
        # inventing a main-model draft or disclosing internal reasoning.
        yield {"type": "phase", "state": "INDEXED_S03_AND_CORTEX_CHECK"}
        context = self.pulse(session, prompt, deep=deep)
        if context.get("state") != "READY_FOR_ONE_NOX_MODEL":
            yield {"type": "hold", "state": context["state"]}
            return
        yield {"type": "cortex_ready", "elapsed_ms": context["elapsed_ms"],
               "cores_unavailable": [k for k, v in context["cores"].items()
                                      if v.get("state") != "OBSERVED"]}
        if not self._gate(session):
            yield {"type": "hold", "state": "HOLD_SCOPE_REVOKED"}
            return
        try:
            source = model_stream(prompt, {"cognitive_context": context["context_json"],
                                           "core_schema": "NOX_V38_SYNAPTIC",
                                           "persona_enabled": session.persona_enabled})
            for part in source:
                if not self._gate(session):
                    yield {"type": "hold", "state": "HOLD_STOP_DURING_STREAM"}
                    return
                if not isinstance(part, str):
                    yield {"type": "hold", "state": "HOLD_INVALID_MODEL_DELTA"}
                    return
                if part:
                    yield {"type": "delta", "text": part}
        except Exception:
            yield {"type": "hold", "state": "HOLD_MODEL_STREAM_ERROR"}
            return
        yield {"type": "done", "model": "EXISTING_NOX_ONLY", "weight_updates": "UNVERIFIED"}
