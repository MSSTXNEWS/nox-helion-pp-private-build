"""Original EXPRESS OCI offline preflight: never write through a caller-provided reparse alias."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/engines/fetch_ollama_weight_layers.py"
spec = importlib.util.spec_from_file_location("nox_express_oci_root_u12", ENGINE)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class TestOciRootAliasPreflight(unittest.TestCase):
    def _dry(self, root):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.main(["--out", str(root)])

    def test_regular_new_staging_root_preserves_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "new" / "cache"
            self.assertEqual(self._dry(out), 0)
            doc = json.loads((out / "NOX_MODEL_DOWNLOAD_RECEIPT.json").read_text(encoding="utf-8"))
            self.assertTrue(doc["models"])
            self.assertTrue(all(m["status"] == "NOT_DOWNLOADED" and not m["installed"] for m in doc["models"]))

    def test_symlink_leaf_rejected_before_any_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlink creation unavailable on runner")
            with self.assertRaisesRegex(ValueError, "ROOT_REPARSE"):
                self._dry(alias)
            self.assertFalse((real / "NOX_MODEL_DOWNLOAD_RECEIPT.json").exists())

    def test_symlink_parent_rejected_before_mkdir(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlink creation unavailable on runner")
            with self.assertRaisesRegex(ValueError, "ROOT_REPARSE"):
                self._dry(alias / "child")
            self.assertFalse((real / "child").exists())

    def test_dangling_output_link_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            alias = Path(td) / "alias"
            try:
                alias.symlink_to(Path(td) / "missing", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlink creation unavailable on runner")
            with self.assertRaisesRegex(ValueError, "ROOT_REPARSE"):
                self._dry(alias)

    def test_receipt_link_cannot_overwrite_foreign_file(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "root"
            root.mkdir()
            sentinel = base / "user-data.txt"
            sentinel.write_text("PRESERVE", encoding="utf-8")
            try:
                (root / "NOX_MODEL_DOWNLOAD_RECEIPT.json").symlink_to(sentinel)
            except (OSError, NotImplementedError):
                self.skipTest("File symlink creation unavailable on runner")
            with self.assertRaisesRegex(ValueError, "RECEIPT_PATH"):
                self._dry(root)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "PRESERVE")

    def test_regular_file_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            blocked = Path(td) / "file"
            blocked.write_text("PRESERVE", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ROOT_COMPONENT"):
                self._dry(blocked / "cache")
            self.assertEqual(blocked.read_text(encoding="utf-8"), "PRESERVE")


if __name__ == "__main__":
    unittest.main()
