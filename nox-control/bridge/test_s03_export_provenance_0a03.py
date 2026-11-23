#!/usr/bin/env python3
"""RELAY35 0A03: local mirror export must not claim canonical S03 readback."""
import asyncio
import json
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


class S03ExportProvenanceTest(unittest.TestCase):
    def test_export_is_private_mirror_not_verified_canonical_s03(self):
        mirrored = [
            {"u": "Первый ход 🧠", "a": "Ответ с Unicode \n"},
            {"u": "Второй ход", "a": "Ответ два"},
        ]
        with (mock.patch.object(W.threading.Thread, "start"),
              mock.patch.object(W.os.path, "isdir", return_value=False),
              mock.patch.object(W, "_jl", return_value=mirrored) as read):
            app = FastAPI()
            W.install(app, Bridge())
            endpoint = next(route.endpoint for route in app.routes
                            if route.path == "/api/s03/export")
            response = asyncio.run(endpoint())
        read.assert_called_once_with(W.ST + "/turns.jsonl", 50)
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertIn("private", response.headers["cache-control"])
        self.assertEqual(payload["status"], "OK")
        self.assertIs(payload["s03_readback_verified"], False)
        self.assertEqual(payload["source_scope"], "LOCAL_TURNS_MIRROR")
        self.assertIsNone(payload["next"])
        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual([r["content"] for r in payload["rows"]],
                         ["Ответ два", "Ответ с Unicode \n"])
        self.assertTrue(all(r["source"] == "LOCAL_TURNS_MIRROR" and
                            r["s03_readback_verified"] is False
                            for r in payload["rows"]))


if __name__ == "__main__":
    unittest.main()
