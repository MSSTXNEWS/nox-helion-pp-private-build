"""NOX V71 no-loss/single-identity tests. No GPUs, users, or remote callbacks."""
from __future__ import annotations
import unittest
from types import SimpleNamespace

from nox_runpod.teacher_mesh.v38.native_bridge_v38 import HostBindings
from nox_runpod.teacher_mesh.v38.synaptic_brain import Session
from nox_runpod.teacher_mesh.v71.disk_budget import verify_new_write_space
from nox_runpod.teacher_mesh.v71.ram_policy import plan_ram, plan_warm_weight, GIB, MIB
from nox_runpod.teacher_mesh.v71.offload_policy import plan_offload
from nox_runpod.teacher_mesh.v71.one_prime import OnePrime, NativeOneHost


def ram(**kwargs):
    s={"native_ram_verified":True,
       "ram_available_bytes":273_725_329_408,
       "shm_free_bytes":22_953_877_504,
       "native_cgroup_verified":True,
       "cgroup_memory_max_bytes":194_065_203_200,
       "cgroup_memory_current_bytes":105_219_207_168,
       "s03_native_revision_verified":True,
       "stop_active":False,
       "native_cgroup_oom_delta_verified":True,
       "cgroup_oom_kill_delta":0}
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

    def test_memavailable_cannot_override_unverified_cgroup(self):
        out=plan_ram(ram(native_cgroup_verified=False))
        self.assertEqual(out['state'],'HOLD_NATIVE_CGROUP_TELEMETRY')
        self.assertEqual(out['cache_bytes'],0)
        self.assertEqual(out['temporary_workspace_bytes'],0)

    def test_container_budget_caps_oversized_host_ram(self):
        out=plan_ram(ram(ram_available_bytes=900*GIB,
            cgroup_memory_max_bytes=64*GIB,
            cgroup_memory_current_bytes=53*GIB))
        self.assertEqual(out['state'],'HOLD_RAM_CACHE_HEADROOM')
        self.assertEqual(out['cache_bytes'],0)

    def test_combined_cache_and_workspace_within_cgroup(self):
        s=ram()
        out=plan_ram(s)
        self.assertEqual(out['state'],'RAM_CACHE_AND_WORKSPACE_READY')
        self.assertTrue(out['cgroup_limit_verified'])
        self.assertLessEqual(s['cgroup_memory_current_bytes']+
            out['cache_bytes']+out['temporary_workspace_bytes'],
            out['cgroup_safe_ceiling_bytes'])
        self.assertFalse(out['model_weights_downloaded'])
        self.assertFalse(out['disk_model_cache_created'])
        self.assertFalse(out['performed'])

    def test_unknown_stop_and_oom_telemetry_never_admits_ram(self):
        trusted=ram()
        for val in (None, 0, 'false'):
            with self.subTest(stop=val):
                self.assertEqual(plan_ram(ram(stop_active=val))['state'],
                                 'HOLD_STOP_NOT_VERIFIED')
        missing_stop=dict(trusted)
        del missing_stop['stop_active']
        self.assertEqual(plan_ram(missing_stop)['state'],
                         'HOLD_STOP_NOT_VERIFIED')
        missing_oom=dict(trusted)
        del missing_oom['cgroup_oom_kill_delta']
        self.assertEqual(plan_ram(missing_oom)['state'],
                         'HOLD_UNVERIFIED_OOM_DELTA')
        self.assertEqual(plan_ram(ram(native_cgroup_oom_delta_verified=False))['state'],
                         'HOLD_UNVERIFIED_OOM_DELTA')
        self.assertEqual(plan_ram(ram(cgroup_oom_kill_delta=None))['state'],
                         'HOLD_UNVERIFIED_OOM_DELTA')
        self.assertEqual(plan_ram(trusted)['state'],
                         'RAM_CACHE_AND_WORKSPACE_READY')

    def test_native_oom_delta_and_stop_fail_closed(self):
        self.assertEqual(plan_ram(ram(cgroup_oom_kill_delta=1))['state'],
                         'HOLD_RECENT_CGROUP_OOM')
        self.assertEqual(plan_ram(ram(stop_active=True))['state'],
                         'HOLD_OWNER_STOP')

    def test_cgroup_high_limit_tighter_than_max(self):
        out=plan_ram(ram(cgroup_memory_high_bytes=108*GIB))
        self.assertLessEqual(out['cgroup_safe_ceiling_bytes'],108*GIB)
        if out['state']=='RAM_CACHE_AND_WORKSPACE_READY':
            self.assertLessEqual(out['cgroup_safe_room_after_budget_bytes'],
                                 108*GIB-105_219_207_168)

    def test_native_inventory_reports_cgroup_not_host_only(self):
        from nox_runpod.teacher_mesh.v71 import ram_inventory
        for token in ('NATIVE_RAM_CGROUP_MAX_BYTES',
                      'NATIVE_RAM_CGROUP_CURRENT_BYTES',
                      'NATIVE_RAM_CGROUP_OOM_KILL_COUNT'):
            self.assertIn(token,ram_inventory.REMOTE)

    def test_no_mmap_or_ram_s03_primary(self):
        r=plan_ram(ram())
        self.assertEqual(r['s03_canonical'],'PERSISTENT_SQLITE_WAL')
        self.assertTrue(r['warm_cache_requires_native_revision'])



