import unittest
from b0_named_delta_encoder import encode_native_delta, HoldWire
from b0_proxy_stream_iter import ProxyDeltaBody


def frame(i, text):
    return {"type": "delta", "event_id": i, "text": text}


class Upstream:
    def __init__(self, frames=(), fail=None, close_fail=None):
        self.frames = iter(frames)
        self.pulls = self.closes = 0
        self.fail = fail
        self.close_fail = close_fail

    def __iter__(self):
        return self

    def __next__(self):
        self.pulls += 1
        try:
            return next(self.frames)
        except StopIteration:
            if self.fail:
                raise self.fail
            raise

    def close(self):
        self.closes += 1
        if self.close_fail:
            raise self.close_fail


class ProxyBodyTests(unittest.TestCase):
    def test_exact_lazy_bytes_and_eof(self):
        a, b = frame("turn2-1", "Привет 🌞"), frame("turn2-2", "¡Hola!\n")
        src = Upstream([a, b])
        body = ProxyDeltaBody(src)
        self.assertEqual(src.pulls, 0)
        self.assertEqual(next(body), encode_native_delta(a))
        self.assertEqual(src.pulls, 1)
        self.assertEqual(next(body), encode_native_delta(b))
        self.assertEqual(src.pulls, 2)
        with self.assertRaises(StopIteration):
            next(body)
        body.close()
        self.assertEqual((src.pulls, src.closes), (3, 1))

    def test_disconnect_before_and_after_first_pull(self):
        for started in (False, True):
            src = Upstream([frame("turn3-1", "a"), frame("turn3-2", "b")])
            body = ProxyDeltaBody(src)
            if started:
                next(body)
            body.close()
            body.close()
            with self.assertRaises(StopIteration):
                next(body)
            self.assertEqual((src.pulls, src.closes), (int(started), 1))

    def test_invalid_or_terminal_frame_closes_without_replay(self):
        for bad in ({"type": "token", "t": "legacy"}, {"type": "done"}):
            src = Upstream([bad, frame("next", "must not pull")])
            body = ProxyDeltaBody(src)
            with self.assertRaises(HoldWire):
                next(body)
            with self.assertRaises(StopIteration):
                next(body)
            self.assertEqual((src.pulls, src.closes), (1, 1))

    def test_upstream_error_not_converted_to_success(self):
        src = Upstream(fail=OSError("upstream lost"))
        with self.assertRaises(OSError):
            next(ProxyDeltaBody(src))
        self.assertEqual(src.closes, 1)

    def test_close_failure_not_clean_eof(self):
        src = Upstream(close_fail=OSError("close failed"))
        body = ProxyDeltaBody(src)
        with self.assertRaises(OSError):
            next(body)
        body.close()
        self.assertEqual(src.closes, 1)

    def test_noncloseable_source_refused(self):
        with self.assertRaises(TypeError):
            ProxyDeltaBody(iter([]))


if __name__ == "__main__":
    unittest.main()
