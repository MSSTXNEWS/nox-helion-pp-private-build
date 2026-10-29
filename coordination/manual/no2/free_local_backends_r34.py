"""NOX V16 optional free-software adapters for the EXISTING P02 LocalVoicePipeline.

Not a second voice host or runtime, and not a replacement for native consent,
rights checks, model provenance, STOP or owner acceptance. Does not load models,
install packages, access the network, persist audio, or claim real microphone QA.
The authenticated native host supplies an ALREADY-LOADED local engine and guards.

Optional upstream software: faster-whisper (MIT), Argos Translate (MIT/CC0).
Model/voice/checkpoint rights and hashes must be approved independently.
"""
from __future__ import annotations

import io
from collections.abc import Callable

MAX_AUDIO_BYTES = 16 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 20_000
MAX_TRANSLATION_CHARS = 30_000
LANGUAGES = frozenset(("ru", "es"))


class FreeBackendHold(RuntimeError):
    """Fail-closed until native owner evidence is verified."""


def _guard(scope, source: str, target: str | None, stop,
           native_authorize: Callable, snapshot_approved: Callable) -> None:
    if stop is None or not callable(getattr(stop, "is_set", None)):
        raise FreeBackendHold("NATIVE_STOP_TOKEN_REQUIRED")
    if stop.is_set():
        raise FreeBackendHold("STOP_REQUESTED")
    if source not in LANGUAGES or (target is not None and
                                  (target not in LANGUAGES or target == source)):
        raise FreeBackendHold("ONLY_RU_ES_APPROVED")
    if native_authorize(scope, "chat.voice") is not True:
        raise PermissionError("NATIVE_VOICE_ACL_HOLD")
    if stop.is_set():
        raise FreeBackendHold("STOP_REQUESTED")
    if snapshot_approved(scope, source, target) is not True:
        raise PermissionError("LOCAL_MODEL_RIGHTS_OR_SHA_HOLD")
    if stop.is_set():
        raise FreeBackendHold("STOP_REQUESTED")


def bind_faster_whisper_asr(model, *, native_authorize: Callable,
                            snapshot_approved: Callable,
                            enable_local_vad: bool = False):
    """Adapt an already loaded faster-whisper model to LocalVoicePipeline.asr.

    Model initialization/weights are deliberately not performed here; calling
    WhisperModel('model-name') can otherwise trigger an unapproved download.
    """
    if not callable(getattr(model, "transcribe", None)) or not callable(native_authorize) or not callable(snapshot_approved):
        raise TypeError("EXISTING_ENGINE_AND_NATIVE_GUARDS_REQUIRED")
    if type(enable_local_vad) is not bool:
        raise TypeError("VAD_OWNER_APPROVAL_REQUIRED")

    def asr(scope, audio: bytes, language: str, stop):
        _guard(scope, language, None, stop, native_authorize, snapshot_approved)
        if type(audio) is not bytes or not 0 < len(audio) <= MAX_AUDIO_BYTES:
            raise ValueError("INVALID_BOUNDED_AUDIO")
        segments, _ = model.transcribe(io.BytesIO(audio), language=language,
                                       beam_size=1, vad_filter=enable_local_vad)
        chunks: list[str] = []
        total = 0
        # Faster-whisper segments are lazy: STOP must be checked while iterating.
        for segment in segments:
            if stop.is_set():
                raise FreeBackendHold("STOP_REQUESTED")
            chunk = getattr(segment, "text", None)
            if type(chunk) is not str or not chunk.strip():
                raise FreeBackendHold("ASR_INVALID_SEGMENT")
            total += len(chunk)
            if total > MAX_TRANSCRIPT_CHARS:
                raise FreeBackendHold("ASR_TEXT_TOO_LONG")
            chunks.append(chunk.strip())
        if stop.is_set():
            raise FreeBackendHold("STOP_REQUESTED")
        if not chunks:
            raise FreeBackendHold("ASR_EMPTY_RESULT")
        return " ".join(chunks)

    return asr


def bind_installed_argos_translation(*, installed_translation: Callable,
                                     native_authorize: Callable,
                                     snapshot_approved: Callable):
    """Optional single host-selected chat provider for RU_ES_TRANSLATE only.

    Does not install .argosmodel files or fetch model lists; owner provides an
    already installed, rights-verified translation object for this direction.
    No MAESTRO fallback to canned text: existing host chat LLM remains default.
    """
    if not all(map(callable, (installed_translation, native_authorize, snapshot_approved))):
        raise TypeError("EXISTING_TRANSLATOR_AND_NATIVE_GUARDS_REQUIRED")

    def translate(scope, transcript: str, source: str, target: str, directive: str, stop):
        _guard(scope, source, target, stop, native_authorize, snapshot_approved)
        if directive != "RU_ES_TRANSLATE":
            raise FreeBackendHold("EXISTING_MAESTRO_LLM_REQUIRED")
        if type(transcript) is not str or not 0 < len(transcript) <= MAX_TRANSCRIPT_CHARS:
            raise ValueError("INVALID_TRANSCRIPT")
        if stop.is_set():
            raise FreeBackendHold("STOP_REQUESTED")
        engine = installed_translation(source, target)
        if engine is None or not callable(getattr(engine, "translate", None)):
            raise FreeBackendHold("INSTALLED_ARGOS_PACKAGE_MISSING")
        response = engine.translate(transcript)
        if stop.is_set():
            raise FreeBackendHold("STOP_REQUESTED")
        if type(response) is not str or not 0 < len(response) <= MAX_TRANSLATION_CHARS:
            raise FreeBackendHold("TRANSLATION_INVALID_RESULT")
        return response

    return translate
