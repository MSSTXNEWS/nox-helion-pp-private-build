"""No GPU needed. Test fail-closed decisions and actual native callback contracts."""
import copy,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from night_v47.policy import assess
from night_v47.native_cycle import stage_native_smoke, OneHostPorts
from control.dispatcher import load_matrix
S='a'*64

def good():
    return {'instance_id':'60509551','native_verified':True,'stop_active':False,
            'chat_gpu0_healthy':True,'s03_native_healthy':True,
            'gpus':[{'index':0,'name':'Tesla V100','compute_capability':'7.0','vram_free_mib':3500},
                    {'index':1,'name':'Tesla V100','compute_capability':'7.0','vram_free_mib':20000,'in_use_for_training':False}],
            'cuda_major':12,'torch_cuda_sm70_verified':True,'precision':'fp16','uses_flashattention2':False,
            'uses_bf16':False,'trainer_step0_root_cause_fixed':True,
            'disk_free_bytes':75_000_000_000,'estimated_new_checkpoint_bytes':20_000_000_000,
            'estimated_temp_bytes':2_000_000_000,'disk_write_estimate_verified':True,
            'ram_available_mib':30000,'offsite_optimizer_restore_verified':True,
            's03_offsite_restore_verified':True,'train_data_license_verified':True,
            'privacy_sanitized':True,'independent_holdout_sealed':True,
            'native_owner_write_scope_verified':True,'trainable_student_sha256':S,
            'checkpoint_sha256':S,'optimizer_sha256':S,'dataset_sha256':S,
            'holdout_sha256':S,'student_format':'HF_SAFETENSORS','no_live_optimizer_process':True,
            'training_owner_lease':True,'chat_state':'idle','chat_recent':False,
            'gpu1_teacher_in_flight':False,'training_mode':'BASE_WEIGHTS',
            'memory_estimate_verified':True,'microbatch':1,'gradient_checkpointing':True,
            'tokenizer_sha256':S,'optimizer_profile_sha256':S,
            'gpu1_model_resident_mib':8500,'gpu1_trainable_grad_mib':500,
            'gpu1_optimizer_state_mib':2000,'gpu1_activation_peak_mib':1100,
            'gpu1_kernel_scratch_mib':500}

