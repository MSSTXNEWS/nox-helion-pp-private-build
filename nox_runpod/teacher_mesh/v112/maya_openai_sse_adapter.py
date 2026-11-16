"""Maya OpenAI SSE provider for the existing V112 owner chat bridge.

This is a completion callback, not a second HTTP service. The caller injects it
as V112's required trusted["_proxy_completion"] callback. It streams the
configured Maya API response and delegates durable S03 persistence to NOX's
existing pair writer; V112 then performs its normal S03 readback and dialog
commit. Importing this module never starts Maya or writes S03.
"""
from __future__ import annotations

import asyncio
import codecs
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

import httpx
from fastapi.responses import StreamingResponse

from .native_v29_full_bridge import _sse_delta


class MayaOpenAICompletion:
    """Call Maya's existing OpenAI-compatible API from V112's provider hook.

    base_url is the already-running Maya API root (for example
    http://127.0.0.1:8080). persist_pair must be the trusted NOX S03 writer
    with the legacy (question, answer) signature. No credentials or endpoint
    are accepted from the chat request.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        persist_pair: Callable[[str, str], object],
        api_key: str | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("HOLD_MAYA_BASE_URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("HOLD_MAYA_BASE_URL")
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ValueError("HOLD_MAYA_MODEL")
        if not callable(persist_pair):
            raise ValueError("HOLD_NATIVE_S03_PAIR_WRITER")
        if api_key is not None and (not isinstance(api_key, str) or not api_key):
            raise ValueError("HOLD_MAYA_API_KEY")
        self.endpoint = base_url.rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.persist_pair = persist_pair
        self.api_key = api_key
        self.client_factory = client_factory

    async def __call__(self, payload: Mapping[str, object]) -> StreamingResponse:
        if not isinstance(payload, Mapping) or payload.get("_owner") is not True:
            raise RuntimeError("HOLD_NATIVE_OWNER_PROVIDER_SCOPE")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("HOLD_NATIVE_MESSAGES")
        last = messages[-1]
        if not isinstance(last, dict) or last.get("role") != "user":
            raise RuntimeError("HOLD_NATIVE_USER_TURN")
        question = last.get("content")
        if not isinstance(question, str) or not question.strip():
            raise RuntimeError("HOLD_NATIVE_USER_TURN")

        # Forward only the bridge's trusted conversation and fixed server-side
        # model choice. Never forward client model hints or the owner marker.
        request_body = {
            "model": self.model,
            "messages": [dict(row) for row in messages],
            "stream": True,
        }
        headers = {"Accept": "text/event-stream"}
        if self.api_key is not None:
            headers["Authorization"] = "Bearer " + self.api_key

        async def body():
            answer: list[str] = []
            text_buffer = ""
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            saw_done = False
            timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
            async with self.client_factory(timeout=timeout) as client:
                async with client.stream(
                    "POST", self.endpoint, json=request_body, headers=headers
                ) as response:
                    if response.status_code != 200:
                        raise RuntimeError("HOLD_MAYA_HTTP_" + str(response.status_code))
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/event-stream" not in content_type:
                        raise RuntimeError("HOLD_MAYA_SSE_CONTENT_TYPE")
                    async for raw in response.aiter_raw():
                        text_buffer += decoder.decode(raw)
                        rows = text_buffer.split("\n")
                        text_buffer = rows.pop()
                        if len(text_buffer) > 300_000 or any(len(row) > 300_000 for row in rows):
                            raise RuntimeError("HOLD_MAYA_SSE_FRAME_LIMIT")
                        for row in rows:
                            frame = row.strip()
                            if not frame or not frame.startswith("data:"):
                                continue
                            if saw_done:
                                raise RuntimeError("HOLD_MAYA_SSE_AFTER_DONE")
                            kind, part = _sse_delta(frame)
                            if kind in ("malformed", "upstream_error", "upstream_finish_incomplete"):
                                raise RuntimeError("HOLD_MAYA_SSE_" + kind.upper())
                            if kind == "done":
                                saw_done = True
                            elif kind == "delta":
                                answer.append(part)
                        yield raw
                    text_buffer += decoder.decode(b"", final=True)
                    if text_buffer.strip():
                        raise RuntimeError("HOLD_MAYA_SSE_UNTERMINATED_FRAME")
                    if not saw_done or not "".join(answer).strip():
                        raise RuntimeError("HOLD_MAYA_SSE_INCOMPLETE")
            complete_answer = "".join(answer)
            result = await asyncio.to_thread(self.persist_pair, question, complete_answer)
            if asyncio.iscoroutine(result):
                await result

        return StreamingResponse(body(), media_type="text/event-stream")
