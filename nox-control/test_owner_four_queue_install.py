"""Temporary-filesystem installer regressions. No native service/network calls."""
import base64
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('four_queue_install_tested',
    HERE / 'owner_four_queue_handoff_entry.py')
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.no_commands = patch.object(install.subprocess, 'run',
            side_effect=AssertionError('A fixture attempted a native command'))
        self.no_commands.start()

    def tearDown(self):
        self.no_commands.stop()
        self.temp.cleanup()

    def put(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def fixture(self, active=False):
        old_rows = [{'id': 'old.' + role, 'handler': 'owner_native_subagent_review',
                     'params': {'role': role}, 'source_sha256': '1' * 64,
                     'deps': [], 'priority': 1}
                    for role in ('runtime', 'memory', 'weights')]
        catalog = {'schema': 'NOX_AUTONOMY_PROCESS_POOL_V1', 'tasks': old_rows}
        config = {'schema': 'NOX_NATIVE_SUBAGENT_BINDING_V1', 'instance_id': 60509551,
                  'owner_authorized': True, 'mode': 'NORMAL', 'target': 3,
                  'catalog': catalog, 'catalog_sha256': install.digest(install.encoded(catalog)),
                  'module_pins': {'preserve_other': '2' * 64},
                  'policy': {'existing': 'preserve'}, 'unrelated': ['preserve']}
        state = {'tasks': {row['id']: {**copy.deepcopy(row), 'status': 'done',
                          'result': {'receipt_sha256': str(i) * 64}}
                          for i, row in enumerate(old_rows, 1)}}
        if active:
            state['tasks']['other.running'] = {'id': 'other.running', 'status': 'running',
                                              'owner_claim': {'nonce': 'a' * 24}}
        self.put(install.CONFIG, install.encoded(config))
        self.put(install.STATE, install.encoded(state))
        self.put('state/owner_maintenance.lock', b'')
        self.put('kb/knowledge.sqlite', b'unchanged-S03-fixture')
        self.put('state/TRAIN_HOLD.flag', b'owner-training-hold')
        self.put('models/current.gguf', b'unchanged-model-fixture')
        self.put('scripts/owner_subagent_dispatcher.py', b'old-source\n')
        assets = {name: b'pass\n' for name in (
            'owner_subagent_dispatcher.py', 'owner_subagent_processes.py', 'owner_autonomy_pool.py')}
        leaves = [{'id': 'scoped.' + str(i), 'queue_id': q,
                   'handler': 'owner_native_typed_leaf', 'resource': 'CPU_LIGHT',
                   'source_sha256': install.digest(assets['owner_subagent_dispatcher.py'])}
                  for i, q in enumerate(install.QUEUE_IDS)]
        expected = {name: install.digest((self.root / name).read_bytes()) for name in
                    (install.CONFIG, 'scripts/owner_subagent_dispatcher.py')}
        specification = {'expected_native': expected, 'leaf_catalog': leaves,
                         'leaf_source_pins': {}, 'project_handoff': {},
                         'install_paths': {'owner_subagent_dispatcher.py': 'scripts/owner_subagent_dispatcher.py'},
                         'protected_processes': {}}
        return config, state, assets, specification

    def install_context(self, assets):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.dict(install.os.environ,
            {'NOX_OWNER_REQUEST_ID': '123456', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}))
        stack.enter_context(patch.object(install, 'decode_assets', return_value=assets))
        stack.enter_context(patch.object(install, 'validate_handoff', return_value={'original_task_ids': 295}))
        stack.enter_context(patch.object(install, 'stop_clear', return_value=True))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        return stack

    def test_changed_preimage_stops_before_service_or_source_writes(self):
        _, _, assets, specification = self.fixture()
        changed = self.put('scripts/owner_subagent_dispatcher.py', b'foreign-source\n')
        with self.install_context(assets), patch.object(install, 'supervisor') as supervisor:
            with self.assertRaisesRegex(install.Hold, 'PREIMAGE_'):
                install.install({}, specification, self.root)
            supervisor.assert_not_called()
        self.assertEqual(changed.read_bytes(), b'foreign-source\n')
        self.assertFalse((self.root / 'state/dispatcher/four_queue_rollback').exists())

    def test_active_claim_refuses_install_before_supervisor_stop(self):
        _, _, assets, specification = self.fixture(active=True)
        before = (self.root / install.STATE).read_bytes()
        with self.install_context(assets), patch.object(install, 'supervisor') as supervisor, \
                patch.object(install.time, 'monotonic', side_effect=[0, 36]), \
                patch.object(install.time, 'sleep'):
            with self.assertRaisesRegex(install.Hold, 'ACTIVE_TASKS_NOT_DRAINED'):
                install.install({}, specification, self.root)
            self.assertTrue(all(call.args[0] == 'status' for call in supervisor.call_args_list))
        self.assertEqual((self.root / install.STATE).read_bytes(), before)
        self.assertEqual((self.root / 'scripts/owner_subagent_dispatcher.py').read_bytes(), b'old-source\n')

    def test_write_readback_failure_restores_already_replaced_file(self):
        path = self.put('scripts/a.py', b'old-a')
        self.put('scripts/b.py', b'old-b')
        before = {'scripts/a.py': b'old-a', 'scripts/b.py': b'old-b'}
        changes = {'scripts/a.py': b'new-a', 'scripts/b.py': b'new-b'}
        read = install.read_regular
        failed = False

        def read_once_bad(candidate, maximum=install.MAX_BYTES):
            nonlocal failed
            raw = read(candidate, maximum)
            if Path(candidate) == path and raw == b'new-a' and not failed:
                failed = True
                raise OSError('injected post-replace readback failure')
            return raw

        with patch.object(install, 'read_regular', side_effect=read_once_bad):
            with self.assertRaises(OSError):
                install.apply_transaction(self.root, changes, before)
        self.assertEqual(path.read_bytes(), b'old-a')
        self.assertEqual((self.root / 'scripts/b.py').read_bytes(), b'old-b')

    def test_rollback_keeps_foreign_changes_and_restores_other_preimages(self):
        a = self.put('scripts/a.py', b'new-a')
        b = self.put('scripts/b.py', b'foreign-b')
        changes = {'scripts/a.py': b'new-a', 'scripts/b.py': b'new-b'}
        before = {'scripts/a.py': b'old-a', 'scripts/b.py': b'old-b'}
        outcome = install.rollback_transaction(self.root, changes, before, list(changes))
        self.assertEqual(a.read_bytes(), b'old-a')
        self.assertEqual(b.read_bytes(), b'foreign-b')
        self.assertEqual(outcome['scripts/a.py'], 'PREIMAGE_RESTORED')
        self.assertEqual(outcome['scripts/b.py'], 'FOREIGN_CHANGE_PRESERVED')

    def test_catalog_extension_preserves_previous_reviews_and_scope(self):
        config, _, assets, specification = self.fixture()
        original = copy.deepcopy(config)
        value = json.loads(install.prepare_config(install.encoded(config), assets, specification,
                                                 '123456', 'a' * 40))
        self.assertEqual(config, original)
        self.assertEqual(value['policy'], original['policy'])
        self.assertEqual(value['unrelated'], original['unrelated'])
        self.assertEqual(value['module_pins']['preserve_other'], '2' * 64)
        self.assertEqual(len(value['catalog']['tasks']), 7)
        for old, new in zip(original['catalog']['tasks'], value['catalog']['tasks'][:3]):
            self.assertEqual({k: v for k, v in new.items() if k != 'queue_id'}, old)
        self.assertEqual(value['catalog_sha256'], install.digest(install.encoded(value['catalog'])))
        self.assertEqual(value['global_worker_cap'], 3)

    def test_success_backs_up_sources_and_preserves_original_state_s03_and_training(self):
        _, _, assets, specification = self.fixture()
        protected = {name: (self.root / name).read_bytes() for name in (
            install.STATE, 'kb/knowledge.sqlite', 'state/TRAIN_HOLD.flag', 'models/current.gguf')}
        running = True

        def supervisor(action, name=install.SERVICE):
            nonlocal running
            self.assertEqual(name, install.SERVICE)
            if action == 'status':
                return {'state': 'RUNNING' if running else 'STOPPED', 'pid': 111 if running else None}
            running = action == 'start'
            return {'action': action, 'rc': 0}

        def identity(pid):
            if pid == 111 and not running:
                return None
            return {'pid': pid, 'start_ticks': pid + 1000, 'pgrp': 111, 'ppid': 111}

        observed = {'native_subexecutors': {'workers': [
            {'pid': pid, 'process_starttime': pid + 1000, 'heartbeat_at': install.time.time()}
            for pid in (222, 223, 224)]},
            'leaf_tasks': [{'task_id': row['id'], 'state': 'done',
                           'exact_s03_readback_verified': True, 'worker_pid': 222 + i % 3,
                           'worker_start_ticks': 1222 + i % 3}
                          for i, row in enumerate(specification['leaf_catalog'])]}
        with self.install_context(assets), patch.object(install, 'supervisor', side_effect=supervisor) as calls, \
                patch.object(install, 'process_identity', side_effect=identity), \
                patch.object(install, 'execution_snapshot', return_value=observed), \
                patch.object(install, 'stop_checked', side_effect=lambda: install.supervisor('stop')), \
                patch.object(install, 'start_checked', side_effect=lambda *args, **kwargs: install.supervisor('start')), \
                patch.object(install, 'load_receipt_reader', return_value=object()), \
                patch.object(install.time, 'sleep'):
            receipt = install.install({}, specification, self.root)
        actions = [c.args[0] for c in calls.call_args_list]
        self.assertEqual([action for action in actions if action != 'status'], ['stop', 'start'])
        self.assertEqual(receipt['state'], 'THREE_NATIVE_WORKERS_FOUR_SCOPED_LEAVES_COMPLETED')
        self.assertFalse(receipt['training_started'])
        self.assertFalse(receipt['model_restarted'])
        self.assertEqual(receipt['original_tasks_accepted'], 0)
        for name, original in protected.items():
            self.assertEqual((self.root / name).read_bytes(), original, name)
        backup = self.root / 'state/dispatcher/four_queue_rollback/123456'
        self.assertEqual((backup / 'scripts/owner_subagent_dispatcher.py').read_bytes(), b'old-source\n')
        self.assertEqual(json.loads((backup / 'original_queue_snapshot.json').read_bytes()),
                         json.loads(protected[install.STATE]))

    def test_supervisor_rejects_training_service_and_unreviewed_action(self):
        for action, service in [('stop', 'nox-train-volta-t866u'), ('restart', install.SERVICE),
                                ('start', 'nox-chat-primary')]:
            with self.subTest(action=action, service=service):
                with self.assertRaisesRegex(install.Hold, 'SUPERVISOR_SCOPE'):
                    install.supervisor(action, service)


if __name__ == '__main__':
    unittest.main()
