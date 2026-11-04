"""R108: exact first manifest-owned uninstall residue is diagnostic only.

These offline filesystem tests cannot certify native Windows or E07.
"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e06"))
from t06_uninstall_admission import verify_original_uninstall


class NoKeys:
    HKEY_CURRENT_USER=object()
    KEY_WOW64_32KEY=0x200
    KEY_WOW64_64KEY=0x100
    KEY_READ=0x20019

    def OpenKey(self,*_):
        raise FileNotFoundError("absent")


class ResidueDiagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install=Path(self.tmp.name)/"NOX HELION"
        self.install.mkdir()

    def test_first_manifest_residue_is_escaped_relative_and_still_hold(self):
        owned=self.install/"Assets"/"remaining.bin"
        owned.parent.mkdir()
        owned.write_bytes(b"original")
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaisesRegex(RuntimeError,"^T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS$"):
                verify_original_uninstall(self.install,(owned,),NoKeys())
        self.assertIn('"Assets/remaining.bin"',output.getvalue())
        self.assertNotIn(str(self.install),output.getvalue())
        self.assertTrue(owned.is_file())

    def test_manifest_residue_symlink_denied_and_not_followed(self):
        outside=Path(self.tmp.name)/"safe-untracked.dat"
        outside.write_bytes(b"untracked")
        owner=self.install/"linked-owned.bin"
        owner.symlink_to(outside)
        with contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError,"MANIFEST_FILE_REMAINS"):
                verify_original_uninstall(self.install,(owner,),NoKeys())
        self.assertEqual(outside.read_bytes(),b"untracked")
        self.assertIn('"linked-owned.bin"', output.getvalue())
        self.assertNotIn(str(outside), output.getvalue())

    def test_long_manifest_name_is_bounded_without_install_path_leak(self):
        owned=self.install/('A'*180+'.bin')
        owned.write_bytes(b"original")
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaisesRegex(RuntimeError,"^T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS$"):
                verify_original_uninstall(self.install,(owned,),NoKeys())
        self.assertIn('T06_UNINSTALL_FIRST_MANIFEST_RESIDUE',output.getvalue())
        self.assertNotIn(str(self.install),output.getvalue())
        self.assertNotIn('A'*161,output.getvalue())
        self.assertTrue(owned.is_file())

    def test_clean_owned_removal_never_deletes_untracked_file(self):
        owned=self.install/'already-removed.bin'
        personal=self.install/'personal-untracked.bin'
        personal.write_bytes(b"user")
        verify_original_uninstall(self.install,(owned,),NoKeys())
        self.assertEqual(personal.read_bytes(),b"user")


if __name__ == "__main__":
    unittest.main()
