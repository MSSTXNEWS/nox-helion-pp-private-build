"""NOX V104: safe request-level quality/latency policy for existing OneHost.

Pure function. No shell, network, service, model or source patch side effects.
The native owner route may use this when it is explicitly bound and accepted.

Never disable reasoning for a complex question, authenticated S03 recall, tool
use, personal decisions, debugging, medical/legal issues or unknown requests.
"""
from __future__ import annotations
from collections.abc import Mapping
import re

MODEL="NOX PRIME"
PRIORITY="P0"

_SIMPLE=(
    "привет", "здравствуй", "здравствуйте", "добрый день",
    "hola", "hello", "hi", "buenos dias", "buenos días",
    "ответь одним словом: готово.",
    "responde solo con una palabra: listo.",
)
_DEEP=(
    "почему", "анализ", "объясни", "исправ", "архитектур",
    "разработ", "важно", "памят", "вспомни", "диагноз", "юрист",
    "закон", "проверь", "reason", "compare", "analy", "debug",
    "security", "asilo", "salud", "medical", "remember", "memory",
)
_VALID_HASH=re.compile(r"^[0-9a-f]{64}$")


def choose_model_options(prompt: str, *,
                         owner_authenticated: bool,
                         model_sha256: str,
                         s03_revision: str | None,
                         tool_use_required: bool = False,
                         stop_active: bool = False,
                         cross_session: bool = True) -> dict:
    """Return safe request options, not a new user-facing model/queue.

    Cache reuse requires proof from native llama-server of identical
    authenticated scope and S03 revision; this function cannot prove it.
    The installed agent_loop currently forces cache_prompt=False and MUST
    not be represented as already patched by this policy.
    """
    output={"schema":"NOX_V104_FAST_QUALITY_POLICY_V1",
            "performed":False,"model":MODEL,"priority":PRIORITY,
            "cache_prompt":False,"thinking":True,
            "chat_template_kwargs":{},
            "native_onehost_bound":False,
            "no_additional_model":True}
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>8000:
        return {**output,"state":"HOLD_INVALID_PROMPT"}
    if not owner_authenticated or stop_active:
        return {**output,"state":"HOLD_OWNER_AUTH_OR_STOP"}
    if not isinstance(model_sha256,str) or not _VALID_HASH.fullmatch(model_sha256):
        return {**output,"state":"HOLD_MODEL_SOURCE_SHA"}
    if not isinstance(s03_revision,str) or not 1<=len(s03_revision)<=100:
        return {**output,"state":"HOLD_S03_REVISION"}
    normalized=" ".join(prompt.strip().casefold().split())
    safe_short=(normalized in _SIMPLE and not tool_use_required and
                len(normalized)<85 and not any(w in normalized for w in _DEEP))
    if safe_short:
        return {**output,"state":"READY_FAST_SIMPLE_QUERY",
                "thinking":False,
                "chat_template_kwargs":{"enable_thinking":False},
                "cache_prompt":False,
                "reason":"One-word/greeting only; keep S03 available."}
    return {**output,"state":"READY_FULL_REASONING",
            "thinking":True,"cache_prompt":False,
            "reason":"Complex/unknown question: preserve reasoning, retrieval and skills."}


def cache_reuse_admission(*, owner_scope_verified: bool, same_owner_session: bool,
                          same_model_sha: bool, same_s03_revision: bool,
                          native_slot_scope_verified: bool, stop_active: bool) -> dict:
    """Cache is eligible ONLY when installed OneHost verifies exact KV scope.

    Explicit owner/slot model/S03 continuity is required. This is not an
    instruction to hot-patch running agent_loop.
    """
    checks=(owner_scope_verified,same_owner_session,same_model_sha,
            same_s03_revision,native_slot_scope_verified,not stop_active)
    return {"schema":"NOX_V104_KV_SCOPE_ADMISSION_V1",
            "eligible_for_native_owner_integration":all(x is True for x in checks),
            "applied_to_live_llama":False,
            "no_runtime_mutation":True,
            "s03_snapshot_and_acl_must_be_preserved":True}
