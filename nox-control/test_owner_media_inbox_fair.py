"""Retained-history regression and exact native dispatcher binding tests."""
import ast
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


F = load('owner_media_inbox_fair.py', 'media_fair_test')
E = load('owner_media_inbox_fair_entry.py', 'media_fair_entry_test')
T = load('owner_subagent_instruction_truth.py', 'media_fair_truth_test')


def bundle():
    paths = {name: HERE / name for name in E.PINS}
    paths.update({'owner_qwen_window_entry.py': Path('/tmp/nox_qwen_window_entry_4d5.py'),
        'owner_qwen_install_entry.py': Path('/tmp/nox_qwen_owner_qwen_install_entry.py'),
        'owner_subagent_install_entry.py': Path('/tmp/nox_subagent_review_b022334/owner_subagent_install_entry.py')})
    return {name: base64.b64encode(path.read_bytes()).decode() for name, path in paths.items()}


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = load('owner_media_runtime.py', 'native_ca8_test_' + str(id(self)))
        self.runtime.ROOT = self.root
        self.state = {'tasks': {}}

    def job(self, number, state='QUEUED', kind='image'):
        job = '%032x' % number
        for folder, data in [('jobs', {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': job,
                  'state': state, 'owner': 'PRIVATE_FIXTURE', 'request': {'kind': kind, 'prompt': 'PRIVATE_PROMPT'}}),
                ('inbox', {'job_id': job})]:
            path = self.root / 'state/media' / folder / (job + '.json')
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data))
        return job

    def test_real_ca8_regression_first_three_terminal_fourth_queued(self):
        for i, state in enumerate(('COMPLETED', 'BLOCKED', 'FAILED'), 1):
            self.job(i, state)
        target = self.job(4)
        before = {p: p.read_bytes() for p in (self.root / 'state/media').rglob('*.json')}
        self.assertEqual(self.runtime.ingest_media_tasks(self.state), 0)
        namespace = {'HANDLERS': {}, 'ingest_owner_orders': lambda _: None,
                     '_nox_owner_task_admitted': lambda _: True, '_owner_plans_bound': True}
        self.runtime.bind_dispatcher(namespace)
        old_ingest = namespace['ingest_owner_orders']
        with patch.object(F, 'RUNTIME_PATH', Path(self.runtime.__file__)), patch.object(F, 'BOUND', None):
            F.bind_dispatcher(namespace, self.runtime)
            old_ingest(self.state)
        self.assertEqual(set(self.state['tasks']), {'owner.media.' + target})
        self.assertEqual(self.state['tasks']['owner.media.' + target]['status'], 'pending')
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_existing_claims_and_results_never_replayed_limit_counts_insertions(self):
        for i in range(1, 9):
            job = self.job(i, 'QUEUED')
            if i <= 3:
                self.state['tasks']['owner.media.' + job] = {'status': 'blocked', 'owner_claim': {'nonce': str(i)},
                                                          'result': {'verified': False}}
        saved = copy.deepcopy(self.state['tasks'])
        self.assertEqual(F.ingest(self.runtime, self.state), 3)
        for key, value in saved.items():
            self.assertEqual(self.state['tasks'][key], value)
        self.assertEqual(len(self.state['tasks']), 6)
        self.assertEqual(F.ingest(self.runtime, self.state), 2)
        self.assertEqual(F.ingest(self.runtime, self.state), 0)

    def test_200_history_bound_is_checked_before_any_admission(self):
        for i in range(1, 202):
            self.job(i)
        with self.assertRaisesRegex(RuntimeError, 'HISTORY_BOUND'):
            F.ingest(self.runtime, self.state)
        self.assertEqual(self.state['tasks'], {})
        for folder in ('jobs', 'inbox'):
            (self.root / 'state/media' / folder / ('%032x.json' % 201)).unlink()
        self.assertEqual(F.ingest(self.runtime, self.state), 3)

    def test_invalid_or_symlink_inbox_is_skipped_without_reading_target(self):
        job = self.job(1)
        inbox = self.root / 'state/media/inbox' / (job + '.json')
        inbox.unlink(); inbox.symlink_to(self.root / 'private.json')
        target = self.job(2)
        self.assertEqual(F.ingest(self.runtime, self.state), 1)
        self.assertEqual(set(self.state['tasks']), {'owner.media.' + target})
        bad = self.job(3)
        p = self.root / 'state/media/inbox' / (bad + '.json'); p.write_text('{"job_id":"mismatch"}')
        self.assertEqual(F.ingest(self.runtime, self.state), 0)

    def test_original_planner_builds_normal_three_branch_dag(self):
        target = self.job(4)
        F.ingest(self.runtime, self.state)
        plans = load('owner_task_plans.py', 'native_plans_fair_test')
        plans.ROOT = self.root
        planner = plans.Planner.__new__(plans.Planner)
        planner.ns = {'_qlock': threading.RLock(), 'save_state': lambda _: None}
        planner.auto_media(self.state)
        h = types.SimpleNamespace(queue_state=lambda: self.state, read=lambda p, maximum=None: Path(p).read_bytes())
        with patch.object(E, 'STATE', self.root / 'state'), patch.object(E, 'TARGET', target):
            result = E.target_plan(h)
        self.assertTrue(result['normal_dag_observed']); self.assertFalse(result['generation_completed_verified'])
        snapshot = copy.deepcopy(self.state)
        F.ingest(self.runtime, self.state); planner.auto_media(self.state)
        self.assertEqual(snapshot, self.state)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundled = bundle()
        with patch.object(E, 'BUNDLE', cls.bundled):
            cls.assets, cls.installer, cls.base, cls.fresh, cls.h, cls.recovery, cls.guard = E.prepared()

    def native_dispatcher(self):
        raw = Path('/tmp/nox_native_sources/nox_dispatcher_admitted_a409.py').read_bytes()
        anchor = b'if __name__ == "__main__":\n    main()'
        raw = raw.replace(anchor, b'# NOX_NATIVE_SUBAGENTS_BIND_V1\nimport owner_subagent_dispatcher\nowner_subagent_dispatcher.bind_dispatcher(globals())\n\n' + anchor)
        return self.installer.patch_dispatcher(self.base.patch_dispatcher(raw), self.base)

    def test_exact_dependency_closure_and_only_one_dispatcher_insert(self):
        self.assertEqual(len(self.assets), 15)
        self.assertEqual(self.h.SERVICE, 'nox-dispatcher-t855u')
        before = self.native_dispatcher(); self.assertEqual(E.digest(before), E.DISPATCHER_BEFORE)
        after = E.patch_dispatcher(before)
        self.assertEqual(after.replace(E.BINDING.encode(), b'', 1), before)
        self.assertLess(after.index(E.MARKER.encode()), after.index(b'# NOX_OWNER_TASK_LIFECYCLE_BIND_V1'))
        self.assertLess(after.index(b'owner_subagent_instruction_truth.bind'), after.index(b'owner_subagent_dispatcher.bind_dispatcher'))
        with self.assertRaisesRegex(RuntimeError, 'DISPATCHER_PREIMAGE'):
            E.patch_dispatcher(after)
        corrupt = dict(self.bundled, **{E.FAIR: base64.b64encode(b'raise Exception("private")').decode()})
        with patch.object(E, 'BUNDLE', corrupt), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            E.prepared()

    def test_current_child_change_cannot_be_hidden_by_same_immutable_sources(self):
        before = {'files': {'a': 'same'}, 'flags': {}, 'student_profile_sha256': 'same',
                  'service': {'state': 'RUNNING', 'pid': 10}, 'process': {'pid': 10, 'starttime': 1},
                  'student': {'pid': 11, 'ppid': 10, 'start_ticks': 2}}
        E.preserve_training(self.fresh, before, copy.deepcopy(before))
        after = copy.deepcopy(before); after['student']['start_ticks'] = 3
        with self.assertRaisesRegex(RuntimeError, 'TRAINING_PROCESS_CHANGED'):
            E.preserve_training(self.fresh, before, after)
        after = copy.deepcopy(before); after['flags'] = {'pause': True}
        with self.assertRaisesRegex(RuntimeError, 'TRAINING_IDENTITY_CHANGED'):
            E.preserve_training(self.fresh, before, after)

    def test_claims_and_completed_results_are_immutable_but_new_dag_is_allowed(self):
        rows = {'old': {'status': 'done', 'owner_claim': {'nonce': 'old'}, 'result': {'verified': True}},
                'pending': {'status': 'pending'}}
        h = types.SimpleNamespace(queue_state=lambda: {'tasks': rows})
        before = E.historical_tasks(h)
        rows['new'] = {'status': 'pending'}; E.preserved_history(h, before)
        rows['old']['owner_claim']['nonce'] = 'replacement'
        with self.assertRaisesRegex(RuntimeError, 'HISTORICAL_CLAIM_OR_RESULT_CHANGED'):
            E.preserved_history(h, before)

    def test_foreign_write_blocks_all_rollback_mutations(self):
        p1, p2 = Path('/first'), Path('/second')
        values = {p1: b'ours', p2: b'foreign'}
        h = types.SimpleNamespace(read=lambda path: values[path], atomic=Mock())
        with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_FOREIGN_WRITE'):
            self.base.restore(h, {p1: b'old', p2: None}, {p1: E.digest(b'ours'), p2: E.digest(b'ours')}, Path('/backup'))
        h.atomic.assert_not_called()

    def test_smoke_requires_spawned_child_proof_and_does_not_export_stderr(self):
        compile(E.SMOKE, '<fair-smoke>', 'exec')
        self.assertIn('multiprocessing.get_context("spawn")', E.SMOKE)
        self.assertIn('p.exitcode==0 and childproof==', E.SMOKE)
        child = types.SimpleNamespace(returncode=2, stdout=b'{"state":"HOLD"}', stderr=b'PRIVATE_FIXTURE')
        with patch.object(E.subprocess, 'run', return_value=child) as run, self.assertRaisesRegex(RuntimeError, 'SMOKE_FAILED'):
            E.smoke('/usr/bin/python3')
        self.assertEqual(run.call_args.kwargs['timeout'], 15)
        self.assertEqual(run.call_args.args[0][:3], ['/usr/bin/python3', '-I', '-B'])


