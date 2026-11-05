"""Original OneHost/S03 result audit owner/STOP fence, no Windows E07 claim."""
import json
import sqlite3
import unittest
from types import SimpleNamespace
from src.nox_selfbuilder.onehost_queue import NativeWorkQueue, NativeQueueHold


class AuditStore:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
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

    def test_unfenced_hold_with_positive_result_rejected(self):
        with self.assertRaisesRegex(PermissionError, 'NATIVE_RESULT_OWNER_FENCE_REQUIRED'):
            self.queue.record(self.scope, self.task_id, 'HOLD',
                              {'status': 'DONE', 'weights_updated': False})
        self.assertEqual(self.count(), 0)

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


if __name__ == '__main__':
    unittest.main()
