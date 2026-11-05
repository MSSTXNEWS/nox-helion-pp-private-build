"""NOX V16 PACK01 — native in-process bindings for the fifty-route catalogue.

Does not launch a server, use another LLM, replace SQLite or install anything.
The trusted Windows host supplies existing owner services and authenticated scope.
Unknown/unavailable actions always HOLD; never simulate completion.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Mapping
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

    def validate(self):
        if not all(isinstance(s, str) and 0 < len(s) <= 128
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

@dataclass(frozen=True)
class BoundPort:
    call: Callable[[NativeSession, dict], Any]
    available: Callable[[], bool]
    evidence_id: str
    owner: int

class NoxPackHost:
    """One in-process dispatcher. No network endpoint, subprocess or new database."""
    def __init__(self, catalog:dict, *, native_approve:Callable[[NativeSession,str,dict],bool] | None=None):
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
        out = {}
        inspected_ports = {}
        for route, item in self.routes.items():
            port = self.ports.get(route)
            inspected_ports[route] = port
            risk = item["risk"]
            # Do not probe an owner before native scope has authorized that route:
            # readiness callbacks can perform work even when advertise() says HOLD.
            # Dangerous actions are never advertised; execute() performs consent.
            can_probe = (route in session.allowed and risk != "dangerous" and
                         (risk == "safe" or route in session.private_approved))
            ready = False
            if port and can_probe:
                try:ready = port.available() is True
                except Exception:ready = False
            scoped = ready
            out[route] = {"state":"CONNECTED" if scoped else "HOLD",
                          "enabled":bool(scoped),
                          "sourceId":port.evidence_id if scoped else None}
        # A later readiness callback can revoke any previously probed route.
        # The existing native Windows host still owns cross-thread locking.
        # Readiness callbacks can revoke native scopes as well as ports.
        # Verify at the end of the entire probe pass (native host still owns
        # cross-thread locks), never advertise a just-revoked capability.
        session.validate()
        for route, cap in out.items():
            if not cap["enabled"]:
                continue
            risk = self.routes[route]["risk"]
            if (self.ports.get(route) is not inspected_ports[route]
                    or route not in session.allowed
                    or (risk != "safe" and route not in session.private_approved)):
                out[route] = {"state":"HOLD", "enabled":False, "sourceId":None}
        return out

    def execute(self, route:str, payload:dict, session:NativeSession):
        if type(session) is not NativeSession:
            raise HostDenied("Existing native session type required")
        session.validate()
        # Bind all native identity and permission fields to this operation.
        # A provider readiness/consent callback cannot switch principal/chat
        # while retaining a route name and making the final ACL check pass.
        admitted_scope = (session.tenant, session.principal, session.chat_id,
                          session.allowed, session.private_approved)
        if type(route) is not str or route not in self.routes or not ROUTE.fullmatch(route) or route not in session.allowed:
            raise HostDenied("Route not allowed for current principal")
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
        risk = self.routes[route]["risk"]
        if risk in ("sensitive","dangerous") and route not in session.private_approved:
            raise HostDenied("Native sensitive action scope required")
        port = self.ports.get(route)
        if not port:raise HostHold("Actual owner backend unbound")
        try:ready = port.available() is True
        except Exception:ready = False
        if not ready:raise HostHold("Owner backend unavailable")
        # The owner readiness probe may revoke a previously granted approval.
        # Check the ONE native approval after the last pre-dispatch probe;
        # never prompt for native consent on an unavailable route.
        if risk == "dangerous" and (
            not callable(self.native_approve) or
            self.native_approve(session,route,json.loads(raw)) is not True):
            raise HostDenied("Fresh native action approval required")
        # Readiness and consent callbacks can synchronously revoke/rebind a port.
        # A previously captured owner method must never dispatch after removal.
        if self.ports.get(route) is not port:
            raise HostHold("Native route owner binding changed before dispatch")
        # Privileged native callbacks can revoke the session scope during
        # readiness/consent. The one-host caller still owns cross-thread locking.
        session.validate()
        if (session.tenant, session.principal, session.chat_id,
            session.allowed, session.private_approved) != admitted_scope:
            raise HostDenied("Native identity or grants changed before dispatch")
        if route not in session.allowed or (risk in ("sensitive", "dangerous")
                and route not in session.private_approved):
            raise HostDenied("Native scope revoked before dispatch")
        return port.call(session,frozen_payload)


class ExistingP02Adapter:
    """Actual owner #2 Python OllamaClient and P02Store, injected by trusted host."""
    def __init__(self, client, store, *, event_sink=None, native_selected_file=None):
        if not all(callable(getattr(client,n,None)) for n in ("models","stream","stop")):
            raise ValueError("Existing P02 OllamaClient required")
        if not all(callable(getattr(store,n,None)) for n in ("history","add_message","add_exchange","store_file")):
            raise ValueError("Existing P02Store required")
        self.client = client
        self.store = store
        self._stop_epoch = 0  # Local monotonic cancellation fence; no new queue.
        self.event_sink = event_sink
        # Native file picker callback returns (MIME, binary stream); never page JSON.
        self.native_selected_file = native_selected_file

    def available(self) -> bool:
        # Empty model inventory is not a ready inference provider.
        # Local SQLite history and native STOP are independently bound below.
        try:
            models = self.client.models()
            return isinstance(models, list) and bool(models)
        except Exception:
            return False

    def list_models(self, session, args):
        return {"models":self.client.models()}

    def history(self, session, args):
        limit = args.get("limit",100)
        if type(limit) != int or not 1 <= limit <= 250:
            raise HostDenied("History limit must be 1..250")
        return {"messages":self.store.history(session.tenant,session.principal,session.chat_id,limit)}

    def stop(self,session,args):
        self._stop_epoch += 1
        self.client.stop()
        return {"stopRequested":True}  # No claim that remote Ollama hard-aborted.

    def chat(self, session, args):
        # Owner callbacks can revoke native identity/ACL during long Ollama streaming.
        # The pre-dispatch NoxPackHost gate alone is not sufficient at commit time.
        admitted_scope = (session.tenant, session.principal, session.chat_id,
                          session.allowed, session.private_approved)
        admitted_stop_epoch = self._stop_epoch
        def require_current_scope():
            if self._stop_epoch != admitted_stop_epoch:
                raise HostDenied("Native chat STOP revoked pending exchange")
            session.validate()
            if ((session.tenant, session.principal, session.chat_id,
                 session.allowed, session.private_approved) != admitted_scope):
                raise HostDenied("Native chat scope revoked during streaming")
        message = args.get("text")
        model = args.get("model")
        if not isinstance(message,str) or not 0 < len(message) <= MAX_TEXT:
            raise HostDenied("Bounded nonempty chat text required")
        installed = self.client.models()
        require_current_scope()
        if model not in installed:raise HostHold("Selected model not installed")
        conversation = self.store.history(session.tenant,session.principal,session.chat_id,80)
        require_current_scope()
        conversation = conversation + [{"role":"user","content":message}]
        answer = []
        bytes_seen = 0
        done = False
        for chunk in self.client.stream(model,conversation):
            require_current_scope()
            # A terminal Ollama frame ends this exchange. Reject any further
            # provider data rather than emitting/persisting unauthenticated tail.
            if done:
                raise HostHold("Ollama stream continued after terminal completion")
            if not isinstance(chunk,dict) or not isinstance(chunk.get("delta"),str):
                raise HostHold("Invalid Ollama chunk")
            delta = chunk["delta"]
            bytes_seen += len(delta.encode("utf-8"))
            if bytes_seen > MAX_ANSWER:
                self.client.stop()
                raise HostHold("Answer too large")
            answer.append(delta)
            if self.event_sink:
                require_current_scope()
                self.event_sink({"route":"helion.chat","state":"streaming","delta":delta})
                require_current_scope()
            if chunk.get("done") is True:done = True
        if not done:raise HostHold("Missing Ollama terminal completion")
        text = "".join(answer)
        # A done=True frame alone is not actual nonempty model output.
        # Never persist or acknowledge a blank provider completion as CHAT.
        if not text.strip():
            raise HostHold("Empty Ollama completion")
        # Commit BOTH rows together through the existing P02Store transaction.
        # Native revoke/STOP during commit aborts without orphan messages.
        self.store.add_exchange(session.tenant,session.principal,
                                session.chat_id,message,text,
                                authorize=require_current_scope)
        return {"answer":text,"done":True}

    def attach_native_selected(self,session,args):
        if not callable(self.native_selected_file):
            raise HostHold("Trusted native file picker not bound")
        selected = self.native_selected_file(session)
        if not isinstance(selected,tuple) or len(selected)!=2:
            raise HostHold("Native file picker returned no approved file")
        mime,stream = selected
        if not isinstance(mime,str) or not callable(getattr(stream,"read",None)):
            raise HostDenied("Native file selection invalid")
        try:
            # Existing P02 handles MIME/signature/size/SHA, SQLite ACL and stored ID.
            result=self.store.store_file(session.tenant,session.principal,
                session.chat_id,mime,stream)
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
            # STOP is an OS-local cancellation path, not model inventory.
            # An offline Ollama must never prevent an authorized stop request.
            # Offline history uses the existing scoped SQLite store, not Ollama.
            # Existing NoxPackHost still enforces SID/ACL and native permission.
            ready=(lambda:True) if route in ("chat.commands", "chat.stop", "chat.history") else self.available
            dispatcher.bind(route,BoundPort(func,ready,receipt,2))
        return frozenset(entries)

