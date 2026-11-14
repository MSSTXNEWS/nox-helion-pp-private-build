"""Fast, offline P04 tests using real merge and trainer helper code; no GPU or weights."""
from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "Packages" / "P04"

def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    if spec is None or spec.loader is None:
        raise RuntimeError("P04_SOURCE_NOT_AVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class MergeAndInputSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.merge = load("p04_merge_guard", "merge_qlora_adapter.py")
        cls.train = load("p04_train_guard", "train_qlora.py")

    def test_evaluation_must_improve(self):
        self.assertEqual(self.merge.verified_loss_improvement(0.8, 0.7), (0.8, 0.7))
        for before, after in [(1, 1), (1, 2), (True, False), (False, True),
                              (float("nan"), 0.5), (1.0, float("inf")),
                              (1.0, "0.8"), (None, 0.8)]:
            with self.subTest(before=repr(before), after=repr(after)):
                with self.assertRaisesRegex(ValueError, "ADAPTER_VALIDATION_DID_NOT_IMPROVE"):
                    self.merge.verified_loss_improvement(before, after)

    def test_nonregular_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected = root / "manifest.json"
            expected.write_text(json.dumps({"fixture": True}), encoding="utf-8")
            self.assertEqual(self.train.read_object(expected), {"fixture": True})
            with self.assertRaisesRegex(ValueError, "INPUT_NOT_REGULAR_FILE"):
                self.train.read_object(root / "missing.json")
            link = root / "link.json"
            try:
                link.symlink_to(expected)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unsupported")
            with self.assertRaisesRegex(ValueError, "INPUT_NOT_REGULAR_FILE"):
                self.train.read_object(link)
            self.assertEqual(self.merge.read_object(expected), {"fixture": True})

    def test_symlinked_model_tree_rejected_before_resolve(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "local-model"
            model.mkdir()
            (model / "config.json").write_text("{}", encoding="utf-8")
            self.assertRegex(self.train.sha256_tree(model), r"^[0-9a-f]{64}$")
            link = root / "model-symlink"
            try:
                link.symlink_to(model, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unsupported")
            with self.assertRaisesRegex(ValueError, "TREE_ROOT_NOT_REGULAR_DIRECTORY"):
                self.train.sha256_tree(link)
            with self.assertRaises(ValueError):
                self.merge.tree_sha256(link)

if __name__ == "__main__":
    unittest.main()
