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
binding.encoded = lambda data: json.dumps(
    data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
binding.digest = lambda data: hashlib.sha256(data).hexdigest()
s03_calls = []
def readback(receipt):
    s03_calls.append(receipt)
    return {'receipt_sha256': binding.digest(binding.encoded(receipt)),
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
                'owner_claim': {'nonce': 'pinned-claim'}}
        worker = {'task_id': task['id'], 'parent_task_id': task['parent_task_id'],
                  'queue_id': task['queue_id'], 'state': 'INTEGRATED',
                  'project_source_changed': True, 'integration_verified': True,
                  'original_task_accepted': False, 'tests': {'passed': True}}
        receipt = {'task_id': task['id'], 'parent_task_id': task['parent_task_id'],
                   'queue_id': task['queue_id'],
                   'phase': 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED',
                   'claim': task['owner_claim'], 'original_task_accepted': False,
                   'source_sha256': 'pinned-source', 'scope': 'SOURCE_PATCH_TESTED',
                   'project_source_changed': True, 'recovery_required': False,
                   'worker_result': {'project_evidence': worker}}
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
                ('blocked_worker', {'worker_result': {
                    'project_evidence': {**worker, 'state': 'BLOCKED'}}}),
                ('nested_original_falsely_accepted', {'worker_result': {
                    'project_evidence': {**worker, 'original_task_accepted': True}}}),
                ('failed_test', {'worker_result': {
                    'project_evidence': {**worker, 'tests': {'passed': False}}}}),
                ('wrong_task', {'worker_result': {
                    'project_evidence': {**worker, 'task_id': 'other-task'}}}),
                ('missing_worker', {'worker_result': None}),
                ('malformed_tests_list', {'worker_result': {
                    'project_evidence': {**worker, 'tests': [{'passed': True}]}}}),
                ('malformed_tests_string', {'worker_result': {
                    'project_evidence': {**worker, 'tests': 'passed'}}}),
            ):
                with self.subTest(label=label):
                    bad = {**receipt, **changes}
                    signed = {'receipt': bad,
                              'receipt_sha256': binding.digest(binding.encoded(bad))}
                    self.assertIsNone(subject.verify(task, signed))
            self.assertEqual(len(s03_calls), 1,
                'Contradictory integrated receipts must not even attempt S03 acceptance.')

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


if __name__ == '__main__':
    unittest.main()
