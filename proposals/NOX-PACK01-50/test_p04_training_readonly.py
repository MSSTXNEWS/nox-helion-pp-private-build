"""Run original P04 training source methods on bounded synthetic local-only fixtures."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod
owner=os.getenv("NOX_P04_TRAIN_SOURCE")
if not owner:raise RuntimeError("ORIGINAL_P04_TRAIN_SOURCE_PIN_REQUIRED")
worker=load("nox_original_train_qlora",owner)
adapter=load("nox_training_readonly",ROOT/"p04_training_readonly.py")

class TrainingSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=pathlib.Path(self.tmp.name)
        self.dataset=(root/"manifest.json",root/"train.jsonl",root/"holdout.jsonl",root/"no-rights-verifier.exe")
        self.checkpoints=root/"checkpoints";self.checkpoints.mkdir()
        self.selected=self.checkpoints/"checkpoint-7"
        self.grants=set()
        self.pack=adapter.P04TrainingReadOnlyPack(worker,
            native_dataset_selection=lambda session:self.dataset,
            native_checkpoint_selection=lambda session:(self.checkpoints,self.selected),
            native_permission=lambda session,route:route in self.grants)
    def tearDown(self):self.tmp.cleanup()

    def test_training_routes_reuse_original_methods_exactly(self):
        self.assertIs(self.pack.worker.verify_manifest,worker.verify_manifest)
        self.assertIs(self.pack.worker.validated_checkpoint,worker.validated_checkpoint)

    def test_dataset_review_no_native_authorization_refused(self):
        with self.assertRaises(PermissionError):self.pack.review_dataset("user")
    def test_dataset_review_no_real_rights_is_refused(self):
        self.grants.add("datasets.review")
        with self.assertRaises((ValueError,FileNotFoundError)):
            self.pack.review_dataset("user")
    def test_checkpoint_no_native_authorization_refused(self):
        with self.assertRaises(PermissionError):self.pack.inspect_checkpoint("user")
    def test_checkpoint_bad_or_missing_state_rejected(self):
        self.grants.add("training.checkpoints")
        self.selected.mkdir()
        with self.assertRaises(ValueError):self.pack.inspect_checkpoint("user")
    def test_original_checkpoint_validates_optimizer_rng_and_exact_sha(self):
        self.grants.add("training.checkpoints")
        self.selected.mkdir()
        (self.selected/"trainer_state.json").write_text(json.dumps({"global_step":7}),encoding="utf8")
        for name in ("adapter_model.safetensors","optimizer.pt","scheduler.pt","rng_state.pth"):
            (self.selected/name).write_bytes(b"test-only-untrained-data")
        result=self.pack.inspect_checkpoint("user")
        self.assertEqual(result["step"],7)
        self.assertEqual(len(result["checkpointSha256"]),64)
        self.assertEqual(result["status"],"STRUCTURE_VERIFIED_NOT_GPU_TRAINED")
    def test_checkpoint_symlink_denied(self):
        if os.name=="nt":self.skipTest("Windows symlink privilege may be unavailable")
        self.grants.add("training.checkpoints")
        self.selected.symlink_to(self.checkpoints,target_is_directory=True)
        with self.assertRaises(ValueError):self.pack.inspect_checkpoint("user")

if __name__=="__main__":unittest.main()
