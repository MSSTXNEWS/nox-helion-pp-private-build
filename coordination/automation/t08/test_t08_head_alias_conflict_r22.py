"""NOX V16 R22 independent T08 conflicting-head fail-closed regression.
Source-only; temporary mocked Git proofs. NO native/Windows/QA acceptance.
"""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("t08_autofix_closeout_gate.py")
spec=importlib.util.spec_from_file_location("nox_r22_t08",MODULE)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
H="a"*40
X="b"*40

class ContradictingHeads(unittest.TestCase):
    def test_all_filled_aliases_match(self):
        for proof in ({"head":H},{"source_head":H},{"head":H,"source_head":H},
                      {"head_sha":H,"source_head_sha":H}):
            with self.subTest(proof=proof):
                self.assertTrue(gate._consistent_source_heads(proof,H))
    def test_one_matching_alias_must_not_hide_conflict(self):
        for proof in ({"head":H,"source_head":X},
                      {"head":X,"source_head":H},
                      {"head_sha":X,"source_head_sha":H},
                      {"head":H,"head_sha":X},
                      {"head":H,"source_head":None},
                      {"head":H,"source_head":"bogus"}):
            with self.subTest(proof=proof):
                self.assertFalse(gate._consistent_source_heads(proof,H))
    def test_all_absent_or_invalid_fails(self):
        for proof in ({},{'source_head':None},{'head':'short'},None):
            with self.subTest(proof=proof):
                self.assertFalse(gate._consistent_source_heads(proof,H))
    def test_downstream_p0_receipt_conflict_rejected(self):
        self._downstream({'head':H,'source_head':X},{'source_head':H},False)
    def test_downstream_handoff_receipt_conflict_rejected(self):
        self._downstream({'head':H},{'head':H,'source_head':X},False)
    def test_downstream_clean_receipts_pass_source_only(self):
        self._downstream({'head':H,'source_head':H},{'source_head':H},True)
    def test_patch_applied_focused_test_alias_conflict_is_rejected(self):
        self._downstream({'head':H},{'head':H},False, 'PATCH_APPLIED',
                         {'status':'PASS','head':H,'source_head':X})
    def test_patch_applied_missing_focused_test_head_is_rejected(self):
        self._downstream({'head':H},{'head':H},False, 'PATCH_APPLIED',
                         {'status':'PASS'})
    def test_patch_applied_consistent_focused_test_sha_can_pass(self):
        self._downstream({'head':H},{'head':H},True, 'PATCH_APPLIED',
                         {'status':'PASS','head':H,'source_head':H})
    def _downstream(self,p0proof,handoffproof,expected,status='NO_CODE_BLOCKERS',focused=None):
        receipts={'0'*40:p0proof,'1'*40:handoffproof}
        if focused is not None:
            receipts['9'*40]=focused
        journal={}
        for i,doc in enumerate(gate.DOCS):
            sha=str(i+2)*40
            receipts[sha]={'doc':doc,'revision_id':'rev-0001',
                           'incident_id':'ERR-T08-TEST','readback_pass':True}
            journal[doc]={'readback_receipt_blob':sha,'revision_id':'rev-0001',
                          'incident_id':'ERR-T08-TEST'}
        def git(*args):
            if args==('rev-parse','HEAD'):return H.encode()
            raise AssertionError(args)
        p0={'receipt_blob':'0'*40,'status':status}
        if status=='PATCH_APPLIED':
            p0['focused_test_blob']='9'*40
        handoff={'receipt_blob':'1'*40}
        with patch.object(gate,'_root_git',return_value=(Path('.'),git)),patch.object(
                gate,'_actual_json_blob',side_effect=lambda git,sha:receipts[sha]):
            self.assertEqual(gate._verified_downstream({'head':H},p0,handoff,journal),expected)

if __name__=="__main__":
    unittest.main()
