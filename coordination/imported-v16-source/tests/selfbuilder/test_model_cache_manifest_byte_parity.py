"""Original NOX model-cache OCI byte parity: offline regression, NO downloading."""
from pathlib import Path
import hashlib
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/nox_selfbuilder/engines/fetch_ollama_weight_layers.py"
spec = importlib.util.spec_from_file_location("nox_oci_cache_under_test", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TAG = "qwen2.5-coder:7b"

class ModelManifestByteParity(unittest.TestCase):
    def _mock_acquire(self, directory, raw, digest):
        model = dict(mod.MODELS[TAG])
        model["display_digest_prefix"] = digest[:12]
        with patch.dict(mod.MODELS, {TAG: model}), \
             patch.object(mod, "manifest_and_blobs", return_value=(raw, digest, [])), \
             patch.object(mod.shutil, "disk_usage", return_value=SimpleNamespace(free=7 * 1024**3)):
            return mod.acquire(TAG, directory, execute=True)

    def test_cached_manifest_is_identical_to_registry_signed_bytes(self):
        # Real OCI JSON may contain indentation, order and trailing whitespace.
        # Re-dumping JSON has a different SHA and cannot be called byte-pinned.
        raw = b'{\n  "schemaVersion": 2, "layers": [], "config": {}\n}\n'
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache"
            receipt = self._mock_acquire(root, raw, digest)
            manifest = root / "manifests/registry.ollama.ai/library/qwen2.5-coder/7b"
            self.assertEqual(manifest.read_bytes(), raw)
            self.assertEqual(receipt["manifest_sha256"], digest)
            self.assertEqual(receipt["manifest_file_sha256"], digest)
            self.assertEqual(receipt["status"], "DOWNLOADED_ALL_LAYERS_SHA256_VERIFIED")
            self.assertFalse(receipt["installed"])
            self.assertFalse(receipt["integrated"])
            self.assertIn("REVIEW", receipt["license_status"])

    def test_mismatched_registry_byte_digest_never_publishes(self):
        raw = b'{"schemaVersion":2,"layers":[]}'
        forged_digest = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache"
            with self.assertRaisesRegex(ValueError, "OFFICIAL_MANIFEST_BYTE_IDENTITY_MISMATCH"):
                self._mock_acquire(root, raw, forged_digest)
            target = root / "manifests/registry.ollama.ai/library/qwen2.5-coder/7b"
            self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
