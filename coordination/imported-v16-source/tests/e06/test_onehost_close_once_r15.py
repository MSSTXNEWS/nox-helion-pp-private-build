"""E06 R15 close-once fence for existing P02 owner iterator.

Offline deterministic contract only. Native Ollama/Windows/GPU E2E remain HOLD.
"""
from __future__ import annotations

import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class _OwnerIterator:
    def __init__(self, frames, *, fail_close=False):
        self.frames = iter(frames)
        self.close_calls = 0
        self.fail_close = fail_close

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.frames)

    def close(self):
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("private-owner-error")
        if self.close_calls > 1:
            raise RuntimeError("double-close-owner-lease")


class OwnerCloseOnceFence(unittest.TestCase):
    def setUp(self):
        fixture = E06StopInterlock("test_05_normal_frame_and_owner_stop_token_survive")
        fixture.setUp()
        self.chat = fixture.chat
        self.bridge = fixture.seam
        self.scope = NativeScope()
        self.stop = threading.Event()

    def attach(self, frames, *, fail_close=False):
        owner = _OwnerIterator(frames, fail_close=fail_close)
        self.chat.send = lambda *_: owner
        return owner, self.bridge.stream_chat(self.scope, "already-installed", "hello", self.stop)

    def test_01_complete_then_webview_close_does_not_close_owner_twice(self):
        owner, stream = self.attach([{"type": "chat.complete"}])
        self.assertEqual(next(stream)["type"], "chat.complete")
        stream.close()
        self.assertEqual(owner.close_calls, 1)
        self.assertTrue(self.stop.is_set())

    def test_02_error_then_webview_close_does_not_close_owner_twice(self):
        owner, stream = self.attach([{"type": "chat.error", "code": "OWNER"}])
        self.assertEqual(next(stream)["type"], "chat.error")
        stream.close()
        self.assertEqual(owner.close_calls, 1)

    def test_03_owner_terminal_cleanup_failure_is_hold_before_delivery(self):
        owner, stream = self.attach([{"type": "chat.complete", "secret": "PRIVATE"}], fail_close=True)
        with self.assertRaisesRegex(SEAM.OneHostHold, "EXISTING_P02_OWNER_STREAM_CLOSE_FAILED"):
            next(stream)
        self.assertEqual(owner.close_calls, 1)
        self.assertTrue(self.stop.is_set())

    def test_04_cancel_after_first_frame_closes_owner_once(self):
        owner, stream = self.attach([{"type": "chat.start"}, {"type": "chat.sources", "secret": "PRIVATE"}])
        self.assertEqual(next(stream)["type"], "chat.start")
        self.stop.set()
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(owner.close_calls, 1)

    def test_05_early_ui_close_after_delta_does_not_double_close(self):
        owner, stream = self.attach([{"type": "chat.delta", "text": "a"}])
        next(stream)
        stream.close()
        self.assertEqual(owner.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
