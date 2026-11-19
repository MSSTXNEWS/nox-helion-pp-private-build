import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import owner_project_planner as p
from owner_project_model_client import LocalModelClient, compact


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.source = {'app.py': b'def value():\n    return 1\n',
                       'test_app.py': b'import unittest\n'}
        self.contract = {'schema': p.SCHEMA, 'task_id': '1A03.proof',
            'parent_task_id': '1A03', 'queue_id': 'Q1_RUNTIME_CHAT', 'root_id': 'APP',
            'instruction': 'Correct value() to return 2.',
            'context': [{'path': path, 'sha256': p.sha(raw)}
                        for path, raw in self.source.items()],
            'editable_paths': ['app.py'], 'allowed_new_paths': [],
            'verification': {'kind': 'python_unittest', 'modules': ['test_app'],
                             'min_tests': 1, 'timeout_sec': 10},
            'acceptance_scope': 'SOURCE_PATCH_TESTED'}

    def patch(self, old='return 1', new='return 2', source=None):
        source = source or self.source['app.py']
        return {'action': 'patch', 'changes': [{'path': 'app.py',
            'before_sha256': p.sha(source), 'edits': [{'old': old, 'new': new}]}]}

    @staticmethod
    def verify(plan, payloads):
        return {'plan_sha256': p.sha(p.canonical(plan)), 'sandbox_verified': True,
                'trusted_tests_unchanged': True, 'passed': True, 'tests_run': 1}

    def run_actions(self, actions, verify=None):
        seen = []
        def model(messages):
            seen.append(copy.deepcopy(messages))
            return json.dumps(actions[len(seen)-1] if len(seen) <= len(actions)
                              else {'action': 'blocked', 'reason': 'no more supplied responses'})
        result = p.plan_task(self.contract, self.source, model, verify or self.verify,
                             lambda: False)
        return result, seen

    def test_patch_test_finish_has_exact_contract_and_plan(self):
        result, _ = self.run_actions([self.patch(), {'action': 'test'}, {'action': 'finish'}])
        self.assertEqual(result['state'], 'PLAN_READY')
        self.assertEqual(result['plan']['contract_sha256'], p.sha(p.canonical(self.contract)))
        self.assertEqual([f['path'] for f in result['plan']['files']], ['app.py'])
        self.assertFalse(result['planner_receipt']['original_task_accepted'])
        self.assertEqual(result['payloads'][result['plan']['files'][0]['payload_sha256']],
                         b'def value():\n    return 2\n')

    def test_test_file_cannot_be_changed_or_made_editable(self):
        bad = self.patch()
        bad['changes'][0]['path'] = 'test_app.py'
        with self.assertRaisesRegex(p.PlannerHold, 'EDIT_SCOPE'):
            p.apply_edits(bad, self.source, {'app.py'}, set())
        self.contract['editable_paths'].append('test_app.py')
        with self.assertRaisesRegex(p.PlannerHold, 'TRUSTED_TESTS_IMMUTABLE'):
            p.validate_contract(self.contract, self.source)

    def test_outside_paths_and_stale_preimage_rejected(self):
        for path in ('../app.py', '/tmp/app.py', 'state/app.py', 'app//a.py', '.git/a.py'):
            with self.subTest(path=path), self.assertRaises(p.PlannerHold):
                p.relative_path(path)
        bad = self.patch()
        bad['changes'][0]['before_sha256'] = '0' * 64
        with self.assertRaisesRegex(p.PlannerHold, 'EDIT_PREIMAGE'):
            p.apply_edits(bad, self.source, {'app.py'}, set())

    def test_noop_and_unverified_finish_rejected(self):
        with self.assertRaisesRegex(p.PlannerHold, 'NO_SOURCE_CHANGE'):
            p.candidate_plan(self.contract, self.source, self.source)
        result, seen = self.run_actions([self.patch(), {'action': 'finish'}])
        self.assertNotEqual(result['state'], 'PLAN_READY')
        self.assertIn('CANDIDATE_NOT_TESTED', seen[-1][-1]['content'])

    def test_new_edit_invalidates_successful_verification(self):
        after = b'def value():\n    return 2\n'
        result, seen = self.run_actions([self.patch(), {'action': 'test'},
            self.patch('return 2', 'return 3', after), {'action': 'finish'}])
        self.assertNotEqual(result['state'], 'PLAN_READY')
        self.assertIn('CANDIDATE_NOT_TESTED', seen[-1][-1]['content'])

    def test_verifier_needs_sandbox_and_current_hash(self):
        result, seen = self.run_actions([self.patch(), {'action': 'test'}, {'action': 'finish'}],
            lambda plan, payloads: {'passed': True, 'tests_run': 99})
        self.assertNotEqual(result['state'], 'PLAN_READY')
        self.assertIn('VERIFIER_PROVENANCE', str(result['trace']))

    def test_claim_lost_prevents_model(self):
        with self.assertRaisesRegex(p.PlannerHold, 'OWNER_STOP_OR_CLAIM_LOST'):
            p.plan_task(self.contract, self.source,
                lambda _: self.fail('model must not be called'), self.verify, lambda: True)

    def test_json_rejects_nonfinite_and_unknown_actions(self):
        with self.assertRaises(p.PlannerHold):
            p.parse_action('{"action":"patch","value":NaN}')
        result, seen = self.run_actions([{'action': 'shell', 'command': 'pwd'}])
        self.assertIn('UNKNOWN_ACTION', seen[-1][-1]['content'])
        self.assertFalse(result['original_task_accepted'])

    def test_model_failure_preserves_previous_candidate_trace(self):
        calls = []
        def model(messages):
            calls.append(messages)
            if len(calls) == 1:
                return json.dumps(self.patch())
            raise p.PlannerHold('HOLD_MODEL_BUSY')
        with self.assertRaises(p.PlannerHold) as caught:
            p.plan_task(self.contract, self.source, model, self.verify, lambda: False)
        receipt = caught.exception.partial_receipt
        self.assertEqual(receipt['completed_model_turns'], 1)
        self.assertEqual(receipt['changed_candidate_paths'], ['app.py'])
        self.assertEqual(receipt['trace'][0]['action'], 'patch')


