import copy
import importlib.util
import json
from pathlib import Path
import unittest

BASE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("pins", BASE/"2D_pins.py")
pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pins)

class EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = json.loads((BASE/"2D_pins.json").read_text())
    def rejects(self, mutate):
        d=copy.deepcopy(self.good)
        mutate(d)
        with self.assertRaises(ValueError): pins.validate(d)
    def test_valid(self):
        self.assertEqual(pins.validate(self.good)["total_remote_file_bytes"],70138500)
    def test_exact_file_count(self):
        self.assertEqual(pins.validate(self.good)["files"],5)
    def test_unknown_base(self):
        self.rejects(lambda d:d.update(active_hf_base_verified=True))
    def test_training_claim(self):
        self.rejects(lambda d:d.update(approved_for_training=True))
    def test_native_claim(self):
        self.rejects(lambda d:d.update(native_download_count=1))
    def test_mutable_revision(self):
        self.rejects(lambda d:d["datasets"][0].update(revision="main"))
    def test_wrong_revision_length(self):
        self.rejects(lambda d:d["datasets"][1].update(revision="a"*39))
    def test_missing_digest(self):
        self.rejects(lambda d:d["datasets"][0]["files"][0].update(sha256=None))
    def test_bad_digest(self):
        self.rejects(lambda d:d["datasets"][0]["files"][0].update(sha256="z"*64))
    def test_duplicate_file(self):
        self.rejects(lambda d:d["datasets"][0]["files"][1].update(path=d["datasets"][0]["files"][0]["path"]))
    def test_unsafe_path(self):
        self.rejects(lambda d:d["datasets"][0]["files"][0].update(path="../evil.bin"))
    def test_wrong_size(self):
        self.rejects(lambda d:d["datasets"][1]["files"][1].update(size_bytes=300))
    def test_float_size(self):
        self.rejects(lambda d:d["datasets"][1]["files"][1].update(size_bytes=350063.0))
    def test_licence_missing(self):
        self.rejects(lambda d:d["datasets"][0].update(licence_card=None))
    def test_privacy_missing(self):
        self.rejects(lambda d:d["datasets"][0].update(sensitive_data_filter_required=False))
    def test_ru_es_mislabeled(self):
        self.rejects(lambda d:d["datasets"][0].update(language_card=["en"]))
    def test_emotions_incorrectly_ru(self):
        self.rejects(lambda d:d["datasets"][1].update(language_card=["en","ru"]))
    def test_tree_holdout(self):
        self.rejects(lambda d:d["datasets"][0].update(split_group_key="message_id"))
    def test_adapter_merge(self):
        self.rejects(lambda d:d["adapters_research_only"][0].update(may_merge=True))
    def test_adapter_unknown_licence(self):
        self.rejects(lambda d:d["adapters_research_only"][1].update(licence_card="apache-2.0"))
    def test_pickle_guard(self):
        self.rejects(lambda d:d["adapters_research_only"][1].update(untrusted_pickle_training_args_bin=False))
    def test_unknown_adapter_checksum(self):
        self.rejects(lambda d:d["adapters_research_only"][1].update(adapter_weight_sha256="a"*64))

if __name__=='__main__':unittest.main(verbosity=2)
