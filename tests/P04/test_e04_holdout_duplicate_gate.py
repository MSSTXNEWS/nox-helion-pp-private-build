"""E04 actual-module regression: duplicate dataset examples fail BEFORE GPU training.

These tests create only licensed-data *fixtures* in temporary directories.
They do not authorize a real dataset, allocate CUDA, or train model weights.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_e04_actual_train", SOURCE)
assert spec is not None and spec.loader is not None
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


class HoldoutIntegrityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.training = self.root / "train.jsonl"
        self.holdout = self.root / "holdout.jsonl"

    def rows(self, training, holdout):
        for path, examples in ((self.training, training), (self.holdout, holdout)):
            path.write_text(
                "".join(json.dumps(example, ensure_ascii=False) + "\n" for example in examples),
                encoding="utf-8",
            )
        train.validate_jsonl(self.training, "TRAIN")
        train.validate_jsonl(self.holdout, "HOLDOUT")
        return train.validate_holdout_separation(self.training, self.holdout)

    def test_unique_examples_return_actual_train_and_holdout_rows(self):
        self.assertEqual(self.rows(
            [{"text": "one"}, {"text": "two"}],
            [{"text": "three"}, {"text": "four"}, {"text": "five"}],
        ), (2, 3))

    def test_duplicate_training_text_is_rejected_before_gpu(self):
        with self.assertRaisesRegex(ValueError, "DATASET_TRAIN_DUPLICATE_EXAMPLE"):
            self.rows([{"text": "sample"}, {"text": " sample "}],
                      [{"text": "holdout"}])

    def test_duplicate_holdout_text_is_rejected_before_gpu(self):
        with self.assertRaisesRegex(ValueError, "DATASET_HOLDOUT_DUPLICATE_EXAMPLE"):
            self.rows([{"text": "train"}],
                      [{"text": "holdout"}, {"text": "holdout"}])

    def test_cross_split_exact_overlap_preserves_original_error(self):
        with self.assertRaisesRegex(ValueError, "DATASET_TRAIN_HOLDOUT_EXAMPLE_OVERLAP"):
            self.rows([{"text": "shared"}], [{"text": "shared"}])

    def test_duplicate_message_rows_use_same_hash_contract(self):
        dialogue = [{"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Answer"}]
        with self.assertRaisesRegex(ValueError, "DATASET_TRAIN_DUPLICATE_EXAMPLE"):
            self.rows([{"messages": dialogue}, {"messages": dialogue}],
                      [{"text": "different"}])

    def test_distinct_message_rows_remain_valid(self):
        def message(answer):
            return {"messages": [{"role": "user", "content": "Question"},
                                 {"role": "assistant", "content": answer}]}
        self.assertEqual(self.rows([message("A")], [message("B")]), (1, 1))


if __name__ == "__main__":
    unittest.main()
