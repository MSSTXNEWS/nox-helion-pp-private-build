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
            'ram_available_mib':30000,'offsite_optimizer_restore_verified':True,
            's03_offsite_restore_verified':True,'train_data_license_verified':True,
            'privacy_sanitized':True,'independent_holdout_sealed':True,
            'native_owner_write_scope_verified':True,'trainable_student_sha256':S,
            'checkpoint_sha256':S,'optimizer_sha256':S,'dataset_sha256':S,
            'holdout_sha256':S,'student_format':'HF_SAFETENSORS','no_live_optimizer_process':True}

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
