"""E06 W3 R13: release the existing P02 Ollama generator at a terminal frame.

Offline deterministic owner stubs. No Windows, installed Ollama or GPU claim.
"""
from __future__ import annotations

import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope


class OneHostTerminalOwnerCleanup(unittest.TestCase):
    def setUp(self):
        fixture = E06StopInterlock("test_05_normal_frame_and_owner_stop_token_survive")
        fixture.setUp()
        self.fixture = fixture
        self.seam = fixture.seam
        self.scope = NativeScope()
        self.close_events = []

    def _frames(self, terminal, stop=None):
        closed = self.close_events
        def owner(*_):
            try:
                yield {"type": "chat.start", "run_id": "owner-one"}
                yield terminal
            finally:
                closed.append("ollama-lease-closed")
        self.fixture.chat.send = owner
        return self.seam.stream_chat(self.scope, "already-installed", "hello", stop)

    def test_01_chat_complete_releases_inner_owner_before_webview_consumes_next(self):
        stream = self._frames({"type": "chat.complete", "run_id": "owner-one"})
        self.assertEqual(next(stream)["type"], "chat.start")
        self.assertEqual(self.close_events, [], "the session must still be live")
        self.assertEqual(next(stream)["type"], "chat.complete")
        self.assertEqual(self.close_events, ["ollama-lease-closed"],
                         "WebView can stop reading at chat.complete; inner Ollama must already be closed")

    def test_02_chat_error_releases_inner_owner_before_webview_stops(self):
        stream = self._frames({"type": "chat.error", "code": "OWNER_FAILED"})
        next(stream)
        self.assertEqual(next(stream)["code"], "OWNER_FAILED")
        self.assertEqual(self.close_events, ["ollama-lease-closed"])

    def test_03_nonterminal_delta_does_not_preempt_owner(self):
        def owner(*_):
            try:
                yield {"type": "chat.delta", "text": "a"}
                yield {"type": "chat.delta", "text": "b"}
            finally:
                self.close_events.append("closed")
        self.fixture.chat.send = owner
        stream = self.seam.stream_chat(self.scope, "already-installed", "hello")
        self.assertEqual(next(stream)["text"], "a")
        self.assertEqual(self.close_events, [])
        self.assertEqual(next(stream)["text"], "b")
        self.assertEqual(self.close_events, [])
        stream.close()
        self.assertEqual(self.close_events, ["closed"])

    def test_04_owner_close_sets_stop_then_terminal_is_not_delivered(self):
        stop = threading.Event()
        def owner(*_):
            try:
                yield {"type": "chat.complete", "run_id": "owner-one"}
            finally:
                self.close_events.append("closed")
                stop.set()
        self.fixture.chat.send = owner
        stream = self.seam.stream_chat(self.scope, "already-installed", "hello", stop)
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(self.close_events, ["closed"])
        self.assertTrue(stop.is_set())

    def test_05_early_user_cancel_releases_owner_after_started_frame(self):
        stop = threading.Event()
        stream = self._frames({"type": "chat.complete"}, stop)
        self.assertEqual(next(stream)["type"], "chat.start")
        stop.set()
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(self.close_events, ["ollama-lease-closed"])


if __name__ == "__main__":
    unittest.main()
