"""Synthetic unit tests for the dataset holdout guard; no GPU or weights."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"

class HoldoutTests(unittest.TestCase):
    def test_overlap_rejected(self):
        spec = importlib.util.spec_from_file_location("nox_train_guard", PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as root:
            train, holdout = Path(root)/"train.jsonl", Path(root)/"holdout.jsonl"
            train.write_text(json.dumps({"text":"same"})+"\n", encoding="utf-8")
            holdout.write_text(json.dumps({"text":"same"})+"\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DATASET_TRAIN_HOLDOUT_EXAMPLE_OVERLAP"):
                mod.validate_holdout_separation(train, holdout)
            holdout.write_text(json.dumps({"text":"different"})+"\n", encoding="utf-8")
            self.assertEqual(mod.validate_holdout_separation(train, holdout), (1,1))
