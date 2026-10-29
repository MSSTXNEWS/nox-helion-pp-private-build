"""G6-A only: a failed SourceLock receipt fsync must never publish partial JSON.

This isolated regression uses a mocked original archive receipt; it does NOT
verify physical 729 ZIP member hashes, the Windows installer, or GitLab CI.
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[5] / "coordination/e06/verify_original_729_source.py"


def load():
    spec = importlib.util.spec_from_file_location("e06_receipt_g6a", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G6AAtomicReceiptTest(unittest.TestCase):
    def test_fsync_failure_does_not_leave_partial_receipt(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "original-729-receipt.json"
            arguments = [
                str(SCRIPT), "--parts-dir", str(root),
                "--out", str(output), "--run-id", "G6A-ATOMIC-FAULT-01",
            ]
            fixture = {
                "schema": "TEST_RECEIPT_ONLY_NOT_ORIGINAL_ARCHIVE",
                "fileCount": 729,
                "releaseAccepted": False,
            }
            with mock.patch.object(module, "verify_original", return_value=fixture), \
                 mock.patch.object(sys, "argv", arguments), \
                 mock.patch.object(os, "fsync", side_effect=OSError("injected disk failure")):
                self.assertEqual(module.main(), 2)
            self.assertFalse(output.exists(), "partial receipt must not be discoverable")
            self.assertFalse(list(root.glob(".nox-source-audit-*.tmp")),
                             "failed publication must clean its private temp files")


if __name__ == "__main__":
    unittest.main()
