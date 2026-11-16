import copy
from datetime import datetime,timedelta,timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_status',HERE/'owner_training_status.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


class TrainingStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('state','scripts','status','logs','config','lora/qlora_t866u/runs_owner_hybrid'):
            (self.root/name).mkdir(parents=True,exist_ok=True)
        for name,value in (('ROOT',self.root),('NATIVE_SHA',g.digest(b'native fixture')),
                           ('HYBRID_SHAS',frozenset({g.digest(b'hybrid fixture')}))):
            p=patch.object(g,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(g,'live_process',return_value=None);p.start();self.addCleanup(p.stop)
        g._HASH_CACHE.clear()
        (self.root/'scripts/hybrid_training_entry.py').write_bytes(b'hybrid fixture')
        (self.root/'scripts/train_qlora_35b_t866u.py').write_bytes(b'native fixture')
        self.pointer={'schema':'NOX_OWNER_TRAINING_ADMISSION_V1','request':'123','source_sha':'a'*40,
                      'max_steps':5,'resume':False,'sources':{
                          str(self.root/'scripts/hybrid_training_entry.py'):g.digest(b'hybrid fixture')}}
        self.sealed={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'123','source_sha':'a'*40,
                     'state':'BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING','started':time.time()-30,
                     'optimizer_steps_verified':False,'admission':self.pointer}
        self.lineage={'schema':g.TRAIN_SCHEMA,'native_sha256':g.NATIVE_SHA,'training_config':{'optimizer':'paged_adamw_8bit'}}
        self.write(g.output()/'owner_lineage.json',self.lineage)
        self.context=self.seal()

    def write(self,path,value):
        raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw);return raw

    def seal(self):
        self.write(self.root/'state/owner_training_admission.json',self.pointer)
        raw=self.write(self.root/'state/owner_maintenance_123.json',self.sealed)
        return {'request':'123','source_sha':'a'*40,'receipt_sha256':g.digest(raw)}

    def checkpoint(self,step=5,start=0,good=3,skipped=2,before='1'*64,after='2'*64):
        directory=g.output()/('checkpoint-'+str(step));directory.mkdir(exist_ok=True)
        hashes={}
        for name in g.FILES:
            raw=json.dumps({'global_step':step}).encode() if name=='trainer_state.json' else ('synthetic-'+name).encode()
            (directory/name).write_bytes(raw);hashes[name]=g.digest(raw)
        value={'schema':g.TRAIN_SCHEMA,'native_sha256':g.NATIVE_SHA,'lineage_sha256':g.json_sha(self.lineage),
               'global_step':step,'start_step':start,'successful_optimizer_steps':good,'skipped_optimizer_steps':skipped,
               'loss':1.25,'before_tensor_sha256':before,'after_tensor_sha256':after,'adapter_delta_verified':good>0,
               'checkpoint':{'path':str(directory),'global_step':step,'files_sha256':hashes},
               'merged':False,'live_promoted':False}
        self.write(g.output()/('owner_receipt_step_'+str(step)+'.json'),value)
        return value

    def test_amp_skips_do_not_become_successful_optimizer_updates(self):
        self.checkpoint();value=g.snapshot(self.context)
        self.assertTrue(value['positive_optimizer_steps_verified'])
        self.assertEqual(value['global_step'],5);self.assertEqual(value['optimizer_steps'],3)
        self.assertEqual(value['verified_counter_chain']['skipped_optimizer_steps'],2)
        self.assertEqual(value['current_model_merge_inclusion'],'NOT_VERIFIED')

    def test_all_skipped_checkpoint_verifies_saved_state_without_claiming_learning(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        value=g.snapshot(self.context)
        self.assertTrue(value['checkpoint_saved_verified'])
        self.assertEqual(value['global_step'],5);self.assertEqual(value['optimizer_steps'],0)
        self.assertEqual(value['skipped_optimizer_steps'],5)
        self.assertFalse(value['positive_optimizer_steps_verified'])
        self.assertFalse(value['latest_verified_checkpoint']['adapter_delta_verified'])
        self.assertEqual(value['verification_state'],'VERIFIED_SAVED_CHECKPOINT_WITHOUT_OPTIMIZER_UPDATE')
        self.assertEqual(value['latest_verified_checkpoint']['checkpoint_file_count'],7)

    def test_hash_verified_hf_grad_norm_nan_does_not_hide_saved_zero_update_state(self):
        row=self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        raw=b'{"global_step":5,"log_history":[{"step":1,"grad_norm":NaN,"private_note":"PRIVATE_HISTORY_SENTINEL"}]}'
        path=g.output()/'checkpoint-5/trainer_state.json';path.write_bytes(raw)
        row['checkpoint']['files_sha256']['trainer_state.json']=g.digest(raw)
        self.write(g.output()/'owner_receipt_step_5.json',row)
        (self.root/'state/TRAIN_HOLD.flag').write_text('OWNER_HYBRID_FAILED request=123\n')
        value=g.snapshot(self.context)
        self.assertEqual(value['state'],'HELD_AFTER_FAILURE')
        self.assertEqual(value['global_step'],5);self.assertEqual(value['optimizer_steps'],0)
        self.assertEqual(value['skipped_optimizer_steps'],5)
        self.assertTrue(value['checkpoint_saved_verified']);self.assertFalse(value['positive_optimizer_steps_verified'])
        metadata=value['latest_verified_checkpoint']['trainer_state_metadata']
        self.assertEqual(metadata['nonfinite_grad_norm_diagnostics'],1)
        self.assertEqual(metadata['raw_sha256'],g.digest(raw))
        self.assertFalse(metadata['metadata_used_as_optimizer_evidence'])
        self.assertNotIn('PRIVATE_HISTORY_SENTINEL',json.dumps(value,allow_nan=False))
        self.assertEqual(path.read_bytes(),raw)
        path.write_bytes(raw+b' ')
        self.assertEqual(g.snapshot(self.context)['reason'],'HOLD_TRAINING_STATUS_CHECKPOINT_HASH')

    def test_trainer_metadata_exceptions_are_narrow_and_hash_bound(self):
        raw=b'{"global_step":5,"log_history":[{"grad_norm":NaN},{"grad_norm":Infinity},{"grad_norm":-Infinity},{"grad_norm":1e999}]}'
        value=g.trainer_state_projection(raw,5,g.digest(raw))
        self.assertEqual(value['nonfinite_grad_norm_diagnostics'],4)
        with self.assertRaisesRegex(g.StatusHold,'TRAINER_STATE_HASH'):
            g.trainer_state_projection(raw,5,'f'*64)
        for bad in (b'{"global_step":NaN}',b'{"global_step":true}',b'{"global_step":5.0}',
                    b'{"global_step":5,"log_history":[{"loss":NaN}]}',
                    b'{"global_step":5,"log_history":[{"grad_norm":{"nested":NaN}}]}',
                    b'{"global_step":5,"other":NaN}',
                    b'{"global_step":5,"log_history":[{"grad_norm":NaN,"grad_norm":1}]}'):
            with self.assertRaises(g.StatusHold):
                g.trainer_state_projection(bad,5,g.digest(bad))

    def test_receipt_and_lineage_nonfinite_json_remains_rejected(self):
        for path in (g.output()/'owner_receipt_step_5.json',g.output()/'owner_lineage.json'):
            path.write_bytes(b'{"global_step":5,"log_history":[{"grad_norm":NaN}]}')
            with self.assertRaisesRegex(g.StatusHold,'NONFINITE_JSON'):
                g.document(path)

    def test_trainer_metadata_depth_is_bounded_before_projection(self):
        raw=b'{"global_step":5,"metadata":'+b'['*34+b'0'+b']'*34+b'}'
        with self.assertRaisesRegex(g.StatusHold,'TRAINER_METADATA_BUDGET'):
            g.trainer_state_projection(raw,5,g.digest(raw))

    def test_zero_update_claim_cannot_hide_changed_weights_or_bad_counters(self):
        value=self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        for change in ({'after_tensor_sha256':'2'*64},{'adapter_delta_verified':True},
                       {'successful_optimizer_steps':1},{'skipped_optimizer_steps':4}):
            with self.assertRaisesRegex(g.StatusHold,'COUNTERS_OR_DELTA'):
                g.checkpoint_metadata({**value,**change})

    def test_zero_update_baseline_supports_positive_resume_chain(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        self.checkpoint(step=8,start=5,good=2,skipped=1,before='1'*64,after='3'*64)
        value=g.snapshot(self.context)
        self.assertTrue(value['positive_optimizer_steps_verified'])
        self.assertEqual(value['global_step'],8);self.assertEqual(value['optimizer_steps'],2)
        self.assertEqual(value['skipped_optimizer_steps'],6)
        self.assertEqual(value['verified_counter_chain']['verified_run_segments'],2)

    def test_two_all_skipped_segments_stay_zero_updates(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        self.checkpoint(step=8,start=5,good=0,skipped=3,before='1'*64,after='1'*64)
        value=g.snapshot(self.context)
        self.assertTrue(value['checkpoint_saved_verified']);self.assertFalse(value['positive_optimizer_steps_verified'])
        self.assertEqual(value['optimizer_steps'],0);self.assertEqual(value['skipped_optimizer_steps'],8)

    def test_corrupt_zero_update_checkpoint_cannot_claim_saved_state(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        (g.output()/'checkpoint-5/scaler.pt').write_bytes(b'changed scaler')
        value=g.snapshot(self.context)
        self.assertFalse(value['checkpoint_saved_verified']);self.assertFalse(value['positive_optimizer_steps_verified'])
        self.assertIsNone(value['optimizer_steps']);self.assertIsNone(value['global_step'])
        self.assertEqual(value['reason'],'HOLD_TRAINING_STATUS_CHECKPOINT_HASH')

    def calibration(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        origin={'schema':'ORIGIN_FIXTURE'}
        origin_raw=self.write(self.root/'state/owner_maintenance_6905764817.json',origin)
        calibration=copy.deepcopy(g.AMP_CALIBRATION)
        calibration['origin_admission']['receipt_sha256']=g.digest(origin_raw)
        calibration['checkpoint_receipt_sha256']=g.digest((g.output()/'owner_receipt_step_5.json').read_bytes())
        calibration['lineage_sha256']=g.json_sha(self.lineage)
        calibration['hybrid_sha256']=g.digest(b'hybrid fixture')
        self.pointer.update(max_steps=20,resume=True,amp_calibration=calibration)
        self.sealed.update(state='AMP_CALIBRATION_RUNNING_ACCEPTANCE_PENDING',amp_calibration=calibration)
        self.context=self.seal()
        return calibration

    def test_calibration20_requires_exact_scope_and_sealed_zero_baseline(self):
        calibration=self.calibration()
        with patch.object(g,'AMP_CALIBRATION',copy.deepcopy(calibration)):
            value=g.snapshot(self.context)
            self.assertEqual(value['optimizer_steps'],0);self.assertEqual(value['global_step'],5)
            self.assertFalse(value['positive_optimizer_steps_verified'])
            self.pointer['amp_calibration']['optimizer_state_preserved']=1
            self.context=self.seal()
            bad=g.snapshot(self.context)
            self.assertEqual(bad['reason'],'HOLD_TRAINING_STATUS_CALIBRATION_SCOPE')

    def test_calibration20_rejects_missing_scope_and_replaced_baseline(self):
        calibration=self.calibration()
        with patch.object(g,'AMP_CALIBRATION',copy.deepcopy(calibration)):
            original=(g.output()/'owner_receipt_step_5.json').read_bytes()
            (g.output()/'owner_receipt_step_5.json').write_bytes(original+b' ')
            self.assertEqual(g.snapshot(self.context)['reason'],'HOLD_TRAINING_STATUS_CALIBRATION_BASELINE')
            (g.output()/'owner_receipt_step_5.json').write_bytes(original)
            del self.pointer['amp_calibration'];self.context=self.seal()
            self.assertEqual(g.snapshot(self.context)['reason'],'HOLD_TRAINING_STATUS_CALIBRATION_SCOPE')

    def test_calibration20_live_loading_keeps_zero_baseline_separate(self):
        calibration=self.calibration()
        process={'pid':91,'start_ticks':110,'started_at':time.time()-1,'target_global_step':20,'resume_argument':True}
        self.write(self.root/'status/train_volta_t866u.json',{'program':g.SERVICE,'output':str(g.output()),
            'phase':'loading_owner_hybrid','step':5,'max_steps':20,'ts':time.time()})
        with patch.object(g,'AMP_CALIBRATION',copy.deepcopy(calibration)),patch.object(g,'live_process',return_value=process):
            value=g.snapshot(self.context)
        self.assertEqual(value['state'],'LOADING');self.assertEqual(value['optimizer_steps'],0)
        self.assertEqual(value['current_run']['process']['target_global_step'],20)
        self.assertFalse(value['positive_optimizer_steps_verified']);self.assertFalse(value['checkpoint_restore_verified'])

    def test_generic_calibration_receipt_counts_only_new_verified_updates(self):
        calibration=self.calibration()
        update=self.checkpoint(step=20,start=5,good=3,skipped=12,before='1'*64,after='3'*64)
        self.sealed.update(state='VERIFIED_POSITIVE_OPTIMIZER_CALIBRATION',optimizer_steps_verified=True,
                           bounded_update_receipt=update)
        self.context=self.seal()
        with patch.object(g,'AMP_CALIBRATION',copy.deepcopy(calibration)):
            value=g.snapshot(self.context)
        self.assertEqual(value['historical_verified_checkpoint']['start_step'],5)
        self.assertEqual(value['global_step'],20);self.assertEqual(value['optimizer_steps'],3)
        self.assertEqual(value['skipped_optimizer_steps'],17)
        self.assertTrue(value['positive_optimizer_steps_verified'])
        self.assertFalse(value['checkpoint_restore_verified'])

    def test_owned_failure_and_saved_zero_update_checkpoint_are_both_reported(self):
        self.checkpoint(good=0,skipped=5,before='1'*64,after='1'*64)
        self.sealed.update(error='HOLD_NO_FINITE_VERIFIED_OPTIMIZER_DELTA');self.context=self.seal()
        (self.root/'state/TRAIN_HOLD.flag').write_text('OWNER_HYBRID_FAILED request=123\n')
        value=g.snapshot(self.context)
        self.assertEqual(value['state'],'HELD_AFTER_FAILURE')
        self.assertEqual(value['failure_cause'],'HOLD_NO_FINITE_VERIFIED_OPTIMIZER_DELTA')
        self.assertEqual(value['global_step'],5);self.assertEqual(value['optimizer_steps'],0)
        self.assertTrue(value['checkpoint_saved_verified']);self.assertFalse(value['positive_optimizer_steps_verified'])

    def test_resume_counters_reset_and_tensor_connected_segments_add_once(self):
        self.checkpoint()
        self.checkpoint(step=7,start=5,good=1,skipped=1,before='2'*64,after='3'*64)
        value=g.snapshot(self.context)
        self.assertEqual(value['global_step'],7);self.assertEqual(value['optimizer_steps'],4)
        self.assertEqual(value['verified_counter_chain']['skipped_optimizer_steps'],3)
        self.assertEqual(value['verified_counter_chain']['verified_run_segments'],2)

    def test_disconnected_resume_never_gets_a_cumulative_count(self):
        self.checkpoint()
        self.checkpoint(step=7,start=5,good=1,skipped=1,before='9'*64,after='3'*64)
        value=g.snapshot(self.context)
        self.assertTrue(value['positive_optimizer_steps_verified'])
        self.assertIsNone(value['optimizer_steps'])
        self.assertEqual(value['counter_chain_state'],'CUMULATIVE_COUNT_UNVERIFIED')

    def test_stat_cache_avoids_second_large_read_and_detects_same_size_mutation(self):
        self.checkpoint();first=g.snapshot(self.context);second=g.snapshot(self.context)
        self.assertGreater(first['checkpoint_bytes_hashed'],0)
        self.assertEqual(second['checkpoint_bytes_hashed'],0)
        path=g.output()/'checkpoint-5/adapter_model.safetensors';before=path.stat()
        path.write_bytes(b'x'*before.st_size);os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        changed=g.snapshot(self.context)
        self.assertFalse(changed['positive_optimizer_steps_verified'])
        self.assertEqual(changed['reason'],'HOLD_TRAINING_STATUS_CHECKPOINT_HASH')

    def test_first_five_history_remains_distinct_from_current_loading(self):
        first=self.checkpoint();self.sealed.update(state='FIVE_STEPS_VERIFIED_CONTINUATION_STARTED',
            optimizer_steps_verified=True,five_step_receipt=first)
        self.pointer.update(max_steps=1000,resume=True);self.context=self.seal()
        process={'pid':91,'start_ticks':110,'started_at':time.time()-1,'target_global_step':1000,'resume_argument':True}
        self.write(self.root/'status/train_volta_t866u.json',{'program':g.SERVICE,'output':str(g.output()),
            'phase':'loading_owner_hybrid','step':5,'max_steps':1000,'ts':time.time()})
        with patch.object(g,'live_process',return_value=process):value=g.snapshot(self.context)
        self.assertEqual(value['state'],'LOADING');self.assertEqual(value['optimizer_steps'],3)
        self.assertIsNone(value['current_run']['telemetry']['successful_optimizer_steps'])
        self.assertFalse(value['checkpoint_restore_verified'])

    def test_heartbeat_without_saved_proof_cannot_claim_verified_learning(self):
        process={'pid':91,'start_ticks':110,'started_at':time.time()-1,'target_global_step':5,'resume_argument':False}
        self.write(self.root/'status/train_volta_t866u.json',{'program':g.SERVICE,'output':str(g.output()),
            'phase':'train_owner_hybrid','step':2,'max_steps':5,'ts':time.time(),
            'successful_optimizer_steps':1,'skipped_optimizer_steps':1})
        with patch.object(g,'live_process',return_value=process):value=g.snapshot(self.context)
        self.assertEqual(value['state'],'RUNNING');self.assertFalse(value['positive_optimizer_steps_verified'])
        self.assertIsNone(value['optimizer_steps']);self.assertEqual(value['current_run']['telemetry']['global_step'],2)

    def test_prior_process_heartbeat_is_not_current_progress(self):
        process={'pid':91,'start_ticks':110,'started_at':time.time(),'target_global_step':5,'resume_argument':False}
        self.write(self.root/'status/train_volta_t866u.json',{'program':g.SERVICE,'output':str(g.output()),
            'phase':'train_owner_hybrid','step':5,'max_steps':5,'ts':time.time()-20,
            'successful_optimizer_steps':5,'skipped_optimizer_steps':0})
        with patch.object(g,'live_process',return_value=process):value=g.snapshot(self.context)
        self.assertEqual(value['state'],'RUNNING_TELEMETRY_UNVERIFIED')
        self.assertIsNone(value['current_run']['telemetry'])

    def test_actual_owned_failure_cause_is_categorical_and_private_lines_stay_private(self):
        self.sealed.update(state='HOLD_TRAINING_RESUME',error='HOLD_TRAINER_EXITED_WITHOUT_OPTIMIZER_PROOF')
        self.context=self.seal()
        (self.root/'state/TRAIN_HOLD.flag').write_text('OWNER_HYBRID_FAILED request=123\n')
        stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M:%S Europe/Moscow (UTC+3)')
        (self.root/'logs/train_volta_t866u.supervisor.log').write_text(
            '['+stamp+'] trainer constructor\nprivate training example or secret\nNOX_HYBRID_FAILURE=HOLD_NATIVE_TRAINER_CONFIG_NOT_APPLIED\n')
        value=g.snapshot(self.context)
        self.assertEqual(value['state'],'HELD_AFTER_FAILURE')
        self.assertEqual(value['failure_cause'],'HOLD_NATIVE_TRAINER_CONFIG_NOT_APPLIED')
        self.assertNotIn('private training example',json.dumps(value));self.assertIsNone(value['optimizer_steps'])

    def test_jsonl_and_missing_file_failure_identifiers_survive_without_raw_exception_text(self):
        self.sealed.update(state='HOLD_TRAINING_CONFIG_RECOVERY',error='HOLD_RECOVERY_TRAINER_EXITED_WITHOUT_PROOF')
        self.context=self.seal()
        (self.root/'state/TRAIN_HOLD.flag').write_text('OWNER_HYBRID_FAILED request=123\n')
        stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M:%S Europe/Moscow (UTC+3)')
        for code in ('JSONDecodeError','FileNotFoundError'):
            (self.root/'logs/train_volta_t866u.supervisor.log').write_text(
                '['+stamp+'] native training\nprivate corpus text\nNOX_HYBRID_FAILURE='+code+'\n')
            self.assertEqual(g.snapshot(self.context)['failure_cause'],code)
        (self.root/'logs/train_volta_t866u.supervisor.log').write_text(
            '['+stamp+'] native training\nNOX_HYBRID_FAILURE=JSONDecodeError: private corpus text\n')
        value=g.snapshot(self.context)
        self.assertEqual(value['failure_cause'],'HOLD_RECOVERY_TRAINER_EXITED_WITHOUT_PROOF')
        self.assertNotIn('private corpus text',json.dumps(value))

    def test_global_step_alone_or_inconsistent_skip_count_is_rejected(self):
        value=self.checkpoint();value['successful_optimizer_steps']=5
        with self.assertRaisesRegex(g.StatusHold,'COUNTERS'):g.checkpoint_metadata(value)
        del value['successful_optimizer_steps']
        with self.assertRaisesRegex(g.StatusHold,'COUNTERS'):g.checkpoint_metadata(value)

    def test_receipt_pin_and_current_lineage_are_required(self):
        self.sealed['extra']='changed';self.seal()
        self.assertEqual(g.snapshot(self.context)['state'],'UNVERIFIED_ADMISSION')
        first=self.checkpoint();self.sealed.update(optimizer_steps_verified=True,five_step_receipt=first)
        self.context=self.seal();self.lineage['different_base']=True
        self.write(g.output()/'owner_lineage.json',self.lineage)
        value=g.snapshot(self.context)
        self.assertEqual(value['reason'],'HOLD_TRAINING_STATUS_ACCEPTED_LINEAGE_CHANGED')
        self.assertIsNone(value['latest_verified_checkpoint'])

    def test_fifo_symlink_and_duplicate_json_rejected(self):
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaisesRegex(g.StatusHold,'FILE'):g.read(fifo)
        link=self.root/'link';link.symlink_to(fifo)
        with self.assertRaisesRegex(g.StatusHold,'PATH'):g.read(link)
        path=self.root/'duplicate.json';path.write_text('{"step":1,"step":2}')
        with self.assertRaisesRegex(g.StatusHold,'DUPLICATE_JSON'):g.document(path)

    def test_binding_replaces_hardcoded_values_and_ignores_caller_training_claims(self):
        self.checkpoint()
        ns={'snapshot':lambda:{'training':{'supervisor_services':[],'positive_optimizer_steps_verified':False}},
            'evidence_for_model':lambda observation,memory:{'state':'NATIVE_SERVICE_OBSERVATION','training':{'optimizer_steps':None}}}
        g.bind_self_observation(ns,self.context)
        value=ns['snapshot']();self.assertTrue(value['training']['positive_optimizer_steps_verified'])
        fake={'training':{'optimizer_steps':100000,'private':'untrusted'}}
        model=ns['evidence_for_model'](fake,[])
        self.assertEqual(model['training']['optimizer_steps'],3)
        self.assertNotIn('untrusted',json.dumps(model))


if __name__=='__main__':unittest.main()
