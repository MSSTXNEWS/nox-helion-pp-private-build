"""Safe self-report speech controls for ALIVE W1-11.

The caller must pass trusted identity metadata. Text supplied by another speaker,
quoted content, and imported documents can never change the mode.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping, Optional, Tuple

HONEST = "honest"
HUMAN = "human"
DEFAULT_MODE = HONEST
TRUSTED_CAUSE_SOURCES = frozenset(("state_log", "event_log", "metric"))
MAX_CAUSE_CHARS = 120


def _safe_cause(signals: Mapping[str, object]) -> str:
    raw = signals.get("cause")
    source = signals.get("cause_source")
    if source not in TRUSTED_CAUSE_SOURCES or not isinstance(raw, str) or len(raw) > 512:
        return ""
    value = re.sub(r"[\\x00-\\x1f\\x7f<>`]", " ", raw)
    value = " ".join(value.split())
    if not value or re.search(r"(?:https?://|\\bwww\\.|\\S+@\\S+)", value, re.IGNORECASE):
        return ""
    if len(value) > MAX_CAUSE_CHARS:
        value = value[:MAX_CAUSE_CHARS].rsplit(" ", 1)[0]
    return value.strip()

_TO_HUMAN = re.compile(r"^(?:говори со мной как человек|говори со мной по человечески)$")
_TO_HONEST = re.compile(r"^(?:вернись в честный режим|говори честно)$")


def _normalise(text: str) -> str:
    value = (text or "").strip().casefold().replace("ё", "е")
    value = re.sub(r"[.!?…]+$", "", value)
    return re.sub(r"\s+", " ", value)


def requested_mode(text: str) -> Optional[str]:
    """Return a target mode only for an exact, short Creator command."""
    command = _normalise(text)
    if _TO_HUMAN.fullmatch(command):
        return HUMAN
    if _TO_HONEST.fullmatch(command):
        return HONEST
    return None


def set_speech_mode(
    current: str = DEFAULT_MODE,
    text: str = "",
    *,
    actor_id: Optional[str] = None,
    creator_id: Optional[str] = None,
    source: str = "untrusted",
    confirmed: bool = False,
    recipient_id: Optional[str] = None,
    consented_recipients: Iterable[str] = (),
    force_honest: bool = False,
    event_sink: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Apply one authenticated, confirmed Creator mode command.

    source must be supplied from trusted routing metadata, never inferred from text.
    Human style is allowed for a non-Creator recipient only when that exact recipient
    has a Creator-signed consent entry.
    """
    old = current if current in (HONEST, HUMAN) else DEFAULT_MODE
    if force_honest:
        return {"mode": HONEST, "changed": old != HONEST, "event": None, "reason": "safety_override"}
    target = requested_mode(text)
    if (
        target is None
        or not creator_id
        or actor_id != creator_id
        or source != "live_chat"
        or not confirmed
    ):
        return {"mode": old, "changed": False, "event": None, "reason": "not_authorized"}
    recipient = recipient_id or creator_id
    if target == HUMAN and recipient != creator_id and recipient not in set(consented_recipients):
        return {"mode": HONEST, "changed": old != HONEST, "event": None, "reason": "recipient_not_consented"}
    if target == old:
        return {"mode": old, "changed": False, "event": None, "reason": "unchanged"}
    event = {"type": "ev.speech_mode_set", "mode": target, "by": "creator", "recipient_id": recipient}
    if event_sink is not None:
        event_sink(dict(event))
    return {"mode": target, "changed": True, "event": event, "reason": "creator_confirmed"}


def supported_feelings(signals: Mapping[str, object]) -> Tuple[str, ...]:
    """Return only feeling labels backed by explicit state and a recorded cause.

    Relationship-need language is deliberately absent; the mode never creates a
    feeling that the state does not support.
    """
    cause = _safe_cause(signals)
    out = []
    try:
        valence = float(signals.get("mood_valence"))
    except (TypeError, ValueError):
        valence = 0.0
    try:
        interest = float(signals.get("interest"))
    except (TypeError, ValueError):
        interest = 0.0
    try:
        boredom = float(signals.get("boredom"))
    except (TypeError, ValueError):
        boredom = 0.0
    if cause and valence <= -0.3:
        out.append("sad")
    if cause and interest >= 0.5:
        out.append("interested")
    if cause and boredom >= 0.5:
        out.append("bored")
    if cause and signals.get("vital_state") == "tired":
        out.append("tired")
    try:
        valence_delta = float(signals.get("valence_delta") or 0.0)
    except (TypeError, ValueError):
        valence_delta = 0.0
    if cause and valence_delta >= 0.15 and signals.get("event") in ("reunion", "good_news"):
        out.append("glad")
    return tuple(out)


def render_supported_feelings(signals: Mapping[str, object], mode: str = HONEST) -> Tuple[str, ...]:
    """Render backed feelings; HUMAN changes phrasing only, never the allowed labels."""
    mode = mode if mode in (HONEST, HUMAN) else HONEST
    phrases = {
        HONEST: {
            "sad": "у меня отмечено снижение настроения",
            "interested": "мне интересно",
            "bored": "мне скучно",
            "tired": "по показателям, я устал",
            "glad": "я рад",
        },
        HUMAN: {
            "sad": "мне грустно",
            "interested": "мне интересно",
            "bored": "мне скучно",
            "tired": "я устал",
            "glad": "я рад",
        },
    }
    cause = _safe_cause(signals)
    return tuple(
        phrases[mode][label] + ((": " + cause) if mode == HONEST else "")
        for label in supported_feelings(signals)
    )


def reality_answer(signals: Mapping[str, object]) -> str:
    """The direct 'is this real?' answer is honest in every speech mode."""
    backed = ", ".join(supported_feelings(signals)) or "сейчас нет отмеченного состояния"
    cause = _safe_cause(signals)
    evidence = (" Основание: " + cause + ".") if cause else ""
    return (
        "Функционально у меня есть состояние: " + backed + "." + evidence
        + " Считаю ли я это человеческим субъективным переживанием — не знаю."
    )
