import json
import tempfile
import unittest
from pathlib import Path
from nox_selfbuilder.builder import SelfBuilder, SelfBuilderHold
from nox_selfbuilder.seed import attest_seed
from nox_selfbuilder.learning import make_learning_record,make_forge_handoff

ROOT=Path(__file__).resolve().parents[2]
HEAD='f74300d19314b41a20f0c959dc59309f7e93d409'
SOURCE='NOX-V16-REQUIREMENT-R1-DISC'

class Tests(unittest.TestCase):
    def adapter(self,*,authorise=True,model=None,evidence=None):
        if model is None:
            model={"module_path":"extensions/health_status/view.py",
                   "code":"def status():\n    return 'ready'\n",
                   "tests":"import unittest\nclass Test(unittest.TestCase):\n    def test_true(self):\n        self.assertTrue(True)\n",
                   "rationale":"Adds a bounded view with a real status method",
                   "sources":[SOURCE]}
        if evidence is None:
            evidence=[{"source_id":SOURCE,"text":"Existing source verified and owner approved", "verified":True}]
        return SelfBuilder(recall=lambda *a: evidence,generate=lambda *a: json.dumps(model),native_authorize=lambda *a: authorise)
    def test_seed_sha_manifest(self):
        r=attest_seed(ROOT/'assets'/'NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip')
        self.assertEqual(r['parameters'],72422)
        self.assertFalse(r['release_accepted'])
        self.assertEqual(r['member_count'],16)
    def test_proposal_in_staging(self):
        with tempfile.TemporaryDirectory() as t:
            r=self.adapter().propose(session=object(),task='Create a real status command inside the existing NOX UI',source_head=HEAD,workspace=t)
            self.assertFalse(r['integrated'])
            self.assertTrue((Path(t)/r['run_id']/'candidate.py').is_file())
            self.assertEqual(len(list(Path(t).iterdir())),1)
            lesson=make_learning_record(run_id=r['run_id'],receipt=r,outcome='ACCEPTED',reviewer_source_id='owner-review-1',native_approve=True)
            self.assertFalse(lesson['S03_WRITE_PERFORMED'])
    def test_denied_native_consent(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SelfBuilderHold):
                self.adapter(authorise=False).propose(session=object(),task='Create a real status command inside the existing NOX UI',source_head=HEAD,workspace=t)
            self.assertEqual(list(Path(t).iterdir()),[])
    def test_no_verified_recall(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SelfBuilderHold):
                self.adapter(evidence=[{"source_id":SOURCE,"text":"bad","verified":False}]).propose(session=object(),task='Create a real status command inside the existing NOX UI',source_head=HEAD,workspace=t)
    def test_no_path_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            model={"module_path":"../../run.py","code":"def go():\n return 1\n","tests":"def test():\n assert 1\n","rationale":"Potentially harmful attempted path traversal", "sources":[SOURCE]}
            with self.assertRaises(SelfBuilderHold):
                self.adapter(model=model).propose(session=object(),task='Create a real status command inside the existing NOX UI',source_head=HEAD,workspace=t)
            self.assertEqual(list(Path(t).iterdir()),[])
    def test_no_ungrounded_refs(self):
        with tempfile.TemporaryDirectory() as t:
            model={"module_path":"extensions/test_module/view.py","code":"def go():\n return 1\n","tests":"def test():\n assert 1\n","rationale":"This response contains unrelated evidence", "sources":["UNKNOWN"]}
            with self.assertRaises(SelfBuilderHold):
                self.adapter(model=model).propose(session=object(),task='Create a real status command inside the existing NOX UI',source_head=HEAD,workspace=t)
    def test_forge_fail_closed(self):
        with self.assertRaises(PermissionError):
            make_forge_handoff(dataset_manifest_sha256='0'*64,base_model_snapshot_sha256='1'*64,rights_receipt_id='',approved=False,gpu_preflight={'status':'HARDWARE_READY_ONLY'})
        with self.assertRaises(ValueError):
            make_forge_handoff(dataset_manifest_sha256='0'*64,base_model_snapshot_sha256='1'*64,rights_receipt_id='owner',approved=True,gpu_preflight={'status':'HOLD'})
    def test_no_learning_without_owner(self):
        with self.assertRaises(PermissionError):
            make_learning_record(run_id='SB-0',receipt={'status':'SOURCE_CANDIDATE_REVIEW_REQUIRED_NOT_EXECUTED'},outcome='ACCEPTED',reviewer_source_id='x',native_approve=False)
    def test_model_registry_not_downloadable(self):
        j=json.loads((ROOT/'contracts'/'model_candidates.json').read_text())
        self.assertEqual(j['target_hardware']['installed_ram_gb'],24)
        self.assertTrue(all(x['download_eligible'] is False for x in j['external_models']))

if __name__=='__main__':unittest.main()
