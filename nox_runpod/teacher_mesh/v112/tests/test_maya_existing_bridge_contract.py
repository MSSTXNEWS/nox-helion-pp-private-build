"""Contract tests for a Maya OpenAI-compatible SSE producer behind the existing V112 bridge.

These are source fixtures only: no Maya binary, OneHost, model or production S03 is
started. They validate the trusted _proxy_completion boundary, RU/ES UTF-8,
native STOP semantics and dialog history/readback.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import queue
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
    ensure_dialog_schema,
    register_native_v29_chat,
)


class MayaExistingBridgeContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.db = self.folder / "existing_s03.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "CREATE TABLE s03_items (id TEXT PRIMARY KEY, sha256 TEXT, text TEXT, ts TEXT)"
            )
        module = types.ModuleType("s03_memory")
        module.DB = self.db
        self.previous_memory = sys.modules.get("s03_memory")
        sys.modules["s03_memory"] = module
        self.addCleanup(self._restore_memory)

        self.calls = []
        self.stop_mode = False
        self.stop_waiting = threading.Event()
        self.delta_received = threading.Event()
        self.receipt_counter = 0
        self.app = FastAPI()

        @self.app.get("/api/nox/status")
        async def old_status():
            return {"model": "existing configured engine", "ts": 123}

        async def maya_openai_completion(payload):
            # The existing bridge owns auth, dialog scope and history. Its trusted
            # callback is the sole integration point for the configured model API.
            self.calls.append(payload.copy())
            question = payload["messages"][-1]["content"]
            if "¿" in question or "Español" in question:
                answer = "Respuesta verificada desde la conversación."
            else:
                answer = "Проверенный ответ из истории."

            async def chunks():
                midpoint = max(1, len(answer) // 2)
                first = {
                    "choices": [{"index": 0, "delta": {"content": answer[:midpoint]}}]
                }
                yield "data: " + json.dumps(first, ensure_ascii=False) + "\n\n"

                if self.stop_mode:
                    # The source bridge must stop before accepting terminal SSE
                    # or committing a complete dialog exchange.
                    self.delta_received.set()
                    await asyncio.to_thread(self.stop_waiting.wait, 5)

                second = {
                    "choices": [{"index": 0, "delta": {"content": answer[midpoint:]}}]
                }
                if answer[midpoint:]:
                    yield "data: " + json.dumps(second, ensure_ascii=False) + "\n\n"
                self.receipt_counter += 1
                record_id = "maya-fixture-" + str(self.receipt_counter).zfill(8)
                stamp = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(self.db) as conn:
                    conn.execute(
                        "INSERT INTO s03_items VALUES(?,?,?,?)",
                        (
                            record_id,
                            hashlib.sha256((question + answer).encode("utf-8")).hexdigest(),
                            "U:" + question + " A:" + answer,
                            stamp,
                        ),
                    )
                yield "data: [DONE]\n\n"

            return StreamingResponse(chunks(), media_type="text/event-stream")

        register_native_v29_chat(
            self.app,
            {
                "_session_ok": lambda request: request.cookies.get("owner") == "yes",
                "_unauthorized": lambda: JSONResponse({"error": "AUTH"}, status_code=401),
                "_proxy_completion": maya_openai_completion,
                "nox_status": old_status,
            },
            site_dir=self.folder,
        )
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.cookies = {"owner": "yes"}
        self.assertTrue(ensure_dialog_schema())

    def _restore_memory(self):
        if self.previous_memory is None:
            sys.modules.pop("s03_memory", None)
        else:
            sys.modules["s03_memory"] = self.previous_memory

    def _new_dialog(self, title):
        response = self.client.post(
            "/api/ui/memory/dialogs/create",
            cookies=self.cookies,
            json={"title": title, "confirmed": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["dialog_id"]

    def _stream(self, question, dialog_id, extra=None):
        body = {"message": question, "dialog_id": dialog_id, "history": []}
        if extra:
            body.update(extra)
        response = self.client.post(
            "/api/nox/chat/stream", cookies=self.cookies, json=body
        )
        self.assertEqual(response.status_code, 200, response.text[:500])
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def test_maya_sse_ru_es_turns_use_server_owned_s03_history(self):
        dialog_id = self._new_dialog("RU ES Maya bridge contract")

        ru = self._stream("Привет, сохрани контекст.", dialog_id)
        self.assertEqual(ru[0]["type"], "preparing")
        self.assertEqual(ru[1]["type"], "start")
        self.assertEqual(ru[-1]["type"], "done")
        self.assertTrue(ru[-1]["saved"])
        self.assertTrue(ru[-1]["s03_integrated"])
        self.assertEqual(ru[-1]["dialog_id"], dialog_id)
        self.assertEqual(
            "".join(frame["text"] for frame in ru if frame["type"] == "delta"),
            "Проверенный ответ из истории.",
        )

        # The browser supplies conflicting history/model hints. Persisted owner
        # dialog history remains authoritative; no client model selector is forwarded.
        es = self._stream(
            "¿Cómo continúa la conversación? Español, por favor.",
            dialog_id,
            {
                "history": [{"role": "assistant", "content": "UNTRUSTED HISTORY"}],
                "model": "client-selected-model-must-be-ignored",
            },
        )
        self.assertEqual(es[-1]["type"], "done")
        self.assertTrue(es[-1]["saved"])
        self.assertTrue(es[-1]["s03_integrated"])
        self.assertEqual(
            "".join(frame["text"] for frame in es if frame["type"] == "delta"),
            "Respuesta verificada desde la conversación.",
        )

        self.assertEqual(len(self.calls), 2)
        second_messages = self.calls[1]["messages"]
        self.assertEqual(
            [(row["role"], row["content"]) for row in second_messages],
            [
                ("user", "Привет, сохрани контекст."),
                ("assistant", "Проверенный ответ из истории."),
                ("user", "¿Cómo continúa la conversación? Español, por favor."),
            ],
        )
        self.assertTrue(all(call["_owner"] is True and call["stream"] is True for call in self.calls))
        self.assertNotIn("model", self.calls[1])

        history = self.client.get(
            "/api/ui/memory/dialogs/history",
            cookies=self.cookies,
            params={"dialog_id": dialog_id},
        )
        self.assertEqual(history.status_code, 200, history.text)
        messages = history.json()["messages"]
        self.assertEqual([row["role"] for row in messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual(messages[-2]["content"], "¿Cómo continúa la conversación? Español, por favor.")
        self.assertEqual(messages[-1]["content"], "Respuesta verificada desde la conversación.")

    def test_stop_cancels_existing_bridge_stream_without_false_done(self):
        dialog_id = self._new_dialog("STOP keeps incomplete Maya turn out of dialog history")
        stream_frames = queue.Queue()
        self.stop_mode = True
        self.delta_received.clear()
        self.stop_waiting.clear()

        def consume_stream():
            with self.client.stream(
                "POST",
                "/api/nox/chat/stream",
                cookies=self.cookies,
                json={"message": "Продолжи только если STOP не пришёл.", "dialog_id": dialog_id},
            ) as response:
                for line in response.iter_lines():
                    if line:
                        frame = json.loads(line)
                        stream_frames.put(frame)
                        if frame.get("type") == "delta":
                            self.delta_received.set()

        worker = threading.Thread(target=consume_stream, daemon=True)
        worker.start()
        self.assertTrue(self.delta_received.wait(3), "Maya-compatible fixture emitted no first delta")

        stopper = TestClient(self.app)
        try:
            stopped = stopper.post("/api/nox/stop", cookies=self.cookies, json={})
        finally:
            stopper.close()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "STOP_REQUESTED")
        self.assertFalse(stopped.json()["gpu_stop_verified"])

        self.stop_waiting.set()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "stream did not terminate after STOP")
        frames = []
        while not stream_frames.empty():
            frames.append(stream_frames.get_nowait())
        self.assertTrue(any(frame.get("type") == "delta" for frame in frames))
        self.assertEqual(frames[-1], {"type": "error", "error": "STREAM_STOP_REQUESTED"})
        self.assertFalse(any(frame.get("type") == "done" or frame.get("saved") for frame in frames))

        history = self.client.get(
            "/api/ui/memory/dialogs/history",
            cookies=self.cookies,
            params={"dialog_id": dialog_id},
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["messages"], [])


class MayaOpenAIProviderBridgeTests(unittest.TestCase):
    """Use the official OpenAI SSE shape through V112 without starting Maya."""

    def setUp(self):
        import asyncio
        import hashlib
        import httpx
        import sqlite3
        import tempfile
        import threading
        import types
        from datetime import datetime, timezone
        from pathlib import Path
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        from nox_runpod.teacher_mesh.v112.maya_openai_sse_adapter import MayaOpenAICompletion
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import ensure_dialog_schema, register_native_v29_chat

        self.asyncio = asyncio
        self.httpx = httpx
        self.sqlite3 = sqlite3
        self.threading = threading
        self.datetime = datetime
        self.timezone = timezone
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "existing_s03.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE s03_items (id TEXT PRIMARY KEY, sha256 TEXT, text TEXT, ts TEXT)")
        self.previous_memory = sys.modules.get("s03_memory")
        memory = types.ModuleType("s03_memory")
        memory.DB = self.db
        sys.modules["s03_memory"] = memory
        self.addCleanup(self._restore_memory)

        self.stop_mode = False
        self.first_delta = threading.Event()
        self.release = threading.Event()
        self.stream_closed = threading.Event()
        self.requests = []
        self.s03_writer_calls = []
        self.app = FastAPI()

        class EventStream(httpx.AsyncByteStream):
            def __init__(stream_self, chunks, pause=False):
                stream_self.chunks = chunks
                stream_self.pause = pause

            async def __aiter__(stream_self):
                for index, chunk in enumerate(stream_self.chunks):
                    yield chunk
                    if stream_self.pause and index == 0:
                        self.first_delta.set()
                        await asyncio.to_thread(self.release.wait, 5)

            async def aclose(stream_self):
                self.stream_closed.set()

        self.EventStream = EventStream

        async def upstream(request):
            self.requests.append(request)
            body = __import__("json").loads(request.content)
            question = body["messages"][-1]["content"]
            answer = (
                "Respuesta confirmada desde el historial."
                if "¿" in question
                else "Проверенный ответ из истории."
            )
            frames = [
                ("data: " + __import__("json").dumps(
                    {"choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}],
                     "model": "maya-test"} , ensure_ascii=False) + "\n\n"),
                ("data: " + __import__("json").dumps(
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                     "model": "maya-test"}, ensure_ascii=False) + "\n\n"),
                "data: [DONE]\n\n",
            ]
            wire = "".join(frames).encode("utf-8")
            # Split inside a multibyte sequence when possible; the adapter must
            # preserve UTF-8 while forwarding the exact SSE bytes.
            split = next((i for i in range(1, len(wire)) if wire[i] & 0xC0 == 0x80), len(wire) // 2)
            chunks = [wire[:split], wire[split:]]
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                stream=EventStream(chunks, pause=self.stop_mode),
            )

        self.transport = httpx.MockTransport(upstream)

        def persist_pair(question, answer):
            self.s03_writer_calls.append((question, answer))
            record_id = "maya-v112-" + str(len(self.s03_writer_calls)).zfill(8)
            stamp = datetime.now(timezone.utc).isoformat()
            text = "U:" + question + "\nA:" + answer
            with sqlite3.connect(self.db) as conn:
                conn.execute(
                    "INSERT INTO s03_items VALUES(?,?,?,?)",
                    (record_id, hashlib.sha256(text.encode("utf-8")).hexdigest(), text, stamp),
                )

        def client_factory(**kwargs):
            return httpx.AsyncClient(transport=self.transport, **kwargs)

        provider = MayaOpenAICompletion(
            base_url="http://maya.internal:8080",
            model="DeepSeek-V4.1-Flash-1017",
            api_key="test-owner-token",
            persist_pair=persist_pair,
            client_factory=client_factory,
        )
        async def status():
            return {"model": "existing configured engine", "ts": 123}

        register_native_v29_chat(
            self.app,
            {
                "_session_ok": lambda request: request.cookies.get("owner") == "yes",
                "_unauthorized": lambda: JSONResponse({"error": "AUTH"}, status_code=401),
                "_proxy_completion": provider,
                "nox_status": status,
            },
            site_dir=Path(self.temp.name),
        )
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.cookies = {"owner": "yes"}
        self.assertTrue(ensure_dialog_schema())

    def _restore_memory(self):
        if self.previous_memory is None:
            sys.modules.pop("s03_memory", None)
        else:
            sys.modules["s03_memory"] = self.previous_memory

    def _new_dialog(self):
        response = self.client.post(
            "/api/ui/memory/dialogs/create",
            cookies=self.cookies,
            json={"title": "Maya provider contract", "confirmed": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["dialog_id"]

    def _turn(self, dialog_id, question, extra=None):
        body = {"message": question, "dialog_id": dialog_id, "history": []}
        if extra:
            body.update(extra)
        response = self.client.post(
            "/api/nox/chat/stream", cookies=self.cookies, json=body
        )
        self.assertEqual(response.status_code, 200, response.text[:500])
        return [__import__("json").loads(line) for line in response.text.splitlines() if line.strip()]

    def test_official_maya_openai_sse_uses_v112_s03_readback_and_owner_history(self):
        dialog_id = self._new_dialog()
        first = self._turn(dialog_id, "Привет, сохрани контекст.")
        self.assertEqual(first[-1]["type"], "done")
        self.assertTrue(first[-1]["saved"])
        self.assertEqual(first[-1]["dialog_id"], dialog_id)
        self.assertEqual(len(self.s03_writer_calls), 1)

        second = self._turn(
            dialog_id,
            "¿Cómo continúa la conversación?",
            {"model": "untrusted-client-model", "history": [{"role": "assistant", "content": "fake"}]},
        )
        self.assertEqual(second[-1]["type"], "done")
        self.assertTrue(second[-1]["s03_integrated"])
        self.assertEqual(len(self.s03_writer_calls), 2)

        first_request = __import__("json").loads(self.requests[0].content)
        second_request = __import__("json").loads(self.requests[1].content)
        self.assertEqual(self.requests[0].url, "http://maya.internal:8080/v1/chat/completions")
        self.assertEqual(self.requests[0].headers["authorization"], "Bearer test-owner-token")
        self.assertEqual(first_request["model"], "DeepSeek-V4.1-Flash-1017")
        self.assertTrue(first_request["stream"])
        self.assertNotIn("_owner", first_request)
        self.assertNotIn("untrusted-client-model", str(second_request))
        self.assertEqual(
            [(row["role"], row["content"]) for row in second_request["messages"]],
            [
                ("user", "Привет, сохрани контекст."),
                ("assistant", "Проверенный ответ из истории."),
                ("user", "¿Cómo continúa la conversación?"),
            ],
        )
        self.assertEqual(
            "".join(frame.get("text", "") for frame in second if frame.get("type") == "delta"),
            "Respuesta confirmada desde el historial.",
        )

    def test_v112_stop_closes_maya_stream_without_s03_write_or_false_done(self):
        dialog_id = self._new_dialog()
        self.stop_mode = True
        frames = queue.Queue()

        def consume():
            with self.client.stream(
                "POST",
                "/api/nox/chat/stream",
                cookies=self.cookies,
                json={"message": "Продолжай до команды остановки.", "dialog_id": dialog_id},
            ) as response:
                for line in response.iter_lines():
                    if line:
                        frames.put(__import__("json").loads(line))

        worker = threading.Thread(target=consume, daemon=True)
        worker.start()
        self.assertTrue(self.first_delta.wait(3), "Maya SSE fixture emitted no first delta")
        stopper = TestClient(self.app)
        try:
            stopped = stopper.post("/api/nox/stop", cookies=self.cookies, json={})
        finally:
            stopper.close()
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertFalse(stopped.json()["gpu_stop_verified"])
        self.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        observed = []
        while not frames.empty():
            observed.append(frames.get_nowait())
        self.assertTrue(any(item.get("type") == "delta" for item in observed))
        self.assertEqual(observed[-1], {"type": "error", "error": "STREAM_STOP_REQUESTED"})
        self.assertFalse(any(item.get("type") == "done" or item.get("saved") for item in observed))
        self.assertEqual(self.s03_writer_calls, [])
        self.assertTrue(self.stream_closed.wait(2))
        history = self.client.get(
            "/api/ui/memory/dialogs/history",
            cookies=self.cookies,
            params={"dialog_id": dialog_id},
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["messages"], [])


if __name__ == "__main__":
    unittest.main()
