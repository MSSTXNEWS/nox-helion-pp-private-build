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


if __name__ == "__main__":
    unittest.main()
