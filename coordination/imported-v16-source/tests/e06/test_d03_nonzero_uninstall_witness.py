"""D03 · never lose first-failure evidence on real NSIS nonzero exit.

SOURCE_ONLY on POSIX: tests original read-only witness invocation with a
disposable manifest fixture. Does not claim Windows INSTALL or E07.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"


def load_smoke():
    spec = importlib.util.spec_from_file_location("nox_d03_nonzero", SMOKE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NonzeroNSISWitness(unittest.TestCase):
    def test_original_nonzero_exit_produces_bounded_readonly_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "installed"
            root.mkdir()
            owned = root / "NOX.P01.Shell.exe"
            owned.write_bytes(b"unchanged-owned-content")
            metadata = root / "payload.sha256.json"
            metadata.write_bytes(b"untouched-metadata")
            foreign = Path(folder) / "user-data.txt"
            foreign.write_bytes(b"FOREIGN_KEEP")
            smoke = load_smoke()
            receipt = smoke.read_only_nonzero_uninstall_witness(
                root, (owned,), None)
            self.assertEqual(
                receipt["disposition"], "DIAGNOSTIC_ONLY_RELEASE_HOLD")
            self.assertFalse(receipt["witness_executed_uninstaller"])
            self.assertFalse(receipt["witness_deleted_files"])
            self.assertEqual(
                receipt["manifest_owned_states"]["PRESENT"], 1)
            self.assertEqual(
                receipt["first_owned_residues"][0]["manifest_relative"],
                "NOX.P01.Shell.exe")
            self.assertEqual(
                receipt["original_nsis_metadata_states"]["payload.sha256.json"],
                "PRESENT")
            self.assertEqual(foreign.read_bytes(), b"FOREIGN_KEEP")
            self.assertEqual(owned.read_bytes(), b"unchanged-owned-content")
            self.assertEqual(metadata.read_bytes(), b"untouched-metadata")

    def test_original_exit_stays_hard_hold_after_diagnostic(self):
        source = SMOKE.read_text(encoding="utf-8")
        guard = 'if uninstalled["code"] != 0:'
        fail = 'require(uninstalled["code"]==0,"T06_CONSERVATIVE_UNINSTALL_EXIT_HOLD")'
        self.assertEqual(source.count(guard), 1)
        self.assertEqual(source.count(fail), 1)
        self.assertLess(source.index(guard), source.index(fail))
        self.assertEqual(source.count('run([str(uninstall),"/S"],220)'), 1)
        self.assertNotIn("shutil.rmtree(", source)


if __name__ == "__main__":
    unittest.main()
