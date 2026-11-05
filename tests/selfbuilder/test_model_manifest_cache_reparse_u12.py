"""Offline OCI manifest cache admission; never counts as model/Windows E07 PASS."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/engines/fetch_ollama_weight_layers.py"
SPEC = importlib.util.spec_from_file_location("nox_manifest_guard_u12", SOURCE)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
TAG = "qwen2.5-coder:7b"
RAW = b'{"schemaVersion":2,"layers":[]}'
DIGEST = hashlib.sha256(RAW).hexdigest()

class ManifestStoreGuard(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "cache"
        self.root.mkdir()
        self.outside = Path(t.name) / "outside"
        self.outside.mkdir()

    def target(self):
        return mod.manifest_cache_target(self.root, "qwen2.5-coder", "7b")

    def link(self, link, target, directory=True):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as e:
            self.skipTest("symlink unavailable: " + str(e))

    def acquire(self):
        model = dict(mod.MODELS[TAG])
        model["display_digest_prefix"] = DIGEST[:12]
        with patch.dict(mod.MODELS, {TAG:model}):
            with patch.object(mod, "manifest_and_blobs", return_value=(RAW, DIGEST, [])):
                with patch.object(mod.shutil, "disk_usage", return_value=SimpleNamespace(free=7*1024**3)):
                    return mod.acquire(TAG, self.root, execute=True)

    def test_regular_cache(self):
        self.assertEqual(self.target().parent.name, "qwen2.5-coder")

    def test_manifest_root_symlink_refused(self):
        self.link(self.root/"manifests", self.outside)
        with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_DIRECTORY"):
            self.target()
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_midchain_symlink_refused(self):
        (self.root/"manifests").mkdir()
        self.link(self.root/"manifests"/"registry.ollama.ai", self.outside)
        with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_DIRECTORY"):
            self.target()

    def test_dangling_directory_symlink_refused(self):
        d=self.root/"manifests"/"registry.ollama.ai"
        d.mkdir(parents=True)
        self.link(d/"library", self.outside/"missing")
        with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_DIRECTORY"):
            self.target()

    def test_final_manifest_link_refused(self):
        p=self.target()
        x=self.outside/"saved"
        x.write_bytes(RAW)
        self.link(p, x, directory=False)
        with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_FILE"):
            self.target()
        self.assertEqual(x.read_bytes(), RAW)

    def test_existing_directory_as_manifest_refused(self):
        self.target().mkdir()
        with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_FILE"):
            self.target()

    def test_identical_preimage_not_rewritten(self):
        p=self.target()
        p.write_bytes(RAW)
        mtime=p.stat().st_mtime_ns
        self.assertEqual(self.acquire()["manifest_file_sha256"], DIGEST)
        self.assertEqual(p.stat().st_mtime_ns,mtime)

    def test_incorrect_preimage_preserved_and_held(self):
        p=self.target()
        p.write_bytes(b"FORENSIC_PREIMAGE")
        with self.assertRaisesRegex(ValueError, "PREEXISTING_MANIFEST_SHA_MISMATCH"):
            self.acquire()
        self.assertEqual(p.read_bytes(), b"FORENSIC_PREIMAGE")

    def test_refusal_happens_before_registry_request(self):
        self.link(self.root/"manifests",self.outside)
        with patch.object(mod, "manifest_and_blobs", side_effect=AssertionError("network reached")):
            with patch.object(mod.shutil, "disk_usage", return_value=SimpleNamespace(free=7*1024**3)):
                with self.assertRaisesRegex(ValueError, "UNSAFE_MANIFEST_CACHE_DIRECTORY"):
                    mod.acquire(TAG,self.root,execute=True)

if __name__ == "__main__":
    unittest.main()
