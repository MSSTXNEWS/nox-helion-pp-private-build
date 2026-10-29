"""QLoRA JSONL limits regression using the real worker, offline only."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]/"Packages"/"P04"/"train_qlora.py"
spec=importlib.util.spec_from_file_location("p04_jsonl",SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DatasetBounds(unittest.TestCase):
    def test_text_line_bound_and_valid_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"train.jsonl"
            path.write_text(json.dumps({"text":"valid short record"})+"\n",encoding="utf8")
            self.assertEqual(module.validate_jsonl(path,"TRAIN"),1)
            path.write_text(json.dumps({"text":"a"*(module.MAX_JSONL_LINE_CHARACTERS+1)})+"\n",encoding="utf8")
            with self.assertRaisesRegex(ValueError,"TRAIN_LINE_TOO_LONG"):
                module.validate_jsonl(path,"TRAIN")

    def test_messages_and_empty_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"train.jsonl"
            path.write_text(json.dumps({"messages":[{"role":"user","content":"Q"},{"role":"assistant","content":"A"}]})+"\n",encoding="utf8")
            self.assertEqual(module.validate_jsonl(path,"TRAIN"),1)
            path.write_text("\n",encoding="utf8")
            with self.assertRaisesRegex(ValueError,"TRAIN_EMPTY"):
                module.validate_jsonl(path,"TRAIN")

if __name__=="__main__":
    unittest.main()
