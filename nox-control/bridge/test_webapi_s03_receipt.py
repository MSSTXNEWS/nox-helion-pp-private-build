#!/usr/bin/env python3
"""One focused source regression: fact receipt cannot outpace S03 persistence."""
import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nox_webapi as W


class Bridge:
    MODEL = "http://127.0.0.1:8098/v1/chat/completions"
    SOUL = None

    def __init__(self):
        self.errors = []

    def log(self, message):
        self.errors.append(message)


class Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


class FactReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fact_path = Path(self.tmp.name) / "owner_facts.jsonl"
        self.patcher = mock.patch.object(W, "FACTS", str(self.fact_path))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        bridge = Bridge()
        # Never start the infinite sampler; this checks the actual FastAPI
        # endpoint function and S03/mirror effects without a live server.
        with mock.patch.object(W.threading.Thread, "start"), mock.patch.object(W.os.path, "isdir", return_value=False):
            app = FastAPI()
            W.install(app, bridge)
        self.bridge = bridge
        self.app = app
        self.endpoint = next(r.endpoint for r in app.routes if r.path == "/api/s03/remember")

    def invoke(self, module):
        with mock.patch.dict(sys.modules, {"s03_memory": module}):
            return asyncio.run(self.endpoint(Request({"content": "Проверенный факт", "fact_key": "x"})))

    def test_failed_s03_does_not_publish_mirror_or_saved_receipt(self):
        m = types.ModuleType("s03_memory")
        def fail(*a):
            raise RuntimeError("database unavailable")
        m.persist_turn = fail
        res = self.invoke(m)
        self.assertEqual(res.status_code, 503)
        row = json.loads(res.body)
        self.assertEqual(row["status"], "HOLD")
        self.assertFalse(row["saved"])
        self.assertFalse(row["s03_readback_verified"])
        self.assertFalse(self.fact_path.exists())

    def test_successful_s03_call_remains_unverified_without_readback(self):
        m = types.ModuleType("s03_memory")
        calls = []
        m.persist_turn = lambda *a: calls.append(a)
        res = self.invoke(m)
        self.assertEqual(res["status"], "RECORDED_UNVERIFIED")
        self.assertTrue(res["saved"])
        self.assertFalse(res["s03_readback_verified"])
        self.assertEqual(len(calls), 1)
        entry = json.loads(self.fact_path.read_text(encoding="utf-8").strip())
        self.assertEqual(entry["content"], "Проверенный факт")

    def test_failed_secondary_log_is_not_an_s03_receipt(self):
        m = types.ModuleType("s03_memory")
        m.persist_turn = lambda *a: None
        with mock.patch.object(W, "FACTS", str(Path(self.tmp.name) / "missing-dir" / "facts.jsonl")):
            res = self.invoke(m)
        self.assertEqual(res.status_code, 500)
        row = json.loads(res.body)
        self.assertEqual(row["status"], "PARTIAL_HOLD")
        self.assertFalse(row["s03_readback_verified"])


    def test_partial_upstream_never_claims_done_or_persists_s03(self):
        """One endpoint-level check for complete, truncated and HTTP-failed streams."""
        class Upstream:
            def __init__(self, complete, status, finish_reason=None, error_event=False):
                self.complete, self.status_code = complete, status
                self.finish_reason, self.error_event = finish_reason, error_event

            async def __aenter__(self):
                return self

            async def __aexit__(self, *ignored):
                return False

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"частичный ответ"}}]}'
                if self.finish_reason is not None:
                    yield 'data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": self.finish_reason}]})
                if self.error_event:
                    yield 'data: {"error":{"message":"upstream worker failed"}}'
                if self.complete:
                    yield 'data: [DONE]'

        class Client:
            def __init__(self, complete, status, finish_reason=None, error_event=False):
                self.complete, self.status = complete, status
                self.finish_reason, self.error_event = finish_reason, error_event

            def stream(self, method, url, json):
                return Upstream(self.complete, self.status, self.finish_reason, self.error_event)

        endpoint = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        module = types.ModuleType("s03_memory")
        writes = []
        module.persist_turn = lambda *args: writes.append(args)
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        body = {"messages": [{"role": "user", "content": "Проверь поток"}],
                "request_id": "r-test", "mini": True, "use_memory": False}

        async def get_frames():
            response = await endpoint(Request(body))
            return [json.loads(part) async for part in response.body_iterator]

        for complete, status, finish_reason, error_event, expected_ok in (
            (False, 200, None, False, False),
            (True, 503, None, False, False),
            (True, 200, "length", False, False),
            (True, 200, None, True, False),
            (True, 200, "stop", False, True),
        ):
            with self.subTest(complete=complete, status=status,
                              finish_reason=finish_reason, error_event=error_event):
                writes.clear()
                bridge.hc = lambda: Client(complete, status, finish_reason, error_event)
                with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
                    frames = asyncio.run(get_frames())
                terminal = [v for v in frames if v.get("done") is True]
                self.assertEqual(frames[0]["request_receipt"]["status"], "RECEIVED")
                self.assertFalse(frames[0]["request_receipt"]["native_admission_verified"])
                if expected_ok:
                    self.assertEqual(len(writes), 1)
                    self.assertEqual(len(terminal), 1)
                    self.assertEqual(terminal[0]["memory_history"]["status"], "SAVED")
                    self.assertFalse(terminal[0]["memory_history"]["s03_readback_verified"])
                    self.assertEqual(terminal[0]["completion_receipt"]["status"], "GENERATED")
                    self.assertTrue(terminal[0]["completion_receipt"]["upstream_done"])
                    self.assertEqual(terminal[0]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                    self.assertFalse(terminal[0]["memory_write_receipt"]["s03_readback_verified"])
                else:
                    self.assertEqual(writes, [])
                    self.assertEqual(terminal, [])
                    self.assertEqual(frames[-1]["status"], "HOLD")
                    self.assertEqual(frames[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
                    self.assertFalse(frames[-1]["done"])
                    self.assertEqual(frames[-1]["completion_receipt"]["status"], "HOLD")
                    self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
                    self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])


    def test_broadcast_stop_survives_new_chat_and_does_not_stop_future_chats(self):
        """New request must not clear a STOP already sent to an older stream."""
        class Upstream:
            status_code = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *ignored):
                return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ"}}]}'
                yield 'data: [DONE]'

        class Client:
            def __init__(self, calls):
                self.calls = calls
            def stream(self, *args, **kwargs):
                self.calls.append("MODEL_POST")
                return Upstream()

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        self.bridge.IDENTITY, self.bridge.STATIC_RULES, self.bridge.NKEEP = "", "", 0
        self.bridge.LAST_CHAT = {"t": 0}
        calls, writes = [], []
        self.bridge.hc = lambda: Client(calls)
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)
        def body(rid):
            return Request({"request_id": rid, "mini": True, "use_memory": False,
                            "messages": [{"role": "user", "content": "Проверь STOP"}]})

        async def scenario():
            old_response = await chat(body("older"))
            old_stream = old_response.body_iterator
            first = json.loads(await old_stream.__anext__())
            await stop(Request({"request_id": "*"}))
            # Merely creating and consuming this newer stream used to discard
            # the global STOP and let the older request reach the model.
            new_response = await chat(body("newer"))
            newer = [json.loads(row) async for row in new_response.body_iterator]
            older = [json.loads(row) async for row in old_stream]
            return first, newer, older

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "W", None), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            first, newer, older = asyncio.run(scenario())
        self.assertEqual(first["request_receipt"]["status"], "RECEIVED")
        self.assertEqual(older[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(older[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertEqual(newer[-1]["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(writes), 1)

if __name__ == "__main__":
    unittest.main()
