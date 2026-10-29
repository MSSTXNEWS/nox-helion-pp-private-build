import datetime as dt
import hashlib
import json
import pathlib
import tempfile
import unittest
from nox_flow import (admit_preview, checked_path, duplicate_guard, evidence_status, component_preview,
                      gitlab_compare, iso_utc, productivity, progress_preview,
                      queue_preview, read_json, registry_ok, test_plan)
H = 'a' * 40
H2 = 'b' * 40
S = lambda b: hashlib.sha256(b).hexdigest()
NOW = iso_utc('2026-10-29T18:00:00+00:00')

class R18Tests(unittest.TestCase):
    def registry(self):
        return {'tasks': [
            {'id':'A', 'package':'P01', 'owner':'1', 'state':'ACCEPTED'},
            {'id':'B', 'package':'P04', 'owner':'3', 'state':'OPEN','depends_on':['A'], 'priority':0},
            {'id':'C', 'package':'P05', 'owner':'3', 'state':'OPEN','depends_on':['B'], 'priority':1},
        ]}
    def test_queue_dependencies(self):
        self.assertEqual([t['id'] for t in queue_preview(self.registry(), NOW)['ready']], ['B'])
    def test_queue_no_work_claim(self):
        self.assertTrue(queue_preview(self.registry(), NOW)['no_remote_reservation_or_owner_authorization'])
    def test_queue_fresh_lease_skipped(self):
        r=self.registry();r['tasks'][1]['lease']={'owner':'3','token':'abc','expires_at':'2026-10-29T19:00:00Z'}
        self.assertEqual(queue_preview(r,NOW)['ready'],[])
    def test_queue_stale_lease_not_autoclaimed(self):
        r=self.registry();r['tasks'][1]['lease']={'owner':'3','token':'abc','expires_at':'2026-10-29T17:00:00Z'}
        self.assertEqual(queue_preview(r,NOW)['ready'][0]['state'],'STALE_LEASE_REQUIRES_OWNER_CAS')
    def test_queue_double_ids(self):
        r=self.registry();r['tasks'].append(dict(r['tasks'][0]))
        with self.assertRaises(ValueError):registry_ok(r)
    def test_queue_cycle(self):
        r=self.registry();r['tasks'][0]['depends_on']=['C']
        with self.assertRaises(ValueError):registry_ok(r)
    def test_queue_unknown_dependency(self):
        r=self.registry();r['tasks'][1]['depends_on']=['Z']
        with self.assertRaises(ValueError):registry_ok(r)
    def test_queue_bool_priority_rejected(self):
        r=self.registry();r['tasks'][1]['priority']=True
        with self.assertRaises(ValueError):registry_ok(r)
    def test_timezone_required(self):
        with self.assertRaises(ValueError):iso_utc('2026-10-29T19:00:00')
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p=pathlib.Path(root,'x.json');p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):read_json(p)
    def temp_patch(self,root,original=b'old',candidate=b'new'):
        src=pathlib.Path(root,'src');cand=pathlib.Path(root,'cand');src.mkdir();cand.mkdir()
        (src/'p04.py').write_bytes(original);(cand/'p04.py').write_bytes(candidate)
        r=self.registry()
        o={'path_owners':{'p04.py':'3'}}
        patch={'schema':'NOX_PATCH_V2','owner':'3','task_id':'B','expected_head':H,
               'files':[{'path':'p04.py','pre_sha256':S(original),'post_sha256':S(candidate)}]}
        return src,cand,r,o,patch
    def test_patch_valid_source_and_candidate_preview(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root)
            result=admit_preview(p,r,o,src,cand,H)
            self.assertFalse(result['merge_performed'])
            self.assertFalse(result['git_remote_owner_authenticated'])
    def test_patch_wrong_owner(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);p['owner']='1'
            with self.assertRaises(ValueError):admit_preview(p,r,o,src,cand,H)
    def test_patch_wrong_candidate_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);(cand/'p04.py').write_bytes(b'poison')
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BYTES_MISMATCH'):admit_preview(p,r,o,src,cand,H)
    def test_patch_stale_head(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root)
            with self.assertRaisesRegex(ValueError,'STALE_OR_INVALID_HEAD'):admit_preview(p,r,o,src,cand,H2)
    def test_patch_wrong_preimage(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);(src/'p04.py').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'PREIMAGE_MISMATCH'):admit_preview(p,r,o,src,cand,H)
    def test_patch_path_escape(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);p['files'][0]['path']='../p04.py'
            o['path_owners']['../p04.py']='3'
            with self.assertRaises(ValueError):admit_preview(p,r,o,src,cand,H)
    def test_patch_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);(cand/'p04.py').unlink()
            (cand/'p04.py').symlink_to(pathlib.Path(root,'src','p04.py'))
            with self.assertRaises(ValueError):admit_preview(p,r,o,src,cand,H)
    def test_patch_absent_file_new(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);(src/'p04.py').unlink();p['files'][0]['pre_sha256']='ABSENT'
            self.assertEqual(admit_preview(p,r,o,src,cand,H)['files'][0]['pre_sha256'],'ABSENT')
    def test_patch_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as root:
            src,cand,r,o,p=self.temp_patch(root);p['files'].append(dict(p['files'][0]))
            with self.assertRaises(ValueError):admit_preview(p,r,o,src,cand,H)
    def test_selected_tests_exact_prefix(self):
        out=test_plan({'always':['security'], 'rules':[{'prefix':'Packages/P04','tests':['rag']}]},['Packages/P04/foo','Packages/P044/bar'])
        self.assertIn('rag',out['tests']);self.assertEqual(out['unmapped_paths'],['Packages/P044/bar'])
        self.assertEqual(out['status'],'MANUAL_TEST_MAPPING_REQUIRED')
    def test_qa_correlated_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            content=json.dumps({'task_id':'B','head':H,'reviewer_role':'2','decision':'PASS'}).encode()
            pathlib.Path(root,'QA.json').write_bytes(content)
            claims=[{'task_id':'B','stage':'ACCEPTED','head':H,
                     'qa_receipt_path':'QA.json','qa_receipt_sha256':S(content)}]
            result=evidence_status(claims,root,H)
            self.assertEqual(result['local_qa_receipts_checksum_matched'],1)
            self.assertFalse(result['count_as_product_done_without_remote_owner_validation'])
    def test_qa_wrong_sha_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            pathlib.Path(root,'QA.json').write_text('{}')
            claims=[{'task_id':'B','stage':'ACCEPTED','head':H,
                     'qa_receipt_path':'QA.json','qa_receipt_sha256':'b'*64}]
            self.assertEqual(evidence_status(claims,root,H)['local_qa_receipts_checksum_matched'],0)
    def test_qa_outdated_head_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            claims=[{'task_id':'B','stage':'ACCEPTED','head':H2,
                     'qa_receipt_path':'not-there','qa_receipt_sha256':'b'*64}]
            self.assertEqual(evidence_status(claims,root,H)['local_qa_receipts_checksum_matched'],0)
    def test_parallel_worker_and_wall_different(self):
        t=[{'started_at':'2026-10-29T10:00:00Z','completed_at':'2026-10-29T10:10:00Z'},
           {'started_at':'2026-10-29T10:05:00Z','completed_at':'2026-10-29T10:15:00Z'}]
        o=productivity(t,[])
        self.assertEqual((o['worker_minutes'],o['wall_active_minutes']),(20,15))
        self.assertEqual(o['forecast'].split(' — ')[0],'N/D')
    def test_throughput_zero_not_eta(self):
        o=productivity([{'started_at':'2026-10-29T10:00:00Z','completed_at':'2026-10-29T10:10:00Z'}])
        self.assertIsNone(o['unique_verified_accepted']);self.assertIsNone(o['accepted_per_worker_hour'])
    def test_progress_manifest_not_enough(self):
        obj={k:{'frozen':True,'manifest_sha256':'c'*64,'tasks':[{'id':k+'-A','weight':1,
           'state':'ACCEPTED','qa_receipt_sha256':'d'*64,'accepted_head':H}]} for k in ['P01','P02','P03','P04','P05']}
        out=progress_preview(obj)
        self.assertIsNone(out['product_percent']);self.assertEqual(out['blocks']['P01']['claimed_evidence_covered_percent'],100)
    def test_progress_unknown_denominator(self):
        self.assertEqual(progress_preview({})['blocks']['P04']['reason'],'FROZEN_MANIFEST_AND_EVIDENCE_REQUIRED')
    def test_claimed_done_not_mistaken_for_authenticated_done(self):
        r=productivity([{'started_at':'2026-10-29T10:00:00Z','completed_at':'2026-10-29T10:10:00Z'}],['A','A'])
        self.assertEqual(r['unique_reported_accepted_unverified'],1)
        self.assertIsNone(r['unique_verified_accepted'])
        self.assertIsNone(r['accepted_per_worker_hour'])
    def test_external_component_requires_pinned_digest_and_license(self):
        entry={'name':'example-library','version':'1.2.3','license_spdx':'MIT','source_url':'https://example.org/release','sha256':'b'*64}
        x=component_preview([entry])
        self.assertFalse(x['can_import_to_product'])
        for key,value in [('version','latest'),('sha256','bad'),('source_url','http://invalid.org')]:
            e=dict(entry);e[key]=value
            with self.assertRaises(ValueError):component_preview([e])
    def test_duplicate_component_prevented(self):
        e={'name':'library','version':'1.0.1','license_spdx':'Apache-2.0','source_url':'https://example.com/src','sha256':'c'*64}
        with self.assertRaisesRegex(ValueError,'DUPLICATE_COMPONENT'):component_preview([e,e])
    def test_gitlab_access_unavailable(self):
        a=gitlab_compare({'source_commit':H},{'head_commit':None})
        self.assertEqual(a['status'],'ACCESS_HOLD')
    def test_gitlab_drift(self):
        a=gitlab_compare({'source_commit':H},{'head_commit':H2,'authenticated_readback':True})
        self.assertEqual(a['status'],'DIVERGENT_COMMIT')
        self.assertFalse(a['gitlab_ready'])

if __name__=='__main__': unittest.main()