"""NOX V16 PACK01 — native in-process bindings for the fifty-route catalogue.

Does not launch a server, use another LLM, replace SQLite or install anything.
The trusted Windows host supplies existing owner services and authenticated scope.
Unknown/unavailable actions always HOLD; never simulate completion.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Any
import json
import re

MAX_TEXT = 20000
MAX_ANSWER = 60000
ROUTE = re.compile(r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$")
TASK = re.compile(r"^NIP01-[0-9]{2}$")
ALLOWED_ROUTES = frozenset((
    "helion.chat","core.chat","persona.chat","chat.model","chat.history",
    "chat.attach","chat.rag","chat.voice","chat.stop","chat.commands",
    "models.catalog","models.installed","models.pull","models.gguf.import",
    "models.queue","models.cancel","models.retry","models.digest",
    "models.preflight","models.licenses",
    "rag.import","rag.search","memory.manage","datasets.review","gpu.preflight",
    "training.start","training.pause","training.resume","training.checkpoints",
    "training.evaluate",
    "translate.ru_es","maestro.spanish","voice.settings","calls.dial",
    "calls.history","media.player","media.subtitles","browser.open",
    "browser.bookmarks","images.generate",
    "space.news","space.weather","space.fx","space.bitcoin","space.brent",
    "system.telemetry","system.update","system.backup","system.pc_control",
    "mobile.connect",
))
assert len(ALLOWED_ROUTES) == 50

# Immutable canonical E06 admission floor. Kept local to support the existing
# standalone native host without importing a second dispatcher or mutable UI data.
# Cross-checked at source time against coordination/e06_host50/admission.py.
APPROVED_NATIVE_POLICY = (
    ("helion.chat", 2, "safe"),
    ("core.chat", 2, "safe"),
    ("persona.chat", 2, "safe"),
    ("chat.model", 2, "safe"),
    ("chat.history", 2, "sensitive"),
    ("chat.attach", 2, "sensitive"),
    ("chat.rag", 2, "safe"),
    ("chat.voice", 2, "sensitive"),
    ("chat.stop", 2, "safe"),
    ("chat.commands", 2, "safe"),
    ("models.catalog", 3, "safe"),
    ("models.installed", 3, "safe"),
    ("models.pull", 3, "sensitive"),
    ("models.gguf.import", 3, "sensitive"),
    ("models.queue", 3, "safe"),
    ("models.cancel", 3, "safe"),
    ("models.retry", 3, "sensitive"),
    ("models.digest", 3, "safe"),
    ("models.preflight", 3, "safe"),
    ("models.licenses", 3, "safe"),
    ("rag.import", 4, "sensitive"),
    ("rag.search", 4, "safe"),
    ("memory.manage", 4, "sensitive"),
    ("datasets.review", 4, "safe"),
    ("gpu.preflight", 4, "safe"),
    ("training.start", 4, "dangerous"),
    ("training.pause", 4, "safe"),
    ("training.resume", 4, "sensitive"),
    ("training.checkpoints", 4, "sensitive"),
    ("training.evaluate", 4, "safe"),
    ("translate.ru_es", 2, "sensitive"),
    ("maestro.spanish", 2, "safe"),
    ("voice.settings", 2, "safe"),
    ("calls.dial", 2, "dangerous"),
    ("calls.history", 2, "sensitive"),
    ("media.player", 1, "sensitive"),
    ("media.subtitles", 1, "safe"),
    ("browser.open", 1, "sensitive"),
    ("browser.bookmarks", 1, "safe"),
    ("images.generate", 4, "sensitive"),
    ("space.news", 5, "safe"),
    ("space.weather", 5, "safe"),
    ("space.fx", 5, "safe"),
    ("space.bitcoin", 5, "safe"),
    ("space.brent", 5, "safe"),
    ("system.telemetry", 5, "safe"),
    ("system.update", 1, "dangerous"),
    ("system.backup", 1, "dangerous"),
    ("system.pc_control", 1, "dangerous"),
    ("mobile.connect", 6, "sensitive"),
)

class HostHold(RuntimeError):
    """No concrete approved and working owner backend bound for this route."""

class HostDenied(PermissionError):
    """Native host refused permission, consent or session."""

@dataclass(frozen=True)
class NativeSession:
    """Constructed ONLY by authenticated native Windows host, never from page JSON."""
    tenant: str
    principal: str
    chat_id: str
    allowed: frozenset[str] = field(default_factory=frozenset)
    private_approved: frozenset[str] = field(default_factory=frozenset)
    # Verified by the trusted Windows host, never copied from WebView/page JSON.
    windows_sid: str = field(default="", repr=False)
    session_lease: str = field(default="", repr=False)

    def validate(self):
        if not all(isinstance(s, str) and 0 < len(s) <= 128 and
                   s == s.strip() and not any(ord(ch) < 32 or ord(ch) == 127 for ch in s)
                   for s in (self.tenant, self.principal, self.chat_id)):
            raise HostDenied("Invalid authenticated native session")
        # Native host only: permissions are immutable exact sets, never a
        # page-provided string or mutable set that callbacks could change.
        if type(self.allowed) is not frozenset or type(self.private_approved) is not frozenset:
            raise HostDenied("Immutable native route scopes required")
        if (any(type(route) is not str for route in self.allowed | self.private_approved) or
                not self.allowed.issubset(ALLOWED_ROUTES) or
                not self.private_approved.issubset(self.allowed)):
            raise HostDenied("Invalid route scopes")
        if (type(self.windows_sid) is not str or len(self.windows_sid) > 184 or
                type(self.session_lease) is not str or len(self.session_lease) > 128):
            raise HostDenied("Malformed native Windows SID/session lease")


def _native_owner_scope(session: NativeSession):
    """Pin exact host identity across nested owner callbacks, including SID/lease.

    This is a mutation guard, not a substitute for NoxPackHost's live Windows
    revocation verifier or the original owner's pre-effect authorization.
    """
    if type(session) is not NativeSession:
        raise HostDenied("Native owner session required")
    session.validate()
    return (session.tenant, session.principal, session.chat_id,
            session.allowed, session.private_approved,
            session.windows_sid, session.session_lease)


@dataclass(frozen=True)
class BoundPort:
    call: Callable[[NativeSession, dict], Any]
    available: Callable[[], bool]
    evidence_id: str
    owner: int

class NoxPackHost:
    """One in-process dispatcher. No network endpoint, subprocess or new database."""
    def __init__(self, catalog:dict, *,
                 native_approve:Callable[[NativeSession,str,dict],bool] | None=None,
                 native_session_live:Callable[[NativeSession],bool] | None=None):
        if not isinstance(catalog, dict) or catalog.get("version") != "NOX-INTEGRATION-PACK-01":
            raise ValueError("Wrong catalogue")
        actions = catalog.get("actions")
        if not isinstance(actions, list) or len(actions) != 50:
            raise ValueError("Exactly 50 approved contracts required")
        if any(type(item) is not dict for item in actions):
            raise ValueError("Native catalogue entries must be objects")
        ids = [item.get("routeId") for item in actions]
        if any(type(route) is not str for route in ids) or set(ids) != ALLOWED_ROUTES:
            raise ValueError("Route set mismatch or duplicate")
        task_ids = [item.get("taskId") for item in actions]
        if (any(type(task) is not str for task in task_ids) or
                task_ids != [f"NIP01-{i:02d}" for i in range(1, 51)]):
            raise ValueError("Invalid or reordered canonical TaskID")
        # UI catalogue is never allowed to downgrade dangerous routes to safe,
        # swap owner IDs or reorder immutable RouteID/TaskID associations.
        if tuple((item["routeId"], item.get("owner"), item.get("risk"))
                 for item in actions) != APPROVED_NATIVE_POLICY:
            raise ValueError("Immutable native route/owner/risk policy mismatch")
        # Freeze security decisions: caller edits to original catalogue must not
        # change consent or owner checks after native registration.
        self.routes = MappingProxyType({
            item["routeId"]: MappingProxyType(dict(item)) for item in actions
        })
        self.ports:dict[str,BoundPort] = {}
        self.native_approve = native_approve
        self.native_session_live = native_session_live

    def _require_live_session(self, session:NativeSession):
        """Trusted host must pin SID to OS token and lease to active session.

        No page-originated SID or lease is accepted; missing native verifier is
        HOLD. Only exact True from the host revocation probe admits a route.
        """
        session.validate()
        if re.fullmatch(r"S-[0-9]+(?:-[0-9]+){2,15}", session.windows_sid) is None:
            raise HostDenied("Native Windows SID required")
        if re.fullmatch(r"[A-Za-z0-9_-]{24,128}", session.session_lease) is None:
            raise HostDenied("Native session lease required")
        if not callable(self.native_session_live):
            raise HostHold("Trusted native SID-bound revocation probe not bound")
        try:
            live = self.native_session_live(session)
        except Exception as exc:
            raise HostDenied("Trusted native session verification failed") from exc
        if live is not True:
            raise HostDenied("Native Windows session revoked or mismatched")

    def bind(self, route:str, port:BoundPort):
        if route not in self.routes or not isinstance(port,BoundPort):
            raise ValueError("Unapproved native port")
        if type(port.owner) is not int or port.owner != self.routes[route]["owner"] or not isinstance(port.evidence_id,str) or not port.evidence_id.strip():
            raise HostHold("Matching owner receipt required")
        if not callable(port.call) or not callable(port.available):
            raise HostHold("Callable owner backend/probe required")
        if route in self.ports:
            raise HostDenied("Refuse competing handler for one route")
        self.ports[route] = port

    def advertise(self, session:NativeSession) -> dict:
        if type(session) is not NativeSession:
            raise HostDenied("Existing native session type required")
        session.validate()
        # Availability probes are native callbacks too. Keep the advertised
        # capabilities bound to the same identity and permission snapshot;
        # never return a partial list assembled across different sessions.
        def session_scope():
            session.validate()
            return (session.tenant, session.principal, session.chat_id,
                    session.allowed, session.private_approved,
                    session.windows_sid, session.session_lease)
        authorized_scope = session_scope()
        def require_unchanged_session():
            if session_scope() != authorized_scope:
                raise HostDenied("Native session changed during advertisement")
        out = {}
        advertised_ports = {}
        for route, item in self.routes.items():
            port = self.ports.get(route)
            ready = False
            # Dangerous actions are never probed merely to draw UI buttons.
            if port and route in session.allowed and item["risk"] != "dangerous":
                try:
                    self._require_live_session(session)
                    ready = port.available() is True
                    self._require_live_session(session)
                except (HostDenied, HostHold):
                    ready = False
                except Exception:
                    ready = False
                # Check even when the probe raised after mutating the session.
                require_unchanged_session()
                if self.ports.get(route) is not port:
                    raise HostHold("Native owner binding changed during advertisement")
            risk = item["risk"]
            scoped = ready and (risk == "safe" or route in session.private_approved)
            if risk == "dangerous":scoped = False
            if scoped:
                advertised_ports[route] = port
            out[route] = {"state":"CONNECTED" if scoped else "HOLD",
                          "enabled":bool(scoped),
                          "sourceId":port.evidence_id if scoped else None}
        require_unchanged_session()
        # A later probe can also revoke an earlier advertised route.
        if any(self.ports.get(route) is not port
               for route, port in advertised_ports.items()):
            raise HostHold("Native owner binding changed during advertisement")
        # A later capability probe could revoke a previously advertised SID.
        # Recheck every enabled capability before publishing the snapshot.
        for route, port in advertised_ports.items():
            try:
                self._require_live_session(session)
            except (HostDenied, HostHold):
                out[route] = {"state":"HOLD", "enabled":False, "sourceId":None}
            require_unchanged_session()
            if self.ports.get(route) is not port:
                raise HostHold("Native owner binding changed during advertisement")
        return out

    def execute(self, route:str, payload:dict, session:NativeSession):
        if type(session) is not NativeSession:
            raise HostDenied("Existing native session type required")
        session.validate()
        # A frozen dataclass is a host contract, not protection against a native
        # callback mutating it. Consent must remain bound to the exact identity
        # and permission snapshot checked at entry, on the same session object.
        def session_scope():
            session.validate()
            return (session.tenant, session.principal, session.chat_id,
                    session.allowed, session.private_approved,
                    session.windows_sid, session.session_lease)
        authorized_scope = session_scope()
        def require_unchanged_session():
            if session_scope() != authorized_scope:
                raise HostDenied("Native session changed during request admission")
        if type(route) is not str or route not in self.routes or not ROUTE.fullmatch(route) or route not in session.allowed:
            raise HostDenied("Route not allowed for current principal")
        # Revalidate the actual SID-bound lease before and after ALL callbacks,
        # including fresh dangerous consent, readiness, STOP and owner output.
        def require_current_authority():
            require_unchanged_session()
            self._require_live_session(session)
            require_unchanged_session()
        require_current_authority()
        if not isinstance(payload, dict):
            raise HostDenied("Missing/oversize request")
        try:
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
            raise HostDenied("Invalid native JSON request") from exc
        if len(raw) > 2 * 1024 * 1024:
            raise HostDenied("Missing/oversize request")
        # Capture the exact JSON approved at this native boundary. Neither the
        # source caller nor a provider-ready check may change the execution data.
        frozen_payload = json.loads(raw)
        require_current_authority()
        risk = self.routes[route]["risk"]
        if risk in ("sensitive","dangerous") and route not in session.private_approved:
            raise HostDenied("Native sensitive action scope required")
        if risk == "dangerous" and (
            not callable(self.native_approve) or
            self.native_approve(session,route,json.loads(raw)) is not True):
            raise HostDenied("Fresh native action approval required")
        require_current_authority()
        port = self.ports.get(route)
        if not port:raise HostHold("Actual owner backend unbound")
        try:ready = port.available() is True
        except Exception:ready = False
        require_current_authority()
        # A readiness callback may revoke or replace the native owner binding.
        # Never call a stale captured port after its registry lease has changed.
        if self.ports.get(route) is not port:
            raise HostHold("Native owner binding changed during request admission")
        if not ready:raise HostHold("Owner backend unavailable")
        result = port.call(session,frozen_payload)
        # A native handler may return data after revoking caller identity/port.
        # Fail closed before publishing any cross-session owner result.
        require_current_authority()
        if self.ports.get(route) is not port:
            raise HostHold("Native owner binding changed during execution")
        return result


class ExistingP02Adapter:
    """Actual owner #2 Python OllamaClient and P02Store, injected by trusted host."""
    def __init__(self, client, store, *, event_sink=None, native_selected_file=None):
        if not all(callable(getattr(client,n,None)) for n in ("models","stream","stop")):
            raise ValueError("Existing P02 OllamaClient required")
        if not all(callable(getattr(store,n,None)) for n in ("history","add_message","store_file")):
            raise ValueError("Existing P02Store required")
        self.client = client
        self.store = store
        self.event_sink = event_sink
        # Native file picker callback returns (MIME, binary stream); never page JSON.
        self.native_selected_file = native_selected_file

    def available(self) -> bool:
        try:return isinstance(self.client.models(),list)
        except Exception:return False

    def list_models(self, session, args):
        return {"models":self.client.models()}

    def history(self, session, args):
        limit = args.get("limit",100)
        if type(limit) != int or not 1 <= limit <= 250:
            raise HostDenied("History limit must be 1..250")
        return {"messages":self.store.history(session.tenant,session.principal,session.chat_id,limit)}

    def stop(self,session,args):
        self.client.stop()
        return {"stopRequested":True}  # No claim that remote Ollama hard-aborted.

    def chat(self, session, args):
        scope = _native_owner_scope(session)
        def check_scope():
            if _native_owner_scope(session) != scope:
                raise HostDenied("Native chat callback changed authenticated scope")
        message = args.get("text")
        model = args.get("model")
        if not isinstance(message,str) or not 0 < len(message) <= MAX_TEXT:
            raise HostDenied("Bounded nonempty chat text required")
        installed = self.client.models()
        if model not in installed:raise HostHold("Selected model not installed")
        check_scope()
        conversation = self.store.history(scope[0],scope[1],scope[2],80)
        check_scope()  # SQLite history is an owner callback.
        conversation = conversation + [{"role":"user","content":message}]
        answer = []
        bytes_seen = 0
        done = False
        for chunk in self.client.stream(model,conversation):
            check_scope()  # The streaming callback may rotate SID/lease.
            if not isinstance(chunk,dict) or not isinstance(chunk.get("delta"),str):
                raise HostHold("Invalid Ollama chunk")
            delta = chunk["delta"]
            bytes_seen += len(delta.encode("utf-8"))
            if bytes_seen > MAX_ANSWER:
                self.client.stop()
                raise HostHold("Answer too large")
            answer.append(delta)
            check_scope()  # Never emit into a stale native Windows session.
            if self.event_sink:
                self.event_sink({"route":"helion.chat","state":"streaming","delta":delta})
            check_scope()
            if chunk.get("done") is True:done = True
        if not done:raise HostHold("Missing Ollama terminal completion")
        text = "".join(answer)
        # Persist only for the exact authenticated scope from chat admission.
        check_scope()
        self.store.add_message(scope[0],scope[1],scope[2],"user",message)
        check_scope()  # Stop a second write if the first owner call changes identity.
        self.store.add_message(scope[0],scope[1],scope[2],"assistant",text)
        return {"answer":text,"done":True}

    def attach_native_selected(self,session,args):
        if not callable(self.native_selected_file):
            raise HostHold("Trusted native file picker not bound")
        initial_scope = _native_owner_scope(session)
        selected = self.native_selected_file(session)
        if not isinstance(selected,tuple) or len(selected)!=2:
            raise HostHold("Native file picker returned no approved file")
        mime,stream = selected
        if not isinstance(mime,str) or not callable(getattr(stream,"read",None)):
            raise HostDenied("Native file selection invalid")
        try:
            if _native_owner_scope(session) != initial_scope:
                raise HostDenied("Native file picker changed authenticated scope")
            # Existing P02 handles MIME/signature/size/SHA and SQLite ACL.
            result=self.store.store_file(initial_scope[0],initial_scope[1],
                initial_scope[2],mime,stream)
            if _native_owner_scope(session) != initial_scope:
                raise HostDenied("Native file store changed authenticated scope")
            return {"storedAttachment":result}
        finally:
            if callable(getattr(stream,"close",None)):stream.close()

    @staticmethod
    def scoped_commands(dispatcher,session,args):
        # No fake buttons: list ONLY native-advertised, enabled route capabilities.
        eligible=dispatcher.advertise(session)
        return {"commands":[route for route,cap in eligible.items()
            if cap["enabled"] and route!="chat.commands"]}

    def register(self, dispatcher:NoxPackHost, *, receipt:str):
        entries = {
          "helion.chat":self.chat,"core.chat":self.chat,"persona.chat":self.chat,
          "chat.model":self.list_models,"chat.history":self.history,"chat.stop":self.stop
        }
        entries["chat.commands"]=lambda scope,args:self.scoped_commands(dispatcher,scope,args)
        if callable(self.native_selected_file):
            entries["chat.attach"]=self.attach_native_selected
        for route,func in entries.items():
            # Chat quick commands reflect current host route registry, not Ollama status.
            ready=(lambda:True) if route=="chat.commands" else self.available
            dispatcher.bind(route,BoundPort(func,ready,receipt,2))
        return frozenset(entries)

