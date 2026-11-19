"""NOX V135: isolated source tests, no GPU/server access or teacher model fake-pass."""
from __future__ import annotations
import hashlib,hmac,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from nox_runpod.teacher_mesh.v135 import zero3_fullbase_plan as policy
from nox_runpod.teacher_mesh.v135 import curate_teacher_distillation as teacher
from nox_runpod.teacher_mesh.v135 import train_full_base_zero3 as training

def fixture_native()->dict:
    checks=('native_signed_owner_receipt','instance_id_verified',
      'model_shards_complete_sha_verified','onehost_original_main_chat_healthy',
      's03_integrity_verified','owner_approved_training','no_shared_gpu_scheduler',
      'live_gpu1_lease','teacher_dataset_rights_verified','teacher_dataset_privacy_verified',
      'disjoint_holdout_verified','offsite_owner_checkpoint_restore_verified',
      'offsite_s03_restore_verified','external_checkpoint_storage_prepared',
      'fp16_sm70_deepspeed_abi_verified','existing_student_identity_sha_verified',
      'zero3_checkpoint_reload_tested','optimizer_is_full_base_no_peft',
      'teacher_slots_not_colocated_with_gpu1','gpu1_automatic_85pct_overcommit_disabled')
    out={k:True for k in checks}
    out.update({
      'native_stop_active':False,'existing_chat_priority':'P0',
      'student_checkpoint_format':'HF_SAFETENSORS',
      'gpu0_role':'CHAT_ONLY','gpu1_role':'TRAINING_EXCLUSIVE',
      'gpu1_name':'Tesla V100','precision':'fp16',
      'cpu_cgroup_max_bytes':128*policy.GIB,
      'cpu_cgroup_current_bytes':20*policy.GIB,
      'cpu_mem_available_bytes':100*policy.GIB,
      'gpu0_free_mib':8192,'gpu1_free_mib':20000,'gpu1_measured_peak_mib':15000,
      'checkpoint_required_new_bytes':20*policy.GIB,
      'disk_free_bytes':100*policy.GIB,
      'student_param_count':1_000_000_000,
      'student_shard_bytes':2_000_000_000,
      'train_rows':400,'holdout_rows':55,
      'hf_weight_index_sha256':'a'*64,'student_base_sha256':'b'*64,
      'train_dataset_sha256':'c'*64,'holdout_dataset_sha256':'d'*64,
      'offsite_checkpoint_manifest_sha256':'e'*64})
    return out

