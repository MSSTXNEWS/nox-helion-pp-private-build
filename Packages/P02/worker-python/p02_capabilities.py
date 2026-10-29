"""NOX P02 owner-scoped contracts for one existing host/chat/LLM/voice/SIP gateway.

This file NEVER launches a server, calls a phone number, downloads weights, makes
an external request, or creates a second LLM/SQLite. #6 supplies actual adapters.
NO-LOSS: prior voice, GUI and persona handlers remain owned by original app/PR18.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable

from p02_runtime import P02Error, Cancelled

LANG = frozenset({'ru','es'})
LEVELS = frozenset({'A1','A2','B1','B2','C1','C2'})
E164 = re.compile(r'^\+[1-9][0-9]{7,14}$')


def _voice_text(value: str, limit: int, error: str) -> None:
    """Reject malformed provider text before another adapter or native storage."""
    if type(value) is not str or not 0 < len(value) <= limit or not value.strip():
        raise P02Error(error)
    try:
        value.encode('utf-8', 'strict')
    except UnicodeEncodeError as exc:
        raise P02Error(error) from exc


@dataclass(frozen=True)
class Identity:
    """Values established from native host authenticated user, never from page JSON."""
    tenant: str
    principal: str
    core_id: str
    persona_id: str
    session_id: str


def context_key(identity: Identity, allowed_cores: frozenset[str],
                allowed_personas: frozenset[str]) -> str:
    """Unique deterministic context token; separate personas/cores, same chat engine.

    Host #6 maps this identifier to an existing authorized chat row; the token
    itself grants no access and does not migrate/create a database.
    """
    if not isinstance(identity, Identity):
        raise TypeError('Native host identity required')
    values = (identity.tenant,identity.principal,identity.core_id,
              identity.persona_id,identity.session_id)
    if any(not isinstance(v,str) or not 0 < len(v) <= 128 for v in values):
        raise ValueError('Invalid identity scope')
    if identity.core_id not in allowed_cores or identity.persona_id not in allowed_personas:
        raise PermissionError('Unregistered CoreID or Persona; scope HOLD')
    # Include lengths so no boundary ambiguity; hashed id is an identifier, not auth.
    canonical = ''.join(f'{len(v)}:{v}' for v in values).encode('utf-8')
    return 'ctx_' + hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class VoiceResult:
    transcript: str
    response: str
    audio: bytes
    source_lang: str
    target_lang: str
    mode: str


class LocalVoicePipeline:
    """Connects existing native microphone/ASR + ONE chat LLM + local TTS.

    Caller/host provides approved local adapters (ASR, LLM, TTS); missing rights,
    models, microphone consent, stop support -> HOLD rather than dummy voices.
    Audio is ephemeral and NEVER logged or auto-saved by this class.
    """
    def __init__(self, asr: Callable, chat: Callable, tts: Callable,
                 *, approved_models: bool = False, permitted_voices: frozenset[str] = frozenset()):
        self.asr, self.chat, self.tts = asr, chat, tts
        self.approved_models = approved_models
        # The caller cannot silently broaden voice rights by mutating its set.
        self.permitted_voices = frozenset(permitted_voices)

    def validate_request(self, scope: Identity, *, source: str, target: str,
                         voice: str, mode: str = 'translate', level: str = 'A2') -> None:
        """Pure preflight, shared with native capture admission before consumption."""
        if (type(source) is not str or type(target) is not str
                or source not in LANG or target not in LANG or source == target):
            raise ValueError('Only RU↔ES is enabled')
        if type(voice) is not str or voice not in self.permitted_voices:
            raise PermissionError('Unapproved voice identity')
        if (type(mode) is not str or type(level) is not str
                or mode not in ('translate', 'maestro') or level not in LEVELS):
            raise ValueError('Unsupported voice mode or learning level')
        if not isinstance(scope, Identity) or not scope.tenant or not scope.principal:
            raise PermissionError('Missing trusted native principal')

    def run(self, scope: Identity, audio: bytes, *, source: str, target: str,
            voice: str, mode: str = 'translate', level: str = 'A2',
            microphone_consent: bool = False,
            stop: threading.Event | None = None) -> VoiceResult:
        # Never invent a detached cancellation Event for microphone capture.
        if not isinstance(stop, threading.Event):
            raise P02Error('VOICE_NATIVE_STOP_TOKEN_REQUIRED')
        if stop.is_set():
            raise Cancelled('Voice STOP before start')
        if microphone_consent is not True or self.approved_models is not True:
            raise PermissionError('VOICE_CONSENT_OR_MODEL_RIGHTS_HOLD')
        providers = (self.asr, self.chat, self.tts)
        if not all(callable(a) for a in providers):
            raise P02Error('LOCAL_ASR_LLM_TTS_PROVIDER_HOLD')
        if not isinstance(audio, bytes) or not 0 < len(audio) <= 16 * 1024 * 1024:
            raise ValueError('Invalid capped microphone audio buffer')
        self.validate_request(scope, source=source, target=target, voice=voice,
                              mode=mode, level=level)
        def retain_admission():
            if self.approved_models is not True or voice not in self.permitted_voices:
                raise PermissionError('VOICE_MODEL_OR_VOICE_RIGHTS_REVOKED')
            if any(current is not pinned for current, pinned in
                   zip((self.asr, self.chat, self.tts), providers)):
                raise P02Error('LOCAL_VOICE_PROVIDER_CHANGED_DURING_RUN')
        asr, chat, tts = providers
        transcript = asr(scope, audio, source, stop)
        if stop.is_set(): raise Cancelled('Voice STOP after ASR')
        retain_admission()
        _voice_text(transcript, 20000, 'ASR_INVALID_RESULT')
        # No other provider; reuse one installed chat LLM supplied by #6.
        directive = ('RU_ES_TRANSLATE' if mode == 'translate' else 'MAESTRO_CEFR_'+level)
        response = chat(scope, transcript, source, target, directive, stop)
        if stop.is_set(): raise Cancelled('Voice STOP after LLM')
        retain_admission()
        _voice_text(response, 30000, 'LLM_INVALID_RESULT')
        output = tts(scope, response, target, voice, stop)
        if stop.is_set(): raise Cancelled('Voice STOP after TTS')
        retain_admission()
        if not isinstance(output, bytes) or not 0 < len(output) <= 16 * 1024 * 1024:
            raise P02Error('TTS_INVALID_RESULT')
        return VoiceResult(transcript,response,output,source,target,mode)

    @staticmethod
    def validate_result(result: VoiceResult, *, source: str, target: str, mode: str) -> None:
        """Native owner must not store audio from a mismatched/overridden adapter."""
        if (type(result) is not VoiceResult or result.source_lang != source
                or result.target_lang != target or result.mode != mode):
            raise P02Error('VOICE_RESULT_REQUEST_MISMATCH')
        _voice_text(result.transcript, 20000, 'ASR_INVALID_RESULT')
        _voice_text(result.response, 30000, 'LLM_INVALID_RESULT')
        if type(result.audio) is not bytes or not 0 < len(result.audio) <= 16 * 1024 * 1024:
            raise P02Error('TTS_INVALID_RESULT')


@dataclass(frozen=True)
class CallQuote:
    number: str
    purpose: str
    max_cost: Decimal
    currency: str
    quote_id: str
    expires_at: float


class ConsentGatedSip:
    """Private SIP host adapter: no call unless quote+fresh scoped confirmation.

    Provider must implement (native host) place_call(scope, quote, stop). This
    module never supplies a provider or estimates a tariff, so costs are not fake.
    """
    def __init__(self, provider: Callable | None, *, user_approval: Callable | None,
                 provider_quote_verify: Callable | None = None):
        self.provider, self.user_approval = provider, user_approval
        self.provider_quote_verify = provider_quote_verify
        self._used: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def new_quote(number: str, purpose: str, max_cost: str,
                  currency: str, quote_id: str, expires_at: float) -> CallQuote:
        if not isinstance(number,str) or not E164.fullmatch(number):
            raise ValueError('SIP destination requires E.164 number')
        if not isinstance(purpose,str) or not 1 <= len(purpose) <= 250:
            raise ValueError('Call purpose required')
        if currency != 'EUR' or not isinstance(quote_id,str) or not 1 <= len(quote_id) <= 128:
            raise ValueError('Invalid provider quote')
        try: value = Decimal(max_cost)
        except (InvalidOperation, TypeError): raise ValueError('Invalid provider tariff')
        if not value.is_finite() or value < 0 or value > Decimal('1000'):
            raise ValueError('Invalid cost ceiling')
        if not isinstance(expires_at,(int,float)) or not time.time() < expires_at <= time.time()+120:
            raise ValueError('Missing fresh time-limited provider quote')
        return CallQuote(number,purpose,value,currency,quote_id,expires_at)

    def place(self, scope: Identity, quote: CallQuote, stop: threading.Event | None = None):
        # The SIP provider must share STOP with the authenticated native session.
        if not isinstance(stop, threading.Event):
            raise P02Error('SIP_NATIVE_STOP_TOKEN_REQUIRED')
        if stop.is_set(): raise Cancelled('CALL_STOP_BEFORE_START')
        if not isinstance(scope, Identity) or not scope.tenant or not scope.principal:
            raise PermissionError('Native principal required')
        # Pin all native/provider authority before any re-entrant callback.
        # Callbacks may update mutable host bindings; no swapped approver or
        # dialer is allowed to inherit an earlier authorization.
        provider, approval, quote_verify = (
            self.provider, self.user_approval, self.provider_quote_verify)
        if not all(callable(x) for x in (provider, approval, quote_verify)):
            raise P02Error('SIP_PROVIDER_QUOTE_OR_CONSENT_HOLD')
        if not isinstance(quote, CallQuote):
            raise PermissionError('Expired SIP quote')
        pinned_scope = (scope.tenant, scope.principal, scope.core_id,
                        scope.persona_id, scope.session_id)
        pinned_quote = (quote.number, quote.purpose, quote.max_cost,
                        quote.currency, quote.quote_id, quote.expires_at)
        def require_native_authority():
            if (self.provider is not provider
                    or self.user_approval is not approval
                    or self.provider_quote_verify is not quote_verify):
                raise P02Error('SIP_NATIVE_HOOK_REBOUND_HOLD')
            if ((scope.tenant, scope.principal, scope.core_id,
                 scope.persona_id, scope.session_id) != pinned_scope
                    or (quote.number, quote.purpose, quote.max_cost,
                        quote.currency, quote.quote_id, quote.expires_at) != pinned_quote):
                raise PermissionError('SIP_SCOPE_OR_QUOTE_REBOUND_HOLD')
        def require_fresh_quote():
            # Provider verification and the native consent dialog may block.
            # Recheck the original quote after each callback, not only on entry.
            if (not isinstance(quote, CallQuote)
                    or type(quote.expires_at) not in (int, float)
                    or not math.isfinite(quote.expires_at)
                    or quote.expires_at <= time.time()):
                raise PermissionError('Expired SIP quote')
        require_fresh_quote()
        if stop.is_set():
            raise Cancelled('CALL_STOP_BEFORE_START')
        # Native approval/provider verification may synchronously reenter SIP.
        # Holding a blocking Lock here would deadlock a native callback.
        if not self._lock.acquire(blocking=False):
            raise P02Error('SIP_CONCURRENT_OR_REENTRANT_CONFIRMATION_HOLD')
        try:
            require_fresh_quote()
            require_native_authority()
            if quote.quote_id in self._used: raise PermissionError('Call quote already consumed')
            # The price and number must be independently bound to a real provider
            # quote; a caller-constructed CallQuote is NOT sufficient authority.
            if quote_verify(scope, quote) is not True:
                raise PermissionError('Provider quote verification required')
            require_native_authority()
            require_fresh_quote()
            if stop.is_set(): raise Cancelled('CALL_STOP_BEFORE_APPROVAL')
            # approval callback MUST be the native consent dialog, not page JS.
            if approval(scope, quote) is not True:
                raise PermissionError('Native user confirmation required')
            require_native_authority()
            require_fresh_quote()
            if stop.is_set(): raise Cancelled('CALL_STOP_BEFORE_DIAL')
            self._used.add(quote.quote_id)
        finally:
            self._lock.release()
        if stop.is_set(): raise Cancelled('CALL_STOP_BEFORE_DIAL')
        require_fresh_quote()
        require_native_authority()
        return provider(scope, quote, stop)


def authorize_private_mobile(scope: Identity, *, verified_private_peer: bool,
                             trusted_origin: str, observed_origin: str,
                             expected_csrf: bytes, received_csrf: bytes,
                             native_session_approved: bool) -> bool:
    """Pure native-host authorization policy, NEVER a public proxy or HTTP server.

    #6 checks Tailscale peer independently (not a header from JS), supplies session
    and rotates CSRF secret. This function cannot establish secure networking.
    """
    if not isinstance(scope, Identity) or not scope.tenant or not scope.principal:
        return False
    if not verified_private_peer or not native_session_approved:
        return False
    try:
        a,b=urllib.parse.urlsplit(trusted_origin),urllib.parse.urlsplit(observed_origin)
        if a.scheme!='https' or not a.hostname or a.username or a.password:
            return False
        if b.scheme!='https' or b.username or b.password or b.hostname!=a.hostname or b.port!=a.port:
            return False
        if b.path not in ('','/') or b.query or b.fragment:
            return False
    except ValueError:
        return False
    if not isinstance(expected_csrf,bytes) or len(expected_csrf)<32:
        return False
    if not isinstance(received_csrf,bytes): return False
    return hmac.compare_digest(expected_csrf,received_csrf)


def authorized_local_video(root: str, candidate: str, *, native_user_selected: bool,
                           max_bytes: int = 2 * 1024**3) -> str:
    """Resolve a consented existing local video for native host media API.

    Must not navigate WebView2 to file:// or inject raw absolute path into JS.
    #6 streams via a privileged native *owned* reader with explicit MIME policy.
    """
    import pathlib
    if not native_user_selected:
        raise PermissionError('VIDEO_PICKER_CONSENT_REQUIRED')
    parent = pathlib.Path(root).resolve(strict=True)
    path = pathlib.Path(candidate)
    if path.is_symlink() or not path.is_file():
        raise P02Error('Untrusted video path')
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(parent):
        raise PermissionError('Video outside user-selected root')
    if resolved.suffix.lower() not in ('.mp4','.webm','.m4v'):
        raise P02Error('Video MIME/extension not supported by built-in viewer')
    if not 0 < resolved.stat().st_size <= max_bytes:
        raise P02Error('Video file outside approved size limit')
    return str(resolved)
