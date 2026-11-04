"""R119: strict read-only uninstall witness must never traverse a redirected ancestor."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_uninstall_firstfail_witness.py"

def load():
    spec=importlib.util.spec_from_file_location("nox_r119_witness",SOURCE)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

class T06UninstallWitnessAncestorGuardR119(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/"installed"
        self.root.mkdir()
        self.outside=self.base/"unrelated"
        self.outside.mkdir()
        self.api=load()

    def link(self, source, target, *, directory):
        try:
            source.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on runner")

    def test_nested_directory_link_is_hold_not_residue(self):
        (self.outside/"Accessibility.dll").write_bytes(b"not an installed payload")
        self.link(self.root/"Backend",self.outside,directory=True)
        receipt=self.api.read_only_uninstall_failure_snapshot(
            self.root,(self.root/"Backend/Accessibility.dll",))
        self.assertEqual(receipt["manifest_owned_states"]["REPARSE_HOLD"],1)
        self.assertEqual(receipt["manifest_owned_states"]["PRESENT"],0)
        self.assertEqual(receipt["first_owned_residues"][0]["state"],"REPARSE_HOLD")
        self.assertEqual((self.outside/"Accessibility.dll").read_bytes(),b"not an installed payload")
        self.assertEqual(receipt["disposition"],"DIAGNOSTIC_ONLY_RELEASE_HOLD")

    def test_root_link_is_hold_for_owned_and_metadata(self):
        (self.outside/"NOX.P01.Shell.exe").write_bytes(b"unrelated")
        (self.outside/"payload.sha256.json").write_bytes(b"unrelated")
        self.root.rmdir()
        self.link(self.root,self.outside,directory=True)
        receipt=self.api.read_only_uninstall_failure_snapshot(
            self.root,(self.root/"NOX.P01.Shell.exe",))
        self.assertEqual(receipt["manifest_owned_states"]["REPARSE_HOLD"],1)
        self.assertEqual(receipt["original_nsis_metadata_states"]["payload.sha256.json"],"REPARSE_HOLD")
        self.assertEqual(receipt["manifest_owned_states"]["PRESENT"],0)
        self.assertFalse(receipt["witness_deleted_files"])

    def test_regular_and_missing_files_still_have_exact_original_states(self):
        payload=self.root/"Accessibility.dll"
        payload.write_bytes(b"installed")
        missing=self.root/"NOX.P01.Shell.exe"
        result=self.api.read_only_uninstall_failure_snapshot(self.root,(payload,missing))
        self.assertEqual(result["manifest_owned_states"]["PRESENT"],1)
        self.assertEqual(result["manifest_owned_states"]["ABSENT"],1)
        self.assertEqual(result["manifest_owned_states"]["REPARSE_HOLD"],0)
        self.assertEqual(payload.read_bytes(),b"installed")

if __name__=="__main__":
    unittest.main()
