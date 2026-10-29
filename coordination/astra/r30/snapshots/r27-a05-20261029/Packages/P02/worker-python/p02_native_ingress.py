"""NOX V16 P02: strict in-process boundary for the ONE existing native host.

This module does not create a server, process, SQLite database, route registry,
WebView bridge, RAG index, or LLM. E06 owns the actual Windows host and supplies
an authenticated native-session resolver and the already existing PACK01 router.
Page JSON is never accepted as user/session identity or authorization.
"""
from __future__ import annotations

import json
import math
import re
import threading
from collections.abc import Mapping
from typing import Callable, Any

MAX_INPUT = 64 * 1024
MAX_OUTPUT = 1024 * 1024
MAX_JSON_NESTING = 512  # Independent of the host Python recursion limit.
NONCE = re.compile(r"[0-9a-f]{32}\Z")
P02_ROUTES = frozenset({
    "helion.chat", "core.chat", "persona.chat", "chat.model", "chat.history",
    "chat.rag", "chat.voice", "chat.stop", "calls.history",
})
# Optional P03 read-only admission. Sensitive model actions stay outside this
# ingress until the native owner explicitly binds and authorizes them.
P03_NATIVE_READ_ROUTES = frozenset({
    "models.catalog", "models.installed", "models.digest",
})


def _reject_nonfinite(_value: str):
    raise ValueError("Non-finite JSON constant forbidden")


def _finite_json_number(token: str) -> float:
    # JSON accepts exponent notation, e.g. 1e9999, which Python can parse as
    # +infinity even while literals NaN/Infinity are separately denied.
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON exponent forbidden")
    return value


def _reject_duplicate_fields(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicated JSON key forbidden")
        obj[key] = value
    return obj


def _enforce_json_depth(raw: str) -> None:
    """Reject excessive nesting before json.loads, including on Windows Python.

    Square/curly brackets inside JSON strings are not structural. The parser
    handles other JSON syntax errors and escaped Unicode after this preflight.
    """
    depth = 0
    quoted = False
    escaped = False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError("JSON nesting exceeds native frame limit")
        elif ch in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced native JSON delimiters")



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
                 *, expected_run_id: str, allow_modelcenter_reads: bool = False):
        if type(allow_modelcenter_reads) is not bool:
            raise ValueError("Explicit native ModelCenter read gate required")
        if not callable(native_session) or not (isinstance(expected_run_id, str)
                and 0 < len(expected_run_id) <= 128
                and all(32 <= ord(c) < 127 for c in expected_run_id)):
            raise ValueError("Trusted native resolver and canonical RunID required")
        if not callable(getattr(existing_dispatcher, "execute", None)):
            raise ValueError("Existing PACK01 dispatcher is required")
        self._dispatch = existing_dispatcher
        self._session = native_session
        self.run_id = expected_run_id
        self._modelcenter_reads = allow_modelcenter_reads
        self._seen = set()
        self._replay_lock = threading.Lock()
        self._serial = threading.Lock()

    def handle(self, encoded: bytes) -> bytes:
        """Pure byte-frame handler; no stdout/pipe/socket opened here."""
        if not isinstance(encoded, bytes) or not 0 < len(encoded) <= MAX_INPUT:
            raise ProtocolHold("NATIVE_FRAME_TOO_LARGE_OR_EMPTY")
        try:
            decoded = encoded.decode("utf-8")
            _enforce_json_depth(decoded)
            request = json.loads(
                decoded,
                parse_constant=_reject_nonfinite,
                parse_float=_finite_json_number,
                object_pairs_hook=_reject_duplicate_fields)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ProtocolHold("NATIVE_FRAME_INVALID_JSON") from exc
        if not isinstance(request, dict) or set(request) != {
                "protocol", "requestId", "route", "payload", "runId"}:
            raise ProtocolHold("NATIVE_ENVELOPE_FIELDS_INVALID")
        if request["protocol"] != "NOX-P02-NATIVE-v1" or request["runId"] != self.run_id:
            raise ProtocolHold("NATIVE_PROTOCOL_OR_RUN_MISMATCH")
        nonce, route, payload = request["requestId"], request["route"], request["payload"]
        if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
            raise ProtocolHold("NATIVE_NONCE_INVALID")
        if not isinstance(route, str) or not isinstance(payload, dict):
            raise ProtocolHold("NATIVE_ROUTE_OR_PAYLOAD_INVALID")
        if route not in P02_ROUTES:
            # ModelCenter read routes need BOTH a host-side opt-in and the
            # existing PACK01 owner's concrete, receipt-bound P03 port.
            # No page data can opt in; no downloads, imports or retries here.
            if not self._modelcenter_reads or route not in P03_NATIVE_READ_ROUTES:
                raise ProtocolHold("NATIVE_ROUTE_OR_PAYLOAD_INVALID")
            routes = getattr(self._dispatch, "routes", None)
            ports = getattr(self._dispatch, "ports", None)
            route_info = routes.get(route) if isinstance(routes, Mapping) else None
            port = ports.get(route) if isinstance(ports, dict) else None
            if (not isinstance(route_info, Mapping)
                    or type(route_info.get("owner")) is not int
                    or route_info["owner"] != 3
                    or getattr(port, "owner", None) != 3
                    or not isinstance(getattr(port, "evidence_id", None), str)
                    or not port.evidence_id.strip()
                    or not callable(getattr(port, "call", None))
                    or not callable(getattr(port, "available", None))):
                raise ProtocolHold("NATIVE_MODEL_CENTER_OWNER_NOT_BOUND")
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
