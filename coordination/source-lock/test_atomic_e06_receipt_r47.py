"""R47 atomic SourceLock receipt regression; synthetic receipt, no original ZIP read."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "e06/verify_original_729_source.py"
spec = importlib.util.spec_from_file_location("nox_e06_receipt_under_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AtomicSourceLockReceiptTests(unittest.TestCase):
    def invoke(self, output):
        with mock.patch.object(module, "verify_original", return_value={
            "schema": "R47_TEST_ONLY", "fileCount": 729, "releaseAccepted": False
        }), mock.patch.object(sys, "argv", ["verify_original_729_source.py",
                                            "--parts-dir", str(output.parent),
                                            "--out", str(output),
                                            "--run-id", "NOX-R47-TEST-ATOMIC"]), contextlib.redirect_stdout(io.StringIO()) as stream:
            code = module.main()
        return code, stream.getvalue()

    def test_success_publishes_complete_receipt_and_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock.json"
            status, message = self.invoke(out)
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["fileCount"], 729)
            self.assertIn(hashlib.sha256(out.read_bytes()).hexdigest(), message)
            self.assertEqual(list(Path(tmp).glob(".nox-source-audit-*")), [])

    def test_denied_final_link_leaves_no_orphan_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock.json"
            with mock.patch("os.link", side_effect=PermissionError("simulated-denial")):
                status, message = self.invoke(out)
            self.assertEqual(status, 2)
            self.assertIn("SOURCELOCK_HOLD", message)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(tmp).glob(".nox-source-audit-*")), [])

    def test_existing_receipt_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock.json"
            out.write_bytes(b"immutable-original")
            status, message = self.invoke(out)
            self.assertEqual(status, 2)
            self.assertEqual(out.read_bytes(), b"immutable-original")

    def test_concurrent_owner_receipt_wins_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock.json"
            true_link = os.link

            def race(source, target):
                Path(target).write_bytes(b"other-owner-receipt")
                return true_link(source, target)

            with mock.patch("os.link", side_effect=race):
                status, message = self.invoke(out)
            self.assertEqual(status, 2)
            self.assertIn("SOURCELOCK_HOLD", message)
            self.assertEqual(out.read_bytes(), b"other-owner-receipt")
            self.assertEqual(list(Path(tmp).glob(".nox-source-audit-*")), [])


if __name__ == "__main__":
    unittest.main()
