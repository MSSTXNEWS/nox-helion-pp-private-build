"""Owned unstarted recovery gates; no native services or GPU are touched."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location('recovery_test_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module
entry=load('owner_training_recovery_entry');repair=load('owner_native_repair');resume=load('owner_training_resume')


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.state=self.root/'state';self.state.mkdir()
        self.output=self.root/'output';self.output.mkdir()
        self.wrapper=self.root/'scripts/run_train_volta_t866u.sh';self.wrapper.parent.mkdir()
        self.hybrid=self.root/'scripts/hybrid_training_entry.py'
        for name,value in [('ROOT',self.root),('STATE',self.state),('OUTPUT',self.output),
                           ('WRAPPER',self.wrapper),('ENTRY',self.hybrid),('POINTER',self.state/'owner_training_admission.json')]:
            patcher=patch.object(entry,name,value);patcher.start();self.addCleanup(patcher.stop)

    def preparation(self):
        data=b'{"text":"synthetic only"}\n';(self.output/'training_text.jsonl').write_bytes(data)
        record={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','native_sha256':resume.NATIVE_SHA,
                'planned_steps':1000,'dataset_sha256':entry.digest(data)}
        raw=json.dumps(record).encode();(self.output/'owner_preparation.json').write_bytes(raw)
        for name,value in [('PREPARATION_SHA',entry.digest(raw)),('DATASET_BYTES',len(data))]:
            patcher=patch.object(entry,name,value);patcher.start();self.addCleanup(patcher.stop)
        return data

    def test_reuses_exact_corpus_and_rejects_any_optimizer_or_unknown_artifact(self):
        before=self.preparation();proof=entry.unstarted_output()
        self.assertTrue(proof['dataset_reused']);self.assertEqual(proof['optimizer_updates_before_recovery'],0)
        self.assertEqual((self.output/'training_text.jsonl').read_bytes(),before)
        for name in ('checkpoint-1','optimizer.pt','owner_lineage.json','unknown.txt'):
            path=self.output/name;path.write_bytes(b'unverified')
            with self.subTest(name=name),self.assertRaisesRegex(RuntimeError,'HAS_CHECKPOINT_OR_UNKNOWN_ARTIFACT'):
                entry.unstarted_output()
            path.unlink()

    def test_prepared_text_mutation_is_rejected_even_when_size_is_unchanged(self):
        data=self.preparation();(self.output/'training_text.jsonl').write_bytes(b'x'*len(data))
        with self.assertRaisesRegex(RuntimeError,'PREPARED_DATASET_CHANGED'):entry.unstarted_output()

    def test_fifo_and_symlink_are_rejected_without_blocking(self):
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaisesRegex(RuntimeError,'FILE_SCOPE'):entry.read(fifo)
        link=self.root/'link';link.symlink_to(fifo)
        with self.assertRaisesRegex(RuntimeError,'SYMLINK'):entry.read(link)

    def test_exact_reviewed_sources_and_first_five_only_recovery_flag(self):
        for name,pin in [('owner_native_repair.py',entry.HELPER_SHA),('owner_training_resume.py',entry.RESUME_SHA),
                         ('owner_training_config_preflight.py',entry.PREFLIGHT_SHA),
                         ('owner_training_disk_guard.py',entry.DISK_GUARD_SHA),('hybrid_training_entry.py',entry.HYBRID_AFTER)]:
            self.assertEqual(entry.digest((HERE/name).read_bytes()),pin,name)
        wrapper=entry.recovery_wrapper(repair,'123456').decode()
        self.assertEqual(wrapper.count('--recover-unstarted'),1)
        self.assertIn('--max-steps 5 --planned-steps 1000 --recover-unstarted\n',wrapper)
        continued=repair.wrapper_source('123456',1000,True)
        self.assertNotIn('--recover-unstarted',continued);self.assertIn('--resume',continued)

    def test_source_set_is_reconstructed_from_previous_backups(self):
        control=self.root/'scripts/nox_dispatcher_t855u.py';original=repair.OWNER_GUARD.encode()
        after=resume.patch_permission(original.decode()).encode();control.write_bytes(after)
        old_hybrid=b'fixture old hybrid';self.hybrid.write_bytes(old_hybrid)
        self.wrapper.write_text(repair.wrapper_source(entry.FAILED_REQUEST))
        original_pins={control:entry.digest(original),self.hybrid:entry.digest(old_hybrid),self.wrapper:'0'*64}
        expected={control:entry.digest(after),self.hybrid:entry.digest(old_hybrid),self.wrapper:entry.digest(self.wrapper.read_bytes())}
        backup=self.root/'backup/owner_training_resume'/entry.FAILED_REQUEST/str(control).lstrip('/')
        backup.parent.mkdir(parents=True);backup.write_bytes(original)
        chains={'dispatcher_upgrade':{'request':'upgrade'},'s03_activation':{'request':'memory'},'media_acceptance':{'request':'media'}}
        pointer={'request':entry.FAILED_REQUEST,'source_sha':entry.FAILED_SOURCE,'max_steps':5,'resume':False,
                 'sources':{str(p):v for p,v in expected.items()},**chains}
        record={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':entry.FAILED_REQUEST,'source_sha':entry.FAILED_SOURCE,
                'state':'HOLD_TRAINING_RESUME','error':'HOLD_TRAINER_EXITED_WITHOUT_OPTIMIZER_PROOF',
                'optimizer_steps_verified':False,'admission':pointer,**chains}
        (self.state/('owner_maintenance_'+entry.FAILED_REQUEST+'.json')).write_text(json.dumps(record))
        entry.POINTER.write_text(json.dumps(pointer))
        review=types.SimpleNamespace(CONTROLS={control:'unused'},BOOST_REQUEST='boost',
            read_json=lambda path:{},boost_pins=lambda receipt:dict(original_pins),
            dispatcher_upgrade_evidence=lambda:({},chains['dispatcher_upgrade']),
            s03_activation_evidence=lambda chain:({},chains['s03_activation']),
            media_acceptance_evidence=lambda chain,rehash_outputs:chains['media_acceptance'],
            patch_permission=resume.patch_permission)
        with patch.object(entry,'HYBRID_BEFORE',entry.digest(old_hybrid)):
            self.assertEqual(entry.failed_admission(repair,review)[0],expected)
            control.write_bytes(after+b'\n# unexpected change\n')
            with self.assertRaisesRegex(RuntimeError,'CURRENT_SOURCE_CHANGED'):entry.failed_admission(repair,review)

    def test_constructor_failure_keeps_owned_hold_sources_and_corpus(self):
        corpus=self.preparation();hold=('OWNER_HYBRID_FAILED request='+entry.FAILED_REQUEST+'\n').encode()
        (self.state/'TRAIN_HOLD.flag').write_bytes(hold);self.hybrid.write_bytes(b'old');self.wrapper.write_bytes(b'old wrapper')
        (self.root/'scripts/train_qlora_35b_t866u.py').write_bytes(b'fixture native')
        (self.state/'task_boost_mode.json').write_text(json.dumps({'training_allowed':True,'training_service':entry.SERVICE}))
        def atomic(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        commands=Mock()
        helper=types.SimpleNamespace(atomic=atomic,health=lambda:{'8080':200,'8081':200,'8082':200},HEAVY_SERVICES=[],
            service_state=lambda name=None:{'state':'FATAL'},program_config=lambda name:{'command':'/bin/bash '+str(self.wrapper)},
            command=commands,gpu=lambda:{'gpus':[]},progress=lambda:{'phase':'loading_owner_hybrid','step':0})
        review=types.SimpleNamespace(BOOST_REQUEST='boost',worker_readback=lambda helper:{'workers':6},
            verify_policy=lambda value:None,resource_admission=lambda helper:{'admitted':True},STOPPED=resume.STOPPED)
        preflight=types.SimpleNamespace(run_preflight=Mock(side_effect=RuntimeError('HOLD_CONFIG_PREFLIGHT_ARGUMENT_MISMATCH')))
        modules={'owner_native_repair':helper,'owner_training_resume':review,
                 'owner_training_config_preflight':preflight,'owner_training_disk_guard':types.SimpleNamespace()}
        previous=({}, {}, {'request':entry.FAILED_REQUEST}, {}, {}, {})
        with patch.object(entry,'load',side_effect=lambda name,pin:(modules[name],b'')), \
             patch.object(entry,'failed_admission',return_value=previous),patch.object(entry,'emit'), \
             patch.object(entry,'BUNDLE',{'hybrid_training_entry.py':base64.b64encode((HERE/'hybrid_training_entry.py').read_bytes()).decode()}), \
             patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123456','NOX_OWNER_SOURCE_SHA':'a'*40},clear=True):
            self.assertEqual(entry.main(),2)
        commands.assert_not_called();preflight.run_preflight.assert_called_once()
        self.assertEqual((self.state/'TRAIN_HOLD.flag').read_bytes(),hold)
        self.assertEqual(self.hybrid.read_bytes(),b'old');self.assertEqual(self.wrapper.read_bytes(),b'old wrapper')
        self.assertEqual((self.output/'training_text.jsonl').read_bytes(),corpus)
        record=json.loads((self.state/'owner_maintenance_123456.json').read_text())
        self.assertEqual(record['state'],'HOLD_TRAINING_CONFIG_RECOVERY')
        self.assertFalse(record['training_started']);self.assertFalse(record['optimizer_steps_verified'])


if __name__=='__main__':unittest.main()
