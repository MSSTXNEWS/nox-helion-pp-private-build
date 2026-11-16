import contextlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import types
import unittest
from unittest.mock import patch, Mock

import owner_subagent_dispatcher as module
from owner_subagent_processes import GateError


class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory()
        self.root = Path(self.area.name)
        self.policy = self.root/'state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md'
        self.policy.parent.mkdir(parents=True)
        self.policy.write_text('# NOX WEB29 + WEIGHTS · MASTER V06\nPolicy ID: NOX_WEB_WEIGHTS_V06\n'
                               '1C: dispatcher scope\n2B: S03 scope\n2D: training scope\n'+'unchanged policy data\n'*1000)
        self.reference = {'path': str(self.policy), 'sha256': module.digest(self.policy.read_bytes())}
        self.db = self.root/'kb/knowledge.sqlite'
        self.db.parent.mkdir()
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,salience REAL,ts TEXT,meta TEXT)')
            conn.execute('CREATE TABLE s03_fts(id TEXT,text TEXT,segment TEXT)')
        self.patches = contextlib.ExitStack()
        for key, value in [('ROOT', self.root), ('POLICY', self.policy), ('DB', self.db)]:
            self.patches.enter_context(patch.object(module, key, value))

    def tearDown(self):
        self.patches.close()
        self.area.cleanup()

    def receipt(self):
        return {'schema': module.RECEIPT, 'phase': 'QUEUE_ADMITTED_NOT_EXECUTED',
                'task_id': 'owner.native.runtime', 'job_id': 'nox-native-abc',
                'policy_sha256': self.reference['sha256'], 'source_sha256': 'a'*64}

    def write_memory(self, receipt, alter=False):
        text = module.memory_text(receipt)
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)',
                         ('existing-item', 'M2', text, 'owner_native_subagents',
                          module.digest(('M2|'+text).encode()), .1, 'now',
                          json.dumps({'receipt': {**receipt, 'job_id': 'wrong'} if alter else receipt})))

    def test_full_19kb_policy_ack_and_bounded_model_excerpt(self):
        task = {'id': 'job.1', 'subagent': 'runtime', 'task': 'do not execute this text',
                '_native_context': {'policy': self.reference, 'operation': 'runtime', 'claim': 'a'*24}}
        prompt, proof = module.worker_input(task)
        self.assertGreater(proof['policy_ack']['bytes_read'], 19000)
        self.assertEqual(proof['policy_ack']['sha256'], self.reference['sha256'])
        self.assertTrue(proof['policy_ack']['full_file_read'])
        self.assertLess(len(prompt['task'].encode()), 8192)
        self.assertNotIn('do not execute this text', prompt['task'])
        self.assertFalse(proof['facts']['training_or_services_changed'])

    def test_policy_rejects_changed_hash_other_path_and_symlink(self):
        for ref in ({**self.reference, 'sha256': 'b'*64},
                    {**self.reference, 'path': str(self.root/'other.md')}):
            with self.assertRaises(GateError):
                module.load_policy(ref)
        self.policy.unlink()
        self.policy.symlink_to(self.root/'missing')
        with self.assertRaisesRegex(GateError, 'PATH'):
            module.load_policy(self.reference)

    def test_no_arbitrary_operation_or_model_owned_command(self):
        with self.assertRaisesRegex(GateError, 'NATIVE_CONTEXT'):
            module.worker_input({'subagent': 'runtime', '_native_context': {
                'policy': self.reference, 'operation': 'shell', 'claim': 'a'*24}})

    def test_s03_exact_persisted_receipt_in_original_table(self):
        receipt = self.receipt()
        self.assertIsNone(module.s03_readback(receipt))
        self.write_memory(receipt)
        proof = module.s03_readback(receipt)
        self.assertTrue(proof['native_verified'])
        self.assertEqual(proof['s03_item_id'], 'existing-item')
        self.assertEqual(proof['phase'], 'QUEUE_ADMITTED_NOT_EXECUTED')
        with sqlite3.connect(self.db) as conn:
            self.assertEqual({x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                             {'s03_items', 's03_fts'})

    def test_model_claim_or_wrong_metadata_is_not_s03_proof(self):
        receipt = self.receipt()
        self.write_memory(receipt, alter=True)
        self.assertIsNone(module.s03_readback(receipt))

    def test_native_segment_hash_required_and_other_segment_cannot_shadow_receipt(self):
        receipt = self.receipt()
        self.write_memory(receipt)
        text = module.memory_text(receipt)
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO s03_items VALUES(?,?,?,?,?,?,?,?)',
                ('other-segment', 'M1', text, 'owner_native_subagents',
                 module.digest(('M1|'+text).encode()), .1, 'now', json.dumps({'receipt': receipt})))
        self.assertEqual(module.s03_readback(receipt)['s03_item_id'], 'existing-item')
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE s03_items SET sha256=? WHERE id='existing-item'", (module.digest(text.encode()),))
        self.assertIsNone(module.s03_readback(receipt))

    def test_ambiguous_http_is_read_back_and_not_posted_twice(self):
        receipt = self.receipt()
        def ambiguous(*args, **kwargs):
            self.write_memory(receipt)
            raise OSError('connection closed after commit')
        opener = Mock()
        opener.open.side_effect = ambiguous
        with patch.object(module.urllib.request, 'build_opener', return_value=opener):
            proof = module.remember(receipt)
            again = module.remember(receipt)
        self.assertEqual(proof, again)
        self.assertEqual(opener.open.call_count, 1)

    def test_failed_http_cannot_be_marked_verified(self):
        opener = Mock()
        opener.open.side_effect = OSError('offline')
        with patch.object(module.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(GateError, 'WRITE_UNVERIFIED'):
                module.remember(self.receipt())
        self.assertEqual(opener.open.call_count, 1)

    def test_exact_native_patch_preserves_existing_scheduler_and_bindings(self):
        source = 'import owner_task_lifecycle\nowner_task_lifecycle.bind_dispatcher(globals(), {})\ndef main():\n    pass\nif __name__ == "__main__":\n    main()\n'
        after = module.patch_dispatcher(source, module.digest(source.encode()))
        self.assertEqual(after.count('owner_subagent_dispatcher.bind_dispatcher(globals())'), 1)
        self.assertIn('owner_task_lifecycle.bind_dispatcher(globals(), {})', after)
        with self.assertRaisesRegex(GateError, 'SOURCE_CHANGED'):
            module.patch_dispatcher(after, module.digest(after.encode()))

    def test_admission_failure_is_durable_blocked_never_done_or_blind_replay(self):
        state_path = self.root/'state/dispatcher/state.json'
        state = {'tasks': {}}
        native = object.__new__(module.Native)
        native.ns = {'_qlock': threading.RLock(), 'STATE': state_path,
                     'save_state': lambda value: state_path.write_text(json.dumps(value))}
        native.state = state
        native.policy = self.reference
        native.source = 'c'*64
        native.admissions = {}
        native.process_readback = lambda: [{'pid': pid} for pid in (10, 11, 12)]
        task = {'id': 'owner.native.review', 'handler': module.HANDLER, 'params': {'role': 'runtime'},
                'source_sha256': self.reference['sha256'], 'deps': [], 'title': 'Runtime review'}
        with patch.object(module, 'remember', side_effect=GateError('HOLD_SUBAGENT_S03_WRITE_UNVERIFIED')) as remember:
            with self.assertRaises(GateError):
                native.native_queue_claim(task, [10, 11, 12])
            self.assertTrue(native.native_duplicate_check(task['id']))
            with self.assertRaisesRegex(GateError, 'DUPLICATE_TASK'):
                native.native_queue_claim(task, [10, 11, 12])
        row = json.loads(state_path.read_text())['tasks'][task['id']]
        self.assertEqual(row['status'], 'blocked')
        self.assertEqual(row['note'], 'WAIT_S03_ADMISSION_READBACK')
        self.assertEqual(remember.call_count, 1)

    def test_current_claim_checks_original_director_pid_and_nonce(self):
        task = {'id': 'owner.native.review', 'status': 'running',
                'owner_claim': {'nonce': 'a'*24, 'pid': os.getpid()}}
        state_path = self.root/'state/dispatcher/state.json'
        state_path.write_text(json.dumps({'tasks': {task['id']: task}}))
        native = object.__new__(module.Native)
        native.ns = {'_qlock': threading.RLock(), 'STATE': state_path}
        native.state = {'tasks': {task['id']: task}}
        self.assertTrue(native._claim_current(task, durable=True))
        changed = json.loads(state_path.read_text())
        changed['tasks'][task['id']]['owner_claim']['nonce'] = 'b'*24
        state_path.write_text(json.dumps(changed))
        self.assertFalse(native._claim_current(task, durable=True))

    def execution_fixture(self):
        task = {'id': 'owner.native.runtime', 'title': 'Runtime review', 'status': 'running',
                'owner_claim': {'nonce': 'a'*24, 'pid': os.getpid()},
                'params': {'role': 'runtime', 'policy_sha256': self.reference['sha256'], 'job_id': 'nox-native-abc'}}
        native = object.__new__(module.Native)
        native.lock = threading.RLock()
        native.policy = self.reference
        native.catalog = {'tasks': [{'id': task['id'], 'params': {'role': 'runtime'}}]}
        native.source = 'c'*64
        native.completed = {}
        native.interrupted = {}
        native.ns = {'owner_mentor': types.SimpleNamespace(clean=lambda value: value)}
        native._claim_current = Mock(return_value=True)
        native.stop_active = Mock(return_value=False)
        native.writer_lease = Mock(return_value=True)
        event = {'id': task['id'], 'pid': 123, 'state': 'CANDIDATE_NOT_APPLIED', 'answer': 'Fixture candidate',
                 'native_observation': {'claim': 'a'*24, 'worker': {'pid': 123},
                    'policy_ack': {'sha256': self.reference['sha256'], 'full_file_read': True}}}
        native._drain = lambda: native.completed.update({task['id']: event})
        native.pool = Mock()
        native.pool.active = {'runtime': task['id']}
        native.pool.__exit__ = Mock()
        return native, task

    def test_temporary_chat_yield_waits_then_same_queue_task_can_resume(self):
        native, task = self.execution_fixture()
        with patch.object(module, 'chat_priority_active', return_value=True), \
             patch.object(module, 'remember') as remember:
            state, note = native._handle(task)
        self.assertEqual(state, 'wait')
        self.assertEqual(note, 'WAIT_OWNER_STOP_OR_CHAT_PRIORITY')
        self.assertIsNone(native.pool)
        remember.assert_not_called()
        native.pool = Mock()
        native.pool.active = {}
        with patch.object(module, 'chat_priority_active', return_value=False), \
             patch.object(module, 'remember', return_value={'native_verified': True}):
            state, result = native._handle(task)
        self.assertIs(state, True)
        self.assertFalse(result['candidate_applied'])

    def test_ambiguous_result_write_is_blocked_not_automatic_wait(self):
        native, task = self.execution_fixture()
        with patch.object(module, 'chat_priority_active', return_value=False), \
             patch.object(module, 'remember', side_effect=GateError('HOLD_SUBAGENT_S03_WRITE_UNVERIFIED')) as remember:
            state, note = native._handle(task)
        self.assertIs(state, False)
        self.assertEqual(note, 'HOLD_SUBAGENT_S03_WRITE_UNVERIFIED')
        self.assertEqual(remember.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
