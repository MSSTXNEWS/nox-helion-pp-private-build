"""Scope, partial-apply and restart gates for the C02 source-only admission.

Real temporary filesystem transactions; no native supervisor, model or S03
access. Process lifecycle observations are explicit controlled test fixtures.
"""
import base64
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import owner_c02_memory_progress_install as install
from test_owner_continuous_executor_install import fixture as base_fixture, frozen


HERE = Path(__file__).resolve().parent
BATCH = HERE / 'c02_memory_progress_20261118'


def asset_bytes(candidate, name):
    return (HERE.parent / candidate['asset_sources'][name]).read_bytes()


def fixture():
    old, _, _, _, _ = base_fixture()
    old['module_pins']['owner_subagent_dispatcher.py'] = install.CALLBACK_SHA256
    old['module_pins']['owner_project_model_client.py'] = install.MODEL_CLIENT_SHA256
    old['project_executor']['model']['source_pins']['owner_project_model_client.py'] = install.MODEL_CLIENT_SHA256
    old['project_executor']['model']['source_pins']['owner_project_planner.py'] = old['module_pins']['owner_project_planner.py']
    old['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'].append(install.C02_SOURCE)
    candidate = json.loads((BATCH / 'candidate.json').read_bytes())
    additions = {path: asset_bytes(candidate, name)
                 for name, path in candidate['source_test_paths'].items()}
    contracts = {Path(path).stem: json.loads(asset_bytes(candidate, name))
                 for name, path in candidate['package_paths'].items()}
    rows = copy.deepcopy(candidate['catalog_append_without_callback_pin'])
    rows[0]['source_sha256'] = install.CALLBACK_SHA256
    return old, {}, additions, contracts, rows


def marker_for(additions=None):
    return {'schema': 'NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1',
        'root': str(install.ROOT / install.SOURCE),
        'file_pins': {install.C02_SOURCE: 'a' * 64},
        'source_refs': [{'kind': 'ORIGINAL_SOURCE', 'sha': 'b' * 40}],
        'manifest_sha256': 'c' * 64, 'source_file_count': 1, 'original_request': '12345'}


