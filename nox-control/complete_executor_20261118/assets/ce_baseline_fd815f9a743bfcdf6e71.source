"""4A02: every train/dev/holdout split needs the declared task categories."""
import unittest

import test_forge_split_guard as original


class PerSplitCoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture=original.SplitPreflightTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def missing(self,split,task):
        self.fixture.split_rows[split]=[row for row in self.fixture.split_rows[split]
                                       if row['task']!=task]
        self.fixture.write_all()
        with self.assertRaisesRegex(ValueError,'TASK_COVERAGE_REQUIRED_PER_SPLIT'):
            self.fixture.assess()

    def test_holdout_without_code_cannot_certify_code_evaluation(self):
        self.missing('holdout','code')

    def test_dev_without_speech_cannot_certify_tuning_coverage(self):
        self.missing('dev','speech')

    def test_train_without_memory_is_not_repaired_by_holdout_rows(self):
        self.missing('train','memory')

    def test_full_categories_in_every_split_still_pass(self):
        result=self.fixture.assess()
        self.assertEqual(result['status'],'SOURCE_SPLITS_VERIFIED')
        for coverage in result['coverage'].values():
            self.assertEqual(set(coverage['tasks']),original.TASKS)
        self.assertFalse(result['training_started'])


if __name__=='__main__':unittest.main()
