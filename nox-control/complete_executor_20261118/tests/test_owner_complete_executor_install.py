import base64
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installer', HERE/'owner_complete_executor_install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def seed(self):
        data=b'def value():\n    return 1\n';assets={'baseline.source':data}
        manifest={'schema':'NOX_PROJECT_SOURCE_BASELINE_V1','files':{'source.py':installer.digest(data)},'source_refs':[]}
        seed={'schema':'NOX_PROJECT_SOURCE_BOOTSTRAP_V1','root':str(self.root/'projects/owner_executor/source_workspace'),
              'files':{'source.py':'baseline.source'},'source_refs':[],
              'manifest_sha256':installer.digest(installer.encoded(manifest))}
        return {'source_bootstrap':seed},assets

    def test_atomic_git_bootstrap_and_reuse_preserves_legitimate_edit(self):
        specification,assets=self.seed()
        first=installer.bootstrap_source(self.root,specification,assets,'1')
        target=Path(first['root'])
        self.assertRegex(first['initial_git_head'],r'^[a-f0-9]{40}$')
        (target/'source.py').write_bytes(b'owner later change\n')
        again=installer.bootstrap_source(self.root,specification,assets,'2')
        self.assertTrue(again['reused_without_source_reset'])
        self.assertEqual((target/'source.py').read_bytes(),b'owner later change\n')
        self.assertEqual(first['initial_git_head'],again['current_git_head'])

    def test_unowned_source_directory_never_reseeded(self):
        specification,assets=self.seed();target=Path(specification['source_bootstrap']['root'])
        target.mkdir(parents=True);(target/'source.py').write_bytes(b'owner content')
        with self.assertRaises((FileNotFoundError,installer.Hold)):
            installer.bootstrap_source(self.root,specification,assets,'1')
        self.assertEqual((target/'source.py').read_bytes(),b'owner content')

    def test_directory_publish_never_replaces_existing(self):
        source=self.root/'stage';source.mkdir();(source/'new').write_text('new')
        destination=self.root/'target';destination.mkdir();(destination/'owner').write_text('old')
        with self.assertRaises(installer.Hold):installer.publish_directory_no_replace(source,destination)
        self.assertEqual((destination/'owner').read_text(),'old')
        self.assertTrue((source/'new').exists())

    def test_bundle_and_content_address_cannot_drift(self):
        data=b'{"schema":"fixture"}';pin=installer.digest(data)
        spec={'schema':'NOX_COMPLETE_EXECUTOR_INSTALL_SPEC_V1','assets':{'m.json':pin},
              'package_files':{'manifests/'+pin+'.json':'m.json'}}
        assets=installer.decode_assets({'m.json':base64.b64encode(data).decode()},spec)
        self.assertEqual(len(installer.package_changes(self.root,spec,assets)),1)
        with self.assertRaises(installer.Hold):installer.decode_assets({'m.json':base64.b64encode(b'{}').decode()},spec)
        spec['package_files']={'manifests/'+'0'*64+'.json':'m.json'}
        with self.assertRaises(installer.Hold):installer.package_changes(self.root,spec,assets)

    def test_failure_after_write_rolls_back_tracked_file(self):
        old=b'old';new=b'new';path=self.root/'scripts/a.py';installer.atomic(path,old)
        real=installer.atomic;calls=[]
        def fail_after_write(p,raw,mode=0o600):
            real(p,raw,mode);calls.append(raw)
            if len(calls)==1:raise OSError('simulated lost control response after replace')
        with patch.object(installer,'atomic',side_effect=fail_after_write):
            with self.assertRaises(OSError):installer.apply_transaction(self.root,{'scripts/a.py':new},{'scripts/a.py':old})
        self.assertEqual(path.read_bytes(),old)

    def test_rollback_refuses_foreign_bytes(self):
        path=self.root/'scripts/a.py';installer.atomic(path,b'foreign')
        result=installer.rollback_transaction(self.root,{'scripts/a.py':b'ours'}, {'scripts/a.py':b'old'},['scripts/a.py'])
        self.assertEqual(path.read_bytes(),b'foreign')
        self.assertNotIn('PREIMAGE_RESTORED',result.values())

    def test_config_preserves_catalog_and_supports_autonomous_contract(self):
        tasks=[{'id':'old.'+str(i),'opaque':{'keep':i}} for i in range(7)]
        catalog={'schema':'NOX_AUTONOMY_PROCESS_POOL_V1','tasks':tasks}
        config={'schema':'NOX_NATIVE_SUBAGENT_BINDING_V1','instance_id':60509551,'owner_authorized':True,
                'mode':'NORMAL','target':3,'catalog':catalog,'catalog_sha256':installer.digest(installer.encoded(catalog))}
        runtime={'scripts/owner_subagent_dispatcher.py':b'callback',
                 'scripts/owner_project_executor.py':b'executor','scripts/owner_project_test_runner.py':b'runner'}
        reference='f'*64
        row={'id':'1A03.project.model','handler':'owner_native_project_work','queue_id':installer.QUEUE_IDS[0],
             'source_sha256':installer.digest(b'callback'),'resource':'CPU_LIGHT','deps':[],
             'params':{'parent_task_id':'1A03','contract_sha256':reference}}
        project={'schema':'NOX_PROJECT_EXECUTOR_CONFIG_V1','enabled':True,'max_workers':3,
                 'package_root':str(self.root/'state/dispatcher/project_executor/package'),
                 'state_root':str(self.root/'state/dispatcher/project_executor/run'),
                 'roots':{'NOX_PROJECT_SOURCE':{'path':str(self.root/'projects/owner_executor/source_workspace'),
                         'integration_kind':'SOURCE_WORKSPACE'}},
                 'source_pins':{name:installer.digest(runtime['scripts/'+name])
                                for name in ('owner_project_executor.py','owner_project_test_runner.py')}}
        specification={'catalog_append':[row],'project_executor':project,
                       'package_files':{'contracts/'+reference+'.json':'contract.json'}}
        changed=json.loads(installer.prepare_config(installer.encoded(config),runtime,specification,self.root,'123','a'*40))
        self.assertEqual(changed['catalog']['tasks'][:7],tasks)
        self.assertEqual(len(changed['catalog']['tasks']),8)
        self.assertEqual(changed['global_worker_cap'],3)
        self.assertEqual(changed['execution_mode'],'NATIVE_PROJECT_V1')
        self.assertIn(installer.LEGACY_LEAF_SHA,changed['historical_leaf_source_sha256'])
        invalid=copy.deepcopy(specification);invalid['catalog_append'][0]['params']['contract_sha256']='0'*64
        with self.assertRaises(installer.Hold):installer.prepare_config(installer.encoded(config),runtime,invalid,self.root,'123','a'*40)

    def test_old_child_census_includes_thread_children_and_reparented_survivors(self):
        proc=self.root/'proc'
        for parent,thread,children in ((10,10,'20'),(10,11,'20 21'),(20,20,'30'),(21,21,''),(30,30,'')):
            directory=proc/str(parent)/'task'/str(thread);directory.mkdir(parents=True)
            (directory/'children').write_text(children)
        identities={20:{'pid':20,'ppid':10,'start_ticks':200,'pgrp':20},
                    21:{'pid':21,'ppid':10,'start_ticks':210,'pgrp':21},
                    30:{'pid':30,'ppid':20,'start_ticks':300,'pgrp':30}}
        with patch.object(installer,'process_identity',side_effect=lambda pid:identities.get(pid)):
            old=installer.descendant_snapshot(10,proc)
            self.assertEqual([x['pid'] for x in old],[20,21,30])
            identities[20]={**identities[20],'ppid':1}
            identities.pop(21);identities[30]={**identities[30],'start_ticks':301}
            self.assertEqual([x['pid'] for x in installer.live_previous_descendants(old)],[20])
            with self.assertRaisesRegex(installer.Hold,'OLD_CHILDREN_ALIVE'):
                installer.wait_previous_descendants_stopped(old,timeout=0)
            identities.pop(20)
            self.assertTrue(installer.wait_previous_descendants_stopped(old,timeout=0)['all_exact_processes_exited'])

    def test_acceptance_requires_same_three_distinct_processes(self):
        first={'director':{'pid':1},'observed_at':1,'workers':[
            {'pid':pid,'start_ticks':pid*10,'ppid':1,'heartbeat_at':1} for pid in (2,3,4)]}
        second=copy.deepcopy(first);second['observed_at']=3
        for row in second['workers']:row['heartbeat_at']=2
        self.assertTrue(installer.stable_three([first,second]))
        stale=copy.deepcopy(first);stale['observed_at']=3
        self.assertFalse(installer.stable_three([first,stale]))
        second['workers'][0]['start_ticks']+=1
        self.assertFalse(installer.stable_three([first,second]))
        second=copy.deepcopy(first);second['observed_at']=3;second['workers'][2]=second['workers'][1]
        self.assertFalse(installer.stable_three([first,second]))
        self.assertFalse(installer.stable_three([first]))

if __name__=='__main__':unittest.main(verbosity=2)
