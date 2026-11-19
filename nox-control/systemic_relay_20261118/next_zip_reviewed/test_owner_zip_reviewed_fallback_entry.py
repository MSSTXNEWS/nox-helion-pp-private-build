"""Source-only negative and positive checks of the terminal ZIP fallback.

Never touches a live server, owner lease or task queue. The real native
publisher remains the only authority for exact S03 and source CAS admission.
"""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

HERE=Path(__file__).parent
ROOT=HERE.parents[1]
TARGET=HERE/'owner_zip_reviewed_fallback_entry.py'
SPEC=importlib.util.spec_from_file_location('zip_fallback_under_test',TARGET)
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeHelper:
    def __init__(self, blocked=True):
        self.blocked=blocked
        self.active=[]
        self.source={
          'files_sha256':m.SOURCE_FILES_SHA,
          'files':{
             m.SOURCE:{'sha256':m.BEFORE_SHA},
             'test_nox_merge_overlay_paths.py':{'sha256':m.TEST_SHA}}}
        self.config={
          'owner_authorized':True,
          'instance_id':60509551,
          'target':3,'global_worker_cap':3,
          'execution_mode':'NATIVE_PROJECT_V1',
          'mode':'NORMAL',
          'systemic_relay':{'sha256':m.PREDECESSOR_MANIFEST_SHA}}
        self.claim={'nonce':'f'*24,'pid':359172}
        self.receipt={
          'phase':'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
          'original_task_accepted':False,
          'project_source_changed':False,
          'plan_sha256':None,
          'claim':self.claim,
          'worker_result':{'project_evidence':{
             'state':'BLOCKED_PLANNER',
             'reason':'HOLD_PROJECT_PLANNER_MODEL_INCOMPLETE_RESPONSE',
             'project_source_changed':False}}}
        self.context=[
          {'path':m.SOURCE,'sha256':m.BEFORE_SHA},
          {'path':'test_nox_merge_overlay_paths.py','sha256':m.TEST_SHA}]
        self.verification={'kind':'python_unittest',
           'modules':['test_nox_merge_overlay_paths'],
           'min_tests':6,'timeout_sec':120}
        self.contract={'context':self.context,'editable_paths':[m.SOURCE],
                       'verification':self.verification,
                       'parent_task_id':m.PARENT,'queue_id':'Q4_INTEGRATION_ACCEPTANCE'}
        self.contract_raw=m.encoded(self.contract)
        self.prior_contract=hashlib.sha256(self.contract_raw).hexdigest()
        self.row={'handler':'owner_native_project_work',
            'status':'blocked' if blocked else 'done',
            'parent_task_id':m.PARENT,
            'params':{'contract_sha256':self.prior_contract},
            'owner_claim':self.claim,
            'native_worker_lease':{'phase':'SETTLED'},
            'result':{'verified':True,'scope':'SOURCE_PATCH_TESTED',
                      'receipt_sha256':'a'*64,'receipt':self.receipt}}

    def stop_clear(self,root):
        return True

    def source_snapshot(self,root,config):
        return deepcopy(self.source)

    def queue_idle(self,root):
        return {'tasks':{m.PREDECESSOR_ID:self.row}},list(self.active)

    def read_regular(self,path,max_bytes=0):
        p=str(path)
        if p.endswith('/owner_native_subagents.json'):
            return m.encoded(self.config)
        if p.endswith('.json') and '/contracts/' in p:
            return self.contract_raw
        raise AssertionError('Unexpected read: '+p)


