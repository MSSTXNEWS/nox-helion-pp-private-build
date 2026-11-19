"""Narrow privacy and association tests; no native services or HTTP calls."""
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('media_retry_observer_test', Path(__file__).with_name('owner_qwen_media_retry_observe.py'))
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.state = self.root / 'state'; self.state.mkdir()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for key, value in {'ROOT': self.root, 'STATE': self.state, 'LINK': self.state / 'media/retries/fixed.json', 'DEADLINE': None}.items():
            self.stack.enter_context(patch.object(M, key, value))

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(M.encoded(value))

    def test_fixed_map_and_job_projection_omit_private_fields(self):
        old, new = sorted(M.OLD)[0], 'a' * 32
        row = {'schema': 'NOX_QWEN_MEDIA_RETRY_V1', 'request': '123', 'source_sha': 'b' * 40,
               'state': 'TWO_REPLACEMENT_JOBS_SUBMITTED', 'private': 'PRIVATE_FIXTURE',
               'replacements': [{'old_job_id': old, 'new_job_id': new, 'kind': 'image',
                                 'state': 'SUBMITTED_GENERATION_PENDING', 'request_sha256': 'c' * 64}]}
        self.save(M.LINK, row)
        projection, ids = M.retry_map(); self.assertEqual(ids, {new})
        request = {'kind': 'image', 'prompt': 'PRIVATE_FIXTURE', 'negative_prompt': 'PRIVATE_NEGATIVE', 'seed': 5}
        self.save(self.state / 'media/jobs' / (new + '.json'), {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': new,
            'state': 'COMPLETED', 'owner': 'PRIVATE_OWNER', 'request': request,
            'generation_verified': True, 'gpu1_released': True, 'outputs': [{'filename': 'PRIVATE_FILENAME.png',
                'bytes': 123, 'sha256': 'd' * 64, 'width': 1024, 'height': 1024, 'subfolder': 'PRIVATE_PATH'}]})
        job, prompt = M.job_record(new)
        raw = M.encoded({'map': projection, 'job': job})
        for marker in (b'PRIVATE_FIXTURE', b'PRIVATE_NEGATIVE', b'PRIVATE_OWNER', b'PRIVATE_FILENAME', b'PRIVATE_PATH'):
            self.assertNotIn(marker, raw)
        self.assertIsNone(prompt); self.assertFalse(job['output_payload_read'])
        self.assertFalse(job['output_sha256_reverified']); self.assertEqual(job['outputs'][0]['bytes'], 123)
        self.assertTrue(job['generation_verified_recorded'])

    def test_only_related_plan_tasks_and_dependency_status_are_exported(self):
        job, plan = 'a' * 32, 'b' * 24
        generation, parent, branch = 'owner.media.' + job, 'owner.plan.media.' + job, 'owner.branch.' + plan + '.budget'
        tasks = {generation: {'id': generation, 'status': 'pending', 'handler': 'owner_media', 'owner_plan_id': plan,
                              'owner_parent_id': parent, 'deps': [branch], 'note': 'PRIVATE_NOTE', 'params': {'prompt': 'PRIVATE_PROMPT'}},
                 parent: {'id': parent, 'status': 'pending', 'handler': 'owner_plan_join', 'owner_plan_id': plan, 'deps': [generation, branch]},
                 branch: {'id': branch, 'status': 'blocked', 'handler': 'owner_plan_step', 'owner_plan_id': plan,
                          'owner_parent_id': parent, 'owner_plan_wait': 'WAIT_RESOURCE_BUDGET', 'deps': [],
                          'owner_claim': {'worker': 'nox-agent-01', 'pid': 123, 'nonce': 'c' * 24, 'private': 'PRIVATE_CLAIM'},
                          'result': {'state': 'WAIT_RESOURCE_BUDGET', 'text': 'PRIVATE_RESULT'}},
                 'unrelated': {'id': 'unrelated', 'status': 'running', 'title': 'PRIVATE_UNRELATED'}}
        self.save(self.state / 'dispatcher/state.json', {'tasks': tasks})
        row = M.task_graph({job}); raw = M.encoded(row)
        self.assertEqual(len(row['relevant_tasks']), 3); self.assertEqual(row['counts']['running'], 1)
        self.assertNotIn(b'PRIVATE_', raw); self.assertNotIn(b'unrelated', raw)
        generated = next(r for r in row['relevant_tasks'] if r['task_id'] == generation)
        self.assertEqual(generated['dependencies'], [{'task_id': branch, 'status': 'blocked'}])
        self.assertIsNone(generated['note_code']); self.assertTrue(generated['note_present'])

    def test_saved_plan_receipt_requires_exact_derived_path_and_claim(self):
        task_id, plan, nonce = 'owner.branch.' + 'a' * 24 + '.budget', 'a' * 24, 'b' * 24
        claim = {'nonce': nonce, 'pid': 1, 'worker': 'nox-agent-01'}
        path = self.state / 'owner_plans' / plan / (M.digest(M.encoded(task_id))[:24] + '.' + nonce + '.json')
        record = {'schema': 'NOX_OWNER_PLAN_RECEIPT_V1', 'plan_id': plan, 'task_id': task_id, 'claim': claim,
                  'verified': True, 'scope': 'OBSERVED_RESOURCE_BUDGET', 'blockers': [], 'private': 'PRIVATE_RECEIPT'}
        self.save(path, record)
        task = {'owner_plan_id': plan, 'owner_claim': claim,
                'result': {'receipt_path': str(path), 'receipt_sha256': M.digest(path.read_bytes())}}
        result = M.plan_receipt(task_id, task)
        self.assertTrue(result['claim_matches']); self.assertNotIn('PRIVATE_RECEIPT', str(result))
        task['result']['receipt_path'] = str(self.root / 'secret')
        with self.assertRaisesRegex(RuntimeError, 'PLAN_RECEIPT_PATH'):
            M.plan_receipt(task_id, task)

    def test_comfy_projection_contains_only_counts_and_target_membership(self):
        rt = types.SimpleNamespace(queue_ids=lambda: {'queue_running': ['private-external-id'], 'queue_pending': ['fixed-target-id']})
        result = M.comfy(rt, {'a' * 32: 'fixed-target-id'})
        self.assertEqual(result['running_count'], 1); self.assertTrue(result['target_jobs']['a' * 32]['pending'])
        self.assertNotIn('private-external-id', str(result)); self.assertNotIn('fixed-target-id', str(result))

    def test_bad_json_symlink_and_special_files_are_rejected(self):
        path = self.root / 'input.json'; path.write_bytes(b'{"state":1,"state":2}')
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_JSON_KEY'):
            M.document(path)
        path.write_bytes(b'{"x":1e999}')
        with self.assertRaises(ValueError):
            M.document(path)
        link = self.root / 'link'; link.symlink_to(path)
        with self.assertRaisesRegex(RuntimeError, 'PATH'):
            M.read(link)
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        with self.assertRaisesRegex(RuntimeError, 'FILE_BOUND'):
            M.read(fifo)


if __name__ == '__main__':
    unittest.main()
