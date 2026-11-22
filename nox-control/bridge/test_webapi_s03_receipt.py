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
    def test_0a03_malformed_chat_never_starts_stream_or_memory(self):
        # Real FastAPI route callback; all cases return before the model/S03
        # generator is created. No fake successful stream receipt.
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        cases = (
            (None, "CHAT_INVALID_BODY"),
            (["not", "a", "dict"], "CHAT_INVALID_BODY"),
            ({"messages": ["not-a-message"]}, "CHAT_INVALID_MESSAGES"),
            ({"messages": [{"role": "user", "content": {"unsafe": True}}]}, "CHAT_INVALID_CONTENT"),
            ({"options": ["wrong-shape"]}, "CHAT_INVALID_OPTIONS"),
            ({"options": {"num_predict": "nan"}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"options": {"num_predict": -1}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"messages": ""}, "CHAT_INVALID_MESSAGES"),
            ({"messages": 0}, "CHAT_INVALID_MESSAGES"),
            ({"messages": False}, "CHAT_INVALID_MESSAGES"),
            ({"messages": None}, "CHAT_INVALID_MESSAGES"),
            ({"options": []}, "CHAT_INVALID_OPTIONS"),
            ({"options": 0}, "CHAT_INVALID_OPTIONS"),
            ({"options": False}, "CHAT_INVALID_OPTIONS"),
            ({"options": None}, "CHAT_INVALID_OPTIONS"),
            ({"options": {"num_predict": 0}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"options": {"num_predict": False}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"options": {"num_predict": None}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"options": {"num_predict": 1.5}}, "CHAT_INVALID_NUM_PREDICT"),
            ({"request_id": {"id": "foreign"}, "messages": [{"role": "user", "content": "hi"}]}, "CHAT_INVALID_REQUEST_ID"),
            ({"request_id": None, "messages": [{"role": "user", "content": "hi"}]}, "CHAT_INVALID_REQUEST_ID"),
            ({"request_id": True, "messages": [{"role": "user", "content": "hi"}]}, "CHAT_INVALID_REQUEST_ID"),
            ({"request_id": "*", "messages": [{"role": "user", "content": "hi"}]}, "CHAT_INVALID_REQUEST_ID"),
            ({"messages": [{"role": "assistant", "content": "only response"}]}, "CHAT_MISSING_USER"),
            ({"messages": [{"role": "user", "content": "   "}]}, "CHAT_MISSING_USER"),
        )
        for body, code in cases:
            with self.subTest(body=body):
                response = asyncio.run(chat(Request(body)))
                self.assertEqual(response.status_code, 400)
                payload = json.loads(response.body)
                self.assertEqual(payload, {"status": "HOLD", "reason": code})

    def test_1a03_process_local_snapshot_reconciles_utf8_and_disconnect(self):
        """Snapshot is bounded, non-replaying and never certifies S03 readback."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        snapshot = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/snapshot")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class Upstream:
            status_code = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def aiter_lines(self):
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "Привет 🌌"}}]}, ensure_ascii=False)
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                return Upstream()

        bridge.hc = lambda: Client()
        def request(rid, ephemeral=False):
            return Request({"request_id": rid, "mini": True, "use_memory": False,
                            "ephemeral": ephemeral,
                            "messages": [{"role": "user", "content": "Проверить Unicode"}]})

        async def scenario():
            response = await chat(request("snap-complete"))
            frames = [json.loads(part) async for part in response.body_iterator]
            sid = frames[0]["stream_id"]
            finished = await snapshot(stream_id=sid, request_id="snap-complete")
            wrong = await snapshot(stream_id=sid, request_id="snap-other")
            disconnected = await chat(request("snap-interrupted"))
            first = json.loads(await disconnected.body_iterator.__anext__())
            await disconnected.body_iterator.aclose()
            partial = await snapshot(stream_id=first["stream_id"], request_id="snap-interrupted")
            private = await chat(request("snap-private", ephemeral=True))
            private_id = json.loads(await private.body_iterator.__anext__())["stream_id"]
            await private.body_iterator.aclose()
            unavailable = await snapshot(stream_id=private_id, request_id="snap-private")
            return frames, finished, wrong, partial, unavailable

        with mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \\
             mock.patch.object(W, "W", None), \\
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames, finished, wrong, partial, unavailable = asyncio.run(scenario())
        self.assertEqual(finished.status_code, 200)
        saved = json.loads(finished.body)
        self.assertEqual(saved["message"]["content"], "Привет 🌌")
        self.assertEqual(saved["event_seq"], len(frames))
        self.assertEqual(saved["status"], "GENERATED")
        self.assertTrue(saved["done"])
        self.assertFalse(saved["s03_readback_verified"])
        self.assertFalse(saved["replay_supported"])
        self.assertEqual(saved["snapshot_scope"], "PROCESS_LOCAL")
        self.assertEqual(saved["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertEqual(wrong.status_code, 404)
        self.assertEqual(json.loads(partial.body)["status"], "INTERRUPTED")
        self.assertFalse(json.loads(partial.body)["done"])
        self.assertEqual(unavailable.status_code, 404)
        self.assertEqual(len(writes), 1)

    def test_missing_legacy_request_id_is_unique_and_stop_addressable(self):
        # A real chat endpoint first frame, without any model POST or S03 write.
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        async def first_frame():
            response = await chat(Request({"messages": [{"role": "user", "content": "hello"}],
                                           "mini": True, "use_memory": False}))
            frame = json.loads(await response.body_iterator.__anext__())
            await response.body_iterator.aclose()
            return frame
        frames = [asyncio.run(first_frame()) for _ in range(2)]
        ids = [frame["request_id"] for frame in frames]
        self.assertEqual(len(set(ids)), 2)
        for frame in frames:
            self.assertRegex(frame["request_id"], r"^[0-9a-f]{32}$")
            self.assertRegex(frame["stream_id"], r"^[0-9a-f]{32}$")
            self.assertEqual(frame["event_seq"], 1)
            self.assertEqual(frame["request_receipt"]["request_id"], frame["request_id"])
            self.assertEqual(frame["request_receipt"]["status"], "RECEIVED")
        self.assertNotEqual(frames[0]["stream_id"], frames[1]["stream_id"])

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
            def __init__(self, complete, status, finish_reason=None, error_event=False, after_done=None):
                self.complete, self.status_code = complete, status
                self.finish_reason, self.error_event, self.after_done = finish_reason, error_event, after_done

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
                    if isinstance(self.after_done, Exception):
                        raise self.after_done
                    if self.after_done is not None:
                        yield self.after_done

        class Client:
            def __init__(self, complete, status, finish_reason=None, error_event=False, after_done=None):
                self.complete, self.status = complete, status
                self.finish_reason, self.error_event, self.after_done = finish_reason, error_event, after_done

            def stream(self, method, url, json):
                return Upstream(self.complete, self.status, self.finish_reason,
                                self.error_event, self.after_done)

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

        seen_stream_ids = set()
        for complete, status, finish_reason, error_event, after_done, expected_ok in (
            (False, 200, None, False, None, False),
            (True, 503, None, False, None, False),
            (True, 200, "length", False, None, False),
            (True, 200, None, True, None, False),
            # [DONE] with visible content but no model stop finish is incomplete.
            (True, 200, None, False, None, False),
            # A successful DONE is only valid after a clean HTTP stream EOF.
            (True, 200, "stop", False, 'data: {"error":"late"}', False),
            (True, 200, "stop", False, OSError("reset after DONE"), False),
            (True, 200, "stop", False, None, True),
        ):
            with self.subTest(complete=complete, status=status,
                              finish_reason=finish_reason, error_event=error_event,
                              after_done=str(after_done)):
                writes.clear()
                bridge.hc = lambda: Client(complete, status, finish_reason,
                                           error_event, after_done)
                with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
                    frames = asyncio.run(get_frames())
                # Every NDJSON frame (including incomplete HOLD) carries
                # the unique server stream ID and a gap-detectable cursor.
                stream_ids = {v.get("stream_id") for v in frames}
                self.assertEqual(len(stream_ids), 1)
                stream_id = next(iter(stream_ids))
                self.assertRegex(stream_id, r"^[0-9a-f]{32}$")
                self.assertNotIn(stream_id, seen_stream_ids)
                seen_stream_ids.add(stream_id)
                self.assertEqual([v.get("event_seq") for v in frames],
                                 list(range(1, len(frames) + 1)))
                self.assertTrue(all(v["request_id"] == "r-test" for v in frames))
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

        # Reviewer counterexample: A -> stop -> B -> DONE must not
        # generate terminal success or persist an unverifiable "AB".
        class PostStopUpstream(Upstream):
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: {"choices":[{"delta":{"content":"B"}}]}'
                yield 'data: [DONE]'

        class PostStopClient(Client):
            def stream(self, *args, **kwargs):
                return PostStopUpstream(True, 200, "stop")

        writes.clear()
        bridge.hc = lambda: PostStopClient(True, 200, "stop")
        with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
            post_stop_frames = asyncio.run(get_frames())
        self.assertEqual(writes, [])
        self.assertFalse(any(v.get("done") is True for v in post_stop_frames))
        self.assertEqual(post_stop_frames[-1]["status"], "HOLD")
        self.assertEqual(post_stop_frames[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
        self.assertEqual(post_stop_frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertTrue(any("UPSTREAM_AFTER_STOP_FINISH" in item for item in bridge.errors))

        # A falsey non-string delta after real tokens must not be quietly
        # erased before finish_reason=stop and committed to S03.
        class FalseyContentUpstream(Upstream):
            status_code = 200
            def __init__(self, invalid):
                self.invalid = invalid
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
                yield 'data: ' + json.dumps({
                    "choices": [{"delta": {"content": self.invalid},
                                 "finish_reason": "stop"}]})
                yield 'data: [DONE]'

        class FalseyContentClient:
            def __init__(self, invalid):
                self.invalid = invalid
            def stream(self, *args, **kwargs):
                return FalseyContentUpstream(self.invalid)

        for invalid in (0, False, [], {}):
            with self.subTest(falsey_invalid=invalid):
                writes.clear()
                bridge.errors.clear()
                bridge.hc = lambda invalid=invalid: FalseyContentClient(invalid)
                with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
                    bad_frames = asyncio.run(get_frames())
                self.assertEqual(writes, [])
                self.assertFalse(any(v.get("done") is True for v in bad_frames))
                self.assertEqual(bad_frames[-1]["status"], "HOLD")
                self.assertEqual(bad_frames[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(bad_frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertTrue(any("UPSTREAM_CONTENT_INVALID" in item for item in bridge.errors))


        # A malformed top-level delta (0/false/[]/""/null) must not be
        # converted to {} by truthiness and accepted as the stop chunk.
        class FalseyDeltaUpstream(Upstream):
            status_code = 200
            def __init__(self, invalid):
                self.invalid = invalid
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
                yield 'data: ' + json.dumps({
                    "choices": [{"delta": self.invalid, "finish_reason": "stop"}]})
                yield 'data: [DONE]'

        class FalseyDeltaClient:
            def __init__(self, invalid):
                self.invalid = invalid
            def stream(self, *args, **kwargs):
                return FalseyDeltaUpstream(self.invalid)

        for invalid_delta in (0, False, [], "", None):
            with self.subTest(falsey_delta=invalid_delta):
                writes.clear()
                bridge.errors.clear()
                bridge.hc = lambda invalid=invalid_delta: FalseyDeltaClient(invalid)
                with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
                    bad_frames = asyncio.run(get_frames())
                self.assertEqual(writes, [])
                self.assertFalse(any(v.get("done") is True for v in bad_frames))
                self.assertEqual(bad_frames[-1]["status"], "HOLD")
                self.assertEqual(bad_frames[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(bad_frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertTrue(any("UPSTREAM_DELTA_INVALID" in item for item in bridge.errors))




    def test_1a03_ambiguous_sse_json_never_certifies_s03(self):
        """Duplicate/nonfinite/multi-choice model envelopes must fail closed."""
        invalid_events = (
            # JSON duplicate keys (including nested keys) must not be
            # interpreted according to provider-specific last-key wins.
            '{"choices":[{"delta":{},"finish_reason":"stop"}],"choices":[{"delta":{},"finish_reason":"stop"}]}',
            '{"choices":[{"delta":{},"finish_reason":"stop","finish_reason":"stop"}]}',
            '{"choices":[{"delta":{"content":"B","content":"B"},"finish_reason":"stop"}]}',
            # Python json.loads accepts nonstandard JSON constants by default.
            '{"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"total_tokens":NaN}}',
            # Ignoring the second choice could falsely authorize completion.
            '{"choices":[{"delta":{},"finish_reason":"stop"},{"delta":{"content":"B"}}]}',
        )

        class Upstream:
            status_code = 200
            def __init__(self, event):
                self.event = event
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
                yield 'data: ' + self.event
                yield 'data: [DONE]'

        class Client:
            def __init__(self, event):
                self.event = event
            def stream(self, *args, **kwargs):
                return Upstream(self.event)

        endpoint = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        mem = types.ModuleType("s03_memory")
        writes = []
        mem.persist_turn = lambda *args: writes.append(args)
        async def frames():
            response = await endpoint(Request({
                "messages": [{"role": "user", "content": "Check stream integrity"}],
                "mini": True, "use_memory": False}))
            return [json.loads(part) async for part in response.body_iterator]

        for event in invalid_events:
            with self.subTest(event=event):
                writes.clear()
                bridge.errors.clear()
                bridge.hc = lambda event=event: Client(event)
                with mock.patch.dict(sys.modules, {"s03_memory": mem}), mock.patch.object(W, "W", None):
                    observed = asyncio.run(frames())
                self.assertEqual(writes, [])
                self.assertFalse(any(frame.get("done") is True for frame in observed))
                self.assertEqual(observed[-1]["status"], "HOLD")
                self.assertEqual(observed[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(observed[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertTrue(any("INVALID_SSE_JSON" in error or
                                    "UPSTREAM_CHOICES_INVALID" in error
                                    for error in bridge.errors))

    def test_upstream_invalid_unicode_or_output_overrun_skips_s03(self):
        """1A03: only bounded valid Unicode may reach terminal SSE/S03."""
        class Upstream:
            status_code = 200
            def __init__(self, content):
                self.content = content
            async def __aenter__(self):
                return self
            async def __aexit__(self, *ignored):
                return False
            async def aiter_lines(self):
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "А"}}]})
                yield 'data: ' + json.dumps({
                    "choices": [{"delta": {"content": self.content},
                                 "finish_reason": "stop"}]})
                yield 'data: [DONE]'

        class Client:
            def __init__(self, content):
                self.content = content
            def stream(self, *args, **kwargs):
                return Upstream(self.content)

        endpoint = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        async def frames():
            response = await endpoint(Request({
                "messages": [{"role": "user", "content": "Проверка UTF-8"}],
                "mini": True, "use_memory": False,
                "request_id": "utf8-bound-test"}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        for content, expected_error in (
            ("\ud800", "UPSTREAM_CONTENT_UNICODE_INVALID"),
            ("x" * (W.MAX_CHAT_OUTPUT_UTF8_BYTES + 1), "UPSTREAM_OUTPUT_LIMIT"),
        ):
            with self.subTest(error=expected_error):
                writes.clear()
                bridge.errors.clear()
                bridge.hc = lambda content=content: Client(content)
                with mock.patch.dict(sys.modules, {"s03_memory": memory}), mock.patch.object(W, "W", None):
                    emitted = asyncio.run(frames())
                self.assertFalse(any(e.get("done") is True for e in emitted))
                self.assertEqual(emitted[-1]["status"], "HOLD")
                self.assertEqual(emitted[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(emitted[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertEqual(writes, [])
                self.assertTrue(any(expected_error in msg for msg in bridge.errors))


    def test_1a03_raw_sse_line_limit_and_utf8_fence_s03(self):
        """Real byte-stream parser rejects malformed/oversize frames before S03."""
        class BytesUpstream:
            status_code = 200
            def __init__(self, wire):
                self.wire = wire
            async def __aenter__(self):
                return self
            async def __aexit__(self, *ignored):
                return False
            async def aiter_bytes(self, chunk_size=4096):
                # Split inside the UTF-8 multi-byte character too.
                for off in range(0, len(self.wire), 3):
                    yield self.wire[off:off + 3]

        async def lines(wire):
            return [line async for line in W._bounded_upstream_sse_lines(BytesUpstream(wire))]

        healthy = 'data: {"content":"А"}\\r\\ndata: [DONE]\\r\\n'.replace('\\r', '\r').replace('\\n', '\n').encode("utf-8")
        self.assertEqual(asyncio.run(lines(healthy)), [
            'data: {"content":"А"}', 'data: [DONE]'])
        with self.assertRaises(UnicodeDecodeError):
            asyncio.run(lines(b'data: {"bad":"\\xff"}\n'.replace(b'\\xff', b'\xff')))
        with self.assertRaisesRegex(ValueError, "UPSTREAM_SSE_LINE_TOO_LONG"):
            asyncio.run(lines(b'data: ' + b'x' * W.MAX_UPSTREAM_SSE_LINE_BYTES))

        class Client:
            def __init__(self, wire):
                self.wire = wire
            def stream(self, *args, **kwargs):
                return BytesUpstream(self.wire)

        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        endpoint = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)
        async def frames():
            response = await endpoint(Request({
                "messages": [{"role": "user", "content": "Проверить сырые SSE bytes"}],
                "request_id": "raw-sse-limit", "mini": True, "use_memory": False}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        good_prefix = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
        for malformed in (
            good_prefix + b'data: {"choices":\xff}\n',
            good_prefix + b'data: ' + b'z' * (W.MAX_UPSTREAM_SSE_LINE_BYTES + 1),
        ):
            with self.subTest(payload_bytes=len(malformed)):
                writes.clear()
                bridge.errors.clear()
                bridge.hc = lambda malformed=malformed: Client(malformed)
                with mock.patch.dict(sys.modules, {"s03_memory": memory}), mock.patch.object(W, "W", None):
                    observed = asyncio.run(frames())
                self.assertFalse(any(frame.get("done") is True for frame in observed))
                self.assertEqual(observed[-1].get("status"), "HOLD")
                self.assertEqual(observed[-1].get("reason"), "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(observed[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertEqual(writes, [])

    def test_skeptic_annotation_never_bypasses_s03_utf8_budget(self):
        """1A03: invalid or oversized optional skeptic text cannot poison S03."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Thinking:
            def __init__(self, doubt): self.doubt = doubt
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            async def skeptic(self, *args, **kwargs):
                return {"ok": False, "doubt": self.doubt}

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT = 0, {"t": 0}
        bridge.SOUL = None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Проверка"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario():
            response = await chat(Request({
                "mode": "thoughtful", "use_memory": False,
                "messages": [{"role": "user", "content": "Проверка"}]}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        for doubt, accepted in (
            ("x" * W.MAX_CHAT_OUTPUT_UTF8_BYTES, False),
            ("\ud800", False),
            (["not", "text"], False),
            ("Сомневаюсь", True),
        ):
            with self.subTest(accepted=accepted, kind=type(doubt).__name__):
                writes.clear()
                with mock.patch.object(W, "W", Thinking(doubt)), \
                     mock.patch.dict(sys.modules, {"s03_memory": memory}):
                    frames = asyncio.run(scenario())
                terminal = frames[-1]
                self.assertTrue(terminal["done"])
                self.assertEqual(terminal["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(terminal["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                self.assertEqual(len(writes), 1)
                suffix = "\n\n⚠ Скептик: Сомневаюсь" if accepted else ""
                self.assertEqual(writes[0][1], "Ответ" + suffix)
                if not accepted:
                    self.assertEqual(terminal["skeptic"]["reason"],
                                     "SKEPTIC_ANNOTATION_INVALID_OR_OVERSIZE")
                self.assertTrue(all(frame.get("status") != "HOLD" for frame in frames))

    def test_optional_skeptic_failure_cannot_lose_completed_answer_or_s03_write(self):
        """1A03: optional verifier errors are explicitly unavailable, not model errors."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ модели"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Thinking:
            def __init__(self, verdict): self.verdict = verdict
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            async def skeptic(self, *args, **kwargs):
                if isinstance(self.verdict, Exception):
                    raise self.verdict
                return self.verdict

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT = 0, {"t": 0}
        bridge.SOUL = None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Вопрос"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def collect():
            response = await chat(Request({
                "mode": "thoughtful", "use_memory": False,
                "messages": [{"role": "user", "content": "Вопрос"}]}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        for verdict, expected_ok in (
            (RuntimeError("verifier unavailable"), None),
            (["invalid", "verdict"], None),
            ({"ok": 1, "doubt": "wrong boolean"}, None),
            ({"ok": True}, True),
        ):
            with self.subTest(verdict_type=type(verdict).__name__, expected_ok=expected_ok):
                writes.clear()
                with mock.patch.object(W, "W", Thinking(verdict)), \
                     mock.patch.dict(sys.modules, {"s03_memory": memory}):
                    frames = asyncio.run(collect())
                terminal = frames[-1]
                self.assertTrue(terminal["done"])
                self.assertEqual(terminal["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(terminal["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                self.assertFalse(terminal["memory_write_receipt"]["s03_readback_verified"])
                self.assertEqual(writes, [("Вопрос", "Ответ модели")])
                self.assertEqual(terminal["skeptic"]["ok"], expected_ok)
                if expected_ok is None:
                    self.assertEqual(terminal["skeptic"]["reason"], "SKEPTIC_UNAVAILABLE")
                    self.assertTrue(any("проверка недоступна" in
                        str(f.get("nox_event", {}).get("text", "")) for f in frames))
                self.assertFalse(any(f.get("status") == "HOLD" for f in frames))

    def test_stop_during_memory_or_prompt_assembly_never_posts_model(self):
        """1A04: accepted STOP after a slow phase must not start GPU inference."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.SOUL = None
        bridge.LAST_CHAT = {"t": 0}
        bridge.NKEEP = 0
        bridge.adapt_tokens = lambda *_: 64
        bridge.self_vol = lambda _: ""
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        for stage in ("memory", "pre-model"):
            with self.subTest(stage=stage):
                rid = "a6-stop-before-" + stage
                model_calls = []
                writes.clear()
                W.CANCEL.discard(rid)

                def memory_block(_):
                    if stage == "memory":
                        W.CANCEL.add(rid)
                    return ""

                def build_msgs(*_):
                    if stage == "pre-model":
                        W.CANCEL.add(rid)
                    return [{"role": "user", "content": "Do not start after STOP"}]

                def client():
                    model_calls.append("POST_ATTEMPT")
                    raise AssertionError("model client must not be constructed")

                bridge.memory_block = memory_block
                bridge.build_msgs = build_msgs
                bridge.hc = client

                async def collect():
                    response = await chat(Request({
                        "messages": [{"role": "user", "content": "STOP during preparation"}],
                        "request_id": rid, "mini": False,
                        "use_memory": stage == "memory",
                    }))
                    return [json.loads(chunk) async for chunk in response.body_iterator]

                with mock.patch.dict(sys.modules, {"s03_memory": memory}), mock.patch.object(W, "W", None):
                    frames = asyncio.run(collect())

                self.assertEqual(model_calls, [])
                self.assertEqual(writes, [])
                self.assertEqual(frames[-1]["done_reason"], "stopped")
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
                self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertNotIn(rid, W.ACTIVE_CHAT_IDS)
                self.assertNotIn(rid, W.CANCEL)


    def test_stop_on_plan_status_prevents_optional_gpu_planning(self):
        """1A04: STOP at plan SSE status must not invoke the planner model."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        bridge = self.bridge
        bridge.LAST_CHAT, bridge.NKEEP = {"t": 0}, 0
        model_calls = []
        bridge.hc = lambda: model_calls.append("main-model")
        bridge.ask = lambda *args, **kwargs: model_calls.append("plan-model")
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        class Thinking:
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return True
            def mode_hint(self, *args): return ""
            async def make_plan(self, *args):
                model_calls.append("make_plan")
                return ["unexpected"]

        async def scenario():
            response = await chat(Request({
                "request_id": "stop-before-plan-model", "mode": "thoughtful",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Составь план"}],
            }))
            frames, stop_result = [], None
            async for item in response.body_iterator:
                frame = json.loads(item)
                frames.append(frame)
                if (frame.get("nox_event") or {}).get("step") == "plan":
                    stop_result = await stop(Request({
                        "scope": "generation", "request_id": "stop-before-plan-model"}))
            return frames, stop_result

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "W", Thinking()), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames, signal = asyncio.run(scenario())
        self.assertEqual(signal["status"], "STOPPING")
        self.assertFalse(signal["stop_confirmed"])
        self.assertEqual(model_calls, [])
        self.assertEqual(writes, [])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])

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
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
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


    def test_stop_during_post_generation_skeptic_skips_s03_write(self):
        """STOP delivered during skeptic must fence later persistence."""
        class Upstream:
            status_code = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *ignored):
                return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                return Upstream()

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        bridge = self.bridge
        bridge.LAST_CHAT, bridge.NKEEP = {"t": 0}, 0
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Проверь отмену"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        class Thinking:
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            async def skeptic(self, *args, **kwargs):
                signal = await stop(Request({"request_id": "stop-in-skeptic"}))
                self.signal = signal
                return {"ok": True}

        thinking = Thinking()
        async def scenario():
            response = await chat(Request({
                "request_id": "stop-in-skeptic",
                "mode": "thoughtful",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Проверь отмену"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "W", thinking), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(scenario())
        self.assertEqual(thinking.signal["status"], "STOPPING")
        self.assertEqual(writes, [])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "HOLD")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_stop_after_skeptic_status_never_calls_second_model(self):
        """1A04: client STOP on check event must fence optional skeptic inference."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *ignored): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        bridge = self.bridge
        bridge.LAST_CHAT, bridge.NKEEP = {"t": 0}, 0
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Стоп проверка"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        class Thinking:
            def __init__(self): self.skeptic_calls = 0
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            async def skeptic(self, *args, **kwargs):
                self.skeptic_calls += 1
                return {"ok": True}

        thinking = Thinking()
        async def scenario():
            response = await chat(Request({
                "request_id": "stop-before-skeptic",
                "mode": "thoughtful",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Стоп проверка"}],
            }))
            frames = []
            stop_status = None
            async for row in response.body_iterator:
                frame = json.loads(row)
                frames.append(frame)
                if (frame.get("nox_event") or {}).get("step") == "check":
                    signal = await stop(Request({"request_id": "stop-before-skeptic"}))
                    stop_status = signal["status"]
            return frames, stop_status

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "W", thinking), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames, signal_status = asyncio.run(scenario())
        self.assertEqual(signal_status, "STOPPING")
        self.assertEqual(thinking.skeptic_calls, 0)
        self.assertEqual(writes, [])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])
        self.assertNotEqual(frames[-1]["memory_write_receipt"]["status"], "SAVED")

    def test_secondary_soul_mirror_is_gated_by_s03_write_and_is_nonfatal(self):
        """S03 failure must not leak into secondary memory; mirror failure cannot hide DONE."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *ignored): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT = 0, {"t": 0}
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Запомни ответ"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        mirror_calls = []

        def mirror(user, answer):
            mirror_calls.append((user, answer))
            raise RuntimeError("secondary mirror unavailable")

        bridge.SOUL = types.SimpleNamespace(log_turn=mirror)
        memory = types.ModuleType("s03_memory")

        async def scenario():
            response = await chat(Request({
                "request_id": "s03-secondary-gate", "mode": "fast",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Запомни ответ"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        for fail_s03 in (True, False):
            with self.subTest(fail_s03=fail_s03):
                mirror_calls.clear()
                bridge.errors.clear()

                def persist(*args):
                    if fail_s03:
                        raise RuntimeError("S03 unavailable")

                memory.persist_turn = persist
                with mock.patch.object(W, "CANCEL", set()), \
                     mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
                     mock.patch.object(W, "W", None), \
                     mock.patch.dict(sys.modules, {"s03_memory": memory}):
                    frames = asyncio.run(scenario())

                terminal = frames[-1]
                self.assertEqual(terminal["completion_receipt"]["status"], "GENERATED")
                self.assertTrue(terminal["done"])
                self.assertFalse(terminal["memory_write_receipt"]["s03_readback_verified"])
                if fail_s03:
                    self.assertEqual(terminal["memory_history"]["status"], "HOLD")
                    self.assertEqual(mirror_calls, [])
                    self.assertFalse(any("soul_secondary_log_error" in e for e in bridge.errors))
                else:
                    self.assertEqual(terminal["memory_history"]["status"], "SAVED")
                    self.assertEqual(mirror_calls, [("Запомни ответ", "Ответ")])
                    self.assertTrue(any("soul_secondary_log_error RuntimeError" in e for e in bridge.errors))

    def test_stop_while_s03_write_returns_preserves_receipt_but_no_soul_mirror(self):
        """A late STOP must not become GENERATED after asynchronous S03 write."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *ignored): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Сохранённый ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        rid = "stop-during-s03-write"
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT = 0, {"t": 0}
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Проверь поздний STOP"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        mirrors = []
        bridge.SOUL = types.SimpleNamespace(log_turn=lambda *args: mirrors.append(args))
        memory = types.ModuleType("s03_memory")
        writes = []

        def persist(*args):
            writes.append(args)
            # The real endpoint is asynchronously awaiting to_thread here.
            W.CANCEL.add(rid)

        memory.persist_turn = persist

        async def scenario():
            response = await chat(Request({
                "request_id": rid, "mode": "fast", "use_memory": False,
                "messages": [{"role": "user", "content": "Проверь поздний STOP"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "W", None), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(scenario())
        self.assertEqual(len(writes), 1)
        self.assertEqual(mirrors, [])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_stop_scope_and_bad_json_cannot_cancel_all(self):
        """Invalid or non-generation commands cannot trigger an implicit broadcast."""
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")

        class BadJSON:
            async def json(self):
                raise ValueError("broken payload")

        async def scenario():
            bad = await stop(BadJSON())
            wrong_shape = await stop(Request(["not", "an", "object"]))
            wrong_scope = await stop(Request({"scope": "owner", "request_id": "*"}))
            media_scope = await stop(Request({"scope": "media", "request_id": "*"}))
            bad_target = await stop(Request({"request_id": {"id": "r1"}}))
            empty_target = await stop(Request({"request_id": ""}))
            missing_target = await stop(Request({}))
            missing_scoped = await stop(Request({"scope": "generation"}))
            null_target = await stop(Request({"request_id": None}))
            before = (W.CANCEL_ALL_EPOCH, set(W.CANCEL))
            valid = await stop(Request({"scope": "generation", "request_id": "chat-1"}))
            return (bad, wrong_shape, wrong_scope, media_scope, bad_target,
                    empty_target, missing_target, missing_scoped, null_target,
                    before, valid, (W.CANCEL_ALL_EPOCH, set(W.CANCEL)))

        with mock.patch.object(W, "CANCEL", set()), mock.patch.object(W, "CANCEL_ALL_EPOCH", 0):
            bad, shape, owner, media, target, empty, missing, scoped, null, before, valid, after = asyncio.run(scenario())
        self.assertEqual([x.status_code for x in (bad, shape, owner, media, target, empty, missing, scoped, null)],
                         [400, 400, 409, 409, 400, 400, 400, 400, 400])
        self.assertEqual(before, (0, set()))
        self.assertEqual(after, (0, {"chat-1"}))
        self.assertEqual(valid["status"], "STOPPING")
        self.assertEqual(valid["scope"], "generation")
        self.assertEqual(valid["target_request_id"], "chat-1")
        self.assertFalse(valid["stop_confirmed"])
        self.assertFalse(valid["media_stopped"])
        self.assertFalse(valid["task_cancelled"])
        self.assertFalse(valid["owner_stop"])

    def test_1a04_pending_scoped_stop_is_bounded_without_broadcast(self):
        """Excess unknown IDs HOLD; existing STOP and explicit broadcast still work."""
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        known = {f"pending-{i}" for i in range(W.MAX_PENDING_SCOPED_STOPS)}

        async def scenario():
            denied = await stop(Request({"scope": "generation", "request_id": "new-id"}))
            repeat = await stop(Request({"scope": "generation", "request_id": "pending-0"}))
            epoch_before = W.CANCEL_ALL_EPOCH
            broadcast = await stop(Request({"scope": "generation", "request_id": "*"}))
            return denied, repeat, broadcast, epoch_before, W.CANCEL_ALL_EPOCH, set(W.CANCEL)

        with mock.patch.object(W, "CANCEL", set(known)), mock.patch.object(W, "CANCEL_ALL_EPOCH", 0):
            denied, repeat, broadcast, before, after, pending = asyncio.run(scenario())
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(json.loads(denied.body), {"status": "HOLD", "reason": "STOP_PENDING_CAPACITY"})
        self.assertEqual(repeat["status"], "STOPPING")
        self.assertFalse(repeat["stop_confirmed"])
        self.assertEqual(repeat["target_request_id"], "pending-0")
        self.assertEqual(broadcast["target_request_id"], "*")
        self.assertEqual((before, after), (0, 1))
        self.assertEqual(pending, known)


    def test_1a04_live_scoped_stop_survives_unknown_id_capacity(self):
        """A real admitted chat remains stoppable when unknown tombstones fill the cap."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        known = {f"pending-{i}" for i in range(W.MAX_PENDING_SCOPED_STOPS)}
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        def request(rid):
            return Request({"request_id": rid, "mini": True, "use_memory": False,
                            "messages": [{"role": "user", "content": "please stop"}]})

        async def scenario():
            live_a = await chat(request("live-a"))
            live_b = await chat(request("live-b"))
            # Both IDs are admitted BEFORE a single SSE frame is consumed.
            admitted = set(W.ACTIVE_CHAT_IDS)
            duplicate = await chat(request("live-a"))
            denied_unknown = await stop(Request({"scope": "generation", "request_id": "never-seen"}))
            stopped_a = await stop(Request({"scope": "generation", "request_id": "live-a"}))
            other_untouched = "live-b" not in W.CANCEL
            frames = [json.loads(x) async for x in live_a.body_iterator]
            first_b = json.loads(await live_b.body_iterator.__anext__())
            await live_b.body_iterator.aclose()
            return admitted, duplicate, denied_unknown, stopped_a, other_untouched, frames, first_b, set(W.ACTIVE_CHAT_IDS)

        with mock.patch.object(W, "CANCEL", set(known)), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            admitted, duplicate, denied, issued, untouched, frames, first_b, active_after = asyncio.run(scenario())
        self.assertEqual(admitted, {"live-a", "live-b"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(json.loads(duplicate.body)["reason"], "CHAT_DUPLICATE_INFLIGHT_REQUEST_ID")
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(issued["status"], "STOPPING")
        self.assertEqual(issued["target_request_id"], "live-a")
        self.assertTrue(untouched)
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertEqual(frames[-1]["memory_history"]["status"], "SKIPPED")
        self.assertEqual(first_b["request_id"], "live-b")
        self.assertEqual(active_after, set())
        self.assertEqual(writes, [])




    def test_1a04_preframe_abort_frees_active_slot_and_allows_retry(self):
        """An unstarted StreamingResponse must not permanently exhaust ACTIVE_CHAT_IDS."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        rid = "aborted-before-first-frame"

        def request():
            return Request({"request_id": rid, "mini": True, "use_memory": False,
                            "messages": [{"role": "user", "content": "retry after abort"}]})

        async def scenario():
            response = await chat(request())
            admitted = rid in W.ACTIVE_CHAT_IDS
            # No __anext__: the response was abandoned before any SSE frame.
            await response.body_iterator.aclose()
            released = rid not in W.ACTIVE_CHAT_IDS
            retry = await chat(request())
            readmitted = hasattr(retry, "body_iterator") and rid in W.ACTIVE_CHAT_IDS
            if hasattr(retry, "body_iterator"):
                await retry.body_iterator.aclose()
            return admitted, released, readmitted, rid not in W.ACTIVE_CHAT_IDS

        with mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CANCEL", set()):
            admitted, released, readmitted, clean = asyncio.run(scenario())
        self.assertEqual((admitted, released, readmitted, clean),
                         (True, True, True, True))

if __name__ == "__main__":
    unittest.main()
