"""R116: original physical uninstall failure must expose read-only evidence."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
WITNESS = ROOT / "coordination/e06/t06_uninstall_firstfail_witness.py"
OWNER = ROOT / "coordination/e06/t06_uninstall_admission.py"


def owner():
    spec = importlib.util.spec_from_file_location("t06_r116_witness", WITNESS)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class T06FirstFailureWitnessR116(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original-installed"
        self.root.mkdir()
        self.a = self.root / "Accessibility.dll"
        self.b = self.root / "NOX.P01.Shell.exe"
        self.a.write_bytes(b"original")
        self.b.write_bytes(b"immutable")
        self.helper = owner()

    def test_two_leftovers_and_source_pin_mismatch_are_diagnostic_only(self):
        remover = Path(self.temp.name) / "Remove-InstalledPayload.ps1"
        remover.write_bytes(b"not original")
        result = self.helper.read_only_uninstall_failure_snapshot(
            self.root, (self.a, self.b), remover)
        self.assertEqual(result["manifest_owned_states"]["PRESENT"], 2)
        self.assertEqual(result["first_owned_residues"][0]["manifest_relative"], "Accessibility.dll")
        self.assertFalse(result["original_r11_remove_script"]["immutable_r11_pin_match"])
        self.assertEqual(result["disposition"], "DIAGNOSTIC_ONLY_RELEASE_HOLD")
        self.assertFalse(result["witness_deleted_files"])
        self.assertEqual(self.a.read_bytes(), b"original")

    def test_partial_removal_is_distinguishable_from_never_started(self):
        self.b.unlink()
        receipt = self.helper.read_only_uninstall_failure_snapshot(self.root, (self.a, self.b))
        self.assertEqual(receipt["manifest_owned_states"]["PRESENT"], 1)
        self.assertEqual(receipt["manifest_owned_states"]["ABSENT"], 1)
        self.assertEqual(len(receipt["first_owned_residues"]), 1)

    def test_outside_install_file_is_rejected_before_read(self):
        outside = Path(self.temp.name) / "private.txt"
        outside.write_bytes(b"secret")
        with self.assertRaisesRegex(ValueError, "PATH_OUTSIDE"):
            self.helper.read_only_uninstall_failure_snapshot(self.root, (outside,))
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_symlink_residue_is_hold_and_does_not_follow_target(self):
        outside = Path(self.temp.name) / "private.txt"
        outside.write_bytes(b"secret")
        self.b.unlink()
        try:
            self.b.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not available")
        receipt = self.helper.read_only_uninstall_failure_snapshot(self.root, (self.a, self.b))
        self.assertEqual(receipt["manifest_owned_states"]["REPARSE_HOLD"], 1)
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_metadata_residue_is_reported_but_never_removed(self):
        meta = self.root / "payload.sha256.json"
        meta.write_bytes(b"immutable")
        receipt = self.helper.read_only_uninstall_failure_snapshot(self.root, (self.a, self.b))
        self.assertEqual(receipt["original_nsis_metadata_states"]["payload.sha256.json"], "PRESENT")
        self.assertEqual(meta.read_bytes(), b"immutable")

    def test_integrated_original_owner_stays_fail_closed_and_emits_witness(self):
        if not OWNER.is_file():
            self.skipTest("Original private repo owner source is not locally mounted")
        spec = importlib.util.spec_from_file_location("t06_r116_original_owner", OWNER)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            with self.assertRaisesRegex(RuntimeError, "T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS"):
                module.verify_original_uninstall(self.root, (self.a, self.b))
        self.assertIn("T06_UNINSTALL_FIRST_MANIFEST_RESIDUE", stream.getvalue())
        self.assertIn("T06_UNINSTALL_READONLY_FIRSTFAIL_WITNESS", stream.getvalue())
        self.assertEqual(self.a.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
