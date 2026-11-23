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


    def test_0a03_fact_commit_revokes_shared_recall_and_holds_ambiguity(self):
        """Fact writes must not leave stale S03 context or invite duplicate retry."""
        import sys
        import tempfile
        import types
        from unittest import mock

        class FactRequest:
            async def json(self):
                return {"content": "Контекст обновлён 🧠", "fact_key": "update"}

        def committed_then_raised(*args):
            writes.append(args)
            raise RuntimeError("writer committed then lost its response")

        with tempfile.TemporaryDirectory() as tempdir:
            for variant in ("returned", "rejected", "uncertain", "cache_failed"):
                with self.subTest(variant=variant):
                    writes = []
                    bridge = Bridge()
                    bridge.log = mock.Mock()
                    bridge.invalidate_s03_cache = mock.Mock(
                        side_effect=(RuntimeError("cache unavailable")
                                     if variant == "cache_failed" else None))
                    fake_s03 = types.ModuleType("s03_memory")
                    if variant == "rejected":
                        fake_s03.persist_turn = lambda *args: writes.append(args) or False
                    elif variant == "uncertain":
                        fake_s03.persist_turn = committed_then_raised
                    else:
                        fake_s03.persist_turn = lambda *args: writes.append(args)
                    fact_path = str(Path(tempdir) / ("fact_" + variant + ".jsonl"))
                    # Mock the sampler threads only while installing routes.
                    # asyncio.to_thread() must retain a real Thread.start during
                    # the S03 writer invocation, or the test deadlocks forever.
                    with (mock.patch.object(W, "FACTS", fact_path),
                          mock.patch.dict(sys.modules, {"s03_memory": fake_s03})):
                        with (mock.patch.object(W.threading.Thread, "start"),
                              mock.patch.object(W.os.path, "isdir", return_value=False)):
                            app = FastAPI()
                            W.install(app, bridge)
                        endpoint = next(route.endpoint for route in app.routes
                                        if route.path == "/api/s03/remember")
                        response = asyncio.run(endpoint(FactRequest()))
                    data = (json.loads(response.body)
                            if hasattr(response, "body") else response)
                    self.assertEqual(len(writes), 1)
                    bridge.invalidate_s03_cache.assert_called_once_with()
                    self.assertFalse(data["s03_readback_verified"])
                    if variant == "returned":
                        self.assertEqual(data["status"], "RECORDED_UNVERIFIED")
                        self.assertTrue(Path(fact_path).is_file())
                    else:
                        self.assertIn(data["status"], ("HOLD", "PARTIAL_HOLD"))
                        self.assertFalse(data["saved"])
                        self.assertFalse(data["retry_safe"])
                        self.assertFalse(Path(fact_path).exists(),
                                         "ambiguous S03 facts may not enter a success mirror")
                        if variant == "cache_failed":
                            self.assertEqual(data["reason"], "S03_CACHE_INVALIDATION_FAILED")
                            self.assertTrue(data["s03_write_returned"])



    def test_0a03_owner_fact_wire_fails_closed_before_s03_write(self):
        """Bound chunked fact JSON, reject duplicate keys, keep valid Unicode."""
        import tempfile
        import types
        from unittest import mock

        class StreamRequest:
            def __init__(self, chunks, headers=None):
                self.chunks = chunks
                self.headers = headers or {}
                self.reads = 0

            async def stream(self):
                self.reads += 1
                for chunk in self.chunks:
                    yield chunk

        with tempfile.TemporaryDirectory() as tmpdir:
            fact_path = str(Path(tmpdir) / "facts.jsonl")
            writer = mock.Mock(return_value=None)
            fake_s03 = types.ModuleType("s03_memory")
            fake_s03.persist_turn = writer
            bridge = Bridge()
            bridge.log = mock.Mock()
            bridge.invalidate_s03_cache = mock.Mock()
            with (mock.patch.object(W, "FACTS", fact_path),
                  mock.patch.dict(sys.modules, {"s03_memory": fake_s03})):
                with (mock.patch.object(W.threading.Thread, "start"),
                      mock.patch.object(W.os.path, "isdir", return_value=False)):
                    app = FastAPI()
                    W.install(app, bridge)
                endpoint = next(route.endpoint for route in app.routes
                                if route.path == "/api/s03/remember")
                cases = [
                    ("declared_over", StreamRequest([b'{}'], {
                        "content-length": str(W.MAX_S03_FACT_WIRE_BYTES + 1)}),
                     "S03_FACT_WIRE_TOO_LARGE", 413),
                    ("chunked_over", StreamRequest([b'x' * (W.MAX_S03_FACT_WIRE_BYTES + 1)]),
                     "S03_FACT_WIRE_TOO_LARGE", 413),
                    ("duplicate_key", StreamRequest([
                        b'{"content":"original","content":"substituted"}']),
                     "S03_FACT_INVALID_JSON", 400),
                    ("nonfinite", StreamRequest([b'{"content":"ok","confidence":NaN}']),
                     "S03_FACT_INVALID_JSON", 400),
                ]
                for name, req, expected_reason, expected_status in cases:
                    with self.subTest(name=name):
                        response = asyncio.run(endpoint(req))
                        self.assertEqual(response.status_code, expected_status)
                        self.assertEqual(json.loads(response.body)["reason"], expected_reason)
                        self.assertEqual(writer.call_count, 0)
                        self.assertFalse(Path(fact_path).exists())
                too_big = cases[0][1]
                self.assertEqual(too_big.reads, 0, "oversized declared body must not be read")
                payload = json.dumps({"content": "Память 🧠 обновлена"},
                                     ensure_ascii=False).encode("utf-8")
                split = payload.index("🧠".encode("utf-8")) + 1
                response = asyncio.run(endpoint(StreamRequest([payload[:split], payload[split:]])))
                self.assertIsInstance(response, dict)
                self.assertEqual(response["status"], "RECORDED_UNVERIFIED")
                self.assertIs(response["s03_readback_verified"], False)
                writer.assert_called_once_with("[ФАКТ ОТ СОЗДАТЕЛЯ] Память 🧠 обновлена",
                                               "Принято и запомнено.")
                bridge.invalidate_s03_cache.assert_called_once_with()
                self.assertTrue(Path(fact_path).is_file())

if __name__ == "__main__":
    unittest.main()
