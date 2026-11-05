"""SOURCE_ONLY G4 regression: user marker identity across NSIS update/rollback/uninstall."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"


def load_original_owner():
    spec = importlib.util.spec_from_file_location("nox_b03_marker_owner", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("B03_G4_ORIGINAL_OWNER_IMPORT_HOLD")
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    return owner


class G4ReadOnlyUserMarker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = load_original_owner()

    def test_all_three_post_update_rollback_uninstall_gates_fail_closed(self):
        src = SOURCE.read_text("utf-8")
        self.assertNotIn("marker.read_bytes()==signature", src)
        for gate in ("T06_UPDATE_MUST_PRESERVE_BINARY_AND_DATA",
                     "T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD",
                     "T06_ORIGINAL_NSIS_UNINSTALL_USER_DATA_LOSS"):
            self.assertIn("original_no_loss_file_preserved(marker,signature,local_base)",
                          src.split('"' + gate + '"')[0][-280:])
        self.assertIn("T06_CONSERVATIVE_UNINSTALL_EXIT_HOLD", src)
        self.assertIn("T06_NOLOSS_UNMANAGED_INSTALL_DATA_LOST", src)

    def test_in_install_unmanaged_data_is_checked_from_update_through_uninstall(self):
        src = SOURCE.read_text("utf-8")
        seed = src.index("unmanaged_identity=original_no_loss_seed_identity(")
        update = src.index('update=run([str(SETUP),"/S"],250)')
        backup = src.index('"T06_UPDATE_UNMANAGED_USER_DATA_LOSS"')
        rollback = src.index('rollback=run([str(SETUP),"/S","/ROLLBACK"],250)')
        restored = src.index('"T06_ROLLBACK_UNMANAGED_USER_DATA_LOSS"')
        uninstall = src.index('uninstalled=run([str(uninstall),"/S"],220)')
        last = src.index('"T06_NOLOSS_UNMANAGED_INSTALL_DATA_LOST"')
        self.assertTrue(0 <= seed < update < backup < rollback < restored < uninstall < last)
        self.assertIn("original_no_loss_inode_preserved(unmanaged_backup,unmanaged_identity,local_base)", src)
        self.assertIn("original_no_loss_inode_preserved(unmanaged,unmanaged_identity,local_base)", src)
        self.assertIn('report["installer_lifecycle"]["update_unmanaged_user_data"]="PRESERVED_IN_BACKUP"', src)
        self.assertIn('report["installer_lifecycle"]["rollback_unmanaged_user_data"]="PRESERVED_IN_RESTORED_INSTALL"', src)

    def test_exact_user_file_and_modified_contents(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            marker=base/"state.txt"
            marker.write_bytes(b"original user data")
            self.assertTrue(self.owner.original_no_loss_file_preserved(marker,b"original user data",base))
            marker.write_bytes(b"modified user data")
            self.assertFalse(self.owner.original_no_loss_file_preserved(marker,b"original user data",base))

    def test_symlink_to_identical_bytes_is_not_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            original=base/"original.txt"
            original.write_bytes(b"identical content")
            marker=base/"user.txt"
            try:
                marker.symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("Windows unprivileged symlinks unavailable")
            self.assertFalse(self.owner.original_no_loss_file_preserved(marker,b"identical content",base))

    def test_parent_directory_redirect_is_not_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            real=base/"real"
            real.mkdir()
            (real/"marker.txt").write_bytes(b"identical content")
            link=base/"redirect"
            try:
                link.symlink_to(real,target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Windows unprivileged directory symlinks unavailable")
            self.assertFalse(self.owner.original_no_loss_file_preserved(link/"marker.txt",b"identical content",base))


if __name__ == "__main__":
    unittest.main()