class TruthTests(unittest.TestCase):
    def native_callback(self):
        raw = (HERE / 'owner_subagent_dispatcher_fresh.py').read_bytes()
        node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'model_instruction')
        callback = types.ModuleType('exact_native_prompt_fixture')
        callback.__file__ = str(T.CALLBACK_PATH); callback.GateError = RuntimeError
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<exact179e-model_instruction>', 'exec'), callback.__dict__)
        return raw, callback

    def test_exact_two_sentence_replacement_preserves_role_policy_and_no_turn_io(self):
        raw, callback = self.native_callback(); reader = Mock(return_value=raw)
        policy = '1C: runtime\n2B: memory\n2D: weights\n'
        original = {role: callback.model_instruction(policy, role) for role in ('runtime', 'memory', 'weights')}
        with patch.object(T, 'BOUND', None):
            T.bind(callback, reader)
            for role, before in original.items():
                self.assertEqual(callback.model_instruction(policy, role), before.replace(T.OLD, T.NEW, 1))
            self.assertEqual(reader.call_count, 1)
            self.assertNotIn('DeepSeek', callback.model_instruction(policy, 'weights'))
            with self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
                T.bind(callback, reader)

    def test_wrong_callback_source_or_prompt_preimage_is_rejected(self):
        _, callback = self.native_callback()
        with patch.object(T, 'BOUND', None), self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
            T.bind(callback, lambda _: b'foreign')
        with self.assertRaisesRegex(RuntimeError, 'PROMPT_PREIMAGE'):
            T.replace_instruction('no verified old sentences')


if __name__ == '__main__':
    unittest.main()
