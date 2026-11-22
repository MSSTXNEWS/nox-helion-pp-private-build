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


if __name__ == "__main__":
    unittest.main()
