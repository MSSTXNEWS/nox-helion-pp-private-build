import copy
import json
import unittest
from flow_r22 import regenerate, git_blob_id, checked_registry

HEAD='a'*40
RHEAD='b'*40
STAMP='2026-10-29T21:00:00+03:00'


def fixture():
    register={'schema':'NOX_V16_COMPACT_CUMULATIVE_ERROR_REGISTER_V4',
       'entries':[
          {'error_id':'ERR-SRC-003','status':'OPEN','owner':'T06/Host50'},
          {'error_id':'ERR-SRC-005','status':'FIX_APPLIED_UNVERIFIED','owner':'T06'},
          {'error_id':'ERR-SYS-006','status':'VERIFIED_CLOSED','owner':'T07/T09'}],
       'stats':{'OPEN':1,'FIX_APPLIED_UNVERIFIED':1,'VERIFIED_CLOSED':1,'total':3}}
    raw=json.dumps(register).encode()
    baseline={'schema':'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1',
        'head_at_snapshot':'d'*40,'register_blob':'e'*40,
        'tasks':[
          {'id':'ERR-SRC-003','state':'OPEN','owner':'T06/Host50','source_error_status':'OPEN','depends_on':[]},
          {'id':'ERR-SRC-005','state':'VERIFIED','owner':'T06','source_error_status':'FIX_APPLIED_UNVERIFIED','depends_on':[]},
          {'id':'ERR-SYS-006','state':'ACCEPTED','owner':'T07/T09','source_error_status':'VERIFIED_CLOSED','depends_on':[]},
          {'id':'T06','state':'OPEN','owner':'T06','depends_on':['ERR-SRC-003','ERR-SRC-005'],'lease':{'owner':'old'}},
          {'id':'T08','state':'ACCEPTED','owner':'T08','depends_on':['T06']},
          {'id':'T09','state':'OPEN','owner':'T09','depends_on':['T08']},
          {'id':'T10','state':'OPEN','owner':'T10','depends_on':['T09']},
          {'id':'T11-GITLAB-AUTH','state':'ACCEPTED','owner':'T11','depends_on':[]},
          {'id':'T11','state':'OPEN','owner':'T11','depends_on':['T10','T11-GITLAB-AUTH']}]}
    return baseline,raw,git_blob_id(raw)


class R22Test(unittest.TestCase):
    def runplan(self, b=None, raw=None, sha=None):
        old,rf,h=fixture()
        return regenerate(b if b is not None else old,raw if raw is not None else rf,HEAD,sha or h,STAMP)
    def test_refresh(self):
        x=self.runplan()
        self.assertEqual(x['status'],'REFRESHED_READ_ONLY_NOT_AUTHORIZED')
        self.assertEqual(x['preview']['status'],'READ_ONLY_PLAN_NOT_AUTHORIZED')
    def test_t06_unblocked(self):
        x=self.runplan()
        self.assertIn('T06',[i['id'] for i in x['preview']['ready']])
    def test_t08_not_fake_accepted(self):
        x=self.runplan()
        self.assertIn('T08',[i['id'] for i in x['preview']['deferred']])
        self.assertFalse(x['source_qa_accepted'])
    def test_no_lease_recovery(self):
        x=self.runplan()
        self.assertNotIn('lease',next(y for y in x['snapshot']['tasks'] if y['id']=='T06'))
        self.assertTrue(x['rejected_old_leases'])
    def test_fixed_not_verified(self):
        x=self.runplan()
        self.assertEqual(next(y['state'] for y in x['snapshot']['tasks'] if y['id']=='ERR-SRC-005'),'PATCHED')
    def test_closed_stays_closed(self):
        x=self.runplan()
        self.assertEqual(next(y['state'] for y in x['snapshot']['tasks'] if y['id']=='ERR-SYS-006'),'ACCEPTED')
    def test_bad_register_sha(self):
        with self.assertRaisesRegex(ValueError,'REGISTER_BYTES_NOT_AT_OBSERVED_BLOB'): self.runplan(sha=RHEAD)
    def test_partial_register_refused(self):
        old,raw,sha=fixture();j=json.loads(raw);j['entries']=j['entries'][:1]
        j['stats']={'OPEN':1,'FIX_APPLIED_UNVERIFIED':0,'VERIFIED_CLOSED':0,'total':1}
        raw=json.dumps(j).encode()
        with self.assertRaisesRegex(ValueError,'ERROR_HISTORY_LOSS'):self.runplan(raw=raw,sha=git_blob_id(raw))
    def test_duplicate_json_key(self):
        raw=b'{"entries": [], "entries": [], "stats": {}}'
        with self.assertRaisesRegex(ValueError,'DUPLICATE_REGISTER_KEY'):checked_registry(raw,git_blob_id(raw))
    def test_new_error_retained(self):
        old,raw,sha=fixture();j=json.loads(raw)
        j['entries'].append({'error_id':'ERR-NEW','owner':'T02','status':'OPEN'});j['stats']['OPEN']=2;j['stats']['total']=4
        raw=json.dumps(j).encode();x=self.runplan(raw=raw,sha=git_blob_id(raw))
        self.assertIn('ERR-NEW',[y['id'] for y in x['snapshot']['tasks']])
    def test_stats_mismatch(self):
        old,raw,sha=fixture();j=json.loads(raw);j['stats']['total']=99;raw=json.dumps(j).encode()
        with self.assertRaisesRegex(ValueError,'REGISTER_TOTAL_INCONSISTENT'):self.runplan(raw=raw,sha=git_blob_id(raw))
    def test_wrong_gate_head_resets(self):
        x=self.runplan()
        self.assertEqual(next(y['state'] for y in x['snapshot']['tasks'] if y['id']=='T08'),'OPEN')
    def test_invalid_owner(self):
        old,raw,sha=fixture();j=json.loads(raw);j['entries'][0]['owner']='';raw=json.dumps(j).encode()
        with self.assertRaisesRegex(ValueError,'REGISTER_OWNER_REQUIRED'):self.runplan(raw=raw,sha=git_blob_id(raw))
    def test_baseline_untouched(self):
        b,raw,sha=fixture();before=copy.deepcopy(b);self.runplan(b=b,raw=raw,sha=sha);self.assertEqual(b,before)
    def test_git_blob_identity(self):
        raw=b'abc';self.assertEqual(git_blob_id(raw),'f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f')

if __name__=='__main__':unittest.main()