class ScopeTests(unittest.TestCase):
    def test_only_two_test_paths_and_one_catalog_row_change(self):
        old, runtime, additions, contracts, rows = fixture()
        baseline = copy.deepcopy(old)
        actual = install.compose(old, runtime, additions, contracts, rows)
        expected = copy.deepcopy(old)
        expected['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'].extend(sorted(additions))
        expected['catalog']['tasks'].extend(copy.deepcopy(rows))
        expected['catalog_sha256'] = install.digest(install.encoded(expected['catalog']))
        self.assertEqual(actual, expected)
        self.assertEqual(old, baseline)
        self.assertEqual(actual['module_pins'], baseline['module_pins'])
        self.assertEqual(actual['historical_leaf_source_sha256'], baseline['historical_leaf_source_sha256'])
        self.assertEqual(actual['historical_project_source_sha256'], baseline['historical_project_source_sha256'])
        self.assertEqual(actual['project_executor']['model'], baseline['project_executor']['model'])
        self.assertEqual(actual['global_worker_cap'], 3)

    def test_runtime_changes_test_scope_and_collision_are_rejected(self):
        for kind, reason in (('runtime', 'RUNTIME_SCOPE'), ('third_test', 'TRUSTED_TEST_SCOPE'),
                             ('missing_test', 'TRUSTED_TEST_SCOPE'), ('collision', 'TEST_ALREADY_ALLOWED')):
            with self.subTest(kind=kind):
                old, runtime, additions, contracts, rows = fixture()
                if kind == 'runtime':
                    runtime['scripts/owner_project_model_client.py'] = b'changed'
                elif kind == 'third_test':
                    additions['test_nox_unreviewed.py'] = b'pass\n'
                elif kind == 'missing_test':
                    additions.pop(next(iter(additions)))
                else:
                    old['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths'].append(next(iter(additions)))
                before = copy.deepcopy(old)
                with self.assertRaisesRegex(install.Hold, reason):
                    install.compose(old, runtime, additions, contracts, rows)
                self.assertEqual(old, before)

    def test_changed_callback_or_client_identity_is_rejected(self):
        for key in ('owner_subagent_dispatcher.py', 'owner_project_model_client.py'):
            with self.subTest(key=key):
                old, runtime, additions, contracts, rows = fixture()
                old['module_pins'][key] = 'f' * 64
                with self.assertRaisesRegex(install.Hold, 'EXISTING_RUNTIME_PINS'):
                    install.compose(old, runtime, additions, contracts, rows)

    def test_contract_cannot_grant_other_source_parent_or_weaker_tests(self):
        for kind in ('parent', 'editable', 'verification', 'context'):
            with self.subTest(kind=kind):
                old, runtime, additions, contracts, rows = fixture()
                contract = copy.deepcopy(next(iter(contracts.values())))
                if kind == 'parent':
                    contract['parent_task_id'] = '3A03'
                elif kind == 'editable':
                    contract['editable_paths'].append('foreign.py')
                elif kind == 'verification':
                    contract['verification']['min_tests'] = 1
                else:
                    contract['context'][0]['path'] = 'foreign.py'
                pin = install.digest(install.encoded(contract))
                rows[0]['params']['contract_sha256'] = pin
                with self.assertRaisesRegex(install.Hold, 'CONTRACT_(SCOPE|EDIT_AND_TEST_SCOPE)'):
                    install.compose(old, runtime, additions, {pin: contract}, rows)

    def test_replay_dependency_or_callback_row_change_is_rejected(self):
        for kind in ('replay', 'dependency', 'callback'):
            with self.subTest(kind=kind):
                old, runtime, additions, contracts, rows = fixture()
                if kind == 'replay':
                    old['catalog']['tasks'].extend(copy.deepcopy(rows))
                    old['catalog_sha256'] = install.digest(install.encoded(old['catalog']))
                elif kind == 'dependency':
                    rows[0]['deps'] = ['other.task']
                else:
                    rows[0]['source_sha256'] = 'e' * 64
                with self.assertRaisesRegex(install.Hold, 'CATALOG_ROW_SCOPE'):
                    install.compose(old, runtime, additions, contracts, rows)

    def test_decode_accepts_only_active_contract_two_tests_and_exact_frozen_helper(self):
        candidate = json.loads((BATCH / 'candidate.json').read_bytes())
        paths = {**candidate['source_test_paths'], **candidate['package_paths']}
        assets = {name: asset_bytes(candidate, name) for name in paths}
        assets['c02_transaction_helpers.py'] = (HERE / 'owner_kernel_self_fd_install.py').read_bytes()
        spec = {'schema': install.SCHEMA, 'runtime_paths': {}, 'expected_extra_tools': {},
                'source_test_paths': candidate['source_test_paths'], 'package_paths': candidate['package_paths'],
                'assets': {name: install.digest(raw) for name, raw in assets.items()},
                'helper_asset': 'c02_transaction_helpers.py', 'helper_sha256': install.FROZEN_HELPER_SHA256}
        bundle = {name: base64.b64encode(raw).decode() for name, raw in assets.items()}
        decoded, helper = install.decode(bundle, spec)
        self.assertEqual(decoded, assets)
        self.assertTrue(callable(helper.wait_previous_descendants_stopped))
        bad = copy.deepcopy(spec)
        bad['runtime_paths'] = {'c02_transaction_helpers.py': 'scripts/owner_project_model_client.py'}
        with self.assertRaisesRegex(install.Hold, 'RUNTIME_SCOPE'):
            install.decode(bundle, bad)
        bad = copy.deepcopy(bundle)
        name = next(iter(candidate['source_test_paths']))
        bad[name] = base64.b64encode(b'foreign test bytes').decode()
        with self.assertRaisesRegex(install.Hold, 'ASSET_HASH'):
            install.decode(bad, spec)
        bad = copy.deepcopy(bundle)
        bad['old_unreferenced_contract.json'] = base64.b64encode(b'{}').decode()
        with self.assertRaisesRegex(install.Hold, 'ASSET_SET'):
            install.decode(bad, spec)

    def test_bootstrap_append_preserves_history_and_rejects_pin_collision(self):
        _, _, additions, _, _ = fixture()
        marker = marker_for()
        before = copy.deepcopy(marker)
        updated = install.extend_marker(marker, additions, 'd' * 40)
        self.assertEqual(marker, before)
        self.assertEqual(updated['source_refs'][:-1], before['source_refs'])
        self.assertEqual(updated['file_pins'][install.C02_SOURCE], before['file_pins'][install.C02_SOURCE])
        self.assertEqual(updated['source_file_count'], 3)
        self.assertEqual(updated['source_refs'][-1]['previous_marker_sha256'], install.digest(install.encoded(before)))
        with self.assertRaisesRegex(install.Hold, 'BOOTSTRAP_TEST_COLLISION'):
            install.extend_marker(updated, additions, 'e' * 40)


