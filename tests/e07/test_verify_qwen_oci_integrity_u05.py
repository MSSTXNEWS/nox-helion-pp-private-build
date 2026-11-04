"""Actual small-byte OCI fixtures; does not substitute Windows model verification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "coordination/e07/verify_qwen_oci_integrity.py"
spec = importlib.util.spec_from_file_location("oci_verify_u05", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OCIGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir()
        self.manifest_path = self.root / "manifests/registry.ollama.ai/library/qwen2.5-coder/1.5b"
        self.manifest_path.parent.mkdir(parents=True)
        self.contents = [b"model bytes", b"config bytes"]
        layers = []
        for part in self.contents:
            sha = hashlib.sha256(part).hexdigest()
            (self.blobs / ("sha256-" + sha)).write_bytes(part)
            layers.append({"digest": "sha256:" + sha, "size": len(part)})
        self.manifest = {"schemaVersion": 2, "config": layers[1], "layers": [layers[0]]}
        self.rewrite()

    def rewrite(self):
        raw = json.dumps(self.manifest, separators=(",", ":")).encode()
        self.manifest_path.write_bytes(raw)
        self.expected = hashlib.sha256(raw).hexdigest()

    def test_valid_exact_oci_bytes(self):
        receipt = m.verify(self.root, self.expected)
        self.assertTrue(receipt["independent_weights_sha_verified"])
        self.assertFalse(receipt["release_accepted"])
        self.assertEqual(receipt["verified_blobs"], 2)

    def install_v2_manifest(self, data: bytes) -> Path:
        named = self.root / "manifests-v2/ollama.com/library/qwen2.5-coder/1.5b"
        named.parent.mkdir(parents=True, exist_ok=True)
        named.write_bytes(data)
        # Ollama v0.40.13 keeps the same named bytes in the immutable blob
        # store. Both paths must match for an accepted v2 manifest.
        digest = hashlib.sha256(data).hexdigest()
        (self.blobs / ("sha256-" + digest)).write_bytes(data)
        return named

    def test_v2_manifest_preferred_over_stale_legacy(self):
        v2 = self.install_v2_manifest(self.manifest_path.read_bytes())
        self.manifest_path.write_bytes(b"STALE_LEGACY_MANIFEST")
        self.assertEqual(m.verify(self.root, self.expected)["verified_blobs"], 2)
        # No silent fallback if the selected v2 file is corrupted.
        v2.write_bytes(b"CORRUPTED_V2")
        # An altered v2 name no longer points to its original content-
        # addressed parent blob. That is a provenance HOLD, never fallback.
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_PATH_UNTRUSTED"):
            m.verify(self.root, self.expected)

    def test_v2_manifest_list_content_addressed_child(self):
        child = dict(self.manifest, mediaType="application/vnd.docker.distribution.manifest.v2+json")
        child_raw = json.dumps(child, separators=(",", ":")).encode()
        digest = hashlib.sha256(child_raw).hexdigest()
        (self.blobs / ("sha256-" + digest)).write_bytes(child_raw)
        parent = {"schemaVersion": 2,
                  "mediaType": "application/vnd.ollama.manifest.list.v2+json",
                  "manifests": [{"mediaType": child["mediaType"],
                                 "runner": "llamacpp", "digest": "sha256:" + digest}]}
        data = json.dumps(parent, separators=(",", ":")).encode()
        self.install_v2_manifest(data)
        # /api/tags reports the CHILD SHA, not the parent-list SHA.
        self.assertEqual(m.verify(self.root, digest)["verified_blobs"], 2)
        # A hash-mismatched referenced child cannot be blessed by a valid parent.
        (self.blobs / ("sha256-" + digest)).write_bytes(b"BAD_CHILD")
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_SHA256"):
            m.verify(self.root, digest)

    def test_v2_parent_sha_is_not_the_model_sha(self):
        child = {"schemaVersion": 2,
                 "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                 "config": self.manifest["config"],
                 "layers": self.manifest["layers"]}
        canonical = json.dumps(child, separators=(",", ":")).encode()
        child_sha = hashlib.sha256(canonical).hexdigest()
        parent = {"schemaVersion": 2,
                  "mediaType": "application/vnd.ollama.manifest.list.v2+json",
                  "manifests": [dict(child, runner="llamacpp")]}
        # Inline Go JSON includes runner in the child's trailing field.
        inline = parent["manifests"][0]
        inline_sha = hashlib.sha256(json.dumps(inline, separators=(",", ":")).encode()).hexdigest()
        data = json.dumps(parent, separators=(",", ":")).encode()
        self.install_v2_manifest(data)
        self.assertEqual(m.verify(self.root, inline_sha)["verified_blobs"], 2)
        # Hashing the parent list must NOT authorize the weights.
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_APPROVED_CHILD"):
            m.verify(self.root, hashlib.sha256(data).hexdigest())

    def test_wrong_approved_manifest_digest(self):
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_SHA256"):
            m.verify(self.root, "0" * 64)

    def test_corrupt_model_blob(self):
        d = self.manifest["layers"][0]["digest"].split(":")[1]
        (self.blobs / ("sha256-" + d)).write_bytes(b"other bytes")
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_SHA256"):
            m.verify(self.root, self.expected)

    def test_missing_model_blob(self):
        d = self.manifest["layers"][0]["digest"].split(":")[1]
        (self.blobs / ("sha256-" + d)).unlink()
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_PATH_UNTRUSTED"):
            m.verify(self.root, self.expected)

    def test_duplicate_manifest_json_field(self):
        raw = b'{"config":{},"config":{},"layers":[]}'
        self.manifest_path.write_bytes(raw)
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_DUPLICATE"):
            m.verify(self.root, hashlib.sha256(raw).hexdigest())

    def test_manifest_layer_size_spoof(self):
        self.manifest["layers"][0]["size"] += 1
        self.rewrite()
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_FILE_SIZE"):
            m.verify(self.root, self.expected)

    def test_manifest_layer_digest_path_injection(self):
        self.manifest["layers"][0]["digest"] = "sha256:../../outside"
        self.rewrite()
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_LAYER_DIGEST"):
            m.verify(self.root, self.expected)

    def test_manifest_duplicate_layer_digest(self):
        self.manifest["layers"] = [self.manifest["layers"][0]] * 2
        self.rewrite()
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_DUPLICATE_LAYER"):
            m.verify(self.root, self.expected)

    def test_manifest_layer_symlink(self):
        path = self.blobs / ("sha256-" + self.manifest["layers"][0]["digest"].split(":")[1])
        target = self.root / "outside"
        target.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed")
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_REPARSE"):
            m.verify(self.root, self.expected)

    def test_invalid_expected_pin(self):
        with self.assertRaisesRegex(m.IntegrityHold, "OCI_EXPECTED"):
            m.verify(self.root, "not-a-sha")


if __name__ == "__main__":
    unittest.main()
