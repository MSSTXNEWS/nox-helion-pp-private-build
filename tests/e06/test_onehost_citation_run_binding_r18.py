"""E06 R20 source-only: citations must match the actual P02 owner run token.

Deterministic existing-owner stubs only; does NOT establish real Ollama/RAG,
SQLite, WebView2, hardware or E07 acceptance.
"""
from __future__ import annotations
import threading
import unittest
from test_onehost_stop_gate_r07 import E06StopInterlock, SEAM


class CitationOwnerRunBinding(unittest.TestCase):
    def setUp(self):
        base = E06StopInterlock('test_05_normal_frame_and_owner_stop_token_survive')
        base.setUp()
        self.base = base

    def frames(self, frames):
        def send(*_):
            for frame in frames:
                yield frame
        self.base.chat.send = send
        stop = threading.Event()
        return self.base.seam.stream_chat(self._scope(), 'installed', 'hello', stop), stop

    def _scope(self):
        from test_onehost_stop_gate_r07 import NativeScope
        return NativeScope()

    def test_01_one_owner_run_citations_accepted(self):
        run = 'a' * 32
        stream, stop = self.frames([
            {'type': 'chat.start', 'run_id': run, 'model': 'installed'},
            {'type': 'chat.sources', 'run_id': run,
             'sources': [{'source_id': 'trusted', 'title': 'Primary'}]},
            {'type': 'chat.complete', 'run_id': run, 'chars': 0},
        ])
        self.assertEqual([f['type'] for f in stream],
                         ['chat.start', 'chat.sources', 'chat.complete'])
        self.assertTrue(stop.is_set())

    def test_02_cross_run_citations_denied_before_webview(self):
        stream, stop = self.frames([
            {'type': 'chat.start', 'run_id': 'a' * 32},
            {'type': 'chat.sources', 'run_id': 'b' * 32,
             'sources': [{'source_id': 'foreign', 'title': 'Private'}]},
        ])
        self.assertEqual(next(stream)['type'], 'chat.start')
        with self.assertRaisesRegex(SEAM.OneHostHold, 'P02_CHAT_OWNER_RUN_ID_CHANGED'):
            next(stream)
        self.assertTrue(stop.is_set())

    def test_03_unattributed_citations_after_owner_run_denied(self):
        stream, stop = self.frames([
            {'type': 'chat.start', 'run_id': 'a' * 32},
            {'type': 'chat.sources', 'sources': [{'source_id': 'foreign'}]},
        ])
        next(stream)
        with self.assertRaisesRegex(SEAM.OneHostHold, 'P02_CHAT_CITATION_RUN_ID_REQUIRED'):
            next(stream)
        self.assertTrue(stop.is_set())

    def test_04_citations_without_started_run_denied(self):
        stream, stop = self.frames([
            {'type': 'chat.sources', 'run_id': 'a' * 32,
             'sources': [{'source_id': 'foreign'}]},
        ])
        with self.assertRaisesRegex(SEAM.OneHostHold, 'P02_CHAT_CITATION_START_REQUIRED'):
            next(stream)
        self.assertTrue(stop.is_set())

    def test_05_invalid_owner_run_token_denied(self):
        stream, stop = self.frames([
            {'type': 'chat.start', 'run_id': '\nspoof'},
            {'type': 'chat.sources', 'run_id': '\nspoof', 'sources': []},
        ])
        with self.assertRaisesRegex(SEAM.OneHostHold, 'P02_CHAT_OWNER_RUN_ID_INVALID'):
            next(stream)
        self.assertTrue(stop.is_set())


if __name__ == '__main__':
    unittest.main()
