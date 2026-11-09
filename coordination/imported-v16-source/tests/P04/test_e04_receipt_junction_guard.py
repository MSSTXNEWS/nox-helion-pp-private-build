"""E04 R10: real P04 receipt writer must reject junction/symlink diversion."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
SPEC = importlib.util.spec_from_file_location("nox_e04_r10_train_qlora", SOURCE)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class ReceiptJunctionGuard(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "approved-run"
        self.output.mkdir()
        self.receipt = {"schema": "NOX-QLORA-TRAINING-RECEIPT-v2",
                        "run_id": "test-R10", "status": "PAUSED"}

    def payload(self):
        return (json.dumps(self.receipt, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")

    def try_symlink(self, link, target, is_dir=False):
        try:
            link.symlink_to(target, target_is_directory=is_dir)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("filesystem symlink privilege unavailable: " + str(exc))

    def test_regular_archive_and_latest_match_digest(self):
        digest, latest = worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(digest, hashlib.sha256(self.payload()).hexdigest())
        self.assertEqual(latest.read_bytes(), self.payload())
        self.assertEqual((self.output / "receipts" / (digest + ".json")).read_bytes(), self.payload())

    def test_repeated_identical_receipt_remains_valid(self):
        first, _ = worker.write_training_receipt(self.output, self.receipt)
        second, _ = worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(first, second)
        self.assertEqual(len(list((self.output / "receipts").iterdir())), 1)

    def test_symlinked_archive_directory_refuses_before_writing(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.try_symlink(self.output / "receipts", outside, is_dir=True)
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_latest_refuses_before_archive_created(self):
        victim = self.root / "victim.txt"
        victim.write_text("UNCHANGED", encoding="utf-8")
        self.try_symlink(self.output / "training-receipt.json", victim)
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(victim.read_text(encoding="utf-8"), "UNCHANGED")
        self.assertFalse((self.output / "receipts").exists())

    def test_symlinked_digest_leaf_refuses_to_follow(self):
        digest = hashlib.sha256(self.payload()).hexdigest()
        archive_dir = self.output / "receipts"
        archive_dir.mkdir()
        victim = self.root / "victim.json"
        victim.write_text("UNCHANGED", encoding="utf-8")
        self.try_symlink(archive_dir / (digest + ".json"), victim)
        with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
            worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(victim.read_text(encoding="utf-8"), "UNCHANGED")
        self.assertFalse((self.output / "training-receipt.json").exists())

    def test_windows_reparse_attribute_on_receipts_detected(self):
        archive_dir = self.output / "receipts"
        archive_dir.mkdir()
        real_lstat = Path.lstat

        def synthetic_windows_lstat(path, *args, **kwargs):
            original = real_lstat(path, *args, **kwargs)
            if path == archive_dir:
                return types.SimpleNamespace(st_mode=original.st_mode,
                                             st_file_attributes=0x400)
            return original

        with mock.patch.object(worker.stat, "FILE_ATTRIBUTE_REPARSE_POINT",
                               0x400, create=True), mock.patch.object(
                               Path, "lstat", synthetic_windows_lstat):
            with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
                worker.write_training_receipt(self.output, self.receipt)
        self.assertFalse((self.output / "training-receipt.json").exists())

    def test_windows_reparse_attribute_on_latest_detected(self):
        latest = self.output / "training-receipt.json"
        latest.write_text("UNCHANGED", encoding="utf-8")
        real_lstat = Path.lstat

        def synthetic_windows_lstat(path, *args, **kwargs):
            original = real_lstat(path, *args, **kwargs)
            if path == latest:
                return types.SimpleNamespace(st_mode=original.st_mode,
                                             st_file_attributes=0x400)
            return original

        with mock.patch.object(worker.stat, "FILE_ATTRIBUTE_REPARSE_POINT",
                               0x400, create=True), mock.patch.object(
                               Path, "lstat", synthetic_windows_lstat):
            with self.assertRaisesRegex(ValueError, "P04_PATH_REPARSE_ANCESTOR"):
                worker.write_training_receipt(self.output, self.receipt)
        self.assertEqual(latest.read_text(encoding="utf-8"), "UNCHANGED")
        self.assertFalse((self.output / "receipts").exists())


if __name__ == "__main__":
    unittest.main()