class RamWeightTiers(unittest.TestCase):
    def s(self,**updates):
        data={'native_ram_verified':True,'owner_authorized':True,
              'stop_active':False,'chat_gpu0_healthy':True,
              's03_native_healthy':True,
              'native_cgroup_verified':True,
              'native_cgroup_oom_delta_verified':True,
              'cgroup_oom_kill_delta':0,
              'chat_state':'idle','prime_active_streams':0,
              'seconds_since_chat_activity':120.0,
              'cgroup_max_bytes':194_065_203_200,
              'cgroup_current_bytes':104_872_435_712,
              'ram_available_bytes':86*GIB}
        data.update(updates)
        return data

    def model(self,**updates):
        data={'kind':'HF_SAFETENSORS','source_state':'LOCAL_VERIFIED',
              'sha_verified':True,'sha256':'a'*64,'license_verified':True,
              'in_use':False,'source_file_open':False,'size_bytes':26*GIB}
        data.update(updates)
        return data

    def test_bounded_reclaimable_pagecache_without_ssd_write(self):
        result=plan_warm_weight(self.s(),self.model())
        self.assertEqual(result['state'],'READY_FOR_EXISTING_V95_V99_OWNER_PAGECACHE_WARMUP')
        self.assertEqual(result['warm_bytes_budget'],2*GIB)
        self.assertEqual(result['new_disk_bytes'],0)
        self.assertFalse(result['performed'])
        self.assertFalse(result['new_model_instance'])
        self.assertFalse(result['physical_warmup_verified'])
        self.assertEqual(result['s03_canonical'],'PERSISTENT_SQLITE_WAL')

    def test_recent_chat_or_unknown_stop_preempts_warmup(self):
        for status in (self.s(chat_state='generating'),self.s(prime_active_streams=1),
                       self.s(seconds_since_chat_activity=3),self.s(stop_active=None)):
            with self.subTest(status=status):
                self.assertTrue(plan_warm_weight(status,self.model())['state'].startswith('HOLD'))

    def test_unverified_s03_health_never_admits_page_cache_pressure(self):
        for health in (False, None, 0, 'true'):
            with self.subTest(s03_health=health):
                out=plan_warm_weight(self.s(s03_native_healthy=health),self.model())
                self.assertEqual(out['state'],'HOLD_S03_HEALTH_NOT_VERIFIED')
                self.assertEqual(out['warm_bytes_budget'],0)
                self.assertFalse(out['performed'])
        missing=self.s()
        del missing['s03_native_healthy']
        self.assertEqual(plan_warm_weight(missing,self.model())['state'],
                         'HOLD_S03_HEALTH_NOT_VERIFIED')

    def test_remote_verified_never_claims_diskless_loader(self):
        out=plan_warm_weight(self.s(),self.model(source_state='REMOTE_VERIFIED'))
        self.assertEqual(out['state'],'HOLD_RAM_ONLY_REMOTE_LOADER_NOT_NATIVE_BOUND')
        self.assertFalse(out['diskless_model_loader_running'])
        self.assertEqual(out['new_disk_bytes'],0)

    def test_unknown_file_or_sha_holds(self):
        for model in (self.model(sha_verified=False),self.model(license_verified=False),
                      self.model(source_file_open=None),self.model(in_use=True),
                      self.model(sha256='not-a-digest')):
            with self.subTest(model=model):
                self.assertTrue(plan_warm_weight(self.s(),model)['state'].startswith('HOLD'))

    def test_cgroup_and_chat_reserve_prevents_oom(self):
        snap=self.s(cgroup_current_bytes=191*GIB,cgroup_max_bytes=194*GIB)
        out=plan_warm_weight(snap,self.model())
        self.assertEqual(out['state'],'HOLD_RAM_HEADROOM_FOR_CHAT')
        self.assertEqual(out['warm_bytes_budget'],0)

    def test_cgroup_bool_sensor_rejected(self):
        out=plan_warm_weight(self.s(cgroup_current_bytes=True),self.model())
        self.assertEqual(out['state'],'HOLD_CGROUP_OR_RAM_SENSOR')
        self.assertEqual(out['warm_bytes_budget'],0)

    def test_warmup_fails_closed_without_native_cgroup_and_oom_proof(self):
        cases=(
            (self.s(native_cgroup_verified=False),'HOLD_NATIVE_CGROUP_TELEMETRY'),
            (self.s(native_cgroup_oom_delta_verified=False),'HOLD_UNVERIFIED_OOM_DELTA'),
            (self.s(cgroup_oom_kill_delta=None),'HOLD_UNVERIFIED_OOM_DELTA'),
            (self.s(cgroup_oom_kill_delta=1),'HOLD_RECENT_CGROUP_OOM'),
        )
        for snap,expected in cases:
            with self.subTest(expected=expected):
                out=plan_warm_weight(snap,self.model())
                self.assertEqual(out['state'],expected)
                self.assertEqual(out['warm_bytes_budget'],0)
                self.assertFalse(out['performed'])

    def test_warmup_obeys_cgroup_memory_high_pressure(self):
        snap=self.s()
        snap['cgroup_memory_high_bytes']=snap['cgroup_current_bytes']+32*MIB
        out=plan_warm_weight(snap,self.model())
        self.assertEqual(out['state'],'HOLD_RAM_HEADROOM_FOR_CHAT')
        self.assertEqual(out['warm_bytes_budget'],0)
        self.assertFalse(out['performed'])
        self.assertEqual(plan_warm_weight(self.s(cgroup_memory_high_bytes='max'),
                        self.model())['state'],'HOLD_CGROUP_MEMORY_HIGH_SENSOR')

    def test_hold_never_exposes_executable_warm_bytes_near_threshold(self):
        # Previously a 32 MiB HOLD still published 32 MiB as an actionable
        # warm_bytes_budget. That ambiguous output must always fail closed.
        for free in (1*MIB,32*MIB,63*MIB):
            with self.subTest(high_minus_current=free):
                snap=self.s()
                snap['cgroup_memory_high_bytes']=snap['cgroup_current_bytes']+free
                out=plan_warm_weight(snap,self.model())
                self.assertEqual(out['state'],'HOLD_RAM_HEADROOM_FOR_CHAT')
                self.assertEqual(out['warm_bytes_budget'],0)
                self.assertEqual(out['headroom_after_budget_bytes'],
                                 snap['cgroup_max_bytes']-snap['cgroup_current_bytes'])
                self.assertFalse(out['performed'])
        snap=self.s()
        snap['cgroup_memory_high_bytes']=snap['cgroup_current_bytes']+64*MIB
        ready=plan_warm_weight(snap,self.model())
        self.assertEqual(ready['state'],'READY_FOR_EXISTING_V95_V99_OWNER_PAGECACHE_WARMUP')
        self.assertEqual(ready['warm_bytes_budget'],64*MIB)
        self.assertFalse(ready['performed'])

    def test_warmup_accepts_canonical_native_v71_keys_not_conflicts(self):
        snap=self.s()
        cap=snap.pop('cgroup_max_bytes')
        current=snap.pop('cgroup_current_bytes')
        snap.update(cgroup_memory_max_bytes=cap,cgroup_memory_current_bytes=current)
        out=plan_warm_weight(snap,self.model())
        self.assertEqual(out['state'],'READY_FOR_EXISTING_V95_V99_OWNER_PAGECACHE_WARMUP')
        self.assertEqual(out['warm_bytes_budget'],2*GIB)
        snap['cgroup_max_bytes']=cap+GIB
        out=plan_warm_weight(snap,self.model())
        self.assertEqual(out['state'],'HOLD_CGROUP_OR_RAM_SENSOR')
        self.assertEqual(out['warm_bytes_budget'],0)

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
