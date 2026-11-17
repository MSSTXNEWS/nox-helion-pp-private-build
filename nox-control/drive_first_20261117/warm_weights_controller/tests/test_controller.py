import hashlib
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from nox_warm import Controller, Snapshot, read_snapshot, load_manifest, Hold, AtomicCache, Paused, warm_pages

MiB=1024*1024


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.calls=[];self.receipts={};self.fail=None
        self.body=b'nox-weight-fixture\n'*1024
        self.sha=hashlib.sha256(self.body).hexdigest();self.source=self.r/'source';self.source.write_bytes(self.body)
        def group(g,mode):return {'id':g,'remote_path':g+'.bin','cache_path':g+'.bin','size_bytes':len(self.body),'sha256':self.sha,'priority':1,'warm_bytes':4096,'ram_load_bytes':MiB,'gpu_load_bytes':MiB,'tier':'warmSSD','modes':[mode],'startup_preload':mode=='WORK','protected':False,'may_unload':True}
        self.m={'schema':'NOX_WARM_MANIFEST_V1','source_policy':'DRIVE_FIRST','startup_storage':'warmSSD','allow_ssd_cache':True,'groups':[group('work','WORK'),group('train','TRAIN')],'mode_groups':{'WORK':['work'],'TRAIN':['train']},'budgets':{'chat_reserve_bytes':MiB,'train_reserve_bytes':MiB,'system_reserve_bytes':MiB,'ssd_reserve_bytes':MiB,'startup_transfer_bytes':MiB,'startup_warm_bytes':8192,'startup_max_groups':1}}
        self.s=Snapshot(10*MiB,100*MiB,100*MiB,90*MiB,2*MiB,5*MiB,5*MiB,0,0)
        self.c=self.make()
        for g in self.m['groups']:self.c.cache.stage_local(g,self.source)
        self.c.adopt_verified_state('WORK',['work'],{'verified':True,'source':'isolated-fixture','observed_at':1})

    def tearDown(self):self.tmp.cleanup()

    def hook(self,name,payload):
        if name=='inspect_operation':
            old=self.receipts.get(payload['operation_key'])
            return {'state':'DONE','receipt':old} if old else {'state':'NOT_STARTED'}
        self.calls.append(name)
        if name==self.fail:raise TimeoutError('fixture interrupted before effect')
        out={'ok':True,'operation_key':payload['operation_key']}
        if name=='checkpoint':
            path=self.r/'checkpoint.json';path.write_text(json.dumps({'fixture_only':True,'state':42}))
            out['checkpoint']={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'durable_verified':True,'components':['model','optimizer','scaler','rng','data_cursor']}
        self.receipts[payload['operation_key']]=out;return out

    def make(self):
        return Controller(self.m,self.r/'cache',self.r/'journal.json',snapshot=lambda:self.s,hooks=self.hook,
            host_resource_admission=lambda x:{'granted':True,'lease_id':'fixture-lease','scope':'host','fencing_token':1},
            host_release_resource=lambda x:{'released':True},owner_should_pause=lambda:False)

    def test_cgroup_accounts_shmem_and_does_not_promote_inactive_file_to_free(self):
        cg=self.r/'cg';cg.mkdir()
        for n,t in {'memory.current':'193361956864','memory.max':'194065203200','memory.stat':'anon 2324660224\nfile 190119346176\nshmem 75403325440\nfile_mapped 121937813504\ninactive_file 92654321664\nactive_file 22061699072','memory.pressure':'some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0'}.items():(cg/n).write_text(t)
        mi=self.r/'meminfo';mi.write_text('MemAvailable: 999999999 kB\n')
        s=read_snapshot(cg,mi)
        self.assertEqual(s.available,703246336);self.assertEqual(s.shmem,75403325440)
        self.assertEqual(s.reclaimable_candidate_upper_bound,92654321664);self.assertEqual(s.reclaimable_guaranteed,0)
        (cg/'memory.max').unlink()
        with self.assertRaises(Hold):read_snapshot(cg,mi)

    def test_manifest_pins_and_path_escape(self):
        p=self.r/'manifest.json';p.write_text(json.dumps(self.m));self.assertEqual(len(load_manifest(p)['groups']),2)
        self.m['groups'][0]['cache_path']='../outside';p.write_text(json.dumps(self.m))
        with self.assertRaises(ValueError):load_manifest(p)
        with self.assertRaises(ValueError):self.c.cache.path('../outside')

    def test_atomic_paused_copy_resume_and_sha_failure(self):
        g=dict(self.m['groups'][0],cache_path='new.bin');n=[0]
        def pause():n[0]+=1;return n[0]>2
        with self.assertRaises(Paused):self.c.cache.stage_local(g,self.source,chunk_bytes=4096,should_pause=pause)
        self.assertFalse((self.r/'cache/new.bin').exists());self.assertEqual((self.r/'cache/new.bin.part').stat().st_size,8192)
        self.c.cache.stage_local(g,self.source);self.assertTrue(self.c.cache.verify(g,allow_hash=False))
        bad=dict(g,cache_path='bad.bin',sha256='0'*64)
        with self.assertRaises(ValueError):self.c.cache.stage_local(bad,self.source)
        self.assertFalse((self.r/'cache/bad.bin').exists());self.assertTrue((self.r/'cache/bad.bin.part').exists())

    def test_low_headroom_holds_startup_no_download_or_gpu_action(self):
        self.s=Snapshot(1000*MiB,1001*MiB,100*MiB,MiB,600*MiB,700*MiB,300*MiB,0,0)
        d=[];self.c.download_verified=lambda *a:d.append(a)
        result=self.c.startup(apply=True)
        self.assertEqual(result['selected'][0]['status'],'HOLD');self.assertEqual(d,[]);self.assertEqual(self.calls,[])
        self.assertFalse(result['gpu_loaded']);self.assertFalse(result['all_drive_preloaded'])

    def test_mmap_warm_is_bounded_hint_and_cooperative(self):
        allowed=[];x=warm_pages(self.source,8193,admission=lambda n:allowed.append(n),chunk_bytes=4096)
        self.assertEqual(x['touched_bytes'],8193);self.assertEqual(sum(allowed),8193);self.assertFalse(x['resident_guaranteed'])
        y=warm_pages(self.source,8193,admission=lambda n:None,should_pause=lambda:True)
        self.assertEqual(y['status'],'WARM_PAUSED');self.assertEqual(y['touched_bytes'],0)

    def test_work_train_pause_resume_real_checkpoint_and_idempotency(self):
        out=self.c.transition('TRAIN','t1',apply=True);self.assertEqual(out['status'],'DONE')
        before=len(self.calls);self.c.transition('TRAIN','t1',apply=True);self.assertEqual(len(self.calls),before)
        out=self.c.transition('PAUSED_TRAIN','t2',apply=True);self.assertEqual(out['memory_reclaimed_by_pause'],0)
        self.assertEqual(self.c.data['loaded'],['train']);self.assertTrue(Path(self.c.data['training_checkpoint']['path']).is_file())
        resumed=self.make();self.assertEqual(resumed.data['mode'],'PAUSED_TRAIN')
        self.assertEqual(resumed.transition('TRAIN','t3',apply=True)['status'],'DONE')

    def test_uncertain_callback_requires_reconcile_then_resumes_without_duplicate_unload(self):
        self.fail='load'
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','broken',apply=True)
        self.assertEqual(self.c.data['mode'],'HOLD');r=self.c.rollback_plan();self.assertEqual(r['status'],'RECONCILE_REQUIRED')
        self.assertFalse(r['automatic_reload_performed']);self.assertEqual(r['restore_groups'],['work'])
        self.fail=None;c=self.make();out=c.transition('TRAIN','broken',apply=True)
        self.assertEqual(out['status'],'DONE');self.assertEqual(self.calls.count('unload'),1)

    def test_protected_group_and_health_failure_never_fake_ready(self):
        self.m['groups'][0].update(protected=True,may_unload=False)
        with self.assertRaisesRegex(Hold,'PROTECTED_RUNTIME_GROUP'):self.c.transition('TRAIN','protect',apply=True)
        self.assertEqual(self.calls,[]);self.assertTrue(self.c.cache.verify(self.m['groups'][0]))
        self.m['groups'][0]['may_unload']=True
        p=self.r/'contradiction.json';p.write_text(json.dumps(self.m))
        with self.assertRaisesRegex(ValueError,'PROTECTED_UNLOAD_CONTRADICTION'):load_manifest(p)
        with self.assertRaisesRegex(Hold,'PROTECTED_RUNTIME_GROUP'):self.c.transition('TRAIN','stillprotect',apply=True)
        self.assertEqual(self.calls,[])
        self.m['groups'][0].update(protected=False,role='chat')
        with self.assertRaisesRegex(Hold,'PROTECTED_RUNTIME_GROUP'):self.c.transition('TRAIN','hardprotect',apply=True)
        self.m['groups'][0].pop('role');self.fail='health'
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','healthfail',apply=True)
        self.assertEqual(self.c.data['mode'],'HOLD');self.assertTrue(self.c.data['transition']['rollback_required'])

    def test_reconciled_rollback_executes_reverse_hooks_and_restores_work(self):
        self.fail='health'
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','failed',apply=True)
        with self.assertRaisesRegex(Hold,'PENDING_EFFECTS_NOT_SETTLED'):
            self.c.adopt_verified_state('TRAIN',['train'],{'verified':True,'source':'fixture-readback','observed_at':2})
        self.c.adopt_verified_state('TRAIN',['train'],{'verified':True,'source':'fixture-readback','observed_at':2,
            'settled_transition_id':'failed','pending_operations_settled':True,
            'resource_lease_settled':True,'settled_lease_id':'fixture-lease','settled_fencing_token':1})
        self.fail=None
        out=self.c.transition('WORK','rollback-failed',apply=True)
        self.assertEqual(out['status'],'DONE');self.assertEqual(self.c.data['mode'],'WORK')
        self.assertEqual(self.c.data['loaded'],['work']);self.assertTrue((self.r/'checkpoint.json').is_file())

    def test_drive_cache_hit_contract_and_startup_selected_cap(self):
        g=self.m['groups'][0];target=self.c.cache.path(g['cache_path'])
        target.unlink();target.with_name(target.name+'.verified.json').unlink();calls=[]
        def download(remote,cache,sha,size,*,should_pause):
            calls.append(remote);self.c.cache.stage_local(g,self.source,should_pause=should_pause)
            return {'status':'cache_hit_verified','sha256':sha,'size_bytes':size}
        self.c.download_verified=download
        result=self.c.startup(apply=True)
        self.assertEqual(calls,['work.bin']);self.assertEqual(len(result['selected']),1)
        self.assertEqual(result['selected'][0]['status'],'CACHED_VERIFIED_RAM_HINT')

    def test_cache_startup_and_local_apply_require_owner_and_host_lease(self):
        downloads=[];self.c.download_verified=lambda *a,**k:downloads.append(a)
        self.c.owner_should_pause=None
        result=self.c.startup(apply=True)
        self.assertEqual(result['selected'][0]['reason'],'CACHE_HOST_LEASE_OR_OWNER_ACTIVITY_UNBOUND')
        self.assertNotIn('warming',result['selected'][0])
        with self.assertRaisesRegex(Hold,'CACHE_HOST_LEASE_OR_OWNER_ACTIVITY_UNBOUND'):
            self.c.cache_local('work',self.source,apply=True)
        self.c.owner_should_pause=lambda:True
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['reason'],'OWNER_ACTIVE_OR_PAUSE_REQUESTED')
        self.c.owner_should_pause=lambda:False;self.c.host_resource_admission=None
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['reason'],'CACHE_HOST_LEASE_OR_OWNER_ACTIVITY_UNBOUND')
        self.assertEqual(downloads,[]);self.assertEqual(self.calls,[])

    def test_local_pause_callback_never_overrides_owner_or_replaces_missing_owner(self):
        self.c.owner_should_pause=lambda:True
        result=self.c.startup(apply=True,should_pause=lambda:False)
        self.assertEqual(result['selected'][0]['reason'],'OWNER_ACTIVE_OR_PAUSE_REQUESTED')
        self.assertNotIn('warming',result['selected'][0])
        with self.assertRaisesRegex(Hold,'OWNER_ACTIVE_OR_PAUSE_REQUESTED'):
            self.c.cache_local('work',self.source,apply=True,should_pause=lambda:False)
        self.c.owner_should_pause=None
        with self.assertRaisesRegex(Hold,'UNBOUND'):self.c._cache_guard(lambda:False)
        self.c.owner_should_pause=lambda:None
        with self.assertRaisesRegex(Hold,'OWNER_ACTIVITY_UNVERIFIED'):self.c._cache_guard(lambda:False)
        active=[False];self.c.owner_should_pause=lambda:active[0]
        callback=self.c._cache_guard(lambda:False);self.assertFalse(callback())
        active[0]=True;self.assertTrue(callback())
        active[0]=False
        with self.assertRaisesRegex(Hold,'PAUSE_REQUESTED'):self.c._cache_guard(lambda:True)
        with self.assertRaisesRegex(Hold,'LOCAL_PAUSE_STATE_UNVERIFIED'):self.c._cache_guard(lambda:None)

    def test_work_return_to_train_restores_checkpoint_and_same_mode_does_not_recheckpoint(self):
        self.c.transition('TRAIN','enter-train',apply=True)
        self.c.transition('WORK','back-to-work',apply=True)
        checkpoint=dict(self.c.data['training_checkpoint'])
        self.c.transition('TRAIN','return-train',apply=True)
        resume=self.c.data['operations']['return-train:resume']['payload']
        self.assertTrue(resume['resume_from_verified_checkpoint'])
        self.assertEqual(resume['checkpoint'],checkpoint)
        before=len(self.calls)
        self.c.transition('TRAIN','same-train',apply=True)
        self.assertEqual(self.calls[before:],['health'])
        self.assertEqual(self.calls.count('checkpoint'),1)
        with self.assertRaisesRegex(Hold,'STALE_TRANSITION_ID_REUSE'):
            self.c.transition('TRAIN','enter-train',apply=True)

    def test_changed_checkpoint_never_reaches_trainer_resume(self):
        self.c.transition('TRAIN','enter-train',apply=True)
        self.c.transition('WORK','back-to-work',apply=True)
        Path(self.c.data['training_checkpoint']['path']).write_text('corrupted fixture')
        before=self.calls.count('resume')
        with self.assertRaisesRegex(Hold,'CHECKPOINT_READBACK_FAILED'):
            self.c.transition('TRAIN','return-corrupt',apply=True)
        self.assertEqual(self.calls.count('resume'),before)
        self.assertEqual(self.c.data['mode'],'HOLD')

    def test_pause_retry_reuses_verified_checkpoint_without_duplicate_checkpoint(self):
        self.c.transition('TRAIN','enter',apply=True);self.fail='pause'
        with self.assertRaises(TimeoutError):self.c.transition('WORK','paused-ack',apply=True)
        checkpoint=dict(self.c.data['training_checkpoint'])
        self.fail=None
        self.c.transition('WORK','paused-ack',apply=True)
        self.assertEqual(self.calls.count('checkpoint'),1)
        self.assertEqual(self.c.data['training_checkpoint'],checkpoint)

    def test_unknown_release_blocks_retry_until_exact_lease_settled(self):
        releases=[]
        def release(lease):
            releases.append(lease);raise TimeoutError('lost release ACK')
        self.c.host_release_resource=release
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','lost-release',apply=True)
        self.assertEqual(self.c.data['transition']['resource_lease_state'],'UNKNOWN')
        before=len(self.calls)
        self.c.host_release_resource=lambda lease:{'released':True}
        with self.assertRaisesRegex(Hold,'LEASE_RECONCILE_REQUIRED'):
            self.c.transition('TRAIN','lost-release',apply=True)
        self.assertEqual(len(self.calls),before);self.assertEqual(len(releases),1)
        receipt={'verified':True,'source':'host-fixture','observed_at':2,
                 'settled_transition_id':'lost-release','pending_operations_settled':True}
        with self.assertRaisesRegex(Hold,'RESOURCE_LEASE_NOT_SETTLED'):
            self.c.adopt_verified_state('TRAIN',['train'],receipt)
        receipt.update(resource_lease_settled=True,settled_lease_id='fixture-lease',settled_fencing_token=1)
        self.c.adopt_verified_state('TRAIN',['train'],receipt)
        self.assertEqual(self.c.transition('WORK','safe-next',apply=True)['status'],'DONE')

    def test_unknown_admission_is_journaled_before_callback_and_not_retried_blindly(self):
        admissions=[]
        def admission(request):
            admissions.append(request)
            recorded=json.loads(self.c.journal_path.read_text())['transition']
            self.assertEqual(recorded['resource_lease_state'],'ADMISSION_PENDING')
            raise TimeoutError('lost admission ACK')
        self.c.host_resource_admission=admission
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','lost-admission',apply=True)
        self.assertEqual(self.calls,[])
        with self.assertRaisesRegex(Hold,'LEASE_RECONCILE_REQUIRED'):
            self.c.transition('TRAIN','lost-admission',apply=True)
        self.assertEqual(len(admissions),1)
        self.c.adopt_verified_state('WORK',['work'],{'verified':True,'source':'host-fixture','observed_at':3,
            'settled_transition_id':'lost-admission','pending_operations_settled':True,
            'resource_lease_settled':True,'settled_resource_request_id':'lost-admission'})
        self.assertEqual(self.c.data['mode'],'WORK')

    def test_registry_retains_handle_without_confirmed_release_and_prevents_overwrite(self):
        class OldUncertainHandle:
            def __init__(self):self.closed=False
            def release_identity(self):return {'ram_handle_id':'old-handle','ram_lease_identity_sha256':'f'*64,'ram_fencing_token':7}
            def close(self):
                if not self.closed:
                    self.closed=True;raise TimeoutError('release unknown')
                return None
        handle=OldUncertainHandle();self.c._ram_handles['work']=handle
        self.c.adopt_verified_state('WORK',[],{'verified':True,'source':'fixture','observed_at':2})
        proof={'group':'work','verified':True,'loader_refs_released':True,**handle.release_identity()}
        with self.assertRaises(TimeoutError):self.c.release_owned_ram('work',proof)
        with self.assertRaisesRegex(Hold,'RAM_RELEASE_UNCONFIRMED'):self.c.release_owned_ram('work',proof)
        self.assertIs(self.c._ram_handles['work'],handle)
        self.m.update(startup_storage='ownedRAM',allow_ssd_cache=False)
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['reason'],'OWNED_RAM_HANDLE_REQUIRES_RECONCILE')

    def test_aborted_ram_release_reconciliation_requires_matching_lease_and_fence(self):
        self.c.data['ram_release_reconcile']={'work':{'lease_id':'held-ram','fencing_token':7}}
        with self.assertRaisesRegex(Hold,'READBACK_UNVERIFIED'):
            self.c.reconcile_owned_ram_release('work',{'verified':True,'lease_id':'wrong','fencing_token':7,'released':True})
        with self.assertRaisesRegex(Hold,'LEASE_STILL_HELD'):
            self.c.reconcile_owned_ram_release('work',{'verified':True,'lease_id':'held-ram','fencing_token':7,'released':False})
        self.assertIn('work',self.c.data['ram_release_reconcile'])
        self.c.reconcile_owned_ram_release('work',{'verified':True,'lease_id':'held-ram','fencing_token':7,'released':True})
        self.assertNotIn('work',self.c.data['ram_release_reconcile'])

    def test_drive_first_real_sealed_memfd_retained_then_released_by_verified_owner(self):
        self.m.update(startup_storage='ownedRAM',allow_ssd_cache=False)
        self.m['budgets']['startup_ram_bytes']=80*MiB
        self.c.adopt_verified_state('WORK',[],{'verified':True,'source':'fixture-readback','observed_at':2})
        downloads=[];reservations=[];releases=[]
        def reserve(n):
            reservations.append(n);return {'granted':True,'scope':'host','lease_id':'ram-fixture','fencing_token':2}
        def release(r):releases.append(r['lease_id']);return {'released':True}
        self.c.host_reserve_ram=reserve;self.c.host_release_ram=release
        class Handle:
            def __init__(obj,fd,sha,size,lease,releaser):
                obj.fd=fd;obj.sha256=sha;obj.size_bytes=size;obj.lease=lease;obj.releaser=releaser
            def fileno(obj):return obj.fd
            def release_identity(obj):return {'ram_handle_id':'fixture-owned-'+str(obj.fd),'ram_lease_identity_sha256':'f'*64,'ram_fencing_token':2}
            def close(obj):
                os.close(obj.fd);obj.fd=-1
                result=obj.releaser(obj.lease)
                if result.get('released') is not True:raise Hold('RAM_RELEASE_UNCONFIRMED')
                return {'closed':True,'lease_released':True}
        def download(remote,sha,size,*,reserve_ram,release_ram,should_pause):
            self.assertFalse(should_pause());downloads.append(remote)
            lease=reserve_ram(size+64*MiB)
            fd=os.memfd_create('nox-drive-local-fixture',os.MFD_ALLOW_SEALING|os.MFD_CLOEXEC)
            self.assertEqual(os.write(fd,self.body),size)
            fcntl.fcntl(fd,getattr(fcntl,'F_ADD_SEALS',1033),15)
            return Handle(fd,sha,size,lease,release_ram)
        self.c.download_memfd_verified=download
        result=self.c.startup(apply=True)
        self.assertEqual(result['selected'][0]['reason'],'PERSISTENT_RAM_HOST_BINDING_REQUIRED')
        self.assertEqual(downloads,[])
        self.c.persistent_host=True
        self.c.owner_should_pause=lambda:True
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['reason'],'OWNER_ACTIVE_OR_PAUSE_REQUESTED')
        self.assertEqual(downloads,[])
        self.c.owner_should_pause=lambda:False
        result=self.c.startup(apply=True)
        self.assertEqual(result['selected'][0]['status'],'OWNED_RAM_VERIFIED_NOT_MODEL')
        self.assertFalse(result['selected'][0]['model_loaded']);self.assertFalse(result['gpu_loaded'])
        self.assertEqual(reservations,[len(self.body)+64*MiB]);self.assertEqual(releases,[])
        handle=self.c.ram_handle_for_loader('work');self.assertEqual(os.pread(handle.fileno(),len(self.body),0),self.body)
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['status'],'OWNED_RAM_ALREADY_VERIFIED')
        self.assertEqual(downloads,['work.bin'])
        with self.assertRaisesRegex(Hold,'RAM_LOADER_REFERENCES_UNCONFIRMED'):
            self.c.release_owned_ram('work',{'group':'work','verified':True})
        self.m['groups'][0]['protected']=True
        with self.assertRaisesRegex(Hold,'PROTECTED_RUNTIME_GROUP'):
            self.c.release_owned_ram('work',{'group':'work','verified':True,'loader_refs_released':True})
        self.assertEqual(releases,[]);self.m['groups'][0]['protected']=False
        with self.assertRaisesRegex(Hold,'RAM_RELEASE_PROOF_IDENTITY_MISMATCH'):
            self.c.release_owned_ram('work',{'group':'work','verified':True,'loader_refs_released':True})
        self.assertEqual(self.c.release_owned_ram('work',{'group':'work','verified':True,'loader_refs_released':True,**handle.release_identity()})['status'],'OWNED_RAM_CLOSED')
        self.assertEqual(releases,['ram-fixture'])
        self.body=b'X'*len(self.body)
        self.assertEqual(self.c.startup(apply=True)['selected'][0]['reason'],'RAM_SHA_READBACK_FAILED')
        self.assertEqual(releases,['ram-fixture','ram-fixture']);self.assertEqual(self.c._ram_handles,{})

if __name__=='__main__':unittest.main()
