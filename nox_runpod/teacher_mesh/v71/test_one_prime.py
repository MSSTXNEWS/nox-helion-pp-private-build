"""NOX V71 no-loss/single-identity tests. No GPUs, users, or remote callbacks."""
from __future__ import annotations
import unittest
from types import SimpleNamespace

from nox_runpod.teacher_mesh.v38.native_bridge_v38 import HostBindings
from nox_runpod.teacher_mesh.v38.synaptic_brain import Session
from nox_runpod.teacher_mesh.v71.disk_budget import verify_new_write_space
from nox_runpod.teacher_mesh.v71.ram_policy import plan_ram, GIB, MIB
from nox_runpod.teacher_mesh.v71.offload_policy import plan_offload
from nox_runpod.teacher_mesh.v71.one_prime import OnePrime, NativeOneHost


def ram(**kwargs):
    s={"native_ram_verified":True,
       "ram_available_bytes":273_725_329_408,
       "shm_free_bytes":22_953_877_504,
       "s03_native_revision_verified":True}
    s.update(kwargs)
    return s


def snapshot(**kwargs):
    data={
        "owner_authorized":True, "stop_active":False,
        "chat_state":"idle", "seconds_since_chat_activity":120,
        "s03_native_healthy":True, "chat_gpu0_healthy":True,
        "disk_free_bytes":17_451_630_592,
        "estimated_new_checkpoint_bytes":1_000_000_000,
        "estimated_temp_bytes":500_000_000,
        "disk_write_estimate_verified":True,
        "external_restore_verified":True,
        "checkpoint_resume_verified":True,
        "runtime_gpu_abi_verified":True,
        "training_owner_lease":True,
        "gpus":[{"vram_free_mib":5000,"temperature_c":35},
                {"vram_free_mib":9000,"temperature_c":40}],
    }
    data.update(ram())
    data.update(kwargs)
    return data


class RamGate(unittest.TestCase):
    def test_measured_273gb_allows_dynamic_ram(self):
        r=plan_ram(ram())
        self.assertEqual(r['state'],'RAM_CACHE_AND_WORKSPACE_READY')
        self.assertEqual(r['cache_bytes'],256*MIB)
        self.assertGreater(r['temporary_workspace_bytes'],10*GIB)
        self.assertGreaterEqual(r['tmpfs_free_after_budget_bytes'],4*GIB)
        self.assertFalse(r['performed'])

    def test_ram_will_not_shadow_unverified_s03_revision(self):
        r=plan_ram(ram(s03_native_revision_verified=False))
        self.assertEqual(r['state'],'RAM_CAPACITY_READY_S03_CACHE_HOLD_REVISION')
        self.assertEqual(r['cache_bytes'],0)

    def test_memavailable_must_be_native(self):
        self.assertEqual(plan_ram(ram(native_ram_verified=False))['cache_bytes'],0)

    def test_no_overcommit_on_small_tmpfs(self):
        r=plan_ram(ram(shm_free_bytes=3*GIB))
        self.assertEqual(r['temporary_workspace_bytes'],0)

    def test_no_mmap_or_ram_s03_primary(self):
        r=plan_ram(ram())
        self.assertEqual(r['s03_canonical'],'PERSISTENT_SQLITE_WAL')
        self.assertTrue(r['warm_cache_requires_native_revision'])


class Disk10GB(unittest.TestCase):
    def test_10gb_floor_mandatory_only_for_new_writes(self):
        r=verify_new_write_space({
            'disk_free_bytes':12_000_000_000,
            'estimated_new_checkpoint_bytes':1_000_000_000,
            'estimated_temp_bytes':500_000_000,
            'disk_write_estimate_verified':True})
        self.assertEqual(r['state'],'READY_FOR_OTHER_NATIVE_GATES')
        self.assertTrue(r['chat_allowed'])

    def test_chat_allowed_below_10gb_but_new_checkpoint_holds(self):
        r=verify_new_write_space({
            'disk_free_bytes':9_000_000_000,
            'estimated_new_checkpoint_bytes':1_000_000_000,
            'estimated_temp_bytes':100_000_000,
            'disk_write_estimate_verified':True})
        self.assertTrue(r['chat_allowed'])
        self.assertEqual(r['state'],'HOLD_INSUFFICIENT_SPACE_FOR_NEW_WRITE')

    def test_without_verified_temp_budget_no_training(self):
        r=verify_new_write_space({'disk_free_bytes':30_000_000_000,
            'estimated_new_checkpoint_bytes':1_000_000_000,
            'estimated_temp_bytes':0,
            'disk_write_estimate_verified':False})
        self.assertFalse(r['training_allowed_by_disk_alone'])


