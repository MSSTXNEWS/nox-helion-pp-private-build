"""Original OneHost/S03 result audit owner/STOP fence, no Windows E07 claim."""
import json
import sqlite3
import unittest
from types import SimpleNamespace
from src.nox_selfbuilder.onehost_queue import NativeWorkQueue, NativeQueueHold


class AuditStore:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        self.conn.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT)')
        self.conn.execute('CREATE TABLE audit (id INTEGER PRIMARY KEY, action TEXT, item_id INTEGER, metadata TEXT, at TEXT)')
        self.after_audit = None

    def _audit(self, action, item_id, data):
        self.conn.execute('INSERT INTO audit(action,item_id,metadata,at) VALUES(?,?,?,?)',
                          (action, item_id, json.dumps(data), '2026-11-02T23:00:00Z'))
        if action == 'NOX_NATIVE_WORK_RESULT' and self.after_audit is not None:
            self.after_audit()


class NativeResultFenceTests(unittest.TestCase):
    def setUp(self):
        self.store = AuditStore()
        self.addCleanup(self.store.conn.close)
        self.scope = SimpleNamespace(tenant='local', principal='owner', chat_id='chat')
        self.epoch = 7
        self.stop = False
        self.permission_reads = []

        def authorize(scope, permission, payload):
            self.permission_reads.append((permission, payload))
            if permission == 'selfbuilder.feedback':
                return payload == {'task_id': self.task_id, 'outcome': 'ACCEPTED'}
            return permission == 'selfbuilder.propose'

        self.queue = NativeWorkQueue(SimpleNamespace(call=lambda f: f(self.store)),
                                     authorize=authorize,
                                     stop_requested=lambda: self.stop,
                                     stop_epoch=lambda: self.epoch)
        self.task_id = self.queue.enqueue(self.scope, kind='SELF_WRITE',
                                          payload={'task': 'bounded native work'},
                                          permission='selfbuilder.propose')

    def count(self):
        return self.store.conn.execute("SELECT COUNT(*) FROM audit WHERE action='NOX_NATIVE_WORK_RESULT'").fetchone()[0]

    def test_unfenced_terminal_result_cannot_forge_owner_acceptance(self):
        before = self.count()
        with self.assertRaisesRegex(PermissionError, 'NATIVE_RESULT_OWNER_FENCE_REQUIRED'):
            self.queue.record(self.scope, self.task_id, 'OWNER_ACCEPTED',
                              {'status': 'OWNER_ACCEPTED'})
        self.assertEqual(self.count(), before)

    def test_original_owner_feedback_exact_consent_payload(self):
        self.assertTrue(self.queue.record(self.scope, self.task_id, 'OWNER_ACCEPTED',
                        {'status': 'OWNER_ACCEPTED'}, expected_epoch=self.epoch,
                        permission='selfbuilder.feedback',
                        permission_payload={'task_id': self.task_id, 'outcome': 'ACCEPTED'}))
        self.assertIn(('selfbuilder.feedback', {'task_id': self.task_id, 'outcome': 'ACCEPTED'}),
                      self.permission_reads)

    def test_revocation_during_sqlite_audit_rolls_back_terminal_result(self):
        before = self.count()
        self.store.after_audit = lambda: setattr(self, 'epoch', self.epoch + 1)
        with self.assertRaisesRegex(NativeQueueHold, 'NATIVE_RESULT_OWNER_REVOKED'):
            self.queue.record(self.scope, self.task_id, 'DONE', {'status': 'DONE'},
                              expected_epoch=7, permission='selfbuilder.propose')
        self.assertEqual(self.count(), before)

    def test_unfenced_native_error_hold_still_records_nonacceptance(self):
        self.assertTrue(self.queue.record(self.scope, self.task_id, 'HOLD',
                        {'status': 'HOLD', 'reason': 'NATIVE_STOP', 'weights_updated': False}))
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'HOLD')

    def test_unfenced_stale_hold_preserves_accepted_owner_receipt(self):
        self.assertTrue(self.queue.record(
            self.scope, self.task_id, 'OWNER_ACCEPTED', {'status': 'OWNER_ACCEPTED'},
            expected_epoch=self.epoch, permission='selfbuilder.feedback',
            permission_payload={'task_id': self.task_id, 'outcome': 'ACCEPTED'}))
        before = self.count()
        with self.assertRaisesRegex(NativeQueueHold, 'S03_UNFENCED_HOLD_AFTER_RESULT_DENIED'):
            self.queue.record(self.scope, self.task_id, 'HOLD',
                              {'status': 'HOLD', 'reason': 'LATE_ERROR', 'weights_updated': False})
        self.assertEqual(self.count(), before)
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'OWNER_ACCEPTED')

    def test_second_unfenced_hold_cannot_rewrite_first_error(self):
        self.assertTrue(self.queue.record(
            self.scope, self.task_id, 'HOLD',
            {'status': 'HOLD', 'reason': 'NATIVE_STOP', 'weights_updated': False}))
        before = self.count()
        with self.assertRaisesRegex(NativeQueueHold, 'S03_UNFENCED_HOLD_AFTER_RESULT_DENIED'):
            self.queue.record(self.scope, self.task_id, 'HOLD',
                              {'status': 'HOLD', 'reason': 'LATE_ERROR', 'weights_updated': False})
        self.assertEqual(self.count(), before)
        self.assertEqual(self.queue.get(self.scope, self.task_id)['result']['reason'], 'NATIVE_STOP')

    def test_unfenced_hold_with_positive_result_rejected(self):
        with self.assertRaisesRegex(PermissionError, 'NATIVE_RESULT_OWNER_FENCE_REQUIRED'):
            self.queue.record(self.scope, self.task_id, 'HOLD',
                              {'status': 'DONE', 'weights_updated': False})
        self.assertEqual(self.count(), 0)

    def test_forge_enqueue_unknown_stop_or_invalid_epoch_does_not_mutate_sqlite(self):
        before = self.store.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        for stop_value, epoch_value in ((None, 7), ("UNKNOWN", 7), (False, True), (False, None)):
            with self.subTest(stop=stop_value, epoch=epoch_value):
                self.queue.stop_requested = lambda v=stop_value: v
                self.queue.stop_epoch = lambda v=epoch_value: v
                with self.assertRaisesRegex(PermissionError, 'NATIVE_QUEUE_CONSENT_REQUIRED'):
                    self.queue.enqueue(
                        self.scope, kind='FORGE',
                        payload={'task': 'rejected-ambiguous-owner'},
                        permission='selfbuilder.propose')
                self.assertEqual(
                    self.store.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], before)

    def test_null_stop_is_not_consent(self):
        self.queue.stop_requested = lambda: None
        with self.assertRaisesRegex(NativeQueueHold, 'NATIVE_RESULT_OWNER_REVOKED'):
            self.queue.record(self.scope, self.task_id, 'DONE', {'status': 'DONE'},
                              expected_epoch=7, permission='selfbuilder.propose')
        self.assertEqual(self.count(), 0)

    def test_bool_epoch_is_not_exact_native_epoch(self):
        self.queue.stop_epoch = lambda: True
        with self.assertRaisesRegex(NativeQueueHold, 'NATIVE_RESULT_OWNER_REVOKED'):
            self.queue.record(self.scope, self.task_id, 'DONE', {'status': 'DONE'},
                              expected_epoch=1, permission='selfbuilder.propose')
        self.assertEqual(self.count(), 0)

    def test_reject_malformed_authority_payload(self):
        with self.assertRaisesRegex(ValueError, 'NATIVE_RESULT_OWNER_PAYLOAD_REQUIRED'):
            self.queue.record(self.scope, self.task_id, 'DONE', {'status': 'DONE'},
                              expected_epoch=7, permission='selfbuilder.propose',
                              permission_payload={'task_id': self.task_id, 'admin': True})
        self.assertEqual(self.count(), 0)


    def test_callback_rechecks_owner_after_claim_before_side_effect(self):
        # Two owner approvals are consumed during the durable SQLite CLAIM.
        # The third is the worker-start check; revocation must prevent the
        # callback itself, not merely turn its already-run result into HOLD.
        original_auth = self.queue.authorize
        claim_reads = []
        def revoked_after_claim(scope, permission, payload):
            if permission == 'selfbuilder.propose' and payload == {'task_id': self.task_id}:
                claim_reads.append(1)
                return len(claim_reads) <= 2
            return original_auth(scope, permission, payload)
        self.queue.authorize = revoked_after_claim
        effects = []
        self.queue.submit_source(self.scope, self.task_id,
                                 lambda: effects.append('side_effect') or {'status': 'DONE'})
        self.queue._thread.join(timeout=3)
        self.assertFalse(self.queue._thread.is_alive())
        self.assertEqual(len(claim_reads), 3)
        self.assertEqual(effects, [])
        row = self.queue.get(self.scope, self.task_id)
        self.assertEqual(row['state'], 'HOLD')
        self.assertEqual(row['result']['reason'], 'NATIVE_WORK_REVOKED_BEFORE_EXECUTION')

    def test_callback_runs_with_current_owner_consent(self):
        effects = []
        self.queue.submit_source(self.scope, self.task_id,
                                 lambda: effects.append('approved') or {'status': 'DONE'})
        self.queue._thread.join(timeout=3)
        self.assertFalse(self.queue._thread.is_alive())
        self.assertEqual(effects, ['approved'])
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'DONE')

    def test_worker_rejects_indeterminate_stop_after_claim(self):
        reads = []
        def stop_loses_confirmation():
            reads.append(1)
            return False if len(reads) <= 2 else None
        self.queue.stop_requested = stop_loses_confirmation
        effects = []
        self.queue.submit_source(self.scope, self.task_id,
                                 lambda: effects.append('unauthorized') or {'status': 'DONE'})
        self.queue._thread.join(timeout=3)
        self.assertFalse(self.queue._thread.is_alive())
        self.assertEqual(effects, [])
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'HOLD')

    def test_worker_rejects_boolean_stop_epoch_before_claim(self):
        self.queue.stop_epoch = lambda: True
        with self.assertRaisesRegex(NativeQueueHold, 'NATIVE_STOP_EPOCH_INVALID'):
            self.queue.submit_source(self.scope, self.task_id, lambda: {'status': 'DONE'})
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'QUEUED')


