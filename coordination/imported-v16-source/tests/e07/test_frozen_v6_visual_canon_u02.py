"""Negative guards are synthetic; the integration invocation uses real GitHub images."""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e07"))
import audit_frozen_v6_visual_canon_u02 as q

class VisualReceiptTests(unittest.TestCase):
    def test_source_pin_and_sha(self):
        self.assertEqual(len(q.SOURCE), 40)
        self.assertEqual(len(q.SETUP), 64)
        self.assertNotEqual(q.PNG1, q.PNG2)
    def test_duplicate_key_refused(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.json"
            f.write_text('{"setup_sha256":"x","setup_sha256":"y"}', encoding="utf8")
            with self.assertRaisesRegex(q.Hold, "DUPLICATE"):
                q.load_json(f)
    def test_nonfinite_json_refused(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.json"
            f.write_text('{"x": NaN}', encoding="utf8")
            with self.assertRaisesRegex(q.Hold, "NONFINITE"):
                q.load_json(f)
    def test_missing_png_refused(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(q.Hold, "PNG_HOLD"):
                q.check_png(Path(tmp) / "absent.png", q.PNG1)
    def test_linked_receipt_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.json"; a.write_text('{"hi":1}', encoding="utf8")
            b = root / "b.json"; b.symlink_to(a)
            with self.assertRaisesRegex(q.Hold, "PATH_HOLD"):
                q.load_json(b)
    def test_bad_receipt_rejected_before_image(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.json"; b = root / "b.json"
            a.write_text('{}', encoding='utf8'); b.write_text('{}', encoding='utf8')
            with self.assertRaisesRegex(q.Hold, "PROVENANCE_HOLD"):
                q.review(root / "first.png", a, root / "second.png", b)

if __name__ == '__main__': unittest.main()
