"""NOX V10: bounded, no-I/O fixture regressions for model inventory admission."""
from __future__ import annotations
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "nox_owner_native_audit_under_test", Path(__file__).with_name("owner_native_audit.py")
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PinnedModelInventoryAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "models"
        self.root.mkdir()
        self.first = self.root / audit.PINNED_MODEL_FILES[0][0]

    def test_missing_files_are_not_claimed_verified(self):
        row = audit.pinned_model_paths(str(self.root))
        self.assertEqual(row["status"], "HOLD_MODEL_FILES_MISSING")  # No files: not admitted.
        self.assertEqual(len(row["files"]), len(audit.PINNED_MODEL_FILES))
        self.assertTrue(all(f["sha_status"] == "NOT_CHECKED" for f in row["files"]))
        self.assertTrue(all(f["type"] == "missing" for f in row["files"]))

    def test_all_expected_sizes_are_not_a_verified_model_without_sha(self):
        # Simulate six matching size metadata rows without allocating 248GB.
        # Lstat is intentionally metadata-only; no payload content is hashed.
        import stat
        from types import SimpleNamespace

        sizes = {
            str(self.root / name): size
            for name, size, _ in audit.PINNED_MODEL_FILES
        }

        def matching_size_lstat(path):
            path = str(path)
            if path in sizes:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_size=sizes[path])
            return os.lstat(path)

        row = audit.pinned_model_paths(str(self.root), lstat=matching_size_lstat)
        self.assertEqual(row["status"], "HOLD_MODEL_SHA_UNVERIFIED")
        self.assertEqual(len(row["files"]), 6)
        self.assertTrue(all(f["size_status"] == "MATCH" for f in row["files"]))
        self.assertTrue(all(f["sha_status"] == "NOT_CHECKED" for f in row["files"]))

    def test_nonexistent_model_root_is_not_reported_ok(self):
        absent = self.root / "not_created"
        row = audit.pinned_model_paths(str(absent))
        self.assertEqual(row["status"], "HOLD_MODEL_FILES_MISSING")
        self.assertEqual(len(row["files"]), len(audit.PINNED_MODEL_FILES))
        self.assertTrue(all(f["type"] == "missing" for f in row["files"]))
        self.assertTrue(all(f["sha_status"] == "NOT_CHECKED" for f in row["files"]))

    def test_permission_denied_target_fails_closed(self):
        denied = str(self.root / audit.PINNED_MODEL_FILES[1][0])

        def denied_lstat(path):
            if str(path) == denied:
                raise PermissionError(13, "read forbidden", denied)
            return os.lstat(path)

        row = audit.pinned_model_paths(str(self.root), lstat=denied_lstat)
        self.assertEqual(row["status"], "HOLD_MODEL_PATH_STAT_PERMISSIONERROR")
        self.assertEqual(row["files"][1]["type"], "unknown")
        self.assertNotEqual(row["status"], "OK")

    def test_regular_file_as_model_root_is_hold(self):
        bad_root = Path(self.tmp.name) / "not_a_directory"
        bad_root.write_text("fixture")
        row = audit.pinned_model_paths(str(bad_root))
        self.assertEqual(row["status"], "HOLD_MODEL_ROOT_COMPONENT_TYPE")

    def test_bad_size_is_not_clean_inventory(self):
        self.first.write_bytes(b"x")
        row = audit.pinned_model_paths(str(self.root))
        self.assertEqual(row["status"], "HOLD_MODEL_FILE_SIZE_MISMATCH")
        self.assertEqual(row["files"][0]["size_status"], "MISMATCH")

    def test_directory_instead_of_weight_is_hold(self):
        self.first.mkdir()
        row = audit.pinned_model_paths(str(self.root))
        self.assertEqual(row["status"], "HOLD_MODEL_TARGET_TYPE")

    def test_symlinked_candidate_still_has_priority(self):
        self.first.symlink_to("missing")
        row = audit.pinned_model_paths(str(self.root))
        self.assertEqual(row["status"], "HOLD_MODEL_PATH_SYMLINK")


if __name__ == "__main__":
    unittest.main()