class ForgeDurableResultAdmissionTests(unittest.TestCase):
    """Real SQLite audit: reject unbound/misleading QLoRA results before commit."""

    def setUp(self):
        self.store = AuditStore()
        self.addCleanup(self.store.conn.close)
        self.scope = SimpleNamespace(tenant='local', principal='owner', chat_id='chat')
        self.epoch = 7
        self.queue = NativeWorkQueue(
            SimpleNamespace(call=lambda f: f(self.store)),
            authorize=lambda scope, permission, payload: True,
            stop_requested=lambda: False, stop_epoch=lambda: self.epoch)
        self.task_id = self.queue.enqueue(
            self.scope, kind='FORGE',
            payload={'task': 'real-original-P04', 'run_id': 'qlora-run-1'},
            permission='training.start')

    def audit_count(self):
        return self.store.conn.execute(
            "SELECT COUNT(*) FROM audit WHERE action='NOX_NATIVE_WORK_RESULT'"
        ).fetchone()[0]

    def put(self, state, result, permission='training.start'):
        return self.queue.record(
            self.scope, self.task_id, state, result,
            expected_epoch=self.epoch, permission=permission)

    def candidate(self, **override):
        result = {'status': 'ADAPTER_CANDIDATE_PENDING_E07',
                  'run_id': 'qlora-run-1', 'receipt_sha256': 'a'*64,
                  'weights_updated': False, 'activation_allowed': False}
        result.update(override)
        return result

    def test_status_mismatch_cannot_be_recorded(self):
        with self.assertRaisesRegex(NativeQueueHold, 'S03_RESULT_STATUS_BINDING_HOLD'):
            self.put('ADAPTER_CANDIDATE_PENDING_E07',
                     self.candidate(status='COMPLETED'))
        self.assertEqual(self.audit_count(), 0)

    def test_forged_or_unbound_training_result_cannot_be_recorded(self):
        self.claim()
        variants = [
            ('COMPLETED', self.candidate(status='COMPLETED')),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(run_id='other-run')),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(receipt_sha256='bad')),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(receipt_sha256='A'*64)),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(weights_updated=True)),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(activation_allowed=True)),
            ('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(activation_allowed=None)),
        ]
        for state, result in variants:
            with self.subTest(state=state, result=result):
                with self.assertRaisesRegex(NativeQueueHold, 'S03_FORGE_RESULT_ADMISSION_HOLD'):
                    self.put(state, result)
                self.assertEqual(self.audit_count(), 0)

    def claim(self, permission='training.start'):
        # Fixture mirrors the original durable claim, not a UI ACK.
        self.queue.actor.call(lambda store: self.queue._event(
            store, self.task_id, 'CLAIM', {
                'scope': {'tenant': 'local', 'principal': 'owner', 'chat_id': 'chat'},
                'state': 'RUNNING', 'permission': permission}))

    def test_unclaimed_receipt_shape_cannot_fake_training_result(self):
        before = self.audit_count()
        with self.assertRaisesRegex(NativeQueueHold, 'S03_FORGE_UNCLAIMED_RESULT_HOLD'):
            self.put('ADAPTER_CANDIDATE_PENDING_E07', self.candidate())
        self.assertEqual(self.audit_count(), before)
        self.assertEqual(self.queue.get(self.scope, self.task_id)['state'], 'QUEUED')

    def test_other_permission_claim_does_not_authorize_resume_result(self):
        self.claim('training.start')
        with self.assertRaisesRegex(NativeQueueHold, 'S03_FORGE_UNCLAIMED_RESULT_HOLD'):
            self.put('ADAPTER_CANDIDATE_PENDING_E07', self.candidate(),
                     permission='training.resume')
        self.assertEqual(self.audit_count(), 0)

    def test_exact_owner_p04_receipt_remains_candidate_only(self):
        self.claim()
        self.assertTrue(self.put('ADAPTER_CANDIDATE_PENDING_E07', self.candidate()))
        row = self.queue.get(self.scope, self.task_id)
        self.assertEqual(row['state'], 'ADAPTER_CANDIDATE_PENDING_E07')
        self.assertEqual(row['result']['receipt_sha256'], 'a'*64)
        self.assertIs(row['result']['activation_allowed'], False)
        self.assertEqual(self.audit_count(), 1)

    def test_forge_result_cannot_smuggle_nonboolean_activation_even_if_hold(self):
        for flag in (True, 1, "approved", None):
            for state in ('HOLD', 'MERGED_CANDIDATE_PENDING_IMPORT'):
                with self.subTest(state=state, activation=flag):
                    result = {'status': state, 'weights_updated': False,
                              'activation_allowed': flag}
                    with self.assertRaisesRegex(NativeQueueHold, 'S03_FORGE_RESULT_ADMISSION_HOLD'):
                        self.put(state, result, permission='training.merge')
                    self.assertEqual(self.audit_count(), 0)

    def test_merge_claim_without_exact_original_sha_receipts_is_not_result(self):
        # Tests S03 admission after a matching CLAIM only; native
        # submit_followup independently checks prior training and consent.
        self.claim('training.merge')
        good = {'status': 'MERGED_CANDIDATE_PENDING_IMPORT',
                'merge_receipt_sha256': 'a'*64,
                'merged_payload_sha256': 'b'*64,
                'weights_updated': False, 'activation_allowed': False}
        invalid = [
            {'status': 'MERGED_CANDIDATE_PENDING_IMPORT',
             'weights_updated': False, 'activation_allowed': False},
            {**good, 'merge_receipt_sha256': None},
            {**good, 'merge_receipt_sha256': 'A'*64},
            {**good, 'merged_payload_sha256': 'not-a-sha'},
            {**good, 'merged_payload_sha256': 1},
            {**good, 'status': 'COMPLETED'},
        ]
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaisesRegex(NativeQueueHold, 'S03_FORGE_MERGE_RECEIPT_BINDING_HOLD'):
                    self.put(row['status'], row, permission='training.merge')
                self.assertEqual(self.audit_count(), 0)
        self.assertTrue(self.put('MERGED_CANDIDATE_PENDING_IMPORT', good, permission='training.merge'))
        self.assertEqual(self.audit_count(), 1)
        self.assertIs(self.queue.get(self.scope, self.task_id)['result']['activation_allowed'], False)

    def test_error_hold_keeps_original_fail_closed_record(self):
        self.assertTrue(self.queue.record(
            self.scope, self.task_id, 'HOLD',
            {'status':'HOLD','reason':'NATIVE_STOP','weights_updated':False}))
        self.assertEqual(self.queue.get(self.scope,self.task_id)['state'], 'HOLD')
        self.assertEqual(self.audit_count(), 1)


if __name__ == '__main__':
    unittest.main()
