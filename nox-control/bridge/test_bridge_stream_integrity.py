"""Offline integrity tests for the actual NOX bridge SSE generator.

Extract only stream_chat's AST to avoid service boot, network, GPU, and S03
side effects. All history/memory callbacks are controlled test doubles.
"""
import ast
import asyncio
import json
from pathlib import Path
import time
import unittest


SOURCE = (Path(__file__).with_name("nox_bridge.py")).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTION = next(n for n in TREE.body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "stream_chat")
CODE = compile(ast.fix_missing_locations(ast.Module(body=[FUNCTION], type_ignores=[])),
               filename="nox_bridge.py", mode="exec")


class FakeResponse:
    def __init__(self, lines, status=200):
        self.lines = lines
        self.status_code = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            if isinstance(line, Exception):
                raise line
            yield line


class BridgeStreamIntegrity(unittest.TestCase):
    def run_stream(self, lines, status=200, write_ok=True,
                   memory_error=False, soul_error=False,
                   vol_error=False, affect_error=False, write_raises=False,
                   token_hint=64, byte_chunks=None):
        writes, soul_logs, notices = [], [], []
        response = FakeResponse(lines, status)
        if byte_chunks is not None:
            async def raw_bytes(chunk_size=4096):
                for chunk in byte_chunks:
                    if isinstance(chunk, Exception):
                        raise chunk
                    yield chunk
            response.aiter_bytes = raw_bytes
        class Client:
            def stream(self, *_args, **_kwargs):
                return response

        def write(user, answer):
            writes.append((user, answer))
            if write_raises:
                raise RuntimeError("S03_WRITE_RETURN_LOST")
            return write_ok

        class Soul:
            def log_turn(self, *args):
                if soul_error:
                    raise RuntimeError("SOUL_LOG_FAULT")
                soul_logs.append(args)

        def recall(_text):
            if memory_error:
                raise RuntimeError("S03_RECALL_FAULT")
            return ""

        def self_state(_text):
            if vol_error:
                raise RuntimeError("SELF_STATE_FAULT")
            return ""

        def affect(_text):
            if affect_error:
                raise RuntimeError("AFFECT_FAULT")
            return {}

        scope = {
            "asyncio": asyncio,
            "json": json,
            "time": time,
            "hc": Client,
            "MODEL": "http://127.0.0.1/test-only",
            "NKEEP": 0,
            "_sse": lambda payload: "data: " + json.dumps(payload) + "\n\n",
            "memory_block": recall,
            "self_vol": self_state,
            "affect_update": affect,
            "affect_words": lambda _: "steady",
            "build_msgs": lambda *_: [],
            "adapt_tokens": (lambda _: (_ for _ in ()).throw(token_hint)
                             if isinstance(token_hint, Exception) else token_hint),
            "remember": write,
            "SOUL": Soul(),
            "LAST_CHAT": {"t": 0},
            "log": notices.append,
        }
        exec(CODE, scope)

        async def collect():
            return [json.loads(raw.removeprefix("data: ").strip())
                    async for raw in scope["stream_chat"]([{"role":"user","content":"Привет"}])]
        return asyncio.run(collect()), writes, soul_logs, scope["LAST_CHAT"]

    @staticmethod
    def chunk(text=None, finish=None):
        return "data: " + json.dumps({
            "choices": [{"delta": {"content": text} if text is not None else {},
                         "finish_reason": finish}]
        }) 

    def test_legacy_chat_admission_fails_closed_without_truncating_valid_history(self):
        # Exercise the actual FastAPI endpoint AST without importing or
        # starting serving modules, model traffic, or canonical S03.
        import copy
        import types
        fn = copy.deepcopy(next(n for n in TREE.body
                                if isinstance(n, ast.AsyncFunctionDef)
                                and n.name == "chat_stream"))
        fn.decorator_list = []
        code = compile(ast.fix_missing_locations(
            ast.Module(body=[fn], type_ignores=[])), "nox_bridge.py", "exec")
        admission = []
        class Response:
            def __init__(self, data, status_code=200):
                self.data, self.status_code = data, status_code
        class Stream:
            def __init__(self, result, **kwargs):
                admission.append((result, kwargs))
        env = {"json": json, "CH": None, "Request": object, "JSONResponse": Response,
               "StreamingResponse": Stream,
               "stream_chat": lambda msgs: msgs}
        exec(code, env)
        class RequestDouble:
            def __init__(self, payload, header=None):
                self.payload = payload
                self.headers = header or {}
            async def stream(self):
                for chunk in self.payload:
                    yield chunk
        def invoke(payload, header=None):
            return asyncio.run(env["chat_stream"](RequestDouble(payload, header)))
        for payload, why in (
                ([b"null"], "CHAT_INVALID_MESSAGES"),
                ([b"[]"], "CHAT_INVALID_MESSAGES"),
                ([b"{not json}"], "CHAT_INVALID_JSON"),
                # Last-key-wins JSON must never rewrite a client history.
                ([b'{"messages":[],"messages":[{"role":"user","content":"overridden"}]}'], "CHAT_INVALID_JSON"),
                ([b'{"messages":[{"role":"user","content":"safe","content":"overridden"}]}'], "CHAT_INVALID_JSON"),
                ([b'{"messages":[{"role":"user","content":"safe","meta":NaN}]}'], "CHAT_INVALID_JSON"),
                ([b'{"messages":[{"role":"user","content":"safe","meta":Infinity}]}'], "CHAT_INVALID_JSON"),
                ([b'{"messages":{}}'], "CHAT_INVALID_MESSAGES"),
                ([b'{"messages":[{"role":"user","content":3}]}'], "CHAT_INVALID_MESSAGES"),
                ([b'{"messages":[{"role":"assistant","content":"only"}]}'], "CHAT_MISSING_USER"),
                # Prior completed exchange cannot accidentally replay the old
                # user prompt and attempt a duplicate S03 write.
                ([b'{"messages":[{"role":"user","content":"old"},{"role":"assistant","content":"done"}]}'], "CHAT_LAST_USER_REQUIRED"),
                ([b'{"messages":[{"role":"user","content":"old"},{"role":"assistant","content":"done"},{"role":"user","content":"   "}]}'], "CHAT_LAST_USER_REQUIRED"),
                ([b'{"messages":[{"role":"user","content":"\\ud800"}]}'], "CHAT_INVALID_UNICODE")):
            with self.subTest(payload=payload):
                result = invoke(payload)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.data["reason"], why)
        huge = invoke([b"x" * (2*1024*1024), b"x"])
        self.assertEqual(huge.status_code, 413)
        self.assertEqual(huge.data["reason"], "CHAT_WIRE_TOO_LARGE")
        self.assertFalse(admission)
        full = [{"role":"user", "content":"И" * 2400},
                {"role":"assistant", "content":"ok"},
                {"role":"user", "content":"Что дальше? 🌍"}]
        good = invoke([json.dumps({"messages":full}, ensure_ascii=False).encode("utf-8")])
        self.assertIsInstance(good, Stream)
        self.assertEqual(admission[-1][0], full)
        self.assertEqual(admission[-1][1]["headers"]["Cache-Control"],
                         "private, no-store, max-age=0")

    def test_nonstream_history_replay_cannot_reach_model_or_s03(self):
        # The legacy JSON route shares the same safe admission constraints as
        # SSE; an assistant-tail replay must be denied before smart()/memory.
        import copy
        from types import SimpleNamespace
        node = copy.deepcopy(next(n for n in TREE.body
                                  if isinstance(n, ast.AsyncFunctionDef)
                                  and n.name == "chat"))
        node.decorator_list = []
        code = compile(ast.fix_missing_locations(
            ast.Module(body=[node], type_ignores=[])), "nox_bridge.py", "exec")
        calls = []
        class Response:
            def __init__(self, data, status_code=200):
                self.data, self.status_code = data, status_code
        async def fake_smart(history, budget):
            calls.append((history, budget))
            return "answer", False
        class RequestDouble:
            def __init__(self, payload, headers=None):
                self.payload = payload
                self.headers = headers or {}
            async def stream(self):
                for item in self.payload:
                    yield item
        env = {"json": json, "CH": None, "Request": object,
               "JSONResponse": Response, "smart": fake_smart,
               "log": lambda *_: None, "traceback": SimpleNamespace(format_exc=lambda: "")}
        exec(code, env)
        def invoke(value, headers=None):
            data = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
            return asyncio.run(env["chat"](RequestDouble([data], headers)))
        for payload, reason in (
            ({"messages": [{"role": "user", "content": "old"},
                           {"role": "assistant", "content": "done"}]}, "CHAT_LAST_USER_REQUIRED"),
            ({"messages": [{"role": "user", "content": "   "}]}, "CHAT_MISSING_USER"),
            ({"messages": [{"role": "user", "content": 5}]}, "CHAT_INVALID_MESSAGES"),
            ({"messages": [{"role": "user", "content": chr(0xD800)}]}, "CHAT_INVALID_UNICODE"),
        ):
            with self.subTest(reason=reason):
                result = invoke(payload)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.data["reason"], reason)
        # The non-stream legacy route must enforce the same strict JSON
        # boundary before smart() or canonical S03 is invoked.
        for raw in (
            b'{"messages":[],"messages":[{"role":"user","content":"overridden"}]}',
            b'{"messages":[{"role":"user","content":"safe","content":"overridden"}]}',
            b'{"messages":[{"role":"user","content":"safe","meta":NaN}]}',
            b'{"messages":[{"role":"user","content":"safe","meta":-Infinity}]}',
        ):
            with self.subTest(raw=raw):
                result = invoke(raw)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.data["reason"], "CHAT_INVALID_JSON")
        self.assertEqual(invoke(b"x" * (2*1024*1024 + 1)).status_code, 413)
        self.assertEqual(calls, [])
        valid = [{"role": "system", "content": "trusted existing context"},
                 {"role": "user", "content": "first"},
                 {"role": "assistant", "content": "reply"},
                 {"role": "user", "content": "second"}]
        result = invoke({"messages": valid, "max_tokens": 350})
        self.assertEqual(result["choices"][0]["message"]["content"], "answer")
        self.assertEqual(calls, [(valid, 350)])

    def test_failed_advisory_token_hint_keeps_sse_and_one_s03_write_attempt(self):
        # Optional token sizing must not strand an accepted request between
        # the status frame and the first model token.
        for hint in (RuntimeError("tokenizer down"), None, True, "700",
                     -1, 50000, float("nan")):
            with self.subTest(hint=repr(hint)):
                events, writes, soul, _ = self.run_stream([
                    self.chunk("Сохраняю 🌍"), self.chunk(finish="stop"),
                    "data: [DONE]"], token_hint=hint)
                self.assertEqual(events[-1]["type"], "done")
                self.assertTrue(events[-1]["generation_complete"])
                self.assertFalse(events[-1]["memory_write_receipt"]["s03_readback_verified"])
                self.assertEqual(writes, [("Привет", "Сохраняю 🌍")])
                self.assertEqual(soul, writes)

    def test_real_http_bytes_are_bounded_and_unicode_exact(self):
        # Actual httpx exposes aiter_bytes, not the fixture-only aiter_lines.
        # CRLF/UTF-8 can cross arbitrary transport chunks without changing S03.
        raw = ("data: " + json.dumps(
            {"choices": [{"delta": {"content": "Привет 🌍"},
                          "finish_reason": None}]}, ensure_ascii=False
        ) + "\r\n\r\n" + self.chunk(finish="stop") +
            "\n\ndata: [DONE]\r\n\r\n").encode("utf-8")
        chunks = [raw[i:i+3] for i in range(0, len(raw), 3)]
        events, writes, soul, _ = self.run_stream([], byte_chunks=chunks)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "Привет 🌍")])
        self.assertEqual(soul, writes)
        # Malformed UTF-8 must not be decoded with replacement characters
        # and then certified as a factual S03 reply.
        bad, bad_writes, bad_soul, _ = self.run_stream(
            [], byte_chunks=[b"data: " + bytes([0xff]) + b"\\n\\n"])
        self.assertEqual(bad[-1]["type"], "error")
        self.assertEqual((bad_writes, bad_soul), ([], []))
        # A provider that never sends a newline cannot force unbounded
        # httpx line buffering before the stream is rejected.
        huge, huge_writes, huge_soul, _ = self.run_stream(
            [], byte_chunks=[b"data: " + b"x" * (1024 * 1024 + 1)])
        self.assertEqual(huge[-1]["type"], "error")
        self.assertEqual((huge_writes, huge_soul), ([], []))

    def test_unterminated_done_wire_never_certifies_s03(self):
        # A model-level stop is provisional: even a fully spelled [DONE]
        # without a final wire line delimiter is not a complete SSE reply.
        prefix = (self.chunk("Живой ответ") + "\n\n" +
                  self.chunk(finish="stop") + "\n\n").encode("utf-8")
        for trailing in ([b"data: [DONE]"], [b"data: [DO", b"NE]"]):
            with self.subTest(trailing=trailing):
                events, writes, soul, _ = self.run_stream(
                    [], byte_chunks=[prefix] + trailing)
                self.assertEqual(events[-1]["type"], "error")
                self.assertEqual(events[-1]["reason"], "UPSTREAM_STREAM_ERROR")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertEqual((writes, soul), ([], []))
        # The canonical CRLF-delimited terminal sentinel still succeeds.
        good, writes, soul, _ = self.run_stream(
            [], byte_chunks=[prefix, b"data: [DONE]\\r\\n\\r\\n".replace(b"\\\\", b"\\")])
        self.assertEqual(good[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "Живой ответ")])
        self.assertEqual(soul, writes)

    def test_complete_stop_done_writes_once_but_never_certifies_s03_readback(self):
        events, writes, logs, _ = self.run_stream([
            self.chunk("¡Привет! 🌍"), self.chunk(finish="stop"), "data: [DONE]"
        ])
        self.assertEqual([x["type"] for x in events if x["type"] == "token"], ["token"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["generation_complete"])
        self.assertEqual(events[-1]["memory_write_receipt"],
                         {"status":"WRITE_RETURNED_UNVERIFIED","s03_readback_verified":False})
        self.assertEqual(writes, [("Привет", "¡Привет! 🌍")])
        self.assertEqual(logs, writes)

    def test_last_visible_token_sharing_stop_frame_is_saved_exactly_once(self):
        # A provider may attach its last visible delta to finish_reason=stop.
        # The terminal event is still provisional until [DONE] + clean EOF.
        events, writes, logs, _ = self.run_stream([
            self.chunk("Прив"), self.chunk("ет 🌌", finish="stop"), "data: [DONE]"
        ])
        text = "".join(e["text"] for e in events if e["type"] == "token")
        self.assertEqual(text, "Привет 🌌")
        self.assertEqual(writes, [("Привет", text)])
        self.assertEqual(logs, writes)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["generation_complete"])
        self.assertFalse(events[-1]["memory_write_receipt"]["s03_readback_verified"])

        # But any *later* text after the stop event must remain a HOLD.
        rejected, writes2, logs2, _ = self.run_stream([
            self.chunk("Прив"), self.chunk("ет", finish="stop"),
            self.chunk("лишний"), "data: [DONE]"
        ])
        self.assertEqual(rejected[-1]["type"], "error")
        self.assertEqual(writes2, [])
        self.assertEqual(logs2, [])

    def test_many_unicode_fragments_keep_exact_token_order_and_s03_content(self):
        # Checks >1,000 token events plus non-ASCII characters and whitespace
        # against the final single S03 write, not only the displayed stream.
        pieces = ["a", "ю", "🙂", " "] * 350
        lines = [self.chunk(part) for part in pieces]
        lines.extend((self.chunk(finish="stop"), "data: [DONE]"))
        events, writes, logs, _ = self.run_stream(lines)
        actual = "".join(e["text"] for e in events if e["type"] == "token")
        self.assertEqual(actual, "".join(pieces))
        self.assertEqual(writes, [("Привет", actual)])
        self.assertEqual(logs, writes)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["generation_complete"])
        self.assertFalse(events[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_s03_receives_exact_visible_bytes_including_edge_whitespace(self):
        # A visually complete SSE turn must not silently normalize the
        # assistant answer before the canonical persistence attempt.
        pieces = ["  ", "Привет", "\n", "🙂", "  "]
        events, writes, logs, _ = self.run_stream(
            [self.chunk(part) for part in pieces] +
            [self.chunk(finish="stop"), "data: [DONE]"])
        displayed = "".join(e["text"] for e in events if e["type"] == "token")
        self.assertEqual(displayed, "".join(pieces))
        self.assertEqual(writes, [("Привет", displayed)])
        self.assertEqual(logs, writes)
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse(events[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_early_eof_cannot_become_done_or_memory(self):
        for lines in ([self.chunk("partial"), self.chunk(finish="stop")],
                      [self.chunk("partial"), "data: [DONE]"],
                      [self.chunk(finish="stop"), "data: [DONE]"]):
            with self.subTest(lines=lines):
                events, writes, logs, last = self.run_stream(lines)
                self.assertEqual(events[-1]["type"], "error")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertFalse(events[-1]["s03_readback_verified"])
                self.assertNotIn("done", [x["type"] for x in events])
                self.assertEqual(writes, [])
                self.assertEqual(logs, [])
                self.assertEqual(last["t"], 0)

    def test_length_or_upstream_error_never_writes_even_with_done_marker(self):
        for lines in (
            [self.chunk("truncated"), self.chunk(finish="length"), "data: [DONE]"],
            [self.chunk("partial"), 'data: {"error":{"message":"fail"}}', "data: [DONE]"],
            [self.chunk("partial"), "{not_sse_frame}", "data: [DONE]"],
            [self.chunk("partial"), "data: {broken", "data: [DONE]"],
            [self.chunk("partial"), OSError("broken socket")],
        ):
            with self.subTest(lines=lines):
                events, writes, _, _ = self.run_stream(lines)
                self.assertEqual(events[-1]["type"], "error")
                self.assertNotIn("done", [x["type"] for x in events])
                self.assertEqual(writes, [])

    def test_falsy_nonstring_sse_content_fails_closed_before_s03(self):
        # A malformed delta with numeric zero, false or [] must not be
        # interpreted as an empty control frame and then committed to S03.
        for invalid in (0, False, []):
            with self.subTest(invalid=invalid):
                wrong = self.chunk("answer")
                malformed = "data: " + json.dumps({
                    "choices": [{"delta": {"content": invalid},
                                 "finish_reason": None}]})
                events, writes, logs, last = self.run_stream([
                    wrong, malformed, self.chunk(finish="stop"), "data: [DONE]"
                ])
                self.assertEqual(events[-1]["type"], "error")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertNotIn("done", [e["type"] for e in events])
                self.assertEqual(writes, [])
                self.assertEqual(logs, [])
                self.assertEqual(last["t"], 0)

    def test_ambiguous_upstream_sse_must_not_write_canonical_memory(self):
        # Previously Python json.loads used last-wins keys, accepted
        # nonfinite constants and ignored additional completion choices.
        invalid_events = (
            'data: {"error":{"message":"failed"},"error":null,'
            '"choices":[{"delta":{"content":"hidden"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"hidden","content":""},'
            '"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"visible"},'
            '"finish_reason":null},{"delta":{"content":"different"},'
            '"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":""},'
            '"finish_reason":null}],"meta":NaN}',
            'data: {"choices":[{"delta":{"content":""},'
            '"finish_reason":null}],"meta":Infinity}',
        )
        for invalid in invalid_events:
            with self.subTest(invalid=invalid):
                events, writes, logs, last = self.run_stream([
                    self.chunk("valid prefix"), invalid,
                    self.chunk(finish="stop"), "data: [DONE]"
                ])
                self.assertEqual(events[-1]["type"], "error")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertNotIn("done", [e["type"] for e in events])
                self.assertEqual(writes, [])
                self.assertEqual(logs, [])
                self.assertEqual(last["t"], 0)
        # One ordinary single-choice SSE still completes and writes once.
        events, writes, _, _ = self.run_stream([
            self.chunk("valid"), self.chunk(finish="stop"), "data: [DONE]"
        ])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "valid")])

    def test_legacy_text_stream_rejects_hidden_tool_work_before_s03(self):
        """A text-only stream must not save visible tokens from an unfinished tool turn."""
        def event(delta, **choice_fields):
            return {"choices": [{"delta": delta, "finish_reason": None,
                                 **choice_fields}]}
        malformed = (
            ("delta_tool", event({"content": "partial", "tool_calls": [{"id": "t1"}]})),
            ("delta_function", event({"function_call": {"name": "act"}})),
            ("non_assistant", event({"role": "tool", "content": "spoof"})),
            ("choice_tool", event({"content": ""}, tool_calls=[{"id": "t2"}])),
            ("top_tool", {**event({"content": ""}), "tool_calls": [{"id": "t3"}]}),
            ("explicit_error", {**event({"content": ""}), "error": None}),
        )
        for label, payload in malformed:
            with self.subTest(case=label):
                lines = [self.chunk("visible prefix"),
                         "data: " + json.dumps(payload),
                         self.chunk(finish="stop"), "data: [DONE]"]
                frames, writes, soul, last = self.run_stream(lines)
                self.assertEqual(frames[-1]["type"], "error")
                self.assertFalse(frames[-1]["generation_complete"])
                self.assertNotIn("done", [item["type"] for item in frames])
                self.assertEqual(writes, [])
                self.assertEqual(soul, [])
                self.assertEqual(last["t"], 0)
        valid, writes, _, _ = self.run_stream([
            self.chunk("full text"), self.chunk(finish="stop"), "data: [DONE]"
        ])
        self.assertEqual(valid[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "full text")])

    def test_bare_named_error_after_stop_never_writes_s03(self):
        events, writes, logs, last = self.run_stream([
            self.chunk("partial"), self.chunk(finish="stop"),
            "event: error", "data: [DONE]"
        ])
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("done", [x["type"] for x in events])
        self.assertEqual(writes, [])
        self.assertEqual(logs, [])
        self.assertEqual(last["t"], 0)

    def test_nonerror_sse_fields_remain_compatible(self):
        events, writes, _, _ = self.run_stream([
            "event: message", "id: 3", self.chunk("hello"),
            self.chunk(finish="stop"), "data: [DONE]"
        ])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "hello")])

    def test_done_sentinel_requires_clean_http_eof_before_s03(self):
        # A late frame or transport failure after [DONE] must not turn
        # partial/corrupt upstream output into a durable conversation.
        complete = [self.chunk("привет 🌍"), self.chunk(finish="stop"),
                    "data: [DONE]"]
        for tail in (["event: error"], [self.chunk("late")],
                     ["data: [DONE]"], ["event: message"],
                     [OSError("transport reset")]):
            with self.subTest(tail=tail):
                events, writes, logs, last = self.run_stream(complete + tail)
                self.assertEqual(events[-1]["type"], "error")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertNotIn("done", [e["type"] for e in events])
                self.assertEqual(writes, [])
                self.assertEqual(logs, [])
                self.assertEqual(last["t"], 0)
        events, writes, _, _ = self.run_stream(
            complete + ["", "", "   "])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(writes, [("Привет", "привет 🌍")])

    def test_http_error_blocks_write(self):
        events, writes, _, _ = self.run_stream([self.chunk("hello"),
            self.chunk(finish="stop"), "data: [DONE]"], status=503)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(writes, [])

    def test_memory_write_failure_does_not_misreport_s03_success(self):
        events, writes, _, _ = self.run_stream([
            self.chunk("hello"), self.chunk(finish="stop"), "data: [DONE]"
        ],write_ok=False)
        self.assertEqual(writes, [("Привет","hello")])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["memory_write_receipt"]["status"], "HOLD")
        self.assertFalse(events[-1]["memory_write_receipt"]["s03_readback_verified"])

    def test_write_exception_after_complete_turn_is_terminal_but_never_s03_success(self):
        events, writes, logs, _ = self.run_stream([
            self.chunk("answer"), self.chunk(finish="stop"), "data: [DONE]"
        ], write_raises=True)
        self.assertEqual([e["type"] for e in events].count("done"), 1)
        self.assertTrue(events[-1]["generation_complete"])
        self.assertEqual(events[-1]["memory_write_receipt"], {
            "status": "HOLD", "s03_readback_verified": False,
            "reason": "S03_WRITE_EXCEPTION", "retry_safe": False})
        self.assertEqual(writes, [("Привет", "answer")])
        self.assertEqual(logs, [])

    def test_failed_s03_context_returns_terminal_hold_without_model_or_write(self):
        events, writes, logs, last = self.run_stream(
            [self.chunk("should-not-run"), self.chunk(finish="stop"),
             "data: [DONE]"], memory_error=True)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["reason"], "S03_CONTEXT_UNAVAILABLE")
        self.assertFalse(events[-1]["generation_complete"])
        self.assertFalse(events[-1]["s03_readback_verified"])
        self.assertNotIn("done", [e["type"] for e in events])
        self.assertEqual(writes, [])
        self.assertEqual(logs, [])
        self.assertEqual(last["t"], 0)

    def test_failed_premodel_state_emits_terminal_hold_without_memory(self):
        complete = [self.chunk("would-not-run"), self.chunk(finish="stop"),
                    "data: [DONE]"]
        for condition in ("vol_error", "affect_error"):
            with self.subTest(condition=condition):
                events, writes, logs, last = self.run_stream(
                    complete, **{condition: True})
                self.assertEqual(events[-1]["type"], "error")
                self.assertEqual(events[-1]["reason"], "PREMODEL_CONTEXT_UNAVAILABLE")
                self.assertFalse(events[-1]["generation_complete"])
                self.assertFalse(events[-1]["s03_readback_verified"])
                self.assertNotIn("done", [x["type"] for x in events])
                self.assertNotIn("token", [x["type"] for x in events])
                self.assertEqual(writes, [])
                self.assertEqual(logs, [])
                self.assertEqual(last["t"], 0)

    def test_failed_optional_soul_log_keeps_exact_s03_receipt(self):
        events, writes, logs, _ = self.run_stream([
            self.chunk("saved"), self.chunk(finish="stop"), "data: [DONE]"
        ], soul_error=True)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["generation_complete"])
        self.assertEqual(events[-1]["memory_write_receipt"],
                         {"status": "WRITE_RETURNED_UNVERIFIED",
                          "s03_readback_verified": False})
        self.assertEqual(writes, [("Привет", "saved")])
        self.assertEqual(logs, [])

    def test_ambiguous_s03_commit_revokes_cache_even_when_writer_raises(self):
        # Source-only: the real S03 writer can commit before raising, so a
        # follow-up recall must not reuse an obsolete process-local answer.
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("remember", "remember_fact")]
        self.assertEqual(len(nodes), 2)
        code = compile(ast.fix_missing_locations(
            ast.Module(body=nodes, type_ignores=[])), "nox_bridge.py", "exec")
        calls, invalidations, notices = [], [], []

        def uncertain_writer(user, answer):
            calls.append((user, answer))
            raise OSError("COMMIT_RETURN_LOST")

        scope = {"invalidate_s03_cache": lambda: invalidations.append(True),
                 "log": notices.append}
        with patch.dict(sys.modules, {
            "s03_memory": SimpleNamespace(persist_turn=uncertain_writer)
        }):
            exec(code, scope)
            self.assertFalse(scope["remember"]("first", "reply"))
            with self.assertRaisesRegex(OSError, "COMMIT_RETURN_LOST"):
                scope["remember_fact"]("fact", "value")
        self.assertEqual(calls, [("first", "reply"), ("fact", "value")])
        self.assertEqual(invalidations, [True, True])
        self.assertEqual(len(notices), 1)

    def test_explicit_s03_rejection_and_nonstream_soul_mirror(self):
        # Exercise the actual remember() and smart() AST functions offline:
        # no live S03 writes, GPU requests or service imports.
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        saved, cache_events, logs = [], [], []
        def persist(_user, _answer):
            saved.append((_user, _answer))
            return False
        remember_node = next(n for n in TREE.body
                             if isinstance(n, ast.FunctionDef) and n.name == "remember")
        remember_code = compile(ast.fix_missing_locations(
            ast.Module(body=[remember_node], type_ignores=[])), "nox_bridge.py", "exec")
        state = {"invalidate_s03_cache": lambda: cache_events.append("invalidated"),
                 "log": logs.append}
        with patch.dict(sys.modules, {"s03_memory": SimpleNamespace(persist_turn=persist)}):
            exec(remember_code, state)
            self.assertIs(state["remember"]("u", "a"), False)
        self.assertEqual(saved, [("u", "a")])
        self.assertEqual(cache_events, ["invalidated"])
        self.assertEqual(logs, ["persist_explicitly_rejected"])

        # The existing S03 writer may return None after a successful commit;
        # preserve that compatibility, rather than requiring truthy metadata.
        with patch.dict(sys.modules, {
            "s03_memory": SimpleNamespace(persist_turn=lambda *_: None)}):
            self.assertIs(state["remember"]("u2", "a2"), True)

        smart_node = next(n for n in TREE.body
                          if isinstance(n, ast.AsyncFunctionDef) and n.name == "smart")
        smart_code = compile(ast.fix_missing_locations(
            ast.Module(body=[smart_node], type_ignores=[])), "nox_bridge.py", "exec")
        mirrored = []
        async def fake_ask(*_args, **_kwargs):
            return "short answer"
        env = {
            "memory_block": lambda _: "",
            "build_msgs": lambda *_: [],
            "self_vol": lambda _: "",
            "ask": fake_ask,
            "adapt_tokens": lambda _: 200,
            "remember": lambda *_: False,
            "SOUL": SimpleNamespace(log_turn=lambda *x: mirrored.append(x)),
            "LAST_CHAT": {"t": 0},
            "time": time,
        }
        exec(smart_code, env)
        reply, _ = asyncio.run(env["smart"]([{"role": "user", "content": "u"}]))
        self.assertEqual(reply, "short answer")
        self.assertEqual(mirrored, [])
        env["remember"] = lambda *_: True
        asyncio.run(env["smart"]([{"role": "user", "content": "u"}]))
        self.assertEqual(mirrored, [("u", "short answer")])

    def test_browser_history_is_gated_on_real_complete(self):
        self.assertIn("if(!complete){", SOURCE)
        self.assertIn("complete=o.generation_complete===true", SOURCE)
        self.assertIn("if(!r.ok||!r.body)throw Error('upstream')", SOURCE)


if __name__ == "__main__":
    unittest.main()
