"""NOX Creative Studio model-source integrity tests (no real network or weights).

Use: python -m unittest discover -s integrations/creative/tests -p test_weight_receipts_r20.py -v
Only test-owned tiny weight files; no Ollama, ComfyUI, Hugging Face service, GPU or EXE.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nox_fastpack.engine import Studio, StudioError

MODEL="sdxl-base"
REPO="stabilityai/stable-diffusion-xl-base-1.0"
REV="a"*40
WEIGHT=b"seven bytes"  # Never genuine model data.


class ModelReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio=Studio(self.temp.name)
        self.folder=self.studio.models/MODEL
        self.folder.mkdir(parents=True,exist_ok=True)

    def receipt(self,name="weights.gguf",weights=WEIGHT):
        file=self.folder/name
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(weights)
        receipt={"schema":"NOX-CREATIVE-WEIGHTS-SHA256-V1",
            "model":MODEL,"repository":REPO,"revision":REV,
            "files":[{"filename":name,"bytes":len(weights),
                "sha256":hashlib.sha256(weights).hexdigest()}],
            "source":"https://huggingface.co/"+REPO}
        (self.folder/"RECEIPT.json").write_text(json.dumps(receipt),encoding="utf-8")
        return receipt

    def installed(self):
        return next(x for x in self.studio.catalog()["models"] if x["id"]==MODEL)

    def test_receipt_alone_is_not_installed_weights(self):
        (self.folder/"RECEIPT.json").write_text("{}",encoding="utf-8")
        self.assertFalse(self.installed()["installed"])

    def test_valid_receipt_and_present_weights_admitted(self):
        self.receipt()
        self.assertTrue(self.installed()["installed"])
        self.assertEqual(self.installed()["checksum"],"ON_DEMAND")

    def test_user_can_request_actual_sha256_verification(self):
        self.receipt()
        result=self.studio.dispatch({"action":"verify_model","model_id":MODEL})
        self.assertEqual(result["status"],"VERIFIED_LOCAL_SHA256")

    def test_missing_weight_file_is_not_installed(self):
        self.receipt()
        (self.folder/"weights.gguf").unlink()
        self.assertFalse(self.installed()["installed"])

    def test_truncated_weight_file_is_not_installed(self):
        self.receipt()
        (self.folder/"weights.gguf").write_bytes(b"short")
        self.assertFalse(self.installed()["installed"])

    def test_same_size_corruption_is_caught_by_explicit_verifier(self):
        self.receipt()
        (self.folder/"weights.gguf").write_bytes(b"x"*len(WEIGHT))
        self.assertEqual(self.installed()["checksum"],"ON_DEMAND")
        with self.assertRaises(StudioError):
            self.studio.verify_model(MODEL)

    def test_receipt_from_wrong_repo_is_hold(self):
        receipt=self.receipt()
        receipt["repository"]="attacker/pretend"
        (self.folder/"RECEIPT.json").write_text(json.dumps(receipt))
        self.assertFalse(self.installed()["installed"])

    def test_receipt_path_traversal_is_hold(self):
        receipt=self.receipt()
        receipt["files"][0]["filename"]="../outside.gguf"
        (self.folder/"RECEIPT.json").write_text(json.dumps(receipt))
        self.assertFalse(self.installed()["installed"])

    def test_receipt_symlink_is_hold(self):
        self.receipt()
        actual=self.folder/"RECEIPT.json"
        backup=self.folder/"receipt-backup.json"
        actual.replace(backup)
        try:
            actual.symlink_to(backup)
        except OSError:
            self.skipTest("OS symlinks unavailable")
        self.assertFalse(self.installed()["installed"])

    def test_filename_symlink_is_hold(self):
        self.receipt()
        original=self.folder/"weights.gguf"
        backup=self.folder/"actual.gguf"
        original.replace(backup)
        try:
            original.symlink_to(backup)
        except OSError:
            self.skipTest("OS symlinks unavailable")
        self.assertFalse(self.installed()["installed"])

    def fake_hf(self,*,hub_size=len(WEIGHT),body=WEIGHT,hub_sha256=None):
        module=ModuleType("huggingface_hub")
        class HfApi:
            def model_info(self,repo_id,revision,files_metadata):
                assert repo_id==REPO and revision==REV and files_metadata is True
                return SimpleNamespace(sha=REV,siblings=[
                    SimpleNamespace(rfilename="weights.gguf",size=hub_size,
                                    lfs={"sha256":hub_sha256} if hub_sha256 else None)])
        def snapshot_download(*,repo_id,revision,allow_patterns,local_dir,max_workers):
            assert repo_id==REPO and revision==REV
            assert allow_patterns==["weights.gguf"]
            assert max_workers==2
            (Path(local_dir)/"weights.gguf").write_bytes(body)
            return local_dir
        module.HfApi=HfApi
        module.snapshot_download=snapshot_download
        return module

    def test_download_records_local_digest_without_network(self):
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf()}):
            result=self.studio.download(MODEL,["weights.gguf"],REV,True)
        self.assertEqual(result["status"],"DOWNLOADED")
        self.assertEqual(result["receipt"]["files"][0]["sha256"],
                         hashlib.sha256(WEIGHT).hexdigest())
        self.assertTrue(self.installed()["installed"])
        self.assertEqual(self.studio.verify_model(MODEL)["status"],"VERIFIED_LOCAL_SHA256")

    def test_hub_size_mismatch_cannot_publish_success_receipt(self):
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf(hub_size=999)}):
            with self.assertRaises(StudioError):
                self.studio.download(MODEL,["weights.gguf"],REV,True)
        self.assertFalse((self.folder/"RECEIPT.json").exists())

    def test_non_boolean_license_confirmation_fails_closed(self):
        with self.assertRaises(StudioError):
            self.studio.download(MODEL,["weights.gguf"],REV,"true")

    def test_executable_filename_is_not_accepted_as_weight(self):
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf()}):
            with self.assertRaises(StudioError):
                self.studio.download(MODEL,["setup.py"],REV,True)

    def test_legacy_receipt_preserves_existing_weights_without_false_sha_claim(self):
        old={"model":MODEL,"source":"https://huggingface.co/"+REPO,
             "revision":REV,"files":[{"filename":"weights.gguf","bytes":len(WEIGHT)}]}
        (self.folder/"weights.gguf").write_bytes(WEIGHT)
        (self.folder/"RECEIPT.json").write_text(json.dumps(old),encoding="utf-8")
        item=self.installed()
        self.assertTrue(item["installed"])
        self.assertEqual(item["checksum"],"LEGACY_UNVERIFIED")
        with self.assertRaises(StudioError):
            self.studio.verify_model(MODEL)

    def test_legacy_receipt_with_missing_weights_is_not_installed(self):
        old={"model":MODEL,"source":"https://huggingface.co/"+REPO,
             "revision":REV,"files":[{"filename":"weights.gguf","bytes":len(WEIGHT)}]}
        (self.folder/"RECEIPT.json").write_text(json.dumps(old),encoding="utf-8")
        self.assertFalse(self.installed()["installed"])

    def test_upstream_hub_lfs_checksum_matches_local_weight(self):
        remote=hashlib.sha256(WEIGHT).hexdigest()
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf(hub_sha256=remote)}):
            result=self.studio.download(MODEL,["weights.gguf"],REV,True)
        self.assertEqual(result["receipt"]["files"][0]["upstream_sha256"],remote)
        self.assertEqual(self.studio.verify_model(MODEL)["status"],"VERIFIED_LOCAL_SHA256")

    def test_upstream_hub_lfs_checksum_mismatch_denies_success(self):
        false_remote=hashlib.sha256(b"not the approved bytes").hexdigest()
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf(hub_sha256=false_remote)}):
            with self.assertRaises(StudioError):
                self.studio.download(MODEL,["weights.gguf"],REV,True)
        self.assertFalse((self.folder/"RECEIPT.json").exists())

    def test_conflicting_upstream_sha_receipt_does_not_advertise_installed(self):
        receipt=self.receipt()
        receipt["files"][0]["upstream_sha256"]=hashlib.sha256(b"different").hexdigest()
        (self.folder/"RECEIPT.json").write_text(json.dumps(receipt),encoding="utf-8")
        self.assertFalse(self.installed()["installed"])

    def test_redirected_model_folder_cannot_receive_download(self):
        outside=Path(self.temp.name)/"outside"
        outside.mkdir()
        self.folder.rmdir()
        try:
            self.folder.symlink_to(outside,target_is_directory=True)
        except OSError:
            self.skipTest("OS symlinks unavailable")
        with patch.dict(sys.modules,{"huggingface_hub":self.fake_hf()}):
            with self.assertRaises(StudioError):
                self.studio.download(MODEL,["weights.gguf"],REV,True)
        self.assertEqual(list(outside.iterdir()),[])

if __name__=="__main__":
    unittest.main()
