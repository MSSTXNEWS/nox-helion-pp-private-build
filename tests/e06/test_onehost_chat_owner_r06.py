"""E06 R06 original owner-module contracts. Authored; native Windows NOT_RUN.

Uses the exact existing P02/P04 fixture. Missing owner source causes an explicit
failure (no mock fallback and no fake GPU/Ollama/Windows acceptance).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_onehost_p02_p04 import OneHostOwnerContract


class OriginalOwnerChatWire(unittest.TestCase):
    def setUp(self):
        fixture = OneHostOwnerContract("test_01_same_existing_sqlite_and_owner_instances")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f = fixture

    def _first(self):
        return next(self.f.seam.stream_chat(self.f.scope, "offline-test-model", "hello"))

    def test_01_existing_chat_frame_allowed(self):
        frame = self._first()
        self.assertEqual(frame["type"], "chat.start")

    def test_02_postauthorize_mutation_cannot_change_citations(self):
        original = {"type": "chat.sources", "sources": [{"source_id": "source-1"}]}
        self.f.chat.send = lambda *args: (item for item in [original])
        trusted = self.f.seam._authorize
        def mutate_after_await(scope, operation):
            original["type"] = "chat.complete"
            original["sources"][0]["source_id"] = "forged"
            return trusted(scope, operation)
        self.f.seam._authorize = mutate_after_await
        frame = self._first()
        self.assertEqual(frame["type"], "chat.sources")
        self.assertEqual(frame["sources"][0]["source_id"], "source-1")

    def test_03_later_owner_mutation_cannot_change_returned_frame(self):
        original = {"type": "chat.sources", "sources": [{"source_id": "source-1"}]}
        self.f.chat.send = lambda *args: (item for item in [original])
        frozen = self._first()
        original["sources"][0]["source_id"] = "changed"
        self.assertEqual(frozen["sources"][0]["source_id"], "source-1")

    def test_04_bad_frame_type_rejected(self):
        self.f.chat.send = lambda *args: (item for item in [{"type": "task.completed"}])
        with self.assertRaisesRegex(Exception, "EXISTING_P02_CHAT_FRAME_TYPE_REQUIRED"):
            self._first()

    def test_05_nonfinite_frame_rejected(self):
        self.f.chat.send = lambda *args: (item for item in [{"type": "chat.delta", "delta": float("nan")}])
        with self.assertRaisesRegex(Exception, "P02_CHAT_FRAME_OWNER_JSON_VALUE_INVALID"):
            self._first()

    def test_06_oversized_frame_rejected(self):
        self.f.chat.send = lambda *args: (item for item in [{"type": "chat.delta", "delta": "x" * 1048577}])
        with self.assertRaisesRegex(Exception, "P02_CHAT_FRAME_OWNER_JSON_OVER_LIMIT"):
            self._first()

    def test_07_existing_owner_stop_terminal_survives(self):
        self.f.chat.send = lambda *args: (item for item in [{"type": "chat.error", "code": "STOP"}])
        self.assertEqual(self._first()["code"], "STOP")


if __name__ == "__main__":
    unittest.main()
