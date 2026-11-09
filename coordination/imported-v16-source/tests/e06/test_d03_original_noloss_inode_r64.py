"""D03 SOURCE_ONLY: byte-identical replacement is NOT original-file NO-LOSS."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

OWNER = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"

class D03FrozenUserFileIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("nox_d03_frozen_owner", OWNER)
        owner=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(owner)
        cls.owner=owner

    def test_identical_bytes_with_replaced_inode_are_hold(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            user=root/"owned_user_state.bin"
            user.write_bytes(b"user-state")
            frozen=self.owner.original_no_loss_seed_identity(user,b"user-state",root)
            self.assertTrue(self.owner.original_no_loss_inode_preserved(user,frozen,root))
            foreign=root/"replacement.bin"
            foreign.write_bytes(b"user-state")
            os.replace(foreign,user)
            self.assertTrue(self.owner.original_no_loss_file_preserved(user,b"user-state",root))
            self.assertFalse(self.owner.original_no_loss_inode_preserved(user,frozen,root))

    def test_changed_inode_denied_even_on_uninstall_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            inside=root/"Programs"/"NOX HELION"
            inside.mkdir(parents=True)
            unmanaged=inside/"user-owned.dat"
            unmanaged.write_bytes(b"original")
            frozen=self.owner.original_no_loss_seed_identity(unmanaged,b"original",root)
            unmanaged.unlink()
            unmanaged.write_bytes(b"original")
            self.assertFalse(self.owner.original_no_loss_inode_preserved(unmanaged,frozen,root))

    def test_hardlink_seed_does_not_count_as_exclusive_user_data(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            data=root/"data"
            data.write_bytes(b"original")
            alias=root/"alias"
            try: os.link(data,alias)
            except OSError: self.skipTest("Hardlinks unavailable")
            with self.assertRaisesRegex(RuntimeError,"T06_NOLOSS_SEED_IDENTITY_HOLD"):
                self.owner.original_no_loss_seed_identity(alias,b"original",root)

    def test_source_all_three_phases_require_original_identity(self):
        text=OWNER.read_text(encoding="utf-8")
        for gate in ("T06_UPDATE_MUST_PRESERVE_BINARY_AND_DATA",
                     "T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD",
                     "T06_ORIGINAL_NSIS_UNINSTALL_USER_DATA_LOSS"):
            prefix=text.split('"'+gate+'"')[0][-350:]
            self.assertIn("original_no_loss_inode_preserved",prefix)
        self.assertIn("unmanaged_identity=original_no_loss_seed_identity",text)
        self.assertIn("persistent_safe=(original_no_loss_file_preserved",text)

if __name__ == "__main__":
    unittest.main()
