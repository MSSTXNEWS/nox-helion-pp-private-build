import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


p=load('owner_training_calibration_proof')


class CalibrationFixture(unittest.TestCase):
    def override(self,name,value):
        handle=patch.object(p,name,value);handle.start();self.addCleanup(handle.stop)

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode();path.write_bytes(raw);return p.digest(raw)

    def checkpoint(self,step,start,good,skipped,changed):
        path=self.output/('checkpoint-'+str(step));path.mkdir(exist_ok=True);hashes={}
        for name in p.FILES:
            raw=json.dumps({'global_step':step}).encode() if name=='trainer_state.json' else (str(step)+'-'+name).encode()
            (path/name).write_bytes(raw);hashes[name]=p.digest(raw)
        value={'schema':p.TRAIN_SCHEMA,'native_sha256':p.NATIVE_SHA,'lineage_sha256':p.LINEAGE_SHA,
            'global_step':step,'start_step':start,'successful_optimizer_steps':good,'skipped_optimizer_steps':skipped,
            'loss':1.25,'before_tensor_sha256':p.BASELINE_TENSOR,
            'after_tensor_sha256':'d'*64 if changed else p.BASELINE_TENSOR,'adapter_delta_verified':changed,
            'merged':False,'live_promoted':False,'external_restore_verified':False,
            'checkpoint':{'path':str(path),'global_step':step,'files_sha256':hashes}}
        sha=self.write(self.output/('owner_receipt_step_'+str(step)+'.json'),value)
        return value,sha

    def sealed(self,record):
        sha=self.write(self.state/('owner_maintenance_'+record['request']+'.json'),record)
        return {'request':record['request'],'source_sha':record['source_sha'],'receipt_sha256':sha}

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state';self.scripts=self.root/'scripts';self.output=self.root/'output'
        for path in (self.state,self.scripts,self.output):path.mkdir()
        for name,value in {'ROOT':self.root,'STATE':self.state,'SCRIPTS':self.scripts,'OUTPUT':self.output,
                           'POINTER':self.state/'owner_training_admission.json','NATIVE_SHA':p.digest(b'native-fixture')}.items():self.override(name,value)
        (self.scripts/'train_qlora_35b_t866u.py').write_bytes(b'native-fixture')
        lineage={'schema':p.TRAIN_SCHEMA,'native_sha256':p.NATIVE_SHA,
            'targets':{'trainable_parameters':100,'trainable_dtype':'float32'},'training_config':{'optimizer':'paged_adamw_8bit'}}
        self.write(self.output/'owner_lineage.json',lineage);self.override('LINEAGE_SHA',p.json_sha(lineage));self.lineage=lineage
        baseline,sha=self.checkpoint(5,0,0,5,False);self.override('BASELINE_SHA',sha);self.baseline=baseline
        zero={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'100','source_sha':'a'*40,
              'admission':{'max_steps':5},'optimizer_steps_verified':False}
        self.override('ORIGIN',self.sealed(zero))
        metadata=copy.deepcopy(p.CALIBRATION)
        metadata.update(origin_admission=p.ORIGIN,checkpoint_receipt_sha256=sha,lineage_sha256=p.LINEAGE_SHA)
        self.override('CALIBRATION',metadata)
        self.sources={}
        paths=[self.scripts/'hybrid_training_entry.py',self.scripts/'run_train_volta_t866u.sh',self.state/'train_cpu_max.env']
        paths += [self.scripts/('scope_'+str(i)+'.py') for i in range(17)]
        for path in paths:
            raw=(HERE/'hybrid_training_entry.py').read_bytes() if path.name=='hybrid_training_entry.py' else b'synthetic-source'
            path.write_bytes(raw);self.sources[str(path)]=p.digest(raw)
        self.pointer={'schema':'NOX_OWNER_TRAINING_ADMISSION_V1','request':'200','source_sha':'b'*40,
            'wrapper_request':'200','max_steps':20,'resume':True,'amp_calibration':metadata,'sources':self.sources}
        positive,_=self.checkpoint(20,5,3,12,True)
        self.positive={**positive,'state':'VERIFIED_BOUNDED_ADAPTER_UPDATE','requested_step':20}
        self.write(self.output/'owner_last_result.json',self.positive)
        self.record={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'200','source_sha':'b'*40,
            'state':'VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION','training_started':True,'optimizer_steps_verified':True,
            'continuation_to_1000_started':False,'amp_calibration':metadata,'admission':self.pointer,
            'bounded_update_receipt':self.positive,'bounded_optimizer_proof':p.checkpoint(self.positive)}
        self.context=self.sealed(self.record);self.write(p.POINTER,self.pointer)
        self.write(self.state/'task_boost_mode.json',{'mode':'TASK_BOOST','enabled':True,'training_allowed':True,
                  'training_service':'nox-train-volta-t866u'})

    def continuation(self):
        _,_,_,value,witness=p.calibration_evidence(self.context)
        modules={}
        for name in p.MODULES:
            raw=('# fixture '+name).encode();(self.scripts/(name+'.py')).write_bytes(raw);modules[name]=p.digest(raw)
        wrapper=self.scripts/'run_train_volta_t866u.sh';wrapper.write_bytes(b'fixture-resume-1000')
        pointer={**self.pointer,'request':'300','source_sha':'c'*40,'wrapper_request':'300','max_steps':1000,
            'sources':{**self.sources,str(wrapper):p.digest(wrapper.read_bytes())},'continuation_modules':modules,
            'calibration_evidence':witness}
        pointer.pop('amp_calibration')
        record={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'300','source_sha':'c'*40,'state':p.STATE_STARTED,
            'optimizer_steps_verified':True,'training_started':True,'continuation_target_steps':1000,
            'admission':pointer,'bounded_update_receipt':value,
            'calibration_evidence':witness,'continuation_modules':modules}
        context=self.sealed(record);self.write(p.POINTER,pointer)
        return context,record,pointer


