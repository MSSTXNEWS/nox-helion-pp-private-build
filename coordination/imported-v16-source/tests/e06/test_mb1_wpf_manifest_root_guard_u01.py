"""Regression of MB1 exact 28-part WPF donor namespace; original archive untouched."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/mb1_extract_original_sources.py"
spec = importlib.util.spec_from_file_location("mb1_owner_manifest_u01", MODULE)
mb1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb1)


class OriginalDonorNamespace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.owner = self.root / "donors/P01_C07"
        self.owner.mkdir(parents=True)
        self.rows = []
        all_bytes = bytearray()
        for index in range(28):
            raw = ("NOX-R11-PART-%02d\n" % index).encode("ascii")
            (self.owner / ("P01_C07_%02d.part" % index)).write_bytes(raw)
            self.rows.append({"path": "donors/P01_C07/P01_C07_%02d.part" % index,
                              "size_bytes": len(raw),
                              "git_blob_sha1": mb1.git_blob(raw)})
            all_bytes.extend(raw)
        self.expected = bytes(all_bytes)
        self.digest = hashlib.sha256(self.expected).hexdigest()
        self.outside = Path(self.temp.name) / "outside_00.part"
        shutil.copyfile(self.owner / "P01_C07_00.part", self.outside)
        self.manifest = self.owner / "P01_C07_RECEIPT.json"
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps({
            "parts": self.rows,
            "original_zip_bytes": len(self.expected)
        }), encoding="utf-8")

    def join(self):
        # The fixture replaces ONLY the physical SourceLock reader. The real
        # reader retains its separate dev/ino/ctime/path/reparse regressions.
        with patch.object(mb1, "ROOT", self.root), \
             patch.object(mb1, "WPFZIP", self.digest), \
             patch.object(mb1, "_owner_part_reader", return_value=lambda p: open(p, "rb")):
            return mb1.join_and_verify_wpf().getvalue()

    def test_exact_original_order_is_still_accepted(self):
        self.assertEqual(self.join(), self.expected)

    def test_parent_traversal_even_with_identical_part_bytes_is_rejected(self):
        self.rows[0]["path"] = "../outside_00.part"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "MB1_WPF_PART_PATH_HOLD"):
            self.join()

    def test_absolute_path_even_with_identical_part_bytes_is_rejected(self):
        self.rows[0]["path"] = str(self.outside)
        self.save()
        with self.assertRaisesRegex(RuntimeError, "MB1_WPF_PART_PATH_HOLD"):
            self.join()

    def test_alias_inside_root_is_rejected(self):
        self.rows[0]["path"] = "donors/P01_C07/../P01_C07/P01_C07_00.part"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "MB1_WPF_PART_PATH_HOLD"):
            self.join()

    def test_truncated_part_manifest_is_rejected(self):
        self.rows.pop()
        self.save()
        with self.assertRaisesRegex(RuntimeError, "MB1_WPF_PART_MANIFEST_HOLD"):
            self.join()

    def test_non_object_part_is_rejected_before_open(self):
        self.rows[0] = "donors/P01_C07/P01_C07_00.part"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "MB1_WPF_PART_PATH_HOLD"):
            self.join()


if __name__ == "__main__":
    unittest.main()
