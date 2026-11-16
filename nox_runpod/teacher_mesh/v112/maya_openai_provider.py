"""Maya stdio-backed OpenAI provider for the existing NOX V112 callback slot.

This module does not start an HTTP listener or select a fallback model.  The
caller injects ``serve.server`` from Maya commit
``c81fab6c9d63cf69b928f92460e0a662b28aa9ec`` and a factory that constructs
its ``Service`` (whose ``StrataEngine`` owns the persistent ``maya-ds4
--serve`` stdio child).  Admission is disabled by default and must be freshly
proven before the factory can spawn that child.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import shlex
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from starlette.responses import StreamingResponse


REQUIRED_ADMISSION = (
    "owner_lease_verified",
    "stop_clear",
    "binary_sha_verified",
    "sm70_verified",
    "model_sha_verified",
    "storage_ready",
    "resource_fit",
    "persistent_stdio_verified",
)
MODEL_ID = "DeepSeek-V4.1-Flash-1017"
MAYA_EXECUTABLE = "maya-ds4"
MAYA_SOURCE_COMMIT = "c81fab6c9d63cf69b928f92460e0a662b28aa9ec"
ADMISSION_MAX_AGE_S = 10.0
_END = object()
_QUEUE_CAPACITY = 8


class MayaAdmissionHold(RuntimeError):
    pass


def admission_ok(snapshot: object, enabled: bool, now: float | None = None) -> bool:
    """Fail closed unless explicit opt-in and a fresh complete admission proof is present."""
    if not enabled or not isinstance(snapshot, Mapping):
        return False
    observed = snapshot.get("observed_at_unix")
    if isinstance(observed, bool) or not isinstance(observed, (int, float)):
        return False
    age = (time.time() if now is None else float(now)) - float(observed)
    if (not -1.0 <= age <= ADMISSION_MAX_AGE_S
            or snapshot.get("model_id") != MODEL_ID
            or snapshot.get("maya_source_commit") != MAYA_SOURCE_COMMIT):
        return False
    if any(not isinstance(snapshot.get(name), str)
           or re.fullmatch(r"[0-9a-f]{64}", snapshot[name]) is None
           for name in ("binary_sha256", "model_sha256")):
        return False
    return all(
        snapshot.get(name) is True for name in REQUIRED_ADMISSION
    )


def _service_contract_ok(service: Any) -> bool:
    """Require the pinned DeepSeek service and one live Maya stdio engine."""
    engine = getattr(service, "engine", None)
    if (getattr(service, "model", None) != MODEL_ID
            or getattr(getattr(service, "template", None), "deepseek", False) is not True
            or type(engine).__name__ != "StrataEngine"
            or not callable(getattr(engine, "generate", None))):
        return False
    proc = getattr(engine, "proc", None)
    poll = getattr(proc, "poll", None)
    if not callable(poll):
        return False
    argv = getattr(proc, "args", None)
    if isinstance(argv, str):
        try:
            argv = shlex.split(argv)
        except ValueError:
            return False
    if not isinstance(argv, (tuple, list)) or len(argv) < 2:
        return False
    try:
        executable = os.path.basename(os.fspath(argv[0]))
    except TypeError:
        return False
    return executable == MAYA_EXECUTABLE and str(argv[1]) == "--serve" and poll() is None


def _sse_error(code: str) -> bytes:
    obj = {"error": {"type": "server_error", "message": code}}
    return b"data: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n\n"


class MayaV112Proxy:
    """An async ``_proxy_completion(payload)`` callback for the existing V112 app.

    ``maya_server`` must be the source-pinned ``serve.server`` module.  It is
    used as a library only: this code never calls ``main()``, ``serve()`` or
    creates a network listener.  ``service_factory`` must return its
    ``Service`` backed by a single resident ``StrataEngine`` stdio process.
    """

    def __init__(self, *, maya_server: Any, service_factory: Callable[[], Any],
                 admission: Callable[[], Mapping[str, object]], enabled: bool = False,
                 worker_join_s: float = 2.0):
        self.maya_server = maya_server
        self.service_factory = service_factory
        self.admission = admission
        self.enabled = enabled
        self.worker_join_s = max(0.1, float(worker_join_s))
        self._service = None
        self._service_lock = threading.Lock()

    def _snapshot_ok(self) -> bool:
        try:
            return admission_ok(self.admission(), self.enabled)
        except Exception:
            return False

    def _get_service(self):
        if not self._snapshot_ok():
            raise MayaAdmissionHold("HOLD_MAYA_ADMISSION")
        with self._service_lock:
            if self._service is None:
                # Recheck under the lock immediately before service_factory can
                # construct StrataEngine and spawn the resident stdio process.
                if not self._snapshot_ok():
                    raise MayaAdmissionHold("HOLD_MAYA_ADMISSION")
                service = self.service_factory()
                if not _service_contract_ok(service):
                    raise MayaAdmissionHold("HOLD_MAYA_ENGINE_UNAVAILABLE")
                self._service = service
            elif not _service_contract_ok(self._service):
                raise MayaAdmissionHold("HOLD_MAYA_ENGINE_UNAVAILABLE")
            return self._service

    @staticmethod
    def _request(payload: object, service: Any) -> dict:
        if not isinstance(payload, dict):
            raise MayaAdmissionHold("HOLD_MAYA_REQUEST_INVALID")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise MayaAdmissionHold("HOLD_MAYA_MESSAGES_INVALID")

        # Keep the existing NOX callback contract small and explicit.  Ignore
        # owner/session fields rather than forwarding them as provider options.
        req = {"messages": messages, "stream": True, "model": str(service.model)}
        for key in (
            "tools", "tool_choice", "max_tokens", "max_completion_tokens",
            "temperature", "top_p", "top_k", "seed", "stop",
            "presence_penalty", "frequency_penalty", "repetition_penalty",
            "reasoning_effort", "response_format",
        ):
            if key in payload:
                req[key] = payload[key]
        return req

    def _prepare(self, service: Any, req: dict, cancel: threading.Event):
        if callable(getattr(service, "with_shared", None)):
            req = service.with_shared(req, "openai")
        service.check_request(req)
        deepseek = bool(getattr(service.template, "deepseek", False))
        glm_dsa = bool(getattr(service.template, "glm_dsa", False))
        messages, tools, kwargs = self.maya_server.openai_to_messages(
            req, deepseek=deepseek, glm_dsa=glm_dsa
        )
        max_new = int(req.get("max_completion_tokens") or req.get("max_tokens") or 0)
        guard = service._loop_guard_on(req) if callable(getattr(service, "_loop_guard_on", None)) else None
        ids, thinking, max_new = service.prepare(
            messages, tools, kwargs, max_new, cancel=cancel, guard=guard
        )
        if kwargs.get("_prefill"):
            req["_prefill"] = kwargs["_prefill"]
        for key in ("_blocked", "_think_resume", "_think_max"):
            if key in kwargs:
                req[key] = kwargs[key]
        return req, messages, tools, ids, thinking, max_new

    async def __call__(self, payload: dict):
        """Return the SSE ``StreamingResponse`` expected by V112's existing callback."""
        try:
            if not self._snapshot_ok():
                raise MayaAdmissionHold("HOLD_MAYA_ADMISSION")
            service = await asyncio.to_thread(self._get_service)
            cancel = threading.Event()
            req = self._request(payload, service)
            prepared = await asyncio.to_thread(self._prepare, service, req, cancel)
            if not self._snapshot_ok():
                raise MayaAdmissionHold("HOLD_MAYA_ADMISSION")
            req, messages, tools, ids, thinking, max_new = prepared
            chunks = self.maya_server.openai_chunks(
                service, req, ids, thinking, tools, max_new, cancel
            )
            return StreamingResponse(
                self._body(chunks, cancel), media_type="text/event-stream"
            )
        except MayaAdmissionHold as exc:
            return StreamingResponse(
                self._one_error(str(exc)), media_type="text/event-stream", status_code=200
            )
        except Exception:
            # Do not leak filesystem paths, subprocess stderr, or credentials.
            return StreamingResponse(
                self._one_error("HOLD_MAYA_PROVIDER_SETUP"),
                media_type="text/event-stream", status_code=200,
            )

    async def _one_error(self, code: str):
        yield _sse_error(code)
        yield b"data: [DONE]\n\n"

    async def _body(self, chunks, cancel: threading.Event):
        """Run Maya's synchronous token iterator off-loop; cancellation reaches its Engine Event."""
        out: queue.Queue = queue.Queue(maxsize=_QUEUE_CAPACITY)
        state = {"complete": False, "error": None}

        def put(item: object) -> bool:
            while not cancel.is_set():
                try:
                    out.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def produce():
            try:
                for chunk in chunks:
                    if cancel.is_set():
                        break
                    if not put(chunk):
                        break
                else:
                    state["complete"] = True
            except Exception:
                state["error"] = "HOLD_MAYA_GENERATION"
            finally:
                close = getattr(chunks, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
                if state["complete"] and not cancel.is_set():
                    put(_END)

        worker = threading.Thread(target=produce, daemon=True, name="nox-maya-stdio-provider")
        worker.start()
        finished = False
        try:
            while True:
                try:
                    item = await asyncio.to_thread(out.get, True, 0.2)
                except queue.Empty:
                    if not worker.is_alive():
                        break
                    continue
                if item is _END:
                    finished = True
                    break
                if item is None:
                    yield b": keep-alive\n\n"
                else:
                    # Recheck immediately before exposing a chunk, not merely
                    # when the model process was first admitted.
                    if not self._snapshot_ok():
                        state["error"] = "HOLD_MAYA_ADMISSION"
                        cancel.set()
                        break
                    yield b"data: " + json.dumps(item, ensure_ascii=False).encode("utf-8") + b"\n\n"
            if state["error"]:
                yield _sse_error(state["error"])
                yield b"data: [DONE]\n\n"
            elif finished and self._snapshot_ok():
                yield b"data: [DONE]\n\n"
            elif not cancel.is_set():
                yield _sse_error("HOLD_MAYA_ADMISSION")
                yield b"data: [DONE]\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            # Closing V112's body_iterator on scoped STOP/disconnect sets this
            # event; official StrataEngine.generate sends STOP and drains DONE.
            cancel.set()
            await asyncio.to_thread(worker.join, self.worker_join_s)


def bind_existing_proxy(trusted: dict, provider: MayaV112Proxy) -> None:
    """Replace only V112's existing provider slot; never keep an old-model fallback."""
    if not isinstance(trusted, dict) or not callable(trusted.get("_proxy_completion")):
        raise MayaAdmissionHold("HOLD_NATIVE_OWNER_CALLBACK__proxy_completion")
    if trusted.get("_maya_v112_provider_bound") is True:
        raise MayaAdmissionHold("HOLD_MAYA_PROVIDER_ALREADY_BOUND")
    trusted["_proxy_completion"] = provider
    trusted["_maya_v112_provider_bound"] = True