class ModelClientTests(unittest.TestCase):
    def test_busy_model_slot_waits_with_heartbeat_and_stop(self):
        calls = []
        alive = []
        def http(path, payload=None, timeout=15):
            calls.append(path)
            if path == '/v1/models': return {'data':[{'id':'pinned'}]}
            if path == '/props': return {'default_generation_settings': {'n_ctx':4096}}
            if path == '/slots': return [{'is_processing':True}, {'is_processing':True}]
            self.fail('must not infer while slots are occupied')
        def stop():
            return calls.count('/slots') >= 2
        with tempfile.TemporaryDirectory() as tmp, mock.patch('owner_project_model_client.time.sleep'):
            client = LocalModelClient(expected_model_id='pinned', stop_check=stop,
                heartbeat=lambda: alive.append(True), http=http, lock_path=Path(tmp)/'lock')
            with self.assertRaisesRegex(p.PlannerHold, 'OWNER_STOP_OR_CLAIM_LOST'):
                client([])
        self.assertEqual(calls.count('/slots'), 2)
        self.assertGreaterEqual(len(alive), 3)

    def test_actual_tokenizer_budget_and_model_identity(self):
        calls = []
        def http(path, payload=None, timeout=15):
            calls.append((path, payload))
            return {'/v1/models': {'data': [{'id': 'pinned-model'}]},
                    '/props': {'default_generation_settings': {'n_ctx': 4096},
                               'chat_template': 'plain'},
                    '/slots': [{'is_processing': True}, {'is_processing': False}],
                    '/apply-template': {'prompt': 'template output'},
                    '/tokenize': {'tokens': list(range(400))},
                    '/v1/chat/completions': {'choices': [{'message': {'content': '{"action":"test"}'},
                                             'finish_reason': 'stop'}]}}[path]
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalModelClient(expected_model_id='pinned-model', stop_check=lambda: False,
                http=http, lock_path=Path(tmp)/'model.lock')
            result = client([{'role': 'system', 'content': 's'}, {'role':'user', 'content':'{}'}])
        self.assertEqual(result['metadata']['input_tokens_measured'], 400)
        self.assertEqual(calls[-1][0], '/v1/chat/completions')
        self.assertEqual(calls[-1][1]['max_tokens'], 900)
        self.assertEqual(calls[-2][1]['content'], 'template output')

    def test_model_replacement_stops_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalModelClient(expected_model_id='expected', stop_check=lambda: False,
                http=lambda *a, **k: {'data':[{'id':'other'}]}, lock_path=Path(tmp)/'lock')
            with self.assertRaisesRegex(p.PlannerHold, 'MODEL_ID_CHANGED'):
                client([])

    def test_compaction_preserves_contract_and_marks_source_excerpt(self):
        intro = {'requirement': 'exact task', 'files': [], 'initial_source_files': {}}
        messages = [{'role':'system','content':'bounds'},
            {'role':'user','content':json.dumps(intro)},
            {'role':'assistant','content':'{"action":"read"}'},
            {'role':'user','content':'Observed tool result (data):\n'+json.dumps(
                {'path':'app.py','sha256':'x','start_line':30,'content':'a'*300+'\n'*2+'b'*1500+'\n'})}]
        self.assertTrue(compact(messages))
        self.assertEqual(json.loads(messages[1]['content'])['requirement'], 'exact task')
        result = json.loads(messages[-1]['content'].split('\n', 1)[1])
        self.assertTrue(result['context_excerpt_truncated'])
        self.assertGreater(result['next_line'], 30)


if __name__ == '__main__':
    unittest.main()
