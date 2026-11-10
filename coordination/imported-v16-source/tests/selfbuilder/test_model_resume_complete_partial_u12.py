"""P04 real model cache recovery without network/rights promotion or Ollama install."""
import hashlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/engines/fetch_ollama_weight_layers.py"
spec = importlib.util.spec_from_file_location("nox_p04_resume_u12", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BYTES = b"valid model artifact bytes: 0123456789"
SHA = hashlib.sha256(BYTES).hexdigest()
DIGEST = "sha256:" + SHA

class FakeResponse:
    status = 200
    def __init__(self, data):
        self.reader = io.BytesIO(data)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def getcode(self):
        return self.status
    def read(self, n):
        return self.reader.read(n)
    def close(self):
        pass

class CompletePartialRecovery(unittest.TestCase):
    def test_verified_complete_partial_recovers_without_http_416(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "blobs"
            folder.mkdir()
            (folder / (".partial-" + SHA)).write_bytes(BYTES)
            with patch.object(mod, "secure_open", side_effect=AssertionError("network must not run")):
                proof = mod.download_blob("model", DIGEST, len(BYTES), root)
            self.assertEqual(proof["status"], "RECOVERED_COMPLETE_SHA256_VERIFIED")
            self.assertEqual((folder / ("sha256-" + SHA)).read_bytes(), BYTES)

    def test_corrupt_complete_partial_quarantined_and_fresh_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "blobs"
            folder.mkdir()
            original = b"X" * len(BYTES)
            (folder / (".partial-" + SHA)).write_bytes(original)
            with patch.object(mod, "secure_open", return_value=FakeResponse(BYTES)) as request:
                proof = mod.download_blob("model", DIGEST, len(BYTES), root)
            self.assertEqual(proof["status"], "DOWNLOADED_SHA256_VERIFIED")
            self.assertEqual((folder / ("sha256-" + SHA)).read_bytes(), BYTES)
            self.assertEqual(next(folder.glob(".corrupt-" + SHA + "-*")).read_bytes(), original)
            self.assertNotIn("Range", request.call_args.kwargs["headers"])

    def test_symlink_partial_refused_and_external_bytes_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "blobs"
            folder.mkdir()
            outside = root / "external"
            outside.write_bytes(BYTES)
            try:
                (folder / (".partial-" + SHA)).symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("platform cannot create a symlink")
            with patch.object(mod, "secure_open", side_effect=AssertionError("no HTTP")):
                with self.assertRaisesRegex(ValueError, "UNSAFE_PARTIAL_BLOB_PATH"):
                    mod.download_blob("model", DIGEST, len(BYTES), root)
            self.assertEqual(outside.read_bytes(), BYTES)

if __name__ == "__main__":
    unittest.main()
