"""B03 R5 · exact-owner path/fd identity with Windows metadata divergence.

SOURCE_ONLY regression. Never treats backup diagnostic as release/E07 acceptance.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_user_probe_slot.py"
SPEC = importlib.util.spec_from_file_location("nox_b03_original_probe_slot", SOURCE)
assert SPEC and SPEC.loader
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)

class TestOriginalOwnedPathHandleIdentity(unittest.TestCase):
    def witness(self, **changes):
        fields = dict(st_dev=7, st_ino=91, st_size=4096, st_nlink=1,
                      st_mtime_ns=11, st_ctime_ns=12)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def test_exact_match(self):
        self.assertTrue(OWNER.owned_file_handle_matches_path(self.witness(), self.witness()))

    def test_cross_api_timestamp_presentation(self):
        self.assertTrue(OWNER.owned_file_handle_matches_path(
            self.witness(), self.witness(st_ctime_ns=43, st_mtime_ns=50)))

    def test_inode_replacement_refused(self):
        self.assertFalse(OWNER.owned_file_handle_matches_path(self.witness(), self.witness(st_ino=92)))

    def test_device_replacement_refused(self):
        self.assertFalse(OWNER.owned_file_handle_matches_path(self.witness(), self.witness(st_dev=8)))

    def test_size_change_refused(self):
        self.assertFalse(OWNER.owned_file_handle_matches_path(self.witness(), self.witness(st_size=13)))

    def test_foreign_hardlink_refused(self):
        self.assertFalse(OWNER.owned_file_handle_matches_path(self.witness(), self.witness(st_nlink=2)))

    def test_inode_zero_refused(self):
        self.assertFalse(OWNER.owned_file_handle_matches_path(self.witness(), self.witness(st_ino=0)))

    def test_probe_same_api_snapshot_stable(self):
        self.assertTrue(OWNER.unchanged_probe_snapshot(self.witness(), self.witness()))

    def test_probe_path_and_handle_api_timestamps_checked_separately(self):
        # A path snapshot can have API-specific timestamps; within each API
        # its own before/after readback must nevertheless remain unchanged.
        path = self.witness(st_mtime_ns=101, st_ctime_ns=102)
        handle = self.witness(st_mtime_ns=201, st_ctime_ns=202)
        self.assertTrue(OWNER.unchanged_probe_snapshot(path, path))
        self.assertTrue(OWNER.unchanged_probe_snapshot(handle, handle))

    def test_probe_in_place_write_timestamp_change_holds(self):
        self.assertFalse(OWNER.unchanged_probe_snapshot(
            self.witness(), self.witness(st_mtime_ns=13)))

    def test_probe_final_metadata_and_identity_change_holds(self):
        for delta in (dict(st_ctime_ns=15), dict(st_ino=92), dict(st_dev=8),
                      dict(st_nlink=2), dict(st_size=4097)):
            with self.subTest(delta=delta):
                self.assertFalse(OWNER.unchanged_probe_snapshot(
                    self.witness(), self.witness(**delta)))

if __name__ == "__main__":
    unittest.main()
