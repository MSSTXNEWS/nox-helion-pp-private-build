import json, pathlib, sys, tempfile, unittest
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pc'));sys.path.insert(0,str(ROOT/'nox'))
from download_models import manifest,disk_admit,digest_file,existing_status,fetch_one
from resource_brain import plan_load,apply_native_plan

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
        self.s={'models':[{'id':'m','sha_verified':True,'approved_license':True,'role':'teacher','loaded':False}],
                'gpus':[{'id':0,'vram_free_mib':900,'protected_student':True},{'id':1,'vram_free_mib':30000}],
                'stop_active':False,'checkpoint_pending':False,'optimizer_step_active':False,
                'disk_free_bytes':80_000_000_000,'ram_free_mib':30000}
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
    def test_disk_below_20gb_moves_cold(self):
        self.s['disk_free_bytes']=15_000_000_000
        self.assertEqual(plan_load(self.req,self.s)['state'],'REMOTE_PC_COLD_OR_DRIVE_ONLY')
    def test_two_vram_not_sum(self):
        self.s['gpus'][1]['vram_free_mib']=12000
        self.assertEqual(plan_load(self.req,self.s)['state'],'REMOTE_PC_OR_HOLD')
    def test_diffusion_runtime_requires_adapter(self):
        self.req['role']='video';self.s['models'][0]['runtime']='none'
        self.assertEqual(plan_load(self.req,self.s)['state'],'HOLD_DIFFUSION_RUNTIME_NOT_VERIFIED')
    def test_native_missing_holds(self):
        p=plan_load(self.req,self.s)
        self.assertEqual(apply_native_plan(p,native_stop=None,native_authorize=None,native_act=None,native_verify=None,native_readback=None)['state'], 'HOLD_NATIVE_CALLBACKS_MISSING')

if __name__=='__main__':unittest.main()
