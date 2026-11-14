"""Exact-source T06 provenance JSON overflow regression; NOT Windows/E07 proof."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_source_receipt_guard.py"
spec = importlib.util.spec_from_file_location("nox_t06_receipt_r61", MODULE)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class ReceiptNumericAdmissionTests(unittest.TestCase):
    def read(self, raw: bytes):
        with tempfile.TemporaryDirectory() as directory:
            proof = Path(directory) / "native-owner.json"
            proof.write_bytes(raw)
            return source._receipt(proof)

    def test_overflowing_positive_exponent_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_RECEIPT_INVALID_JSON"):
            self.read(b'{"source":{"age":1e9999}}')

    def test_overflowing_negative_exponent_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_RECEIPT_INVALID_JSON"):
            self.read(b'{"nested":[{"v":-1e9999}]}')

    def test_finite_exponent_and_small_float_admitted(self):
        result = self.read(b'{"a":2.25e3,"b":-1.5e-3,"ok":true}')
        self.assertEqual(result, {"a":2250.0,"b":-0.0015,"ok":True})

    def test_duplicate_keys_still_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_RECEIPT_INVALID_JSON"):
            self.read(b'{"route":"models","route":"owner"}')

    def test_literal_nonfinite_still_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_RECEIPT_INVALID_JSON"):
            self.read(b'{"value":NaN}')


if __name__ == "__main__":
    unittest.main()
