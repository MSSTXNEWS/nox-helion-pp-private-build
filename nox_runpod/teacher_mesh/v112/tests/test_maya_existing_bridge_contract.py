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


if __name__ == "__main__":
    unittest.main()