class ZeRO3Safety(unittest.TestCase):
    def test_identical_train_holdout_digest_blocks_despite_verified_flag(self):
        native=fixture_native()
        native['holdout_dataset_sha256']=native['train_dataset_sha256']
        result=policy.fullbase_admission(native)
        self.assertNotEqual(result['state'],'READY_FOR_SIGNED_ONEHOST_TRAINING_START')
        self.assertIn('HOLD_TRAIN_HOLDOUT_LEAKAGE',result['reasons'])

    def test_fullbase_config_is_exact_cpu_offload_no_adapter(self):
        c=policy.zero3_cpu_config()
        self.assertEqual(c['zero_optimization']['stage'],3)
        self.assertEqual(c['zero_optimization']['offload_param']['device'],'cpu')
        self.assertEqual(c['zero_optimization']['offload_optimizer']['device'],'cpu')
        self.assertFalse(c['bf16']['enabled'])
        self.assertTrue(c['fp16']['enabled'])
        self.assertNotIn('peft',str(c).lower())
        self.assertNotIn('lora',str(c).lower())

    def test_8b_requires_real_ram_not_two_v100_aggregated(self):
        needed=policy.required_cpu_bytes(8_000_000_000)
        self.assertGreater(needed,170_000_000_000)
        observed=fixture_native()
        observed['student_param_count']=8_000_000_000
        observed['cpu_mem_available_bytes']=85*policy.GIB
        result=policy.fullbase_admission(observed)
        self.assertIn('HOLD_ZERO3_CPU_OFFLOAD_MEMORY',result['reasons'])
        self.assertEqual(result['optimizer_steps_verified'],0)

    def test_missing_live_everything_holds_before_start(self):
        p=policy.fullbase_admission(None)
        self.assertEqual(p['state'],'HOLD')
        self.assertEqual(p['optimizer_steps_verified'],0)
        self.assertFalse(p['native_training_started'])

    def test_fully_evidenced_fixture_admission_not_a_native_run(self):
        p=policy.fullbase_admission(fixture_native(),teacher_lanes=('qwen-language','deepseek-reasoning'))
        self.assertEqual(p['state'],'READY_FOR_SIGNED_ONEHOST_TRAINING_START')
        self.assertFalse(p['native_training_started'])
        self.assertEqual(p['gpu1_compute_target_pct_after_admission'],85)
        self.assertIsNone(p['gpu1_vram_target_pct'])

    def test_stop_s03_checkpoint_gpu_and_rights_each_block(self):
        modifications=[
          ('native_stop_active',True,'HOLD_STOP_ACTIVE_OR_UNKNOWN'),
          ('s03_integrity_verified',False,'HOLD_S03'),
          ('offsite_owner_checkpoint_restore_verified',False,'HOLD_OFFSITE_RESTORE'),
          ('gpu1_free_mib',17000,'HOLD_GPU1_PEAK_OR_MARGIN'),
          ('teacher_dataset_rights_verified',False,'HOLD_TEACHER_DATA_LICENSE'),
          ('optimizer_is_full_base_no_peft',False,'HOLD_ADAPTER_OR_PARTIAL_WEIGHTS'),
          ('owner_approved_training',False,'HOLD_OWNER_APPROVAL'),
        ]
        for key,value,reason in modifications:
            with self.subTest(key=key):
                native=fixture_native();native[key]=value
                admission=policy.fullbase_admission(native)
                self.assertEqual(admission['state'],'HOLD')
                self.assertIn(reason,admission['reasons'])

    def test_bad_lanes_and_duplicate_teacher_roles_refused(self):
        p=policy.fullbase_admission(fixture_native(),
                                    teacher_lanes=('qwen-language','qwen-language'))
        self.assertIn('HOLD_TEACHER_LANE_SCHEMA',p['reasons'])

    def test_independent_checkpoint_proof_not_fake_weight_delta(self):
        p=policy.native_checkpoint_acceptance({})
        self.assertEqual(p['state'],'HOLD')
        self.assertFalse(p['weights_changed_verified'])
        self.assertEqual(p['optimizer_steps_verified'],0)

    def test_signed_owner_hmac_binds_source_and_expires(self):
        native=fixture_native()
        key=b'OWNER_SECRET_IS_IN_NATIVE_RUNTIME_ONLY_12345'
        approval={'action':'nox.forge.fullbase.distill','instance_id':60509551,
                  'issued_at':1000,'expires_at':1300,
                  'admission_sha256':policy.sha256_manifest(native)}
        raw=json.dumps(approval,sort_keys=True,separators=(',',':'),
                       ensure_ascii=False).encode('utf8')
        approval['signature']=hmac.new(key,raw,hashlib.sha256).hexdigest()
        permitted=training.verify_owner(native,approval,key,now=1100)
        self.assertEqual(permitted['state'],'READY_FOR_SIGNED_ONEHOST_TRAINING_START')
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_APPROVAL_EXPIRED'):
            training.verify_owner(native,approval,key,now=1400)
        modified=dict(native);modified['student_base_sha256']='f'*64
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_SOURCE_PIN'):
            training.verify_owner(modified,approval,key,now=1100)
        with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_SIGNATURE'):
            training.verify_owner(native,approval,b'a'*40,now=1100)


    def test_cuda12_binary_sm70_required_not_only_visible_gpu(self):
        # SOURCE-ONLY simulated wheel metadata; no claim of native GPU probe.
        from types import SimpleNamespace
        def wheel(version='12.6',arches=('sm_70',),cap=(7,0),visible=True,devices=1):
            cuda=SimpleNamespace(
                is_available=lambda:visible,device_count=lambda:devices,
                get_device_capability=lambda i:cap,
                get_arch_list=lambda:list(arches))
            return SimpleNamespace(version=SimpleNamespace(cuda=version),cuda=cuda)
        for arches in (('sm_70',),('compute_70',)):
            result=training.validate_existing_v100_torch(wheel(arches=arches))
            self.assertTrue(result['compiled_sm70'])
            self.assertEqual(result['precision'],'fp16')
        cases=[
            (wheel(version='13.0'), 'HOLD_CUDA12_TORCH_BUILD'),
            (wheel(version=None), 'HOLD_CUDA12_TORCH_BUILD'),
            (wheel(version='12.8',arches=('sm_75','sm_80')), 'HOLD_TORCH_WHEEL_SM70_ARCH'),
            (wheel(version='12.6',cap=(7,5)), 'HOLD_V100_GPU1_SM70'),
            (wheel(version='12.6',devices=2), 'HOLD_V100_GPU1_SM70'),
            (wheel(version='12.6',visible=False), 'HOLD_V100_GPU1_SM70'),
        ]
        for value,reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(RuntimeError,reason):
                    training.validate_existing_v100_torch(value)
        cuda=wheel().cuda
        delattr(cuda,'get_arch_list')
        with self.assertRaisesRegex(RuntimeError,'HOLD_TORCH_WHEEL_SM70_ARCH'):
            training.validate_existing_v100_torch(
                SimpleNamespace(version=SimpleNamespace(cuda='12.6'),cuda=cuda))
        source=Path(training.__file__).read_text(encoding='utf8')
        self.assertLess(source.index('p0_runtime=validate_existing_v100_torch(torch)'),
                        source.index('out.mkdir(mode=0o700)'))

    def test_run_without_owner_cannot_import_gpu_or_train(self):
        class Args:
            max_steps=1;max_tokens=256;accum=16;lr=5e-6;execute=False
        with self.assertRaisesRegex(RuntimeError,'HOLD_SIGNED_NATIVE_LAUNCH_REQUIRED'):
            training.run(Args())

