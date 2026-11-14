"""NOX V99 resource policy tests: 85% is a compute/cache target, not VRAM OOM."""
import unittest
from nox_runpod.teacher_mesh.v99.training_85_budget import resource_plan,GIB

def snapshot(**changes):
    data={
        'instance_id':60509551,'native_verified':True,
        'owner_authorized':True,'stop_active':False,
        'chat_gpu0_healthy':True,'s03_native_healthy':True,
        'chat_state':'idle','chat_recent':False,
        'cpu_affinity_count':80,'cpu_preparation_verified':True,
        'cgroup_max_bytes':194_065_203_200,
        'cgroup_current_bytes':144_508_354_560,
        'gpu1_free_mib':30000,'gpu1_peak_training_mib':17000,
        'gpu1_peak_profile_verified':True,
        'gpu1_trainer_active':False,'gpu1_teacher_active':False,
        'onehost_gpu1_lease':True,
        'trainable_student_format':'HF_BASE_SAFETENSORS',
        'full_weight_training':True,'uses_lora':False,'precision':'fp16',
        'sm70_cuda_abi_verified':True,
        'checkpoint_owner_key_restore_verified':True,
        'train_holdout_license_privacy_verified':True,
        'disk_free_bytes':32_000_000_000,
        'estimated_full_checkpoint_temp_bytes':10_000_000_000,
        'checkpoint_write_budget_verified':True,
    }
    data.update(changes)
    return data

class Budget85(unittest.TestCase):
    def test_80_logical_cpus_cap_68_not_80(self):
        r=resource_plan(snapshot())
        self.assertEqual(r['cpu_worker_cap_when_chat_idle'],68)
        self.assertEqual(r['cpu_threads_reserved_for_chat'],12)
        self.assertEqual(r['cpu_workers_start'],4)
        self.assertEqual(r['target_compute_utilization_pct'],85)
        self.assertFalse(r['performed'])
        self.assertEqual(r['gpu1_base_weight_training'],'READY_FOR_EXISTING_ONEHOST_ONE_JOB')
        self.assertEqual(r['gpu1_vram_target_pct'],None)

    def test_memory_cap_is_85_percent_of_cgroup_not_host(self):
        r=resource_plan(snapshot())
        self.assertEqual(r['ram_cache_85pct_target_bytes'],int(194_065_203_200*.85))
        self.assertLessEqual(r['ram_new_cache_budget_bytes'],24*GIB)
        self.assertGreater(r['ram_new_cache_budget_bytes'],GIB)
        self.assertTrue(r['ram_cache_is_reclaimable'])

    def test_actual_v100_8gb_free_blocks_full_model(self):
        r=resource_plan(snapshot(gpu1_free_mib=8477,gpu1_peak_training_mib=15000))
        self.assertEqual(r['gpu1_base_weight_training'],'HOLD_PROTECTED')
        self.assertIn('HOLD_GPU1_CUDA_OOM_EXPECTED',r['reasons'])
        self.assertFalse(r['training_started'])

    def test_existing_teacher_prevents_concurrent_training(self):
        r=resource_plan(snapshot(gpu1_teacher_active=True))
        self.assertIn('HOLD_GPU1_EXISTING_WORK',r['reasons'])

    def test_chat_p0_preempts_gpu1_and_cpu_background(self):
        r=resource_plan(snapshot(chat_state='generating',chat_recent=True))
        self.assertIn('CHAT_P0_PREEMPTS_BACKGROUND',r['reasons'])
        self.assertEqual(r['cpu_data_preparation'],'HOLD_OR_IDLE_REQUIRED')
        self.assertEqual(r['gpu1_base_weight_training'],'HOLD_PROTECTED')

    def test_missing_owner_lease_or_restore_denies(self):
        r=resource_plan(snapshot(onehost_gpu1_lease=False,
                                 checkpoint_owner_key_restore_verified=False))
        self.assertIn('HOLD_GPU1_ONEHOST_LEASE',r['reasons'])
        self.assertIn('HOLD_CHECKPOINT_OWNER_RESTORE',r['reasons'])

    def test_lora_and_gguf_never_count_as_base_weight_training(self):
        r=resource_plan(snapshot(trainable_student_format='GGUF_Q4',
                                 uses_lora=True,full_weight_training=False))
        self.assertIn('HOLD_NOX_TRAINABLE_BASE_REQUIRED',r['reasons'])
        self.assertIn('HOLD_NO_ADAPTER_DIRECT_BASE_ONLY',r['reasons'])

    def test_85_percent_cgroup_target_does_not_force_memory_allocation(self):
        r=resource_plan(snapshot(cgroup_current_bytes=180_000_000_000))
        self.assertEqual(r['ram_new_cache_budget_bytes'],0)
        self.assertIn('HOLD_RAM_85PCT_TARGET_REACHED',r['reasons'])
        self.assertFalse(r['performed'])

    def test_10gb_disk_floor_only_new_checkpoint(self):
        r=resource_plan(snapshot(disk_free_bytes=15_000_000_000,
                   estimated_full_checkpoint_temp_bytes=10_000_000_000))
        self.assertIn('HOLD_CHECKPOINT_DISK_BUDGET',r['reasons'])

    def test_unknown_peak_memory_fails_closed(self):
        r=resource_plan(snapshot(gpu1_peak_profile_verified=False))
        self.assertIn('HOLD_GPU1_MODEL_OPTIMIZER_PEAK',r['reasons'])

    def test_no_new_scheduler_and_chats_remain_one_identity(self):
        r=resource_plan(snapshot())
        self.assertFalse(r['new_scheduler'])
        self.assertFalse(r['new_backend'])
        self.assertEqual(r['student_model_count'],1)
        self.assertEqual(r['chat_gpu_index'],0)
        self.assertEqual(r['training_gpu_index'],1)
        self.assertFalse(r['weight_changes_verified'])

if __name__=="__main__":
    unittest.main()
