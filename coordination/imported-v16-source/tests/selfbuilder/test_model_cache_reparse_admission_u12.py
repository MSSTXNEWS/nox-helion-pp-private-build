"""Regression: NOX EXPRESS OCI content-addressed cache must not follow links."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/engines/fetch_ollama_weight_layers.py"
spec = importlib.util.spec_from_file_location("nox_oci_cache_admission_u12", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ModelCacheAdmission(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "stage"
        self.root.mkdir()
        self.body = b"NOX-EXACT-VERIFIED-LAYER"
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.tag = "sha256:" + self.digest

    def download(self):
        return module.download_blob("qwen2.5-coder", self.tag, len(self.body), self.root)

    def symlink_or_skip(self, link, target, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("host cannot create symlinks: " + str(exc))

    def test_regular_verified_existing_blob_remains_admitted_without_network(self):
        folder = self.root / "blobs"
        folder.mkdir()
        (folder / ("sha256-" + self.digest)).write_bytes(self.body)
        self.assertEqual(self.download()["status"], "ALREADY_SHA256_VERIFIED")

    def test_valid_bytes_through_final_symlink_not_admitted(self):
        outside = self.root / "external"
        outside.write_bytes(self.body)
        folder = self.root / "blobs"
        folder.mkdir()
        self.symlink_or_skip(folder / ("sha256-" + self.digest), outside)
        with self.assertRaisesRegex(ValueError, "UNSAFE_PREEXISTING_BLOB_PATH"):
            self.download()
        self.assertEqual(outside.read_bytes(), self.body)

    def test_dangling_final_symlink_not_replaced(self):
        folder = self.root / "blobs"
        folder.mkdir()
        link = folder / ("sha256-" + self.digest)
        self.symlink_or_skip(link, self.root / "missing")
        with self.assertRaisesRegex(ValueError, "UNSAFE_PREEXISTING_BLOB_PATH"):
            self.download()
        self.assertTrue(link.is_symlink())

    def test_linked_blob_cache_directory_rejected(self):
        destination = self.root / "outside"
        destination.mkdir()
        self.symlink_or_skip(self.root / "blobs", destination, directory=True)
        with self.assertRaisesRegex(ValueError, "UNSAFE_BLOB_CACHE_DIRECTORY"):
            self.download()
        self.assertEqual(list(destination.iterdir()), [])

    def test_non_regular_final_blob_rejected(self):
        folder = self.root / "blobs"
        folder.mkdir()
        (folder / ("sha256-" + self.digest)).mkdir()
        with self.assertRaisesRegex(ValueError, "UNSAFE_PREEXISTING_BLOB_PATH"):
            self.download()

if __name__ == "__main__":
    unittest.main()