class PositiveProofTests(CalibrationFixture):
    def test_zero_baseline_and_positive_resume_remain_distinct(self):
        record,pointer,lineage,value,witness=p.calibration_evidence(self.context)
        self.assertEqual(witness['baseline_successful_optimizer_steps'],0)
        self.assertEqual(witness['baseline_skipped_optimizer_steps'],5)
        self.assertEqual(witness['positive_checkpoint_global_step'],20)
        self.assertEqual(witness['positive_successful_optimizer_steps'],3)
        self.assertEqual(value['start_step'],5);self.assertNotIn('five_step_receipt',record)
        self.assertFalse(witness['quality_gate_passed'])

    def test_changed_saved_optimizer_is_not_accepted(self):
        (self.output/'checkpoint-20/optimizer.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'CHECKPOINT_HASH'):p.calibration_evidence(self.context)

    def test_all_skipped_or_disconnected_positive_claim_is_rejected(self):
        for update in ({'successful_optimizer_steps':0,'skipped_optimizer_steps':15},
                       {'before_tensor_sha256':'e'*64},{'loss':float('nan')},
                       {'after_tensor_sha256':p.BASELINE_TENSOR,'adapter_delta_verified':False}):
            with self.assertRaises(RuntimeError):p.checkpoint({**self.positive,**update})

    def test_observer_record_must_reference_the_sealed_original_pending_admission(self):
        pending={**self.record,'state':'AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING','optimizer_steps_verified':False}
        pending.pop('bounded_update_receipt');pending.pop('bounded_optimizer_proof')
        pending_context=self.sealed(pending)
        observed={**self.record,'schema':'NOX_OWNER_AMP_CALIBRATION_OBSERVATION_V1','request':'201','source_sha':'e'*40,
                  'observed_admission_context':pending_context}
        context=self.sealed(observed)
        witness=p.calibration_evidence(context)[4]
        self.assertEqual(witness['calibration_admission_context'],pending_context)
        self.assertEqual(witness['calibration_receipt'],context)
        observed['observed_admission_context']={**pending_context,'receipt_sha256':'f'*64}
        with self.assertRaisesRegex(RuntimeError,'SEALED_RECEIPT'):p.calibration_evidence(self.sealed(observed))

    def test_newer_current_pointer_does_not_reauthorize_old_initial_calibration(self):
        context,_,_=self.continuation()
        with self.assertRaisesRegex(RuntimeError,'CURRENT_POINTER'):p.calibration_evidence(self.context)
        _,lineage,value=p.continuation_context(context,rehash=True)
        self.assertEqual(value['global_step'],20);self.assertEqual(value['successful_optimizer_steps'],3)
        self.assertEqual(lineage,self.lineage)

    def test_continuation_only_permits_declared_wrapper_transition_and_pinned_modules(self):
        context,record,pointer=self.continuation();p.continuation_context(context)
        another=str(self.scripts/'scope_0.py');pointer['sources'][another]='0'*64
        record['admission']=pointer;context=self.sealed(record);self.write(p.POINTER,pointer)
        with self.assertRaisesRegex(RuntimeError,'UNDECLARED_TRAINING_SOURCE_CHANGE'):p.continuation_context(context)

    def test_changed_guard_module_cannot_borrow_historical_positive_proof(self):
        context,_,_=self.continuation()
        (self.scripts/'owner_training_calibration_guard.py').write_bytes(b'# foreign module')
        with self.assertRaisesRegex(RuntimeError,'MODULE_CHANGED'):p.continuation_context(context)

    def test_lightweight_guard_revalidates_metadata_without_rehashing_checkpoint_tensors(self):
        context,_,_=self.continuation()
        with patch.object(p,'file_sha',side_effect=AssertionError('guard polling must not hash tensors')):
            p.continuation_context(context,rehash=False)
        raw=(self.output/'owner_receipt_step_5.json').read_bytes()
        (self.output/'owner_receipt_step_5.json').write_bytes(raw+b' ')
        with self.assertRaisesRegex(RuntimeError,'BASELINE_RECEIPT'):p.continuation_context(context,rehash=False)


if __name__=='__main__':unittest.main()
