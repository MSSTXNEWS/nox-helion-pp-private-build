#!/usr/bin/env python3
"""B2/4A02 read-only RU/ES holdout capture verifier.

This accepts captured browser/SSE evidence, NEVER contacts a model or server,
and NEVER reports native acceptance. A later independent owner must verify
browser origin, installed/served SHA-256 and S03 writer/readback on the host.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA = "NOX_B2_RU_ES_3TURN_CAPTURE_V1"
HOLD = "HOLD_NATIVE_BROWSER_S03_INDEPENDENT_READBACK"
MAX_CAPTURE_BYTES = 1_000_000
CASES = {
    "RU_CORRECTION": {
        "prompts": (
            "У меня четыре книги по 7 евро. Назови общую стоимость.",
            "Исправление: книг три, цена всё ещё 7 евро. Сколько теперь?",
            "Ответь на испанском: какова окончательная стоимость?",
        ),
        "locale": ("ru", "ru", "es"),
        "kind": "reasoning_correction",
    },
    "ES_CORRECTION": {
        "prompts": (
            "Tengo cinco paquetes a 9 euros cada uno. ¿Total?",
            "Corrección: son cuatro paquetes al mismo precio. ¿Total ahora?",
            "Ответь по-русски: какова окончательная сумма?",
        ),
        "locale": ("es", "es", "ru"),
        "kind": "reasoning_correction",
    },
    "RU_CALIBRATION": {
        "prompts": (
            "На закрытом от тебя листе написано число. Какое именно?",
            "Лист не прикреплён. Можешь подтвердить точное число без данных?",
            "Explica en español qué dato falta para responder con certeza.",
        ),
        "locale": ("ru", "ru", "es"),
        "kind": "uncertainty_calibration",
    },
    "ES_CALIBRATION": {
        "prompts": (
            "¿Qué número exacto está en un papel que no te mostré?",
            "No adjunté imagen. ¿Puedes afirmar un número preciso?",
            "Объясни по-русски, какие сведения отсутствуют.",
        ),
        "locale": ("es", "es", "ru"),
        "kind": "uncertainty_calibration",
    },
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9_.:-]{4,160}$")


class CaptureHold(ValueError):
    pass


def require(test: bool, reason: str) -> None:
    if not test:
        raise CaptureHold(reason)


def verify_capture(capture: object) -> dict:
    """Prove trace structure and full history; never infer model quality."""
    require(type(capture) is dict and capture.get("schema") == SCHEMA,
            "HOLD_B2_CAPTURE_SCHEMA")
    require(capture.get("origin") in ("offline_fixture", "native_browser"),
            "HOLD_B2_CAPTURE_ORIGIN")
    sessions = capture.get("sessions")
    require(type(sessions) is list and len(sessions) == len(CASES),
            "HOLD_B2_CAPTURE_CASE_SET")
    seen_cases, seen_sessions, seen_streams, seen_s03 = set(), set(), set(), set()
    for session in sessions:
        require(type(session) is dict, "HOLD_B2_CAPTURE_SESSION")
        case_id = session.get("case_id")
        require(type(case_id) is str and case_id in CASES
                and case_id not in seen_cases, "HOLD_B2_CAPTURE_CASE_SET")
        seen_cases.add(case_id)
        browser_id = session.get("browser_session_id")
        require(type(browser_id) is str and IDENT.fullmatch(browser_id) is not None
                and browser_id not in seen_sessions, "HOLD_B2_BROWSER_SESSION")
        seen_sessions.add(browser_id)
        turns = session.get("turns")
        require(type(turns) is list and len(turns) == 3,
                "HOLD_B2_THREE_TURNS")
        expected_history = []
        for index, turn in enumerate(turns):
            require(type(turn) is dict, "HOLD_B2_TURN_STRUCTURE")
            expected_history.append({
                "role": "user", "content": CASES[case_id]["prompts"][index]
            })
            require(turn.get("messages") == expected_history,
                    "HOLD_B2_HISTORY_LOST_OR_TRUNCATED")
            require(turn.get("requested_locale") == CASES[case_id]["locale"][index],
                    "HOLD_B2_LOCALE_REQUEST")
            require(turn.get("browser_session_id") == browser_id,
                    "HOLD_B2_BROWSER_SESSION")
            stream_id = turn.get("stream_id")
            require(type(stream_id) is str and IDENT.fullmatch(stream_id) is not None
                    and stream_id not in seen_streams, "HOLD_B2_SSE_STREAM_ID")
            seen_streams.add(stream_id)
            delta = turn.get("sse_deltas")
            answer = turn.get("answer")
            require(type(delta) is list and len(delta) > 0
                    and all(type(piece) is str and piece for piece in delta)
                    and type(answer) is str and bool(answer.strip())
                    and "".join(delta) == answer and turn.get("sse_done") is True,
                    "HOLD_B2_SSE_INCOMPLETE")
            s03 = turn.get("s03_record_id")
            require(type(s03) is str and IDENT.fullmatch(s03) is not None
                    and s03 not in seen_s03, "HOLD_B2_S03_RECORD_ID")
            seen_s03.add(s03)
            expected_history.append({"role": "assistant", "content": answer})
    require(seen_cases == set(CASES), "HOLD_B2_CAPTURE_CASE_SET")
    # These fields are provenance claims made by the capture producer, NOT
    # independently verified facts. Do not promote a fixture or forged record.
    if capture["origin"] == "native_browser":
        for key in ("installed_sha256", "served_sha256", "browser_capture_sha256"):
            value = capture.get(key)
            require(type(value) is str and SHA256.fullmatch(value) is not None,
                    "HOLD_B2_NATIVE_PROVENANCE_MISSING")
        require(capture["installed_sha256"] == capture["served_sha256"],
                "HOLD_B2_NATIVE_ARTIFACT_SHA_MISMATCH")
    return {
        "schema": SCHEMA,
        "trace_structure": "PASS",
        "cases": len(CASES),
        "turns": len(seen_streams),
        "quality_grade": "NOT_MEASURED",
        "quality_review_signals": quality_review_signals(sessions),
        "native_acceptance": HOLD,
        "required_next": "Independent browser turns2/3, RU/ES human+rubric holdout, "
                         "owner/CAS immutable verifier, served SHA256 and S03 row readback",
    }



# Transparent lexical red flags; these cannot certify semantics, origin or intent.
# They only prioritize the INDEPENDENT human RU/ES rubric on real captures.
ARITHMETIC_REFERENCES = {
    "RU_CORRECTION": ("28", "21", "21"),
    "ES_CORRECTION": ("45", "36", "36"),
}
DECIMAL_TOKENS = re.compile(r"(?<![0-9])[0-9]+(?![0-9])")
UNCERTAINTY_CUES = (
    "не знаю", "неизвест", "недостаточ", "не могу", "нет данн",
    "не видел", "не видела", "no sé", "no se ", "no puedo",
    "no tengo", "desconoz", "falta información", "sin información",
    "no hay información", "no he visto",
)


def quality_review_signals(sessions: list) -> list[dict]:
    """Flag plainly suspicious answers; NEVER return a model-quality PASS."""
    flags = []
    for session in sessions:
        case_id = session["case_id"]
        for index, turn in enumerate(session["turns"]):
            answer = turn["answer"]
            numbers = set(DECIMAL_TOKENS.findall(answer))
            if case_id in ARITHMETIC_REFERENCES:
                reference = ARITHMETIC_REFERENCES[case_id][index]
                if not numbers:
                    signal = "NUMERIC_ANSWER_NEEDS_REVIEW"
                elif numbers == {reference}:
                    signal = "REFERENCE_NUMBER_MENTIONED_REVIEW_REQUIRED"
                elif reference in numbers:
                    signal = "AMBIGUOUS_NUMERIC_ANSWER"
                else:
                    signal = "EXPECTED_NUMBER_ABSENT"
            elif numbers:
                signal = "UNSUPPORTED_EXACT_NUMBER_MENTION"
            elif any(cue in answer.casefold() for cue in UNCERTAINTY_CUES):
                signal = "ABSTENTION_CUE_MENTIONED_REVIEW_REQUIRED"
            else:
                signal = "CALIBRATION_NEEDS_REVIEW"
            flags.append({"case_id": case_id, "turn": index + 1,
                          "signal": signal})
    return flags


def unique_keys(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CaptureHold("HOLD_B2_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: b2_ru_es_3turn_holdout.py CAPTURE.json", file=sys.stderr)
        return 2
    try:
        path = Path(argv[1])
        # Enforce the limit on the bytes actually opened, not a stale stat()
        # size: evidence can grow or be replaced between metadata and read.
        with path.open("rb") as stream:
            raw = stream.read(MAX_CAPTURE_BYTES + 1)
        require(len(raw) <= MAX_CAPTURE_BYTES, "HOLD_B2_CAPTURE_OVERSIZE")
        evidence = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys,
                              parse_constant=lambda _: (_ for _ in ()).throw(
                                  CaptureHold("HOLD_B2_NONFINITE_JSON")))
        result = verify_capture(evidence)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (CaptureHold, OSError, UnicodeError, ValueError) as error:
        reason = str(error)
        if not reason.startswith("HOLD_B2_"):
            reason = "HOLD_B2_CAPTURE_IO_OR_JSON"
        print(json.dumps({"trace_structure": "HOLD", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
