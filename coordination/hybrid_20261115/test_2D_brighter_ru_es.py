"""Source-only strict checks for pinned BRIGHTER RU/ES evidence, never an executable remote dataset."""
import copy
import json
from pathlib import Path
import re
import unittest

REV = "419566ac8f46f951b51584be36c13e5363008144"
EXPECTED = {
    "esp/dev-00000-of-00001.parquet": (16128, "8d50aa3e0e9099af800088a3912e52faa066cd3bba09d2b01d6ac9978d4276f7"),
    "esp/test-00000-of-00001.parquet": (100028, "aca2327c3bb63493759a39539e569540eec7b9c816e898ceb9b57a1f8686da0b"),
    "esp/train-00000-of-00001.parquet": (100563, "89bda45d0e5c08227c1c32c5a3a0b9b8eaef4215ed9ccf619fbea9423ed27968"),
    "rus/dev-00000-of-00001.parquet": (20896, "44b26790b8699b5a0bf860b40dc2dbb6a30d1f8e890c12706c0e69e2b22100ab"),
    "rus/test-00000-of-00001.parquet": (86892, "0fbadac53f28dd8f2652bc13c90221af3bcbc3236d92efdaeb2fed511225a64f"),
    "rus/train-00000-of-00001.parquet": (204424, "10fcc51921a451adb6064c9bd04e08bbf10c43afca4844d2958c5cce6caade6d"),
}


def validate(d):
    def require(ok, code):
        if not ok:
            raise ValueError('HOLD_' + code)
    require(isinstance(d, dict) and d.get('schema') == 'NOX_2D_BRIGHTER_RU_ES_CATEGORIES_PINS_V1', 'SCHEMA')
    require(d.get('instructions_version') == '0.0.6', 'VERSION')
    require(d.get('repo_id') == 'brighter-dataset/BRIGHTER-emotion-categories' and d.get('revision') == REV, 'IMMUTABLE_REPO')
    require(d.get('repo_type') == 'dataset' and d.get('license_card') == 'cc-by-4.0', 'LICENCE')
    require(d.get('evidence_scope') == 'OFFICIAL_HF_IMMUTABLE_REPOSITORY_TREE_XET_POINTERS_ONLY', 'SCOPE')
    require(d.get('labels') == ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise'], 'EMOTION_LABELS')
    require([x.get('code') for x in d.get('languages', [])] == ['esp', 'rus'], 'LANGUAGES')
    require(d.get('role') == 'HOLDOUT_EVAL_CANDIDATE_ONLY_NOT_AN_EMPATHY_MODEL', 'ROLE')
    require(d.get('approved_for_training') is False and d.get('approved_for_merge') is False and d.get('active_nox_hf_base_verified') is False, 'FALSE_ADMISSION')
    for k in ('native_files_downloaded', 'native_training_steps_verified', 'native_files_removed', 'native_freed_bytes'):
        require(type(d.get(k)) is int and d[k] == 0, 'FALSE_NATIVE_EVIDENCE')
    fs = d.get('files')
    require(isinstance(fs, list) and len(fs) == 6, 'FILES_COUNT')
    seen = set()
    for f in fs:
        require(isinstance(f,dict), 'FILE_SCHEMA')
        name = f.get('path')
        require(isinstance(name,str) and name in EXPECTED and name not in seen, 'FILE_PATH_DUPLICATE')
        seen.add(name)
        require(f.get('split') == name.split('/')[-1].split('-')[0], 'SPLIT')
        size, sha = EXPECTED[name]
        require(type(f.get('size_bytes')) is int and f['size_bytes'] == size, 'REMOTE_SIZE')
        require(isinstance(f.get('sha256'),str) and re.fullmatch(r'[a-f0-9]{64}', f['sha256']) is not None and f['sha256'] == sha, 'REMOTE_SHA')
    require(seen == set(EXPECTED), 'FILES_MISSING')
    require(type(d.get('total_remote_bytes')) is int and d['total_remote_bytes'] == sum(x[0] for x in EXPECTED.values()), 'TOTAL_SIZE')
    src=d.get('sources')
    require(isinstance(src,list) and len(src)==4 and all(isinstance(s,str) for s in src), 'SOURCES')
    require(REV in src[0] and all(REV in s for s in src[1:3]), 'MUTABLE_SOURCE')
    require('never train' in d.get('split_policy','').lower(), 'SPLIT_POLICY')
    require('not downloaded' in d.get('limitations','').lower(), 'RESEARCH_ONLY')
    return {'source_only':True,'files':len(seen),'remote_metadata_bytes':d['total_remote_bytes']}


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid=json.loads(Path(__file__).with_name('2D_brighter_ru_es.json').read_text())
    def reject(self, change):
        d=copy.deepcopy(self.valid)
        change(d)
        with self.assertRaises(ValueError):validate(d)
    def test_valid(self):self.assertEqual(validate(self.valid)['remote_metadata_bytes'], 528931)
    def test_revision(self):self.reject(lambda d:d.update(revision='main'))
    def test_license(self):self.reject(lambda d:d.update(license_card='apache-2.0'))
    def test_scope(self):self.reject(lambda d:d.update(evidence_scope='DOWNLOADED'))
    def test_training(self):self.reject(lambda d:d.update(approved_for_training=True))
    def test_merge(self):self.reject(lambda d:d.update(approved_for_merge=True))
    def test_base(self):self.reject(lambda d:d.update(active_nox_hf_base_verified=True))
    def test_download(self):self.reject(lambda d:d.update(native_files_downloaded=6))
    def test_false_bool_size(self):self.reject(lambda d:d['files'][0].update(size_bytes=True))
    def test_wrong_size(self):self.reject(lambda d:d['files'][0].update(size_bytes=16129))
    def test_wrong_sha(self):self.reject(lambda d:d['files'][1].update(sha256='a'*64))
    def test_dup(self):self.reject(lambda d:d['files'].append(copy.deepcopy(d['files'][0])))
    def test_path(self):self.reject(lambda d:d['files'][0].update(path='../check.parquet'))
    def test_split(self):self.reject(lambda d:d['files'][0].update(split='test'))
    def test_total(self):self.reject(lambda d:d.update(total_remote_bytes=42))
    def test_source(self):self.reject(lambda d:d['sources'].__setitem__(1,'https://huggingface.co/datasets/main'))
    def test_labels(self):self.reject(lambda d:d.update(labels=['love']))
    def test_languages(self):self.reject(lambda d:d.update(languages=[{'code':'en'}]))
    def test_role(self):self.reject(lambda d:d.update(role='ready for empathy'))
    def test_training_test_contamination(self):self.reject(lambda d:d.update(split_policy='train on everything'))
    def test_native_steps(self):self.reject(lambda d:d.update(native_training_steps_verified=1))
    def test_deleted(self):self.reject(lambda d:d.update(native_files_removed=1))
    def test_freed(self):self.reject(lambda d:d.update(native_freed_bytes=128))

if __name__=='__main__': unittest.main(verbosity=2)
