import unittest,tempfile,json
from pathlib import Path
from nox_selfbuilder.release_governor import inspect_release_task,choose_next,source_ready
from nox_selfbuilder.model_admission import model_candidates,p03_review_handoff
from nox_selfbuilder.release_learning import train_advisory
HEAD='f74300d19314b41a20f0c959dc59309f7e93d409'
REG=Path(__file__).resolve().parents[2]/'contracts'/'coding_model_registry_v3.json'

def ticket(n='NOX-1'):
    return dict(task_id=n,owner_id='1',head=HEAD,existing_code_checked=True,critical_sources_complete=True,
                overlapping_owner_paths=False,required_scope_fixed=True,code_preimage_sha='ABSENT',dependency_unblocks=2,blocks_onehost=True,ready_patch_found=True)
class R3Tests(unittest.TestCase):
    def test_single_owner(self):
        a=ticket();a['owner_id']='3';self.assertIn('SINGLE_OWNER_1_REQUIRED',inspect_release_task(a,current_head=HEAD).reasons)
    def test_correct_owner_and_head(self):
        self.assertEqual(inspect_release_task(ticket(),current_head=HEAD).status,'PATCH_CANDIDATE_ALLOWED')
    def test_drift_blocks(self):
        a=ticket();a['head']='0'*40;self.assertEqual(inspect_release_task(a,current_head=HEAD).status,'HOLD')
    def test_missing_source_blocks(self):
        a=ticket();a['critical_sources_complete']=False;self.assertIn('SOURCE_COVERAGE_HOLD',inspect_release_task(a,current_head=HEAD).reasons)
    def test_duplicate_blocks(self):
        self.assertIn('DUPLICATE_TASK_ID',inspect_release_task(ticket(),current_head=HEAD,seen_task_ids=frozenset({'NOX-1'})).reasons)
    def test_unknown_denominator_not_pass(self):
        self.assertEqual(source_ready(mandatory_total=None,source_verified=6,patch_tests_passed=6,integration_receipts=6,windows_runner_ready=True)['status'],'HOLD')
    def test_source_ready_not_windows_acceptance(self):
        x=source_ready(mandatory_total=3,source_verified=3,patch_tests_passed=3,integration_receipts=3,windows_runner_ready=True)
        self.assertEqual(x['status'],'SOURCE_READY');self.assertFalse(x['windows_release'])
    def test_critical_path_over_cosmetic(self):
        a=ticket('CRITICAL');b=ticket('COSMETIC');b['blocks_onehost']=False;b['ready_patch_found']=False
        selected,_=choose_next([b,a],head=HEAD);self.assertEqual(selected['task_id'],'CRITICAL')
    def test_collision_prevents_candidate(self):
        a=ticket();a['overlapping_owner_paths']=True;self.assertIn('OWNER_FILE_COLLISION',inspect_release_task(a,current_head=HEAD).reasons)
    def test_p03_catalog_and_license(self):
        models=model_candidates(REG)
        self.assertTrue(any(x['tag']=='qwen2.5-coder:7b' for x in models))
        self.assertTrue(all(x['download_eligible'] is False and x['manifest_full_digest'] is None for x in models))
        m=next(x for x in models if x['tag']=='qwen2.5-coder:3b')
        self.assertEqual(m['commercial_policy'],'RESEARCH_ONLY_NOT_COMMERCIAL')
    def test_download_requires_verified_full_sha(self):
        with self.assertRaises(ValueError): p03_review_handoff(catalog_path=REG,tag='qwen2.5-coder:7b',attestation={},owner_consent=True)
    def test_research_model_not_admitted(self):
        with self.assertRaises(PermissionError): p03_review_handoff(catalog_path=REG,tag='qwen2.5-coder:3b',attestation={},owner_consent=True)
    def test_model_owner_consent(self):
        with self.assertRaises(PermissionError): p03_review_handoff(catalog_path=REG,tag='qwen2.5-coder:7b',attestation={},owner_consent=False)
    def test_good_attestation_only_handoff(self):
        a=dict(full_manifest_sha256='a'*64,official_manifest_verified=True,license_evidence_verified=True,hardware_preflight_passed=True,reviewer_independent=True,immutable_revision='v1',rights_receipt_id='rights-v1',owner_receipt_id='owner-v1',installed_ram_gb=24)
        result=p03_review_handoff(catalog_path=REG,tag='qwen2.5-coder:7b',attestation=a,owner_consent=True)
        self.assertFalse(result['network_called']);self.assertIn('NOT_DOWNLOADED',result['status'])
    def test_advisory_training_and_holdout(self):
        training=[dict(features=[a,b,c],label=int(2*a+b+c>.8),source_id='train:'+str(i)) for i,(a,b,c) in enumerate([(0,0,0),(1,0,0),(0,1,0),(0,0,1),(.5,.5,.5),(1,1,1),(1,0,.2),(0,.2,0),(1,1,0),(0,0,.5),(0,1,1),(.5,0,0)])]
        hold=[dict(features=[a,b,c],label=int(2*a+b+c>.8),source_id='hold:'+str(i)) for i,(a,b,c) in enumerate([(1,0,.5),(.1,0,.1),(1,1,.1),(.3,.1,.1),(0,.1,.8),(0,.9,.1)])]
        w=train_advisory(training,hold)
        self.assertEqual(w['status'],'SIMULATED_ADVISORY_ONLY');self.assertGreaterEqual(w['holdout_accuracy'],.8)
        self.assertFalse(w['trained_llm_weights'])
    def test_holdout_source_overlap_rejected(self):
        a=dict(features=[0,0,0],label=0,source_id='same')
        with self.assertRaises(ValueError):train_advisory([a]*8,[a]*4)
    def test_existing_seed_is_bit_identical(self):
        import hashlib
        original_sha='b1bc0c27997d76b4c654842101d28738080e8c83d3b077b12585aaa28b500c9f'
        current=Path(__file__).resolve().parents[2]/'assets'/'NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip'
        self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),original_sha)
    def test_no_new_downloader_or_trainer(self):
        code=(Path(__file__).resolve().parents[2]/'src'/'nox_selfbuilder'/'model_admission.py').read_text()
        self.assertNotIn('requests.get(',code);self.assertNotIn('urllib.request',code)
    def test_evolution_selfwrite_requires_governor(self):
        from nox_selfbuilder.evolution import EvolutionWorker
        from test_evolution_worker import Host,job
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()]);h.release_ticket=None
            w=EvolutionWorker(h,workspace=t,idle_seconds=.2)
            r=w.tick()
            self.assertEqual(r.status,'HOLD');self.assertEqual(h.call_count,0)
            self.assertIn('RELEASE_GOVERNOR_NATIVE_CALLBACK_REQUIRED',r.receipt['reason'])
    def test_evolution_bad_owner_fails_without_generation(self):
        from nox_selfbuilder.evolution import EvolutionWorker
        from test_evolution_worker import Host,job
        with tempfile.TemporaryDirectory() as t:
            h=Host([job()]);h.release_ticket=lambda task:dict(ticket(),task_id=task['task_id'],owner_id='3')
            w=EvolutionWorker(h,workspace=t,idle_seconds=.2)
            r=w.tick()
            self.assertEqual(r.status,'HOLD');self.assertEqual(h.call_count,0)
            self.assertIn('SINGLE_OWNER_1_REQUIRED',r.receipt['reason'])
    def test_governance_one_person(self):
        j=json.loads((Path(__file__).resolve().parents[2]/'contracts'/'one_owner_release_policy.json').read_text())
        self.assertEqual(j['developer_count'],1);self.assertEqual(j['sole_integrator'],'1');self.assertEqual(j['independent_release_acceptor'],'2')
