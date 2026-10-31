"""Independent narrow QA for NOX OIE MEGABLOCK 1. No market data is faked."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.megablock1 import (run_megablock1, verify_megablock1,
                               stable_hash, _similarity)
from engine.integration import run_job
from engine.cli import main
from engine.studio import Server, make_handler
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'catalog/ideas_60.json').read_text('utf-8'))

class MegaBlockOneAcceptance(unittest.TestCase):
    def setUp(self):
        self.report=run_megablock1(DATA,count=3,seed=11)

    def test_three_passports_and_streams(self):
        self.assertEqual(self.report['counts']['proposals'],3)
        self.assertEqual(self.report['counts']['distinct_streams'],3)
    def test_structured_contents(self):
        for p in self.report['passports']:
            self.assertTrue(p['problem_hypothesis'])
            self.assertTrue(p['buyer_hypothesis'])
            self.assertTrue(p['first_five_minutes'])
            self.assertTrue(p['existing_alternative_to_check'])
            self.assertTrue(p['falsification_test'])
    def test_no_commercial_conclusion(self):
        self.assertEqual(self.report['verified_market_cases'],0)
        self.assertEqual(self.report['pilots_started'],0)
        self.assertEqual(self.report['commercial_revenue_verified'],0)
        self.assertEqual(self.report['qa']['owner_grant'],'NOT_PRESENT')
    def test_internal_similarity_is_not_prior_art(self):
        self.assertIn('not_market_prior_art',next(k for k in self.report['passports'][0] if 'nearest' in k))
        self.assertEqual(self.report['passports'][0]['external_demand_evidence'],[])
    def test_receipt_valid(self):
        self.assertTrue(verify_megablock1(self.report,catalog=DATA)['valid'])
    def test_determinism(self):
        self.assertEqual(self.report,run_megablock1(DATA,count=3,seed=11))
    def test_count_limit(self):
        for n in [0,13,True,1.5]:
            with self.assertRaises(ValueError):run_megablock1(DATA,count=n)
    def test_seed_limit(self):
        for n in [-1000001,1000001,False,'11']:
            with self.assertRaises(ValueError):run_megablock1(DATA,seed=n)
    def test_unsafe_theme_length(self):
        with self.assertRaisesRegex(ValueError,'INVALID_THEME'):
            run_megablock1(DATA,theme='x'*241)
    def test_unknown_theme_fails_honestly(self):
        with self.assertRaisesRegex(ValueError,'NO_MATCHING_CURATED_SEEDS'):
            run_megablock1(DATA,theme='Totally_UNRELATED_phrase_z90')
    def test_receipt_detects_malicious_promotion(self):
        altered=copy.deepcopy(self.report)
        altered['passports'][0]['status']='PILOT_APPROVED'
        v=verify_megablock1(altered,catalog=DATA)
        self.assertFalse(v['valid'])
        self.assertTrue(any('PROMOTION' in e for e in v['errors']))
    def test_receipt_detects_changed_prose(self):
        altered=copy.deepcopy(self.report)
        altered['passports'][1]['problem_hypothesis']='NEW PHRASE'
        self.assertIn('PASSPORTS_HASH_MISMATCH',verify_megablock1(altered)['errors'])
    def test_receipt_detects_changed_catalog(self):
        alternate=copy.deepcopy(DATA)
        alternate[0]['name']='Wrong name'
        self.assertIn('CATALOG_CHANGED',verify_megablock1(self.report,alternate)['errors'])
    def test_revenue_fraud(self):
        altered=copy.deepcopy(self.report)
        altered['verified_market_cases']=2
        self.assertIn('UNSUPPORTED_EXTERNAL_SUCCESS',verify_megablock1(altered)['errors'])
    def test_duplicate_candidate(self):
        altered=copy.deepcopy(self.report)
        altered['passports'][1]['idea_id']=altered['passports'][0]['idea_id']
        self.assertIn('DUPLICATE_CANDIDATE',verify_megablock1(altered)['errors'])
    def test_no_false_scoring(self):
        self.assertTrue(all(p['market_demand']=='UNKNOWN' for p in self.report['passports']))
        self.assertTrue(all(p['independent_review']=='NOT_RUN' for p in self.report['passports']))
        self.assertTrue(all(p['decision']=='RESEARCH_REQUIRED' for p in self.report['passports']))
    def test_similarity(self):
        self.assertEqual(_similarity('Family Scam Shield','Family Scam Shield'),1)
        self.assertEqual(_similarity('AAA','BBB'),0)
    def test_bridge_only_preview(self):
        x=run_job({'contract':'nox.oie.job.v1','action':'megablock1.preview','parameters':{'count':2,'seed':4}})
        self.assertTrue(x['ok'])
        self.assertEqual(x['result']['counts']['proposals'],2)
    def test_bridge_prohibited_commands(self):
        for cmd in ['megablock1.deploy','megablock1.pilot.approve','megablock1.pay']:
            self.assertEqual(run_job({'contract':'nox.oie.job.v1','action':cmd})['error'],'ACTION_DENIED')
    def test_save_and_recheck_immutable_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'mb1.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['megablock1','--count','3','--seed','11','--output',str(path)]),0)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['megablock1-verify',str(path)]),0)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['megablock1','--output',str(path)]),2)
    def test_http_megablock1(self):
        server=Server(('127.0.0.1',0),make_handler('unit-test-token'))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f'http://127.0.0.1:{server.server_port}/api/megablock1'
        try:
            with self.assertRaises(HTTPError) as unauthorized:
                urlopen(Request(url,data=b'{}',method='POST'))
            self.assertEqual(unauthorized.exception.code,403)
            body=json.dumps({'count':3,'theme':''}).encode()
            req=Request(url,data=body,method='POST',headers={'X-NOX-OIE-Token':'unit-test-token','Content-Type':'application/json'})
            with urlopen(req) as response:
                result=json.load(response)
            self.assertTrue(result['ok'])
            self.assertEqual(result['result']['counts']['proposals'],3)
            self.assertTrue(verify_megablock1(result['result'],DATA)['valid'])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