class ZipFastFallbackTests(TestCase):
    def prepare(self,*,blocked=True):
        helper=FakeHelper(blocked=blocked)
        repo=ROOT
        assets={
         'owner_systemic_reviewed_publish.py':
           (HERE.parent/'owner_systemic_reviewed_publish.py').read_bytes(),
         'continuous_transaction_helpers.py':
           (repo/'continuous_executor_20261118/assets/continuous_transaction_helpers.py').read_bytes(),
         'merge_web_source.py':
           (HERE/'merge_web_source.py').read_bytes()
        }
        bundle={k:base64.b64encode(v).decode('ascii') for k,v in assets.items()}
        return helper,bundle

    def invoke(self,helper,bundle):
        # A synthetic config cannot reproduce a private live SHA; simulate only
        # the verified owner config pin while retaining real asset/diff hashes.
        actual_sha=m.sha
        fake_config=m.encoded(helper.config)
        def pinned_sha(raw):
            return m.CONFIG_SHA if raw == fake_config else actual_sha(raw)
        with patch.dict(m.os.environ,{'NOX_OWNER_REQUEST_ID':'123456',
                                      'NOX_OWNER_SOURCE_SHA':'e'*40}), \
             patch.object(m,'BUNDLE',bundle), \
             patch.object(m,'module',return_value=helper), \
             patch.object(m,'sha',side_effect=pinned_sha):
            return m.prepare()

    def test_exact_asset_and_owner_schema(self):
        helper,bundle=self.prepare()
        spec,payload,publisher=self.invoke(helper,bundle)
        self.assertEqual(spec['expected_config_sha256'],m.CONFIG_SHA)
        self.assertRegex(m.PARENT_SPEC_SHA,r'^[a-f0-9]{64}        self.assertEqual(spec['expected_source_files_sha256'],m.SOURCE_FILES_SHA)
        self.assertEqual(len(spec['batches']),1)
        self.assertEqual(len(spec['predecessors']),1)
        self.assertEqual(spec['predecessors'][0]['status'],'blocked')
        self.assertEqual(spec['batches'][0]['catalog_row']['id'],m.TASK_ID)
        self.assertEqual(len(payload),3)
        plan=json.loads(payload['reviewed_zip_plan.json'])
        self.assertEqual(plan['files'][0]['before_sha256'],m.BEFORE_SHA)
        self.assertNotEqual(plan['files'][0]['after_sha256'],m.BEFORE_SHA)
        self.assertFalse(plan['original_task_accepted'])
        self.assertEqual(plan['context'],helper.context)

    def test_never_replace_unsettled_claim(self):
        helper,bundle=self.prepare()
        helper.active=[m.PREDECESSOR_ID]
        with self.assertRaisesRegex(RuntimeError,'PRIOR_CLAIM_ACTIVE'):
            self.invoke(helper,bundle)

    def test_never_replay_terminal_success(self):
        helper,bundle=self.prepare(blocked=False)
        with self.assertRaisesRegex(RuntimeError,'PRIOR_NOT_SETTLED_BLOCKED'):
            self.invoke(helper,bundle)

    def test_never_rebase_changed_source(self):
        helper,bundle=self.prepare()
        helper.source['files'][m.SOURCE]['sha256']='b'*64
        with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'):
            self.invoke(helper,bundle)

    def test_missing_predecessor_receipt_stops(self):
        helper,bundle=self.prepare()
        helper.row['result']['verified']=False
        with self.assertRaisesRegex(RuntimeError,'PRIOR_RECEIPT_SCOPE'):
            self.invoke(helper,bundle)

    def test_only_pre_reviewed_candidate_blob(self):
        helper,bundle=self.prepare()
        raw=bytearray(base64.b64decode(bundle['merge_web_source.py']))
        raw[-3]^=1
        bundle['merge_web_source.py']=base64.b64encode(raw).decode('ascii')
        with self.assertRaisesRegex(RuntimeError,'REVIEWED_PATCH_PIN'):
            self.invoke(helper,bundle)


if __name__=='__main__':
    main()
)
        self.assertEqual(m.PARENT_SPEC_SHA,
            '3ace28409839c1e1259e5a24b7d40c11bf9dec3445b2b0073ef90ecc22b2216e')
        self.assertEqual(spec['expected_source_files_sha256'],m.SOURCE_FILES_SHA)
        self.assertEqual(len(spec['batches']),1)
        self.assertEqual(len(spec['predecessors']),1)
        self.assertEqual(spec['predecessors'][0]['status'],'blocked')
        self.assertEqual(spec['batches'][0]['catalog_row']['id'],m.TASK_ID)
        self.assertEqual(len(payload),3)
        plan=json.loads(payload['reviewed_zip_plan.json'])
        self.assertEqual(plan['files'][0]['before_sha256'],m.BEFORE_SHA)
        self.assertNotEqual(plan['files'][0]['after_sha256'],m.BEFORE_SHA)
        self.assertFalse(plan['original_task_accepted'])
        self.assertEqual(plan['context'],helper.context)

    def test_never_replace_unsettled_claim(self):
        helper,bundle=self.prepare()
        helper.active=[m.PREDECESSOR_ID]
        with self.assertRaisesRegex(RuntimeError,'PRIOR_CLAIM_ACTIVE'):
            self.invoke(helper,bundle)

    def test_never_replay_terminal_success(self):
        helper,bundle=self.prepare(blocked=False)
        with self.assertRaisesRegex(RuntimeError,'PRIOR_NOT_SETTLED_BLOCKED'):
            self.invoke(helper,bundle)

    def test_never_rebase_changed_source(self):
        helper,bundle=self.prepare()
        helper.source['files'][m.SOURCE]['sha256']='b'*64
        with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'):
            self.invoke(helper,bundle)

    def test_missing_predecessor_receipt_stops(self):
        helper,bundle=self.prepare()
        helper.row['result']['verified']=False
        with self.assertRaisesRegex(RuntimeError,'PRIOR_RECEIPT_SCOPE'):
            self.invoke(helper,bundle)

    def test_only_pre_reviewed_candidate_blob(self):
        helper,bundle=self.prepare()
        raw=bytearray(base64.b64decode(bundle['merge_web_source.py']))
        raw[-3]^=1
        bundle['merge_web_source.py']=base64.b64encode(raw).decode('ascii')
        with self.assertRaisesRegex(RuntimeError,'REVIEWED_PATCH_PIN'):
            self.invoke(helper,bundle)


if __name__=='__main__':
    main()
