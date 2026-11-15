"""V47/V175 60 logical OneHost jobs: actual owner-native registration gates.

These use fake native port callbacks as negative/source regressions ONLY;
never claim a single job was registered on the Vast.ai production host.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest

from nox_runpod.teacher_mesh.v47.control.dispatcher import (
    load_matrix,plan,enqueue_approved,NativePorts,
)
from nox_runpod.teacher_mesh.v47.control.test_v94_priority import state

ROOT=Path(__file__).resolve().parents[4]
R60=ROOT/'coordination/NOX_R60_MASTER.json'


class NativeRegistrationGates(unittest.TestCase):
    def setUp(self):
        self.matrix=load_matrix()
        self.canonical=json.loads(R60.read_text('utf-8'))
        self.snapshot=state(native_queue_verified=True,task_status={},now_unix=2000,
                            native_writes_available=True,owner_queue_writer_lease_verified=True)
        self.scope='nox-owner-001'
        self.calls={'enqueue':0,'duplicate':[],'s03':0,'readback':0,'task_status':0}
        self.queued=None
        self.registry_override=None
        self.fail_s03=False
        self.dupe_alias=None

    def ports(self):
        def duplicate(tid):
            self.calls['duplicate'].append(tid)
            return tid==self.dupe_alias
        def enqueue(payload):
            self.calls['enqueue']+=1
            self.queued=payload
            return {'accepted':True,'job_id':'native-job-001','native_verified':True}
        def task_status(tid):
            self.calls['task_status']+=1
            if self.registry_override is not None:
                return self.registry_override
            return {'task_id':tid,'job_id':'native-job-001',
                    'state':'PENDING','native_verified':True,
                    'owner_scope':self.scope,'receipt_sha256':'c'*64}
        def audit(event):
            self.calls['s03']+=1
            self.last_s03_event=event
            return {'event_id':'durable-event-001'}
        def readback(jid):
            self.calls['readback']+=1
            return {'job_id':jid,'task_id':self.queued['task_id'],'state':'pending'}
        return NativePorts(
            authorize=lambda scope:scope==self.scope,
            stop=lambda:False,
            state=lambda:self.snapshot,
            native_task_status=task_status,
            native_duplicate_check=duplicate,
            approve=lambda scope,digest,inventory:scope==self.scope,
            queue_enqueue=enqueue,
            queue_readback=readback,
            verify_queue_receipt=lambda ticket,payload:True,
            s03_audit=audit,
            s03_verify=lambda receipt,event:not self.fail_s03,
        )

    def test_verified_single_native_registration_requires_registry_and_s03(self):
        result=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(result['state'],'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED')
        self.assertEqual(result['jobs_enqueued'],1)
        self.assertEqual(self.calls['enqueue'],1)
        self.assertEqual(self.calls['task_status'],1)
        self.assertEqual(self.calls['s03'],1)
        self.assertEqual(result['receipts'][0]['job_id'],'native-job-001')
        self.assertEqual(self.last_s03_event['native_task_status_receipt_sha256'],'c'*64)
        self.assertFalse(result['weights_changed'])

    def test_writer_lease_queue_status_and_owner_write_are_all_required(self):
        for key,bad in [('owner_queue_writer_lease_verified',None),
                        ('native_queue_verified',False),
                        ('native_writes_available',False),
                        ('task_status',None),
                        ('now_unix',None)]:
            with self.subTest(key=key):
                old=self.snapshot[key]
                self.snapshot[key]=bad
                result=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
                self.assertEqual(result['state'],'HOLD_NATIVE_QUEUE_WRITER_LEASE_OR_STATUS')
                self.assertEqual(self.calls['enqueue'],0)
                self.snapshot[key]=old

    def test_native_registry_job_id_mismatch_holds_after_queue(self):
        self.registry_override={'task_id':'NOX-V46-01','job_id':'stale-job',
                                'state':'PENDING','native_verified':True,
                                'owner_scope':self.scope,'receipt_sha256':'a'*64}
        result=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(result['state'],'HOLD_NATIVE_TASK_REGISTRY_READBACK')
        self.assertTrue(result['enqueues_may_have_occurred'])
        self.assertEqual(self.calls['enqueue'],1)
        self.assertEqual(self.calls['s03'],0)

    def test_unverified_task_registry_receipt_does_not_claim_native(self):
        self.registry_override={'task_id':'NOX-V46-01','job_id':'native-job-001',
                                'state':'PENDING','native_verified':True,
                                'owner_scope':self.scope,'receipt_sha256':'bogus'}
        r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_TASK_REGISTRY_READBACK')
        self.assertEqual(r['jobs_enqueued_verified'],0)

    def test_s03_failure_is_hold_not_fake_success(self):
        self.fail_s03=True
        r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_S03_DURABILITY_UNVERIFIED')
        self.assertTrue(r['enqueues_may_have_occurred'])
        self.assertEqual(self.calls['enqueue'],1)

    def test_canonical_r60_and_v46_are_not_two_schedulers(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.assertEqual(p['state'],'SOURCE_PLAN_ONLY')
        self.assertEqual(len(p['planned']),1)
        self.assertTrue(p['planned'][0]['task_id'].startswith('R60-'))
        self.assertTrue(p['planned'][0]['legacy_task_id'].startswith('NOX-V46-'))
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED')
        self.assertTrue(self.queued['task_id'].startswith('R60-'))
        self.assertTrue(self.queued['legacy_task_id'].startswith('NOX-V46-'))
        self.assertIn(self.queued['task_id'],self.calls['duplicate'])
        self.assertIn(self.queued['legacy_task_id'],self.calls['duplicate'])
        self.assertEqual(self.calls['enqueue'],1)

    def test_canonical_registered_legacy_alias_prevents_double_enqueue(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'NATIVE_QUEUE_NO_NEW_JOBS')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(r['jobs_enqueued'],0)

    def test_tampered_source_matrix_alias_or_dependency_fails_closed(self):
        for mutation in ('alias','dependency','priority','resource','duplicate'):
            with self.subTest(mutation=mutation):
                obj=copy.deepcopy(self.canonical)
                if mutation=='alias':
                    obj['tasks'][0]['legacy_task_id']='NOX-V46-59'
                elif mutation=='dependency':
                    obj['tasks'][1]['depends_on']=[]
                elif mutation=='priority':
                    obj['tasks'][0]['priority']='P9'
                elif mutation=='resource':
                    obj['tasks'][0]['resource_class']='GPU1_EXCLUSIVE'
                else:
                    obj['tasks'][1]['task_id']=obj['tasks'][0]['task_id']
                result=plan(obj,self.snapshot,max_new=1)
                self.assertEqual(result['state'],'HOLD_SOURCE_MATRIX_ALIAS_OR_SCHEMA')
                self.assertEqual(result['planned'],[])

    def test_untrusted_native_queue_snapshot_never_enqueues(self):
        self.snapshot['task_status']={'NOX-V46-01':{
            'task_id':'NOX-V46-01','state':'RUNNING',
            'native_verified':False,'receipt_sha256':'a'*64}}
        r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_QUEUE_RECONCILE_OR_UNTRUSTED')
        self.assertEqual(self.calls['enqueue'],0)


if __name__=='__main__':
    unittest.main()
