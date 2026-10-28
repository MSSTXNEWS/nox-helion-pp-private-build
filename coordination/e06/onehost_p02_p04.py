"""E06 V16 single-host P02↔P04 admission seam.

Uses ONLY the owner P02 ChatBridge/P02Store/OllamaClient and P04 LocalRag.
Neither a new HTTP endpoint, database, GPU worker nor events.v3 bus is created.
Source component candidate: native Windows/LLM/GPU/E07 acceptance is HOLD.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from p02_capabilities import context_key
from p02_chat_bridge import ChatBridge
from p02_owner_route_ports import NativeScope
from p02_runtime import OllamaClient, P02Store
from rag_python_compat import LocalRag, p02_callback

_SID = re.compile(r"S-1-[0-9]{1,15}(?:-[0-9]{1,10}){1,15}\Z")
_GPU_COMMANDS = frozenset({"gpu.stop", "gpu.pause", "gpu.resume", "gpu.checkpoint", "gpu.status"})
_GPU_EVENTS = frozenset({"task.started", "task.progress", "training.step",
                         "checkpoint.saved", "task.completed", "task.failed",
                         "model.stopped", "gpu.sample"})
_P02_CHAT_FRAMES = frozenset({"chat.start", "chat.sources", "chat.delta",
                              "chat.complete", "chat.error"})


class OneHostHold(RuntimeError):
    """The existing owner/native contract has not been proved; do not fake success."""


def _owner_wire_snapshot(payload: Mapping, *, kind: str, max_bytes: int = 262144) -> dict:
    """Freeze ONE verified-owner JSON payload before callbacks can mutate it.

    This is a local value copy, NOT a new message bus, certificate or GPU
    receipt. Native callbacks still bear the burden of authenticity.
    """
    if not isinstance(payload, Mapping) or any(type(k) is not str for k in payload):
        raise OneHostHold(f"{kind}_OWNER_JSON_OBJECT_REQUIRED")
    try:
        raw = json.dumps(dict(payload), ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":"))
        wire_bytes = raw.encode("utf-8")  # Reject lone surrogates before UI/IPC.
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise OneHostHold(f"{kind}_OWNER_JSON_VALUE_INVALID") from exc
    if len(wire_bytes) > max_bytes:
        raise OneHostHold(f"{kind}_OWNER_JSON_OVER_LIMIT")
    return json.loads(raw)


class P02P04OneHost:
    """Bind already-created owner objects once, during native host startup.

    Native authorization, SID lookup, context->existing-chat resolution, genuine
    P04 worker control and P05 event verification are injected by ONE WPF host.
    Calling this from WebView/JS directly is forbidden.
    """

    def __init__(
        self, *, chat: ChatBridge, store: P02Store, rag: LocalRag,
        native_sid: Callable[[str, str], str],
        native_context_chat: Callable[[str, NativeScope], str],
        native_authorize: Callable[[NativeScope, str], bool],
        approved_core_ids: frozenset[str], approved_personas: frozenset[str],
        native_verify_registry: Callable[[frozenset[str], frozenset[str]], bool],
        owner_gpu_control: Callable[[NativeScope, str, str], dict] | None = None,
        native_verify_gpu_ack: Callable[[dict], bool] | None = None,
        native_verify_v3: Callable[[dict], bool] | None = None,
        native_publish_v3: Callable[[dict], None] | None = None,
    ):
        if (not isinstance(chat, ChatBridge) or not isinstance(store, P02Store)
                or chat.store is not store or not isinstance(chat.ollama, OllamaClient)
                or not isinstance(rag, LocalRag)):
            raise OneHostHold("EXISTING_P02_P04_INSTANCES_REQUIRED")
        if (not callable(native_sid) or not callable(native_context_chat)
                or not callable(native_authorize)):
            raise OneHostHold("TRUSTED_NATIVE_HOST_CALLBACKS_REQUIRED")
        if (type(approved_core_ids) is not frozenset or len(approved_core_ids) != 8
                or "HELION" in approved_core_ids
                or any(not isinstance(x, str) or not x or len(x) > 128
                       for x in approved_core_ids)
                or type(approved_personas) is not frozenset
                or len(approved_personas) != 5
                or any(not isinstance(x, str) or not x or len(x) > 128
                       for x in approved_personas)):
            raise OneHostHold("ORIGINAL_EIGHT_CORE_AND_FIVE_PERSONA_REGISTRY_REQUIRED")
        if not callable(native_verify_registry) or native_verify_registry(
                approved_core_ids, approved_personas) is not True:
            raise OneHostHold("ORIGINAL_P01_CORE_PERSONA_RECEIPT_REQUIRED")
        # One physical loopback Ollama server for chat and P04 embeddings.
        # Localhost and 127.0.0.1 may address the same listener, but ports
        # must agree. Both owner constructors independently enforce loopback.
        ollama_uri, embed_uri = urlsplit(chat.ollama.base), urlsplit(rag.endpoint)
        if (not ollama_uri.port or ollama_uri.port != embed_uri.port):
            raise OneHostHold("ONE_OLLAMA_ENDPOINT_PORT_REQUIRED")
        # A matching port is NOT a listener identity: IPv4, IPv6 and DNS
        # localhost can resolve to different loopback processes on that port.
        # Refuse an unproven single-host binding rather than silently using
        # two Ollama listeners. Owners may explicitly configure the SAME
        # normalized local scheme+host+port; E07 must still test the process.
        if (ollama_uri.scheme != embed_uri.scheme
                or ollama_uri.hostname != embed_uri.hostname):
            raise OneHostHold("ONE_OLLAMA_LISTENER_IDENTITY_REQUIRED")
        if chat.rag_context is not None:
            raise OneHostHold("RAG_ALREADY_BOUND_DO_NOT_OVERRIDE")
        self.chat, self.store, self.rag = chat, store, rag
        self._native_sid = native_sid
        self._native_context_chat = native_context_chat
        self._authorize = native_authorize
        self._cores = approved_core_ids | frozenset({"HELION"})
        self._personas = approved_personas
        self._gpu = owner_gpu_control
        self._verify_ack = native_verify_gpu_ack
        self._verify_v3 = native_verify_v3
        self._publish_v3 = native_publish_v3

        # The only RAG binding is the existing P04 callback. Never create a new
        # index or mutable per-user callback on the shared ChatBridge.
        self.chat.rag_context = p02_callback(rag, native_sid)

    def _admit(self, scope: NativeScope, operation: str) -> None:
        if type(scope) is not NativeScope:
            raise PermissionError("NATIVE_SCOPE_REQUIRED_NOT_WEBVIEW_JSON")
        who = scope.identity
        if (who.tenant != scope.tenant or who.principal != scope.principal
                or who.session_id != scope.session_id):
            raise PermissionError("NATIVE_IDENTITY_SESSION_MISMATCH")
        sid = self._native_sid(scope.tenant, scope.principal)
        if (not isinstance(sid, str) or _SID.fullmatch(sid) is None
                or sid != scope.windows_sid):
            raise PermissionError("NATIVE_WINDOWS_SID_MISMATCH")
        token = context_key(who, self._cores, self._personas)
        if self._native_context_chat(token, scope) != scope.conversation_id:
            raise PermissionError("NATIVE_CONTEXT_NOT_BOUND_TO_EXISTING_CHAT")
        if self._authorize(scope, operation) is not True:
            raise PermissionError("NATIVE_OWNER_ROUTE_DENIED")
        # This checks the same existing SQLite history and tenant ACL. No
        # initialize(), CREATE TABLE, connection.open() or migration happens here.
        self.store.history(scope.tenant, scope.principal, scope.conversation_id, 1)

    def stream_chat(self, scope: NativeScope, model: str, prompt: str,
                    stop: threading.Event | None = None):
        """Return owner P02 chat frames to the existing native WebView2 channel.

        P02 chat.start/delta/sources are NOT events.v3 event_type values:
        never pretend these frames were published on the P05 bus.
        """
        self._admit(scope, "chat.send")
        if stop is not None and not isinstance(stop, threading.Event):
            raise TypeError("NATIVE_STOP_EVENT_REQUIRED")
        # The owner ChatBridge is a lazy generator: its SQLite write and
        # streaming work happen at next(), NOT when send() is called. Recheck
        # the native session immediately before every owner advancement so a
        # revoked SID/route/context cannot keep receiving deltas or completion.
        # This adds no LLM, host, database, RAG index or GPU worker.
        native_stop = stop if stop is not None else threading.Event()
        owner_frames = self.chat.send(scope.tenant, scope.principal,
                                      scope.conversation_id, model, prompt,
                                      native_stop)

        def guarded_stream():
            try:
                while True:
                    # A STOP delivered between yields must not advance the
                    # existing owner generator (which can read private RAG and
                    # write to the original SQLite history during next()).
                    if native_stop.is_set():
                        return
                    self._admit(scope, "chat.send")
                    if native_stop.is_set():
                        return
                    try:
                        frame = next(owner_frames)
                    except StopIteration:
                        return
                    # STOP may arrive inside a blocking owner/RAG/Ollama next().
                    # Drop the returned frame before citations reach WebView2.
                    # This cannot undo writes already done INSIDE the owner;
                    # native atomic SQLite/worker E2E remains HOLD.
                    if native_stop.is_set():
                        return
                    # Freeze the original P02 frame BEFORE the post-await
                    # native authorization callback. Like GPU/event receipts,
                    # this must not allow a callback or producer to mutate a
                    # delta into completion or replace source citations.
                    # The bounded copy is a wire value, not a second chat.
                    wire = _owner_wire_snapshot(frame, kind="P02_CHAT_FRAME",
                                                max_bytes=1048576)
                    if (type(wire.get("type")) is not str
                            or wire["type"] not in _P02_CHAT_FRAMES):
                        raise OneHostHold("EXISTING_P02_CHAT_FRAME_TYPE_REQUIRED")
                    # A blocking owner generator may complete a RAG/LLM await
                    # after native permission was revoked. Pre-next admission
                    # alone cannot protect the newly produced frame.
                    self._admit(scope, "chat.send")
                    # Recheck after host authorization, which may itself block
                    # or observe cancellation. No fabricated STOP frame.
                    if native_stop.is_set():
                        return
                    yield wire
            finally:
                # Releasing a partially consumed stream must cancel the native
                # owner request, never leave an orphan Ollama stream running.
                native_stop.set()
                owner_frames.close()

        return guarded_stream()

    def gpu_command(self, scope: NativeScope, command: str, worker_id: str) -> dict:
        """Call ONLY the already-running P04 managed worker's native control port."""
        if (type(command) is not str or command not in _GPU_COMMANDS
                or not isinstance(worker_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_.:-]{1,128}", worker_id)):
            raise OneHostHold("GPU_OWNER_COMMAND_OR_WORKER_INVALID")
        self._admit(scope, command)
        if not callable(self._gpu) or not callable(self._verify_ack):
            raise OneHostHold("EXISTING_P04_GPU_WORKER_CONTROL_NOT_BOUND")
        reply = _owner_wire_snapshot(self._gpu(scope, command, worker_id),
                                     kind="GPU_ACK")
        # Never let a verifier mutate the ACK that the UI receives. Only the
        # original owner bytes (captured before verify) may cross this seam.
        if (reply.get("worker_id") != worker_id
                or reply.get("command") != command
                or self._verify_ack(_owner_wire_snapshot(reply, kind="GPU_ACK")) is not True):
            raise OneHostHold("GPU_OWNER_OBSERVED_ACK_RECEIPT_REQUIRED")
        # Native authorization can expire while a GPU owner port blocks.
        # Recheck before returning even an ACK to the UI.
        self._admit(scope, command)
        # A verified command ACK is not proof of a completed training step,
        # checkpoint, evaluation, CUDA availability or resumed optimizer.
        return reply

    def publish_owner_gpu_event(self, scope: NativeScope, event: Mapping) -> None:
        """Forward one owner/P05-verified event unchanged, never synthesize GPU data."""
        self._admit(scope, "gpu.observe")
        snapshot = _owner_wire_snapshot(event, kind="P05_EVENT")
        if (snapshot.get("schema") != "NOX-INSTALLER-EVENT-v3"
                or snapshot.get("package_id") != "P04"
                or type(snapshot.get("event_type")) is not str
                or snapshot["event_type"] not in _GPU_EVENTS
                or snapshot.get("evidence_verified") is not True
                or not callable(self._verify_v3)
                or not callable(self._publish_v3)
                or self._verify_v3(_owner_wire_snapshot(snapshot, kind="P05_EVENT")) is not True):
            raise OneHostHold("EXISTING_P05_V3_VERIFIED_EVENT_REQUIRED")
        # Event verification may await an owner receipt; refuse publication
        # if native scope was revoked while that verification was in flight.
        self._admit(scope, "gpu.observe")
        # Verification may mutate its argument or the caller may mutate the
        # source mapping mid-callback; publish only the PRE-VERIFICATION bytes.
        self._publish_v3(_owner_wire_snapshot(snapshot, kind="P05_EVENT"))
