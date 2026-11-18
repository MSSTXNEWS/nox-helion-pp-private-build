"""Original 1A03: reconnect rejection must not create or recover model work.

Runs against the existing bridge and ledger on temporary SQLite and in-process
ASGI. The proxy is a bounded fixture; no native model or remote service is used.
These tests are immutable input to the NOX source-generation contract.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

import native_v29_full_bridge as bridge
from owner_chat_request_ledger import RequestLedger


DIALOG = "a" * 32
QUESTION = "Проверка восстановления"
ANSWER = "Ответ 🌌 — mañana!"


class CursorAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "original-s03.sqlite"
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TABLE s03_items(id TEXT PRIMARY KEY, sha256 TEXT, ts REAL, text TEXT)")
        self.s03 = patch.dict(sys.modules, s03_memory=types.SimpleNamespace(DB=self.db_path))
        self.s03.start()
        self.addCleanup(self.s03.stop)
        self.assertTrue(bridge.ensure_dialog_schema())
        with bridge._db(True) as db:
            db.execute("INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)",
                       (DIALOG, bridge.OWNER, "test", 0, 1, bridge._now(), bridge._now()))
        self.calls = 0
        self.app = FastAPI()

        async def proxy(payload):
            self.calls += 1
            call_id = self.calls
            question = payload["messages"][-1]["content"]

            async def stream():
                frame = {"choices": [{"delta": {"content": ANSWER}}]}
                yield ("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n").encode()
                with bridge._db(True) as db:
                    db.execute("INSERT INTO s03_items VALUES(?,?,?,?)",
                               ("native-fixture-" + str(call_id), "b" * 64,
                                time.time(), question + " " + ANSWER))
                yield b"data: [DONE]\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")

        async def status():
            return {"primary_model": "local-test-fixture"}

        trusted = {"_session_ok": lambda request: request.cookies.get("owner") == "test",
                   "_unauthorized": lambda: JSONResponse({"error": "unauthorized"}, status_code=401),
                   "_proxy_completion": proxy, "nox_status": status}
        bridge.register_native_v29_chat(self.app, trusted, site_dir=self.temp.name)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                      base_url="http://fixture", cookies={"owner": "test"})
        self.addAsyncCleanup(self.client.aclose)
        self.body = {"request_id": "cursor-request", "dialog_id": DIALOG, "message": QUESTION}

    def rows(self):
        with bridge._db() as db:
            return {
                "requests": [dict(row) for row in db.execute("SELECT * FROM nox_chat_requests ORDER BY request_id")],
                "events": [dict(row) for row in db.execute("SELECT * FROM nox_chat_events ORDER BY request_id,event_id")],
                "messages": [dict(row) for row in db.execute("SELECT * FROM nox_v29_dialog_messages ORDER BY row_id")],
            }

    @staticmethod
    def frames(response):
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]

    def dead_request(self):
        scope = hashlib.sha256(json.dumps([["owner", "test"]], separators=(",", ":")).encode()).hexdigest()
        ledger = RequestLedger(bridge._db, bridge.OWNER)
        ledger.accept(self.body["request_id"], QUESTION, DIALOG,
                      {"message": QUESTION, "dialog_id": DIALOG, "history": []}, scope)
        with bridge._db(True) as db:
            db.execute("UPDATE nox_chat_requests SET producer_pid=2147483647")

    async def test_new_positive_cursor_rejected_without_request_or_model(self):
        for cursor in (1, 999, 2**63 - 1):
            with self.subTest(cursor=cursor):
                body = {**self.body, "request_id": "fresh-" + str(cursor), "after_event_id": cursor}
                response = await self.client.post("/api/nox/chat/stream", json=body)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"], "EVENT_CURSOR_AHEAD")
                self.assertEqual(self.calls, 0, "rejected reconnect must not invoke inference")
                self.assertEqual(self.rows(), {"requests": [], "events": [], "messages": []})

    async def test_bad_cursor_syntax_rejected_before_any_write(self):
        for cursor in (-1, True, "1", 2**63, 10**90):
            response = await self.client.post("/api/nox/chat/stream",
                                              json={**self.body, "after_event_id": cursor})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"], "INVALID_EVENT_CURSOR")
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.rows(), {"requests": [], "events": [], "messages": []})

    async def test_dead_producer_ahead_cursor_does_not_recover_or_mutate(self):
        self.dead_request()
        before = self.rows()
        response = await self.client.post("/api/nox/chat/stream",
                                          json={**self.body, "after_event_id": 999})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "EVENT_CURSOR_AHEAD")
        self.assertEqual(self.rows(), before, "rejected replay must not append recovery events")
        self.assertEqual(self.calls, 0)

    async def test_valid_dead_producer_replay_still_recovers_once(self):
        self.dead_request()
        response = await self.client.post("/api/nox/chat/stream", json=self.body)
        self.assertEqual(response.status_code, 200)
        frames = self.frames(response)
        self.assertEqual(frames[-1]["error"], "STREAM_INTERRUPTED_RESTART")
        self.assertEqual(self.calls, 0)
        before = self.rows()
        again = await self.client.post("/api/nox/chat/stream", json=self.body)
        self.assertEqual(self.frames(again), frames)
        self.assertEqual(self.rows(), before)

    async def test_zero_cursor_completes_and_exact_retry_runs_once(self):
        first = await self.client.post("/api/nox/chat/stream", json=self.body)
        self.assertEqual(first.status_code, 200)
        frames = self.frames(first)
        self.assertEqual(frames[-1]["type"], "done")
        self.assertEqual("".join(x.get("text", "") for x in frames), ANSWER)
        second = await self.client.post("/api/nox/chat/stream", json=self.body)
        self.assertEqual(self.frames(second), frames)
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.rows()["messages"]), 2)

    async def test_valid_existing_cursor_replays_only_later_events(self):
        first = self.frames(await self.client.post("/api/nox/chat/stream", json=self.body))
        response = await self.client.post("/api/nox/chat/stream",
                                          json={**self.body, "after_event_id": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.frames(response), [x for x in first if x["event_id"] > 2])
        self.assertEqual(self.calls, 1)

    async def test_existing_ahead_cursor_is_side_effect_free(self):
        await self.client.post("/api/nox/chat/stream", json=self.body)
        before = self.rows()
        response = await self.client.post("/api/nox/chat/stream",
                                          json={**self.body, "after_event_id": 999})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.calls, 1)

    async def test_conflicting_payload_and_unauthorized_retry_stay_fenced(self):
        await self.client.post("/api/nox/chat/stream", json=self.body)
        before = self.rows()
        response = await self.client.post("/api/nox/chat/stream",
                                          json={**self.body, "message": "Different"})
        self.assertEqual(response.status_code, 409)
        self.client.cookies.clear()
        unauthorized = await self.client.post("/api/nox/chat/stream", json=self.body)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
