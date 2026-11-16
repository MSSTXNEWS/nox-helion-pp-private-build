"""Source-only safety regression for existing NOX V28 Teacher Arena.

No native queue, S03 connection, GPU, model or trainer is used.
"""
import hashlib, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from nox_adviser_arena_v28 import evaluate_teacher_arena

RECEIPT = 'e'*64
HARNESS = 'c'*64

def candidate(uri='https://example.org/sources/teacher1'):
    text='Verified independent evidence; no private source data.'
    return {'teacher_id':'teacher1','origin':'isolated_frozen_teacher',
            'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_uri':uri,'training_data_rights_verified':True,
            'source_license_verified':True,'source_provenance_verified':True,
            'pii_review':'PASS','deidentified':True,'owner_sample_approved':True,
            'independent_grade':{'verified':True,'harness_sha256':HARNESS,
                'source_receipt_sha256':RECEIPT,'quality_score':0.9}}

def policy():
    return {'signed_by_native_owner':True,'stop_requested':False,
            'allowed_teacher_ids':['teacher1'],'max_evidence_capsules':1,
            'user_data_private':False,'scope':'owner',
            'accepted_source_receipt_shas':[RECEIPT],
            'training_approved_source_receipt_shas':[RECEIPT]}

class ArenaOwnerProofTests(unittest.TestCase):
    def test_happy_public_source_evidence_and_training_review_only(self):
        out=evaluate_teacher_arena([candidate()],policy())
        self.assertEqual(out['state'],'EVIDENCE_READY_FOR_NOX_SYNTHESIS')
        self.assertEqual(out['training_candidate_count'],1)
        self.assertFalse(out['training_started'])
        self.assertEqual(out['neural_weight_updates_verified'],0)
    def test_missing_owner_source_allowlist_fails_closed(self):
        p=policy();p.pop('accepted_source_receipt_shas')
        self.assertEqual(evaluate_teacher_arena([candidate()],p)['state'],
                         'HOLD_OWNER_SOURCE_RECEIPT_ALLOWLIST')
    def test_spoofed_teacher_receipt_not_evidence(self):
        c=candidate();c['independent_grade']['source_receipt_sha256']='f'*64
        self.assertEqual(evaluate_teacher_arena([c],policy())['evidence_capsules'],[])
    def test_absent_training_license_never_trains(self):
        c=candidate();c['source_license_verified']=False
        self.assertEqual(evaluate_teacher_arena([c],policy())['training_candidate_count'],0)
    def test_unverified_provenance_never_trains(self):
        c=candidate();c['source_provenance_verified']=False
        self.assertEqual(evaluate_teacher_arena([c],policy())['training_candidate_count'],0)
    def test_unreviewed_pii_never_trains(self):
        c=candidate();c['pii_review']='UNKNOWN'
        self.assertEqual(evaluate_teacher_arena([c],policy())['training_candidate_count'],0)
    def test_training_source_requires_separate_owner_allowlist(self):
        p=policy();p['training_approved_source_receipt_shas']=[]
        self.assertEqual(evaluate_teacher_arena([candidate()],p)['training_candidate_count'],0)
    def test_training_allowlist_cannot_exceed_evidence_allowlist(self):
        p=policy();p['training_approved_source_receipt_shas']=['f'*64]
        self.assertEqual(evaluate_teacher_arena([candidate()],p)['state'],
                         'HOLD_TRAINING_SOURCE_RECEIPT_ALLOWLIST')
    def test_s03_private_source_blocked_without_owner_acl(self):
        c=candidate('s03://owner/private');p=policy()
        self.assertEqual(evaluate_teacher_arena([c],p)['evidence_capsules'],[])
        p['allow_owner_s03_evidence']=True
        self.assertEqual(evaluate_teacher_arena([c],p)['evidence_capsules'],[])
    def test_s03_native_acl_can_be_evidence_but_not_training(self):
        c=candidate('s03://owner/private');c['s03_owner_acl_verified']=True;c['scope']='owner'
        p=policy();p['allow_owner_s03_evidence']=True
        out=evaluate_teacher_arena([c],p)
        self.assertEqual(len(out['evidence_capsules']),1)
        self.assertEqual(out['training_candidate_count'],0)
    def test_s03_wrong_scope_isolation(self):
        c=candidate('s03://owner/private');c['s03_owner_acl_verified']=True;c['scope']='other'
        p=policy();p['allow_owner_s03_evidence']=True;p['allow_owner_s03_training']=True
        self.assertEqual(evaluate_teacher_arena([c],p)['evidence_capsules'],[])
    def test_owner_stop_preempts_all(self):
        p=policy();p['stop_requested']=True
        self.assertEqual(evaluate_teacher_arena([candidate()],p)['state'],'HOLD_STOP')
if __name__=='__main__':unittest.main()
