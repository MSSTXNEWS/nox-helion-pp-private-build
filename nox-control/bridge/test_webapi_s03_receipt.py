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

    def test_1a01_optional_plan_and_skeptic_timeouts_keep_real_chat(self):
        """Timed-out optional model calls must not prevent primary SSE or S03."""
        chat = next(route.endpoint for route in self.app.routes if route.path == "/api/chat")
        bridge = self.bridge
        bridge.SOUL, bridge.NKEEP, bridge.LAST_CHAT = None, 0, {"t": 0}
        bridge.self_vol = lambda user: "[SELF]"
        bridge.build_msgs = lambda history, user, mem, vol, extra="": [
            {"role": "user", "content": user + extra}
        ]
        bridge.adapt_tokens = lambda user, limit: limit
        bridge.invalidate_s03_cache = lambda: None

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Готово 🌟"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Advisory:
            cancelled = 0
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return True
            def mode_hint(self, *args): return ""
            def is_factual(self, *args): return True
            async def make_plan(self, *args, **kwargs):
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    self.cancelled += 1
                    raise
            async def skeptic(self, *args, **kwargs):
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    self.cancelled += 1
                    raise

        bridge.hc = lambda: Client()
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)
        advisory = Advisory()

        async def exercise():
            response = await chat(Request({
                "request_id": "a1-optional-timeouts",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Спланируй и проверь факт"}],
            }))
            return [json.loads(frame) async for frame in response.body_iterator]

        with (mock.patch.object(W, "W", advisory),
              mock.patch.object(W, "ADVISORY_PLAN_TIMEOUT_SECONDS", 0.01),
              mock.patch.object(W, "ADVISORY_SKEPTIC_TIMEOUT_SECONDS", 0.01),
              mock.patch.object(W, "CANCEL", set()),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            frames = asyncio.run(exercise())
        final = frames[-1]
        self.assertTrue(final["done"])
        self.assertEqual(final["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(final["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertEqual(final["skeptic"]["reason"], "SKEPTIC_UNAVAILABLE")
        self.assertEqual(advisory.cancelled, 2)
        self.assertEqual(writes, [("Спланируй и проверь факт", "Готово 🌟")])
        self.assertEqual("".join(f["message"]["content"] for f in frames
                         if f.get("message") and f["message"]["content"]), "Готово 🌟")

    def test_1a03_skeptic_unicode_delta_matches_terminal_frames_and_snapshot(self):
        """A post-model skeptic annotation counts as a real emitted text frame."""
        import hashlib

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        snapshot = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/snapshot")
        bridge = self.bridge
        bridge.SOUL = None
        bridge.MODEL = "http://127.0.0.1:8098/v1/chat/completions"
        bridge.NKEEP, bridge.LAST_CHAT = 0, {"t": 0}
        bridge.self_vol = lambda user: "[SELF]"
        bridge.build_msgs = lambda history, user, mem, vol, extra="": [
            {"role": "user", "content": user}
        ]
        bridge.adapt_tokens = lambda user, limit: limit
        bridge.invalidate_s03_cache = lambda: None

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ 🧠"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                return Upstream()

        class Advisory:
            def maybe_reminder(self, *args):
                return None
            def wants_plan(self, *args):
                return False
            def mode_hint(self, *args):
                return ""
            def is_factual(self, *args):
                return True
            async def skeptic(self, *args, **kwargs):
                return {"ok": False, "doubt": "нужна ссылка"}

        bridge.hc = lambda: Client()
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        async def exercise():
            response = await chat(Request({
                "request_id": "skeptic-frame-1a03",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Уточни факт"}],
            }))
            frames = [json.loads(frame) async for frame in response.body_iterator]
            self.assertTrue(frames[-1]["done"])
            readback = await snapshot(frames[-1]["stream_id"], "skeptic-frame-1a03")
            return frames, json.loads(readback.body)

        with (mock.patch.object(W, "W", Advisory()),
              mock.patch.object(W, "CANCEL", set()),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.object(W, "SRC", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            frames, snap = asyncio.run(exercise())

        deltas = [f["message"]["content"] for f in frames
                  if isinstance(f.get("message"), dict) and f["message"].get("content")]
        expected = "Ответ 🧠\n\n⚠ Скептик: нужна ссылка"
        self.assertEqual("".join(deltas), expected)
        self.assertEqual(len(deltas), 2)
        self.assertEqual(frames[-1]["frames"], len(deltas))
        self.assertEqual(frames[-1]["digest"], hashlib.sha256(expected.encode()).hexdigest())
        self.assertEqual(snap["message"]["content"], expected)
        self.assertTrue(snap["terminal_digest_verified"])
        self.assertEqual(snap["snapshot_integrity"], "COMPLETE")
        self.assertFalse(snap["s03_readback_verified"])
        self.assertEqual(writes, [("Уточни факт", expected)])

    def test_2a05_stream_metrics_do_not_invent_provider_tokens(self):
        """Chunks are not tokens; duration must use monotonic time."""
        chat = next(route.endpoint for route in self.app.routes if route.path == "/api/chat")
        bridge = self.bridge
        bridge.SOUL, bridge.LAST_CHAT = None, {"t": 0}
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Два"}}]}'
                yield 'data: {"choices":[{"delta":{"content":" фрагмента"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        bridge.hc = lambda: Client()

        async def collect():
            response = await chat(Request({
                "request_id": "honest-metric-2a05", "mini": True,
                "use_memory": False, "ephemeral": True,
                "messages": [{"role": "user", "content": "Ответь"}]}))
            return [json.loads(frame) async for frame in response.body_iterator]

        # Simulate an invalid backward wall-clock correction: elapsed time
        # must stay nonnegative and remain independent of wall time.
        with mock.patch.object(W, "W", None), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.object(W.time, "time", return_value=-1000):
            frames = asyncio.run(collect())
        final = frames[-1]
        self.assertTrue(final["done"])
        self.assertEqual(final["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(final["frames"], 2)
        self.assertIsNone(final["eval_count"])
        self.assertEqual(final["eval_count_status"], "NOT_REPORTED_BY_UPSTREAM")
        self.assertGreaterEqual(final["total_duration"], 0)
        self.assertEqual("".join(f["message"]["content"] for f in frames
                                 if f.get("message") and f["message"]["content"]),
                         "Два фрагмента")

    def test_1a02_conversation_id_cursor_reconciles_stream_and_snapshot(self):
        """A client-visible conversation identifier must not be lost or coerced."""
        chat = next(route.endpoint for route in self.app.routes if route.path == "/api/chat")
        snapshot = next(route.endpoint for route in self.app.routes if route.path == "/api/chat/snapshot")
        original = {"request_id": "conversation-cursor-request-01",
                    "exchange_id": "conversation-cursor-exchange-01",
                    "mini": True, "use_memory": False,
                    "messages": [{"role": "user", "content": "Привет, NOX"}]}
        async def scenario():
            invalid = (None, True, 7, {}, [], "", "a b", "x" * 129, "\\ud800")
            for value in invalid:
                response = await chat(Request({**original, "conversation_id": value}))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.body)["reason"], "CHAT_INVALID_CONVERSATION_ID")
            response = await chat(Request({**original, "conversation_id": "resonance-thread-01"}))
            first = json.loads(await response.body_iterator.__anext__())
            row = await snapshot(first["stream_id"], first["request_id"],
                                 original["exchange_id"])
            saved = json.loads(row.body)
            wrong = await snapshot(first["stream_id"], first["request_id"],
                                   "different-exchange")
            invalid = await snapshot(first["stream_id"], first["request_id"], "bad exchange")
            self.assertEqual(wrong.status_code, 409)
            self.assertEqual(json.loads(wrong.body)["reason"], "CHAT_SNAPSHOT_EXCHANGE_MISMATCH")
            self.assertNotIn("message", json.loads(wrong.body))
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(json.loads(invalid.body)["reason"], "CHAT_SNAPSHOT_INVALID_EXCHANGE_ID")
            await response.body_iterator.aclose()
            legacy = await chat(Request({**original, "request_id": "legacy-no-cursor-01",
                                         "exchange_id": "legacy-exchange-01"}))
            legacy_first = json.loads(await legacy.body_iterator.__anext__())
            await legacy.body_iterator.aclose()
            return first, saved, legacy_first
        with (mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CANCEL", set())):
            first, saved, legacy_first = asyncio.run(scenario())
            self.assertEqual(W.ACTIVE_CHAT_IDS, set())
        self.assertEqual(first["conversation_id"], "resonance-thread-01")
        self.assertEqual(first["exchange_id"], original["exchange_id"])
        self.assertEqual(saved["conversation_id"], first["conversation_id"])
        self.assertEqual(saved["exchange_id"], first["exchange_id"])
        self.assertEqual(saved["event_seq"], first["event_seq"])
        self.assertEqual(saved["snapshot_integrity"], "PARTIAL")
        self.assertFalse(saved["s03_readback_verified"])
        self.assertNotIn("conversation_id", legacy_first)

    def test_3a02_s03_context_lookup_fail_closed_before_model(self):
        """A missing canonical context must not produce invented continuity."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        calls = []
        bridge.hc = lambda: calls.append("model")  # never reached
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: calls.append("write")

        async def run_case(idx):
            response = await chat(Request({
                "request_id": "s03-read-hold-" + str(idx),
                "use_memory": True,
                "messages": [{"role": "user", "content": "Продолжи наш разговор"}],
            }))
            return [json.loads(x) async for x in response.body_iterator]

        with (mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "W", None),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            for idx, outcome in enumerate(("raises", "nontext")):
                if outcome == "raises":
                    bridge.memory_block = mock.Mock(side_effect=RuntimeError("S03 offline"))
                else:
                    bridge.memory_block = mock.Mock(return_value={"wrong": "shape"})
                frames = asyncio.run(run_case(idx))
                self.assertEqual(frames[-1]["status"], "HOLD")
                self.assertEqual(frames[-1]["reason"], "S03_MEMORY_LOOKUP_FAILED")
                self.assertFalse(frames[-1]["done"])
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "HOLD")
                self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
                self.assertFalse(frames[-1]["memory_history"]["s03_readback_verified"])
        self.assertEqual(calls, [])
        self.assertEqual(len(bridge.errors), 2)

    def test_0a03_malformed_chat_never_starts_stream_or_memory(self):
        # Real FastAPI route callback; all cases return before the model/S03
        # generator is created. No fake successful stream receipt.
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        cases = (
            (None, "CHAT_INVALID_BODY"),
            (["not", "a", "dict"], "CHAT_INVALID_BODY"),
            ({"messages": ["not-a-message"]}, "CHAT_INVALID_MESSAGES"),
            # Unknown/missing roles must not silently vanish from history.
            ({"messages": [{"role": "system", "content": "Do not drop this"}]}, "CHAT_INVALID_ROLE"),
            ({"messages": [{"content": "missing explicit role"}, {"role": "user", "content": "Ответь"}]}, "CHAT_INVALID_ROLE"),
            ({"messages": [{"role": "tool", "content": {"result": "x"}}, {"role": "user", "content": "Ответь"}]}, "CHAT_INVALID_ROLE"),
            ({"messages": [{"role": "user", "content": {"unsafe": True}}]}, "CHAT_INVALID_CONTENT"),
            ({"messages": [{"role": "user", "content": "\ud800"}]}, "CHAT_INVALID_UNICODE"),
            ({"messages": [{"role": "user", "content": "ж" * (W.MAX_CHAT_INPUT_UTF8_BYTES // 2 + 1)}]}, "CHAT_INPUT_TOO_LARGE"),
            ({"mini": True, "messages": [{"role": "user", "content": "a" * 3001}]}, "MINI_INPUT_TOO_LONG"),
            ({"messages": [{"role": "user", "content": "ok"}] * (W.MAX_CHAT_INPUT_MESSAGES + 1)}, "CHAT_INPUT_TOO_MANY_MESSAGES"),
            # Malformed privacy flags previously silently changed the caller's
            # requested S03 persistence / recall / mini mode semantics.
            ({"ephemeral": "true", "messages": [{"role": "user", "content": "private"}]}, "CHAT_INVALID_BOOLEAN_FLAG"),
            ({"ephemeral": 0, "messages": [{"role": "user", "content": "private"}]}, "CHAT_INVALID_BOOLEAN_FLAG"),
            ({"use_memory": "false", "messages": [{"role": "user", "content": "no recall"}]}, "CHAT_INVALID_BOOLEAN_FLAG"),
            ({"mini": None, "messages": [{"role": "user", "content": "mini"}]}, "CHAT_INVALID_BOOLEAN_FLAG"),
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
            # A reconnect/retry caller must append a NEW user turn. Never
            # reinterpret a historical user turn as new when assistant is last.
            ({"messages": [{"role": "user", "content": "Уже отвечено"},
                           {"role": "assistant", "content": "Готово"}]}, "CHAT_LAST_MESSAGE_NOT_USER"),
            ({"messages": [{"role": "user", "content": "Вопрос"},
                           {"role": "assistant", "content": "Ответ"},
                           {"role": "assistant", "content": "Продолжение"}]}, "CHAT_LAST_MESSAGE_NOT_USER"),
            ({"messages": [{"role": "assistant", "content": "only response"}]}, "CHAT_MISSING_USER"),
            ({"messages": [{"role": "user", "content": "   "}]}, "CHAT_MISSING_USER"),
        )
        for body, code in cases:
            with self.subTest(body=body):
                response = asyncio.run(chat(Request(body)))
                self.assertEqual(response.status_code, 400)
                payload = json.loads(response.body)
                if code == "CHAT_INVALID_BOOLEAN_FLAG":
                    self.assertEqual(payload, {"status": "HOLD", "reason": code,
                                               "flag": next(f for f in
                                               ("ephemeral", "use_memory", "mini")
                                               if f in body)})
                else:
                    self.assertEqual(payload, {"status": "HOLD", "reason": code})

    def test_1v14_01_raw_chat_wire_bound_before_model_or_s03(self):
        """Reject oversized headers and chunked bodies without parsing or admission."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")

        class WireRequest:
            def __init__(self, chunks, declared=None):
                self.chunks = chunks
                self.headers = {} if declared is None else {"content-length": declared}

            async def stream(self):
                for chunk in self.chunks:
                    yield chunk

            async def json(self):
                raise AssertionError("real ASGI wire path must not call json()")

        async def scenario():
            header = await chat(WireRequest([b'{}'], "65"))
            chunked = await chat(WireRequest([b'a' * 40, b'b' * 25]))
            bad_length = await chat(WireRequest([b'{}'], "-1"))
            malformed = await chat(WireRequest([b'{"messages":']))
            duplicate_request = await chat(WireRequest([b'{"request_id":"A","request_id":"B"}']))
            duplicate_nested = await chat(WireRequest([b'{"options":{"mode":"fast","mode":"slow"}}']))
            nonfinite = await chat(WireRequest([b'{"options":{"num_predict":NaN}}']))
            return header, chunked, bad_length, malformed, duplicate_request, duplicate_nested, nonfinite

        with (mock.patch.object(W, "MAX_CHAT_WIRE_BYTES", 64),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {})):
            (header, chunked, bad_length, malformed,
             duplicate_request, duplicate_nested, nonfinite) = asyncio.run(scenario())
            self.assertEqual(W.ACTIVE_CHAT_IDS, set())
            self.assertEqual(W.CHAT_SNAPSHOTS, {})
        for response in (header, chunked):
            self.assertEqual(response.status_code, 413)
            self.assertEqual(json.loads(response.body),
                             {"status": "HOLD", "reason": "CHAT_WIRE_TOO_LARGE"})
        self.assertEqual(bad_length.status_code, 400)
        self.assertEqual(json.loads(bad_length.body)["reason"], "CHAT_INVALID_CONTENT_LENGTH")
        for invalid in (malformed, duplicate_request, duplicate_nested, nonfinite):
            with self.subTest(body=invalid.body):
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(json.loads(invalid.body),
                                 {"status": "HOLD", "reason": "CHAT_INVALID_JSON"})

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
            # Force a snapshot-specific budget exhaustion after admission.
            # The actual SSE is still able to finish, but a reconnect must
            # never reconstruct incomplete bytes as GENERATED or S03-proven.
            overflow = await chat(request("snap-overflow"))
            first_overflow = json.loads(await overflow.body_iterator.__anext__())
            W.CHAT_SNAPSHOTS[first_overflow["stream_id"]]["text_bytes"] = W.MAX_CHAT_OUTPUT_UTF8_BYTES
            overflow_tail = [json.loads(part) async for part in overflow.body_iterator]
            held = await snapshot(stream_id=first_overflow["stream_id"], request_id="snap-overflow")
            return frames, finished, wrong, partial, unavailable, overflow_tail, held

        with (mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.object(W, "W", None),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            frames, finished, wrong, partial, unavailable, overflow_tail, held = asyncio.run(scenario())
        self.assertEqual(finished.status_code, 200)
        saved = json.loads(finished.body)
        self.assertEqual(saved["message"]["content"], "Привет 🌌")
        self.assertEqual(saved["snapshot_utf8_bytes"], len("Привет 🌌".encode("utf-8")))
        self.assertEqual(saved["snapshot_sha256"], frames[-1]["digest"])
        self.assertTrue(saved["terminal_digest_verified"])
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
        self.assertTrue(any(frame.get("done") for frame in overflow_tail))
        self.assertEqual(held.status_code, 200)
        unsafe_snapshot = json.loads(held.body)
        self.assertEqual(unsafe_snapshot["status"], "HOLD")
        self.assertEqual(unsafe_snapshot["snapshot_integrity"], "HOLD")
        self.assertEqual(unsafe_snapshot["snapshot_hold_reason"], "CHAT_SNAPSHOT_TEXT_OVERFLOW")
        self.assertFalse(unsafe_snapshot["done"])
        self.assertIsNone(unsafe_snapshot["completion_receipt"])
        self.assertIsNone(unsafe_snapshot["memory_write_receipt"])
        self.assertFalse(unsafe_snapshot["s03_readback_verified"])
        self.assertEqual(len(writes), 2)

    def test_6a04_invalid_vram_census_is_not_spare_capacity(self):
        """Reject a bad GPU sample rather than report fabricated spare VRAM."""
        def sample(output):
            with mock.patch.object(W.subprocess, "run",
                                   return_value=types.SimpleNamespace(stdout=output)):
                return W._gpu()

        valid = ("0, 20, 1024, 32768, 58, 90\n"
                 "1, 10, 0, 32768, 53, 80")
        self.assertEqual(len(sample(valid)), 2)
        # Even a malformed second GPU invalidates the whole two-GPU census.
        for bad in ("-1, 32768", "32769, 32768", "NaN, 32768",
                    "0, Infinity", "0, 0", "1e309, 32768"):
            with self.subTest(vram=bad):
                self.assertEqual(sample("0, 20, 1024, 32768, 58, 90\n"
                                        "1, 10, " + bad + ", 53, 80"), [])

    def test_1a03_stopped_snapshot_must_not_claim_complete_recovery(self):
        """A terminal STOP is not a completed model turn or canonical S03 proof."""
        snapshot = next(r.endpoint for r in self.app.routes
                        if r.path == "/api/chat/snapshot")
        stream_id = "a" * 32
        request_id = "stop-snapshot"
        row = {
            "request_id": request_id, "event_seq": 3,
            "text_chunks": ["Частичный 🌌"], "state": "STOPPED",
            "terminal": True, "updated_at": W.time.monotonic(),
            "completion_receipt": {"status": "STOPPED", "upstream_done": False},
            "memory_write_receipt": {"status": "SKIPPED"},
            "snapshot_hold_reason": None,
        }
        with mock.patch.object(W, "CHAT_SNAPSHOTS", {stream_id: row}):
            stopped = json.loads(asyncio.run(snapshot(
                stream_id=stream_id, request_id=request_id)).body)
            self.assertTrue(stopped["done"])
            self.assertEqual(stopped["status"], "STOPPED")
            self.assertEqual(stopped["snapshot_integrity"], "PARTIAL")
            self.assertFalse(stopped["s03_readback_verified"])
            row["state"], row["terminal"] = "INTERRUPTED", False
            interrupted = json.loads(asyncio.run(snapshot(
                stream_id=stream_id, request_id=request_id)).body)
            self.assertEqual(interrupted["snapshot_integrity"], "PARTIAL")
            row["state"], row["terminal"] = "GENERATED", True
            row["terminal_digest"] = W.hashlib.sha256("Частичный 🌌".encode("utf-8")).hexdigest()
            completed = json.loads(asyncio.run(snapshot(
                stream_id=stream_id, request_id=request_id)).body)
            self.assertEqual(completed["snapshot_integrity"], "COMPLETE")
            self.assertTrue(completed["terminal_digest_verified"])
            self.assertFalse(completed["s03_readback_verified"])
            # Corrupted/reordered snapshot bytes must never inherit an older
            # terminal GENERATED or S03 receipt even when terminal=True.
            row["text_chunks"] = ["Частичный 🌌", " подмена"]
            mismatch = json.loads(asyncio.run(snapshot(
                stream_id=stream_id, request_id=request_id)).body)
            self.assertEqual(mismatch["status"], "HOLD")
            self.assertEqual(mismatch["snapshot_integrity"], "HOLD")
            self.assertEqual(mismatch["snapshot_hold_reason"], "CHAT_SNAPSHOT_DIGEST_MISMATCH")
            self.assertFalse(mismatch["done"])
            self.assertFalse(mismatch["terminal_digest_verified"])
            self.assertIsNone(mismatch["completion_receipt"])
            self.assertIsNone(mismatch["memory_write_receipt"])

    def test_0a03_s03_persists_exact_streamed_unicode_and_whitespace(self):
        """Successful canonical writer call receives exact SSE text, not stripped text."""
        import hashlib
        reply = "  Привет 🌌\n"
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "  Привет 🌌"}}]}, ensure_ascii=False)
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "\n"}}]}, ensure_ascii=False)
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        bridge.hc = lambda: Client()
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")

        async def scenario():
            response = await chat(Request({
                "request_id": "a3-exact-unicode-whitespace", "mini": True,
                "use_memory": False, "messages": [
                    {"role": "user", "content": "Проверь сохранение Unicode"}
                ]}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        with (mock.patch.object(W, "W", None),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            frames = asyncio.run(scenario())
        streamed = "".join(frame.get("message", {}).get("content", "") for frame in frames)
        self.assertEqual(streamed, reply)
        self.assertEqual(writes, [("[mini] Проверь сохранение Unicode", reply)])
        self.assertEqual(frames[-1]["digest"], hashlib.sha256(reply.encode()).hexdigest())
        self.assertTrue(frames[-1]["done"])
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_1a03_snapshot_ttl_not_extended_by_wall_clock_rollback(self):
        """A backward wall-clock jump must never retain chat snapshots past TTL."""
        snapshots = {
            "expired": {"updated_at": 300.0},
            "fresh": {"updated_at": 499.0},
        }
        # Ten minutes of monotonic time have passed, but system time jumps
        # backward. The cache is a privacy-limited process-local buffer.
        with (mock.patch.object(W, "CHAT_SNAPSHOTS", snapshots),
              mock.patch.object(W.time, "monotonic", return_value=500.0),
              mock.patch.object(W.time, "time", return_value=-9999999.0)):
            W._prune_chat_snapshots()
        self.assertNotIn("expired", snapshots)
        self.assertIn("fresh", snapshots)

    def test_1a02_completed_request_retry_cannot_duplicate_s03_turn(self):
        """A recent request ID is one non-ephemeral generation, not a new S03 write."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        writes, model_calls = [], []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class Upstream:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"готово"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                model_calls.append(1)
                return Upstream()

        bridge.hc = lambda: Client()
        body = {"request_id": "stable-req-1a02", "exchange_id": "stable-ex-1a02",
                "mini": True, "use_memory": False,
                "messages": [{"role": "user", "content": "Проверка повторного POST"}]}

        async def scenario():
            first = await chat(Request(body))
            # A second request ID cannot sidestep an admitted exchange, even
            # before the first response produces its initial SSE frame.
            changed_id = dict(body, request_id="other-request-same-exchange")
            in_flight = await chat(Request(changed_id))
            in_flight_status = in_flight.status_code
            first_frames = [json.loads(x) async for x in first.body_iterator]
            second = await chat(Request(body))
            second_status = second.status_code
            second_body = json.loads(second.body)
            after_done = await chat(Request(changed_id))
            after_done_status = after_done.status_code
            changed_exchange = await chat(Request(
                dict(body, exchange_id="different-exchange-1a02")))
            changed_exchange_status = changed_exchange.status_code
            changed_exchange_body = json.loads(changed_exchange.body)
            # TTL/eviction is deliberately NOT durable idempotency. Once the
            # bounded entry expires, a new request may be admitted again.
            W.CHAT_SNAPSHOTS[first_frames[0]["stream_id"]]["updated_at"] = (
                W.time.monotonic() - W.CHAT_SNAPSHOT_TTL_S - 1)
            third = await chat(Request(body))
            third_frames = [json.loads(x) async for x in third.body_iterator]
            unstarted_body = dict(body, request_id="aborted-before-first-frame",
                                  exchange_id="aborted-exchange")
            unstarted = await chat(Request(unstarted_body))
            await unstarted.body_iterator.aclose()
            readmitted = await chat(Request(unstarted_body))
            was_readmitted = hasattr(readmitted, "body_iterator")
            if was_readmitted:
                await readmitted.body_iterator.aclose()
            return (first_frames, in_flight_status, second_status,
                    second_body, after_done_status, changed_exchange_status,
                    changed_exchange_body, third_frames, was_readmitted)

        with (mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "W", None),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            (first_frames, in_flight_status, status, rejected,
             after_done_status, changed_exchange_status, changed_exchange_body,
             third_frames, was_readmitted) = asyncio.run(scenario())
        self.assertTrue(first_frames[-1]["done"])
        self.assertEqual(in_flight_status, 409)
        self.assertEqual(status, 409)
        self.assertEqual(after_done_status, 409)
        self.assertEqual(changed_exchange_status, 409)
        self.assertEqual(changed_exchange_body, {
            "status": "HOLD", "reason": "CHAT_REQUEST_ID_REUSED_ACROSS_EXCHANGES",
            "retry_same_id": False, "snapshot_scope": "PROCESS_LOCAL",
            "s03_readback_verified": False,
        })
        self.assertEqual(rejected, {
            "status": "HOLD", "reason": "CHAT_EXCHANGE_RECENTLY_USED",
            "retry_same_id": False, "snapshot_scope": "PROCESS_LOCAL",
            "s03_readback_verified": False,
        })
        self.assertTrue(third_frames[-1]["done"])
        self.assertTrue(was_readmitted)  # no frame, no model call or S03 write
        self.assertEqual(len(model_calls), 2)
        self.assertEqual(len(writes), 2)

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

    def test_1a01_required_web_premodel_failure_has_terminal_hold(self):
        """No silent SSE EOF or fake S03 success when self-state/prompt fails."""
        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        self.bridge.SOUL = None
        self.bridge.LAST_CHAT = {"t": 0}
        self.bridge.NKEEP = 0
        self.bridge.memory_block = lambda user: "S03 memory available"
        model_attempts, writes = [], []
        self.bridge.hc = lambda: model_attempts.append("POST")
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        def fail(*_args):
            raise RuntimeError("synthetic required premodel failure")

        async def collect(request_id):
            response = await chat(Request({
                "request_id": request_id, "mini": False, "use_memory": True,
                "messages": [{"role": "user", "content": "Продолжи с S03"}],
            }))
            return [json.loads(frame) async for frame in response.body_iterator]

        with (mock.patch.object(W, "W", None),
              mock.patch.object(W, "CANCEL", set()),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            for phase in ("self_vol", "build_msgs"):
                with self.subTest(phase=phase):
                    if phase == "self_vol":
                        self.bridge.self_vol = fail
                        self.bridge.build_msgs = lambda *_: [{"role": "user", "content": "unused"}]
                    else:
                        self.bridge.self_vol = lambda _: ""
                        self.bridge.build_msgs = fail
                    rid = "web-premodel-hold-" + phase
                    frames = asyncio.run(collect(rid))
                    last = frames[-1]
                    self.assertEqual(last["status"], "HOLD")
                    self.assertEqual(last["reason"], "PREMODEL_CONTEXT_UNAVAILABLE")
                    self.assertFalse(last["done"])
                    self.assertFalse(last["completion_receipt"]["upstream_done"])
                    self.assertEqual(last["completion_receipt"]["status"], "HOLD")
                    self.assertEqual(last["memory_write_receipt"]["status"], "SKIPPED")
                    self.assertFalse(last["memory_history"]["s03_readback_verified"])
                    self.assertEqual(model_attempts, [])
                    self.assertEqual(writes, [])
                    self.assertNotIn(rid, W.ACTIVE_CHAT_IDS)
        self.assertEqual(len(self.bridge.errors), 2)

    def test_1a01_adaptive_hint_failure_does_not_drop_live_sse_or_s03(self):
        """An optional output-budget helper cannot strand a real chat turn."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        bridge.SOUL = None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Вопрос"}]
        seen = []

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                seen.append(kwargs["json"]["max_tokens"])
                return Upstream()

        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def collect(idx):
            response = await chat(Request({
                "request_id": "adapt-hint-failure-" + str(idx), "mode": "auto",
                "use_memory": False, "messages": [{"role": "user", "content": "Вопрос"}],
            }))
            return [json.loads(part) async for part in response.body_iterator]

        with (mock.patch.object(W, "W", None),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            for idx, hint in enumerate((RuntimeError("helper offline"), None, float("nan"), True)):
                with self.subTest(idx=idx):
                    def adaptive(*args, _hint=hint):
                        if isinstance(_hint, Exception):
                            raise _hint
                        return _hint
                    bridge.adapt_tokens = adaptive
                    frames = asyncio.run(collect(idx))
                    last = frames[-1]
                    self.assertTrue(last["done"])
                    self.assertEqual(last["completion_receipt"]["status"], "GENERATED")
                    self.assertEqual(last["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                    self.assertFalse(last["memory_write_receipt"]["s03_readback_verified"])
                    self.assertTrue(all(frame.get("status") != "HOLD" for frame in frames))
                    self.assertEqual(writes[-1][1], "Ответ 🌌")
                    self.assertNotIn("adapt-hint-failure-" + str(idx), W.ACTIVE_CHAT_IDS)
        self.assertEqual(seen, [700] * 4)
        self.assertEqual(len(writes), 4)
        self.assertEqual(len(bridge.errors), 4)

    def test_1a01_explicit_low_num_predict_is_not_raised_to_64(self):
        """A validated small completion ceiling must reach the actual model call."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Вопрос"}]
        bridge.adapt_tokens = lambda *args: 900
        posted_limits, persisted = [], []

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ок"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                posted_limits.append(kwargs["json"]["max_tokens"])
                return Upstream()

        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: persisted.append(args)
        cases = ((False, "auto", 1), (False, "auto", 63),
                 (False, "auto", 64), (False, "auto", 700),
                 (False, "fast", 1), (True, "auto", 1))

        async def collect(index, mini, mode, ceiling):
            response = await chat(Request({
                "request_id": "low-ceiling-" + str(index),
                "mini": mini, "mode": mode, "use_memory": False,
                "options": {"num_predict": ceiling},
                "messages": [{"role": "user", "content": "Вопрос"}],
            }))
            return [json.loads(frame) async for frame in response.body_iterator]

        with (mock.patch.object(W, "W", None),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            for index, (mini, mode, ceiling) in enumerate(cases):
                frames = asyncio.run(collect(index, mini, mode, ceiling))
                self.assertTrue(frames[-1]["done"])
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"],
                                 "WRITE_RETURNED_UNVERIFIED")
                self.assertNotIn("low-ceiling-" + str(index), W.ACTIVE_CHAT_IDS)
        self.assertEqual(posted_limits, [1, 63, 64, 700, 1, 1])
        self.assertEqual(len(persisted), len(cases))

    def test_1v14_01_ephemeral_turn_does_not_persist_emotional_signal(self):
        """Private chat keeps the real model stream, but never updates affect."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT = {"t": 0}
        bridge.self_vol = mock.Mock(side_effect=AssertionError(
            "ephemeral text must not update persistent PAD"))
        vol_seen = []
        def build(messages, user, mem, vol, extra=""):
            vol_seen.append(vol)
            return [{"role": "user", "content": user + "\\n" + vol}]
        bridge.build_msgs = build
        bridge.adapt_tokens = lambda *_: 700
        memory = types.ModuleType("s03_memory")
        saved = []
        memory.persist_turn = lambda *args: saved.append(args)

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Частный ответ 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()
        bridge.hc = lambda: Client()

        async def scenario():
            response = await chat(Request({
                "request_id": "private-pad-isolation", "ephemeral": True,
                "use_memory": False,
                "messages": [{"role": "user", "content": "Мой приватный вопрос"}],
            }))
            return [json.loads(part) async for part in response.body_iterator]

        with (mock.patch.object(W, "W", None),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {}),
              mock.patch.dict(sys.modules, {"s03_memory": memory})):
            frames = asyncio.run(scenario())
            self.assertNotIn("private-pad-isolation", W.ACTIVE_CHAT_IDS)
            self.assertEqual(W.CHAT_SNAPSHOTS, {})
        self.assertTrue(frames[-1]["done"])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(frames[-1]["memory_history"]["status"], "SKIPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])
        self.assertEqual(saved, [])
        bridge.self_vol.assert_not_called()
        self.assertEqual(len(vol_seen), 1)
        self.assertIn("не обновляется", vol_seen[0])
        self.assertNotIn("Мой приватный вопрос", vol_seen[0])

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

    def test_3a03_missing_source_reference_never_claims_s03_readback(self):
        """A stale/unknown local source ID must not look like a found fact."""
        endpoint = next(r.endpoint for r in self.app.routes if r.path == "/api/s03/record")
        with mock.patch.object(W, "SRC", {"1": "контекст S03", "2": ""}):
            missing = asyncio.run(endpoint("999"))
            blank = asyncio.run(endpoint("2"))
            hit = asyncio.run(endpoint("1"))
        for response in (missing, blank):
            self.assertEqual(response.status_code, 404)
            row = json.loads(response.body)
            self.assertEqual(row["status"], "HOLD")
            self.assertEqual(row["reason"], "S03_SOURCE_NOT_FOUND")
            self.assertFalse(row["s03_readback_verified"])
            self.assertNotIn("content", row)
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(hit.status_code, 200)
        row = json.loads(hit.body)
        self.assertEqual(row["status"], "OK")
        self.assertEqual(row["content"], "контекст S03")
        self.assertEqual(row["source_scope"], "PROCESS_LOCAL")
        self.assertFalse(row["s03_readback_verified"])
        self.assertEqual(hit.headers["cache-control"], "no-store")

    def test_0a03_local_history_and_facts_are_not_canonical_s03(self):
        # All values come from process-local JSONL, not independent S03.
        history = next(r.endpoint for r in self.app.routes if r.path == "/api/nox/history")
        facts = next(r.endpoint for r in self.app.routes
                     if r.path == "/api/nox/memory/facts" and "GET" in r.methods)

        def local_tail(path, limit):
            if str(path).endswith("/turns.jsonl"):
                return [{"t": 10, "u": "Привет 🌌", "a": "Помню"}]
            if str(path) == str(self.fact_path):
                return [{"t": 11, "key": "owner", "content": "Запомни", "source": "owner"}]
            return []

        with mock.patch.object(W, "_jl", side_effect=local_tail), mock.patch.object(W, "W", None):
            h = asyncio.run(history())
            f = asyncio.run(facts(limit=20))
        self.assertEqual(h.status_code, 200)
        self.assertEqual(f.status_code, 200)
        for response in (h, f):
            self.assertEqual(response.headers["cache-control"], "private, no-store, max-age=0")
            self.assertFalse(json.loads(response.body)["s03_readback_verified"])
        h_body = json.loads(h.body)
        self.assertEqual(h_body["source_scope"], "LOCAL_TURNS_MIRROR")
        self.assertEqual(h_body["messages"], [
            {"role": "user", "content": "Привет 🌌"},
            {"role": "assistant", "content": "Помню"}])
        f_body = json.loads(f.body)
        self.assertEqual(f_body["source_scope"], "AUXILIARY_LOCAL_MIRRORS")
        facts_by_kind = {row["kind"]: row for row in f_body["facts"]}
        self.assertEqual(facts_by_kind["dialog_turn"]["provenance"], "LOCAL_TURNS_MIRROR")
        self.assertEqual(facts_by_kind["owner_fact"]["source_scope"], "LOCAL_FACTS_MIRROR")
        self.assertFalse(facts_by_kind["dialog_turn"]["s03_readback_verified"])
        self.assertFalse(facts_by_kind["owner_fact"]["s03_readback_verified"])

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

    def test_explicit_false_fact_write_fails_closed_without_mirror(self):
        m = types.ModuleType("s03_memory")
        calls = []
        def reject(*args):
            calls.append(args)
            return False
        m.persist_turn = reject
        res = self.invoke(m)
        self.assertEqual(res.status_code, 503)
        row = json.loads(res.body)
        self.assertEqual(row["reason"], "S03_PERSIST_REJECTED")
        self.assertEqual(row["status"], "HOLD")
        self.assertFalse(row["saved"])
        self.assertFalse(row["s03_write_returned"])
        self.assertFalse(row["retry_safe"])
        self.assertFalse(row["s03_readback_verified"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.fact_path.exists())

    def test_successful_s03_call_remains_unverified_without_readback(self):
        m = types.ModuleType("s03_memory")
        calls = []
        m.persist_turn = lambda *a: calls.append(a)
        res = self.invoke(m)
        self.assertEqual(res["status"], "RECORDED_UNVERIFIED")
        self.assertTrue(res["saved"])
        self.assertTrue(res["s03_write_returned"])
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
        # The S03 writer already returned; the failed secondary JSONL mirror
        # cannot authorize replay of the same user fact.
        self.assertFalse(row["saved"])
        self.assertTrue(row["s03_write_returned"])
        self.assertFalse(row["retry_safe"])
        self.assertFalse(row["s03_readback_verified"])


    def test_s03_fact_admission_rejects_ambiguous_input_before_persistence(self):
        """Malformed JSON, structured content, truncation and unsafe Unicode HOLD."""
        m = types.ModuleType("s03_memory")
        writes = []
        m.persist_turn = lambda *args: writes.append(args)
        cases = (
            (None, "S03_FACT_INVALID_BODY"),
            ([], "S03_FACT_INVALID_BODY"),
            ({"content": None}, "S03_FACT_INVALID_CONTENT"),
            ({"content": False}, "S03_FACT_INVALID_CONTENT"),
            ({"content": {"value": "wrong"}}, "S03_FACT_INVALID_CONTENT"),
            ({"content": ["wrong"]}, "S03_FACT_INVALID_CONTENT"),
            ({"content": "   "}, "пустой факт"),
            ({"content": "A" * 2001}, "S03_FACT_TOO_LONG"),
            ({"content": "A\x00B"}, "S03_FACT_INVALID_UNICODE"),
            ({"content": "A\ud800B"}, "S03_FACT_INVALID_UNICODE"),
        )
        with mock.patch.dict(sys.modules, {"s03_memory": m}):
            for body, reason in cases:
                with self.subTest(reason=reason, body_type=type(body).__name__):
                    result = asyncio.run(self.endpoint(Request(body)))
                    self.assertEqual(result.status_code, 400)
                    data = json.loads(result.body)
                    self.assertEqual(data["reason"], reason)
                    self.assertEqual(data["status"], "HOLD")
                    self.assertFalse(data["saved"])
                    self.assertFalse(data["s03_readback_verified"])

            class MalformedJSON:
                async def json(self):
                    raise ValueError("bad JSON")

            result = asyncio.run(self.endpoint(MalformedJSON()))
            self.assertEqual(result.status_code, 400)
            self.assertEqual(json.loads(result.body)["reason"], "S03_FACT_INVALID_JSON")

        self.assertEqual(writes, [])
        self.assertFalse(self.fact_path.exists())

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
                if self.error_event == "named":
                    # A bare named SSE error must not be ignored just because
                    # the provider later sends a valid stop and [DONE].
                    yield 'event: error'
                elif self.error_event:
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
            (True, 429, None, False, None, False),
            (True, 502, None, False, None, False),
            (True, 504, None, False, None, False),
            (True, 200, "length", False, None, False),
            (True, 200, None, True, None, False),
            (True, 200, "stop", "named", None, False),
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
                    if status != 200:
                        expected = {429: "UPSTREAM_RATE_LIMIT", 502: "UPSTREAM_GATEWAY",
                                    503: "UPSTREAM_UNAVAILABLE", 504: "UPSTREAM_TIMEOUT"}
                        self.assertEqual(frames[-1]["upstream_hold_code"], expected[status])
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

        # A provider may accidentally send the terminal stop twice. This is
        # not a canonical completed turn, even when [DONE] later arrives.
        class DuplicateStopUpstream(Upstream):
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class DuplicateStopClient:
            def stream(self, *args, **kwargs):
                return DuplicateStopUpstream(True, 200, "stop")

        writes.clear()
        bridge.errors.clear()
        bridge.hc = lambda: DuplicateStopClient()
        with mock.patch.dict(sys.modules, {"s03_memory": module}), mock.patch.object(W, "W", None):
            duplicate_frames = asyncio.run(get_frames())
        self.assertEqual(writes, [])
        self.assertFalse(any(v.get("done") is True for v in duplicate_frames))
        self.assertEqual(duplicate_frames[-1]["status"], "HOLD")
        self.assertEqual(duplicate_frames[-1]["reason"], "MODEL_STREAM_INCOMPLETE")
        self.assertEqual(duplicate_frames[-1]["upstream_hold_code"], "UPSTREAM_DUPLICATE_STOP_FINISH")
        self.assertEqual(duplicate_frames[-1]["memory_write_receipt"]["status"], "SKIPPED")

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
            # Exactly one choice still carries an identity: a nonzero or
            # non-integral index cannot be silently written as choice zero.
            '{"choices":[{"index":1,"delta":{},"finish_reason":"stop"}]}',
            '{"choices":[{"index":false,"delta":{},"finish_reason":"stop"}]}',
            '{"choices":[{"index":"0","delta":{},"finish_reason":"stop"}]}',
            # A text-only model reply cannot silently omit a hidden tool call
            # or accept a provider frame with the wrong speaker role.
            '{"choices":[{"delta":{"tool_calls":[{"id":"call-1","type":"function"}]},"finish_reason":"stop"}]}',
            '{"choices":[{"delta":{"function_call":{"name":"do_action"}},"finish_reason":"stop"}]}',
            '{"choices":[{"delta":{"role":"tool"},"finish_reason":"stop"}]}',
            '{"choices":[{"delta":{"role":"assistant"},"finish_reason":"stop"}],"tool_calls":[{"id":"ignored"}]}',
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
                                    "UPSTREAM_CHOICES_INVALID" in error or
                                    "UPSTREAM_UNSUPPORTED_DELTA" in error
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
        # A syntactically complete [DONE] with no wire-line delimiter is
        # still a truncated SSE record, never canonical S03 acceptance.
        with self.assertRaisesRegex(ValueError, "UPSTREAM_SSE_UNTERMINATED_LINE"):
            asyncio.run(lines(b'data: [DONE]'))
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
            good_prefix + b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
                        + b'data: [DONE]',
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

        for verdict, expected_ok, suffix in (
            (RuntimeError("verifier unavailable"), None, ""),
            (["invalid", "verdict"], None, ""),
            ({"ok": 1, "doubt": "wrong boolean"}, None, ""),
            ({"ok": True}, True, ""),
            # Valid decisions can carry unsafe incidental metadata from a plugin.
            # It must never reach terminal SSE or suppress an S03 persistence.
            ({"ok": True, "debug": object()}, True, ""),
            ({"ok": False, "doubt": "сомнение", "debug": object()},
             False, "\n\n⚠ Скептик: сомнение"),
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
                self.assertEqual(writes, [("Вопрос", "Ответ модели" + suffix)])
                if isinstance(verdict, dict) and "debug" in verdict:
                    self.assertNotIn("debug", terminal["skeptic"])
                self.assertEqual(terminal["skeptic"]["ok"], expected_ok)
                if expected_ok is None:
                    self.assertEqual(terminal["skeptic"]["reason"], "SKEPTIC_UNAVAILABLE")
                    self.assertTrue(any("проверка недоступна" in
                        str(f.get("nox_event", {}).get("text", "")) for f in frames))
                self.assertFalse(any(f.get("status") == "HOLD" for f in frames))

    def test_optional_factual_classifier_failure_keeps_completed_answer(self):
        """1A01: a failed optional classifier cannot erase DONE or skip S03."""
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
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            def is_factual(self, *args):
                raise RuntimeError("classifier unavailable")
            async def skeptic(self, *args, **kwargs):
                raise AssertionError("no second model on classifier failure")

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT, bridge.SOUL = 0, {"t": 0}, None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Вопрос"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def collect():
            response = await chat(Request({
                "mode": "auto", "use_memory": False,
                "messages": [{"role": "user", "content": "Вопрос"}]}))
            return [json.loads(chunk) async for chunk in response.body_iterator]

        with mock.patch.object(W, "W", Thinking()), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(collect())
        self.assertEqual(writes, [("Вопрос", "Ответ")])
        self.assertTrue(frames[-1]["done"])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertIsNone(frames[-1]["skeptic"])
        self.assertFalse(any(f.get("status") == "HOLD" for f in frames))

    def test_1v14_stop_on_premodel_status_skips_persistent_affect(self):
        """A STOP on the final premodel SSE frame cannot write user-derived PAD."""
        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        rid = "a2-stop-before-affect"
        bridge = self.bridge
        bridge.SOUL = None
        bridge.self_vol = mock.Mock(side_effect=AssertionError(
            "cancelled user text must not reach persistent affect journal"))
        bridge.build_msgs = mock.Mock(side_effect=AssertionError(
            "cancelled turn must not assemble model prompt"))
        bridge.hc = mock.Mock(side_effect=AssertionError(
            "cancelled turn must not make model POST"))
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = mock.Mock(side_effect=AssertionError(
            "cancelled turn must not write S03"))

        async def scenario():
            response = await chat(Request({
                "request_id": rid, "mode": "fast", "use_memory": False,
                "messages": [{"role": "user", "content": "STOP before affect"}],
            }))
            frames = []
            async for wire in response.body_iterator:
                frame = json.loads(wire)
                frames.append(frame)
                if frame.get("nox_event", {}).get("text") == "формулирую ответ":
                    W.CANCEL.add(rid)
            return frames

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.object(W, "W", None), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(scenario())
            self.assertEqual(W.ACTIVE_CHAT_IDS, set())
        self.assertTrue(any(f.get("nox_event", {}).get("text") == "формулирую ответ"
                            for f in frames))
        self.assertTrue(frames[-1]["done"])
        self.assertEqual(frames[-1]["done_reason"], "stopped")
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])
        bridge.self_vol.assert_not_called()
        bridge.build_msgs.assert_not_called()
        bridge.hc.assert_not_called()
        memory.persist_turn.assert_not_called()

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


    def test_1a04_stop_on_memory_source_prevents_reminder_side_effect(self):
        """A STOP on the memory SSE frame cannot create a reminder or invoke GPU."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")
        bridge = self.bridge
        bridge.LAST_CHAT, bridge.NKEEP = {"t": 0}, 0
        model_calls, reminders, writes = [], [], []
        bridge.hc = lambda: model_calls.append("main-model")
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class Thinking:
            def maybe_reminder(self, *args):
                reminders.append("created")
                return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""

        rid = "stop-before-reminder-side-effect"
        async def scenario():
            response = await chat(Request({
                "request_id": rid, "mode": "fast", "use_memory": False,
                "messages": [{"role": "user", "content": "Поставь напоминание"}],
            }))
            frames, signal = [], None
            async for item in response.body_iterator:
                frame = json.loads(item)
                frames.append(frame)
                if "nox_sources" in frame:
                    signal = await stop(Request({
                        "scope": "generation", "request_id": rid}))
            return frames, signal

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "W", Thinking()), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames, signal = asyncio.run(scenario())
        self.assertEqual(signal["status"], "STOPPING")
        self.assertEqual(reminders, [])
        self.assertEqual(model_calls, [])
        self.assertEqual(writes, [])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "STOPPED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "SKIPPED")
        self.assertFalse(frames[-1]["completion_receipt"]["upstream_done"])

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
                return {"ok": False, "doubt": "Не должно появиться после STOP"}

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
        visible = "".join(f.get("message", {}).get("content", "") for f in frames)
        self.assertEqual(visible, "Ответ")
        self.assertEqual(frames[-1]["skeptic"], {"ok": None, "reason": "SKEPTIC_STOPPED"})
        self.assertEqual(sum(f.get("nox_event", {}).get("step") == "check" for f in frames), 1)
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

        for write_outcome in ("raise", "reject", "return_none"):
            with self.subTest(write_outcome=write_outcome):
                mirror_calls.clear()
                bridge.errors.clear()

                def persist(*args):
                    if write_outcome == "raise":
                        raise RuntimeError("S03 unavailable")
                    if write_outcome == "reject":
                        return False
                    return None

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
                if write_outcome != "return_none":
                    self.assertEqual(terminal["memory_history"]["status"], "HOLD")
                    self.assertTrue(terminal["memory_write_receipt"]["retry_unsafe"])
                    self.assertEqual(mirror_calls, [])
                    self.assertFalse(any("soul_secondary_log_error" in e for e in bridge.errors))
                    if write_outcome == "reject":
                        self.assertEqual(terminal["memory_history"]["reason"], "S03_PERSIST_REJECTED")
                        self.assertFalse(terminal["memory_write_receipt"]["s03_write_returned"])
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

    def test_1a01_corrupt_optional_reminder_cannot_abort_real_chat(self):
        """Invalid reminder metadata is no substitute for actual model/S03 output."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Живой ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Reminder:
            def __init__(self, result): self.result = result
            def maybe_reminder(self, *args): return self.result
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            def is_factual(self, *args): return False

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Привет"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario(idx):
            response = await chat(Request({
                "request_id": "bad-reminder-advisory-" + str(idx),
                "mode": "fast", "use_memory": False,
                "messages": [{"role": "user", "content": "Привет"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        cases = (
            "corrupt",
            {"reminder": None},
            {"reminder": {"due": None}},
            {"reminder": {"due": "tomorrow"}},
            {"reminder": {"due": float("nan")}},
            {"reminder": {"due": float("inf")}},
            {"reminder": {"due": True}},
            {"reminder": {"due": 10**100}},
            # Valid due but invalid sidecar payload: old fr() advanced the
            # event counter before JSON encoding raised, losing a cursor.
            {"reminder": {"due": 1760000000, "corrupt": {"not-serializable"}}},
            {"reminder": {"due": 1760000000}},
        )
        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            for idx, result in enumerate(cases):
                with self.subTest(idx=idx), mock.patch.object(W, "W", Reminder(result)):
                    frames = asyncio.run(scenario(idx))
                # No phantom SSE cursor or snapshot event from a suppressed
                # advisory serialization error: stream remains gap-free.
                self.assertEqual([f["event_seq"] for f in frames],
                                 list(range(1, len(frames) + 1)))
                self.assertEqual(W.CHAT_SNAPSHOTS[frames[0]["stream_id"]]["event_seq"],
                                 len(frames))
                self.assertTrue(any(f.get("message", {}).get("content") == "Живой ответ" for f in frames))
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                reminders = [f for f in frames if f.get("nox_event", {}).get("step") == "reminder"]
                self.assertEqual(len(reminders), 1 if idx == len(cases) - 1 else 0)
        self.assertEqual(writes, [("Привет", "Живой ответ")] * len(cases))

    def test_1a01_optional_planner_and_mode_hint_fail_open_to_real_stream(self):
        """An advisory planner outage cannot replace real tokens with HTTP 500."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Живой ответ 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class BrokenOptionalDecorators:
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): raise RuntimeError("planner unavailable")
            def mode_hint(self, *args): raise ValueError("hint formatter unavailable")
            def is_factual(self, *args): return False

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Привет"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario():
            response = await chat(Request({
                "request_id": "plan-advisory-outage",
                "mode": "auto", "use_memory": False,
                "messages": [{"role": "user", "content": "Привет"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.object(W, "W", BrokenOptionalDecorators()), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(scenario())

        self.assertTrue(any(frame.get("message", {}).get("content") == "Живой ответ 🌌" for frame in frames))
        terminal = frames[-1]
        self.assertTrue(terminal["done"])
        self.assertEqual(terminal["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(terminal["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
        self.assertEqual(writes, [("Привет", "Живой ответ 🌌")])
        self.assertTrue(any("web_plan_classifier_unavailable RuntimeError" in msg for msg in bridge.errors))
        self.assertTrue(any("web_mode_hint_unavailable ValueError" in msg for msg in bridge.errors))

    def test_1a01_optional_mode_hint_strict_utf8_budget_keeps_real_chat(self):
        """Untrusted advisory hints never break a real model/S03 turn."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Живой ответ 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Hint:
            def __init__(self, value): self.value = value
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return self.value
            def is_factual(self, *args): return False

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.self_vol = lambda user: ""
        model_contexts = []
        def build_msgs(*args):
            model_contexts.append(args[-1])
            return [{"role": "user", "content": "Привет"}]
        bridge.build_msgs = build_msgs
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def attempt(number):
            response = await chat(Request({
                "request_id": "hint-budget-" + str(number),
                "mode": "auto", "use_memory": False,
                "messages": [{"role": "user", "content": "Привет"}],
            }))
            return [json.loads(frame) async for frame in response.body_iterator]

        # 512 four-byte Unicode scalars meet the 2048-byte boundary;
        # lone surrogate and 2049+ bytes must discard ONLY the hint.
        cases = (("\ud800", True), ("🚀" * 513, True), ("🧠" * 512, False))
        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            for idx, (value, invalid) in enumerate(cases):
                bridge.errors.clear()
                with mock.patch.object(W, "W", Hint(value)):
                    frames = asyncio.run(attempt(idx))
                self.assertTrue(frames[-1]["done"])
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"],
                                 "WRITE_RETURNED_UNVERIFIED")
                self.assertTrue(any(f.get("message", {}).get("content") == "Живой ответ 🌌"
                                    for f in frames))
                if invalid:
                    self.assertEqual(model_contexts[-1], "")
                    self.assertTrue(any("web_mode_hint_unavailable" in e
                                        for e in bridge.errors))
                else:
                    self.assertIn(value, model_contexts[-1])
                    self.assertFalse(any("web_mode_hint_unavailable" in e
                                         for e in bridge.errors))
        self.assertEqual(writes, [("Привет", "Живой ответ 🌌")] * len(cases))

    def test_1a01_malformed_optional_plan_keeps_real_stream_and_s03_attempt(self):
        """Bad advisory plan payload must never abort the primary SSE stream."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Живой ответ 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class BadPlan:
            def __init__(self, payload): self.payload = payload
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return True
            async def make_plan(self, *args): return self.payload
            def mode_hint(self, *args): return ""
            def is_factual(self, *args): return False

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Привет"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario(idx):
            response = await chat(Request({
                "request_id": f"bad-plan-{idx}", "mode": "plan", "use_memory": False,
                "messages": [{"role": "user", "content": "Привет"}],
            }))
            return [json.loads(row) async for row in response.body_iterator]

        bad_payloads = (
            ["valid", {"unserializable": object()}],
            ["surrogate \\ud800".replace("\\ud800", "\ud800")],
            ["x" * 101],
            {"wrong": "shape"},
        )
        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            for idx, payload in enumerate(bad_payloads):
                with self.subTest(idx=idx), mock.patch.object(W, "W", BadPlan(payload)):
                    frames = asyncio.run(scenario(idx))
                self.assertTrue(any(f.get("message", {}).get("content") == "Живой ответ 🌌" for f in frames))
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"], "WRITE_RETURNED_UNVERIFIED")
                self.assertFalse(any(f.get("nox_event", {}).get("plan") for f in frames))
        self.assertEqual(writes, [("Привет", "Живой ответ 🌌")] * len(bad_payloads))
        self.assertEqual(sum("web_plan_result_unavailable" in e for e in bridge.errors),
                         len(bad_payloads))

    def test_1a01_optional_s03_provenance_failure_keeps_real_model_and_write(self):
        """Malformed advisory provenance must never abort a valid S03-backed answer."""
        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Ответ сохранён 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Optional:
            def __init__(self, outcome): self.outcome = outcome
            def provenance(self, line):
                if self.outcome == "error":
                    raise RuntimeError("owner metadata offline")
                return {"source": "WRONG", "id": 999, "provenance": "OWNER",
                        "origin": object()}
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return False
            def mode_hint(self, *args): return ""
            def is_factual(self, *args): return False

        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.memory_block = lambda user: "S03: проверенный контекст"
        bridge.self_vol = lambda user: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Продолжай"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        writes = []
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario(idx):
            response = await chat(Request({
                "request_id": "provenance-fallback-" + str(idx),
                "use_memory": True,
                "messages": [{"role": "user", "content": "Продолжай"}],
            }))
            return [json.loads(part) async for part in response.body_iterator]

        with mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.object(W, "CANCEL_ALL_EPOCH", 0), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            for idx, outcome in enumerate(("error", "invalid")):
                with mock.patch.object(W, "W", Optional(outcome)):
                    frames = asyncio.run(scenario(idx))
                sources = next(f["nox_sources"] for f in frames if "nox_sources" in f)
                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0]["source"], "S03")
                self.assertEqual(sources[0]["id"], 1)
                self.assertEqual(sources[0]["provenance"], "UNVERIFIED")
                self.assertEqual(sources[0]["origin"], "s03")
                self.assertTrue(any(f.get("message", {}).get("content") == "Ответ сохранён 🌌"
                                    for f in frames))
                self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
                self.assertEqual(frames[-1]["memory_write_receipt"]["status"],
                                 "WRITE_RETURNED_UNVERIFIED")
        self.assertEqual(writes, [("Продолжай", "Ответ сохранён 🌌")] * 2)
        self.assertEqual(sum("web_memory_provenance_unavailable" in err
                             for err in bridge.errors), 2)

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

    def test_1a04_stop_wire_rejects_oversize_and_ambiguous_requests(self):
        """Real ASGI STOP admission is bounded, including chunked wire bodies."""
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")

        class WireRequest:
            def __init__(self, chunks, declared=None):
                self.chunks = chunks
                self.headers = {} if declared is None else {"content-length": declared}

            async def stream(self):
                for chunk in self.chunks:
                    yield chunk

            async def json(self):
                raise AssertionError("STOP must not eagerly parse unbounded wire input")

        async def scenario():
            oversized_header = await stop(WireRequest([b'{}'], "65"))
            oversized_chunked = await stop(WireRequest([b' ' * 48, b' ' * 17]))
            bad_length = await stop(WireRequest([b'{}'], "-2"))
            duplicate_scope = await stop(WireRequest([
                b'{"scope":"generation","scope":"owner","request_id":"*"}'
            ]))
            duplicate_target = await stop(WireRequest([
                b'{"scope":"generation","request_id":"a","request_id":"*"}'
            ]))
            nonfinite = await stop(WireRequest([
                b'{"scope":"generation","request_id":"*","debug":NaN}'
            ]))
            valid = await stop(WireRequest([
                b'{"scope":"generation","request_id":"live-1"}'
            ]))
            return (oversized_header, oversized_chunked, bad_length,
                    duplicate_scope, duplicate_target, nonfinite, valid)

        with (mock.patch.object(W, "MAX_STOP_WIRE_BYTES", 64),
              mock.patch.object(W, "CANCEL", set()),
              mock.patch.object(W, "CANCEL_ALL_EPOCH", 0)):
            out = asyncio.run(scenario())
            self.assertEqual(W.CANCEL_ALL_EPOCH, 0)
            self.assertEqual(W.CANCEL, {"live-1"})
        self.assertEqual([x.status_code for x in out[:6]], [413, 413, 400, 400, 400, 400])
        self.assertEqual([json.loads(x.body)["reason"] for x in out[:6]],
                         ["STOP_WIRE_TOO_LARGE", "STOP_WIRE_TOO_LARGE",
                          "STOP_INVALID_CONTENT_LENGTH", "STOP_INVALID_JSON",
                          "STOP_INVALID_JSON", "STOP_INVALID_JSON"])
        self.assertEqual(out[6]["status"], "STOPPING")
        self.assertEqual(out[6]["target_request_id"], "live-1")
        self.assertFalse(out[6]["stop_confirmed"])

    def test_1a04_stop_signal_receipt_does_not_claim_idle_work_stopped(self):
        """A queued unknown ID, a live ID and broadcast have distinct truthful ACKs."""
        stop = next(r.endpoint for r in self.app.routes if r.path == "/api/chat/stop")

        async def scenario():
            pending = await stop(Request({"scope": "generation", "request_id": "unknown"}))
            admitted = await stop(Request({"scope": "generation", "request_id": "real-a"}))
            broadcast = await stop(Request({"scope": "generation", "request_id": "*"}))
            return pending, admitted, broadcast

        with (mock.patch.object(W, "CANCEL", set()),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", {"real-a", "real-b"}),
              mock.patch.object(W, "CANCEL_ALL_EPOCH", 0)):
            pending, admitted, broadcast = asyncio.run(scenario())
            self.assertEqual(W.CANCEL, {"unknown", "real-a"})
            self.assertEqual(W.CANCEL_ALL_EPOCH, 1)

        for item in (pending, admitted, broadcast):
            self.assertEqual(item["status"], "STOPPING")
            self.assertFalse(item["stop_confirmed"])
            self.assertEqual(item["scope"], "generation")
            self.assertFalse(item["owner_stop"])
            self.assertFalse(item["media_stopped"])
            self.assertFalse(item["task_cancelled"])
        self.assertEqual((pending["active_requests_at_signal"], pending["signal_receipt"]),
                         (0, "PENDING_UNKNOWN_REQUEST_ID"))
        self.assertEqual((admitted["active_requests_at_signal"], admitted["signal_receipt"]),
                         (1, "ADMITTED_REQUEST_SIGNALLED"))
        self.assertEqual((broadcast["active_requests_at_signal"], broadcast["signal_receipt"]),
                         (2, "BROADCAST_EPOCH_SET"))

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


    def test_1a01_many_small_sse_deltas_reconstruct_exact_s03_answer(self):
        """Long live token streams retain exact ordered UTF-8, receipt and S03."""
        expected = "Ж🌌" * 700
        fragments = ["Ж", "🌌"] * 700
        captured = []

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                for part in fragments:
                    yield 'data: ' + json.dumps(
                        {"choices": [{"delta": {"content": part}}]},
                        ensure_ascii=False)
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs):
                captured.append(kwargs["json"])
                return Upstream()

        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        snapshot = next(route.endpoint for route in self.app.routes
                        if route.path == "/api/chat/snapshot")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.LAST_CHAT, bridge.SOUL = {"t": 0}, None
        bridge.hc = lambda: Client()
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario():
            response = await chat(Request({
                "request_id": "many-deltas-utf8", "mini": True,
                "use_memory": False,
                "messages": [{"role": "user", "content": "Продолжай"}],
            }))
            frames = [json.loads(frame) async for frame in response.body_iterator]
            sid = frames[0]["stream_id"]
            snap = await snapshot(stream_id=sid, request_id="many-deltas-utf8")
            row = W.CHAT_SNAPSHOTS[sid]
            return (frames, json.loads(snap.body),
                    len(row.get("text_chunks", [])), "text" in row)

        with mock.patch.object(W, "W", None), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames, saved, chunks, retained_legacy_text = asyncio.run(scenario())
        self.assertEqual(saved["message"]["content"], expected)
        self.assertEqual(saved["event_seq"], len(frames))
        self.assertEqual(saved["snapshot_integrity"], "COMPLETE")
        self.assertFalse(saved["s03_readback_verified"])
        self.assertEqual(chunks, len(fragments))
        self.assertFalse(retained_legacy_text)
        self.assertEqual("".join(f.get("message", {}).get("content", "")
                                 for f in frames), expected)
        self.assertEqual(captured[0]["stream"], True)
        self.assertEqual(writes, [("[mini] Продолжай", expected)])
        terminal = frames[-1]
        self.assertTrue(terminal["done"])
        self.assertEqual(terminal["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(terminal["memory_write_receipt"]["status"],
                         "WRITE_RETURNED_UNVERIFIED")
        self.assertEqual(terminal["digest"],
                         W.hashlib.sha256(expected.encode("utf-8")).hexdigest())



    def test_1a01_long_multiline_plan_stream_keeps_progress_and_s03_exact(self):
        """Incremental plan progress must not lose tokens or repeat step events."""
        expected = "1. Начало 🌌\n2. Итог\n" + "Примечание\n" * 600
        fragments = ["1. Начало 🌌\n", "2. Итог\n"] + ["Примечание\n"] * 600
        writes = []

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                for part in fragments:
                    yield "data: " + json.dumps(
                        {"choices": [{"delta": {"content": part}}]},
                        ensure_ascii=False)
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        class Planner:
            def maybe_reminder(self, *args): return None
            def wants_plan(self, *args): return True
            async def make_plan(self, *args, **kwargs): return ["Начало", "Итог"]
            def mode_hint(self, *args): return ""
            def is_factual(self, *args): return False

        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        bridge = self.bridge
        bridge.NKEEP, bridge.LAST_CHAT, bridge.SOUL = 0, {"t": 0}, None
        bridge.self_vol = lambda *args: ""
        bridge.build_msgs = lambda *args: [{"role": "user", "content": "Шаги"}]
        bridge.adapt_tokens = lambda *args: 300
        bridge.hc = lambda: Client()
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        async def scenario():
            response = await chat(Request({
                "request_id": "linear-plan-progress",
                "use_memory": False,
                "messages": [{"role": "user", "content": "Дай два шага"}],
            }))
            return [json.loads(f) async for f in response.body_iterator]

        with mock.patch.object(W, "W", Planner()), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            frames = asyncio.run(scenario())

        progress = [f["nox_event"]["index"] for f in frames
                    if f.get("nox_event", {}).get("step") == "plan"
                    and "index" in f["nox_event"]]
        self.assertEqual(progress, [1, 2])
        self.assertEqual("".join(f.get("message", {}).get("content", "")
                                 for f in frames), expected)
        self.assertEqual(writes, [("Дай два шага", expected)])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(frames[-1]["memory_write_receipt"]["status"],
                         "WRITE_RETURNED_UNVERIFIED")
        self.assertFalse(frames[-1]["memory_write_receipt"]["s03_readback_verified"])
        self.assertEqual(frames[-1]["digest"],
                         W.hashlib.sha256(expected.encode("utf-8")).hexdigest())



    def test_0a03_real_bridge_recall_failure_and_cache_generation_fence(self):
        """A failed S03 recall cannot masquerade as no memories; stale reads cannot refill cache."""
        # Import bridge with startup warmers disabled; never touch a real host.
        # The lean source gate installs fastapi/httpx but not uvicorn.
        # Stub the server runner only; the actual bridge logic is imported.
        with mock.patch.object(W.threading.Thread, "start"), \
             mock.patch.object(W.os.path, "isdir", return_value=False), \
             mock.patch.dict(sys.modules, {"uvicorn": types.ModuleType("uvicorn")}):
            import nox_bridge as bridge
        memory = types.ModuleType("s03_memory")
        calls = []
        memory.recall = lambda q: calls.append(q) or ["source"]
        memory.format_for_prompt = lambda rows: "S03 remembers important context"
        with mock.patch.dict(sys.modules, {"s03_memory": memory}), \
             mock.patch.object(bridge, "_RC", {}), \
             mock.patch.object(bridge, "_RC_GENERATION", 0), \
             mock.patch.object(bridge, "_trivial", return_value=False):
            first = bridge.memory_block("первый вопрос")
            self.assertEqual(first, "S03 remembers important context")
            self.assertEqual(bridge.memory_block("первый вопрос"), first)
            self.assertEqual(len(calls), 1)
            bridge.invalidate_s03_cache()
            self.assertEqual(bridge.memory_block("первый вопрос"), first)
            self.assertEqual(len(calls), 2)

            def concurrent_recall(q):
                # Simulate an S03 write completing while recall is in flight.
                bridge.invalidate_s03_cache()
                return ["old-version"]

            memory.recall = concurrent_recall
            with self.assertRaisesRegex(RuntimeError, "S03_MEMORY_CHANGED_DURING_LOOKUP"):
                bridge.memory_block("второй вопрос")
            self.assertNotIn(
                bridge.hashlib.md5("второй вопрос".encode()).hexdigest(), bridge._RC)

            # If only one write intervenes, discard the first recalled text
            # and return the newer generation instead of an obsolete prompt.
            generations = []
            def revoke_once(q):
                generations.append(q)
                if len(generations) == 1:
                    bridge.invalidate_s03_cache()
                    return ["obsolete-source-version"]
                return ["fresh-source-version"]

            memory.recall = revoke_once
            memory.format_for_prompt = lambda rows: rows[0]
            self.assertEqual(bridge.memory_block("третий вопрос"), "fresh-source-version")
            self.assertEqual(len(generations), 2)

            memory.recall = lambda q: ["invalid-output"]
            memory.format_for_prompt = lambda rows: {"not": "text"}
            with self.assertRaisesRegex(RuntimeError, "S03_MEMORY_LOOKUP_FAILED"):
                bridge.memory_block("память неверного типа")

            memory.recall = mock.Mock(side_effect=OSError("private S03 unavailable"))
            with self.assertRaisesRegex(RuntimeError, "S03_MEMORY_LOOKUP_FAILED"):
                bridge.memory_block("нужна память")
            self.assertNotIn(
                bridge.hashlib.md5("нужна память".encode()).hexdigest(), bridge._RC)

    def test_3a03_ambiguous_s03_write_revokes_cached_recall_without_retry(self):
        """A canonical S03 write may commit before an exception or False return."""
        chat = next(r.endpoint for r in self.app.routes if r.path == "/api/chat")
        bridge = self.bridge
        bridge.IDENTITY, bridge.STATIC_RULES, bridge.NKEEP = "", "", 0
        bridge.invalidate_s03_cache = mock.Mock()
        events = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: events.append(args)

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Готово 🌌"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        bridge.hc = lambda: Client()

        async def run_one(rid):
            response = await chat(Request({
                "request_id": rid, "mini": True, "use_memory": False,
                "messages": [{"role": "user", "content": "Проверь S03"}]}))
            return [json.loads(line) async for line in response.body_iterator]

        with mock.patch.object(W, "W", None), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            ok = asyncio.run(run_one("cache-write-returned"))
            self.assertTrue(ok[-1]["done"])
            self.assertEqual(ok[-1]["memory_write_receipt"]["status"],
                             "WRITE_RETURNED_UNVERIFIED")
            self.assertFalse(ok[-1]["memory_write_receipt"]["s03_readback_verified"])
            bridge.invalidate_s03_cache.assert_called_once_with()
            self.assertEqual(events, [("[mini] Проверь S03", "Готово 🌌")])

            memory.persist_turn = mock.Mock(side_effect=OSError("S03 write failed"))
            held = asyncio.run(run_one("cache-write-failed"))
            self.assertEqual(held[-1]["memory_write_receipt"]["status"], "HOLD")
            self.assertFalse(held[-1]["memory_write_receipt"]["s03_write_returned"])
            self.assertTrue(held[-1]["memory_write_receipt"]["retry_unsafe"])
            self.assertEqual(bridge.invalidate_s03_cache.call_count, 2)
            # Even an explicit rejection could follow an actual S03 commit.
            # Do not leave cached old recall alive or retry the writer.
            memory.persist_turn = mock.Mock(return_value=False)
            rejected = asyncio.run(run_one("cache-write-rejected"))
            self.assertEqual(rejected[-1]["memory_history"]["reason"], "S03_PERSIST_REJECTED")
            self.assertEqual(rejected[-1]["memory_write_receipt"]["status"], "HOLD")
            self.assertTrue(rejected[-1]["memory_write_receipt"]["retry_unsafe"])
            self.assertFalse(rejected[-1]["memory_write_receipt"]["s03_write_returned"])
            self.assertFalse(rejected[-1]["memory_write_receipt"]["s03_readback_verified"])
            self.assertEqual(bridge.invalidate_s03_cache.call_count, 3)

            # A completed write followed by cache-revocation failure is not a
            # failed/absent write. The user must not retry the same turn blindly.
            memory.persist_turn = lambda *args: events.append(args)
            bridge.invalidate_s03_cache = mock.Mock(
                side_effect=RuntimeError("cache generation unavailable"))
            stale = asyncio.run(run_one("cache-revoke-failed"))
            receipt = stale[-1]["memory_write_receipt"]
            self.assertEqual(receipt["status"], "HOLD")
            self.assertTrue(receipt["s03_write_returned"])
            self.assertTrue(receipt["retry_unsafe"])
            self.assertFalse(receipt["s03_readback_verified"])
            self.assertEqual(stale[-1]["memory_history"]["reason"],
                             "S03_CACHE_INVALIDATION_FAILED")
            self.assertEqual(stale[-1]["memory_history"]["status"], "HOLD")
            self.assertEqual(events[-1], ("[mini] Проверь S03", "Готово 🌌"))
            self.assertEqual(len(events), 2)



    def test_6a05_transport_holds_are_specific_and_never_replayed(self):
        """An uncertain model POST returns a bounded cause and never writes S03."""
        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        self.bridge.IDENTITY, self.bridge.STATIC_RULES = "", ""
        self.bridge.NKEEP, self.bridge.LAST_CHAT = 0, {"t": 0}
        self.bridge.SOUL = None
        writes, posts = [], []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class FailedUpstream:
            def __init__(self, failure):
                self.failure = failure

            async def __aenter__(self):
                raise self.failure

            async def __aexit__(self, *args):
                return False

        class Client:
            def __init__(self, failure):
                self.failure = failure

            def stream(self, *args, **kwargs):
                posts.append(1)
                return FailedUpstream(self.failure)

        async def attempt(index):
            response = await chat(Request({
                "request_id": "transport-failure-" + str(index),
                "mini": True, "use_memory": False,
                "messages": [{"role": "user", "content": "Ответь"}],
            }))
            return [json.loads(frame) async for frame in response.body_iterator]

        failures = (
            (W.httpx.ReadTimeout("upstream timed out"), "UPSTREAM_TIMEOUT"),
            (W.httpx.ReadError("socket closed"), "UPSTREAM_NETWORK"),
            (W.httpx.RemoteProtocolError("bad framing"), "UPSTREAM_PROTOCOL"),
            (RuntimeError("unexpected error"), "UPSTREAM_NOT_COMPLETE"),
        )
        with mock.patch.object(W, "W", None), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            for index, (failure, expected) in enumerate(failures):
                self.bridge.hc = lambda failure=failure: Client(failure)
                frames = asyncio.run(attempt(index))
                terminal = frames[-1]
                self.assertEqual(terminal["status"], "HOLD")
                self.assertEqual(terminal["reason"], "MODEL_STREAM_INCOMPLETE")
                self.assertEqual(terminal["upstream_hold_code"], expected)
                self.assertFalse(terminal["done"])
                self.assertEqual(terminal["completion_receipt"]["status"], "HOLD")
                self.assertEqual(terminal["memory_write_receipt"]["status"], "SKIPPED")
                self.assertFalse(terminal["memory_history"]["s03_readback_verified"])
        self.assertEqual(len(posts), len(failures), "no ambiguous POST replay")
        self.assertEqual(writes, [], "transport failure cannot persist partial S03")



    def test_1a01_mini_chat_preserves_main_s03_source_links(self):
        """A mini turn must not wipe the main Resonance's local source cursor."""
        chat = next(route.endpoint for route in self.app.routes
                    if route.path == "/api/chat")
        record = next(route.endpoint for route in self.app.routes
                      if route.path == "/api/s03/record")
        self.bridge.IDENTITY, self.bridge.STATIC_RULES = "", ""
        self.bridge.NKEEP, self.bridge.LAST_CHAT = 0, {"t": 0}
        self.bridge.SOUL = None
        self.bridge.hc = lambda: Client()
        writes = []
        memory = types.ModuleType("s03_memory")
        memory.persist_turn = lambda *args: writes.append(args)

        class Upstream:
            status_code = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Мини ответ"}}]}'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield 'data: [DONE]'

        class Client:
            def stream(self, *args, **kwargs): return Upstream()

        async def scenario():
            before = await record("1")
            response = await chat(Request({
                "request_id": "mini-preserve-main-sources",
                "mini": True, "use_memory": False,
                "messages": [{"role": "user", "content": "Запиши заметку"}],
            }))
            frames = [json.loads(f) async for f in response.body_iterator]
            after = await record("1")
            return json.loads(before.body), frames, json.loads(after.body)

        with mock.patch.object(W, "SRC", {"1": "Проверенная ссылка из основного чата"}), \
             mock.patch.object(W, "W", None), \
             mock.patch.object(W, "CANCEL", set()), \
             mock.patch.object(W, "ACTIVE_CHAT_IDS", set()), \
             mock.patch.object(W, "CHAT_SNAPSHOTS", {}), \
             mock.patch.dict(sys.modules, {"s03_memory": memory}):
            before, frames, after = asyncio.run(scenario())
            self.assertEqual(W.SRC, {"1": "Проверенная ссылка из основного чата"})
        self.assertEqual(before["status"], "OK")
        self.assertEqual(after["status"], "OK")
        self.assertEqual(after["content"], before["content"])
        self.assertFalse(after["s03_readback_verified"])
        self.assertEqual(frames[-1]["completion_receipt"]["status"], "GENERATED")
        self.assertEqual(writes, [("[mini] Запиши заметку", "Мини ответ")])


if __name__ == "__main__":
    unittest.main()
