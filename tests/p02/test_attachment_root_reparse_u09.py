"""Windows-junction and ancestor fail-closed admissions for existing P02Store.

These are local source tests; they do not prove installed Windows/OneHost E07.
"""
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Packages" / "P02" / "worker-python"))
from p02_runtime import P02Error, P02Store, _safe_blob_path


class AttachmentReparseU09(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)

    @staticmethod
    def junction(target):
        original = getattr(pathlib.Path, "is_junction", lambda path: False)
        return patch.object(pathlib.Path, "is_junction",
                            lambda path: path == target or original(path), create=True)

    def test_regular_store_root_unchanged(self):
        store = P02Store(self.db, self.root / "app")
        self.assertTrue(store.blobs.is_dir())
        store._assert_storage_roots()
        self.assertEqual(_safe_blob_path(store.blobs, "a" * 32).parent, store.blobs)

    def test_root_junction_denied_before_resolve(self):
        path = self.root / "app"
        with self.junction(path), self.assertRaisesRegex(P02Error, "ROOT_REPARSE_DENIED"):
            P02Store(self.db, path)

    def test_parent_junction_denied_before_resolve(self):
        parent = self.root / "redirect"
        with self.junction(parent), self.assertRaisesRegex(P02Error, "ROOT_REPARSE_DENIED"):
            P02Store(self.db, parent / "app")

    def test_existing_staging_junction_denied(self):
        path = self.root / "app" / "staging"
        with self.junction(path), self.assertRaisesRegex(P02Error, "STORAGE_SYMLINK_DENIED"):
            P02Store(self.db, self.root / "app")

    def test_existing_stored_junction_denied(self):
        path = self.root / "app" / "stored"
        with self.junction(path), self.assertRaisesRegex(P02Error, "STORAGE_SYMLINK_DENIED"):
            P02Store(self.db, self.root / "app")

    def test_post_start_parent_alias_denied_on_recheck(self):
        store = P02Store(self.db, self.root / "app")
        with self.junction(store.root.parent), self.assertRaisesRegex(P02Error, "OUTSIDE_APPROVED_ROOT"):
            store._assert_storage_roots()

    def test_post_start_storage_alias_denied_on_recheck(self):
        store = P02Store(self.db, self.root / "app")
        with self.junction(store.blobs), self.assertRaisesRegex(P02Error, "OUTSIDE_APPROVED_ROOT"):
            store._assert_storage_roots()

    def test_blob_junction_denied(self):
        store = P02Store(self.db, self.root / "app")
        candidate = store.blobs / ("f" * 32 + ".blob")
        with self.junction(candidate), self.assertRaisesRegex(P02Error, "reparse"):
            _safe_blob_path(store.blobs, "f" * 32)

    def test_real_symlink_parent_denied(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation not permitted on runner")
        with self.assertRaisesRegex(P02Error, "ROOT_REPARSE_DENIED"):
            P02Store(self.db, link / "app")


if __name__ == "__main__":
    unittest.main()