class TestNight(unittest.TestCase):
    def test_01_requires_native_inventory(self):self.assertEqual(assess({})['state'],'HOLD')
    def test_02_valid_plan_is_never_execution(self):
        r=assess(good());self.assertEqual(r['state'],'READY_FOR_NATIVE_OWNER_APPROVAL');self.assertFalse(r['performed']);self.assertEqual(r['gpu_index'],1)
    def test_03_no_driver_upgrades(self):self.assertFalse(assess(good())['allow_driver_upgrade'])
    def test_04_reject_cuda13(self):
        d=good();d['cuda_major']=13;self.assertIn('CUDA_12_REQUIRED_FOR_V100',assess(d)['reasons'])
    def test_05_reject_flashattention2(self):
        d=good();d['uses_flashattention2']=True;self.assertIn('VOLTA_UNSUPPORTED_KERNEL_OR_PRECISION',assess(d)['reasons'])
    def test_06_reject_bf16(self):
        d=good();d['precision']='bf16';self.assertIn('V100_FP16_REQUIRED',assess(d)['reasons'])
    def test_07_no_optimizer_without_backup(self):
        d=good();d['offsite_optimizer_restore_verified']=False;self.assertIn('OPTIMIZER_OFFSITE_RESTORE_UNVERIFIED',assess(d)['reasons'])
    def test_08_no_data_without_rights(self):
        d=good();d['train_data_license_verified']=False;self.assertIn('LICENSE_OR_PRIVACY_GATE',assess(d)['reasons'])
    def test_09_disk_reserve(self):
        d=good();d['disk_free_bytes']=19_000_000_000;self.assertIn('CHECKPOINT_SPACE_AND_RESERVE_NOT_PROVEN',assess(d)['reasons'])
    def test_09a_measured_smaller_checkpoint_below_20gb_is_eligible(self):
        d=good();d['disk_free_bytes']=17_475_031_040
        d['estimated_new_checkpoint_bytes']=1_000_000_000
        d['estimated_temp_bytes']=1_000_000_000
        self.assertEqual(assess(d)['state'],'READY_FOR_NATIVE_OWNER_APPROVAL')
    def test_09b_unknown_checkpoint_temp_never_eligible(self):
        d=good();d['estimated_temp_bytes']=None
        self.assertIn('CHECKPOINT_SPACE_AND_RESERVE_NOT_PROVEN',assess(d)['reasons'])
    def test_09c_no_verified_estimate_is_hold(self):
        d=good();d['disk_write_estimate_verified']=False
        self.assertIn('CHECKPOINT_SPACE_AND_RESERVE_NOT_PROVEN',assess(d)['reasons'])
    def test_10_no_gguf_training(self):
        d=good();d['student_format']='GGUF';self.assertIn('TRAINABLE_STUDENT_REQUIRED_GGUF_NOT_TRAINABLE',assess(d)['reasons'])
    def test_11_student_gpu_protected(self):
        d=good();d['chat_gpu0_healthy']=False;self.assertIn('FAST_CHAT_NOT_HEALTHY',assess(d)['reasons'])
    def test_12_stop_guard(self):
        d=good();d['stop_active']=True;self.assertIn('STOP_OR_UNVERIFIED_STOP',assess(d)['reasons'])
    def test_13_gpu1_not_concurrent(self):
        d=good();d['gpus'][1]['in_use_for_training']=True;self.assertIn('GPU1_TRAINER_ALREADY_RUNNING',assess(d)['reasons'])
    def test_14_must_have_real_step0_fix(self):
        d=good();d['trainer_step0_root_cause_fixed']=False;self.assertIn('TRAIN_ERROR_STEP0_NOT_FIXED',assess(d)['reasons'])
    def test_15_bad_sha(self):
        d=good();d['checkpoint_sha256']='not-sha';self.assertIn('SHA_MISSING_CHECKPOINT_SHA256',assess(d)['reasons'])
    def test_15a_real_v100_gpu1_oom_fails_before_trainer(self):
        d=good();d['gpus'][1]['vram_free_mib']=12523
        d['gpu1_model_resident_mib']=11000
        self.assertIn('HOLD_CUDA_OOM_EXPECTED',assess(d)['reasons'])
    def test_15b_active_teacher_cannot_compete_for_gpu1(self):
        d=good();d['gpu1_teacher_in_flight']=True
        self.assertIn('HOLD_TEACHER_ACTIVE_OR_UNKNOWN',assess(d)['reasons'])
    def test_15c_qlora_is_not_no_adapter_base_training(self):
        d=good();d['training_mode']='QLORA'
        self.assertIn('HOLD_BASE_WEIGHT_ONLY_NOT_ADAPTER',assess(d)['reasons'])
    def test_15d_peak_model_snapshot_unverified_is_hold(self):
        d=good();d['memory_estimate_verified']=False
        self.assertIn('HOLD_PEAK_ESTIMATE_UNVERIFIED',assess(d)['reasons'])
    def test_15e_recent_chat_preempts_gpu1_training(self):
        d=good();d['chat_state']='generating'
        self.assertIn('HOLD_CHAT_P0_PREEMPTS_GPU1',assess(d)['reasons'])
    def test_16_fail_no_ports(self):
        self.assertEqual(stage_native_smoke(None,'owner-test')['state'],'HOLD_NATIVE_CALLBACKS')
    def test_17_matrix(self):
        d=load_matrix();self.assertEqual(len(d['tasks']),60)
    def test_18_backup_not_self_gated(self):
        d=load_matrix();rows={t['number']:t for t in d['tasks']};self.assertFalse(rows[9]['requires_backup_restore'])
    def test_19_no_restore_dependency_cycle(self):
        d=load_matrix();rows={t['number']:t for t in d['tasks']};self.assertIn('NOX-V46-56',rows[20]['depends_on']);self.assertNotIn('NOX-V46-20',rows[56]['depends_on'])
    def test_20_staged_smoke_with_true_native_receipt(self):
        state=good();receipt={'checkpoint_staged':True,'active_student_unchanged':True,'stage_id':'stage-1'}
        ports=OneHostPorts(authorize=lambda k:True,stop=lambda:False,observe=lambda:state,
                approve=lambda s,h,pre:True,stage_smoke=lambda p:receipt,verify_stage=lambda x:True,
                readback=lambda k:{'stage_id':k,'checkpoint_staged':True},
                s03_audit=lambda evt:{'stored':True},s03_verify=lambda a,e:a['stored'])
        r=stage_native_smoke(ports,'owner-verified');self.assertEqual(r['state'],'NATIVE_SMOKE_STAGED_VERIFIED');self.assertFalse(r['weights_changed_verified'])
    def test_21_fail_open_native_approval(self):
        ports=OneHostPorts(authorize=lambda k:True,stop=lambda:False,observe=lambda:good(),
                approve=lambda s,h,pre:False,stage_smoke=lambda p:None,verify_stage=lambda x:False,
                readback=lambda k:{},s03_audit=lambda evt:{},s03_verify=lambda a,e:False)
        r=stage_native_smoke(ports,'owner-verified');self.assertEqual(r['state'],'HOLD_NOT_APPROVED')
    def test_22_stage_not_weights(self):
        d=good();self.assertEqual(assess(d)['optimizer_steps_executed'],0)
