import unittest,hashlib
from flow_r20 import create_r20_queue, flow_plan, normalize_error_status,verify_handoff,schedule_audit
from nox_flow import iso_utc
H='a'*40;S='b'*64

def data():
    return {'entries':[{'error_id':'ERR-SRC-003','owner':'T06','status':'OPEN'},
                       {'error_id':'ERR-SRC-004','owner':'T06','status':'OPEN'},
                       {'error_id':'ERR-005','owner':'T08','status':'FIX_APPLIED_UNVERIFIED'},
                       {'error_id':'ERR-006','owner':'T07','status':'VERIFIED_CLOSED'}],
            'source_blob':'c'*40}

class TestR20(unittest.TestCase):
    def build(self):return create_r20_queue({},data(),H)
    def test_unverified_fix_not_verified(self):self.assertEqual(normalize_error_status('FIX_APPLIED_UNVERIFIED'),'PATCHED')
    def test_t06_not_blocked_by_own_errors(self):
        r=self.build();t=next(x for x in r['tasks'] if x['id']=='T06')
        self.assertEqual(t['depends_on'],[])
        out=flow_plan(r,iso_utc('2026-10-29T19:00:00Z'),H)
        self.assertIn('T06',[x['id'] for x in out['ready']])
    def test_same_sha_qa_still_deferred(self):
        o=flow_plan(self.build(),iso_utc('2026-10-29T19:00:00Z'),H)
        self.assertEqual(next(x for x in o['deferred'] if x['task_id']=='T08')['missing_accepted_dependencies'],['T06'])
    def test_gitlab_auth_independent(self):
        o=flow_plan(self.build(),iso_utc('2026-10-29T19:00:00Z'),H)
        self.assertIn('T11-GITLAB-AUTH',[r['id'] for r in o['ready']]);self.assertNotIn('T11',[r['id'] for r in o['ready']])
    def test_accepted_errors_not_need_repeat(self):
        o=flow_plan(self.build(),iso_utc('2026-10-29T19:00:00Z'),H)
        self.assertNotIn('ERR-006',[r['id'] for r in o['ready']])
    def test_stale_head_prevents_plan(self):
        o=flow_plan(self.build(),iso_utc('2026-10-29T19:00:00Z'),'d'*40)
        self.assertEqual(o['status'],'STALE_SNAPSHOT_REGENERATE');self.assertEqual(o['ready'],[])
    def test_invalid_duplicate_errors(self):
        d=data();d['entries'].append(dict(d['entries'][0]));
        with self.assertRaises(ValueError):create_r20_queue({},d,H)
    def test_no_forged_head(self):
        h={'task_id':'P04.E04.02','owner':'3','expected_head':H,'files':[{'path':'Packages/P04/rag.py','pre_sha256':S,'post_sha256':'c'*64}]}
        with self.assertRaises(ValueError):verify_handoff(h,'d'*40,'3')
    def test_no_owner_switch(self):
        h={'task_id':'P04.E04.02','owner':'3','expected_head':H,'files':[{'path':'Packages/P04/rag.py','pre_sha256':S,'post_sha256':'c'*64}]}
        with self.assertRaises(ValueError):verify_handoff(h,H,'1')
    def test_handoff_is_preview(self):
        h={'task_id':'P04.E04.02','owner':'3','expected_head':H,'files':[{'path':'Packages/P04/rag.py','pre_sha256':S,'post_sha256':'c'*64}]}
        v=verify_handoff(h,H,'3');self.assertFalse(v['remote_owner_authenticated']);self.assertFalse(v['cas_performed'])
    def test_no_noop_source(self):
        h={'task_id':'P04.E04.02','owner':'3','expected_head':H,'files':[{'path':'Packages/P04/rag.py','pre_sha256':S,'post_sha256':S}]}
        with self.assertRaises(ValueError):verify_handoff(h,H,'3')
    def test_no_parent_traversal(self):
        h={'task_id':'P04.E04.02','owner':'3','expected_head':H,'files':[{'path':'../bad','pre_sha256':S,'post_sha256':'c'*64}]}
        with self.assertRaises(ValueError):verify_handoff(h,H,'3')
    def test_schedule_gap(self):
        q=schedule_audit([{'id':'G2-C','minute':13},{'id':'G3-C','minute':39},{'id':'G4-B','minute':51},{'id':'G4-C','minute':3},{'id':'G5-B','minute':15},{'id':'G5-C','minute':27}]);
        self.assertEqual(next(x for x in q['pairs'] if x['downstream']=='G3-C')['scheduled_gap_minutes'],26)
        self.assertEqual(next(x for x in q['pairs'] if x['downstream']=='G4-C')['scheduled_gap_minutes'],12)
    def test_product_is_unknown(self):self.assertIsNone(self.build()['product_percent'])
    def test_dependencies_are_acyclic(self):
        r=self.build();ids={t['id'] for t in r['tasks']};self.assertTrue(all(set(t['depends_on']).issubset(ids) for t in r['tasks']))

if __name__=='__main__':unittest.main()