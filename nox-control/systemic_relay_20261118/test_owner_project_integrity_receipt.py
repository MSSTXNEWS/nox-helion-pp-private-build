"""One focused proof for TaskID 4V14-07: never accept contradictory S03 project receipts.

Source-only; does not start a worker, mutate a queue or access the server.
Run from systemic_relay_20261118/: python -m unittest test_owner_project_integrity_receipt
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parent / 'runtime' / 'owner_project_native.py'
executor = types.ModuleType('owner_project_executor')
executor.PROJECT_HANDLER = 'owner_native_project_work'
subprocesses = types.ModuleType('owner_subagent_processes')
class GateError(RuntimeError):
    pass
subprocesses.GateError = GateError
binding = types.ModuleType('owner_subagent_dispatcher')
binding.RECEIPT = 'NOX_TEST_RECEIPT'
binding.encoded = lambda data: json.dumps(
    data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
binding.digest = lambda data: hashlib.sha256(data).hexdigest()
s03_calls = []
def readback(receipt):
    s03_calls.append(receipt)
    return {'native_verified': True, 'task_id': receipt['task_id'],
            'job_id': receipt['job_id'],
            'receipt_sha256': binding.digest(binding.encoded(receipt)),
            's03_item_id': 'S03-TEST'}
binding.s03_readback = readback

with patch.dict(sys.modules, {
        'owner_project_executor': executor,
        'owner_subagent_processes': subprocesses,
        'owner_subagent_dispatcher': binding}):
    spec = importlib.util.spec_from_file_location('a4_project_integrity', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


class ProjectReceiptIntegrityTest(unittest.TestCase):
    def test_one_integrated_receipt_cannot_forge_source_acceptance(self):
        task = {'id': '4V14-07', 'parent_task_id': '4V14',
                'queue_id': 'Q4_INTEGRATION_ACCEPTANCE',
                'params': {'job_id': 'job-4V14-07', 'plan_sha256': 'pinned-plan',
                           'contract_sha256': 'pinned-contract'},
                'owner_claim': {'nonce': 'pinned-claim'}}
        worker = {'task_id': task['id'], 'parent_task_id': task['parent_task_id'],
                  'queue_id': task['queue_id'], 'state': 'INTEGRATED',
                  'plan_sha256': task['params']['plan_sha256'],
                  'contract_sha256': task['params']['contract_sha256'],
                  'acceptance_scope': 'SOURCE_PATCH_TESTED',
                  'project_source_changed': True, 'integration_verified': True,
                  'original_task_accepted': False, 'tests': {'passed': True}}
        def worker_result(item):
            return {'project_evidence': item,
                    'project_evidence_sha256': binding.digest(binding.encoded(item))}

        receipt = {'task_id': task['id'], 'parent_task_id': task['parent_task_id'],
                   'queue_id': task['queue_id'],
                   'job_id': task['params']['job_id'],
                   'plan_sha256': task['params']['plan_sha256'],
                   'phase': 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED',
                   'claim': task['owner_claim'], 'original_task_accepted': False,
                   'source_sha256': 'pinned-source', 'scope': 'SOURCE_PATCH_TESTED',
                   'project_source_changed': True, 'recovery_required': False,
                   'worker_result': worker_result(worker)}
        native = types.SimpleNamespace(
            receipt_source_allowed=lambda *_: True)
        subject = module.ProjectBinding.__new__(module.ProjectBinding)
        subject.native = native
        s03_calls.clear()

        valid = {'receipt': receipt,
                 'receipt_sha256': binding.digest(binding.encoded(receipt))}
        with patch.dict(sys.modules, {'owner_subagent_dispatcher': binding}):
            self.assertTrue(subject.verify(task, valid)['project_source_changed'])
            self.assertEqual(len(s03_calls), 1)

            for label, changes in (
                ('false_source', {'project_source_changed': False}),
                ('recovering', {'recovery_required': True}),
                ('wrong_job', {'job_id': 'another-job'}),
                ('wrong_plan', {'plan_sha256': 'another-plan'}),
                ('wrong_worker_plan', {'worker_result': worker_result({**worker, 'plan_sha256': 'another-plan'})}),
                ('wrong_worker_contract', {'worker_result': worker_result({**worker, 'contract_sha256': 'another-contract'})}),
                ('wrong_worker_scope', {'worker_result': worker_result({**worker, 'acceptance_scope': 'OTHER'})}),
                ('blocked_worker', {'worker_result': worker_result({**worker, 'state': 'BLOCKED'})}),
                ('nested_original_falsely_accepted', {'worker_result': worker_result({**worker, 'original_task_accepted': True})}),
                ('failed_test', {'worker_result': worker_result({**worker, 'tests': {'passed': False}})}),
                ('wrong_task', {'worker_result': worker_result({**worker, 'task_id': 'other-task'})}),
                ('nested_digest_mismatch', {'worker_result': {
                    **worker_result(worker), 'project_evidence_sha256': '0' * 64}}),
                ('missing_worker', {'worker_result': None}),
                ('malformed_tests_list', {'worker_result': worker_result({**worker, 'tests': [{'passed': True}]})}),
                ('malformed_tests_string', {'worker_result': worker_result({**worker, 'tests': 'passed'})}),
            ):
                with self.subTest(label=label):
                    bad = {**receipt, **changes}
                    signed = {'receipt': bad,
                              'receipt_sha256': binding.digest(binding.encoded(bad))}
                    self.assertIsNone(subject.verify(task, signed))
            self.assertEqual(len(s03_calls), 1,
                'Contradictory integrated receipts must not even attempt S03 acceptance.')

            # A truthy but incorrect S03 witness is not durable acceptance.
            for wrong in ({'receipt_sha256': '0' * 64},
                          {'task_id': 'another-task'},
                          {'job_id': 'another-job'},
                          {'native_verified': False},
                          {'s03_item_id': ''}):
                proof = {**readback(receipt), **wrong}
                with self.subTest(s03_mismatch=wrong):
                    with patch.object(binding, 's03_readback', return_value=proof):
                        self.assertIsNone(subject.verify(task, valid))
            # Only the legitimate witness may authenticate this exact receipt.
            self.assertTrue(subject.verify(task, valid)['project_source_changed'])

            inconsistent = {**worker, 'project_source_changed': False}
            event = {'project_evidence': inconsistent,
                     'project_evidence_sha256': binding.digest(binding.encoded(inconsistent))}
            with self.assertRaisesRegex(GateError, 'HOLD_PROJECT_INTEGRATION_PROOF'):
                subject._finish(task, event, 'pinned-claim')

            for malformed in ([{'passed': True}], 'passed', True):
                with self.subTest(malformed_tests=repr(malformed)):
                    invalid = {**worker, 'tests': malformed}
                    invalid_event = {'project_evidence': invalid,
                        'project_evidence_sha256': binding.digest(binding.encoded(invalid))}
                    with self.assertRaisesRegex(GateError, 'HOLD_PROJECT_INTEGRATION_PROOF'):
                        subject._finish(task, invalid_event, 'pinned-claim')

            # Clean/sanitize is an untrusted transformation: it may shorten
            # presentation fields but cannot rewrite the signed verdict.
            for changed in ({'state': 'BLOCKED'},
                            {'project_source_changed': False},
                            {'original_task_accepted': True},
                            {'tests': {'passed': False}}):
                with self.subTest(sanitized_change=changed):
                    before = worker_result(worker)
                    after = {**before, 'project_evidence': {**worker, **changed}}
                    fake = types.SimpleNamespace(ns={
                        'owner_mentor': types.SimpleNamespace(clean=lambda _value: after)})
                    subject.native = fake
                    with self.assertRaisesRegex(GateError, 'HOLD_PROJECT_SANITIZED_EVIDENCE'):
                        subject._finish(task, before, 'pinned-claim')

            # The sanitizer can return its input object after mutating it:
            # comparing post-clean objects to one another is not a proof.
            for changed in ({'state': 'BLOCKED'},
                            {'acceptance_scope': 'FORGED'},
                            {'tests': {'passed': True, 'failed': 2}}):
                with self.subTest(in_place_sanitized_change=changed):
                    before = worker_result(copy.deepcopy(worker))
                    def mutate_same_event(value, delta=changed):
                        value['project_evidence'].update(delta)
                        return value
                    subject.native = types.SimpleNamespace(ns={
                        'owner_mentor': types.SimpleNamespace(clean=mutate_same_event)})
                    with self.assertRaisesRegex(GateError, 'HOLD_PROJECT_SANITIZED_EVIDENCE'):
                        subject._finish(task, before, 'pinned-claim')


    def test_blocked_terminal_capacity_needs_exact_durable_witness(self):
        """A truthy S03 result for a different job cannot free this worker slot."""
        task = {'id': '4V14-07', 'status': 'blocked',
                'owner_claim': {'nonce': 'claim-4V14-07'}}
        receipt = {'task_id': task['id'], 'job_id': 'job-4V14-07',
                   'phase': 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
                   'original_task_accepted': False, 'claim': task['owner_claim'],
                   'worker_result': {'project_evidence': {
                       'state': 'BLOCKED_SOURCE_CHANGED'}}}
        sha = binding.digest(binding.encoded(receipt))
        task['native_project_terminal'] = {'receipt': receipt,
                                           'receipt_sha256': sha}
        subject = module.ProjectBinding.__new__(module.ProjectBinding)
        subject.native = types.SimpleNamespace(
            pool=None, receipt_source_allowed=lambda *_: True)
        subject.terminal_cache = set()
        good = {'native_verified': True, 'task_id': task['id'],
                'job_id': receipt['job_id'], 'receipt_sha256': sha,
                's03_item_id': 'S03-CAPACITY-TEST'}
        with patch.dict(sys.modules, {'owner_subagent_dispatcher': binding}):
            with patch.object(executor, 'TERMINAL_WITHOUT_CHANGES',
                              {'BLOCKED_SOURCE_CHANGED'}, create=True):
                for invalid in (True, {'native_verified': True},
                                {**good, 'task_id': 'another-task'},
                                {**good, 'job_id': 'another-job'},
                                {**good, 'receipt_sha256': '0' * 64},
                                {**good, 'native_verified': False},
                                {**good, 's03_item_id': ''}):
                    with self.subTest(invalid=invalid):
                        with patch.object(binding, 's03_readback',
                                          return_value=invalid):
                            self.assertFalse(subject.terminal_for_capacity(task))
                            self.assertNotIn(sha, subject.terminal_cache)
                with patch.object(binding, 's03_readback', return_value=good):
                    self.assertTrue(subject.terminal_for_capacity(task))
                    self.assertIn(sha, subject.terminal_cache)


    def test_reconcile_terminal_status_needs_exact_receipt_and_s03_witness(self):
        """Do not mark an unverified pending attempt as durably blocked."""
        from contextlib import nullcontext
        task = {'id': '4V14-07', 'handler': executor.PROJECT_HANDLER,
                'status': 'pending', 'owner_claim': {'nonce': 'claim-4V14-07'},
                'params': {'job_id': 'job-4V14-07', 'source_sha256': 'pinned-source'}}
        receipt = {'task_id': task['id'], 'job_id': task['params']['job_id'],
                   'phase': 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
                   'claim': task['owner_claim'], 'original_task_accepted': False}
        sha = binding.digest(binding.encoded(receipt))
        task['native_project_terminal'] = {'receipt': receipt, 'receipt_sha256': sha}
        saves = []
        native = types.SimpleNamespace(
            stop_active=lambda: False, owner_allowed=lambda: True,
            writer_lease=lambda: True, lock=nullcontext(), pool=None,
            source='pinned-source', state={'tasks': {task['id']: task}},
            ns={'_qlock': nullcontext(), 'save_state': lambda _state: saves.append(task['status'])},
            receipt_source_allowed=lambda *_args: True)
        subject = module.ProjectBinding.__new__(module.ProjectBinding)
        subject.native = native
        good = {'native_verified': True, 'task_id': task['id'],
                'job_id': receipt['job_id'], 'receipt_sha256': sha,
                's03_item_id': 'S03-EXACT'}
        with patch.dict(sys.modules, {'owner_subagent_dispatcher': binding}):
            for invalid in (True, {'native_verified': True},
                            {**good, 'task_id': 'other-task'},
                            {**good, 'job_id': 'other-job'},
                            {**good, 'receipt_sha256': '0' * 64},
                            {**good, 'native_verified': False},
                            {**good, 's03_item_id': ''}):
                with self.subTest(s03=repr(invalid)):
                    with patch.object(binding, 's03_readback', return_value=invalid):
                        subject.reconcile()
                    self.assertEqual(task['status'], 'pending')
                    self.assertFalse(saves)
            # A fabricated local SHA cannot initiate a trusted S03 check.
            task['native_project_terminal']['receipt_sha256'] = '0' * 64
            with patch.object(binding, 's03_readback', side_effect=AssertionError('untrusted S03 call')):
                subject.reconcile()
            self.assertEqual(task['status'], 'pending')
            task['native_project_terminal']['receipt_sha256'] = sha
            with patch.object(binding, 's03_readback', return_value=good):
                subject.reconcile()
            self.assertEqual(task['status'], 'blocked')
            self.assertEqual(saves, ['blocked'])


    def test_remember_ack_is_not_independent_s03_terminal_proof(self):
        """A write acknowledgement must not bypass the exact S03 readback gate."""
        from contextlib import nullcontext
        task = {'id': '4V14-07', 'parent_task_id': '4V14',
                'queue_id': 'Q4_INTEGRATION_ACCEPTANCE', 'status': 'blocked',
                'owner_claim': {'nonce': 'claim-4V14-07'},
                'params': {'job_id': 'job-4V14-07',
                           'plan_sha256': 'pinned-plan',
                           'contract_sha256': 'pinned-contract'}}
        worker = {'task_id': task['id'],
                  'parent_task_id': task['parent_task_id'],
                  'queue_id': task['queue_id'],
                  'plan_sha256': task['params']['plan_sha256'],
                  'contract_sha256': task['params']['contract_sha256'],
                  'claim': 'claim-4V14-07',
                  'acceptance_scope': 'SOURCE_PATCH_TESTED',
                  'state': 'STOPPED', 'original_task_accepted': False,
                  'project_source_changed': False,
                  'integration_verified': False}
        event = {'project_evidence': worker,
                 'project_evidence_sha256': binding.digest(binding.encoded(worker))}
        native = types.SimpleNamespace(
            source='pinned-source', state={}, pool=None,
            writer_lease=lambda: True,
            _claim_current=lambda *_args, **_kwargs: True,
            receipt_source_allowed=lambda *_args: True,
            ns={'_qlock': nullcontext(),
                'save_state': lambda _state: None,
                'owner_mentor': types.SimpleNamespace(clean=lambda value: value)})
        subject = module.ProjectBinding.__new__(module.ProjectBinding)
        subject.native = native
        subject.terminal_cache = set()
        with patch.dict(sys.modules, {'owner_subagent_dispatcher': binding}):
            with patch.object(binding, 'remember',
                              return_value={'write_ack': True}, create=True):
                integrated, info = subject._finish(task, event, 'claim-4V14-07')
            self.assertFalse(integrated)
            self.assertEqual(info['s03'], {'write_ack': True})
            self.assertNotIn(info['receipt_sha256'], subject.terminal_cache)
            # Even though the local worker reached STOPPED, an unrelated
            # readback cannot free its capacity.
            with patch.object(executor, 'TERMINAL_WITHOUT_CHANGES',
                              {'STOPPED'}, create=True):
                with patch.object(binding, 's03_readback',
                                  return_value={'native_verified': True,
                                                'task_id': 'other-task'}) as read:
                    self.assertFalse(subject.terminal_for_capacity(task))
                    read.assert_called_once()


if __name__ == '__main__':
    unittest.main()
