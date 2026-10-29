"""P02 glue for original preview-approved native voice, not a voice engine.

Original WindowsSapiTTS returns native playback metadata, not audio bytes. This
explicit opt-in port preserves that contract and the existing byte-audio port.
The native host supplies real capture, permissions and physical review UI.
"""
from __future__ import annotations
from dataclasses import astuple, dataclass
import re
from typing import Callable
from p02_owner_route_ports import NativeScope, OwnerTwoPorts, RouteHold

_CAPTURE = re.compile(r'[0-9a-f]{32}\Z')

@dataclass(frozen=True)
class NativePreviewDecision:
    """Returned by the trusted native review UI; never constructed from page JSON."""
    request_id: str
    text_sha256: str
    approved_preview: bool
    approved_meaning: bool = False

class OriginalVoicePort:
    def __init__(self, owner_ports: OwnerTwoPorts, service, ingress,
                 scope_from_session: Callable, *, use_local_model: bool,
                 native_model_authorize: Callable | None = None,
                 native_review: Callable | None = None):
        try:
            from helion_voice.service import VoiceService
            from helion_voice.control import VoiceSession
            from p02_native_ingress import NativeIngress
            from helion_voice.adapters import LocalWhisperASR, LocalOllamaTranslator, WindowsSapiTTS
        except ImportError as exc:
            # Optional original service is not part of this loader source tree.
            # Missing native owners are HOLD, never a substitute voice engine.
            raise RouteHold('ORIGINAL_VOICE_NATIVE_MODULES_HOLD') from exc
        if (not isinstance(owner_ports, OwnerTwoPorts) or type(service) is not VoiceService
                or not callable(scope_from_session)
                or type(ingress) is not NativeIngress
                or ingress._voice_session_type is not VoiceSession
                or type(use_local_model) is not bool
                or type(service.asr) is not LocalWhisperASR
                or type(service.tts) is not WindowsSapiTTS
                or (use_local_model and type(service.translator) is not LocalOllamaTranslator)
                or (native_model_authorize is not None and not callable(native_model_authorize))
                or (native_review is not None and not callable(native_review))):
            raise RouteHold('ORIGINAL_VOICE_NATIVE_BINDINGS_REQUIRED')
        self.owner_ports, self.service, self.ingress = owner_ports, service, ingress
        self.scope_from_session = scope_from_session
        self.use_local_model = use_local_model
        self.model_authorize, self.review = native_model_authorize, native_review

    def available(self):
        p = self.owner_ports
        try:
            return (callable(p.owner_ready) and p.owner_ready('chat.voice') is True
                    and callable(p.take_audio) and callable(p.mic_consent)
                    and self.service.asr is not None
                    and (not self.use_local_model or
                         (self.service.translator is not None and callable(self.model_authorize))))
        except Exception:
            return False

    def call(self, native_session, args):
        from helion_voice.control import VoiceCancelled, VoiceTimeout, VoicePermissionDenied
        from p02_native_ingress import ProtocolHold
        try:
            return self._call_original(native_session, args)
        except VoiceCancelled as exc:
            raise ProtocolHold('NATIVE_VOICE_STOPPED') from exc
        except VoiceTimeout as exc:
            # STOP is the active native operation's state, not inferred from
            # an arbitrary provider message. A late timeout must not replace it.
            voice = self.ingress.voice_session_from_native(native_session)
            code = 'NATIVE_VOICE_STOPPED' if voice.stopped else 'NATIVE_VOICE_TIMEOUT'
            raise ProtocolHold(code) from exc
        except VoicePermissionDenied as exc:
            raise ProtocolHold('NATIVE_PERMISSION_DENIED') from exc

    def _call_original(self, native_session, args):
        from helion_voice.safety import Direction
        from helion_voice.service import TranslationPreview
        if type(args) is not dict or not set(args) <= {'capture_id','source','target','speak'}:
            raise RouteHold('ORIGINAL_VOICE_REQUEST_FIELDS_INVALID')
        capture, source, target, speak = (args.get('capture_id'), args.get('source'),
                                        args.get('target'), args.get('speak', False))
        if (type(capture) is not str or not _CAPTURE.fullmatch(capture)
                or type(source) is not str or type(target) is not str
                or (source, target) not in (('ru','es'),('es','ru')) or type(speak) is not bool):
            raise RouteHold('ORIGINAL_VOICE_REQUEST_INVALID')
        if speak and self.review is None:
            raise RouteHold('ORIGINAL_NATIVE_PREVIEW_UI_REQUIRED')
        if not self.available():
            raise RouteHold('ORIGINAL_VOICE_PROVIDER_NOT_READY')
        scope = self.scope_from_session(native_session)
        if type(scope) is not NativeScope:
            raise RouteHold('ORIGINAL_NATIVE_SCOPE_REQUIRED')
        pinned_scope = astuple(scope)
        ingress, scope_resolver, owner = self.ingress, self.scope_from_session, self.owner_ports
        voice_session = ingress.voice_session_from_native(native_session)
        service = self.service
        providers = (service.asr, service.translator, service.tts)
        use_local = self.use_local_model
        native_hooks = (self.owner_ports.authorize, self.owner_ports.mic_consent,
                        self.owner_ports.take_audio, self.model_authorize, self.review)
        model_id = getattr(service.translator, 'model_id', None)
        def configuration():
            values = (getattr(service.translator,'model_id',None),
                      getattr(service.translator,'port',None), service.asr.model_dir,
                      service.asr.prefer_cuda, service.asr.allow_cpu_fallback)
            return tuple((type(value),value) for value in values)
        pinned_configuration = configuration()
        def bindings_stable():
            return (self.ingress is ingress and self.scope_from_session is scope_resolver
                    and self.owner_ports is owner and self.service is service
                    and self.use_local_model is use_local
                    and configuration() == pinned_configuration
                    and all(a is b for a,b in zip(
                        (owner.authorize,owner.mic_consent,owner.take_audio,
                         self.model_authorize,self.review),native_hooks))
                    and all(a is b for a,b in zip(
                        (service.asr,service.translator,service.tts),providers)))
        def current():
            voice_session.check()
            if not bindings_stable():
                raise RouteHold('ORIGINAL_VOICE_BINDING_CHANGED')
            resolved = scope_resolver(native_session)
            if (type(resolved) is not NativeScope or astuple(resolved) != pinned_scope
                    or astuple(scope) != pinned_scope
                    or ingress.voice_session_from_native(native_session) is not voice_session):
                raise RouteHold('ORIGINAL_VOICE_BINDING_CHANGED')
            owner._session(resolved, 'chat.voice')
            voice_session.check()
            after = scope_resolver(native_session)
            # The final native resolver can re-enter STOP or replace the active
            # request. Recheck before invoking consent/review/provider effects.
            voice_session.check()
            if (not bindings_stable() or type(after) is not NativeScope
                    or astuple(after) != pinned_scope or astuple(resolved) != pinned_scope
                    or astuple(scope) != pinned_scope
                    or ingress.voice_session_from_native(native_session) is not voice_session):
                raise RouteHold('ORIGINAL_VOICE_BINDING_CHANGED')
            return resolved
        current()
        consented = self.owner_ports.mic_consent(scope, capture) is True
        current()
        if not consented:
            raise PermissionError('NATIVE_MIC_CONSENT_REQUIRED')
        model_permission = False
        if use_local:
            model_permission = self.model_authorize(scope, model_id) is True
            current()
            if not model_permission:
                raise PermissionError('ORIGINAL_MODEL_PERMISSION_REQUIRED')
        try:
            audio = self.owner_ports.take_audio(scope, capture)
        except (KeyError, FileNotFoundError) as exc:
            raise RouteHold('NATIVE_CAPTURE_EXPIRED_OR_CONSUMED') from exc
        current()
        transcript = service.transcribe(audio, source, voice_session, permission=consented)
        current()
        if use_local:
            model_permission = self.model_authorize(scope, model_id) is True
            current()
            if not model_permission:
                raise PermissionError('ORIGINAL_MODEL_PERMISSION_REVOKED')
        preview = service.translate(transcript['text'], Direction(source+'-'+target),
                                    voice_session, use_local_model=use_local,
                                    model_permission=model_permission)
        current()
        if type(preview) is not TranslationPreview:
            raise RouteHold('ORIGINAL_TRANSLATION_PREVIEW_REQUIRED')
        challenge = service.approval_challenge(preview)
        response = {'state':'PREVIEW_ONLY', 'preview':challenge,
                    'asr_review_flags':list(transcript.get('asr_review_flags',())),
                    'audio_quality_flags':list(transcript.get('audio_quality_flags',())),
                    'transcript_review_required':True, 'physical_audio_confirmed':False,
                    'audio_stored':False}
        if not speak:
            return response
        # Native UI receives the exact original challenge. Page intent to speak
        # is not approval; original service independently checks the bound digest.
        decision = self.review(scope, dict(challenge, safety_flags=list(challenge['safety_flags'])))
        current()
        if (type(decision) is not NativePreviewDecision
                or type(decision.approved_preview) is not bool
                or type(decision.approved_meaning) is not bool):
            raise RouteHold('ORIGINAL_NATIVE_PREVIEW_DECISION_REQUIRED')
        if not decision.approved_preview:
            return response
        if use_local:
            if self.model_authorize(scope, model_id) is not True:
                raise PermissionError('ORIGINAL_MODEL_PERMISSION_REVOKED')
            current()
        receipt = service.speak_preview(preview, voice_session,
            owner_approved_preview=decision.approved_preview,
            owner_approved_meaning=decision.approved_meaning,
            approved_request_id=decision.request_id,
            approved_text_sha256=decision.text_sha256)
        current()
        if (type(receipt) is not dict or set(receipt) != {'state','language','evidence'}
                or receipt['state'] != 'TTS_SUBPROCESS_COMPLETED'
                or receipt['language'] != target
                or receipt['evidence'] != 'requires_independent_physical_audio_confirmation'):
            raise RouteHold('ORIGINAL_NATIVE_PLAYBACK_RECEIPT_INVALID')
        response['state'] = 'NATIVE_TTS_SUBPROCESS_COMPLETED'
        response['playback'] = dict(receipt)
        return response
