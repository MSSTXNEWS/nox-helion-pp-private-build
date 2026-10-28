"""NOX V16 P02: strict in-process boundary for the ONE existing native host.

This module does not create a server, process, SQLite database, route registry,
WebView bridge, RAG index, or LLM. E06 owns the actual Windows host and supplies
an authenticated native-session resolver and the already existing PACK01 router.
Page JSON is never accepted as user/session identity or authorization.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Callable, Any

MAX_INPUT = 64 * 1024
MAX_OUTPUT = 1024 * 1024
NONCE = re.compile(r"[0-9a-f]{32}\Z")
P02_ROUTES = frozenset({
    "helion.chat", "core.chat", "persona.chat", "chat.model", "chat.history",
    "chat.rag", "chat.voice", "chat.stop", "calls.history",
})


class ProtocolHold(Exception):
    """The native host must not treat this request as successful."""


class NativeIngress:
    """One authenticated entry to an *injected existing* PACK01 dispatcher.

    The host MUST create trusted session objects from its Windows SID/session,
    not from the message supplied by WebView. A host-owned dispatcher must
    independently enforce its own scopes, origin, consent and provider readiness.
    Each request ID is single-use. STOP can overtake an active serial chat call.
    """

    def __init__(self, existing_dispatcher: Any, native_session: Callable[[], Any],
                 *, expected_run_id: str):
        if not callable(native_session) or not (isinstance(expected_run_id, str)
                and 0 < len(expected_run_id) <= 128
                and all(32 <= ord(c) < 127 for c in expected_run_id)):
            raise ValueError("Trusted native resolver and canonical RunID required")
        if not callable(getattr(existing_dispatcher, "execute", None)):
            raise ValueError("Existing PACK01 dispatcher is required")
        self._dispatch = existing_dispatcher
        self._session = native_session
        self.run_id = expected_run_id
        self._seen = set()
        self._replay_lock = threading.Lock()
        self._serial = threading.Lock()

    def handle(self, encoded: bytes) -> bytes:
        """Pure byte-frame handler; no stdout/pipe/socket opened here."""
        if not isinstance(encoded, bytes) or not 0 < len(encoded) <= MAX_INPUT:
            raise ProtocolHold("NATIVE_FRAME_TOO_LARGE_OR_EMPTY")
        try:
            request = json.loads(encoded.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ProtocolHold("NATIVE_FRAME_INVALID_JSON") from exc
        if not isinstance(request, dict) or set(request) != {
                "protocol", "requestId", "route", "payload", "runId"}:
            raise ProtocolHold("NATIVE_ENVELOPE_FIELDS_INVALID")
        if request["protocol"] != "NOX-P02-NATIVE-v1" or request["runId"] != self.run_id:
            raise ProtocolHold("NATIVE_PROTOCOL_OR_RUN_MISMATCH")
        nonce, route, payload = request["requestId"], request["route"], request["payload"]
        if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
            raise ProtocolHold("NATIVE_NONCE_INVALID")
        if not isinstance(route, str) or route not in P02_ROUTES or not isinstance(payload, dict):
            raise ProtocolHold("NATIVE_ROUTE_OR_PAYLOAD_INVALID")
        # This intentionally bans any identity or permission claim in page data.
        if any(key in payload for key in (
                "tenant", "principal", "windows_sid", "session_id", "scopes",
                "private_approved", "native_approve", "nativeConsent", "admin")):
            raise ProtocolHold("PAGE_AUTHORITY_CLAIM_DENIED")
        with self._replay_lock:
            if nonce in self._seen:
                raise ProtocolHold("NATIVE_REQUEST_REPLAY_DENIED")
            # Never permit a replay after an eviction: fail closed and require
            # the native host to rotate the run/session rather than re-use IDs.
            if len(self._seen) >= 8192:
                raise ProtocolHold("NATIVE_NONCE_WINDOW_EXHAUSTED")
            self._seen.add(nonce)
        try:
            # Only host-supplied session objects; do not import an identity
            # from untrusted WebView JSON or invent a local user account.
            trusted_session = self._session()
            if trusted_session is None:
                raise ProtocolHold("NATIVE_AUTHENTICATED_SESSION_REQUIRED")
            if route == "chat.stop":
                result = self._dispatch.execute(route, payload, trusted_session)
            else:
                # Shared native SQLite connections may not be thread safe.
                # STOP is deliberately not queued behind this lock.
                with self._serial:
                    result = self._dispatch.execute(route, payload, trusted_session)
            answer = {"protocol": "NOX-P02-NATIVE-v1", "runId": self.run_id,
                      "requestId": nonce, "status": "OK", "result": result}
            out = json.dumps(answer, allow_nan=False, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
            if len(out) > MAX_OUTPUT:
                raise ProtocolHold("NATIVE_RESPONSE_TOO_LARGE")
            return out
        except ProtocolHold:
            raise
        except PermissionError as exc:
            raise ProtocolHold("NATIVE_PERMISSION_DENIED") from exc
        except Exception as exc:
            # Do not leak provider or user data through a privileged native error.
            raise ProtocolHold("NATIVE_PROVIDER_HOLD") from exc
