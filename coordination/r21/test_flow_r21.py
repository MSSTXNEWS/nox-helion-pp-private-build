import unittest
from flow_r21 import reconcile, preview
H='a'*40
B='b'*40
D='d'*40

def saved():
    return {'schema':'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1',
            'head_at_snapshot':H,'register_blob':B,
            'tasks':[
                {'id':'ERR-SRC-003','package':'GATE','owner':'T06','state':'OPEN','priority':0,'depends_on':[], 'source_error_status':'OPEN'},
                {'id':'ERR-SRC-005','package':'GATE','owner':'T06','state':'PATCHED','priority':0,'depends_on':[], 'source_error_status':'FIX_APPLIED_UNVERIFIED'},
                {'id':'T06','package':'GATE','owner':'T06','state':'OPEN','priority':0,'depends_on':[]},
                {'id':'T08','package':'GATE','owner':'T08','state':'OPEN','priority':0,'depends_on':['T06']},
                {'id':'T09','package':'GATE','owner':'T09','state':'OPEN','priority':1,'depends_on':['T08']},
                {'id':'T10','package':'GATE','owner':'T10','state':'OPEN','priority':1,'depends_on':['T09']},
                {'id':'T11-GITLAB-AUTH','package':'GATE','owner':'T11','state':'OPEN','priority':0,'depends_on':[]},
                {'id':'T11','package':'GATE','owner':'T11','state':'OPEN','priority':1,'depends_on':['T10','T11-GITLAB-AUTH']}]}

class TestPersistedR20Compatibility(unittest.TestCase):
    def test_actual_persisted_schema_normalizes(self):
        r=reconcile(saved(),H,B)
        self.assertEqual(r['dispatch']['schema'],'NOX_V16_R20_DISPATCH_SNAPSHOT_V1')
    def test_head_drift_fails_closed(self):
        r=preview(saved(),D,B,'2026-10-29T20:00:00+03:00')
        self.assertEqual(r['ready'],[])
        self.assertTrue(r['head_drift'])
    def test_registry_drift_fails_closed(self):
        r=preview(saved(),H,D,'2026-10-29T20:00:00+03:00')
        self.assertTrue(r['register_drift'])
        self.assertEqual(r['status'],'STALE_SNAPSHOT_REGENERATE')
    def test_missing_register_provenance_fails(self):
        s=saved();s.pop('register_blob')
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_PROVENANCE_MISSING'):
            reconcile(s,H,B)
    def test_unverified_cannot_be_promoted(self):
        s=saved();s['tasks'][1]['state']='VERIFIED'
        with self.assertRaisesRegex(ValueError,'UNVERIFIED_ERROR_PROMOTED'):
            reconcile(s,H,B)
    def test_t06_self_dependency_rejected(self):
        s=saved();s['tasks'][2]['depends_on']=['ERR-SRC-003']
        with self.assertRaisesRegex(ValueError,'T06_SELF_DEADLOCK_REINTRODUCED'):
            reconcile(s,H,B)
    def test_t06_ready_qa_deferred(self):
        p=preview(saved(),H,B,'2026-10-29T20:00:00+03:00')
        self.assertIn('T06',[i['id'] for i in p['ready']])
        self.assertNotIn('T08',[i['id'] for i in p['ready']])
        self.assertIn('T11-GITLAB-AUTH',[i['id'] for i in p['ready']])
        self.assertFalse(p['qa_accepted'])
    def test_no_build_permission_generated(self):
        p=preview(saved(),H,B,'2026-10-29T20:00:00+03:00')
        self.assertTrue(p['zero_mutations'])
        self.assertFalse(p['remote_owner_authenticated'])
    def test_invalid_duplicate_task_rejected(self):
        s=saved();s['tasks'].append(dict(s['tasks'][0]))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_TASK_ID'):
            reconcile(s,H,B)
    def test_invalid_sha_rejected(self):
        with self.assertRaisesRegex(ValueError,'OBSERVED_HEAD_SHA_REQUIRED'):
            reconcile(saved(),'short',B)
    def test_already_canonical_schema_supported(self):
        s=saved();s['schema']='NOX_V16_R20_DISPATCH_SNAPSHOT_V1';s['head_snapshot']=s.pop('head_at_snapshot');s['error_register_blob']=s.pop('register_blob')
        self.assertEqual(reconcile(s,H,B)['status'],'CURRENT_SNAPSHOT_METADATA_VALIDATED_NOT_AUTHORIZED')

if __name__ == '__main__':unittest.main()