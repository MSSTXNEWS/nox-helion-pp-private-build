import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('corpus_probe_test',HERE/'owner_training_corpus_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class CorpusProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'fixture.jsonl'

    def scan(self,rows):
        raw=b''.join(json.dumps({'text':text},ensure_ascii=False).encode()+b'\n' for text in rows)
        self.path.write_bytes(raw);return probe.scan(self.path,probe.digest(raw),len(raw)),raw

    def test_actual_lf_is_correct_for_valid_unicode_json_strings(self):
        result,raw=self.scan(['synthetic private a\u2028b','c\u2029d','e\u0085f','ordinary'])
        self.assertEqual(result['actual_lf_valid_records'],4);self.assertTrue(result['lf_jsonl_valid'])
        self.assertTrue(result['legacy_splitlines_invalid']);self.assertEqual(result['legacy_invalid_segments'],6)
        self.assertEqual(result['legacy_splitlines_segments'],7)
        self.assertEqual(result['first_legacy_failure']['exception'],'JSONDecodeError')
        self.assertEqual(result['separator_counts']['U+2028'],1)
        self.assertEqual(self.path.read_bytes(),raw);self.assertNotIn('synthetic private',json.dumps(result))

    def test_escaped_newlines_and_unicode_escapes_do_not_create_legacy_failure(self):
        result,_=self.scan(['line1\nline2','literal \\u2028 text'])
        self.assertTrue(result['lf_jsonl_valid']);self.assertFalse(result['legacy_splitlines_invalid'])

    def test_hash_mismatch_and_binary_source_cannot_be_claimed_valid(self):
        result,raw=self.scan(['fixture'])
        with self.assertRaisesRegex(RuntimeError,'DATASET_SHA'):probe.scan(self.path,'0'*64,len(raw))
        raw=b'\xff\n';self.path.write_bytes(raw)
        result=probe.scan(self.path,probe.digest(raw),len(raw))
        self.assertFalse(result['lf_jsonl_valid']);self.assertEqual(result['first_lf_failure']['exception'],'UnicodeDecodeError')

    def test_invalid_json_does_not_export_decoder_text(self):
        raw=b'{"secret corpus fragment"\n';self.path.write_bytes(raw)
        result=probe.scan(self.path,probe.digest(raw),len(raw))
        self.assertFalse(result['lf_jsonl_valid']);self.assertNotIn('secret corpus',json.dumps(result))


if __name__=='__main__':unittest.main()