class Offload10GB(unittest.TestCase):
    def test_above_floor_never_deletes_or_migrates(self):
        out=plan_offload({'disk_free_bytes':17_462_976_512})
        self.assertEqual(out['state'],'NO_CLEANUP_NEEDED')
        self.assertEqual(out['actions'],[])
        self.assertTrue(out['chat_allowed'])
        self.assertFalse(out['source_deleted'])

    def test_below_floor_proposes_cache_first(self):
        data={'disk_free_bytes':8_200_000_000,'stop_active':False,
              'native_owner_authorized':True,
              'drive_destination_authorized':True,
              'candidates':[{'kind':'pip_cache','native_verified':True,
                'not_open':True,'not_used_by_running_process':True,
                'allowlisted_root':True}]}
        out=plan_offload(data)
        self.assertEqual(out['state'],'OFFLOAD_REQUIRED')
        self.assertIn('OWNER_NATIVE_REGENERABLE_CACHE_CLEANUP_PROPOSAL',out['actions'])
        self.assertIn('ENCRYPTED_DRIVE_COPY_THROUGH_EXISTING_OFFLOAD',out['actions'])
        self.assertFalse(out['performed'])

    def test_protected_weight_memory_and_checkpoint_never_candidates(self):
        out=plan_offload({'disk_free_bytes':7_000_000_000,
           'stop_active':False,'native_owner_authorized':True,
           'candidates':[{'kind':k,'native_verified':True,'not_open':True,
                'not_used_by_running_process':True,'allowlisted_root':True}
                for k in ('active_student','s03','checkpoint','optimizer')]})
        self.assertFalse(any('CLEANUP_PROPOSAL' in v for v in out['actions']))

    def test_cold_backup_not_owner_restored_blocks_deletion(self):
        out=plan_offload({'disk_free_bytes':7_000_000_000,
           'stop_active':False,'native_owner_authorized':True,
           'candidates':[{'kind':'cold_model','active_student':False,
                          'original_full_sha_verified':True,
                          'offsite_cipher_sha_verified':True,
                          'offsite_download_roundtrip_verified':True,
                          'owner_key_restore_verified':False}]})
        self.assertIn('VERIFY_COLD_MODEL_OFFSITE_AND_RESTORE_BEFORE_CLEANUP',out['actions'])
        self.assertFalse(any('VERIFIED_COLD_COPY_CLEANUP_PROPOSAL'==x for x in out['actions']))


class OnePrimeTest(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.llm_calls=[]
        self.memory_queries=[]
        self.s=Session(tenant='nox',principal='owner',chat_id='resonance')
        self.native_status=snapshot()
        def recall(session,prompt,limit):
            self.memory_queries.append(prompt)
            return [{'id':'m','tenant':session.tenant,'principal':session.principal,
                     'chat_id':session.chat_id,'source_uri':'s03://verified/x',
                     'content':'real-memory','verified':True,'superseded':False,'segment':'M7'}]
        def record(session,event):
            self.events.append(event)
            return {'verified':True,'durable':True,'event_id':'n-'+str(len(self.events))}
        def model(prompt,context):
            self.llm_calls.append(context)
            yield 'NOX PRIME'
            yield ' отвечает.'
        host=HostBindings(authorize=lambda s:True,stop=lambda:False,
             s03_recall=recall,s03_revision=lambda s:'rev-1',
             s03_append=record,model_stream=model)
        self.prime=OnePrime(NativeOneHost(chat=host,observe=lambda:self.native_status))
        self.addCleanup(self.prime.close)

    def test_one_model_and_s03_durable_turn(self):
        r=list(self.prime.stream(self.s,'Вспомни вчера','turn-v71-1'))
        self.assertEqual(r[-1]['type'],'done')
        self.assertEqual(len(self.llm_calls),1)
        self.assertGreaterEqual(len(self.memory_queries),1)
        self.assertEqual(self.events[0]['kind'],'user_message')
        self.assertEqual(self.events[-1]['kind'],'assistant_final')
        self.assertEqual(self.prime.active_chats if hasattr(self.prime,'active_chats') else self.prime._active,0)

    def test_live_stream_preempts_teachers(self):
        gen=self.prime.stream(self.s,'Привет','turn-v71-2')
        self.assertEqual(next(gen)['type'],'phase')
        self.assertEqual(self.prime._active,1)
        p=self.prime.background_admission()
        self.assertIn('CHAT_FIRST',p['reasons'])
        self.assertEqual(p['chat_priority'],'P0')
        self.assertEqual(p['background_priority'],'P1')
        self.assertFalse(p['training_launch'])
        gen.close()
        self.assertEqual(self.prime._active,0)

    def test_no_implicit_training_and_only_one_onehost(self):
        p=self.prime.background_admission()
        self.assertIn('REQUEST_ONEHOST_GPU1_DISTILLATION_ADMISSION',p['actions'])
        self.assertFalse(p['training_launch'])
        self.assertEqual(p['queue_owner'],'EXISTING_NOX_ONEHOST')
        self.assertFalse(p['new_backend'])
        self.assertFalse(p['new_scheduler'])
        out=self.prime.enqueue_existing_verified_plan({'state':'PROPOSAL_ONLY_NOT_ENQUEUED',
                        'planned':[]},owner_scope='nox.owner')
        self.assertEqual(out['jobs_enqueued'],0)

    def test_memory_not_silently_disabled_for_speed(self):
        self.prime.native.chat.s03_recall  # the callback is mandatory
        self.prime.on_s03_write(self.s)
        self.assertTrue(self.prime.chat.brain.cfg.require_memory)

if __name__=='__main__':
    unittest.main()
