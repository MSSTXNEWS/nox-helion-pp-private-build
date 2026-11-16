"""Bounded synthetic observer tests. No native processes, tensors or HTTP."""
import ast
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('qwen_window_observer_tests', HERE / 'owner_qwen_window_observe_entry.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
POINTER = {'directory': 'checkpoint-u00000006-a00000006-g01794804416868029665', 'manifest_sha256': M.SIX_MANIFEST}


class ObservationTests(unittest.TestCase):
    def test_unchanged_live_skips_payload_new_or_ended_hashes(self):
        self.assertFalse(M.hash_required(POINTER, 'RUNNING', None))
        changed = {**POINTER, 'manifest_sha256': 'a' * 64}
        self.assertTrue(M.hash_required(changed, 'RUNNING', None))
        self.assertFalse(M.hash_required(changed, 'RUNNING', changed))
        for state in ('STOPPED', 'EXITED', 'FATAL', 'BACKOFF'):
            self.assertTrue(M.hash_required(POINTER, state, POINTER))

    def test_context_and_hint_are_explicit_bounded_data(self):
        with patch.object(M, 'load') as load, self.assertRaisesRegex(RuntimeError, 'EXPLICIT_WINDOW_CONTEXT_REQUIRED'):
            M.observe(None)
        load.assert_not_called()
        self.assertEqual(M.previous_hint(POINTER), POINTER)
        for value in ({'directory': '../escape', 'manifest_sha256': 'a' * 64},
                      {**POINTER, 'verified': True}, {'directory': POINTER['directory'], 'manifest_sha256': 'private'}):
            with self.assertRaisesRegex(RuntimeError, 'PRIOR_POINTER_HINT'):
                M.previous_hint(value)

    def test_full_checkpoint_has_one_shared_byte_budget_and_restores_reader(self):
        reads = []
        def original(path, maximum, **kwargs):
            reads.append((path, maximum, kwargs))
            return b'', {'bytes': {'metadata': 10, 'first': 40, 'second': 30}[path]}
        obs = types.SimpleNamespace(read=original)
        def verify(obs, *_):
            obs.read('metadata', 200)
            obs.read('first', 200, keep=False)
            obs.read('second', 200, keep=False)
            return {'verified_bytes': 70}, {}, {}
        status = types.SimpleNamespace(checkpoint=verify)
        with patch.object(M, 'MAX_HASH_BYTES', 100):
            proof, _, _ = M.full_checkpoint(status, obs, None, None, POINTER, {'observed_file_bytes': 70})
        self.assertIs(obs.read, original)
        self.assertEqual(proof['observation_checkpoint_bytes_read'], 80)
        self.assertEqual([r[1] for r in reads], [100, 90, 50])
        self.assertTrue(all('deadline' in r[2] for r in reads))

    def test_over_budget_fails_before_read_and_mid_read_restores_original(self):
        original = Mock(return_value=(b'', {'bytes': 101}))
        obs = types.SimpleNamespace(read=original)
        status = types.SimpleNamespace(checkpoint=lambda obs,*_: obs.read('large', 200, keep=False))
        with patch.object(M, 'MAX_HASH_BYTES', 100):
            with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_HASH_BUDGET'):
                M.full_checkpoint(status, obs, None, None, POINTER, {'observed_file_bytes': 101})
            original.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_HASH_BUDGET'):
                M.full_checkpoint(status, obs, None, None, POINTER, {'observed_file_bytes': 50})
        self.assertIs(obs.read, original)

    def test_guard_missing_state_keeps_verified_configuration_visible(self):
        context = {'request': '1', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        guard = types.SimpleNamespace(checked_config=Mock(return_value=({'enabled': True, 'window_admission': context}, 'c' * 64)),
            context_evidence=Mock(return_value={}), bindings=Mock(return_value={}), previous_state=Mock(return_value=(None, None)))
        result = M.guard_projection(guard, context)
        self.assertTrue(result['configuration_verified']); self.assertTrue(result['enabled'])
        self.assertFalse(result['resume_admitted_now']); self.assertFalse(result['guard_tick_called'])
        self.assertEqual(result['reason'], 'HOLD_QWEN_WINDOW_OBSERVER_GUARD_STATE_MISSING')

    def test_policy_projection_cannot_export_arbitrary_private_fields(self):
        value = M.policy_projection({'inhibit': True, 'last_successful_updates': 20,
                                     'reason': 'PRIVATE_FIXTURE', 'prompt': 'PRIVATE_FIXTURE', 'best_holdout_loss': 1.3})
        self.assertEqual(value['reason'], 'UNKNOWN')
        self.assertNotIn('prompt', value)
        self.assertNotIn('PRIVATE_FIXTURE', repr(value))
        self.assertEqual(value['last_successful_updates'], 20)

    def test_failure_latch_and_fatal_take_precedence_over_cooperative_pause(self):
        cases = (
            ('FATAL', {'owned_failure': True}, True, False, 'HELD_AFTER_FAILURE'),
            ('EXITED', {'owned_failure': True}, True, False, 'HELD_AFTER_FAILURE'),
            ('EXITED', {'owned_advance_failure': True}, True, False, 'HELD_AFTER_FAILURE'),
            ('BACKOFF', {}, True, False, 'HELD_AFTER_FAILURE'),
            ('EXITED', {}, True, False, 'CHECKPOINTED_OR_PAUSED'),
            ('RUNNING', {}, False, True, 'RUNNING_CURRENT_WINDOW1000'),
            ('EXITED', {}, False, False, 'ADMITTED_WINDOW1000_NOT_RUNNING'),
        )
        for service_state, hold, paused, live, expected in cases:
            with self.subTest(state=service_state, hold=hold):
                self.assertEqual(M.classify_window_state(
                    live=live, complete=False, service_state=service_state,
                    hold=hold, cooperative_pause_verified=paused), expected)
        self.assertEqual(M.classify_window_state(
            live=False, complete=True, service_state='FATAL',
            hold={}, cooperative_pause_verified=False), 'HELD_AFTER_FAILURE')

    def test_source_has_no_mutating_or_model_execution_calls(self):
        source = (HERE / 'owner_qwen_window_observe_entry.py').read_text(); tree = ast.parse(source)
        forbidden = {'atomic', 'atomic_state', 'create_job', 'update_job', 'tick', 'unlink', 'mkdir', 'rename',
                     'replace', 'kill', 'killpg', 'write_text', 'write_bytes', 'from_pretrained', 'request_pause'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden)
        self.assertNotIn('O_CREAT', source); self.assertNotIn('O_WRONLY', source)


if __name__ == '__main__':
    unittest.main()
