import base64
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('kernel_installer',HERE/'owner_kernel_self_fd_install.py')
m=importlib.util.module_from_spec(loader);loader.loader.exec_module(m)

class KernelSelfFDInstallerTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((HERE/'self_fd_install_spec.json').read_text())
        self.assets={name:(HERE/'self_fd_install_assets'/name).read_bytes() for name in self.spec['assets']}
        self.bundle={name:base64.b64encode(raw).decode() for name,raw in self.assets.items()}
        self.raw=(HERE/'current_config_6967801407.json').read_bytes()
        self.runtime,self.package,self.descriptor=m.self_fd_assets(self.bundle,self.spec)

    def test_actual_inputs_change_runner_two_pins_and_one_catalog_row_only(self):
        old,new=m.self_fd_compose(self.raw,self.runtime,self.spec)
        self.assertEqual(len(old['catalog']['tasks']),20);self.assertEqual(len(new['catalog']['tasks']),21)
        self.assertEqual(new['catalog']['tasks'][:-1],old['catalog']['tasks'])
        for key,value in old.items():
            if key not in ('catalog','catalog_sha256','module_pins','project_executor'):self.assertEqual(new[key],value)
        for key,value in old['module_pins'].items():
            if key!='owner_project_test_runner.py':self.assertEqual(new['module_pins'][key],value)
        project=copy.deepcopy(new['project_executor']);project['source_pins']['owner_project_test_runner.py']=old['project_executor']['source_pins']['owner_project_test_runner.py']
        self.assertEqual(project,old['project_executor']);self.assertEqual(new['catalog']['tasks'][-1]['params'],{'parent_task_id':'1A03','plan_sha256':m.SELF_FD_PLAN})

    def test_model_contract_or_changed_predecessor_config_is_rejected(self):
        bad=copy.deepcopy(self.spec);bad['catalog_append'][0]['params']={'parent_task_id':'1A03','contract_sha256':'a'*64}
        with self.assertRaisesRegex(m.Hold,'SELF_FD_APPEND_SCOPE'):m.self_fd_compose(self.raw,self.runtime,bad)
        changed=json.loads(self.raw);changed['owner_request']='foreign'
        with self.assertRaisesRegex(m.Hold,'SELF_FD_CONFIG_PREIMAGE'):m.self_fd_compose(m.encoded(changed),self.runtime,self.spec)

    def test_assets_cannot_overwrite_another_runtime_or_unpinned_package(self):
        bad=copy.deepcopy(self.spec);name=next(iter(bad['runtime_paths']));bad['runtime_paths'][name]='scripts/owner_project_executor.py'
        with self.assertRaisesRegex(m.Hold,'SELF_FD_ASSET_SCOPE'):m.self_fd_assets(self.bundle,bad)
        bad=copy.deepcopy(self.spec);name=next(iter(bad['package_paths']));bad['package_paths'][name]='config/owner_native_subagents.json'
        with self.assertRaisesRegex(m.Hold,'SELF_FD_PACKAGE_PATH'):m.self_fd_assets(self.bundle,bad)
        bad=copy.deepcopy(self.bundle);name=next(iter(self.spec['runtime_paths']));bad[name]=base64.b64encode(b'foreign').decode()
        with self.assertRaisesRegex(m.Hold,'SELF_FD_ASSET_HASH'):m.self_fd_assets(bad,self.spec)

    def facts(self):
        proof={'schema':'NOX_KERNEL_SELF_FD_TEST_ADAPTER_V1','mode':'KERNEL_SELF_FD_TEST_ADAPTER',
            'scope':'SELF_STAT_AND_BOOT_ID_ONLY','kernel_backed':True,'fresh_pread_offset_zero':True,
            'own_pid_start_verified':True,'full_proc_available':False,'foreign_pid_visibility':False,
            'reserved_regular_file_descriptors':2,'directory_descriptors_preserved':0,'procfs_magic':40864,
            'verifier_pid':12346,'verifier_parent_pid':12345,'start_ticks':1000,'boot_id_sha256':'a'*64,
            'stat_reads':4,'boot_reads':4}
        return {'uid':65534,'gid':65534,**{k:True for k in ('network_denied','fork_denied','exec_denied','host_path_hidden','no_new_privs','seccomp_filter')},'kernel_self_fd_adapter':proof}

    def test_adapter_requires_real_self_only_proof_and_actual_parent(self):
        facts=self.facts();m.self_fd_adapter(facts,12345)
        for key,value in [('kernel_backed',False),('full_proc_available',True),('foreign_pid_visibility',True),
                          ('directory_descriptors_preserved',1),('verifier_parent_pid',999),('boot_reads',0)]:
            wrong=copy.deepcopy(facts);wrong['kernel_self_fd_adapter'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(m.Hold,'SELF_FD_KERNEL_PROOF'):m.self_fd_adapter(wrong,12345)
        with self.assertRaisesRegex(m.Hold,'SELF_FD_CONFINEMENT'):m.self_fd_adapter({**facts,'uid':0},12345)

    def test_current_fd_descriptor_equals_integrated_plan_postimages(self):
        pin=self.descriptor['original_plan_reference']['plan_sha256']
        path=HERE.parent/'bindings/retries/6V14-04/plans'/(pin+'.json');plan=json.loads(path.read_text())
        context={x['path']:x['sha256'] for x in plan['context']};context.update({x['path']:x['after_sha256'] for x in plan['files']})
        self.assertEqual(context,{x['path']:x['sha256'] for x in self.descriptor['context']})
        self.assertEqual(plan['verification'],self.descriptor['verification']);self.assertEqual(plan['verification']['min_tests'],36)
        candidate=HERE.parent/'bindings/retries/6V14-04/candidate'
        for name,pin in context.items():self.assertEqual(m.digest((candidate/name).read_bytes()),pin)

    def test_history_keeps_terminal_failures_but_allows_pending_claim_progress(self):
        before={'tasks':{'failed_model':{'status':'blocked','owner_claim':{'pid':1},'result':{'sha':'model'}},
                         'failed_rescue':{'status':'blocked','owner_claim':{'pid':1},'result':{'sha':'reviewed'}},
                         'pending':{'status':'pending','owner_claim':{'pid':1},'result':None}}}
        after=copy.deepcopy(before);after['tasks']['pending']['owner_claim']['pid']=2
        self.assertTrue(m.preserve_terminal_history(before,after)['verified'])
        after['tasks']['failed_rescue']['result']={'sha':'lost'}
        self.assertFalse(m.preserve_terminal_history(before,after)['verified'])

    def test_native_preflight_failure_cannot_stop_or_apply(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.ExitStack() as stack:
            root=Path(directory);(root/'state').mkdir();lock=root/'state/owner_maintenance.lock';lock.write_bytes(b'');lock.chmod(0o600)
            before={key:b'existing-reviewed-fixture' for key in self.spec['expected_native']};before[m.CONFIG]=self.raw
            owner={'director':{'pid':3760381,'start_ticks':176197984,'ppid':114,'pgrp':3760381},'workers':[]}
            funcs={'preimages':Mock(return_value=before),'protected_snapshot':Mock(return_value={'protected':'same'}),
                'stop_clear':Mock(return_value=True),'self_fd_drain':Mock(return_value=({'tasks':{}},{'processes':owner})),
                'self_fd_history':Mock(return_value={'old':'exact-S03-fixture'}),
                'source_snapshot':Mock(return_value={'count':28,'files_sha256':m.SELF_FD_SOURCE_PIN}),
                'load_budget_module':Mock(return_value=(object(),root/'private-budget')),
                'budget_preflight':Mock(return_value={'decision':{'eligible':True}}),
                'self_fd_preflight':Mock(side_effect=m.Hold('HOLD_COMPLETE_EXECUTOR_SELF_FD_NATIVE_FIXTURE_FAILED')),
                'stop_checked':Mock(),'apply_transaction':Mock(),'self_fd_receipt':Mock(),'supervisor':Mock()}
            for name,value in funcs.items():stack.enter_context(patch.object(m,name,value))
            stack.enter_context(patch.dict(os.environ,NOX_OWNER_REQUEST_ID='123456',NOX_OWNER_SOURCE_SHA='d'*40))
            with self.assertRaisesRegex(m.Hold,'NATIVE_FIXTURE_FAILED'):m.install_self_fd(self.bundle,self.spec,root)
            funcs['self_fd_preflight'].assert_called_once();funcs['stop_checked'].assert_not_called();funcs['apply_transaction'].assert_not_called()
            funcs['supervisor'].assert_not_called()
            for path in self.package:self.assertFalse((root/path).exists())
            self.assertFalse((root/m.CONFIG).exists());self.assertFalse((root/m.SELF_FD_RUNNER).exists())

if __name__=='__main__':unittest.main(verbosity=2)
