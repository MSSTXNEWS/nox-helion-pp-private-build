import base64
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


e=load('owner_training_status_entry');b=load('owner_training_status_binding');p=load('owner_download_status_entry')
status=load('owner_training_status');fixture=load('test_owner_training_status_binding').PROXY_FIXTURE


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.scripts=self.root/'scripts';self.scripts.mkdir()
        self.state=self.root/'state';(self.state/'media').mkdir(parents=True);(self.root/'config').mkdir()
        self.context={'request':'789','source_sha':'c'*40,'receipt_sha256':'d'*64}
        self.events=[];self.proxy_state='RUNNING';self.source_guard={'preserved.py':'b'*64}
        self.deploy=types.SimpleNamespace(ROOT=self.root,SCRIPTS=self.scripts,STATE=self.state,PYTHON='/not-used',
            plain=p.plain,read=p.read,lock=p.lock,stopped_by_owner=lambda:False,slots_idle=lambda:True,
            model_identity=lambda _:{'pid':7637,'starttime':'149189867','pgrp':7059},
            proxy_identity=lambda _:{'pid':20,'starttime':'30','pgrp':20},stop_proxy=self.stop,start_proxy=self.start)
        self.helper=types.SimpleNamespace(atomic=self.atomic,service_state=lambda name:{'state':self.proxy_state})
        self.evidence=types.SimpleNamespace(training_observation=lambda _:{'state':'RUNNING','pid':542746,'control_action_performed':False})
        self.proof=types.SimpleNamespace(CONFIG_SCHEMA=status.CONFIG_SCHEMA,context_value=status.context_value,
            admission=lambda context:({},{'context':context}))
        self.raw={name:(HERE/(name+'.py')).read_bytes() for name in ('owner_training_status','owner_training_status_binding')}
        self.observer=b'def snapshot():return {}\ndef evidence_for_model(*args):return {}\n'
        self.atomic(self.scripts/'chat_proxy.py',fixture);self.atomic(self.scripts/'nox_v137_owner_self_observation.py',self.observer)
        for item in (patch.object(e,'BUNDLE',{name+'.py':base64.b64encode(raw).decode() for name,raw in self.raw.items()}),
                     patch.object(b,'PROXY_BEFORE',e.digest(fixture)),patch.object(b,'OBSERVER_BEFORE',e.digest(self.observer))):
            item.start();self.addCleanup(item.stop)

    def atomic(self,path,raw):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o600)

    def stop(self,*args):
        self.events.append('stop-proxy');self.proxy_state='STOPPED'

    def start(self,*args):
        self.events.append('start-proxy');self.proxy_state='RUNNING'

    def run_install(self,probe=lambda *args:{'verified':True},admission=None):
        env={'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40,
             'NOX_TRAINING_RECOVERY_CONTEXT':json.dumps(self.context)}
        if admission is not None:self.proof.admission=admission
        with patch.dict(os.environ,env),patch.object(e,'dependencies',return_value=(self.deploy,self.evidence,self.proof,b,self.helper)),\
             patch.object(e,'guards',side_effect=lambda *args:dict(self.source_guard)),patch.object(e,'live_probe',side_effect=probe),redirect_stdout(io.StringIO()):
            code=e.main()
        return code,json.loads((self.state/'owner_training_status_binding_123.json').read_text())

    def test_valid_pending_admission_installs_without_claiming_optimizer_progress(self):
        code,record=self.run_install()
        self.assertEqual(code,0);self.assertEqual(self.events,['stop-proxy','start-proxy'])
        self.assertEqual(record['training_admission'],self.context)
        self.assertEqual(record['training_before'],record['training_after'])
        self.assertFalse(record['training_control_performed']);self.assertFalse(record['model_restarted'])
        saved=json.loads((self.root/'config/owner_training_status.json').read_text())
        self.assertEqual(saved['admission'],self.context)
        self.assertNotIn('optimizer_steps_verified',record)
        for name in ('owner_training_status.py','owner_training_status_binding.py','chat_proxy.py'):
            self.assertEqual((self.scripts/name).stat().st_mode & 0o777,0o600)

    def test_exact_source_noop_is_idempotent_and_unknown_source_is_rejected(self):
        rows=e.sources(self.deploy,self.proof,b,self.context)
        for row in rows:self.atomic(row['path'],row['new'])
        self.assertFalse(any(row['changed'] for row in e.sources(self.deploy,self.proof,b,self.context)))
        self.atomic(self.scripts/'chat_proxy.py',fixture+b'# unknown\n')
        with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):e.sources(self.deploy,self.proof,b,self.context)

    def test_reviewed_previous_reader_upgrades_but_unknown_reader_does_not(self):
        previous=b'# reviewed previous reader fixture\n'
        self.atomic(self.scripts/'owner_training_status.py',previous)
        with patch.object(e,'PREVIOUS_STATUS_SHA',e.digest(previous)):
            rows=e.sources(self.deploy,self.proof,b,self.context)
            row=next(row for row in rows if row['path'].name=='owner_training_status.py')
            self.assertEqual(row['old'],previous);self.assertTrue(row['changed'])
        self.atomic(self.scripts/'owner_training_status.py',b'# unrelated reader\n')
        with self.assertRaisesRegex(RuntimeError,'MODULE_PREIMAGE'):
            e.sources(self.deploy,self.proof,b,self.context)

    def test_exact_installed_727_reader_upgrade_preserves_existing_bindings(self):
        self.assertEqual(e.LAST_INSTALLED_STATUS_SHA,'72732887e7bf4e4032cb99289b7620301ba48d04d583200464942ebffbd4ff2e')
        previous=b'# exact installed 727 fixture\n'
        for row in e.sources(self.deploy,self.proof,b,self.context):
            self.atomic(row['path'],row['new'])
        self.atomic(self.scripts/'owner_training_status.py',previous)
        with patch.object(e,'LAST_INSTALLED_STATUS_SHA',e.digest(previous)):
            rows=e.sources(self.deploy,self.proof,b,self.context)
        changed=[row['path'].name for row in rows if row['changed']]
        self.assertEqual(changed,['owner_training_status.py'])
        self.assertEqual(self.events,[])

    def test_missing_or_unsealed_context_never_stops_proxy(self):
        with patch.dict(os.environ,{'NOX_TRAINING_RECOVERY_CONTEXT':''}):
            with self.assertRaisesRegex(RuntimeError,'CONTEXT_REQUIRED'):e.read_context(self.proof)
        with patch.dict(os.environ,{'NOX_TRAINING_RECOVERY_CONTEXT':json.dumps(self.context)}):
            self.proof.admission=lambda _:(_ for _ in ()).throw(RuntimeError('HOLD_ADMISSION_CHANGED'))
            with self.assertRaisesRegex(RuntimeError,'ADMISSION_CHANGED'):e.read_context(self.proof)
        self.assertEqual(self.events,[])

    def test_failed_acceptance_rolls_back_only_own_files(self):
        def failed(*args):raise RuntimeError('HOLD_SYNTHETIC_PROBE')
        code,record=self.run_install(failed)
        self.assertEqual(code,2);self.assertTrue(record['rollback_verified'])
        self.assertEqual((self.scripts/'chat_proxy.py').read_bytes(),fixture)
        self.assertEqual((self.scripts/'nox_v137_owner_self_observation.py').read_bytes(),self.observer)
        self.assertFalse((self.root/'config/owner_training_status.json').exists())
        self.assertFalse((self.scripts/'owner_training_status.py').exists())
        self.assertEqual(self.events,['stop-proxy','start-proxy','stop-proxy','start-proxy'])

    def test_foreign_source_change_is_preserved_without_second_proxy_stop(self):
        def failed(*args):
            self.atomic(self.scripts/'chat_proxy.py',b'# foreign change\n')
            raise RuntimeError('HOLD_SYNTHETIC_CONCURRENT_EDIT')
        code,record=self.run_install(failed)
        self.assertEqual(code,2);self.assertFalse(record['rollback_verified'])
        self.assertEqual((self.scripts/'chat_proxy.py').read_bytes(),b'# foreign change\n')
        self.assertEqual(self.events,['stop-proxy','start-proxy']);self.assertEqual(self.proxy_state,'RUNNING')

    def test_busy_chat_wait_does_not_interrupt_chat_or_train(self):
        with patch.object(e,'wait_idle',side_effect=RuntimeError('WAIT_TRAINING_STATUS_INSTALL_OWNER_CHAT_ACTIVE')):
            code,record=self.run_install()
        self.assertEqual(code,2);self.assertEqual(self.events,[])
        self.assertFalse(record['proxy_restarted']);self.assertFalse(record['training_control_performed'])

    def test_current_admission_race_is_detected_before_restart(self):
        count=[0]
        def admission(context):
            count[0]+=1
            if count[0]==3:raise RuntimeError('HOLD_ADMISSION_CHANGED')
            return {},{}
        code,record=self.run_install(admission=admission)
        self.assertEqual(code,2);self.assertEqual(self.events,[])
        self.assertIn('ADMISSION_CHANGED',record['reason'])

    def test_private_child_details_are_not_exported(self):
        child=types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'PRIVATE_SENTINEL')
        with patch.object(e.subprocess,'run',return_value=child):
            with self.assertRaisesRegex(RuntimeError,'PRIVATE_ACCEPTANCE_FAILED') as caught:
                e.live_probe(self.deploy,self.context)
        self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))


class FrozenSourceTests(unittest.TestCase):
    def test_exact_dependencies_and_private_probe_compile(self):
        for name,pin in (('owner_download_status_entry',e.DEPLOY_SHA),('owner_chat_evidence_entry',e.EVIDENCE_ENTRY_SHA),
                         ('owner_training_status',e.STATUS_SHA),('owner_training_status_binding',e.BINDING_SHA)):
            self.assertEqual(e.digest((HERE/(name+'.py')).read_bytes()),pin,name)
        compile(e.HTTP_PROBE,'<native-private-training-status>','exec')
        self.assertNotIn('supervisorctl',Path(e.__file__).read_text())
        self.assertNotIn('optimizer.pt',Path(e.__file__).read_text())


if __name__=='__main__':unittest.main()
