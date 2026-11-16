"""Offline guards for pinned DeepSeek identity versus actual local verification."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deepseek_owner_range_v10 as model


def manifest_fixture():
    files = [
        {
            "path": name,
            "bytes": size,
            "sha256": digest,
            "url": f"https://huggingface.co/{model.REPO}/resolve/{model.REVISION}/{name}",
        }
        for name, (size, digest) in model.PINNED_FILE_FACTS.items()
    ]
    return {
        "schema": "NOX_MODEL_DOWNLOAD_MANIFEST_V1",
        "repository": model.REPO,
        "revision": model.REVISION,
        "files": files,
        "total_unique_gguf_bytes": 248834257920,
        "alias": {
            "path": "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf",
            "target": "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf",
            "duplicate_bytes": False,
        },
    }


class DeepSeekManifestIdentityRegressions(unittest.TestCase):
    def test_00001_metadata_size_and_expected_pin_do_not_claim_full_model_readback(self):
        parsed = model.load_manifest(json.dumps(manifest_fixture()).encode())
        name = "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf"
        size, _expected_sha = model.PINNED_FILE_FACTS[name]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            # Exact expected size with untrusted fixture bytes is metadata only.
            with (target / name).open("wb") as stream:
                stream.truncate(size)
            rows = model.inventory(parsed, target)

        by_name = {row["file"]: row for row in rows}
        self.assertEqual(len(rows), 6)
        self.assertEqual(by_name[name]["present_bytes"], size)
        self.assertTrue(by_name[name]["metadata_complete"])
        self.assertFalse(by_name[name]["verified"])
        self.assertEqual(by_name[name]["verification_scope"], "SHA_UNCHECKED")
        self.assertEqual(sum(row["verified"] for row in rows), 0)
        self.assertEqual(sum(row["expected_bytes"] for row in rows), 248834257920)

    def test_engram_alias_is_one_unique_payload_and_cannot_be_counted_twice(self):
        fixture = manifest_fixture()
        parsed = model.load_manifest(json.dumps(fixture).encode())
        engram = "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf"
        self.assertEqual(sum(row["bytes"] for row in parsed.values()), 248834257920)
        self.assertEqual(sum(name == engram for name in parsed), 1)

        duplicated_alias = manifest_fixture()
        duplicated_alias["alias"]["duplicate_bytes"] = True
        with self.assertRaisesRegex(model.Hold, "HOLD_SHARED_ENGRAM_ALIAS"):
            model.load_manifest(json.dumps(duplicated_alias).encode())

        duplicated_payload = manifest_fixture()
        duplicated_payload["files"].append({
            "path": "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf",
            "bytes": model.PINNED_FILE_FACTS[engram][0],
            "sha256": model.PINNED_FILE_FACTS[engram][1],
            "url": (f"https://huggingface.co/{model.REPO}/resolve/"
                    f"{model.REVISION}/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf"),
        })
        with self.assertRaisesRegex(model.Hold, "HOLD_MANIFEST_COUNT"):
            model.load_manifest(json.dumps(duplicated_payload).encode())


if __name__ == "__main__":
    unittest.main()
