"""Focused tests for the append-only supplemental acceptance rollup."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

CONTROL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CONTROL/'complete_executor_20261118/source_baseline'))

import work_progress


GPU_ADDENDUM = ('complete_executor_20261118/evidence/addenda/'
                'native_gpu_inventory_addendum_20261119_2v14-12_run44545226279.json')
CENSUS_ADDENDUM = ('complete_executor_20261118/evidence/addenda/'
                   'native_process_census_addendum_20261119_run44547824185_6v14-02.json')
LEGACY_ADDENDUM = ('complete_executor_20261118/evidence/addenda/'
                   'native_snapshot_addendum_20261119_2v14-12_6v14-02.json')
MANIFEST = ('complete_executor_20261118/evidence/'
            'all295_execution_disposition.json')


class SupplementalAcceptanceRollupTests(unittest.TestCase):
    def fixture(self, sidecars):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / 'nox-control'
        tasks_dir = root / 'four_queue_20261118'
        tasks_dir.mkdir(parents=True)
        for filename in ('work_tasks.json', 'work_ideas.json', 'work_receipts.json'):
            shutil.copyfile(CONTROL/'four_queue_20261118'/filename, tasks_dir/filename)
        evidence_dir = root/'complete_executor_20261118/evidence'
        addenda_dir = evidence_dir/'addenda'
        addenda_dir.mkdir(parents=True)
        shutil.copyfile(CONTROL/MANIFEST, evidence_dir/'all295_execution_disposition.json')
        for path in sidecars:
            source = CONTROL/'complete_executor_20261118/evidence/addenda'/Path(path).name
            shutil.copyfile(source, addenda_dir/source.name)
        return temporary, tasks_dir

    def assert_separate_counts(self, summary, task_id):
        self.assertEqual(summary['frozen_295_count'], 295)
        self.assertEqual(summary['existing_receipt_count'], summary['total']['completed'])
        self.assertEqual(summary['supplemental_accepted_count'], 1)
        self.assertEqual(summary['supplemental_accepted_task_ids'], [task_id])
        self.assertEqual(summary['supplemental_acceptance']['original_acceptance_added'], 0)
        self.assertEqual(summary['supplemental_acceptance']['frozen_295_count'], 295)
        self.assertEqual(summary['supplemental_acceptance']['existing_receipt_count'],
                         summary['existing_receipt_count'])

    def test_gpu_inventory_shape_uses_task_spec_record_pointer_and_owner_run_binding(self):
        temporary, directory = self.fixture([GPU_ADDENDUM])
        self.addCleanup(temporary.cleanup)
        summary = work_progress.summarize(directory)
        self.assert_separate_counts(summary, '2V14-12')
        item = summary['supplemental_acceptance']['items'][0]
        self.assertEqual(item['acceptance_pointer'], '#/additional_evidence_records/0')
        self.assertEqual(item['evidence_pointer'], '#/evidence/inventory')
        self.assertEqual(item['workflow_run_id'], 44545226279)
        self.assertEqual(item['job_id'], 135633879980)
        self.assertEqual(item['owner_authorization_id'], 7012187265)
        self.assertEqual(item['record_number'], 6)
        self.assertTrue(item['source_path'].endswith(Path(GPU_ADDENDUM).name))
        self.assertTrue(item['source_url'].startswith('https://github.com/'))

    def test_process_census_shape_uses_explicit_evidence_pointer_and_audit_run_binding(self):
        temporary, directory = self.fixture([CENSUS_ADDENDUM])
        self.addCleanup(temporary.cleanup)
        summary = work_progress.summarize(directory)
        self.assert_separate_counts(summary, '6V14-02')
        item = summary['supplemental_acceptance']['items'][0]
        self.assertEqual(item['acceptance_pointer'], '#/additional_evidence_records/0')
        self.assertEqual(item['evidence_pointer'], '#/audit_evidence/point_in_time_census')
        self.assertEqual(item['workflow_run_id'], 44547824185)
        self.assertEqual(item['job_id'], 135643082464)
        self.assertEqual(item['owner_authorization_id'], 7012555110)
        self.assertEqual(item['workflow_conclusion'], 'failure')
        self.assertEqual(item['evidence_result'], 'HOLD_AUDIT_CENSUS_INCOMPLETE')
        self.assertEqual(item['title'], 'Проверить реальный набор фоновых процессов.')

    def test_legacy_unbound_snapshot_sidecar_is_excluded_with_reason(self):
        temporary, directory = self.fixture([LEGACY_ADDENDUM])
        self.addCleanup(temporary.cleanup)
        summary = work_progress.summarize(directory)
        self.assertEqual(summary['frozen_295_count'], 295)
        self.assertEqual(summary['supplemental_accepted_count'], 0)
        self.assertEqual(summary['supplemental_accepted_task_ids'], [])
        self.assertEqual(summary['existing_receipt_count'], summary['total']['completed'])
        excluded = summary['supplemental_acceptance']['excluded']
        self.assertTrue(any(row.get('task_id') == '2V14-12' and
                            row['reason'] == 'FROZEN_MANIFEST_BINDING_MISMATCH'
                            for row in excluded))

    def test_wrong_spec_sha_does_not_increment(self):
        temporary, directory = self.fixture([GPU_ADDENDUM])
        self.addCleanup(temporary.cleanup)
        sidecar_path = directory.parent/'complete_executor_20261118/evidence/addenda'/Path(GPU_ADDENDUM).name
        document = json.loads(sidecar_path.read_text(encoding='utf-8'))
        document['scope']['criteria']['2V14-12']['spec_sha256'] = '0' * 64
        sidecar_path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        summary = work_progress.summarize(directory)
        self.assertEqual(summary['frozen_295_count'], 295)
        self.assertEqual(summary['supplemental_accepted_count'], 0)
        self.assertEqual(summary['existing_receipt_count'], summary['total']['completed'])
        reasons = {row['reason'] for row in summary['supplemental_acceptance']['excluded']}
        self.assertIn('CRITERION_SPEC_SHA_MISMATCH', reasons)

    def test_unresolved_evidence_pointer_does_not_increment(self):
        temporary, directory = self.fixture([GPU_ADDENDUM])
        self.addCleanup(temporary.cleanup)
        sidecar_path = directory.parent/'complete_executor_20261118/evidence/addenda'/Path(GPU_ADDENDUM).name
        document = json.loads(sidecar_path.read_text(encoding='utf-8'))
        document['scope']['criteria']['2V14-12']['acceptance_binding']['evidence_pointer'] = (
            '#/additional_evidence_records/99')
        sidecar_path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        summary = work_progress.summarize(directory)
        self.assertEqual(summary['frozen_295_count'], 295)
        self.assertEqual(summary['supplemental_accepted_count'], 0)
        self.assertEqual(summary['existing_receipt_count'], summary['total']['completed'])
        reasons = {row['reason'] for row in summary['supplemental_acceptance']['excluded']}
        self.assertIn('POINTER_TARGET_MISSING', reasons)


if __name__ == '__main__':
    unittest.main()
