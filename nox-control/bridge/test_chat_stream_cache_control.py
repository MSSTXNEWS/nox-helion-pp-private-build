#!/usr/bin/env python3
"""RELAY35 1A03: chat NDJSON must not be stored by HTTP intermediaries."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nox_webapi as W


class Bridge:
    MODEL = "http://127.0.0.1:8098/v1/chat/completions"
    SOUL = None

    def log(self, *args):
        pass


class Request:
    async def json(self):
        return {
            "request_id": "cache-policy-stream-1",
            "use_memory": False,
            "messages": [{"role": "user", "content": "Private chat text"}],
        }


class StreamCachePolicyTest(unittest.TestCase):
    def test_stream_is_private_and_no_store_before_first_model_frame(self):
        with (mock.patch.object(W.threading.Thread, "start"),
              mock.patch.object(W.os.path, "isdir", return_value=False),
              mock.patch.object(W, "ACTIVE_CHAT_IDS", set()),
              mock.patch.object(W, "CHAT_SNAPSHOTS", {})):
            app = FastAPI()
            W.install(app, Bridge())
            chat = next(route.endpoint for route in app.routes if
                        route.path == "/api/chat")

            async def run():
                response = await chat(Request())
                try:
                    self.assertEqual(response.media_type, "application/x-ndjson")
                    cache_directives = {
                        part.strip().lower()
                        for part in response.headers["cache-control"].split(",")
                    }
                    self.assertIn("no-store", cache_directives)
                    self.assertIn("private", cache_directives)
                    self.assertEqual(response.headers["x-accel-buffering"], "no")
                finally:
                    # No model or S03 side effects: admission ends before iteration.
                    await response.body_iterator.aclose()

            asyncio.run(run())
            self.assertEqual(W.ACTIVE_CHAT_IDS, set())


    def test_legacy_bridge_sse_is_private_and_no_store(self):
        # Exercise the real legacy endpoint's AST without importing NOX
        # services or consuming a model/S03 stream.
        import ast
        from fastapi.responses import StreamingResponse

        tree = ast.parse(Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if
                    isinstance(n, ast.AsyncFunctionDef) and n.name == "chat_stream")
        node.decorator_list = []
        compiled = compile(ast.fix_missing_locations(
            ast.Module(body=[node], type_ignores=[])), "nox_bridge.py", "exec")

        async def never_consume(_history):
            if False:
                yield None

        context = {
            "CH": None,
            "Request": Request,
            "StreamingResponse": StreamingResponse,
            "stream_chat": never_consume,
        }
        exec(compiled, context)

        async def run():
            response = await context["chat_stream"](Request())
            try:
                directives = {d.strip().lower() for d in
                              response.headers["cache-control"].split(",")}
                self.assertIn("private", directives)
                self.assertIn("no-store", directives)
                self.assertEqual(response.media_type, "text/event-stream")
                self.assertEqual(response.headers["x-accel-buffering"], "no")
            finally:
                await response.body_iterator.aclose()

        asyncio.run(run())

if __name__ == "__main__":
    unittest.main()
