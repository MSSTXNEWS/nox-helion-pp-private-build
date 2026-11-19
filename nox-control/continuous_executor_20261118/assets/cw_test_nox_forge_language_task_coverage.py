"""4A02: each evaluation language must cover every intended task in each split."""
import unittest

import test_forge_split_guard as original


class LanguageTaskCoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.SplitPreflightTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def missing_pair(self, split, language, task):
        self.fixture.split_rows[split] = [row for row in self.fixture.split_rows[split]
            if (row['language'], row['task']) != (language, task)]
        self.fixture.write_all()
        with self.assertRaisesRegex(ValueError, 'LANGUAGE_TASK_COVERAGE_REQUIRED_PER_SPLIT'):
            self.fixture.assess()

    def test_holdout_needs_spanish_code_despite_full_marginal_sets(self):
        self.missing_pair('holdout', 'es', 'code')

    def test_dev_needs_russian_speech_despite_full_marginal_sets(self):
        self.missing_pair('dev', 'ru', 'speech')

    def test_train_needs_spanish_memory_despite_full_marginal_sets(self):
        self.missing_pair('train', 'es', 'memory')

    def test_full_bilingual_task_matrix_is_still_source_only(self):
        result = self.fixture.assess()
        self.assertEqual(result['status'], 'SOURCE_SPLITS_VERIFIED')
        self.assertFalse(result['training_started'])


if __name__ == '__main__':
    unittest.main()
