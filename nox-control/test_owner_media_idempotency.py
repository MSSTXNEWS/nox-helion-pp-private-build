"""B5/5B01 focused offline negative gates; does NOT execute real OneHost."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from owner_media_idempotency import (request_identity, find_existing,
    repair_queued_inbox, create_or_resume, IdempotencyHold)

class B5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.jobs=self.root/'jobs';self.inbox=self.root/'inbox'
        self.jobs.mkdir();self.inbox.mkdir()
        self.owner='alice';self.body={'client_request_id':'a'*32,'kind':'image','prompt':'Hola'}
        self.key,self.payload,self.digest=request_identity(self.body)
        self.lock=threading.RLock();self.count=0
    def rd(self,p):
        try:return json.loads(p.read_text())
        except (ValueError,OSError):return None
    def atomic(self,p,v):p.write_text(json.dumps(v))
    def make(self,payload):
        self.count+=1
        return {'id':format(self.count,'032x'),'owner':self.owner,'state':'QUEUED','request':payload}
    def call(self,body=None,atomic=None,preflight=None):
        return create_or_resume(body or self.body,self.owner,lock=lambda:self.lock,
            jobs_dir=self.jobs,inbox_dir=self.inbox,read_json=self.rd,
            atomic=atomic or self.atomic,new_job=self.make,
            preflight=preflight or (lambda _:None))
    def test_reordered_payload_same_digest(self):
        self.assertEqual(request_identity(self.body),
            request_identity({'prompt':'Hola','kind':'image','client_request_id':'a'*32}))
    def test_key_validation(self):
        for key in ('bad','A'*32,None,1):
            with self.subTest(key=key),self.assertRaises(IdempotencyHold):
                request_identity({**self.body,'client_request_id':key})
    def test_unknown_field_rejected(self):
        with self.assertRaises(IdempotencyHold):request_identity({**self.body,'x':True})
    def test_invalid_number_rejected(self):
        with self.assertRaises(IdempotencyHold):request_identity({**self.body,'seed':float('nan')})
    def test_lost_response_reuses_job(self):
        first=self.call();second=self.call()
        self.assertEqual(first['id'],second['id']);self.assertEqual(self.count,1)
    def test_payload_conflict_fails_closed(self):
        self.call()
        with self.assertRaisesRegex(IdempotencyHold,'CONFLICT'):
            self.call(body={**self.body,'prompt':'different'})
        self.assertEqual(self.count,1)
    def test_existing_skips_unavailable_engine(self):
        self.call()
        self.call(preflight=lambda _:(_ for _ in ()).throw(AssertionError('called')))
    def test_other_owner_cannot_read_job(self):
        self.call()
        self.assertIsNone(find_existing(self.jobs,'bob',self.key,self.digest,self.rd))
    def test_crash_after_job_write_recovers_inbox(self):
        def crash(path,val):
            if path.parent==self.inbox:raise OSError('crash')
            self.atomic(path,val)
        with self.assertRaises(OSError):self.call(atomic=crash)
        recovered=self.call(preflight=lambda _:(_ for _ in ()).throw(AssertionError()))
        self.assertEqual(recovered['id'],format(1,'032x'));self.assertEqual(self.count,1)
        self.assertEqual(self.rd(self.inbox/(recovered['id']+'.json'))['job_id'],recovered['id'])
    def test_malformed_job_fails_closed(self):
        (self.jobs/('f'*32+'.json')).write_text('not json')
        with self.assertRaisesRegex(IdempotencyHold,'INDEX_UNREADABLE'):self.call()
    def test_inbox_collision_fails_closed(self):
        job=self.call()
        self.atomic(self.inbox/(job['id']+'.json'),{'job_id':'b'*32})
        with self.assertRaisesRegex(IdempotencyHold,'INBOX_CHANGED'):self.call()
    def test_cross_owner_same_key_isolated(self):
        self.call()
        self.assertIsNone(find_existing(self.jobs,'bob',self.key,self.digest,self.rd))
    def test_duplicate_job_records_fail_closed(self):
        first=self.call();copy=dict(first,id='f'*32)
        self.atomic(self.jobs/(copy['id']+'.json'),copy)
        with self.assertRaisesRegex(IdempotencyHold,'DUPLICATE'):self.call()
    def test_parallel_calls_share_one_result(self):
        got=[];errors=[]
        def worker():
            try:got.append(self.call()['id'])
            except Exception as e:errors.append(e)
        ts=[threading.Thread(target=worker) for _ in range(12)]
        for t in ts:t.start()
        for t in ts:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(set(got)),1);self.assertEqual(self.count,1)

if __name__=='__main__':unittest.main()
