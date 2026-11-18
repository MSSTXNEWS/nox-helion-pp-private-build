"""Focused native-queue contracts. S03 transport is represented by exact receipts."""
import copy
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import owner_project_executor as executor
from owner_project_native import ProjectBinding
import owner_subagent_dispatcher as binding
from owner_subagent_processes import GateError
from test_owner_project_executor import config_for, plan_for, FIXED


class Mentor:
    @staticmethod
    def clean(value):
        return copy.deepcopy(value)


class NativeProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        cfg = config_for(Path(self.temp.name))
        self.native = binding.Native.__new__(binding.Native)
        native = self.native
        native.config = {'project_executor':cfg, 'execution_mode':binding.PROJECT_MODE}
        native.source = executor.digest((Path(__file__).parent / 'owner_subagent_dispatcher.py').read_bytes())
        native.lock = threading.RLock()
        native.ns = {'_qlock':threading.RLock(), 'save_state':lambda value:None, 'owner_mentor':Mentor()}
        native.state = {'tasks':{}}
        native.pool = None
        native.admissions = {}
        native.process_readback = lambda:[{'pid':pid} for pid in (101,102,103)]
        native.stop_active = lambda:False
        native.owner_allowed = lambda:True
        native.writer_lease = lambda:True
        native._claim_current = lambda task, durable=False:True
        native.projects = ProjectBinding(native)
        self.tasks = []
        for number in range(4):
            plan, blobs = plan_for(cfg, number=number)
            reference = executor.materialize_plan(plan, blobs, cfg)
            raw = {'id':plan['task_id'], 'handler':executor.PROJECT_HANDLER,
                   'source_sha256':native.source, 'queue_id':plan['queue_id'],
                   'params':{'parent_task_id':plan['parent_task_id'], **reference}}
            self.tasks.append(binding.autonomy._task(raw, native.allowed_handlers()))
        native.catalog = {'schema':binding.autonomy.SCHEMA, 'tasks':self.tasks}
        self.receipts = {}
        def remember(value):
            sha = executor.digest(executor.encoded(value))
            self.receipts[sha] = copy.deepcopy(value)
            return {'receipt_sha256':sha, 's03_item_id':'unit-' + sha[:12]}
        def readback(value):
            sha = executor.digest(executor.encoded(value))
            return {'receipt_sha256':sha, 's03_item_id':'unit-' + sha[:12]} if self.receipts.get(sha) == value else None
        self.addCleanup(patch.stopall)
        patch.object(binding, 'remember', side_effect=remember).start()
        patch.object(binding, 's03_readback', side_effect=readback).start()

    def test_pending_claims_consume_global_three_slots(self):
        for task in self.tasks[:3]:
            self.native.projects.claim(task, [101,102,103])
        rows = list(self.native.state['tasks'].values())
        self.assertEqual([row['native_queue_sequence'] for row in rows], [1,2,3])
        self.assertTrue(all(row['status'] == 'pending' for row in rows))
        with self.assertRaisesRegex(GateError, 'GLOBAL_WORKER_CAP'):
            self.native.projects.claim(self.tasks[3], [101,102,103])
        self.assertEqual(len(self.native.state['tasks']), 3)

    def test_only_durable_inactive_blocked_result_releases_capacity(self):
        task = self.tasks[0]
        self.native.projects.claim(task, [101,102,103])
        row = self.native.state['tasks'][task['id']]
        row.update(status='running', owner_claim={'nonce':'a' * 24, 'pid':os.getpid()})
        evidence = {'schema':executor.EVIDENCE_SCHEMA, 'task_id':row['id'],
                    'parent_task_id':row['parent_task_id'], 'queue_id':row['queue_id'],
                    'plan_sha256':row['params']['plan_sha256'], 'original_task_accepted':False,
                    'acceptance_scope':'SOURCE_PATCH_TESTED', 'state':'FAILED_TESTS',
                    'project_source_changed':False}
        event = {'project_evidence':evidence,
                 'project_evidence_sha256':executor.digest(executor.encoded(evidence))}
        ok, info = self.native.projects._finish(row, event, 'a' * 24)
        self.assertFalse(ok)
        self.assertFalse(self.native.projects.terminal_for_capacity(row))
        row['status'] = 'blocked'
        self.assertTrue(self.native.projects.terminal_for_capacity(row))
        self.assertFalse(self.native.projects.admitted(row))
        self.assertFalse(info['original_task_accepted'])
        self.native.projects.terminal_cache.clear()
        self.receipts.clear()
        self.assertFalse(self.native.projects.terminal_for_capacity(row))

    def test_uncertain_rollback_keeps_reservation(self):
        task = self.tasks[0]
        self.native.projects.claim(task, [101,102,103])
        row = self.native.state['tasks'][task['id']]
        row.update(status='running', owner_claim={'nonce':'a' * 24, 'pid':os.getpid()})
        evidence = {'schema':executor.EVIDENCE_SCHEMA, 'task_id':row['id'],
                    'parent_task_id':row['parent_task_id'], 'queue_id':row['queue_id'],
                    'plan_sha256':row['params']['plan_sha256'], 'original_task_accepted':False,
                    'acceptance_scope':'SOURCE_PATCH_TESTED', 'state':'HOLD_RECOVERY_REQUIRED',
                    'project_source_changed':False}
        event = {'project_evidence':evidence,
                 'project_evidence_sha256':executor.digest(executor.encoded(evidence))}
        ok, _ = self.native.projects._finish(row, event, 'a' * 24)
        self.assertFalse(ok)
        row['status'] = 'blocked'
        self.assertFalse(self.native.projects.terminal_for_capacity(row))

    def test_existing_native_handler_runs_worker_applies_and_reads_exact_receipt(self):
        native = self.native
        native.completed, native.interrupted = {}, {}
        native._fresh_admission_reason = lambda **kwargs:None
        native.process_readback = binding.Native.process_readback.__get__(native)
        self.addCleanup(native.close_pool)
        self.assertTrue(native.ensure_processes(3))
        before = {row['role']:row['pid'] for row in native.process_readback()}
        native.projects.claim(self.tasks[0], list(before.values()))
        row = native.state['tasks'][self.tasks[0]['id']]
        row.update(status='running', owner_claim={'nonce':'c' * 24, 'pid':os.getpid()})
        ok, info = native._handle(row)
        self.assertTrue(ok, info)
        source = Path(native.projects.config['roots']['TEST_SOURCE']['path']) / 'source.py'
        self.assertEqual(source.read_bytes(), FIXED)
        self.assertEqual(info['receipt']['phase'], 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED')
        self.assertIsNotNone(native.verify(row, info))
        self.assertFalse(info['original_task_accepted'])
        self.assertEqual(before, {row['role']:row['pid'] for row in native.process_readback()})


if __name__ == '__main__':
    unittest.main()
