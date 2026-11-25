import unittest
from b0_framework_r80 import FrameworkDeltaBody
from b0_proxy_stream_iter import ProxyDeltaBody
from test_b0_proxy_stream_iter import Upstream, frame
from b0_named_delta_encoder import encode_native_delta


class FrameworkFence(unittest.TestCase):
    def test_cancel_distinct_from_drain(self):
        for started in (False, True):
            for cls in (ProxyDeltaBody, FrameworkDeltaBody):
                with self.subTest(started=started, cls=cls.__name__):
                    src = Upstream([frame("turn2-1", "Привет ¡Hola!"), frame("turn2-2", "later")])
                    body = cls(src)
                    if started:
                        self.assertEqual(next(body), encode_native_delta(frame("turn2-1", "Привет ¡Hola!")))
                    body.close()
                    body.close()
                    for _ in range(2):
                        if cls is ProxyDeltaBody:
                            with self.assertRaises(StopIteration):
                                next(body)
                        else:
                            with self.assertRaisesRegex(RuntimeError, "HOLD_PROXY_FRAMEWORK_CANCELLED"):
                                next(body)
                    self.assertEqual((src.pulls, src.closes), (int(started), 1))

        src = Upstream([frame("turn3-1", "¡Hola!")])
        body = FrameworkDeltaBody(src)
        self.assertEqual(next(body), encode_native_delta(frame("turn3-1", "¡Hola!")))
        with self.assertRaises(StopIteration):
            next(body)
        body.close()
        with self.assertRaises(StopIteration):
            next(body)
        self.assertEqual((src.pulls, src.closes), (2, 1))

        for disposal in (False, True):
            src = Upstream(fail=None if disposal else OSError("lost"),
                           close_fail=StopIteration("broken") if disposal else None)
            body = FrameworkDeltaBody(src)
            with self.assertRaises((OSError, RuntimeError)):
                body.close() if disposal else next(body)
            with self.assertRaisesRegex(RuntimeError, "HOLD_PROXY_FRAMEWORK_FAULT"):
                next(body)
            body.close()
            self.assertEqual((src.pulls, src.closes), (0 if disposal else 1, 1))


if __name__ == "__main__":
    unittest.main()
