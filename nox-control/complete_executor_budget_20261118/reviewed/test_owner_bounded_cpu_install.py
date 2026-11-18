import base64
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('budget_installer',HERE/'owner_bounded_cpu_install.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class BudgetInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=json.loads((HERE/'current_config_6966949947.json').read_bytes())
        self.expected=json.loads((HERE/'expected_native_before_budget.json').read_bytes())
        source=HERE.parent/'runtime_budget_fix';self.runtime={}
        for name in b.BUDGET_MODULES:
            actual='owner_subagent_instruction_truth_project.py' if name=='owner_subagent_instruction_truth.py' else name
            self.runtime['scripts/'+name]=(source/actual).read_bytes()
        self.spec={'schema':b.BUDGET_UPDATE_SCHEMA,'expected_native':self.expected,
            'rebind_task_ids':[row['id'] for row in self.config['catalog']['tasks'][15:]],
            'expected_no_children':True,'expected_director':{'pid':77,'start_ticks':700}}

    def test_exact_four_catalog_rebind_and_narrow_configuration_changes(self):
        before=copy.deepcopy(self.config);old,new=b.compose_budget_config(b.encoded(before),self.runtime,self.spec)
        self.assertEqual(old,before);self.assertEqual(self.config,before)
        self.assertEqual(len(new['catalog']['tasks']),19);self.assertEqual(new['catalog']['tasks'][:15],before['catalog']['tasks'][:15])
        callback=b.digest(self.runtime['scripts/owner_subagent_dispatcher.py'])
        for a,z in zip(before['catalog']['tasks'][15:],new['catalog']['tasks'][15:]):self.assertEqual(z,{**a,'source_sha256':callback})
        self.assertEqual(new['project_executor'],before['project_executor'])
        self.assertEqual(new['owner_request'],before['owner_request']);self.assertEqual(new['owner_source_sha'],before['owner_source_sha'])
        self.assertIn(before['module_pins']['owner_subagent_dispatcher.py'],new['historical_project_source_sha256'])
        invalid=copy.deepcopy(self.spec);invalid['rebind_task_ids'][0]='unknown'
        with self.assertRaisesRegex(b.Hold,'REBIND_EXACT'):b.compose_budget_config(b.encoded(before),self.runtime,invalid)

    def test_only_four_binding_modules_can_be_written(self):
        assets={Path(path).name:raw for path,raw in self.runtime.items()}
        spec={**self.spec,'assets':{key:b.digest(value) for key,value in assets.items()},
            'runtime_paths':{Path(path).name:path for path in self.runtime}}
        bundle={key:base64.b64encode(value).decode() for key,value in assets.items()}
        self.assertEqual(b.budget_assets(bundle,spec),self.runtime)
        invalid=copy.deepcopy(spec);invalid['runtime_paths']['owner_autonomy_pool.py']='scripts/owner_project_executor.py'
        with self.assertRaisesRegex(b.Hold,'MODULE_SET'):b.budget_assets(bundle,invalid)

    def test_retry_rebind_forbids_any_existing_authoritative_row(self):
        b.absent_retry_rows({'tasks':{}},self.spec['rebind_task_ids'])
        for status in ('pending','running','done','blocked'):
            with self.subTest(status=status),self.assertRaisesRegex(b.Hold,'ALREADY_ADMITTED'):
                b.absent_retry_rows({'tasks':{self.spec['rebind_task_ids'][0]:{'status':status}}},self.spec['rebind_task_ids'])

    def test_pending_resumption_is_not_terminal_history_loss(self):
        before={'tasks':{'pending':{'status':'pending','owner_claim':{'pid':1},'result':'wait'},
            'done':{'status':'done','owner_claim':{'pid':1},'result':'verified'},
            'blocked':{'status':'blocked','owner_claim':{'pid':1},'result':'verified failure'}}}
        after=copy.deepcopy(before);after['tasks']['pending']['owner_claim']={'pid':2};after['tasks']['pending']['status']='running'
        result=b.preserve_terminal_history(before,after)
        self.assertTrue(result['verified']);self.assertEqual(result['terminal_rows_checked'],2)
        self.assertEqual(result['nonterminal_claim_changes_count'],1)
        after['tasks']['done']['result']='tampered';self.assertFalse(b.preserve_terminal_history(before,after)['verified'])
        del after['tasks']['done'];self.assertIn('done',b.preserve_terminal_history(before,after)['missing_old_ids'])

    def test_transient_child_is_waited_out_without_a_kill(self):
        states=[({'tasks':{'legacy':{'status':'running'}}},['legacy']),({'tasks':{}},[])]
        observations=[b.Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_UNEXPECTED_DIRECTOR_CHILDREN'),
            {'director':{'pid':77,'start_ticks':700},'children':[],'observed_at':1}]
        with patch.object(b,'stop_clear',return_value=True),patch.object(b,'queue_idle',side_effect=states), \
             patch.object(b,'zero_children_guard',side_effect=observations),patch.object(b.time,'sleep') as sleep:
            state,observed=b.wait_idle_zero_children(self.root,self.spec)
        self.assertEqual(state['tasks'],{});self.assertEqual(observed['children'],[]);sleep.assert_called_once_with(.5)
        with patch.object(b,'stop_clear',return_value=True),patch.object(b,'queue_idle',return_value=({'tasks':{}},[])), \
             patch.object(b,'zero_children_guard',side_effect=observations[0]):
            with self.assertRaisesRegex(b.Hold,'NOT_DRAINED'):b.wait_idle_zero_children(self.root,self.spec,timeout=0)

    def cgroup(self,inactive_gib=10,psi=0):
        path=self.root/'cgroup';path.mkdir(exist_ok=True)
        files={'memory.current':str(99*b.GIB),'memory.max':str(100*b.GIB),
            'memory.stat':'file '+str(95*b.GIB)+'\nshmem '+str(40*b.GIB)+'\ninactive_file '+str(inactive_gib*b.GIB)+'\n',
            'memory.pressure':f'some avg10={psi} avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n',
            'cpu.pressure':'some avg10=0 avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n'}
        for name,value in files.items():(path/name).write_text(value)
        return path

    def test_real_pure_validator_and_independent_arithmetic_hold_boundaries(self):
        (self.root/'scripts').mkdir();policy=(HERE.parent/'runtime_budget_fix/owner_resource_policy.py').read_bytes()
        (self.root/'scripts/owner_resource_policy.py').write_bytes(policy)
        module,stage=b.load_budget_module(self.root,self.runtime,self.expected,'fixture')
        with contextlib.redirect_stdout(io.StringIO()):
            result=b.budget_preflight(self.config,module,stage,'first',self.cgroup())
            self.assertTrue(result['decision']['eligible'])
            self.assertEqual(result['decision']['reserved_bytes'],3*384*b.MIB)
            self.assertEqual(result['decision']['headroom_bytes'],100*b.GIB-99*b.GIB+10*b.GIB-3*384*b.MIB)
            with self.assertRaisesRegex(b.Hold,'NATIVE_ADMISSION_HOLD'):
                b.budget_preflight(self.config,module,stage,'low',self.cgroup(inactive_gib=0))
            with self.assertRaisesRegex(b.Hold,'NATIVE_ADMISSION_HOLD'):
                b.budget_preflight(self.config,module,stage,'pressure',self.cgroup(psi=1))

    def test_seven_historical_project_receipts_verify_without_requiring_current_director_claim(self):
        (self.root/'kb').mkdir();state={'tasks':{}};old_source=self.config['module_pins']['owner_subagent_dispatcher.py']
        with sqlite3.connect(self.root/'kb/knowledge.sqlite') as db:
            db.execute('CREATE TABLE s03_items(id INTEGER PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,meta TEXT,sha256 TEXT)')
            for i in range(7):
                tid='fixture.'+str(i);claim={'pid':3734446,'nonce':str(i)};status='done' if i<3 else 'blocked'
                phase='PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED' if status=='done' else 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                receipt={'task_id':tid,'job_id':tid,'phase':phase,'claim':claim,'source_sha256':old_source,'original_task_accepted':False}
                pin=b.digest(b.encoded(receipt));state['tasks'][tid]={'status':status,'handler':b.PROJECT_HANDLER,'owner_claim':claim,
                    'result':{'verified':True,'receipt':receipt,'receipt_sha256':pin}}
                text='NOX native job '+tid+' '+phase+' receipt_sha256 '+pin
                db.execute('INSERT INTO s03_items(segment,text,provenance,meta,sha256) VALUES(?,?,?,?,?)',
                    ('M2',text,'owner_native_subagents',json.dumps({'receipt':receipt}),b.digest(('M2|'+text).encode())))
        before=(self.root/'kb/knowledge.sqlite').read_bytes();proof=b.project_history_proofs(self.root,state,self.config)
        self.assertEqual(len(proof),7);self.assertEqual((self.root/'kb/knowledge.sqlite').read_bytes(),before)
        updated=copy.deepcopy(self.config);updated['module_pins']['owner_subagent_dispatcher.py']='f'*64
        updated['historical_project_source_sha256']=[old_source]
        self.assertEqual(b.project_history_proofs(self.root,state,updated),proof)

if __name__=='__main__':unittest.main(verbosity=2)
