"""NOX V16 P02: three missing PACK01 ports using EXISTING native owners.

Not an HTTP service, RAG index, call-log database, browser bridge or voice engine.
#6 must obtain a trusted Windows scope from the canonical host, approve the
exact route and bind its existing provider. All unbound ports remain HOLD.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
import re
import threading
from typing import Callable, Any

from p02_capabilities import Identity, LocalVoicePipeline
from p02_chat_bridge import ChatBridge
from p02_runtime import P02Error, P02Store

_SID = re.compile(r"S-1-[0-9]{1,15}(?:-[0-9]{1,10}){1,15}\Z")
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")
_STATUS = frozenset({"requested", "ringing", "connected", "completed", "cancelled", "failed", "declined"})


class RouteHold(P02Error):
    """Unavailable existing owner implementation: explicitly HOLD, not success."""


@dataclass(frozen=True)
class NativeScope:
    """Created only by the authenticated native host, NEVER from page JSON."""
    tenant: str
    principal: str
    conversation_id: str
    windows_sid: str
    session_id: str
    identity: Identity


def _bounded(value: str, n: int = 128) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= n and value.strip() == value
            and all(ord(ch) >= 32 for ch in value))


class OwnerTwoPorts:
    """Adapters for chat.rag, chat.voice, calls.history; zero new persistent state."""

    def __init__(self, *, store: P02Store, native_authorize: Callable[[NativeScope, str], bool],
                 rag_index: Any = None,
                 voice_pipeline: LocalVoicePipeline | None = None,
                 native_take_audio: Callable[[NativeScope, str], bytes] | None = None,
                 native_mic_consent: Callable[[NativeScope, str], bool] | None = None,
                 native_store_output_audio: Callable[[NativeScope, bytes], str] | None = None,
                 native_discard_output_audio: Callable[[NativeScope, str], bool] | None = None,
                 native_call_history: Callable[[NativeScope, int], list[dict]] | None = None,
                 owner_ready: Callable[[str], bool] | None = None):
        if not isinstance(store, P02Store) or not callable(native_authorize):
            raise ValueError("One existing P02Store and native authorization required")
        self.store, self.authorize = store, native_authorize
        self.rag, self.voice, self.take_audio, self.call_history = (
            rag_index, voice_pipeline, native_take_audio, native_call_history)
        self.store_output_audio = native_store_output_audio
        self.discard_output_audio = native_discard_output_audio
        # R17 donor: only the authenticated host can attest this capture's
        # current OS permission and user consent; no page JSON flags.
        self.mic_consent = native_mic_consent
        self.owner_ready = owner_ready

    def _session(self, scope: NativeScope, route: str) -> None:
        if (not isinstance(scope, NativeScope)
                or not all(_bounded(x, 256) for x in (
                    scope.tenant, scope.principal, scope.conversation_id, scope.session_id))
                or not isinstance(scope.windows_sid, str) or not _SID.fullmatch(scope.windows_sid)
                or not isinstance(scope.identity, Identity)
                or scope.identity.tenant != scope.tenant
                or scope.identity.principal != scope.principal
                or scope.identity.session_id != scope.session_id):
            raise PermissionError("Authentic native SID and session required")
        if self.authorize(scope, route) is not True:
            raise PermissionError("Native host denied route permission")
        # Existing store enforces tenant+principal+conversation ownership.
        self.store.history(scope.tenant, scope.principal, scope.conversation_id, 1)

    def available(self, route: str) -> bool:
        """A source method alone never proves a real installed service."""
        if not callable(self.owner_ready):
            return False
        implementations = {"chat.rag": callable(getattr(self.rag, "context", None)),
                           "chat.voice": isinstance(self.voice, LocalVoicePipeline)
                                         and callable(self.take_audio)
                                         and callable(self.mic_consent)
                                         and callable(self.store_output_audio)
                                         and self.voice.approved_models,
                           "calls.history": callable(self.call_history)}
        try:
            return bool(implementations.get(route) and self.owner_ready(route) is True)
        except Exception:
            return False

    def rag_context(self, scope: NativeScope, args: dict) -> dict:
        """Read existing P04 index; never create an index or elevate citations."""
        self._session(scope, "chat.rag")
        if not self.available("chat.rag"):
            raise RouteHold("EXISTING_P04_RAG_NOT_READY")
        if not isinstance(args, dict):
            raise ValueError("Invalid RAG request")
        query, topk = args.get("query"), args.get("top_k", 5)
        if not isinstance(query, str) or not query.strip() or len(query) > 16000:
            raise ValueError("Bounded RAG query required")
        if type(topk) is not int or not 1 <= topk <= 20:
            raise ValueError("top_k must be 1..20")
        output = self.rag.context(scope.windows_sid, scope.conversation_id, query, topk)
        context, citations = ChatBridge._rag_evidence(output)
        return {"context": context, "sources": citations}

    def captured_voice(self, scope: NativeScope, args: dict, stop: threading.Event | None = None) -> dict:
        """Consume ONLY native-host-captured audio; never accept JS audio/path bytes."""
        if (type(args) is not dict or any(key in args for key in
                ("audio", "audio_path", "microphone_consent", "mic_consent"))):
            raise PermissionError("Audio and consent must come from trusted native capture")
        # Capture primitive request values before any native callback can mutate
        # the caller's request. Invalid input must not burn a one-use capture.
        cap_id = args.get("capture_id")
        source, target, voice = args.get("source"), args.get("target"), args.get("voice")
        mode, level = args.get("mode", "translate"), args.get("level", "A2")
        self._session(scope, "chat.voice")
        if not self.available("chat.voice"):
            raise RouteHold("INSTALLED_LOCAL_ASR_TTS_OR_HOST_CAPTURE_HOLD")
        if type(cap_id) is not str or not _TOKEN.fullmatch(cap_id):
            raise ValueError("Opaque native capture id required")
        self.voice.validate_request(scope.identity, source=source, target=target,
                                    voice=voice, mode=mode, level=level)
        # STOP before consumption must preserve the one-use native capture.
        if stop is not None and stop.is_set():
            raise RouteHold("NATIVE_VOICE_STOPPED_BEFORE_CAPTURE")
        try:
            consented = self.mic_consent(scope, cap_id) is True
        except Exception as exc:
            raise RouteHold("NATIVE_MIC_PERMISSION_CHECK_HOLD") from exc
        if not consented:
            raise PermissionError("NATIVE_MIC_CONSENT_REQUIRED")
        if stop is not None and stop.is_set():
            raise RouteHold("NATIVE_VOICE_STOPPED_BEFORE_CAPTURE")
        # Native host consumes capture exactly once; a second lookup MUST fail.
        try:
            audio = self.take_audio(scope, cap_id)
        except (KeyError, FileNotFoundError) as exc:
            raise RouteHold("NATIVE_CAPTURE_EXPIRED_OR_CONSUMED") from exc
        if not isinstance(audio, bytes) or not 0 < len(audio) <= 16*1024*1024:
            raise RouteHold("NATIVE_AUDIO_CAPTURE_UNAVAILABLE")
        if stop is not None and stop.is_set():
            raise RouteHold("NATIVE_VOICE_STOPPED_BEFORE_ASR")
        result = self.voice.run(
            scope.identity, audio, source=source, target=target, voice=voice,
            mode=mode, level=level, microphone_consent=consented, stop=stop)
        # A STOP while ASR/LLM/TTS was running must not publish new audio.
        if stop is not None and stop.is_set():
            raise RouteHold("NATIVE_VOICE_STOPPED_BEFORE_OUTPUT")
        LocalVoicePipeline.validate_result(result, source=source, target=target, mode=mode)
        # Native host owns the temporary output bytes; no raw audio to page JSON.
        output_id = self.store_output_audio(scope, result.audio)
        # Reuse R18's post-persistence STOP boundary, then revoke the exact
        # native receipt. Only the authenticated host may delete its audio.
        if stop is not None and stop.is_set():
            if (not isinstance(output_id, str) or not _TOKEN.fullmatch(output_id)
                    or not callable(self.discard_output_audio)):
                raise RouteHold("NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE_CLEANUP_HOLD")
            try:
                discarded = self.discard_output_audio(scope, output_id)
            except Exception as exc:
                raise RouteHold("NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE_CLEANUP_HOLD") from exc
            if discarded is not True:
                raise RouteHold("NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE_CLEANUP_HOLD")
            raise RouteHold("NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE")
        if not isinstance(output_id, str) or not _TOKEN.fullmatch(output_id):
            raise RouteHold("NATIVE_OUTPUT_AUDIO_RECEIPT_REQUIRED")
        return {"transcript": result.transcript, "response": result.response,
                "output_audio_id": output_id, "target_lang": result.target_lang,
                "mode": result.mode}

    def calls_history(self, scope: NativeScope, args: dict) -> dict:
        """Read EXISTING authorized provider's call history; no new storage."""
        self._session(scope, "calls.history")
        if not self.available("calls.history"):
            raise RouteHold("EXISTING_CALL_HISTORY_PROVIDER_HOLD")
        if not isinstance(args, dict):
            raise ValueError("Call history request must be an object")
        limit = args.get("limit", 30)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Call history limit 1..100")
        rows = self.call_history(scope, limit)
        if not isinstance(rows, list) or len(rows) > limit:
            raise RouteHold("CALL_HISTORY_PROVIDER_INVALID")
        safe = []
        for r in rows:
            if (not isinstance(r, dict) or r.get("tenant") != scope.tenant
                    or r.get("principal") != scope.principal
                    or not _bounded(r.get("call_id", ""))
                    or r.get("status") not in _STATUS
                    or type(r.get("started_epoch")) is not int
                    or not 0 <= r["started_epoch"] <= 253402300799):
                raise PermissionError("Call record not authorized / malformed")
            # Never copy opaque provider/internal attributes into the WebView.
            safe.append({"call_id": r["call_id"], "status": r["status"],
                         "started_epoch": r["started_epoch"]})
        return {"calls": safe}

    def route_methods(self):
        """#6 passes these callables to its EXISTING 50-route dispatcher only."""
        return {"chat.rag": self.rag_context,
                "chat.voice": self.captured_voice,
                "calls.history": self.calls_history}