def bind_owner_methods(dispatcher:NoxPackHost, owner:int, provider:object,
                       methods:dict[str,str], *, receipt:str,
                       probe:Callable[[],bool]):
    """Bind existing native-owner methods as a fail-closed batch.

    The trusted integrator supplies the already-verified provider, receipt and
    native host lock. This is NOT a new host or an implementation of a missing
    provider. Stage all seven P01 routes (or another owner's approved subset)
    before any writes, and restore original ports if any bind fails.
    """
    if type(owner) is not int or not 1 <= owner <= 6:
        raise HostDenied("Exact native owner identity required")
    if type(methods) is not dict or not methods or not callable(probe):
        raise HostHold("Native method map and health probe required")
    if type(receipt) is not str or not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise HostHold("SHA-256 owner source receipt required")
    if not isinstance(dispatcher, NoxPackHost):
        raise HostDenied("Existing single native host required")

    # Preflight everything without touching dispatcher.ports; a late missing
    # method must never leave earlier route cards spuriously connected.
    before = dict(dispatcher.ports)
    planned = []
    for route, method in methods.items():
        if type(route) is not str or type(method) is not str or not method.isidentifier():
            raise HostDenied("Trusted literal route-to-method mapping required")
        item = dispatcher.routes.get(route)
        if (not isinstance(item, Mapping) or type(item.get("owner")) is not int
                or item["owner"] != owner):
            raise HostDenied("Native route owner mismatch")
        if route in before:
            raise HostDenied("Existing handler collision")
        if item.get("risk") == "dangerous" and not callable(dispatcher.native_approve):
            raise HostHold("Native dangerous-action consent is not installed")
        try:
            fn = getattr(provider, method)
        except Exception as exc:
            raise HostHold("Native owner implementation missing: "+route) from exc
        if not callable(fn):
            raise HostHold("Native owner implementation missing: "+route)
        planned.append((route, BoundPort(fn, probe, receipt, owner)))

    if (len(before) != len(dispatcher.ports)
            or any(dispatcher.ports.get(key) is not value for key, value in before.items())
            or any(route in dispatcher.ports for route, _ in planned)):
        raise HostHold("Native port registry changed during source preflight")
    try:
        for route, port in planned:
            dispatcher.bind(route, port)
    except Exception:
        # Undo ONLY writes owned by this batch. A broad clear/update would also
        # destroy another owner's independent registration if the native caller
        # accidentally failed to serialize an overlapping operation.
        for route, _port in planned:
            # The caller holds the EXISTING native host mutation lock.
            # Any port at a planned route did not exist before this batch,
            # including one injected by a failing bind callback: remove it.
            if route not in before:
                dispatcher.ports.pop(route, None)
        for route, old_port in before.items():
            if dispatcher.ports.get(route) is not old_port:
                dispatcher.ports[route] = old_port
        raise
    return frozenset(route for route, _ in planned)


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
        # Deny untrusted selectors BEFORE invoking identity or microphone callbacks.
        # A rejected direction/voice/CEFR level must never activate audio capture.
        direction=args.get("direction","ru-es")
        if type(direction) is not str or direction not in ("ru-es","es-ru"):
            raise HostDenied("Only RU/ES directions")
        voice=args.get("voiceId")
        if type(voice) is not str or not voice or len(voice)>128:
            raise HostDenied("Voice must be one actually installed and approved")
        level=args.get("level","A2")
        if type(level) is not str or level not in ("A1","A2","B1","B2","C1","C2"):
            raise HostDenied("Unsupported CEFR level")
        if mode not in ("translate","maestro"):
            raise HostDenied("Unsupported voice mode")
        if not self.voice_ready():raise HostHold("Local ASR/LLM/TTS weights or voices missing")
        if voice not in self.voice.permitted_voices:
            raise HostDenied("Voice must be one actually installed and approved")
        source,target=("ru","es") if direction=="ru-es" else ("es","ru")
        identity=self.native_identity(session)
        # The native callback obtains permission; no page-provided audio is accepted.
        captured=self.native_audio(session)
        if not isinstance(captured,bytes) or not 0<len(captured)<=16*1024*1024:
            raise HostDenied("No trusted bounded microphone capture")
        response=self.voice.run(identity,captured,source=source,target=target,
            voice=voice,mode=mode,level=level,microphone_consent=True)
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
        identity=self.native_identity(session)
        quote=self.native_quote(session)  # NEVER generated from client price or number.
        if quote is None:raise HostHold("No live quote approved by SIP provider")
        return self.sip.place(identity,quote)

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
