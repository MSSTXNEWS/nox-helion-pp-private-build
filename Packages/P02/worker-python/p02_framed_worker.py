"""NOX E02: bounded binary frame pump for the already-existing Python host.

Owner #6 owns the authentic Windows SID/session, original backend process and
WPF/WebView2 transport. This module is ONLY an in-process stdio/pipe adapter to
an injected P02 NativeIngress. It never launches a process, accepts network
connections, constructs a session, creates a database or bypasses native consent.

Frames: unsigned 32-bit big-endian byte count followed by a UTF-8 P02 native
JSON envelope. Responses use the same framing and carry exact requestId. A
valid chat.stop bypasses the non-STOP worker to preserve cancellation liveness.
"""
from __future__ import annotations

import json
import re
import struct
import threading
from typing import BinaryIO

from p02_native_ingress import MAX_INPUT, MAX_OUTPUT, NativeIngress, ProtocolHold, _enforce_json_depth, _reject_duplicate_fields

_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_HEADER = struct.Struct(">I")
_MAX_FAIL = 1024


def _read_exact(reader: BinaryIO, n: int) -> bytes:
    data = bytearray()
    while len(data) < n:
        block = reader.read(n - len(data))
        if not isinstance(block, bytes) or not block:
            raise ProtocolHold("NATIVE_TRUNCATED_FRAME")
        data.extend(block)
    return bytes(data)


def _encode_status(ingress: NativeIngress, nonce: str | None, code: str) -> bytes:
    payload = {"protocol": "NOX-P02-NATIVE-v1", "runId": ingress.run_id,
               "requestId": nonce, "status": "HOLD", "errorCode": code}
    result = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if len(result) > _MAX_FAIL:
        raise ProtocolHold("NATIVE_ERROR_REPLY_TOO_LARGE")
    return result


def serve_native_frames(ingress: NativeIngress, reader: BinaryIO,
                        writer: BinaryIO, *, drain_timeout: float = 5.0) -> int:
    """Serve frames on the *existing* host transport. No standalone server.

    Only one non-STOP request may execute at a time. The reader always remains
    responsive to STOP. Output frames are atomic; an earlier request may finish
    after STOP, so consumers must match requestId, not assume reply order.
    The caller owns process lifetime; no long-lived thread is spawned here.
    """
    if not isinstance(ingress, NativeIngress):
        raise TypeError("An already authenticated P02 NativeIngress is required")
    if not (hasattr(reader, "read") and hasattr(writer, "write") and
            hasattr(writer, "flush")):
        raise TypeError("Existing binary host pipe handles required")
    if type(drain_timeout) not in (int, float) or not 0 < drain_timeout <= 30:
        raise ValueError("Invalid transport shutdown budget")

    write_lock = threading.Lock()
    active_lock = threading.Lock()
    active = False
    workers: list[threading.Thread] = []
    count = 0
    fatal_errors: list[Exception] = []
    output_failed = threading.Event()

    def require_output_transport() -> None:
        if output_failed.is_set():
            raise ProtocolHold("NATIVE_OUTPUT_TRANSPORT_FAILED")

    def send(payload: bytes) -> None:
        try:
            if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_OUTPUT:
                raise ProtocolHold("NATIVE_FRAME_OUTPUT_INVALID")
            with write_lock:
                require_output_transport()
                # Raw host pipes may accept only part of a write. Keep the entire
                # frame under one lock and require progress before acknowledging it.
                for part in (_HEADER.pack(len(payload)), payload):
                    view = memoryview(part)
                    while view:
                        written = writer.write(view)
                        if type(written) is not int or not 0 < written <= len(view):
                            raise ProtocolHold("NATIVE_OUTPUT_TRANSPORT_FAILED")
                        view = view[written:]
                writer.flush()
        except Exception as exc:
            # A partial frame/failed flush has unknown delivery. Never append a
            # new reply or admit another native operation on that same stream.
            output_failed.set()
            if isinstance(exc, ProtocolHold):
                raise
            raise ProtocolHold("NATIVE_OUTPUT_TRANSPORT_FAILED") from exc

    def dispatch(data: bytes, nonce: str | None) -> None:
        nonlocal active
        try:
            try:
                require_output_transport()
                result = ingress.handle(data)
            except ProtocolHold as exc:
                # Only fixed, documented error codes are returned. No raw data,
                # file paths, model prompts, or exception traces leave the host.
                code = str(exc)
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", code):
                    code = "NATIVE_PROVIDER_HOLD"
                result = _encode_status(ingress, nonce, code)
            except Exception:
                result = _encode_status(ingress, nonce, "NATIVE_PROVIDER_HOLD")
            send(result)
        except Exception as exc:
            fatal_errors.append(exc)
        finally:
            with active_lock:
                active = False

    try:
        while True:
            require_output_transport()
            header = reader.read(1)
            if header == b"":
                break
            if not isinstance(header, bytes) or len(header) != 1:
                raise ProtocolHold("NATIVE_TRUNCATED_HEADER")
            header += _read_exact(reader, 3)
            if count >= 8192:
                raise ProtocolHold("NATIVE_SESSION_FRAME_WINDOW_EXHAUSTED")
            size = _HEADER.unpack(header)[0]
            if not 0 < size <= MAX_INPUT:
                raise ProtocolHold("NATIVE_FRAME_SIZE_INVALID")
            data = _read_exact(reader, size)
            # A worker can lose its reply while this reader is blocked. Check
            # again after input arrives, before parsing/admitting more work.
            require_output_transport()
            count += 1
            nonce = None
            route = None
            try:
                decoded = data.decode("utf-8")
                # Reuse the existing NativeIngress depth limit at the OUTER
                # parser, before Python's platform-dependent json recursion.
                _enforce_json_depth(decoded)
                request = json.loads(decoded, object_pairs_hook=_reject_duplicate_fields)
                if isinstance(request, dict):
                    candidate = request.get("requestId")
                    nonce = candidate if isinstance(candidate, str) and _NONCE.fullmatch(candidate) else None
                    route = request.get("route")
            except (ValueError, UnicodeError, RecursionError):
                # Invalid frames must not kill the native pipe, occupy the
                # one non-STOP worker, or hide the following valid request.
                send(_encode_status(ingress, nonce, "NATIVE_FRAME_INVALID_JSON"))
                continue
            # Let NativeIngress validate even malformed STOP envelopes; it
            # independently verifies run ID, nonce, capabilities and session.
            if route == "chat.stop":
                try:
                    send(ingress.handle(data))
                except ProtocolHold as exc:
                    code = str(exc)
                    send(_encode_status(ingress, nonce, code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", code) else "NATIVE_PROVIDER_HOLD"))
                continue
            with active_lock:
                require_output_transport()
                if active:
                    busy = True
                else:
                    active = True
                    busy = False
            if busy:
                send(_encode_status(ingress, nonce, "NATIVE_BUSY"))
            else:
                t = threading.Thread(target=dispatch, args=(data, nonce), daemon=True)
                workers = [old for old in workers if old.is_alive()]
                workers.append(t)
                t.start()
    finally:
        for worker in workers:
            worker.join(timeout=drain_timeout)
        if any(worker.is_alive() for worker in workers):
            raise ProtocolHold("NATIVE_WORKER_NOT_DRAINED")
        if fatal_errors:
            raise ProtocolHold("NATIVE_OUTPUT_TRANSPORT_FAILED") from fatal_errors[0]
    return count
