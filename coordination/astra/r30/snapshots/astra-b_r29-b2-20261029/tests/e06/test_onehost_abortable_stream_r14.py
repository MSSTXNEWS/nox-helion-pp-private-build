"""R14 E06 owner-stream cancellation contract, exact owner bridge with local stubs.

P02 ChatBridge.send() is an abortable generator. The E06 WebView2 seam must
refuse any non-closable/non-iterator replacement BEFORE forwarding RAG sources.
NO GPU, live Ollama, Windows or installed EXE acceptance is claimed.
"""
from __future__ import annotations

import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class AbortableOwnerStreamContract(unittest.TestCase):
    def setUp(self):
        fixture = E06StopInterlock("test_05_normal_frame_and_owner_stop_token_survive")
        fixture.setUp()
        self.fixture = fixture
        self.bridge = fixture.seam
        self.chat = fixture.chat
        self.scope = NativeScope()
        self.stop = threading.Event()

    def test_01_list_iterator_without_close_must_not_leak_rag_sources(self):
        self.chat.send = lambda *_: iter([{"type": "chat.sources", "sources": [{"title": "PRIVATE"}]}])
        with self.assertRaisesRegex(SEAM.OneHostHold, "ABORTABLE_OWNER_STREAM_REQUIRED"):
            self.bridge.stream_chat(self.scope, "installed-model", "hello", self.stop)
        self.assertTrue(self.stop.is_set())

    def test_02_none_owner_result_is_hold_before_any_webview_frame(self):
        self.chat.send = lambda *_: None
        with self.assertRaisesRegex(SEAM.OneHostHold, "ABORTABLE_OWNER_STREAM_REQUIRED"):
            self.bridge.stream_chat(self.scope, "installed-model", "hello", self.stop)
        self.assertTrue(self.stop.is_set())

    def test_03_iterator_with_noncallable_close_is_rejected(self):
        class BrokenIterator:
            close = "NOT_CALLABLE"
            def __iter__(self): return self
            def __next__(self): return {"type": "chat.sources", "sources": [{"title": "PRIVATE"}]}
        self.chat.send = lambda *_: BrokenIterator()
        with self.assertRaisesRegex(SEAM.OneHostHold, "ABORTABLE_OWNER_STREAM_REQUIRED"):
            self.bridge.stream_chat(self.scope, "installed-model", "hello", self.stop)
        self.assertTrue(self.stop.is_set())

    def test_04_closable_noniterator_is_cleaned_once_and_refused(self):
        closed = []
        class CloseOnly:
            def close(self): closed.append(True)
        self.chat.send = lambda *_: CloseOnly()
        with self.assertRaisesRegex(SEAM.OneHostHold, "ABORTABLE_OWNER_STREAM_REQUIRED"):
            self.bridge.stream_chat(self.scope, "installed-model", "hello", self.stop)
        self.assertEqual(closed, [True])
        self.assertTrue(self.stop.is_set())

    def test_05_original_generator_still_yields_sources_and_close_stops_it(self):
        closed = []
        def owner(*_):
            try:
                yield {"type": "chat.sources", "sources": [{"title": "LOCAL"}]}
            finally:
                closed.append(True)
        self.chat.send = owner
        stream = self.bridge.stream_chat(self.scope, "installed-model", "hello", self.stop)
        self.assertEqual(next(stream)["sources"][0]["title"], "LOCAL")
        stream.close()
        self.assertEqual(closed, [True])
        self.assertTrue(self.stop.is_set())


if __name__ == "__main__":
    unittest.main()
