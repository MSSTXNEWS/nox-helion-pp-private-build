"""Offline unit tests for the existing raw E07 receipt admission helper."""
import tempfile
import unittest
from pathlib import Path
from strict_receipt_json_r13 import read_unambiguous


class ReceiptSafety(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "receipt.json"

    def parse(self, content):
        self.path.write_text(content, encoding="utf-8")
        return read_unambiguous(self.path)

    def test_normal_receipt(self):
        result = self.parse('{"schema":"NOX","source":{"sha256":"abc"}}')
        self.assertEqual(result["status"], "RAW_JSON_UNAMBIGUOUS_ONLY")

    def test_repeated_source_digest(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            self.parse('{"source":{"sha256":"one","sha256":"two"}}')

    def test_case_alias(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            self.parse('{"source":{"sha256":"one","Sha256":"two"}}')

    def test_nonfinite_number(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            self.parse('{"ratio":1e9999}')

    def test_no_mutation(self):
        original = '{"schema":"NOX"}'
        self.parse(original)
        self.assertEqual(self.path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