class TransactionTests(unittest.TestCase):
    def test_partial_apply_restores_config_and_removes_owned_test_without_runtime_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = [install.SOURCE + '/' + p for p in sorted(install.TRUSTED_TESTS)]
            native = 'scripts/owner_project_model_client.py'
            frozen.atomic(root / native, b'existing native runtime')
            frozen.atomic(root / install.CONFIG, b'original config')
            changes = {install.CONFIG: b'new config', first: b'first test', second: b'second test'}
            before = {install.CONFIG: b'original config', first: None, second: None}
            def fail_second(path, raw, mode=0o600):
                if path == root / second:
                    raise OSError('injected partial apply')
                frozen.atomic(path, raw, mode)
            helper = SimpleNamespace(read_regular=frozen.read_regular, atomic=fail_second,
                                     rollback_transaction=frozen.rollback_transaction)
            applied = []
            with self.assertRaises(OSError):
                install.apply_tracked(root, changes, before, helper, applied)
            self.assertEqual(applied, list(changes))
            install.rollback_owned(root, changes, before, helper, applied)
            self.assertEqual((root / install.CONFIG).read_bytes(), before[install.CONFIG])
            self.assertEqual((root / native).read_bytes(), b'existing native runtime')
            self.assertFalse((root / first).exists())
            self.assertFalse((root / second).exists())

    def test_rollback_preserves_foreign_new_test_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            added = install.SOURCE + '/' + sorted(install.TRUSTED_TESTS)[0]
            frozen.atomic(root / install.CONFIG, b'old config')
            changes = {install.CONFIG: b'new config', added: b'owned test'}
            before = {install.CONFIG: b'old config', added: None}
            applied = []
            install.apply_tracked(root, changes, before, frozen, applied)
            frozen.atomic(root / added, b'foreign bytes')
            with self.assertRaisesRegex(install.Hold, 'NEW_TEST_CHANGED_NO_CLEANUP'):
                install.rollback_owned(root, changes, before, frozen, applied)
            self.assertEqual((root / added).read_bytes(), b'foreign bytes')
            self.assertEqual((root / install.CONFIG).read_bytes(), b'old config')

    def test_cas_and_rollback_never_overwrite_foreign_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frozen.atomic(root / install.CONFIG, b'foreign config')
            before, changes = {install.CONFIG: b'old config'}, {install.CONFIG: b'new config'}
            applied = []
            with self.assertRaisesRegex(install.Hold, 'CONCURRENT_WRITE'):
                install.apply_tracked(root, changes, before, frozen, applied)
            self.assertEqual(applied, [])
            outcomes = install.rollback_owned(root, changes, before, frozen, [install.CONFIG])
            self.assertEqual(outcomes[install.CONFIG], 'FOREIGN_CHANGE_PRESERVED')
            self.assertEqual((root / install.CONFIG).read_bytes(), b'foreign config')