def bind_owner_methods(dispatcher:NoxPackHost, owner:int, provider:object,
                       methods:dict[str,str], *, receipt:str,
                       probe:Callable[[],bool]):
    """Wire other owners' real methods without copying or inventing their implementations.

    Method names are supplied by trusted integrator, never selected from page input.
    A missing method is HOLD, not a no-op success.
    """
    if not callable(probe):raise ValueError("Owner-native health check required")
    wired = []
    for route,method in methods.items():
        if route not in dispatcher.routes or dispatcher.routes[route]["owner"] != owner:
            raise HostDenied("Route owner mismatch")
        fn = getattr(provider, method, None)
        if not callable(fn):raise HostHold("No real native method for "+route)
        dispatcher.bind(route,BoundPort(fn,probe,receipt,owner))
        wired.append(route)
    return frozenset(wired)


class ExistingP02VoiceAdapter:
    """Owner #2's ORIGINAL LocalVoicePipeline/ConsentGatedSip source methods.

    All audio, identity and SIP quote capabilities must come from trusted native
    Windows callbacks. This adapter does not install voices, initiate new provider
    sessions, create another LLM or record audio.
    """
    def __init__(self, voice_pipeline, sip_client, *,
                 native_identity, native_microphone_sample, native_provider_quote):
        if not callable(native_identity) or not callable(native_microphone_sample) or not callable(native_provider_quote):
            raise ValueError("Native identity/audio/quote selectors required")
        if not callable(getattr(voice_pipeline,"run",None)):
            raise ValueError("Existing owner LocalVoicePipeline required")
        if not callable(getattr(sip_client,"place",None)):
            raise ValueError("Existing owner ConsentGatedSip required")
        self.voice=voice_pipeline
        self.sip=sip_client
        self.native_identity=native_identity
        self.native_audio=native_microphone_sample
        self.native_quote=native_provider_quote

    def voice_ready(self):
        # True only if local weights were independently approved and an installed
        # voice exists. This is not a synthetic "connected" signal.
        return self.voice.approved_models is True and bool(self.voice.permitted_voices)

    def sip_ready(self):
        return (callable(self.sip.provider) and callable(self.sip.user_approval) and
                callable(self.sip.provider_quote_verify))

    def speak(self,session,args, *,mode):
        if not self.voice_ready():raise HostHold("Local ASR/LLM/TTS weights or voices missing")
        expected_scope = _native_owner_scope(session)
        identity=self.native_identity(session)
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native identity changed before microphone capture")
        captured=self.native_audio(session)
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native microphone callback changed session scope")
        if not isinstance(captured,bytes) or not 0<len(captured)<=16*1024*1024:
            raise HostDenied("No trusted bounded microphone capture")
        direction=args.get("direction","ru-es")
        if direction not in ("ru-es","es-ru"):raise HostDenied("Only RU/ES directions")
        source,target=("ru","es") if direction=="ru-es" else ("es","ru")
        voice=args.get("voiceId")
        if voice not in self.voice.permitted_voices:
            raise HostDenied("Voice must be one actually installed and approved")
        level=args.get("level","A2")
        # Native Windows permission for the microphone happens before returning bytes.
        response=self.voice.run(identity,captured,source=source,target=target,
            voice=voice,mode=mode,level=level,microphone_consent=True)
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native voice owner changed authenticated scope")
        return {"transcript":response.transcript,"answer":response.response,
                "audio":response.audio,"source":response.source_lang,
                "target":response.target_lang,"mode":response.mode}

    def voice_settings(self,session,args):
        # Read the owner-approved local voice identities. No synthetic voices or downloads.
        if not self.voice_ready():
            raise HostHold("Installed local voice catalogue not approved")
        return {"voices":sorted(self.voice.permitted_voices),
                "modelsApproved":self.voice.approved_models is True,
                "voiceCount":len(self.voice.permitted_voices)}

    def dial(self,session,args):
        if not self.sip_ready():raise HostHold("SIP provider, quote verification or consent not configured")
        expected_scope = _native_owner_scope(session)
        identity=self.native_identity(session)
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native identity changed before SIP quote")
        quote=self.native_quote(session)  # NEVER generated from client price or number.
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native SIP quote changed authenticated scope")
        if quote is None:raise HostHold("No live quote approved by SIP provider")
        result = self.sip.place(identity,quote)
        if _native_owner_scope(session) != expected_scope:
            raise HostDenied("Native SIP owner changed authenticated scope")
        return result

    def register(self,dispatcher:NoxPackHost,*,receipt:str):
        entries={
            "translate.ru_es":(lambda session,args:self.speak(session,args,mode="translate"),self.voice_ready),
            "maestro.spanish":(lambda session,args:self.speak(session,args,mode="maestro"),self.voice_ready),
            "calls.dial":(self.dial,self.sip_ready),
            "voice.settings":(self.voice_settings,self.voice_ready)
        }
        for route,(fn,ready) in entries.items():
            dispatcher.bind(route,BoundPort(fn,ready,receipt,2))
        return frozenset(entries)
