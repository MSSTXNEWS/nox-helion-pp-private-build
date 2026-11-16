import json, pathlib, sys, tempfile, unittest
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pc'));sys.path.insert(0,str(ROOT/'nox'))
from download_models import manifest,disk_admit,digest_file,existing_status,fetch_one
from resource_brain import plan_load,apply_native_plan,plan_adaptive_gpu,plan_gpu_stop,execute_gpu_stop,plan_gpu_recovery,execute_gpu_recovery

class TestManifestAndVault(unittest.TestCase):
    def setUp(self):self.models=manifest()['models']
    def test_five_and_pinned_three(self):
        self.assertEqual(len(self.models),5)
        self.assertEqual(sum(x['method']=='single_file' for x in self.models),3)
        self.assertTrue(all(len(x['sha256'])==64 for x in self.models[:3]))
    def test_all_sources_verified(self):
        self.assertTrue(all(x['source_url'].startswith('https://huggingface.co/') for x in self.models))
    def test_disk_admission(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(disk_admit(d,9999)['state'],'HOLD_DISK')
    def test_missing_is_not_installed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(existing_status(self.models[0],pathlib.Path(d)/'none'),'MISSING')
    def test_existing_bad_gguf_hold(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/self.models[0]['source_file'];p.write_bytes(b'junk')
            self.assertEqual(existing_status(self.models[0],d,True),'HOLD_SHA_MISMATCH')
    def test_bad_manifest_hold(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'manifest.json';p.write_text('{}')
            with self.assertRaises(ValueError):manifest(p)
    def test_official_partial_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/self.models[3]['id'];p.mkdir();(p/'model.safetensors').write_bytes(b'fragment')
            out=fetch_one(self.models[3],d)
            self.assertEqual(out['state'],'HOLD_EXISTING_SNAPSHOT_UNVERIFIED')
    def test_pin_and_snapshot_resume(self):
        with tempfile.TemporaryDirectory() as d:
            m=dict(self.models[3],approx_gb=0.1);p=pathlib.Path(d)/m['id'];p.mkdir()
            sha='a'*40
            (p/'NOX_V43_PENDING_REVISION.json').write_text(json.dumps({'repo_id':m['source_repo'],'revision':sha}))
            called=[]
            def snap(**kwargs):
                called.append(kwargs)
                (p/'weights.safetensors').write_bytes(b'x'*150_000_000)
            out=fetch_one(m,d,SimpleNamespace(model_info=lambda repo: (_ for _ in ()).throw(Exception('must not repin'))),
                          lambda **k:None,snap)
            self.assertEqual(out['state'],'DOWNLOADED_AND_HASHED')
            self.assertEqual(called[0]['revision'],sha)
            self.assertTrue((p/'NOX_V43_VERIFIED_RECEIPT.json').exists())

class TestResourceBrain(unittest.TestCase):
    def setUp(self):
        self.s={'models':[{'id':'m','sha_verified':True,'approved_license':True,
                            'installed_locally':True,'role':'teacher','loaded':False}],
                'gpus':[{'id':0,'vram_free_mib':900,'protected_student':True},
                        {'id':1,'vram_free_mib':30000,'protected_student':False}],
                'native_verified':True,'chat_gpu0_healthy':True,
                'stop_active':False,'checkpoint_pending':False,'optimizer_step_active':False,
                'gpu1_trainer_active':False,'gpu1_teacher_in_flight':False,
                'onehost_gpu1_lease':True,
                'disk_free_bytes':80_000_000_000,'ram_free_mib':30000,
                'cgroup_max_bytes':128*1024**3,'cgroup_current_bytes':16*1024**3}
        self.req={'model_id':'m','role':'teacher','peak_vram_mib':16000}
    def test_proposes_only(self):
        r=plan_load(self.req,self.s)
        self.assertEqual(r['state'],'OWNER_NATIVE_APPROVAL_REQUIRED')
        self.assertFalse(r['performed'])
    def test_never_evict_main_chat(self):
        self.s['models'].append({'id':'nox','role':'student','loaded':True,'in_flight':0,'native_owner':'OneHost'})
        self.s['models'].append({'id':'other','role':'teacher','loaded':True,'in_flight':0,'pinned':True,'native_owner':'OneHost'})
        r=plan_load(self.req,self.s)
        self.assertEqual(r['state'],'HOLD_TEACHER_LIMIT')
        self.assertEqual(r['unload_candidates'],[])
    def test_idling_teacher_can_only_be_proposed(self):
        self.s['models'].append({'id':'old','role':'teacher','loaded':True,'in_flight':0,'pinned':False,'native_owner':'OneHost'})
        r=plan_load(self.req,self.s)
        self.assertEqual(r['state'],'OWNER_NATIVE_UNLOAD_AND_RETRY_REQUIRED')
        self.assertFalse(r['performed'])
    def test_no_disruption_active_optimizer(self):
        self.s['optimizer_step_active']=True
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_CHECKPOINT_OR_ACTIVE_OPTIMIZER')
    def test_existing_verified_teacher_can_be_proposed_below_20gb(self):
        self.s['disk_free_bytes']=15_000_000_000
        self.assertEqual(plan_load(self.req,self.s)['state'],'OWNER_NATIVE_APPROVAL_REQUIRED')
    def test_new_download_never_started_by_resource_brain(self):
        self.req['download_needed']=True
        self.assertEqual(plan_load(self.req,self.s)['state'],'REMOTE_PC_COLD_OR_DRIVE_ONLY')
    def test_any_new_disk_write_requires_separate_budget(self):
        self.req['new_disk_bytes']=1_000_000_000
        self.assertEqual(plan_load(self.req,self.s)['state'],
                         'HOLD_NEW_DISK_WRITE_NEEDS_SEPARATE_VERIFIED_BUDGET')
    def test_two_vram_not_sum(self):
        self.s['gpus'][1]['vram_free_mib']=12000
        self.assertEqual(plan_load(self.req,self.s)['state'],'REMOTE_PC_OR_HOLD')
    def test_diffusion_runtime_requires_adapter(self):
        self.req['role']='video';self.s['models'][0]['runtime']='none'
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_DIFFUSION_RUNTIME_NOT_VERIFIED')
    def test_no_native_snapshot_or_malformed_rows_fail_closed(self):
        self.assertEqual(plan_load(self.req,None)['state'],'HOLD_NATIVE_INVENTORY_UNVERIFIED')
        self.s.pop('native_verified')
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_NATIVE_INVENTORY_UNVERIFIED')
        self.s['native_verified']=True
        self.s['models']=[None]
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_INVALID_INVENTORY')
    def test_missing_checkpoint_or_optimizer_state_is_not_idle(self):
        for key in ('checkpoint_pending','optimizer_step_active'):
            with self.subTest(key=key):
                data=dict(self.s);data.pop(key)
                self.assertEqual(plan_load(self.req,data)['state'],
                                 'HOLD_CHECKPOINT_OR_ACTIVE_OPTIMIZER')
    def test_active_trainer_or_unknown_exclusive_lease_never_admitted(self):
        for key,bad in (('gpu1_trainer_active',True),
                        ('gpu1_teacher_in_flight',True),
                        ('onehost_gpu1_lease',None)):
            with self.subTest(key=key):
                data=dict(self.s);data[key]=bad
                self.assertEqual(plan_load(self.req,data)['state'],
                                 'HOLD_GPU1_BUSY_OR_LEASE_UNVERIFIED')
    def test_gpu0_chat_must_be_known_healthy(self):
        self.s.pop('chat_gpu0_healthy')
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_CHAT_GPU0_UNVERIFIED')
    def test_asset_cannot_be_assumed_local_or_loaded(self):
        self.s['models'][0].pop('installed_locally')
        self.assertEqual(plan_load(self.req,self.s)['state'],'REMOTE_PC_COLD_OR_DRIVE_ONLY')
        self.s['models'][0]['loaded']=None
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_MODEL_LOAD_STATE_UNVERIFIED')
    def test_invalid_gpu1_vram_and_aggregate_sensor_fail_closed(self):
        for bad in (True,'30000',65536):
            with self.subTest(bad=repr(bad)):
                self.s['gpus'][1]['vram_free_mib']=bad
                self.assertEqual(plan_load(self.req,self.s)['state'],
                                 'HOLD_GPU1_NATIVE_SENSOR_UNVERIFIED')
        self.s['gpus'][1]['vram_free_mib']=30000
        self.s['gpus'][1].pop('protected_student')
        self.assertEqual(plan_load(self.req,self.s)['state'],
                         'HOLD_GPU1_NATIVE_SENSOR_UNVERIFIED')
    def test_ram_free_mib_must_be_numeric(self):
        self.s['ram_free_mib']='30000'
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_RAM_SENSOR_UNVERIFIED')
    def test_native_stop_appearing_during_authorization_prevents_activation(self):
        plan=plan_load(self.req,self.s)
        calls={'stop':0,'act':0}
        def native_stop():
            calls['stop']+=1
            return calls['stop']>=2
        def native_act(p):
            calls['act']+=1
            return {'status':'should_not_run'}
        r=apply_native_plan(plan,native_stop=native_stop,
             native_authorize=lambda p:True,native_act=native_act,
             native_verify=lambda p,receipt:True,
             native_readback=lambda p,receipt:{'model_id':'m','running':True})
        self.assertEqual(r['state'],'HOLD_NATIVE_STOP_RACE')
        self.assertEqual(calls['act'],0)
    def test_unload_unknown_inflight_or_pinned_is_never_proposed(self):
        # Existing teacher is present, but may be busy or pinned; no
        # auto-unload candidate from default/missing evidence.
        self.s['models'].append({'id':'old','role':'teacher','loaded':True,
                                 'native_owner':'OneHost'})
        for changes in ({},{'in_flight':0},{'in_flight':0,'pinned':None},
                        {'in_flight':False,'pinned':False},
                        {'in_flight':1,'pinned':False}):
            with self.subTest(changes=changes):
                m=self.s['models'][-1]
                for key in ('in_flight','pinned'):
                    m.pop(key,None)
                m.update(changes)
                result=plan_load(self.req,self.s)
                self.assertEqual(result['state'],'HOLD_TEACHER_LIMIT')
                self.assertEqual(result['unload_candidates'],[])
    def test_verified_unpinned_idle_teacher_still_only_proposed(self):
        self.s['models'].append({'id':'old','role':'teacher','loaded':True,
                                 'in_flight':0,'pinned':False,
                                 'native_owner':'OneHost'})
        result=plan_load(self.req,self.s)
        self.assertEqual(result['state'],'OWNER_NATIVE_UNLOAD_AND_RETRY_REQUIRED')
        self.assertEqual(result['unload_candidates'],['old'])
        self.assertFalse(result['performed'])
    def test_missing_or_unbounded_cgroup_does_not_admit_new_gpu1_load(self):
        for change in ({'cgroup_max_bytes':None},
                       {'cgroup_max_bytes':'max'},
                       {'cgroup_current_bytes':None},
                       {'cgroup_current_bytes':200*1024**3}):
            with self.subTest(change=change):
                snapshot=dict(self.s);snapshot.update(change)
                self.assertEqual(plan_load(self.req,snapshot)['state'],
                                 'HOLD_CGROUP_RAM_UNVERIFIED')
    def test_host_ram_cannot_override_nearly_full_cgroup(self):
        self.s['cgroup_current_bytes']=self.s['cgroup_max_bytes']-5*1024**3
        result=plan_load(self.req,self.s)
        self.assertEqual(result['state'],'REMOTE_PC_OR_HOLD')
        self.assertEqual(result['reason'],'CGROUP_OR_HOST_RAM_RESERVE')
    def test_native_gpu1_readback_must_match_owner_lease_and_stop(self):
        # Previously the same model_id and running=True on GPU0 incorrectly
        # produced NATIVE_ACTIVATED_VERIFIED even without a GPU1 attestation.
        plan=plan_load(self.req,self.s)
        good={'model_id':'m','running':True,'gpu_id':1,'native_owner':'OneHost',
              'onehost_gpu1_lease':True,'stop_active':False}
        bad=[{'model_id':'m','running':True}, dict(good,gpu_id=0),
             dict(good,gpu_id=True),dict(good,native_owner='unknown'),
             dict(good,onehost_gpu1_lease=False),dict(good,stop_active=None),
             None]
        for evidence in bad:
            with self.subTest(evidence=evidence):
                result=apply_native_plan(plan,native_stop=lambda:False,
                    native_authorize=lambda p:True,native_act=lambda p:{'id':'test'},
                    native_verify=lambda p,r:True,
                    native_readback=lambda p,r:evidence)
                self.assertEqual(result['state'],'HOLD_NATIVE_READBACK_FAILED')
                self.assertEqual(result['performed'],'UNKNOWN')

    def test_native_gpu1_readback_passes_only_with_complete_attestation(self):
        plan=plan_load(self.req,self.s)
        evidence={'model_id':'m','running':True,'gpu_id':1,
                  'native_owner':'OneHost','onehost_gpu1_lease':True,
                  'stop_active':False}
        result=apply_native_plan(plan,native_stop=lambda:False,
            native_authorize=lambda p:True,native_act=lambda p:{'id':'test'},
            native_verify=lambda p,r:True,native_readback=lambda p,r:evidence)
        self.assertEqual(result['state'],'NATIVE_ACTIVATED_VERIFIED')
        self.assertIs(result['performed'],True)

    def test_native_stop_activating_after_readback_blocks_success(self):
        plan=plan_load(self.req,self.s)
        calls={'stop':0}
        def stop():
            calls['stop']+=1
            return calls['stop']>=3
        evidence={'model_id':'m','running':True,'gpu_id':1,
                  'native_owner':'OneHost','onehost_gpu1_lease':True,
                  'stop_active':False}
        result=apply_native_plan(plan,native_stop=stop,
            native_authorize=lambda p:True,native_act=lambda p:{'id':'test'},
            native_verify=lambda p,r:True,native_readback=lambda p,r:evidence)
        self.assertEqual(result['state'],'HOLD_NATIVE_STOP_AFTER_READBACK')
        self.assertEqual(result['performed'],'UNKNOWN')

    def test_native_missing_holds(self):
        p=plan_load(self.req,self.s)
        self.assertEqual(apply_native_plan(p,native_stop=None,native_authorize=None,native_act=None,native_verify=None,native_readback=None)['state'], 'HOLD_NATIVE_CALLBACKS_MISSING')


class TestSafeGPUControl(unittest.TestCase):
    """OneHost source-only admission: never represent a native GPU operation."""
    def setUp(self):
        self.inv={
            'native_verified':True,'stop_active':False,
            'gpus':[
                {'id':0,'native_owner':'OneHost','utilization_pct':78,
                 'vram_free_mib':10000,'temperature_c':46},
                {'id':1,'native_owner':'OneHost','utilization_pct':84,
                 'vram_free_mib':10000,'temperature_c':45}],
            'manual_stop_latched':{'0':False,'1':False},
            'onehost_gpu_lease':{'0':True,'1':True},
            'gpu1_trainer_owner_verified':True,'gpu1_checkpoint_safe':True,
            'cgroup_max_bytes':180*1024**3,
            'cgroup_current_bytes':90*1024**3,'disk_free_bytes':20_000_000_000,
            'pending_useful_work':{'0':2,'1':5}}
    def test_steady_80_to_85_burst_to_95_no_artificial_gpu_work(self):
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'STEADY_80_85_PCT')
        self.inv['gpus'][1]['utilization_pct']=89
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'PEAK_EXISTING_WORK_ONLY')
        self.inv['gpus'][1]['utilization_pct']=95
        r=plan_adaptive_gpu(self.inv,1)
        self.assertEqual(r['state'],'BACKPRESSURE_AT_95_PCT')
        self.assertIs(r['hard_gpu_util_cap_guaranteed'],False)
        self.inv['gpus'][1]['utilization_pct']=77
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'OWNER_QUEUE_TUNING_CANDIDATE')
        self.inv['pending_useful_work']['1']=0
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'IDLE_NO_ARTIFICIAL_GPU_LOAD')
    def test_gpu0_independent_stop_and_resource_fail_closed(self):
        self.inv['manual_stop_latched']['0']=True
        self.assertEqual(plan_adaptive_gpu(self.inv,0)['state'],'HOLD_MANUAL_STOP_LATCHED')
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'STEADY_80_85_PCT')
        self.inv['manual_stop_latched']['0']=False
        self.inv['gpus'][0]['temperature_c']=70
        self.assertEqual(plan_adaptive_gpu(self.inv,0)['state'],
                         'HOLD_GPU_THERMAL_VRAM_DISK_OR_CGROUP_RESERVE')
        self.inv['gpus'][0]['temperature_c']=50
        self.inv['cgroup_current_bytes']=179*1024**3
        self.assertEqual(plan_adaptive_gpu(self.inv,0)['state'],
                         'HOLD_GPU_THERMAL_VRAM_DISK_OR_CGROUP_RESERVE')
    def test_gpu_stop_latches_before_s03_or_checkpoint_and_verifies_stop(self):
        p=plan_gpu_stop(self.inv,0)
        calls=[]
        def cb(name,result):
            return lambda *args: (calls.append(name),result)[1]
        proof={'s03_fsync_verified':True}
        r=execute_gpu_stop(p,authorize=cb('authorize',True),
          latch_stop=cb('latch',True),quiesce=cb('quiesce',True),
          save_progress=cb('save',proof),verify_progress=cb('verify',True),
          stop_owned=cb('stop',True),
          readback=cb('readback',{'gpu_id':0,'native_owner':'OneHost',
                                'owned_process_running':False,'manual_stop_latched':True}))
        self.assertEqual(r['state'],'NATIVE_GPU_STOP_VERIFIED')
        self.assertEqual(calls,['authorize','latch','quiesce','save','verify','stop','readback'])
    def test_gpu1_stop_holds_when_optimizer_offsite_unverified(self):
        p=plan_gpu_stop(self.inv,1)
        called=[]
        r=execute_gpu_stop(p,authorize=lambda x:True,
          latch_stop=lambda x:True,quiesce=lambda x:True,
          save_progress=lambda x:{'checkpoint_sha_verified':True,'optimizer_state_verified':True,
                                   'offsite_restore_verified':False},
          verify_progress=lambda p,r:True,
          stop_owned=lambda *args:called.append('unsafe'),
          readback=lambda *args:called.append('unsafe'))
        self.assertEqual(r['state'],'HOLD_STOP_LATCHED_PERSISTENCE')
        self.assertEqual(called,[])
    def test_manual_stop_blocks_all_auto_restart(self):
        self.inv['unexpected_owner_process_failure']={'0':True,'1':True}
        self.inv['restart_attempts']={'0':0,'1':0}
        self.inv['seconds_since_restart']={'0':75,'1':75}
        self.inv['s03_restorable']=True
        self.inv['checkpoint_optimizer_restorable']=True
        self.inv['offsite_restore_verified']=True
        self.inv['manual_stop_latched']['1']=True
        self.assertEqual(plan_gpu_recovery(self.inv,1)['state'],
                         'HOLD_MANUAL_STOP_REQUIRES_EXPLICIT_RESUME')
        self.inv['manual_stop_latched']['1']=False
        p=plan_gpu_recovery(self.inv,1)
        self.assertEqual(p['state'],'OWNER_NATIVE_RECOVERY_ADMITTED')
        self.inv['restart_attempts']['1']=3
        self.assertEqual(plan_gpu_recovery(self.inv,1)['state'],
                         'HOLD_RESTART_BACKOFF_OR_BUDGET')
    def test_gpu_recovery_two_attempt_limit_and_finite_backoff(self):
        # A NaN cooldown used to bypass elapsed < 60; the former default
        # allowed a third restart despite the owner two-per-hour policy.
        self.inv['unexpected_owner_process_failure']={'1':True}
        self.inv['restart_attempts']={'1':0}
        self.inv['seconds_since_restart']={'1':75}
        self.inv['checkpoint_optimizer_restorable']=True
        self.inv['offsite_restore_verified']=True
        for bad in (float('nan'), float('inf'), float('-inf'), True):
            with self.subTest(elapsed=repr(bad)):
                self.inv['seconds_since_restart']['1']=bad
                self.assertEqual(plan_gpu_recovery(self.inv,1)['state'],
                                 'HOLD_RESTART_BACKOFF_OR_BUDGET')
        self.inv['seconds_since_restart']['1']=75
        self.inv['restart_attempts']['1']=2
        self.assertEqual(plan_gpu_recovery(self.inv,1)['state'],
                         'HOLD_RESTART_BACKOFF_OR_BUDGET')
        self.inv['restart_attempts']['1']=0
        self.assertEqual(plan_gpu_recovery(self.inv,1,max_attempts=3)['state'],
                         'HOLD_RESTART_BACKOFF_OR_BUDGET')
        self.assertEqual(plan_gpu_recovery(self.inv,1,max_attempts=True)['state'],
                         'HOLD_RESTART_BACKOFF_OR_BUDGET')
        self.assertEqual(plan_gpu_recovery(self.inv,1)['state'],
                         'OWNER_NATIVE_RECOVERY_ADMITTED')

    def test_owned_recovery_needs_restored_progress_and_clean_readback(self):
        self.inv['unexpected_owner_process_failure']={'0':True,'1':True}
        self.inv['restart_attempts']={'0':0,'1':0}
        self.inv['seconds_since_restart']={'0':75,'1':75}
        self.inv['checkpoint_optimizer_restorable']=True
        self.inv['offsite_restore_verified']=True
        p=plan_gpu_recovery(self.inv,1)
        events=[]
        def cb(name,value):
            return lambda *args:(events.append(name),value)[1]
        r=execute_gpu_recovery(p,authorize=cb('auth',True),
          stop_state=cb('stopped',False),restore=cb('restore',True),
          start_existing=cb('start',True),
          readback=cb('readback',{'gpu_id':1,'native_owner':'OneHost',
                                 'owned_process_running':True,'manual_stop_latched':False,
                                 'onehost_gpu_lease':True,'stop_active':False,
                                 'pid':123,'start_ticks':4567,
                                 'heartbeat_fresh_after_restart':True,
                                 'new_successful_optimizer_updates_after_restart':1}))
        self.assertEqual(r['state'],'NATIVE_OWNER_PROCESS_RECOVERED')
        self.assertEqual(r['pid'],123)
        self.assertEqual(events,['auth','stopped','restore','stopped','start','readback','stopped'])

    def test_recovered_running_flag_not_progress_and_stale_pid_not_proof(self):
        self.inv['unexpected_owner_process_failure']={'1':True}
        self.inv['restart_attempts']={'1':0}
        self.inv['seconds_since_restart']={'1':75}
        self.inv['checkpoint_optimizer_restorable']=True
        self.inv['offsite_restore_verified']=True
        plan=plan_gpu_recovery(self.inv,1)
        good={'gpu_id':1,'native_owner':'OneHost','owned_process_running':True,
              'manual_stop_latched':False,'onehost_gpu_lease':True,
              'stop_active':False,'pid':123,'start_ticks':4567,
              'heartbeat_fresh_after_restart':True,
              'new_successful_optimizer_updates_after_restart':1}
        cases=[
            (dict(good,pid=0),'HOLD_RECOVERY_READBACK'),
            (dict(good,pid=True),'HOLD_RECOVERY_READBACK'),
            (dict(good,start_ticks='4567'),'HOLD_RECOVERY_READBACK'),
            (dict(good,gpu_id=True),'HOLD_RECOVERY_READBACK'),
            (dict(good,heartbeat_fresh_after_restart=False),'HOLD_RECOVERY_READBACK'),
            (dict(good,onehost_gpu_lease=None),'HOLD_RECOVERY_READBACK'),
            (dict(good,stop_active=True),'HOLD_RECOVERY_READBACK'),
            (dict(good,new_successful_optimizer_updates_after_restart=0),
             'HOLD_RECOVERY_NO_NEW_USEFUL_PROGRESS'),
            (dict(good,new_successful_optimizer_updates_after_restart=True),
             'HOLD_RECOVERY_NO_NEW_USEFUL_PROGRESS'),
            (dict(good,new_successful_optimizer_updates_after_restart='1'),
             'HOLD_RECOVERY_NO_NEW_USEFUL_PROGRESS'),
        ]
        for evidence,want in cases:
            with self.subTest(evidence=evidence):
                out=execute_gpu_recovery(plan,authorize=lambda p:True,
                      stop_state=lambda p:False,restore=lambda p:True,
                      start_existing=lambda p:True,readback=lambda p:evidence)
                self.assertEqual(out['state'],want)
                self.assertEqual(out['performed'],'UNKNOWN')
        state={'reads':0}
        def stop_late(p):
            state['reads']+=1
            return state['reads']>=3
        out=execute_gpu_recovery(plan,authorize=lambda p:True,
              stop_state=stop_late,restore=lambda p:True,
              start_existing=lambda p:True,readback=lambda p:good)
        self.assertEqual(out['state'],'HOLD_RECOVERY_STOP_AFTER_READBACK')

    def test_gpu0_recovery_needs_new_completed_job_not_weight_step(self):
        self.inv['unexpected_owner_process_failure']={'0':True}
        self.inv['restart_attempts']={'0':0}
        self.inv['seconds_since_restart']={'0':75}
        self.inv['s03_restorable']=True
        plan=plan_gpu_recovery(self.inv,0)
        evidence={'gpu_id':0,'native_owner':'OneHost','owned_process_running':True,
                  'manual_stop_latched':False,'onehost_gpu_lease':True,
                  'stop_active':False,'pid':88,'start_ticks':999,
                  'heartbeat_fresh_after_restart':True,
                  'new_successful_optimizer_updates_after_restart':1}
        run=lambda:execute_gpu_recovery(plan,authorize=lambda p:True,
                  stop_state=lambda p:False,restore=lambda p:True,
                  start_existing=lambda p:True,readback=lambda p:evidence)
        self.assertEqual(run()['state'],'HOLD_RECOVERY_NO_NEW_USEFUL_PROGRESS')
        evidence['new_completed_job_after_restart']=True
        self.assertEqual(run()['state'],'NATIVE_OWNER_PROCESS_RECOVERED')
    def test_unknown_owner_or_sensors_never_stop_or_restart(self):
        self.inv['gpus'][1]['native_owner']='UNKNOWN'
        self.assertEqual(plan_gpu_stop(self.inv,1)['state'],'HOLD_UNOWNED_GPU_PROCESS')
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],'HOLD_GPU_OWNER_TOPOLOGY')
        self.inv['gpus'][1]['native_owner']='OneHost'
        self.inv['gpus'][1]['utilization_pct']='85'
        self.assertEqual(plan_adaptive_gpu(self.inv,1)['state'],
                         'HOLD_GPU_MEMORY_THERMAL_OR_CGROUP_SENSOR')

if __name__=='__main__':unittest.main()