def register_with_existing_pack01(dispatcher, bound_port_type,
                                  host_scope_from_session: Callable,
                                  owner_ports: OwnerTwoPorts, *, receipt: str,
                                  native_stop_from_session: Callable | None = None) -> frozenset[str]:
    """Bind three owner #2 ports to #6's already-existing PACK01 dispatcher.

    The native scope resolver is provided by the integrator, never page input;
    no extra router, processes or direct WebView privilege are introduced.
    """
    if (not callable(host_scope_from_session) or not isinstance(owner_ports, OwnerTwoPorts)
            or not _bounded(receipt, 256)):
        raise RouteHold("CURRENT_OWNER_RECEIPT_AND_NATIVE_SCOPE_REQUIRED")
    if native_stop_from_session is not None and not callable(native_stop_from_session):
        raise RouteHold("NATIVE_VOICE_STOP_BINDING_REQUIRED")
    mapping = owner_ports.route_methods()
    # Preflight all three canonical owner routes BEFORE publishing any handler.
    # A late foreign owner/missing route must not leave two live P02 ports.
    routes = getattr(dispatcher, "routes", None)
    ports = getattr(dispatcher, "ports", None)
    if not isinstance(routes, Mapping) or not isinstance(ports, dict) or not callable(getattr(dispatcher, "bind", None)):
        raise RouteHold("EXISTING_PACK01_DISPATCHER_REQUIRED")
    for route in mapping:
        if route in ports:
            raise RouteHold("EXISTING_ROUTE_ALREADY_BOUND_NO_OVERRIDE")
        info = routes.get(route)
        if not isinstance(info, Mapping) or type(info.get("owner")) is not int or info["owner"] != 2:
            raise RouteHold("CANONICAL_PACK01_OWNER_ROUTE_REQUIRED")
    staged = {}
    for route, handler in mapping.items():
        def call(session, args, fn=handler, name=route):
            native_scope = host_scope_from_session(session)
            if name == "chat.voice":
                if native_stop_from_session is None:
                    raise RouteHold("NATIVE_VOICE_STOP_BINDING_REQUIRED")
                # Reuse the host session's existing cancellation token. Never
                # create a disconnected Event or read STOP authority from args.
                stop = native_stop_from_session(session)
                if not isinstance(stop, threading.Event):
                    raise RouteHold("NATIVE_VOICE_STOP_TOKEN_REQUIRED")
                return fn(native_scope, args, stop=stop)
            return fn(native_scope, args)
        def available(name=route):
            return (name != "chat.voice" or native_stop_from_session is not None) and owner_ports.available(name)
        staged[route] = bound_port_type(call, available, receipt, 2)
    try:
        for route, port in staged.items():
            dispatcher.bind(route, port)
            if ports.get(route) is not port:
                raise RouteHold("EXISTING_PACK01_BIND_RESULT_MISMATCH")
    except Exception:
        # Only remove OUR exact new port objects, never another owner's
        # concurrent registration. This is rollback, not a second router.
        for route, port in staged.items():
            if ports.get(route) is port:
                ports.pop(route, None)
        raise
    return frozenset(mapping)