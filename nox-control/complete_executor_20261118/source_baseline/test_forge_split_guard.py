import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from forge_split_guard import TASKS, SPLITS, validate


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SplitPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.split_rows = {}
        for split in SPLITS:
            rows = []
            for task in sorted(TASKS):
                for language in ('ru', 'es'):
                    key = f'{split}-{task}-{language}'
                    rows.append(dict(sample_id=key, origin_id='origin-'+key,
                        source_sha256=sha(('source-'+key).encode()),
                        source_url='https://example.org/data/'+key,
                        license='CC-BY-4.0', language=language, task=task,
                        goal='answer-'+task, prompt='Prompt '+key,
                        response='Answer '+key))
            self.split_rows[split] = rows
        self.write_all()

    def write_all(self):
        specs = {}
        for split, rows in self.split_rows.items():
            payload = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode()
            (self.root / (split+'.jsonl')).write_bytes(payload)
            specs[split] = {'path': split+'.jsonl', 'sha256': sha(payload), 'rows': len(rows)}
        self.manifest = self.root/'splits.json'
        manifest_bytes = json.dumps({'splits': specs}).encode()
        self.manifest.write_bytes(manifest_bytes)
        self.pin = sha(manifest_bytes)

    def assess(self):
        return validate(self.root, self.manifest, self.pin)

    def test_clean_three_way_split(self):
        a=self.assess()
        self.assertEqual(a['status'], 'SOURCE_SPLITS_VERIFIED')
        self.assertEqual(a['cross_split_duplicates'], 0)
        self.assertFalse(a['training_started'])

    def test_origin_leakage(self):
        self.split_rows['dev'][0]['origin_id'] = self.split_rows['train'][0]['origin_id']
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'): self.assess()

    def test_prompt_leakage_with_different_sources(self):
        self.split_rows['holdout'][0]['prompt'] = self.split_rows['train'][0]['prompt'].lower().replace('  ', ' ')
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'): self.assess()

    def test_provenance_sha_leakage(self):
        self.split_rows['holdout'][0]['source_sha256'] = self.split_rows['train'][0]['source_sha256']
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'): self.assess()

    def test_source_url_leakage_even_with_different_origins_and_hashes(self):
        original = self.split_rows['train'][0]['source_url']
        self.assertNotEqual(self.split_rows['train'][0]['origin_id'], self.split_rows['dev'][0]['origin_id'])
        self.assertNotEqual(self.split_rows['train'][0]['source_sha256'], self.split_rows['dev'][0]['source_sha256'])
        for url in (original, original.replace('example.org', 'EXAMPLE.ORG')):
            with self.subTest(url=url):
                self.split_rows['dev'][0]['source_url'] = url
                self.write_all()
                with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'):
                    self.assess()

    def test_https_default_port_alias_is_same_source(self):
        original = self.split_rows['train'][0]['source_url']
        # Explicit 443 and leading-zero 0443 are the same HTTPS resource.
        for alias in (original.replace('example.org', 'EXAMPLE.ORG:443'),
                      original.replace('example.org', 'example.org:0443')):
            with self.subTest(alias=alias):
                self.split_rows['dev'][0]['source_url'] = alias
                self.write_all()
                with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'):
                    self.assess()

    def test_https_absolute_dns_hostname_is_same_source(self):
        # A final DNS root dot does not change the HTTPS origin or document.
        original = self.split_rows['train'][0]['source_url']
        for alias in (original.replace('example.org', 'example.org.'),
                      original.replace('example.org', 'EXAMPLE.ORG.')):
            with self.subTest(alias=alias):
                self.split_rows['dev'][0]['source_url'] = alias
                self.write_all()
                with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'):
                    self.assess()

    def test_https_absolute_hostname_different_document_is_not_leakage(self):
        original = self.split_rows['train'][0]['source_url']
        self.split_rows['dev'][0]['source_url'] = original.replace(
            'example.org/data/', 'example.org./data/other-')
        self.write_all()
        self.assertEqual(self.assess()['status'], 'SOURCE_SPLITS_VERIFIED')

    def test_distinct_https_port_is_not_false_leakage(self):
        original = self.split_rows['train'][0]['source_url']
        self.split_rows['dev'][0]['source_url'] = original.replace(
            'example.org', 'example.org:444')
        self.write_all()
        self.assertEqual(self.assess()['status'], 'SOURCE_SPLITS_VERIFIED')

    def test_percent_encoded_unreserved_path_alias_is_leakage(self):
        original = self.split_rows['train'][0]['source_url']
        self.split_rows['dev'][0]['source_url'] = original.replace(
            'example.org/data/', 'EXAMPLE.ORG:443/%64ata/')
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'):
            self.assess()

    def test_percent_encoded_unreserved_query_alias_is_leakage(self):
        original = self.split_rows['train'][0]['source_url']
        self.split_rows['train'][0]['source_url'] = original + '?ref=alpha'
        self.split_rows['holdout'][0]['source_url'] = original + '?ref=%61lpha'
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'CROSS_SPLIT_LEAKAGE'):
            self.assess()

    def test_reserved_slash_escape_is_not_decoded(self):
        self.split_rows['train'][0]['source_url'] = 'https://example.org/source%2Fone'
        self.split_rows['dev'][0]['source_url'] = 'https://example.org/source/one'
        self.write_all()
        self.assertEqual(self.assess()['status'], 'SOURCE_SPLITS_VERIFIED')

    def test_malformed_source_url_percent_escape_rejected(self):
        self.split_rows['dev'][0]['source_url'] = 'https://example.org/%gg'
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'MALFORMED_SOURCE_URL_ESCAPE'):
            self.assess()

    def test_changed_data_after_manifest(self):
        with (self.root/'dev.jsonl').open('ab') as f: f.write(b'{}\n')
        with self.assertRaises((ValueError, KeyError)): self.assess()

    def test_corrupt_manifest_pin(self):
        with self.assertRaisesRegex(ValueError, 'MANIFEST_SHA_MISMATCH'):
            validate(self.root, self.manifest, '0'*64)

    def test_missing_spanish_holdout(self):
        self.split_rows['holdout']=[r for r in self.split_rows['holdout'] if r['language']!='es']
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'RU_ES_COVERAGE_REQUIRED'): self.assess()

    def test_symlink_rejected(self):
        p=self.root/'dev.jsonl'
        p.rename(self.root/'real.jsonl')
        p.symlink_to(self.root/'real.jsonl')
        with self.assertRaisesRegex(ValueError, 'SPLIT_SYMLINK_REJECTED'): self.assess()

    def test_duplicate_key_rejected(self):
        (self.root/'train.jsonl').write_text('{"sample_id":"a","sample_id":"b"}\n')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): self.assess()

    def test_duplicate_sample_id_inside_train(self):
        self.split_rows['train'][1]['sample_id'] = self.split_rows['train'][0]['sample_id']
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_WITHIN_SPLIT'): self.assess()

    def test_duplicate_origin_id_inside_dev(self):
        self.split_rows['dev'][1]['origin_id'] = self.split_rows['dev'][0]['origin_id']
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_WITHIN_SPLIT'): self.assess()

    def test_nonfinite_numeric_exponent_in_manifest_rejected(self):
        original = self.manifest.read_bytes()
        self.assertTrue(original.endswith(b'}'))
        payload = original[:-1] + b', "optional_metric": 1e999}'
        self.manifest.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, 'NONFINITE_JSON'):
            validate(self.root, self.manifest, sha(payload))

    def test_nonfinite_numeric_exponent_in_row_rejected(self):
        candidate = self.root / 'train.jsonl'
        payload = candidate.read_bytes().replace(
            b'"response":', b'"optional_metric": -1e999, "response":', 1)
        candidate.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, 'NONFINITE_JSON'):
            self.assess()

    def test_finite_optional_float_remains_valid(self):
        self.split_rows['dev'][0]['optional_metric'] = 1e308
        self.write_all()
        self.assertEqual(self.assess()['status'], 'SOURCE_SPLITS_VERIFIED')

    def test_nonfinite_optional_field_rejected(self):
        p = self.root / 'train.jsonl'
        original = p.read_text()
        p.write_text(original.replace('"response":', '"weight": NaN, "response":', 1))
        with self.assertRaisesRegex(ValueError, 'NONFINITE_JSON'): self.assess()

    def test_empty_https_hostname_rejected(self):
        self.split_rows['dev'][0]['source_url'] = 'https://'
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'SOURCE_URL_REQUIRED'): self.assess()

    def test_unknown_training_licence_rejected(self):
        self.split_rows['holdout'][0]['license'] = 'all rights reserved'
        self.write_all()
        with self.assertRaisesRegex(ValueError, 'LICENSE_REVIEW_REQUIRED'): self.assess()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_manifest_fifo_rejected_without_waiting_for_writer(self):
        self.manifest.unlink()
        os.mkfifo(self.manifest)
        with self.assertRaisesRegex(ValueError, "MANIFEST_NOT_SINGLE_REGULAR_FILE"):
            self.assess()

    def test_manifest_oversize_rejected_before_json_parse(self):
        payload = b" " * 1_000_001
        self.manifest.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, "MANIFEST_OVERSIZE"):
            validate(self.root, self.manifest, sha(payload))

    def test_oversize_jsonl_row_bounded_read(self):
        self.split_rows["dev"][0]["prompt"] = "x" * 2_000_001
        self.write_all()
        with self.assertRaisesRegex(ValueError, "EMPTY_OR_OVERSIZE_ROW"):
            self.assess()

    def test_malformed_manifest_shape_is_hold(self):
        for manifest in ([], {"splits": None}, {"splits": ["train", "dev", "holdout"]},
                         {"splits": "train"}, 5):
            with self.subTest(manifest=manifest):
                payload = json.dumps(manifest).encode()
                self.manifest.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, "EXACT_TRAIN_DEV_HOLDOUT_REQUIRED"):
                    validate(self.root, self.manifest, sha(payload))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_split_fifo_rejected_without_waiting_for_writer(self):
        candidate = self.root / "dev.jsonl"
        candidate.unlink()
        os.mkfifo(candidate)
        with self.assertRaisesRegex(ValueError, "SPLIT_NOT_SINGLE_REGULAR_FILE"):
            self.assess()

if __name__ == '__main__': unittest.main()
