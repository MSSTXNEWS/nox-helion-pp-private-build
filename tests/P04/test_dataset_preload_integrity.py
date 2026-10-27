"""P04 pre-load dataset integrity: synthetic fixtures only, no GPU/weights."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

worker=Path(__file__).resolve().parents[2]/"Packages"/"P04"/"train_qlora.py"
spec=importlib.util.spec_from_file_location("p04_c12_worker",worker)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class DatasetReattestation(unittest.TestCase):
    def test_exact_bytes_and_mutation_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            train=root/"train.jsonl"
            holdout=root/"holdout.jsonl"
            train.write_text('{"text":"alpha"}\n',encoding="utf8")
            holdout.write_text('{"text":"beta"}\n',encoding="utf8")
            manifest={name+"_sha256":hashlib.sha256(path.read_bytes()).hexdigest()
                      for name,path in (("train",train),("holdout",holdout))}
            mod.verify_dataset_unchanged(manifest,train,holdout)
            train.write_text('{"text":"changed"}\n',encoding="utf8")
            with self.assertRaisesRegex(ValueError,"DATASET_TRAIN_MODIFIED_AFTER_PREFLIGHT"):
                mod.verify_dataset_unchanged(manifest,train,holdout)
    def test_event_identity_before_log_access(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"events.jsonl"
            with self.assertRaisesRegex(ValueError,"EVENT_RUN_TASK_ID_INVALID"):
                mod.EventWriter(path,"run with spaces","task")
            self.assertFalse(path.exists())

if __name__=="__main__":
    unittest.main()