class RestartSafetyTests(unittest.TestCase):
    def test_old_children_still_alive_prevent_every_restore_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, runtime, additions, contracts, rows = fixture()
            old['project_executor']['roots']['NOX_PROJECT_SOURCE']['path'] = str(root / install.SOURCE)
            before = {'scripts/' + name: ('old ' + name).encode() for name in old['module_pins']}
            before['scripts/owner_subagent_dispatcher.py'] = (HERE / 'complete_executor_budget_20261118/runtime/owner_subagent_dispatcher.py').read_bytes()
            before['scripts/owner_project_model_client.py'] = (HERE / 'complete_executor_retries_20261118/runtime/owner_project_model_client.py').read_bytes()
            before['scripts/owner_autonomy_pool.py'] = b'OLD_POOL = True\n'
            for name in old['module_pins']:
                old['module_pins'][name] = install.digest(before['scripts/' + name])
            old['project_executor']['model']['source_pins']['owner_project_planner.py'] = old['module_pins']['owner_project_planner.py']
            before[install.CONFIG] = install.encoded(old)
            marker = marker_for()
            marker['root'] = str(root / install.SOURCE)
            marker_raw = install.encoded(marker)
            for path, raw in {**before, install.MARKER: marker_raw, 'state/owner_maintenance.lock': b'fixture'}.items():
                frozen.atomic(root / path, raw)
            frozen.atomic(root / install.SOURCE / install.C02_SOURCE, b'old C02 source')
            candidate = json.loads((BATCH / 'candidate.json').read_bytes())
            assets = {name: asset_bytes(candidate, name)
                      for name in {**candidate['source_test_paths'], **candidate['package_paths']}}
            snapshot = {'files_sha256': 'e' * 64, 'files': {}, 'git_pins': {},
                        'bootstrap_sha256': install.digest(marker_raw)}
            spec = {'expected_native': {path: install.digest(raw) for path, raw in before.items()},
                'runtime_paths': {}, 'source_test_paths': candidate['source_test_paths'],
                'package_paths': candidate['package_paths'], 'catalog_append': rows,
                'expected_bootstrap_sha256': install.digest(marker_raw),
                'expected_source_files_sha256': snapshot['files_sha256'], 'expected_extra_tools': {}}
            claim = {'nonce': 'a' * 24, 'pid': 122}
            state = {'tasks': {'old.task': {'handler': 'owner_native_project_work', 'status': 'done',
                'owner_claim': claim, 'result': {'verified': True, 'receipt': {
                    'claim': claim, 'task_id': 'old.task', 'original_task_accepted': False}}}}}
            children = [{'pid': 123, 'start_ticks': 456, 'ppid': 122}]
            helper = SimpleNamespace(
                Hold=frozen.Hold, preimages=Mock(side_effect=lambda *args: dict(before)),
                read_regular=frozen.read_regular, atomic=frozen.atomic, relpath=frozen.relpath,
                protected_snapshot=Mock(return_value={'protected': 'unchanged'}),
                stop_clear=Mock(return_value=True), queue_idle=Mock(return_value=(state, [])),
                self_fd_children=Mock(return_value={'processes': [], 'children': children, 'unexpected_children': []}),
                exact_s03=Mock(return_value={'verified': True, 'receipt_sha256': 'f' * 64}),
                source_snapshot=Mock(return_value=snapshot), load_budget_module=Mock(return_value=(object(), object())),
                budget_preflight=Mock(return_value={'verified': True}),
                preserve_terminal_history=Mock(return_value={'verified': True}),
                stop_checked=Mock(), supervisor=Mock(return_value={'state': 'STOPPED'}),
                wait_previous_descendants_stopped=Mock(side_effect=frozen.Hold('OLD_CHILD_STILL_ALIVE')),
                start_checked=Mock(), start_update_checked=Mock(),
            )
            planner = SimpleNamespace(__file__=str(root / 'scripts/owner_project_planner.py'), validate_contract=Mock())
            with patch.object(install, 'ROOT', root), patch.object(install, 'decode', return_value=(assets, helper)), \
                    patch.dict(os.environ, NOX_OWNER_REQUEST_ID='123456', NOX_OWNER_SOURCE_SHA='a' * 40), \
                    patch.dict(sys.modules, owner_project_planner=planner), patch.object(sys, 'path', list(sys.path)), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(frozen.Hold, 'OLD_CHILD_STILL_ALIVE'):
                    install.run({}, spec, root)
            helper.stop_checked.assert_called_once()
            self.assertEqual(helper.wait_previous_descendants_stopped.call_count, 2)
            helper.start_checked.assert_not_called()
            helper.start_update_checked.assert_not_called()
            self.assertEqual((root / install.CONFIG).read_bytes(), before[install.CONFIG])
            self.assertEqual((root / install.SOURCE / install.C02_SOURCE).read_bytes(), b'old C02 source')
            self.assertEqual((root / 'scripts/owner_project_model_client.py').read_bytes(), before['scripts/owner_project_model_client.py'])
            self.assertTrue(all(not (root / install.SOURCE / name).exists() for name in additions))


if __name__ == '__main__':
    unittest.main()
