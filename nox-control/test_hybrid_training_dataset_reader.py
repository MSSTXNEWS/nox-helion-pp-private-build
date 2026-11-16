"""Regression for frozen JSONL containing valid non-LF Unicode separators."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('hybrid_dataset_reader_test',HERE/'hybrid_training_entry.py')
hybrid=importlib.util.module_from_spec(spec);spec.loader.exec_module(hybrid)


class DatasetReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'training_text.jsonl'

    def test_unicode_separators_inside_strings_are_preserved_byte_for_byte(self):
        rows=[{'text':'a\u0085b'},{'text':'c\u2028d'},{'text':'e\u2029f'},{'text':'ordinary\nline\r\nnext'}]
        raw=b''.join(json.dumps(row,ensure_ascii=False).encode()+b'\n' for row in rows)
        self.path.write_bytes(raw);before=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(json.JSONDecodeError):
            [json.loads(line) for line in raw.decode().splitlines()]
        self.assertEqual(hybrid.read_frozen_dataset(self.path),rows)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)

    def test_reader_does_not_use_whole_file_splitlines(self):
        self.path.write_text('{"text":"synthetic"}\n',encoding='utf8')
        with patch.object(Path,'read_text',side_effect=AssertionError('whole-file read forbidden')):
            self.assertEqual(hybrid.read_frozen_dataset(self.path),[{'text':'synthetic'}])

    def test_invalid_json_on_physical_lf_is_not_silently_joined_or_skipped(self):
        self.path.write_bytes(b'{"text":"broken\nrecord"}\n')
        with self.assertRaises(json.JSONDecodeError):hybrid.read_frozen_dataset(self.path)

    def test_final_record_without_lf_and_crlf_are_valid_jsonl(self):
        self.path.write_bytes(b'{"text":"one"}\r\n{"text":"two"}')
        self.assertEqual(hybrid.read_frozen_dataset(self.path),[{'text':'one'},{'text':'two'}])


if __name__=='__main__':unittest.main()
