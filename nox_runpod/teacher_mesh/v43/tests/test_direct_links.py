"""NOX direct download links tests: synthetic-only; no network/model/GPU writes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from nox_runpod.teacher_mesh.v43.pc import direct_links as dl


class DirectLinksTests(unittest.TestCase):
    def setUp(self):
        self.data = dl.load_catalog()
        self.entry = self.data["files"][0]

    def test_seven_existing_verified_links(self):
        self.assertEqual(len(self.data["files"]), 7)
        self.assertEqual(sum(bool(x.get("requires_repo_snapshot")) for x in self.data["files"]), 3)

    def test_orig_v43_three_sha_match(self):
        old = json.loads(dl.V43_CATALOG.read_text())["models"]
        first = {(x["source_repo"], x["source_file"]): x["sha256"]
                 for x in old if x["method"] == "single_file"}
        for x in self.data["files"]:
            k = (x["source_repo"], x["filename"])
            if k in first:
                self.assertEqual(x["expected_sha256"], first[k])

    def test_invalid_external_url_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            obj = copy.deepcopy(self.data)
            obj["files"][0]["url"] = "https://example.com/unsloth/a/resolve/main/b.gguf"
            p = Path(d) / "catalog.json"
            p.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HOLD_URL_ORIGIN"):
                dl.load_catalog(p)

    def test_old_source_sha_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            obj = copy.deepcopy(self.data)
            obj["files"][0]["expected_sha256"] = "0" * 64
            p = Path(d) / "catalog.json"
            p.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HOLD_V43_HASH_DRIFT"):
                dl.load_catalog(p)

    def fake_meta(self, entry, value=None):
        return {"sha": "f" * 40, "siblings": [
            {"rfilename": entry["filename"],
             "lfs": {"sha256": value or entry["expected_sha256"]}}]}

    def test_upstream_committed_url_and_sha(self):
        r = dl.upstream_receipt(self.entry, metadata_fetch=lambda url: self.fake_meta(self.entry))
        self.assertEqual(r["state"], "UPSTREAM_SHA_VERIFIED")
        self.assertIn("/resolve/" + "f" * 40 + "/", r["pinned_url"])
        self.assertFalse(r["file_downloaded"])

    def test_upstream_mismatch_is_hold(self):
        r = dl.upstream_receipt(self.entry, metadata_fetch=lambda url: self.fake_meta(self.entry, "a" * 64))
        self.assertEqual(r["state"], "HOLD_UPSTREAM_SHA_MISMATCH")

    def test_upstream_unknown_revision_is_hold(self):
        r = dl.upstream_receipt(self.entry, metadata_fetch=lambda url: {"sha": "main", "siblings": []})
        self.assertEqual(r["state"], "HOLD_REVISION_NOT_PINNED")

    def test_local_hash_match_skips_network(self):
        with tempfile.TemporaryDirectory() as d:
            ent = dict(self.entry, expected_sha256=hashlib.sha256(b"already").hexdigest())
            file = Path(d) / ent["id"] / ent["filename"]
            file.parent.mkdir()
            file.write_bytes(b"already")
            self.assertEqual(dl.cold_status(ent, Path(d))["state"], "SKIP_SHA_VERIFIED")

    def test_local_mismatch_is_hold(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / self.entry["id"] / self.entry["filename"]
            file.parent.mkdir()
            file.write_bytes(b"wrong")
            self.assertEqual(dl.cold_status(self.entry, Path(d))["state"], "HOLD_LOCAL_HASH_MISMATCH")

    def test_disk_reserve_prevents_download(self):
        with tempfile.TemporaryDirectory() as d:
            r = dl.download_to_pc(self.entry, Path(d), free_bytes=1)
            self.assertEqual(r["state"], "HOLD_PC_DISK_RESERVE")

    def test_synthetic_pc_download_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            payload = b"synthetic-weights-not-real"
            e = dict(self.entry, expected_sha256=hashlib.sha256(payload).hexdigest(),
                     size_gb_approx=0.000001)
            def fake_download(**k):
                path = Path(k["local_dir"]) / k["filename"]
                path.write_bytes(payload)
                return str(path)
            out = dl.download_to_pc(
                e, Path(d), metadata_fetch=lambda url: self.fake_meta(e),
                file_download=fake_download, snapshot_download=lambda **kwargs: None,
                free_bytes=100_000_000_000)
            self.assertEqual(out["state"], "PC_COLD_DOWNLOADED_SHA_VERIFIED")
            receipt = json.loads((Path(d) / e["id"] / "NOX_DIRECT_LINK_RECEIPT.json").read_text())
            self.assertFalse(receipt["weights_trained"])
            self.assertFalse(receipt["vast_changed"])
            self.assertEqual(receipt["files"][0]["sha256"], e["expected_sha256"])

    def test_download_without_explicit_id_rejected(self):
        self.assertEqual(dl.main(["--download"]), 2)


if __name__ == "__main__":
    unittest.main()
