from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch


HERE=Path(__file__).parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


entry=load('owner_training_amp_calibration');recovery=load('owner_training_recovery_entry')
native=load('owner_native_repair')


class CheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state';self.state.mkdir()
        self.output=self.root/'output';self.output.mkdir();self.scripts=self.root/'scripts';self.scripts.mkdir()
        lineage={'schema':entry.TRAIN_SCHEMA,'fixture':'synthetic-no-private-data'}
        (self.output/'owner_lineage.json').write_text(json.dumps(lineage))
        for key,value in {'ROOT':self.root,'STATE':self.state,'SCRIPTS':self.scripts,'OUTPUT':self.output,
                          'POINTER':self.state/'owner_training_admission.json','WRAPPER':self.scripts/'run_train_volta_t866u.sh',
                          'LINEAGE_SHA':entry.json_sha(lineage)}.items():
            handle=patch.object(entry,key,value);handle.start();self.addCleanup(handle.stop)
        self.helper=types.SimpleNamespace(CHECKPOINT_NAMES=native.CHECKPOINT_NAMES)

    def checkpoint(self,step,start,good,skipped,changed):
        path=self.output/('checkpoint-'+str(step));path.mkdir(exist_ok=True)
        hashes={}
        for name in native.CHECKPOINT_NAMES:
            raw=json.dumps({'global_step':step}).encode() if name=='trainer_state.json' else ('fixture-'+name).encode()
            (path/name).write_bytes(raw);hashes[name]=entry.digest(raw)
        return {'schema':entry.TRAIN_SCHEMA,'native_sha256':entry.NATIVE_SHA,'lineage_sha256':entry.LINEAGE_SHA,
            'start_step':start,'global_step':step,'successful_optimizer_steps':good,'skipped_optimizer_steps':skipped,
            'before_tensor_sha256':entry.BASELINE_TENSOR_SHA,
            'after_tensor_sha256':'d'*64 if changed else entry.BASELINE_TENSOR_SHA,
            'adapter_delta_verified':changed,'loss':1.2,'merged':False,'live_promoted':False,
            'checkpoint':{'path':str(path),'global_step':step,'files_sha256':hashes}}

    def test_all_skipped_complete_checkpoint_is_saved_state_not_learning(self):
        value=self.checkpoint(5,0,0,5,False)
        proof=entry.checkpoint_proof(recovery,self.helper,value,baseline=True)
        self.assertEqual(proof['successful_optimizer_steps'],0)
        self.assertFalse(proof['positive_optimizer_updates_verified'])
        self.assertFalse(proof['adapter_delta_verified']);self.assertEqual(proof['checkpoint_file_count'],7)
        with self.assertRaisesRegex(RuntimeError,'NO_POSITIVE_OPTIMIZER_PROOF'):
            entry.checkpoint_proof(recovery,self.helper,value)

    def test_resume_requires_actual_success_and_connected_tensor_hash(self):
        value=self.checkpoint(20,5,3,12,True)
        proof=entry.checkpoint_proof(recovery,self.helper,value)
        self.assertEqual(proof['successful_optimizer_steps'],3)
        self.assertEqual(proof['skipped_optimizer_steps'],12)
        self.assertTrue(proof['positive_optimizer_updates_verified'])
        self.assertFalse(proof['quality_gate_passed'])
        for changed in ({'successful_optimizer_steps':15},{'before_tensor_sha256':'a'*64},
                        {'loss':float('nan')},{'adapter_delta_verified':False}):
            with self.assertRaises(RuntimeError):entry.checkpoint_proof(recovery,self.helper,{**value,**changed})

    def test_changed_optimizer_or_missing_scaler_cannot_be_resumed_as_verified(self):
        value=self.checkpoint(5,0,0,5,False);path=self.output/'checkpoint-5'
        (path/'optimizer.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_HASH'):
            entry.checkpoint_proof(recovery,self.helper,value,baseline=True)
        value=self.checkpoint(5,0,0,5,False);(path/'scaler.pt').unlink()
        with self.assertRaises(FileNotFoundError):entry.checkpoint_proof(recovery,self.helper,value,baseline=True)

    def test_observation_only_accepts_terminal_proof_without_any_start(self):
        value=self.checkpoint(20,5,3,12,True)
        value.update(state='VERIFIED_BOUNDED_ADAPTER_UPDATE',requested_step=20)
        (self.output/'owner_last_result.json').write_text(json.dumps(value))
        context={'request':'456','source_sha':'a'*40,'receipt_sha256':'b'*64}
        pointer={'request':'456','max_steps':20,'resume':True,'sources':{}}
        (self.state/'owner_training_admission.json').write_text(json.dumps(pointer))
        command=Mock(side_effect=AssertionError('observation must never start a process'))
        def atomic(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        helper=types.SimpleNamespace(CHECKPOINT_NAMES=native.CHECKPOINT_NAMES,atomic=atomic,command=command,
            health=lambda:{'8081':200},service_state=lambda:{'state':'STOPPED'},gpu=lambda:{},progress=lambda:{'step':20})
        loaded={'owner_native_repair':helper,'owner_training_resume':object(),
                'owner_training_recovery_entry':recovery,'owner_training_disk_guard':object()}
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'789','NOX_OWNER_SOURCE_SHA':'c'*40}),\
             patch.object(entry,'load',side_effect=lambda name:loaded[name]),\
             patch.object(entry,'policy_admission'),patch.object(entry,'sources_unchanged'),\
             patch.object(entry,'pending_evidence',return_value=({'baseline_saved_state':{'successful_optimizer_steps':0}},pointer,{'pid':123})),\
             redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(context),0)
        result=json.loads((self.state/'owner_maintenance_789.json').read_text())
        self.assertEqual(result['schema'],'NOX_OWNER_AMP_CALIBRATION_OBSERVATION_V1')
        self.assertEqual(result['state'],entry.VERIFIED)
        self.assertEqual(result['admission'],pointer);self.assertFalse(result['training_started'])
        self.assertFalse(result['continuation_to_1000_started']);command.assert_not_called()

    def test_unsealed_pending_context_is_rejected_before_start(self):
        context={'request':'456','source_sha':'a'*40,'receipt_sha256':'b'*64}
        (self.state/'owner_maintenance_456.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'PENDING_RECEIPT'):
            entry.pending_evidence(recovery,self.helper,context)
        with self.assertRaisesRegex(RuntimeError,'CONTEXT'):
            entry.context_value(dict(context,request='../456'))


class SourceContracts(unittest.TestCase):
    def test_bound_changes_only_explicit_step_argument_and_keeps_resume(self):
        before=native.wrapper_source('123',5,True).encode();after=entry.wrapper_source(native,'123')
        self.assertEqual(before.replace(b' --max-steps 5 --planned-steps 1000 --resume\n',
                                       b' --max-steps 20 --planned-steps 1000 --resume\n'),after)
        self.assertNotIn(b'--recover-unstarted',after)
        self.assertIn(b'OWNER_HYBRID_',after);self.assertIn(b'TRAIN_PAUSE_REQUEST.flag',after)

    def test_frozen_training_and_existing_dependency_pins_unchanged(self):
        self.assertEqual(hashlib.sha256((HERE/'hybrid_training_entry.py').read_bytes()).hexdigest(),entry.HYBRID_SHA)
        for name,pin in entry.PINS.items():
            self.assertEqual(hashlib.sha256((HERE/(name+'.py')).read_bytes()).hexdigest(),pin,name)
        self.assertEqual(entry.calibration_metadata()['successful_optimizer_steps_before'],0)
        self.assertEqual(entry.calibration_metadata()['origin_admission'],entry.ORIGIN)


if __name__=='__main__':unittest.main()
