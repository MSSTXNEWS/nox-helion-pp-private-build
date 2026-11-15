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
from nox_runpod.teacher_mesh.v47.control.native_registration_recovery import _hash
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
        self.s03_present=True
        self.s03_readback_fault=None
        self.approved=True
        self.native_status_conflict=False
        self.lease_lost_after_first=False

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
            if self.registry_override is not None:return self.registry_override
            if self.native_status_conflict and tid.startswith('NOX-V46-'):
                return {'task_id':tid,'job_id':'native-job-ALT','state':'PENDING',
                        'native_verified':True,'owner_scope':self.scope,
                        'receipt_sha256':'c'*64}
            return {'task_id':tid,'job_id':'native-job-001',
                    'state':'PENDING','native_verified':True,
                    'owner_scope':self.scope,'receipt_sha256':'c'*64}
        def audit(event):
            self.calls['s03']+=1
            self.last_s03_event=event
            return {'event_id':'durable-event-001'}
        def s03_lookup(event):
            if event.get('schema')=='NOX_V46_QUEUED_RECEIPT' and self.s03_readback_fault:
                if self.s03_readback_fault=='MISSING':
                    return {'state':'MISSING','native_verified':True}
                return {'state':'PRESENT','native_verified':True,
                        'event_sha256':'e'*64,'job_id':event['job_id'],
                        'owner_scope':event['owner_scope']}
            if self.s03_present or self.calls['s03']>0:
                return {'state':'PRESENT','native_verified':True,'event_sha256':_hash(event),
                        'job_id':event['job_id'],'owner_scope':event['owner_scope']}
            return {'state':'MISSING','native_verified':True}
        def native_state():
            x=dict(self.snapshot)
            if self.lease_lost_after_first and self.calls['enqueue']>=1:
                x['owner_queue_writer_lease_verified']=False
            return x
        def readback(jid):
            self.calls['readback']+=1
            return {'job_id':jid,'task_id':self.queued['task_id'] if self.queued else (self.dupe_alias or 'NOX-V46-01'),'state':'pending'}
        return NativePorts(
            authorize=lambda scope:scope==self.scope,
            stop=lambda:False,
            state=native_state,
            native_task_status=task_status,
            native_duplicate_check=duplicate,
            approve=lambda scope,digest,inventory:scope==self.scope and self.approved,
            queue_enqueue=enqueue,
            queue_readback=readback,
            verify_queue_receipt=lambda ticket,payload:True,
            s03_audit=audit,
            s03_verify=lambda receipt,event:not self.fail_s03,
            s03_registration_lookup=s03_lookup,
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

    def test_new_queue_s03_ack_without_independent_readback_is_hold(self):
        # Previous V47 trusted s03_verify alone; an ACK does not prove the
        # original S03 is durable or bound to this exact owner/job/event.
        for fault in ('MISSING','WRONG_EVENT_DIGEST'):
            with self.subTest(fault=fault):
                self.setUp()
                self.s03_readback_fault=fault
                r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
                self.assertEqual(r['state'],'HOLD_S03_INDEPENDENT_READBACK')
                self.assertTrue(r['enqueues_may_have_occurred'])
                self.assertEqual(r['jobs_enqueued_verified'],0)
                self.assertEqual(self.calls['enqueue'],1)
                self.assertEqual(self.calls['s03'],1)

    def test_unbound_native_s03_readback_port_blocks_before_enqueue(self):
        from dataclasses import replace
        ports=replace(self.ports(),s03_registration_lookup=None)
        r=enqueue_approved(ports,self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_CALLBACKS')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)
        self.assertTrue(self.calls['duplicate'])

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


    def test_orphaned_native_registration_recovers_s03_not_gpu_process(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'NATIVE_S03_RECONCILIATION_VERIFIED')
        self.assertEqual(r['jobs_enqueued'],0)
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],1)
        self.assertEqual(len(r['orphaned_s03_receipts_recovered']),1)
        self.assertEqual(self.last_s03_event['schema'],
                         'NOX_V175_EXISTING_REGISTRATION_S03_RECONCILE_V1')
        self.assertEqual(self.last_s03_event['owner_scope'],self.scope)

    def test_orphan_registration_requires_independent_s03_proof(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        self.approved=False
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_EXISTING_REGISTRATION_RECONCILIATION')
        self.assertEqual(r['reason'],'HOLD_S03_REPAIR_NOT_APPROVED')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)

    def test_s03_repair_fails_closed_after_uncertain_write(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        self.fail_s03=True
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_EXISTING_REGISTRATION_RECONCILIATION')
        self.assertEqual(r['reason'],'HOLD_S03_REPAIR_READBACK')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],1)

    def test_duplicate_registration_mismatched_alias_job_blocks_repair(self):
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.native_status_conflict=True
        r=enqueue_approved(self.ports(),self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_EXISTING_REGISTRATION_RECONCILIATION')
        self.assertEqual(r['reason'],'HOLD_EXISTING_JOB_MISSING_OR_AMBIGUOUS')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)

    def test_orphan_s03_repair_lease_revoked_by_approval_never_writes(self):
        from dataclasses import replace
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        original=self.ports()
        def revoke(scope,digest,snapshot):
            self.snapshot['owner_queue_writer_lease_verified']=False
            return True
        r=enqueue_approved(replace(original,approve=revoke),self.canonical,
                           self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_EXISTING_REGISTRATION_RECONCILIATION')
        self.assertEqual(r['reason'],'HOLD_S03_REPAIR_LEASE_CHANGED_AFTER_APPROVAL')
        self.assertEqual(self.calls['s03'],0)
        self.assertEqual(self.calls['enqueue'],0)

    def test_orphan_s03_repair_epoch_rotated_by_approval_never_writes(self):
        from dataclasses import replace
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        self.snapshot['owner_queue_writer_lease_epoch']='old'
        original=self.ports()
        def rotate(scope,digest,snapshot):
            self.snapshot['owner_queue_writer_lease_epoch']='new'
            return True
        r=enqueue_approved(replace(original,approve=rotate),self.canonical,
                           self.scope,limit=1)
        self.assertEqual(r['reason'],'HOLD_S03_REPAIR_LEASE_CHANGED_AFTER_APPROVAL')
        self.assertEqual(self.calls['s03'],0)
        self.assertEqual(self.calls['enqueue'],0)

    def test_orphan_s03_repair_registry_switch_after_approval_holds(self):
        from dataclasses import replace
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        self.s03_present=False
        original=self.ports()
        def change_job(scope,digest,snapshot):
            self.registry_override={'task_id':p['planned'][0]['task_id'],
                'job_id':'native-job-replaced','state':'PENDING',
                'native_verified':True,'owner_scope':self.scope,'receipt_sha256':'c'*64}
            return True
        r=enqueue_approved(replace(original,approve=change_job),self.canonical,
                           self.scope,limit=1)
        self.assertEqual(r['reason'],'HOLD_S03_REPAIR_NATIVE_JOB_CHANGED')
        self.assertEqual(self.calls['s03'],0)
        self.assertEqual(self.calls['enqueue'],0)

    def test_owner_approval_receives_current_per_item_native_snapshot(self):
        """A refreshed queue lease must never be approved via stale inventory."""
        from dataclasses import replace
        reads={'count':0}
        approvals=[]
        original=self.ports()
        def per_item_inventory():
            reads['count']+=1
            row=dict(self.snapshot)
            # Initial inventory and per-item refresh are distinct snapshots.
            row['now_unix']=2000 if reads['count']==1 else 2001
            return row
        def owner_approval(scope,digest,inventory):
            approvals.append(inventory.get('now_unix'))
            return scope==self.scope
        native=replace(original,state=per_item_inventory,approve=owner_approval)
        result=enqueue_approved(native,self.matrix,self.scope,limit=1)
        self.assertEqual(result['state'],'NATIVE_QUEUE_READBACK_AND_S03_VERIFIED')
        self.assertEqual(result['jobs_enqueued'],1)
        self.assertGreaterEqual(reads['count'],2)
        self.assertEqual(approvals,[2001])

    def test_approval_revokes_writer_lease_before_enqueue_fail_closed(self):
        """Owner approval can invalidate the lease even before the first write."""
        from dataclasses import replace
        original=self.ports()
        def revoke_during_approval(scope,digest,inventory):
            self.snapshot['owner_queue_writer_lease_verified']=False
            return scope==self.scope
        native=replace(original,approve=revoke_during_approval)
        result=enqueue_approved(native,self.matrix,self.scope,limit=1)
        self.assertEqual(result['state'],'HOLD_NATIVE_LEASE_CHANGED_AFTER_APPROVAL')
        self.assertEqual(result['jobs_enqueued_verified'],0)
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)

    def test_approval_rotates_owner_epoch_before_enqueue_fail_closed(self):
        """A fresh valid-looking lease with a different owner epoch is not ours."""
        from dataclasses import replace
        self.snapshot['owner_queue_writer_lease_epoch']='e1'
        original=self.ports()
        def rotate_during_approval(scope,digest,inventory):
            self.snapshot['owner_queue_writer_lease_epoch']='e2'
            return scope==self.scope
        native=replace(original,approve=rotate_during_approval)
        result=enqueue_approved(native,self.matrix,self.scope,limit=1)
        self.assertEqual(result['state'],'HOLD_NATIVE_LEASE_CHANGED_AFTER_APPROVAL')
        self.assertEqual(self.calls['enqueue'],0)

    def test_native_lease_loss_between_two_batch_jobs_cannot_continue(self):
        prior=plan(self.matrix,self.snapshot,max_new=2)
        self.assertGreaterEqual(len(prior['planned']),2)
        self.lease_lost_after_first=True
        r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=2)
        self.assertEqual(r['state'],'HOLD_NATIVE_LEASE_REVOKED_DURING_BATCH')
        self.assertEqual(r['jobs_enqueued_verified'],1)
        self.assertEqual(self.calls['enqueue'],1)

    def test_unknown_s03_receipt_lookup_never_requeues_duplicate(self):
        from dataclasses import replace
        p=plan(self.canonical,self.snapshot,max_new=1)
        self.dupe_alias=p['planned'][0]['legacy_task_id']
        ports=replace(self.ports(),s03_registration_lookup=None)
        r=enqueue_approved(ports,self.canonical,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_EXISTING_REGISTRATION_RECONCILIATION')
        self.assertEqual(r['reason'],'HOLD_REGISTRATION_NATIVE_PORTS')
        self.assertEqual(self.calls['enqueue'],0)

    def test_uncertain_native_enqueue_ack_reports_possible_side_effect(self):
        """An invalid remote ACK can conceal a committed native queue job."""
        from dataclasses import replace
        for reply in ({'accepted':False}, {'accepted':True},
                      {'accepted':True,'job_id':'invalid id'}):
            with self.subTest(reply=reply):
                self.calls['enqueue']=0
                self.calls['s03']=0
                original=self.ports()
                def ack_after_side_effect(payload):
                    # The remote write was invoked: negative/missing/invalid ACK
                    # cannot prove that the job was NOT enqueued.
                    self.calls['enqueue']+=1
                    return reply
                native=replace(original,queue_enqueue=ack_after_side_effect)
                result=enqueue_approved(native,self.matrix,self.scope,limit=1)
                self.assertEqual(result['state'],'HOLD_QUEUE_NOT_ACCEPTED')
                self.assertTrue(result['enqueues_may_have_occurred'])
                self.assertEqual(result['jobs_enqueued_verified'],0)
                self.assertEqual(self.calls['enqueue'],1)
                self.assertEqual(self.calls['s03'],0)

    def test_untrusted_native_queue_snapshot_never_enqueues(self):
        self.snapshot['task_status']={'NOX-V46-01':{
            'task_id':'NOX-V46-01','state':'RUNNING',
            'native_verified':False,'receipt_sha256':'a'*64}}
        r=enqueue_approved(self.ports(),self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_QUEUE_RECONCILE_OR_UNTRUSTED')
        self.assertEqual(self.calls['enqueue'],0)


    def test_owner_approval_native_registry_task_appears_never_enqueues(self):
        """A newly visible valid native job is protected even if the lease remains valid."""
        p=plan(self.matrix,self.snapshot,max_new=1)
        tid=p['planned'][0]['task_id']
        from dataclasses import replace
        old=self.ports()
        def external_registration_during_approval(scope,digest,inventory):
            self.snapshot['task_status']={tid:{
                'task_id':tid,'state':'PENDING','native_verified':True,
                'receipt_sha256':'c'*64,'job_id':'native-job-external'}}
            return True
        native=replace(old,approve=external_registration_during_approval)
        r=enqueue_approved(native,self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_TASK_APPEARED_AFTER_APPROVAL')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)

    def test_owner_approval_duplicate_port_changes_never_enqueues(self):
        """Native duplicate registry can change even when state snapshot lags."""
        p=plan(self.matrix,self.snapshot,max_new=1)
        tid=p['planned'][0]['task_id']
        from dataclasses import replace
        old=self.ports()
        def external_duplicate_during_approval(scope,digest,inventory):
            self.dupe_alias=tid
            return True
        native=replace(old,approve=external_duplicate_during_approval)
        r=enqueue_approved(native,self.matrix,self.scope,limit=1)
        self.assertEqual(r['state'],'HOLD_NATIVE_TASK_APPEARED_AFTER_APPROVAL')
        self.assertEqual(self.calls['enqueue'],0)
        self.assertEqual(self.calls['s03'],0)


if __name__=='__main__':
    unittest.main()