if __name__=='__main__':unittest.main()

class TestVoltaOomPreflight(unittest.TestCase):
    def test_12gb_free_rejects_9gb_base_weights(self):
        from night_v47.direct_weights_smoke import ensure_gpu1_preload_budget
        with self.assertRaisesRegex(RuntimeError,'MODEL_PRELOAD_OOM_EXPECTED'):
            ensure_gpu1_preload_budget(12*1024**3,9*1024**3)
    def test_20gb_free_accepts_2gb_base(self):
        from night_v47.direct_weights_smoke import ensure_gpu1_preload_budget
        self.assertLess(ensure_gpu1_preload_budget(20*1024**3,2*1024**3),20*1024**3)
    def test_optimizer_memory_is_reserved_after_model_load(self):
        from night_v47.direct_weights_smoke import ensure_gpu1_postload_budget
        with self.assertRaisesRegex(RuntimeError,'OPTIMIZER_ACTIVATION_OOM_EXPECTED'):
            ensure_gpu1_postload_budget(4*1024**3,100_000_000)
    def test_zero_gradient_params_rejected(self):
        from night_v47.direct_weights_smoke import ensure_gpu1_postload_budget
        with self.assertRaisesRegex(RuntimeError,'TRAINABLE_TENSOR_MEASUREMENT'):
            ensure_gpu1_postload_budget(20*1024**3,0)
    def test_reload_drops_optimizer_before_second_model(self):
        import inspect
        from night_v47 import direct_weights_smoke
        src=inspect.getsource(direct_weights_smoke.run)
        self.assertLess(src.index('del optimizer'),src.index('reload_model='))
        self.assertLess(src.index('del params'),src.index('reload_model='))
        self.assertIn('ensure_gpu1_preload_budget(int(available_for_reload)',src)


class TestSmokeReadOnly(unittest.TestCase):
    def test_sample_file_consent_and_split(self):
        import tempfile, json
        from night_v47.direct_weights_smoke import read_samples
        with tempfile.TemporaryDirectory() as p:
            a=Path(p)/'a.jsonl'
            a.write_text('\n'.join(json.dumps({'prompt':'q'+str(i),'completion':'a','source_uri':'s'+str(i),'rights_verified':True,'privacy_approved':True}) for i in range(4)))
            rows,sources=read_samples(a,'TRAIN');self.assertEqual(len(rows),4);self.assertEqual(len(sources),4)
    def test_data_with_no_consent_rejected(self):
        import tempfile,json
        from night_v47.direct_weights_smoke import read_samples
        with tempfile.TemporaryDirectory() as p:
            a=Path(p)/'a.jsonl';a.write_text('\n'.join(json.dumps({'prompt':'x','completion':'y','source_uri':'z'}) for _ in range(4)))
            with self.assertRaisesRegex(RuntimeError,'LICENSE_OR_PRIVACY'):read_samples(a,'TRAIN')
    def test_gguf_is_not_hf(self):
        import tempfile
        from night_v47.direct_weights_smoke import model_manifest_bytes
        with tempfile.TemporaryDirectory() as p:
            Path(p,'config.json').write_text('{}');Path(p,'model.gguf').write_bytes(b'x')
            with self.assertRaisesRegex(RuntimeError,'GGUF_OR_NO_TRAINABLE'):model_manifest_bytes(p)
    def test_smoke_requires_native_authorization(self):
        import argparse
        from night_v47.direct_weights_smoke import run
        with self.assertRaisesRegex(RuntimeError,'ONEHOST_NATIVE_APPROVAL'):
            run(argparse.Namespace(execute=False))
