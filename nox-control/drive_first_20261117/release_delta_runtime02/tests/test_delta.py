import copy
import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('delta',HERE/'delta.py');m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)

class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.base=m.read_json(HERE/'BASE_SHA256.json');self.facts=m.read_json(HERE/'DELTA_FACTS.json');self.outcomes=m.read_json(HERE/'NATIVE_OUTCOMES.json');self.release=Path(self.base['source_release_directory'])
    def test_deterministic_no_loss_and_payload_hash(self):
        old,new,block,checks=m.build_candidates(self.release,self.base,self.facts,self.outcomes)
        self.assertEqual(new,m.build_candidates(self.release,self.base,self.facts,self.outcomes)[1])
        plan=json.loads(new[m.PLAN]);claim=plan.pop('payload_sha256_without_self_hash');self.assertEqual(claim,m.sha(m.canonical(plan)))
        self.assertEqual(plan['runtime02_delta']['runtime02']['local_tests']['total'],48)
        self.assertEqual(plan['native_release']['native_canary']['model_requests'],1)
        self.assertEqual(plan['runtime02_delta']['native_outcomes']['source_stage']['receipt']['status'],'SOURCE_INSTALLED_NOT_BOUND')
        self.assertEqual(plan['native_release']['runtime02_source_staging']['previous_outcomes'][0]['receipt']['status'],'HOLD_DIRECTORY_OWNER_OR_MODE')
        latest=plan['runtime02_delta']['latest_native_facts']
        self.assertEqual(latest['read_only_status'],'HOLD_HISTORY_HTTP_OR_JSON')
        self.assertEqual(latest['history_http_diagnostic']['status'],422)
        self.assertTrue(latest['authenticated_login']);self.assertTrue(latest['ui_asset_acceptance_pass'])
        self.assertFalse(latest['native_canary_pass']);self.assertFalse(latest['runtime_bound'])
        self.assertEqual(plan['native_release']['read_only_reconciliation']['previous_outcomes'][0]['receipt']['status'],'HOLD_MAINTENANCE_BUSY')
        self.assertIn('HTTP `422`',block);self.assertIn('HOLD_MAINTENANCE_BUSY',block)
        self.assertTrue(checks['markdown_body_reversible_exact'])
        self.assertTrue(all((self.release/name).read_bytes()==raw for name,raw in old.items()))
    def test_stale_guard_blocks_then_fresh_guard_applies_only_temp_copy(self):
        old,new,_,_=m.build_candidates(self.release,self.base,self.facts,self.outcomes)
        with tempfile.TemporaryDirectory() as td:
            release=Path(td)
            for name,raw in old.items():(release/name).write_bytes(raw)
            guard={'same_drive_ids':True,'all_five_verified':True,'verified_utc':self.base['previous_drive_readback']['verified_utc'],'files':[dict(entry,byte_exact=True,matches_frozen=True) for entry in self.base['files']]}
            with self.assertRaisesRegex(ValueError,'DRIVE_GUARD_STALE_OR_FUTURE'):m.apply_local(release,self.base,self.facts,self.outcomes,guard)
            self.assertTrue(all((release/name).read_bytes()==raw for name,raw in old.items()))
            guard['verified_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            with tempfile.TemporaryDirectory() as output:
                original=m.HERE;m.HERE=Path(output)
                try:result=m.apply_local(release,self.base,self.facts,self.outcomes,guard)
                finally:m.HERE=original
            self.assertEqual(result['status'],'APPLIED_LOCAL_ONLY_NOT_PUBLISHED')
            self.assertTrue(all((release/name).read_bytes()==raw for name,raw in new.items()))
            self.assertTrue(all((Path(result['backup'])/name).read_bytes()==raw for name,raw in old.items()))
    def test_outcome_slots_reject_false_activation_or_replayed_chat(self):
        stage=self.facts['source_stage'];observed={'state':'OBSERVED','run_id':1,'job_id':2,'source_commit':'a'*40,'receipt':{'status':'SOURCE_INSTALLED_NOT_BOUND','bundle_sha256':stage['bundle_sha256'],'directory':stage['directory'],'files':12,'bytes':stage['bytes'],'file_pins':stage['expected_file_pins'],'source_staging_only':True,'runtime_imported':False,'runtime_bound':False,'model_requests':0,'model_downloads':0,'new_services':0,'workers_started':0}}
        self.assertEqual(m.normalize_outcome('source_stage',observed,self.facts)['receipt']['status'],'SOURCE_INSTALLED_NOT_BOUND')
        bad=copy.deepcopy(observed);bad['receipt']['runtime_bound']=True
        with self.assertRaisesRegex(ValueError,'STAGING_SCOPE'):m.normalize_outcome('source_stage',bad,self.facts)
        rec={'state':'OBSERVED','run_id':1,'job_id':2,'source_commit':'a'*40,'receipt':{'status':'HOLD_HISTORY_HTTP_OR_JSON','mode':'reconcile','model_requests':1,'dialogs_created':0,'native_canary_pass':False}}
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_MUST_NOT_GENERATE'):m.normalize_outcome('readonly_reconcile',rec,self.facts)
        old={'state':'OBSERVED','run_id':3,'job_id':4,'source_commit':'b'*40,'receipt':{'status':'HOLD_MAINTENANCE_BUSY','mode':'reconcile','model_requests':0,'dialogs_created':0,'native_canary_pass':False}}
        new=copy.deepcopy(old);new.update(run_id=5,job_id=6);new['receipt'].update(status='HOLD_HISTORY_HTTP_OR_JSON',ui_asset_acceptance_pass=True,authenticated_login=True,history_http_diagnostic={'status':422})
        slots={'schema':'NOX_V24_RUNTIME02_NATIVE_OUTCOMES_V1','readonly_reconcile':old,'source_stage':{'state':'PENDING','receipt':None}}
        m.record_outcome(slots,'readonly_reconcile',new,self.facts)
        self.assertEqual(slots['history'],[{'kind':'readonly_reconcile','outcome':old}])
        frozen=copy.deepcopy(slots);m.record_outcome(slots,'readonly_reconcile',new,self.facts)
        self.assertEqual(slots,frozen)

if __name__=='__main__':unittest.main()
