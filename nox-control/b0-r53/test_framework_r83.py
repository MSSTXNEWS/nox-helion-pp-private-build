"""Regression against immutable R80 constructor and R83 successor."""
import unittest
from b0_framework_r80 import FrameworkDeltaBody as Old
from b0_framework_r83 import FrameworkDeltaBody as New


class Up:
    def __init__(self, init_error=None, close_error=None):
        self.init_error = init_error
        self.close_error = close_error
        self.reads = self.closed = 0

    def __iter__(self):
        if self.init_error is not None:
            raise self.init_error
        return self

    def __next__(self):
        self.reads += 1
        raise StopIteration

    def close(self):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class FrameworkInit(unittest.TestCase):
    def test_constructor_fence(self):
        old = Up(StopIteration())
        with self.assertRaises(StopIteration):
            Old(old)
        self.assertEqual((old.closed, old.reads), (0, 0))
        for err, cleanup, expected, message in (
            (StopIteration(), None, RuntimeError, "HOLD_PROXY_FRAMEWORK_INIT_FALSE_EOF"),
            (OSError("upstream"), None, OSError, "upstream"),
            (StopIteration(), StopIteration(), RuntimeError, "HOLD_PROXY_FRAMEWORK_INIT_CLOSE_FALSE_EOF"),
            (OSError("upstream"), StopIteration(), RuntimeError, "HOLD_PROXY_FRAMEWORK_INIT_CLOSE_FALSE_EOF"),
            (StopIteration(), OSError("dispose"), OSError, "dispose"),
        ):
            with self.subTest(err=type(err), cleanup=type(cleanup)):
                up = Up(err, cleanup)
                with self.assertRaisesRegex(expected, message):
                    New(up)
                self.assertEqual((up.closed, up.reads), (1, 0))
        up = Up()
        body = New(up)
        self.assertEqual(list(body), [])
        body.close()
        self.assertEqual((up.closed, up.reads), (1, 1))
        up = Up()
        body = New(up)
        body.close()
        with self.assertRaisesRegex(RuntimeError, "HOLD_PROXY_FRAMEWORK_CANCELLED"):
            next(body)
        self.assertEqual((up.closed, up.reads), (1, 0))


if __name__ == "__main__":
    unittest.main()
