"""Source-only regression for the incumbent non-stream NOX bridge.

Exercise the real AST-extracted ask/smart functions with fake HTTP and S03.
No network, model, worker, STOP, Drive, or S03 storage is involved.
"""
import ast
import asyncio
from pathlib import Path
import time
import unittest

SOURCE = Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8")
tree = ast.parse(SOURCE)
functions = [n for n in tree.body
             if isinstance(n, ast.AsyncFunctionDef) and n.name in ("ask", "smart")]
assert {n.name for n in functions} == {"ask", "smart"}
compiled = compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                   "nox_bridge.py", "exec")


class NonstreamCompletionFence(unittest.TestCase):
    def invoke(self, finish_reason, content="finished"):
        writes = []
        class Response:
            status_code = 200
            def json(self):
                return {"choices": [{"finish_reason": finish_reason,
                                     "message": {"content": content}}]}
        class Client:
            async def post(self, *args, **kwargs):
                return Response()
        clock = {"t": 0}
        scope = {
            "hc": lambda: Client(),
            "MODEL": "http://127.0.0.1/never-contacted",
            "NKEEP": 0,
            "log": lambda _: None,
            "memory_block": lambda _: "",
            "build_msgs": lambda *args: [],
            "self_vol": lambda _: "",
            "adapt_tokens": lambda _: 64,
            "LAST_CHAT": clock,
            "remember": lambda u, a: writes.append((u, a)) or True,
            "SOUL": None,
            "time": time,
        }
        exec(compiled, scope)
        async def run():
            return await scope["smart"]([{"role": "user", "content": "question"}])
        try:
            response = asyncio.run(run())
        except ValueError as exc:
            response = str(exc)
        return response, writes, clock

    def test_stop_persists_one_complete_turn(self):
        reply, writes, clock = self.invoke("stop")
        self.assertEqual(reply, ("finished", False))
        self.assertEqual(writes, [("question", "finished")])
        self.assertGreater(clock["t"], 0)

    def test_length_tool_or_unknown_finish_never_reaches_s03(self):
        for reason in ("length", "tool_calls", "content_filter", None):
            with self.subTest(reason=reason):
                result, writes, clock = self.invoke(reason)
                self.assertEqual(result, "UPSTREAM_NONSTOP_COMPLETION")
                self.assertEqual(writes, [])
                self.assertEqual(clock["t"], 0)


if __name__ == "__main__":
    unittest.main()