class TeacherCuration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.source=self.folder/'lessons.jsonl'
        self.dest=self.folder/'curated'
        train_groups=[f'archive-train-{i:04d}' for i in range(70)
                      if teacher.split_group(f'archive-train-{i:04d}')=='train'][:7]
        held_groups=[f'archive-held-{i:04d}' for i in range(40)
                     if teacher.split_group(f'archive-held-{i:04d}')=='holdout'][:2]
        assert len(train_groups)>=7 and len(held_groups)>=2
        i=0;self.records=[]
        for group in train_groups+held_groups:
            for j in range(55):
                prompt=f'Public verified mathematics question {i:05d} ?'
                answer=f'Independently checked value {i:05d}'
                role='qwen-language' if i%2==0 else 'deepseek-reasoning'
                row={'prompt':prompt,'completion':answer,'teacher_role':role,
                     'teacher_model_sha256':'a'*64,'source_group':group,
                     'source_uri':'https://example.org/public-source/'+group,
                     'source_license':'cc0-1.0','rights_verified':True,
                     'privacy_approved':True,'independent_validation_passed':True,
                     'source_content_sha256':teacher._digest(prompt+'\n'+answer),
                     'training_allowed':True}
                self.records.append(row);i+=1
        self.source.write_text(''.join(json.dumps(r)+'\n' for r in self.records),
                               encoding='utf8')
        self.assertGreaterEqual(sum(teacher.split_group(r['source_group'])=='train' for r in self.records),300)
        self.assertGreaterEqual(sum(teacher.split_group(r['source_group'])=='holdout' for r in self.records),30)

    def test_train_holdout_group_disjoint_and_sha_verified(self):
        result=teacher.build(self.source,self.dest)
        self.assertEqual(result['release_status'],'TRAINSET_READY_NOT_MODEL_TRAINED')
        self.assertTrue(result['source_groups_disjoint'])
        self.assertGreaterEqual(result['train_rows'],300)
        self.assertGreaterEqual(result['holdout_rows'],30)
        self.assertEqual(result['optimizer_steps_verified'],0)
        self.assertFalse(result['student_weights_changed'])
        for part in ('train','holdout'):
            self.assertEqual(teacher._file_sha(self.dest/(part+'.jsonl')),
                             result[part+'_sha256'])

    def test_duplicate_prompt_across_sources_never_spills_into_holdout(self):
        self.records[1]['prompt']=self.records[0]['prompt']
        self.records[1]['source_content_sha256']=teacher._digest(
            self.records[1]['prompt']+'\n'+self.records[1]['completion'])
        self.source.write_text(''.join(json.dumps(r)+'\n' for r in self.records))
        with self.assertRaisesRegex(ValueError,'HOLD_DUPLICATE_TRAIN_OR_HOLDOUT_PROMPT'):
            teacher.build(self.source,self.dest)
        self.assertFalse(self.dest.exists())

    def test_private_example_rejected_before_file_write(self):
        self.records[0]['prompt']='What is private passport information?'
        self.records[0]['source_content_sha256']=teacher._digest(
            self.records[0]['prompt']+'\n'+self.records[0]['completion'])
        self.source.write_text(''.join(json.dumps(r)+'\n' for r in self.records))
        with self.assertRaisesRegex(ValueError,'HOLD_TEACHER_PRIVATE_DATA'):
            teacher.build(self.source,self.dest)
        self.assertFalse(self.dest.exists())

    def test_rights_or_unverified_answer_block(self):
        with self.assertRaisesRegex(ValueError,'HOLD_TEACHER_UNVERIFIED'):
            teacher.check_row({**self.records[0],'independent_validation_passed':False})
        with self.assertRaisesRegex(ValueError,'HOLD_TEACHER_TRAINING_CONSENT'):
            teacher.check_row({**self.records[0],'training_allowed':False})

    def test_unapproved_licenses_refused(self):
        with self.assertRaisesRegex(ValueError,'HOLD_TEACHER_LICENSE'):
            teacher.check_row({**self.records[0],'source_license':'proprietary-unknown'})

    def test_output_conflict_no_overwrite(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError,'HOLD_OUTPUT_DESTINATION_CONFLICT'):
            teacher.build(self.source,self.dest)

if __name__=='__main__':
    unittest.main()
