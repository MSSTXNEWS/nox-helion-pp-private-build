"""Creative Studio source regression: pinned Hugging Face weight download gate.

The real Studio.download is executed with a fake in-memory huggingface_hub
module and a temporary directory; tests never perform network downloads or
install weights. Runtime model execution, independent license review and
Windows E07 are outside this component test.
Run: python -m unittest discover -s integrations/creative/tests -p test_model_weight_gate_r21.py -v
"""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nox_fastpack.engine import Studio, StudioError


class ModelWeightBoundary(unittest.TestCase):
    def setUp(self):
        self.sandbox=tempfile.TemporaryDirectory(prefix="nox-weights-r21-")
        self.addCleanup(self.sandbox.cleanup)
        self.root=Path(self.sandbox.name)/"studio"
        self.root.mkdir()
        self.studio=Studio(self.root)
        self.revision="a"*40
        self.filename="weights/model.safetensors"
        self.allowed=[self.filename]
        self.reported_sha=self.revision
        self.download_count=0
        self.written=[]
        self.write_as_symlink=False
        hf=ModuleType("huggingface_hub")
        hf.HfApi=lambda:SimpleNamespace(model_info=self.model_info)
        hf.snapshot_download=self.download_mock
        self.injection=patch.dict(sys.modules,{"huggingface_hub":hf})
        self.injection.start()
        self.addCleanup(self.injection.stop)

    def model_info(self, repo, *, revision, files_metadata):
        self.assertEqual(repo,"stabilityai/stable-diffusion-xl-base-1.0")
        self.assertTrue(files_metadata)
        return SimpleNamespace(
            sha=self.reported_sha,
            siblings=[SimpleNamespace(rfilename=name) for name in self.allowed])

    def download_mock(self,*,repo_id,revision,allow_patterns,local_dir,max_workers):
        self.download_count+=1
        self.assertEqual(repo_id,"stabilityai/stable-diffusion-xl-base-1.0")
        self.assertEqual(revision,self.revision)
        self.assertEqual(max_workers,2)
        self.assertEqual(allow_patterns,[self.filename])
        directory=Path(local_dir)
        target=directory/self.filename
        target.parent.mkdir(parents=True,exist_ok=True)
        if self.write_as_symlink:
            outside=self.root/"outside.bin"
            outside.write_bytes(b"ORIGINAL")
            target.symlink_to(outside)
        else:
            target.write_bytes(b"WEIGHT")
        self.written.append(target)

    def request(self,*,filenames=None,license_confirmed=True):
        return self.studio.download("sdxl-base",
            [self.filename] if filenames is None else filenames,
            self.revision,license_confirmed=license_confirmed)

    def test_valid_pinned_literal_weight_keeps_original_download(self):
        result=self.request()
        self.assertEqual(result["status"],"DOWNLOADED")
        self.assertEqual(result["receipt"]["revision"],self.revision)
        self.assertEqual(self.download_count,1)
        self.assertEqual(self.written[0].read_bytes(),b"WEIGHT")
        disk=json.loads((self.root/"models"/"sdxl-base"/"RECEIPT.json").read_text("utf-8"))
        self.assertEqual(disk["files"][0]["filename"],self.filename)

    def test_boolean_consent_is_explicit_not_string(self):
        with self.assertRaises(StudioError):
            self.request(license_confirmed="yes")
        self.assertEqual(self.download_count,0)

    def test_unknown_revision_from_provider_is_hold_before_download(self):
        self.reported_sha="b"*40
        with self.assertRaisesRegex(StudioError,"revision changed"):
            self.request()
        self.assertEqual(self.download_count,0)

    def test_glob_patterns_never_expand_to_more_files(self):
        for name in ("weights/*.safetensors","weights/?.safetensors",
                     "weights/[ab].safetensors"):
            with self.subTest(name=name):
                self.filename=name
                self.allowed=[name]
                with self.assertRaises(StudioError):
                    self.request()
        self.assertEqual(self.download_count,0)

    def test_upstream_file_metadata_cannot_escape_model_directory(self):
        for name in ("../weights/model.safetensors","/tmp/model.safetensors",
                     "weights\\model.safetensors","weights//model.safetensors"):
            with self.subTest(name=name):
                self.filename=name
                self.allowed=[name]
                with self.assertRaises(StudioError):
                    self.request()
        self.assertEqual(self.download_count,0)

    def test_not_a_weight_file_is_rejected(self):
        self.filename="pipeline.py"
        self.allowed=[self.filename]
        with self.assertRaises(StudioError):
            self.request()
        self.assertEqual(self.download_count,0)

    def test_non_string_and_duplicate_filename_rejected(self):
        for items in ([["not-hashable"]],[self.filename,self.filename]):
            with self.subTest(items=repr(items)):
                with self.assertRaises(StudioError):
                    self.request(filenames=items)
        self.assertEqual(self.download_count,0)

    def test_symlinked_models_root_is_rejected_before_download(self):
        outside=self.root/"outside"
        outside.mkdir()
        (self.root/"models").symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(StudioError,"Untrusted model root"):
            self.request()
        self.assertEqual(self.download_count,0)
        self.assertFalse((outside/"sdxl-base").exists())

    def test_symlinked_model_directory_is_rejected_before_download(self):
        outside=self.root/"outside"
        outside.mkdir()
        self.studio.models.mkdir()
        (self.studio.models/"sdxl-base").symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(StudioError,"Untrusted model destination"):
            self.request()
        self.assertEqual(self.download_count,0)

    def test_nested_symlink_in_existing_target_is_rejected(self):
        self.studio.models.mkdir()
        model_dir=self.studio.models/"sdxl-base"
        model_dir.mkdir()
        outside=self.root/"outside"
        outside.mkdir()
        (model_dir/"weights").symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(StudioError,"reparse link"):
            self.request()
        self.assertEqual(self.download_count,0)
        self.assertFalse((outside/"model.safetensors").exists())

    def test_upstream_download_symlink_does_not_write_receipt(self):
        self.write_as_symlink=True
        with self.assertRaisesRegex(StudioError,"reparse link"):
            self.request()
        self.assertEqual(self.download_count,1)
        self.assertFalse((self.studio.models/"sdxl-base"/"RECEIPT.json").exists())


if __name__=="__main__":
    unittest.main()
