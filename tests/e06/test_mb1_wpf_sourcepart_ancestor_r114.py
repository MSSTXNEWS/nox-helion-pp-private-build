"""W09 R114: original MB1 WPF donor parts must have trusted path ancestry."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]/"coordination/e06/mb1_extract_original_sources.py"
spec=importlib.util.spec_from_file_location("w09_mb1_exact_source", SOURCE)
mb1=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb1)

class WPFPartIdentity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.donors=self.root/"donors"/"P01_C07"
        self.donors.mkdir(parents=True)
        self.data=b"original R11 WPF bytes pinned by sha"
        mb1.ROOT=self.root
        mb1.WPFZIP=hashlib.sha256(self.data).hexdigest()
    def stage(self,rel="donors/P01_C07/part00.part", bytes_=None):
        payload=self.data if bytes_ is None else bytes_
        target=self.root/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(payload)
        manifest={"parts":[{"path":rel,"size_bytes":len(self.data),
                             "git_blob_sha1":mb1.git_blob(self.data)}],
                  "original_zip_bytes":len(self.data)}
        (self.donors/"P01_C07_RECEIPT.json").write_text(json.dumps(manifest),"utf-8")
        return target
    def test_regular_wpf_donor(self):
        self.stage()
        self.assertEqual(mb1.join_and_verify_wpf().getvalue(),self.data)
    def test_ancestor_symlink_part_is_hold_even_with_matching_hash(self):
        redirect=self.donors/"redirect"
        cache=self.root/"cache"
        cache.mkdir()
        (cache/"part00.part").write_bytes(self.data)
        redirect.symlink_to(cache,target_is_directory=True)
        self.stage("donors/P01_C07/placeholder.part")
        manifest=json.loads((self.donors/"P01_C07_RECEIPT.json").read_text())
        manifest["parts"][0]["path"]="donors/P01_C07/redirect/part00.part"
        (self.donors/"P01_C07_RECEIPT.json").write_text(json.dumps(manifest))
        with self.assertRaises(Exception):
            mb1.join_and_verify_wpf()
    def test_ancestor_symlink_manifest_is_hold_even_with_matching_hash(self):
        self.stage()
        real=self.root/"physicalparts"
        self.donors.rename(real)
        self.donors.symlink_to(real,target_is_directory=True)
        with self.assertRaises(Exception):
            mb1.join_and_verify_wpf()
    def test_leaf_symlink_part_is_hold(self):
        target=self.stage()
        other=self.root/"physical"
        other.write_bytes(self.data)
        target.unlink()
        target.symlink_to(other)
        with self.assertRaises(Exception):
            mb1.join_and_verify_wpf()
    def test_mismatched_payload_is_hold(self):
        self.stage(bytes_=b"x"*len(self.data))
        with self.assertRaises(Exception):
            mb1.join_and_verify_wpf()

if __name__=="__main__":
    unittest.main()
