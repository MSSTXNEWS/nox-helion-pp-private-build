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
                   vol_error=False, affect_error=False, write_raises=False):
        writes, soul_logs, notices = [], [], []
        response = FakeResponse(lines, status)
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
            "adapt_tokens": lambda _: 64,
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

    def test_browser_history_is_gated_on_real_complete(self):
        self.assertIn("if(!complete){", SOURCE)
        self.assertIn("complete=o.generation_complete===true", SOURCE)
        self.assertIn("if(!r.ok||!r.body)throw Error('upstream')", SOURCE)


if __name__ == "__main__":
    unittest.main()
