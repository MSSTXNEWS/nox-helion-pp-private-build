"""B03 G4 physical-manifest identity regressions; SOURCE_ONLY, not E07.

Tests the imported original verifier helper on real local filesystem objects,
including a controlled same-inode write-race witness.
"""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06"))
from t06_user_probe_slot import read_stable_manifest_bytes


class G4StableManifest(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.file = self.root / "payload.sha256.json"
        self.expected = b'{"files":[]}'
        self.file.write_bytes(self.expected)

    def test_original_manifest_is_read_through_one_handle(self):
        self.assertEqual(read_stable_manifest_bytes(self.file), self.expected)

    def test_same_inode_handle_write_race_fails_closed(self):
        original = os.fstat
        calls = [0]
        def witness(fd):
            value = original(fd)
            calls[0] += 1
            if calls[0] != 2:
                return value
            fields = ("st_dev", "st_ino", "st_size", "st_nlink",
                      "st_mtime_ns", "st_ctime_ns")
            changed = {name: getattr(value, name) for name in fields}
            changed["st_mtime_ns"] += 999999999
            return SimpleNamespace(**changed)
        with patch("os.fstat", side_effect=witness):
            with self.assertRaisesRegex(RuntimeError, "MANIFEST_RACE_HOLD"):
                read_stable_manifest_bytes(self.file)
        self.assertEqual(calls[0], 2)

    def test_hard_link_to_external_file_fails_closed(self):
        os.link(self.file, self.root / "other.bin")
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_IDENTITY_HOLD"):
            read_stable_manifest_bytes(self.file)

    def test_symlink_substitution_fails_closed(self):
        other = self.root / "other.bin"
        self.file.rename(other)
        try:
            self.file.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not allowed")
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_IDENTITY_HOLD"):
            read_stable_manifest_bytes(self.file)

    def test_empty_manifest_fails_closed(self):
        self.file.write_bytes(b"")
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_IDENTITY_HOLD"):
            read_stable_manifest_bytes(self.file)


if __name__ == "__main__":
    main()
