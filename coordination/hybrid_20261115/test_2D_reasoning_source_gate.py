"""Synthetic fixture suite. No external dataset and no native OneHost access."""
import copy
import importlib
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parent))
g=importlib.import_module('2D_reasoning_source_gate')

class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.catalogue={'schema':'NOX_AUTO_2D_IMMUTABLE_PUBLIC_EVIDENCE_V2',
          'reasoning_dataset_research_only':{'repo_id':g.REPO,'revision':g.REV,'training_authorized':False,
            'quality_privacy_license_review_required':True,'file':{'path':g.SHARD,'size_bytes':g.SIZE,'sha256':g.SHA}}}
        self.policy={'schema':'NOX_OWNER_REVIEWED_SOURCE_LICENSES_V1','repository':g.REPO,'revision':g.REV,
          'approved_triplets':[{'dataset':'curated','platform':'example','license':'mit',
                                'source_license_reviewed':True,'attribution_reviewed':True}]}
        self.sample={'dataset':'curated','source':'example','id':'q100','license':'mit','split':'train',
                     'input':'Write a pure function','output':'Synthetic controlled response'}
        self.holdout={g.group_hash({**self.sample,'id':'q999'})}
    def check(self,rows=None):
        return g.validate([self.sample] if rows is None else rows,self.catalogue,self.policy,self.holdout)
    def reject(self,change):
        change(self)
        with self.assertRaises(g.Hold):self.check()
    def test_01_no_native_claim(self):
        r=self.check();self.assertFalse(r['native_training_verified']);self.assertFalse(r['parquet_payload_sha_verified'])
    def test_02_card_license_not_row_license(self):self.reject(lambda x:x.sample.update(license='cc-by-4.0'))
    def test_03_unknown_platform(self):self.reject(lambda x:x.sample.update(source='unknown'))
    def test_04_unknown_license(self):self.reject(lambda x:x.sample.update(license='proprietary'))
    def test_05_unreviewed_rights(self):self.reject(lambda x:x.policy['approved_triplets'][0].update(source_license_reviewed=False))
    def test_06_unreviewed_attribution(self):self.reject(lambda x:x.policy['approved_triplets'][0].update(attribution_reviewed=False))
    def test_07_no_reviewed_policy(self):self.reject(lambda x:x.policy.update(approved_triplets=[]))
    def test_08_policy_wrong_revision(self):self.reject(lambda x:x.policy.update(revision='main'))
    def test_09_dataset_wrong_revision(self):self.reject(lambda x:x.catalogue['reasoning_dataset_research_only'].update(revision='main'))
    def test_10_dataset_wrong_sha(self):self.reject(lambda x:x.catalogue['reasoning_dataset_research_only']['file'].update(sha256='0'*64))
    def test_11_no_auto_training(self):self.reject(lambda x:x.catalogue['reasoning_dataset_research_only'].update(training_authorized=True))
    def test_12_original_test_split(self):self.reject(lambda x:x.sample.update(split='test'))
    def test_13_original_valid_split(self):self.reject(lambda x:x.sample.update(split='valid'))
    def test_14_unresolved_input(self):self.reject(lambda x:x.sample.update(input='-'))
    def test_15_empty_completion(self):self.reject(lambda x:x.sample.update(output=''))
    def test_16_holdout_family_overlap(self):self.reject(lambda x:x.holdout.add(g.group_hash(x.sample)))
    def test_17_holdout_family_casefold(self):self.reject(lambda x:x.holdout.add(g.group_hash({**x.sample,'source':'EXAMPLE','dataset':'CURATED'})))
    def test_18_empty_holdout_set(self):self.reject(lambda x:x.holdout.clear())
    def test_19_bad_holdout_sha(self):self.reject(lambda x:x.holdout.add('bad'))
    def test_20_duplicate_completion(self):
        with self.assertRaises(g.Hold):self.check([self.sample,copy.deepcopy(self.sample)])
    def test_21_multiple_reasoning_paths_same_question(self):
        other={**self.sample,'output':'Different synthetic solution'}
        self.assertEqual(self.check([self.sample,other])['distinct_question_families'],1)
    def test_22_distinct_question(self):
        other={**self.sample,'id':'q101'}
        self.assertEqual(self.check([self.sample,other])['distinct_question_families'],2)
    def test_23_empty_source(self):self.reject(lambda x:x.sample.update(source=''))
    def test_24_duplicate_policy_tuple(self):self.reject(lambda x:x.policy['approved_triplets'].append(copy.deepcopy(x.policy['approved_triplets'][0])))
    def test_25_policy_wrong_repo(self):self.reject(lambda x:x.policy.update(repository='other/repo'))
    def test_26_empty_rows(self):
        with self.assertRaises(g.Hold):self.check([])
if __name__=='__main__':unittest.main()
