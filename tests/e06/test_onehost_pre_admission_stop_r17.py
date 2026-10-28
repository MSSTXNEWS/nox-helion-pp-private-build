"""E06 W3.03 source-only STOP/SQLite admission regression.

Uses existing bridge with owner stubs. Does not claim Ollama, native ACL,
real GPU, installed host, Windows or E07 validation.
"""
from __future__ import annotations

import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class StopBeforeOwnerAdmission(unittest.TestCase):
    def setUp(self):
        f = E06StopInterlock('test_05_normal_frame_and_owner_stop_token_survive')
        f.setUp()
        self.seam, self.chat, self.scope = f.seam, f.chat, NativeScope()
        self.actions = []
        def history(*args):
            self.actions.append('sqlite.history')
            return []
        self.chat.store.history = history
        def owner(*args):
            self.actions.append('chat.send')
            yield {'type': 'chat.start'}
        self.chat.send = owner
        def auth(*args):
            self.actions.append('native.authorize')
            return True
        self.seam._authorize = auth

    def test_01_presignaled_stop_skips_sqlite_acl_and_owner(self):
        stop = threading.Event()
        stop.set()
        stream = self.seam.stream_chat(self.scope, 'model', 'prompt', stop)
        self.assertEqual(list(stream), [])
        self.assertEqual(self.actions, [])
        self.assertTrue(stop.is_set())
        # STOP result retains a closeable generator interface for WebView2.
        self.assertTrue(callable(getattr(stream, 'close', None)))

    def test_02_malformed_stop_is_rejected_before_any_sqlite_read(self):
        with self.assertRaisesRegex(TypeError, 'NATIVE_STOP_EVENT_REQUIRED'):
            self.seam.stream_chat(self.scope, 'model', 'prompt', 'javascript STOP')
        self.assertEqual(self.actions, [])

    def test_03_stop_during_sqlite_admission_never_constructs_owner_stream(self):
        stop = threading.Event()
        def history(*args):
            self.actions.append('sqlite.history')
            stop.set()
            return []
        self.chat.store.history = history
        def eager_owner(*args):
            self.actions.append('chat.send')
            return (frame for frame in [{'type': 'chat.start'}])
        self.chat.send = eager_owner
        stream = self.seam.stream_chat(self.scope, 'model', 'prompt', stop)
        self.assertEqual(list(stream), [])
        self.assertNotIn('chat.send', self.actions)
        self.assertEqual(self.actions.count('sqlite.history'), 1)
        self.assertTrue(stop.is_set())


if __name__ == '__main__':
    unittest.main()
