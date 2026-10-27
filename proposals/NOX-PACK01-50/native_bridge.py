"""NOX V16 PACK01 — native in-process bindings for the fifty-route catalogue.

Does not launch a server, use another LLM, replace SQLite or install anything.
The trusted Windows host supplies existing owner services and authenticated scope.
Unknown/unavailable actions always HOLD; never simulate completion.
"""
from __future__ import annotations
from dataclasses import dataclass, field
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
        if not self.allowed.issubset(ALLOWED_ROUTES):
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
        ids = [item.get("routeId") for item in actions if isinstance(item, dict)]
        if set(ids) != ALLOWED_ROUTES or len(set(ids)) != 50:
            raise ValueError("Route set mismatch or duplicate")
        task_ids = [item.get("taskId") for item in actions]
        if len(set(task_ids)) != 50 or any(not isinstance(t,str) or not TASK.fullmatch(t) for t in task_ids):
            raise ValueError("Invalid TaskID")
        self.routes = {item["routeId"]:item for item in actions}
        self.ports:dict[str,BoundPort] = {}
        self.native_approve = native_approve

    def bind(self, route:str, port:BoundPort):
        if route not in self.routes or not isinstance(port,BoundPort):
            raise ValueError("Unapproved native port")
        if port.owner != self.routes[route]["owner"] or not isinstance(port.evidence_id,str) or not port.evidence_id.strip():
            raise HostHold("Matching owner receipt required")
        if not callable(port.call) or not callable(port.available):
            raise HostHold("Callable owner backend/probe required")
        if route in self.ports:
            raise HostDenied("Refuse competing handler for one route")
        self.ports[route] = port

    def advertise(self, session:NativeSession) -> dict:
        session.validate()
        out = {}
        for route, item in self.routes.items():
            port = self.ports.get(route)
            ready = False
            if port and route in session.allowed:
                try:ready = port.available() is True
                except Exception:ready = False
            risk = item["risk"]
            scoped = ready and (risk == "safe" or route in session.private_approved)
            if risk == "dangerous":scoped = False
            out[route] = {"state":"CONNECTED" if scoped else "HOLD",
                          "enabled":bool(scoped),
                          "sourceId":port.evidence_id if scoped else None}
        return out

    def execute(self, route:str, payload:dict, session:NativeSession):
        session.validate()
        if route not in self.routes or not ROUTE.fullmatch(route) or route not in session.allowed:
            raise HostDenied("Route not allowed for current principal")
        if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False)) > 2*1024*1024:
            raise HostDenied("Missing/oversize request")
        risk = self.routes[route]["risk"]
        if risk in ("sensitive","dangerous") and route not in session.private_approved:
            raise HostDenied("Native sensitive action scope required")
        if risk == "dangerous" and (
            not callable(self.native_approve) or self.native_approve(session,route,payload) is not True):
            raise HostDenied("Fresh native action approval required")
        port = self.ports.get(route)
        if not port:raise HostHold("Actual owner backend unbound")
        try:ready = port.available() is True
        except Exception:ready = False
        if not ready:raise HostHold("Owner backend unavailable")
        return port.call(session,payload)


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
        message = args.get("text")
        model = args.get("model")
        if not isinstance(message,str) or not 0 < len(message) <= MAX_TEXT:
            raise HostDenied("Bounded nonempty chat text required")
        installed = self.client.models()
        if model not in installed:raise HostHold("Selected model not installed")
        conversation = self.store.history(session.tenant,session.principal,session.chat_id,80)
        conversation = conversation + [{"role":"user","content":message}]
        answer = []
        bytes_seen = 0
        done = False
        for chunk in self.client.stream(model,conversation):
            if not isinstance(chunk,dict) or not isinstance(chunk.get("delta"),str):
                raise HostHold("Invalid Ollama chunk")
            delta = chunk["delta"]
            bytes_seen += len(delta.encode("utf-8"))
            if bytes_seen > MAX_ANSWER:
                self.client.stop()
                raise HostHold("Answer too large")
            answer.append(delta)
            if self.event_sink:
                self.event_sink({"route":"helion.chat","state":"streaming","delta":delta})
            if chunk.get("done") is True:done = True
        if not done:raise HostHold("Missing Ollama terminal completion")
        text = "".join(answer)
        # Persist messages only after real terminal success.
        self.store.add_message(session.tenant,session.principal,session.chat_id,"user",message)
        self.store.add_message(session.tenant,session.principal,session.chat_id,"assistant",text)
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
