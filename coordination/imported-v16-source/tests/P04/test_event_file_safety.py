"""Fail closed on unsafe or interrupted P04 event journal files."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

PATH=Path(__file__).resolve().parents[2]/"Packages"/"P04"/"train_qlora.py"
spec=importlib.util.spec_from_file_location("p04_event_safety",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class EventFileSafety(unittest.TestCase):
    def test_incomplete_or_invalid_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"events.jsonl"
            file.write_bytes(b'{"incomplete":true}')
            with self.assertRaises(ValueError):
                module.EventWriter(file,"run1","task1")
            file.write_bytes(b'invalid-json\n')
            with self.assertRaises(ValueError):
                module.EventWriter(file,"run1","task1")

    def test_destination_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=root/"original.txt"
            original.write_text("untouched",encoding="utf8")
            link=root/"events.jsonl"
            try:
                link.symlink_to(original)
            except (OSError,NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                module.EventWriter(link,"run1","task1")
            self.assertEqual(original.read_text(encoding="utf8"),"untouched")

if __name__=="__main__":
    unittest.main()
