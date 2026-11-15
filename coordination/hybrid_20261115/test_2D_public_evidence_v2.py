"""NOX AUTO 2D: source metadata consistency and negative safety tests."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('proof',HERE/'2D_public_evidence_v2.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class OfficialPointerSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid=json.loads((HERE/'2D_public_evidence_v2.json').read_text())
    def bad(self,fn):
        d=copy.deepcopy(self.valid);fn(d)
        with self.assertRaises(ValueError):mod.validate(d)
    def test_valid_catalogue(self):
        result=mod.validate(self.valid)
        self.assertEqual(result['adapters'],2)
        self.assertEqual(result['code_files'],3)
        self.assertEqual(result['new_metadata_bytes'],488063294)
        self.assertEqual(result['native_merges'],0)
    def test_no_fake_base(self):self.bad(lambda d:d.update(active_nox_hf_base_verified=True))
    def test_no_fake_download(self):self.bad(lambda d:d.update(authorized_native_downloads_this_run=1))
    def test_no_fake_lease(self):self.bad(lambda d:d.update(owner_native_write_lease_verified=True))
    def test_no_fake_optimizer(self):self.bad(lambda d:d.update(native_optimizer_steps_this_run=1))
    def test_no_fake_merged(self):self.bad(lambda d:d.update(native_merges_this_run=1))
    def test_merge_requires_base(self):self.bad(lambda d:d['adapters_research_only'][0].update(merge_approved=True))
    def test_base_revision_must_be_unknown(self):self.bad(lambda d:d['adapters_research_only'][0].update(base_revision_in_adapter_config='a'*40))
    def test_revision_is_not_main(self):self.bad(lambda d:d['adapters_research_only'][0].update(revision='main'))
    def test_adapter_weight_sha(self):self.bad(lambda d:d['adapters_research_only'][0]['weights'].update(sha256='a'*64))
    def test_adapter_weight_size(self):self.bad(lambda d:d['adapters_research_only'][1]['weights'].update(size_bytes=1))
    def test_unknown_license_remains_unknown(self):self.bad(lambda d:d['adapters_research_only'][1].update(license_card='apache-2.0'))
    def test_pickle_guard(self):self.bad(lambda d:d['adapters_research_only'][1].update(unsafe_metadata_filename=None))
    def test_bad_module_targets(self):self.bad(lambda d:d['adapters_research_only'][0].update(target_modules=['q_proj','q_proj']))
    def test_benchmark_not_for_training(self):self.bad(lambda d:d['code_benchmark_research_only'].update(training_authorized=True))
    def test_code_source_revision(self):self.bad(lambda d:d['code_benchmark_research_only'].update(revision='b'*40))
    def test_code_train_size(self):self.bad(lambda d:d['code_benchmark_research_only']['files'][0].update(size_bytes=0))
    def test_code_split_duplication(self):self.bad(lambda d:d['code_benchmark_research_only']['files'][2].update(split='train'))
    def test_code_unsafe_path(self):self.bad(lambda d:d['code_benchmark_research_only']['files'][0].update(path='../hack.py'))
    def test_code_wrong_hash(self):self.bad(lambda d:d['code_benchmark_research_only']['files'][1].update(sha256='0'*64))
    def test_code_float_size(self):self.bad(lambda d:d['code_benchmark_research_only']['files'][2].update(size_bytes=115824.0))
    def test_reasoning_language_not_implicit_ru(self):self.bad(lambda d:d['reasoning_dataset_research_only'].update(training_authorized=True))
    def test_source_link_must_be_pinned(self):self.bad(lambda d:d['reasoning_dataset_research_only'].update(source='https://huggingface.co/datasets/nvidia/OpenCodeReasoning/blob/main/split_0/train-00000-of-00030.parquet'))
    def test_reasoning_shard_size(self):self.bad(lambda d:d['reasoning_dataset_research_only']['file'].update(size_bytes=242388598))
    def test_existing_emotions_not_duplicated(self):self.bad(lambda d:d.update(existing_multilingual_emotion_pins='new_unreviewed.json'))

if __name__=='__main__':unittest.main(verbosity=2)
