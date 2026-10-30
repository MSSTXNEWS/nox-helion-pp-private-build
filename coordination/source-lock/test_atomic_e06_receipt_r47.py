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


    def test_reserved_windows_device_names_fail_both_source_gates(self):
        """Reject Win32 device aliases before ZIP read; retain normal names."""
        canonical_spec = importlib.util.spec_from_file_location(
            "nox_original_archive_under_test", module.CANONICAL_VALIDATOR)
        self.assertIsNotNone(canonical_spec)
        canonical = importlib.util.module_from_spec(canonical_spec)
        canonical_spec.loader.exec_module(canonical)
        prohibited = (
            "COM¹", "COM².txt", "COM³", "LPT¹", "LPT².dat", "LPT³",
            "CONIN$", "CONOUT$.log", "nested/COM¹.txt",
        )
        allowed = (
            "COM10.txt", "COMx.txt", "LPT10", "CONSOLE.txt",
            "home/menu/work", "AUXILIARY.txt", "user.txt",
        )
        for name in prohibited:
            with self.subTest(name=name):
                with self.assertRaises(module.SourceHold):
                    module.safe_member(name, False)
                self.assertFalse(canonical.safe_name(name))
        for name in allowed:
            with self.subTest(name=name):
                self.assertEqual(module.safe_member(name, False), name)
                self.assertTrue(canonical.safe_name(name))


    def test_forbidden_windows_filename_characters_match_both_gates(self):
        """E06 safe_member must reject forbidden Win32 chars BEFORE ZIP scanning."""
        canonical_spec = importlib.util.spec_from_file_location(
            "nox_win32_invalid_chars_under_test", module.CANONICAL_VALIDATOR)
        canonical = importlib.util.module_from_spec(canonical_spec)
        canonical_spec.loader.exec_module(canonical)
        forbidden = ("a<b.txt", "a>b.txt", 'a"b.txt', "a|b.txt",
                     "a?b.txt", "a*b.txt", "folder/what?.txt")
        valid = ("home/menu/work", "source_00.part",
                 "assets/approved.png", "folders/name-2026.txt")
        for name in forbidden:
            with self.subTest(unsafe=name):
                with self.assertRaisesRegex(
                        module.SourceHold, "ZIP_WINDOWS_FORBIDDEN_CHARACTER"):
                    module.safe_member(name, False)
                self.assertFalse(canonical.safe_name(name))
        for name in valid:
            with self.subTest(valid=name):
                self.assertEqual(module.safe_member(name, False), name)
                self.assertTrue(canonical.safe_name(name))


    def test_canonical_rejects_double_directory_separator_and_overlong_path(self):
        """Windows ZIP canonical names allow one directory slash, never repeated."""
        canonical_spec = importlib.util.spec_from_file_location(
            "nox_original_archive_under_test", module.CANONICAL_VALIDATOR)
        canonical = importlib.util.module_from_spec(canonical_spec)
        canonical_spec.loader.exec_module(canonical)
        malformed = (("folder//", True), ("folder///", True),
                     ("nested/folder//", True), ("x" * 501, False))
        for name, is_directory in malformed:
            with self.subTest(unsafe=name[:32]):
                self.assertFalse(canonical.safe_name(name))
                with self.assertRaises(module.SourceHold):
                    module.safe_member(name, is_directory)
        valid = (("folder/", True), ("nested/folder/", True),
                 ("x" * 255 + "/" + "y" * 244, False), ("home/menu/work", False))
        for name, is_directory in valid:
            with self.subTest(valid=name[:32]):
                self.assertTrue(canonical.safe_name(name))
                self.assertEqual(module.safe_member(name, is_directory),
                                 name[:-1] if is_directory else name)


    def test_readback_rejects_semantically_equal_mutated_bytes(self):
        """The receipt must match exactly, not merely parse to the same JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock.json"
            real_link = os.link

            def altered_link(source, target):
                result = real_link(source, target)
                # Simulate a post-publish write of legal JSON whitespace.
                # Previous json.loads(readback)==receipt incorrectly passed.
                with open(target, "ab") as stream:
                    stream.write(b" ")
                return result

            with mock.patch("os.link", side_effect=altered_link):
                status, message = self.invoke(out)
            self.assertEqual(status, 2)
            self.assertIn("SOURCELOCK_RECEIPT_READBACK_MISMATCH", message)
            self.assertEqual(json.loads(out.read_bytes())["fileCount"], 729)


    def test_ntfs_utf16_component_limit_and_surrogates(self):
        """Fail closed on >255 UTF-16 units per Windows filename component."""
        canonical_spec = importlib.util.spec_from_file_location(
            "nox_original_archive_under_test", module.CANONICAL_VALIDATOR)
        canonical = importlib.util.module_from_spec(canonical_spec)
        canonical_spec.loader.exec_module(canonical)
        rejected = ("x" * 256, "😀" * 128, "nested/" + "😀" * 128,
                    "bad\ud800")
        accepted = ("x" * 255, "😀" * 127,
                    "x" * 255 + "/" + "y" * 244, "home/menu/work")
        for name in rejected:
            with self.subTest(rejected=name[:24].encode("ascii", "backslashreplace")):
                self.assertFalse(canonical.safe_name(name))
                with self.assertRaises(module.SourceHold):
                    module.safe_member(name, False)
        for name in accepted:
            with self.subTest(accepted=name[:24].encode("ascii", "backslashreplace")):
                self.assertTrue(canonical.safe_name(name))
                self.assertEqual(module.safe_member(name, False), name)



    def test_canonical_publisher_rejects_post_link_receipt_tampering(self):
        """A changed-but-parseable receipt is HOLD, even on direct CLI path."""
        canonical_spec = importlib.util.spec_from_file_location(
            "nox_original_archive_readback", module.CANONICAL_VALIDATOR)
        canonical = importlib.util.module_from_spec(canonical_spec)
        canonical_spec.loader.exec_module(canonical)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "source-lock-direct.json"
            real_link = os.link

            def alter_after_link(source, target):
                result = real_link(source, target)
                with open(target, "ab") as stream:
                    stream.write(b" ")
                return result

            with mock.patch("os.link", side_effect=alter_after_link):
                with self.assertRaisesRegex(
                        ValueError, "OUTPUT_READBACK_BYTES_MISMATCH"):
                    canonical.publish_manifest_exclusive(
                        out, {"schema": "T07_TEST_ONLY", "fileCount": 729})
            self.assertTrue(out.exists())
            self.assertEqual(list(Path(tmp).glob(".nox-source-audit-*")), [])


if __name__ == "__main__":
    unittest.main()
