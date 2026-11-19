import ast
import base64
import contextlib
import copy
import hashlib
import importlib.util
import json
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('runtime_update',HERE/'owner_project_runtime_update.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class RuntimeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=json.loads((HERE/'current_config_6966579330.json').read_bytes())
        self.config['project_executor']['package_root']=str(self.root/'state/dispatcher/project_executor/package')
        self.config['project_executor']['state_root']=str(self.root/'state/dispatcher/project_executor/run')
        self.config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']=str(self.root/'projects/owner_executor/source_workspace')
        self.catalog=copy.deepcopy(json.loads((HERE.parent/'bindings/retries/catalog_append_template.json').read_bytes()))
        if isinstance(self.catalog,dict):self.catalog=self.catalog.get('tasks',self.catalog.get('catalog_append'))
        planner=json.loads((HERE.parent/'planner/manifest.json').read_bytes())
        self.catalog.append({'id':'1A03.project.cursor_admission.focus_retry.20261118','handler':u.PROJECT_HANDLER,
            'queue_id':'Q1_RUNTIME_CHAT','deps':[],'resource':'CPU_LIGHT','priority':'P1','estimated_cost':2,
            'title':'Actual focused planner retry','source_sha256':None,
            'params':{'parent_task_id':'1A03','contract_sha256':planner['contract_sha256']}})
        self.callback=self.config['module_pins']['owner_subagent_dispatcher.py']
        for row in self.catalog:row['source_sha256']=self.callback
        previous={'1A03':'1A03.project.cursor_admission.20261118','3A02':'3A02.project.readback_revoke.20261118',
            '3B05':'3B05.project.strict_skill_json.20261118','6V14-04':'6V14-04.project.receipt_time_order.20261118'}
        package={}
        for row in self.catalog:
            field='contract_sha256' if row['params']['parent_task_id']=='1A03' else 'plan_sha256'
            package[('contracts/' if field=='contract_sha256' else 'plans/')+row['params'][field]+'.json']='fixture_'+str(len(package))
        self.spec={'schema':u.UPDATE_SCHEMA,'expected_native':{'scripts/owner_subagent_dispatcher.py':self.callback},
            'catalog_append':self.catalog,'package_files':package,'retry_of':{row['id']:previous[row['params']['parent_task_id']] for row in self.catalog},
            'expected_director':{'pid':777,'start_ticks':7000},
            'expected_workers':[{'pid':pid,'start_ticks':8000} for pid in (778,779,780)]}
        self.runtime={'scripts/owner_project_executor.py':b'# candidate executor\n','scripts/owner_project_test_runner.py':b'# candidate runner\n',
            'scripts/owner_project_planner.py':b'# candidate planner\n','scripts/owner_project_model_client.py':b'# candidate client\n'}

    def test_update_changes_only_authorized_pins_and_appends_old_fifteen(self):
        before=copy.deepcopy(self.config)
        old,new=u.compose_update(u.encoded(before),self.runtime,self.spec,self.root)
        self.assertEqual(old,before);self.assertEqual(self.config,before)
        self.assertEqual(new['catalog']['tasks'][:15],before['catalog']['tasks'])
        self.assertEqual(len(new['catalog']['tasks']),19)
        for field in ('owner_request','owner_source_sha','policy','historical_leaf_source_sha256','leaf_source_pins','project_handoff'):
            self.assertEqual(new.get(field),before.get(field))
        self.assertEqual(new['module_pins']['owner_subagent_dispatcher.py'],self.callback)
        self.assertEqual(new['project_executor']['roots'],before['project_executor']['roots'])
        self.assertEqual(new['project_executor']['sandbox'],before['project_executor']['sandbox'])
        self.assertEqual(new['project_executor']['dependency_manifest'],before['project_executor']['dependency_manifest'])
        invalid=copy.deepcopy(self.spec);invalid['catalog_append'][0]['priority']='P88'
        with self.assertRaisesRegex(u.Hold,'ROW_PRESENTATION'):u.compose_update(u.encoded(before),self.runtime,invalid,self.root)

    def test_runtime_allowlist_excludes_callback_or_source_workspace(self):
        assets={'executor.py':b'# executor\n','runner.py':b'# runner\n'}
        pins={key:u.digest(value) for key,value in assets.items()}
        spec={'schema':u.UPDATE_SCHEMA,'assets':pins,'runtime_paths':{
            'executor.py':'scripts/owner_project_executor.py','runner.py':'scripts/owner_project_test_runner.py'}}
        bundle={key:base64.b64encode(value).decode() for key,value in assets.items()}
        self.assertEqual(set(u.decode_update_assets(bundle,spec)[1]),{'scripts/owner_project_executor.py','scripts/owner_project_test_runner.py'})
        for bad in ('scripts/owner_subagent_dispatcher.py','projects/owner_executor/source_workspace/work_progress.py'):
            invalid=copy.deepcopy(spec);invalid['runtime_paths']['executor.py']=bad
            with self.assertRaisesRegex(u.Hold,'RUNTIME_PATH'):u.decode_update_assets(bundle,invalid)

    def source_tree(self):
        root=Path(self.config['project_executor']['roots']['NOX_PROJECT_SOURCE']['path']);root.mkdir(parents=True)
        pins={}
        for i,relative in enumerate(self.config['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths']):
            data=('approved baseline '+str(i)).encode();u.atomic(root/relative,data,0o644);pins[relative]=u.digest(data)
        marker={'schema':'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1','root':str(root),'file_pins':pins,'initial_git_head':'a'*40}
        u.atomic(root/'NOX_EXECUTOR_BOOTSTRAP.json',u.encoded(marker))
        u.atomic(root/'.git/HEAD',b'ref: refs/heads/nox-owner-project-source\n')
        u.atomic(root/'.git/refs/heads/nox-owner-project-source',b'a'*40+b'\n');u.atomic(root/'.git/index',b'original-index')
        return root

    def test_full_twenty_eight_file_snapshot_preserves_dirty_postimages(self):
        root=self.source_tree();path=root/'work_progress.py';path.write_bytes(b'legitimate integrated dirty postimage')
        before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        first=u.source_snapshot(self.root,self.config);second=u.source_snapshot(self.root,self.config)
        self.assertEqual(first,second);self.assertEqual(first['count'],28)
        self.assertEqual(first['files']['work_progress.py']['sha256'],u.digest(b'legitimate integrated dirty postimage'))
        after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        (root/'unapproved.py').write_text('foreign')
        with self.assertRaisesRegex(u.Hold,'UNKNOWN_SOURCE_FILE'):u.source_snapshot(self.root,self.config)
        self.assertEqual(path.read_bytes(),b'legitimate integrated dirty postimage')

    def terminal_state(self):
        state={'tasks':{}};expected={};(self.root/'kb').mkdir(exist_ok=True)
        with sqlite3.connect(self.root/'kb/knowledge.sqlite') as db:
            db.execute('CREATE TABLE s03_items(id INTEGER PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,meta TEXT,sha256 TEXT)')
            for index,row in enumerate(self.catalog):
                old=self.spec['retry_of'][row['id']];claim={'pid':777,'nonce':format(index+1,'024x')}
                receipt={'job_id':'fixture-'+str(index),'task_id':old,'phase':'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
                    'source_sha256':self.callback,'claim':claim,'original_task_accepted':False,'project_source_changed':False,
                    'worker_result':{'project_evidence':{'state':'BLOCKED_PLANNER' if old.startswith('1A03.') else 'BLOCKED_TESTS',
                        'project_source_changed':False}}}
                pin=u.digest(u.encoded(receipt));expected[old]=pin
                state['tasks'][old]={'handler':u.PROJECT_HANDLER,'parent_task_id':row['params']['parent_task_id'],'status':'blocked',
                    'owner_claim':claim,'result':{'verified':True,'receipt_sha256':pin,'receipt':receipt}}
                text='NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+pin
                db.execute('INSERT INTO s03_items(segment,text,provenance,meta,sha256) VALUES(?,?,?,?,?)',
                    ('M2',text,'owner_native_subagents',json.dumps({'receipt':receipt}),u.digest(('M2|'+text).encode())))
        self.spec['terminal_receipts']=expected;return state

    def test_all_four_terminal_receipts_are_exact_s03_and_current_claim(self):
        state=self.terminal_state();raw=(self.root/'kb/knowledge.sqlite').read_bytes()
        proof=u.terminal_proofs(self.root,state,self.spec,self.config)
        self.assertEqual(len(proof),4);self.assertTrue(all(row['verified'] for row in proof.values()))
        self.assertEqual((self.root/'kb/knowledge.sqlite').read_bytes(),raw)
        for change in ('running','claim','receipt'):
            bad=copy.deepcopy(state);row=bad['tasks']['1A03.project.cursor_admission.20261118']
            if change=='running':row['status']='running'
            elif change=='claim':row['owner_claim']['nonce']='f'*24
            else:row['result']['receipt']['project_source_changed']=True
            with self.subTest(change=change),self.assertRaises(u.Hold):u.terminal_proofs(self.root,bad,self.spec,self.config)

    def test_history_rejects_missing_or_rewritten_claim_result(self):
        state=self.terminal_state();after=copy.deepcopy(state);after['tasks']['new']={'status':'pending'}
        self.assertTrue(u.unchanged_history(state,after)['verified'])
        old_id=next(iter(state['tasks']));after['tasks'][old_id]['result']['verified']=False
        self.assertFalse(u.unchanged_history(state,after)['verified'])
        del after['tasks'][old_id];self.assertFalse(u.unchanged_history(state,after)['verified'])

    def test_sandbox_preflight_failure_occurs_before_dispatcher_stop_or_source_write(self):
        state=self.terminal_state();source=self.source_tree();config=copy.deepcopy(self.config)
        # Exact local fixture module preimages; no fixture source is ever executed.
        expected={}
        for name in config['module_pins']:
            raw=('# current '+name+'\n').encode();u.atomic(self.root/'scripts'/name,raw,0o644)
            expected['scripts/'+name]=config['module_pins'][name]=u.digest(raw)
        self.callback=config['module_pins']['owner_subagent_dispatcher.py']
        for row in self.spec['catalog_append']:row['source_sha256']=self.callback
        for name in u.SANDBOX_MODULES:config['project_executor']['source_pins'][name]=config['module_pins'][name]
        for name in u.MODEL_MODULES:config['project_executor']['model']['source_pins'][name]=config['module_pins'][name]
        u.atomic(self.root/'scripts/nox_dispatcher_t855u.py',b'# dispatcher\n');expected['scripts/nox_dispatcher_t855u.py']=u.digest(b'# dispatcher\n')
        dep=b'{"schema":"fixture"}';dep_pin=u.digest(dep);dep_path=self.root/'state/dispatcher/project_executor/package/manifests'/(dep_pin+'.json')
        u.atomic(dep_path,dep);config['project_executor']['dependency_manifest']={'path':str(dep_path),'sha256':dep_pin}
        raw=u.encoded(config);u.atomic(self.root/u.CONFIG,raw);expected[u.CONFIG]=u.digest(raw)
        u.atomic(self.root/u.STATE,u.encoded(state));u.atomic(self.root/'state/owner_maintenance.lock',b'')
        specification=copy.deepcopy(self.spec);specification['expected_native']=expected
        assets={Path(path).name:value for path,value in self.runtime.items()}
        specification['runtime_paths']={Path(path).name:path for path in self.runtime}
        specification['assets']={key:u.digest(value) for key,value in assets.items()}
        bundle={key:base64.b64encode(value).decode() for key,value in assets.items()}
        source_before={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
        queue_before=(self.root/u.STATE).read_bytes()
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'1234','NOX_OWNER_SOURCE_SHA':'a'*40}), \
             patch.object(u,'package_changes',return_value={str(dep_path.relative_to(self.root)):dep}), \
             patch.object(u,'protected_snapshot',return_value={}),patch.object(u,'expected_processes',return_value={}), \
             patch.object(u,'terminal_proofs',return_value={}),patch.object(u,'supervisor') as supervisor, \
             patch.object(u,'sandbox_preflight',side_effect=u.Hold('HOLD_COMPLETE_EXECUTOR_PREFLIGHT_FIXTURE_FAILURE')), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(u.Hold,'PREFLIGHT_FIXTURE_FAILURE'):u.update(bundle,specification,self.root)
        supervisor.assert_not_called()
        self.assertEqual((self.root/u.CONFIG).read_bytes(),raw);self.assertEqual((self.root/u.STATE).read_bytes(),queue_before)
        self.assertEqual(source_before,{str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()})
        for path,pin in expected.items():self.assertEqual(u.digest((self.root/path).read_bytes()),pin)

    def test_shared_helpers_match_reviewed_installer_and_fixture_checks_depth(self):
        old=ast.parse((HERE/'owner_complete_executor_install.py').read_text());new=ast.parse((HERE/'owner_project_runtime_update.py').read_text())
        olddefs={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)};newdefs={n.name:n for n in new.body if isinstance(n,ast.FunctionDef)}
        copied={'preimages','apply_transaction','rollback_transaction','stop_checked','descendant_snapshot','wait_previous_descendants_stopped','sandbox_preflight','stable_three'}
        for name in copied:self.assertEqual(ast.dump(olddefs[name]),ast.dump(newdefs[name]),name)
        compile(u.PREFLIGHT_TEST,'test_source.py','exec')
        self.assertIn(b'/work/project/source',u.PREFLIGHT_TEST);self.assertIn(b'parents[3]',u.PREFLIGHT_TEST)
        self.assertEqual(u.PREFLIGHT_TEST.count(b'    def test_'),4)

    def test_exact_first_prompt_is_tokenized_without_inference_or_compaction(self):
        manifest=json.loads((HERE.parent/'planner/manifest.json').read_bytes())
        contract_path=HERE.parent/'planner'/manifest.get('contract_file','contract_1a03.json')
        if not contract_path.exists():
            candidates=list((HERE.parent/'planner').glob('*.json'))
            matches=[p for p in candidates if u.digest(p.read_bytes())==manifest['contract_sha256']]
            self.assertEqual(len(matches),1);contract_path=matches[0]
        contract=json.loads(contract_path.read_bytes())
        baseline=HERE.parent/'bindings/minimal_project_source'
        snapshot={row['path']:(baseline/row['path']).read_bytes() for row in contract['context']}
        project=copy.deepcopy(self.config['project_executor']);project['model']=manifest['model']
        planner=(HERE.parent/'planner/owner_project_planner.py').read_bytes()
        modules=self.root/'preflight/modules';modules.mkdir(parents=True)
        sent=[];count=[3068]
        class Response:
            status=200
            def __init__(self,value):self.value=value
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return u.encoded(self.value)
        def request(req,timeout):
            sent.append((req.full_url,json.loads(req.data) if req.data else None))
            path=req.full_url.removeprefix('http://127.0.0.1:8098')
            values={'/v1/models':{'data':[{'id':project['model']['expected_model_id']}]},
                '/props':{'default_generation_settings':{'n_ctx':4096}},
                '/apply-template':{'prompt':'actual server template stub'},'/tokenize':{'tokens':[1]*count[0]}}
            self.assertIn(path,values);return Response(values[path])
        opener=Mock();opener.open.side_effect=request
        with patch.object(u.urllib.request,'build_opener',return_value=opener),contextlib.redirect_stdout(io.StringIO()):
            result=u.model_prompt_preflight(self.root,project,contract,snapshot,modules,{'scripts/owner_project_planner.py':planner})
            self.assertTrue(result['fits_context']);self.assertFalse(result['model_inference_called'])
            self.assertTrue(result['first_prompt_unmodified']);self.assertEqual(result['input_tokens'],3068)
            intro=json.loads(sent[2][1]['messages'][1]['content']);self.assertTrue(intro['focused_source'])
            self.assertEqual(intro['requirement'],contract['instruction'])
            count[0]=3069
            with self.assertRaisesRegex(u.Hold,'FIRST_PROMPT_CONTEXT_EXCEEDED'):
                u.model_prompt_preflight(self.root,project,contract,snapshot,modules,{'scripts/owner_project_planner.py':planner})
        self.assertNotIn('/v1/chat/completions',[path for path,_ in sent])

if __name__=='__main__':unittest.main(verbosity=2)
