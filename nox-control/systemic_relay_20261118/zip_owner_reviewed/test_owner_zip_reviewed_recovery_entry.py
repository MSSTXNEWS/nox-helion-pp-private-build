"""Source-only acceptance of the one-shot reviewed ZIP recovery handoff.

No remote access, no new worker, no S03 write and no queue mutation.
"""
import hashlib
import importlib.util
from pathlib import Path
import os
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
ENTRY=HERE/'owner_zip_reviewed_recovery_entry.py'
OPERATOR=REPO/'nox-control/owner_native_operator.py'
CANDIDATE=HERE/'merge_web_source.py'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReviewedZipRecovery(unittest.TestCase):
    def test_pinned_candidate_matches_reviewed_source(self):
        op=load(ENTRY,'owner_zip_reviewed_entry')
        actual=hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
        self.assertEqual(actual,op.REVIEWED_SHA)
        self.assertEqual(op.SOURCE_SHA,
           'a580a7d9f3efd570cf4e84396ceb3e6f980fe2dc846d0fda633b6e65b4c36b54')
        self.assertNotEqual(actual,op.SOURCE_SHA)
        self.assertEqual(op.PREDECESSOR_REASON,'MODEL_REPORTED_BLOCKER_NOT_VERIFIED')
        self.assertEqual(op.PREDECESSOR_RECEIPT_SHA,
           'f0657485d16c6fb8010929ddec27108e0438196d4fba4a8f197cd4479e6f8b85')

    def test_immutable_plan_has_exact_original_scope(self):
        op=load(ENTRY,'owner_zip_reviewed_plan')
        p=op.reviewed_plan()
        self.assertEqual(p['operation'],'apply_reviewed_files')
        self.assertEqual(p['review_origin'],'OWNER_REVIEWED')
        self.assertEqual(p['root_id'],'NOX_PROJECT_SOURCE')
        self.assertEqual(p['parent_task_id'],'0V14-14')
        self.assertEqual(p['original_task_accepted'],False)
        self.assertEqual(p['acceptance_scope'],'SOURCE_PATCH_TESTED')
        self.assertEqual(p['verification'],{'kind':'python_unittest','min_tests':6,
            'modules':['test_nox_merge_overlay_paths'],'timeout_sec':120})
        self.assertEqual({r['path'] for r in p['context']},
                         {'merge_web_source.py','test_nox_merge_overlay_paths.py'})
        self.assertEqual(p['files'],[{'path':'merge_web_source.py',
           'before_sha256':op.SOURCE_SHA,'after_sha256':op.REVIEWED_SHA,
           'payload_sha256':op.REVIEWED_SHA}])
        self.assertEqual(len(op.encoded(p)),len(op.encoded(p)))  # deterministic

    def test_exact_owner_bundle_no_name_or_path_collisions(self):
        own=load(OPERATOR,'owner_zip_reviewed_transport')
        op=load(ENTRY,'owner_zip_reviewed_transport_entry')
        self.assertEqual(own.FILES['repair'],
            'nox-control/systemic_relay_20261118/zip_owner_reviewed/owner_zip_reviewed_recovery_entry.py')
        previous=os.getcwd()
        try:
            os.chdir(REPO)
            selected=own.repair_bundle_paths('repair',own.FILES['repair'],())
        finally:
            os.chdir(previous)
        self.assertEqual({Path(z).name for z in selected},op.ASSET_NAMES)
        self.assertEqual(len(selected),3)
        helper=REPO/'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py'
        self.assertEqual(hashlib.sha256(helper.read_bytes()).hexdigest(),op.HELPER_SHA)

    def test_no_mutation_prior_to_existing_publisher(self):
        data=ENTRY.read_text()
        for unsafe in ('subprocess.run(', 'os.system(', 'supervisorctl stop',
                       'killall', '/proc/sys/vm/drop_caches'):
            self.assertNotIn(unsafe,data)
        self.assertIn("reviewed_publisher.run(bundle, spec)",data)
        self.assertIn("not active, 'ACTIVE_NATIVE_CLAIM'",data)
        self.assertIn('ONE_SHOT_NO_REPLAY',data)


if __name__=='__main__':
    unittest.main()
