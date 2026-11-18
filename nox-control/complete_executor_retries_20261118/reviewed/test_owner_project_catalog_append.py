import base64
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('append_helper',HERE/'owner_project_catalog_append.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class CatalogAppendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'kb').mkdir()
        self.db=self.root/'kb/knowledge.sqlite'
        with sqlite3.connect(self.db) as con:
            con.execute('CREATE TABLE s03_items(id INTEGER PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,meta TEXT,sha256 TEXT)')

    def config(self):
        catalog={'schema':'NOX_AUTONOMY_PROCESS_POOL_V1','tasks':[{'id':'1A03.project.fixture','keep':{'claim':'untouched'}}]}
        return {'schema':'NOX_NATIVE_SUBAGENT_BINDING_V1','instance_id':60509551,
            'execution_mode':'NATIVE_PROJECT_V1','owner_authorized':True,'mode':'NORMAL','target':3,
            'catalog':catalog,'catalog_sha256':a.digest(a.encoded(catalog)),
            'owner_request':'original-owner','owner_source_sha':'a'*40,
            'module_pins':{'owner_subagent_dispatcher.py':'b'*64},
            'project_executor':{'roots':{'NOX_PROJECT_SOURCE':{'path':str(self.root/'source')}}},
            'extra_metadata':{'keep':True}}

    def s03(self,receipt):
        pin=a.digest(a.encoded(receipt));text='NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+pin
        with sqlite3.connect(self.db) as con:
            con.execute('INSERT INTO s03_items(segment,text,provenance,meta,sha256) VALUES(?,?,?,?,?)',
                ('M2',text,'owner_native_subagents',json.dumps({'receipt':receipt}),a.digest(('M2|'+text).encode())))

    def test_compose_changes_only_catalog_and_hash(self):
        config=self.config();before=copy.deepcopy(config);pin='c'*64
        plan={'parent_task_id':'1A02','task_id':'1A02.project.receipt_order','root_id':'NOX_PROJECT_SOURCE',
              'review_origin':'OWNER_REVIEWED','original_task_accepted':False,'queue_id':'Q1_RUNTIME_CHAT'}
        row={'id':plan['task_id'],'handler':a.HANDLER,'queue_id':'Q1_RUNTIME_CHAT','resource':'CPU_LIGHT',
             'source_sha256':'b'*64,'params':{'parent_task_id':'1A02','plan_sha256':pin},'deps':['1A03.project.fixture']}
        after=a.compose(config,row,plan,pin)
        self.assertEqual(config,before)
        self.assertEqual(after['catalog']['tasks'][:-1],before['catalog']['tasks'])
        for key,value in before.items():
            if key not in ('catalog','catalog_sha256'):self.assertEqual(after[key],value)
        with self.assertRaisesRegex(a.Hold,'ALREADY_CATALOGED'):a.compose(after,row,plan,pin)
        row['params']['parent_task_id']='1A04'
        with self.assertRaisesRegex(a.Hold,'NEW_CATALOG_SCOPE'):a.compose(config,row,plan,pin)

    def test_malformed_row_cannot_block_live_catalog_refresh(self):
        config=self.config();pin='c'*64
        plan={'parent_task_id':'1A02','task_id':'1A02.project.receipt_order','root_id':'NOX_PROJECT_SOURCE',
              'review_origin':'OWNER_REVIEWED','original_task_accepted':False,'queue_id':'Q1_RUNTIME_CHAT'}
        row={'id':plan['task_id'],'handler':a.HANDLER,'queue_id':'Q1_RUNTIME_CHAT','resource':'CPU_LIGHT',
             'source_sha256':'b'*64,'params':{'parent_task_id':'1A02','plan_sha256':pin},'deps':['1A03.project.fixture']}
        for change in ({'priority':'P99'},{'estimated_cost':True},{'estimated_cost':float('nan')},
                       {'title':''},{'unreviewed':True},{'deps':['1A03.project.fixture']*2}):
            with self.subTest(change=change),self.assertRaises(a.Hold):
                a.compose(config,{**row,**change},plan,pin)

    def test_exact_s03_requires_unique_receipt_and_does_not_write(self):
        receipt={'job_id':'job-fixture','phase':'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED','value':2}
        self.s03(receipt);before=self.db.read_bytes()
        proof=a.exact_s03(self.root,receipt)
        self.assertTrue(proof['verified']);self.assertEqual(self.db.read_bytes(),before)
        with self.assertRaisesRegex(a.Hold,'S03_EXACT'):a.exact_s03(self.root,{**receipt,'value':3})
        self.s03(receipt)
        with self.assertRaisesRegex(a.Hold,'S03_EXACT'):a.exact_s03(self.root,receipt)

    def test_config_cas_preserves_foreign_edit(self):
        path=self.root/'config.json';a.atomic(path,b'old')
        old,info=a.read(path);a.atomic(path,b'foreign')
        with self.assertRaisesRegex(a.Hold,'CONFIG_CAS_CHANGED'):a.config_cas(path,old,info,b'new')
        self.assertEqual(path.read_bytes(),b'foreign')
        raw,info=a.read(path);a.config_cas(path,raw,info,b'new')
        self.assertEqual(path.read_bytes(),b'new')

    def test_asset_payload_is_exact_and_bounded(self):
        raw=b'fixture';pin=a.digest(raw);specification={'assets':{'fixture.source':pin}}
        self.assertEqual(a.decode_assets({'fixture.source':base64.b64encode(raw).decode()},specification),{'fixture.source':raw})
        with self.assertRaisesRegex(a.Hold,'ASSET_DIGEST'):
            a.decode_assets({'fixture.source':base64.b64encode(b'other').decode()},specification)

    def test_predecessor_requires_done_current_claim_and_actual_model(self):
        tid='1A03.project.fixture';claim={'pid':777,'nonce':'c'*24}
        evidence={'state':'INTEGRATED','integration_verified':True,'task_id':tid,'claim':claim['nonce'],
                  'trusted_tests_unchanged':True,'tests':{'passed':True,'failures':0,'errors':0,'skipped':0}}
        event={'project_evidence':evidence,'project_evidence_sha256':a.digest(a.encoded(evidence)),
               'planner_receipt':{'model_called':True,'model_turns':2},
               'reference':{'plan_sha256':'d'*64,'contract_sha256':'e'*64}}
        receipt={'task_id':tid,'claim':claim,'source_sha256':'b'*64,'job_id':'job-fixture',
                 'phase':'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED','original_task_accepted':False,
                 'worker_result':event,'plan_sha256':'d'*64}
        pin=a.digest(a.encoded(receipt));self.s03(receipt)
        row={'status':'done','handler':a.HANDLER,'parent_task_id':'1A03','owner_claim':claim,
             'result':{'receipt':receipt,'receipt_sha256':pin,'verified':True}}
        state={'tasks':{tid:row}};config=self.config();specification={
             'required_task':{'id':tid,'receipt_sha256':pin,'contract_sha256':'e'*64},
             'expected_director':{'pid':777},'expected_callback_sha256':'b'*64}
        import contextlib
        executor=Mock();executor.load_plan.return_value={'task_id':tid,'review_origin':'MODEL_CANDIDATE','root_id':'NOX_PROJECT_SOURCE'}
        executor.tree.side_effect=lambda path:contextlib.nullcontext('anchored-source')
        proof=a.predecessor_proof(self.root,state,config,specification,executor)
        self.assertTrue(proof['source_postimages_verified']);executor._check_source.assert_called_once_with('anchored-source',executor.load_plan.return_value,integrated=True)
        bad=copy.deepcopy(state);bad['tasks'][tid]['status']='pending'
        with self.assertRaisesRegex(a.Hold,'REQUIRED_TASK_NOT_DONE'):a.predecessor_proof(self.root,bad,config,specification,executor)
        bad=copy.deepcopy(state);bad['tasks'][tid]['owner_claim']['nonce']='f'*24
        with self.assertRaisesRegex(a.Hold,'REQUIRED_TASK_RECEIPT'):a.predecessor_proof(self.root,bad,config,specification,executor)
        # A valid-shaped non-model receipt cannot unlock the next code task.
        bad=copy.deepcopy(state);bad_receipt=bad['tasks'][tid]['result']['receipt'];bad_receipt['worker_result']['planner_receipt']['model_called']=False
        badpin=a.digest(a.encoded(bad_receipt));bad['tasks'][tid]['result']['receipt_sha256']=badpin
        spec2=copy.deepcopy(specification);spec2['required_task']['receipt_sha256']=badpin
        with self.assertRaisesRegex(a.Hold,'REQUIRED_MODEL_INTEGRATION'):a.predecessor_proof(self.root,bad,config,spec2,executor)

if __name__=='__main__':unittest.main(verbosity=2)
