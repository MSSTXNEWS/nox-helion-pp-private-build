"""Immutable upstream evidence for one Ollama discovery candidate.

Only confirms official OCI manifest bytes and published layer digests.
It does NOT approve a download, attest local weights, sign a rights receipt,
or claim installed inference on Windows.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TAG = "qwen3:0.6b"
MANIFEST_SHA = "7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435"
WEIGHT_SHA = "7f4030143c1c477224c5434f8272c662a8b042079a0a584f0a27a1684fe2e1fa"
LICENSE_LAYER_SHA = "d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12"
WEIGHT_BYTES = 522640096

def upstream_manifest(raw):
    if len(raw) != 858 or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError("UPSTREAM_MANIFEST_BYTE_IDENTITY_HOLD")
    doc = json.loads(raw.decode("utf-8"))
    if (type(doc) is not dict or doc.get("schemaVersion") != 2 or
            doc.get("mediaType") != "application/vnd.docker.distribution.manifest.v2+json" or
            type(doc.get("layers")) is not list or len(doc["layers"]) != 4):
        raise ValueError("UPSTREAM_MANIFEST_SCHEMA_HOLD")
    return doc

class Qwen3OfficialManifestEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "contracts/engines/QWEN3_06B_OLLAMA_UPSTREAM_MANIFEST.json").read_bytes()
        cls.manifest = upstream_manifest(cls.raw)

    def test_exact_original_registry_manifest_sha(self):
        self.assertEqual(len(self.raw), 858)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), MANIFEST_SHA)

    def test_expected_weight_layer_digest_and_bytes(self):
        layer = self.manifest["layers"][0]
        self.assertEqual(layer["mediaType"], "application/vnd.ollama.image.model")
        self.assertEqual(layer["digest"], "sha256:" + WEIGHT_SHA)
        self.assertEqual(layer["size"], WEIGHT_BYTES)

    def test_upstream_license_layer_is_evidence_not_rights_receipt(self):
        license_layer = self.manifest["layers"][2]
        self.assertEqual(license_layer["mediaType"], "application/vnd.ollama.image.license")
        self.assertEqual(license_layer["digest"], "sha256:" + LICENSE_LAYER_SHA)
        self.assertEqual(license_layer["size"], 11338)

    def test_manifest_and_candidates_link_without_unreviewed_pull(self):
        catalog = json.loads((ROOT / "contracts/p03_download_candidates.json").read_text("utf-8"))
        self.assertEqual(catalog["schema"], "NOX-P03-DOWNLOAD-CANDIDATES-V1")
        self.assertEqual(catalog["state"], "DISCOVERY_ONLY")
        selected = [item for item in catalog["items"] if item.get("tag") == TAG]
        self.assertEqual(len(selected), 1)
        card = selected[0]
        self.assertEqual(card["official_page"], "https://ollama.com/library/qwen3")
        self.assertEqual(card["manifest_sha256"], MANIFEST_SHA)
        self.assertEqual(card["weights_sha256"], WEIGHT_SHA)
        self.assertIsNone(card["license_receipt"])
        self.assertIs(card["download_enabled"], False)

    def test_mutated_manifest_rejected_without_network(self):
        altered = bytearray(self.raw)
        altered[20] ^= 1
        with self.assertRaisesRegex(ValueError, "BYTE_IDENTITY_HOLD"):
            upstream_manifest(bytes(altered))

if __name__ == "__main__":
    unittest.main()
