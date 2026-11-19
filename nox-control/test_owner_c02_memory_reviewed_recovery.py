"""Reviewed C02 recovery scope, exact predecessor and transactional gates.

The native failure observation is a projection, so complete local receipt
fixtures use their own synthetic hashes. They are never native acceptance
proof. Temporary filesystem writes are real; supervisor/S03 are substituted.
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

import owner_c02_memory_reviewed_recovery as install
import owner_c02_memory_progress_install as admission
from test_owner_c02_memory_progress_install import fixture as admission_fixture
from test_owner_continuous_executor_install import frozen


HERE = Path(__file__).resolve().parent
BATCH = HERE / 'c02_memory_progress_20261118'
FAILED_OBSERVATION = HERE / 'continuous_executor_20261118/native_receipts/c02_failed_model_attempt.json'


def fixture():
    prior, runtime, additions, contracts, rows = admission_fixture()
    old = admission.compose(prior, runtime, additions, contracts, rows)
    revision = json.loads((BATCH / 'reviewed_recovery_revision.json').read_bytes())
    plan_raw = (HERE.parent / revision['plan_path']).read_bytes()
    payload = (HERE.parent / revision['payload_path']).read_bytes()
    plan = json.loads(plan_raw)
    plan_pin, payload_pin = install.digest(plan_raw), install.digest(payload)
    assert plan_pin == revision['reviewed_plan_sha256']
    assert payload_pin == revision['reviewed_payload_sha256']
    row = {'id': plan['task_id'], 'handler': 'owner_native_project_work',
        'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [],
        'source_sha256': install.CALLBACK_SHA256,
        'params': {'parent_task_id': '3A01', 'plan_sha256': plan_pin}}
    assets = {'reviewed_plan.json': plan_raw, 'reviewed_payload.source': payload,
              'c02_reviewed_helpers.py': (HERE / 'owner_kernel_self_fd_install.py').read_bytes()}
    spec = {'schema': install.SCHEMA, 'reviewed_plan_sha256': plan_pin,
        'reviewed_payload_sha256': payload_pin, 'runtime_paths': {}, 'source_test_paths': {},
        'expected_extra_tools': {}, 'helper_asset': 'c02_reviewed_helpers.py',
        'helper_sha256': install.FROZEN_HELPER_SHA256,
        'package_paths': {'reviewed_plan.json': install.PACKAGE + '/plans/' + plan_pin + '.json',
                          'reviewed_payload.source': install.PACKAGE + '/blobs/' + payload_pin},
        'catalog_append': [row], 'assets': {name: install.digest(raw) for name, raw in assets.items()}}
    return old, {plan_pin: plan}, [row], spec, assets


def predecessor_fixture():
    observed = json.loads(FAILED_OBSERVATION.read_bytes())['row']
    event = copy.deepcopy(observed['receipt'])
    event['claim'] = copy.deepcopy(observed['owner_claim'])
    event['worker_result'] = {
        'state': observed['worker_event']['state'],
        'project_evidence': copy.deepcopy(observed['project_evidence']),
        'planner_receipt': copy.deepcopy(observed['planner_receipt']),
    }
    pin = install.digest(install.encoded(event))
    state = {'tasks': {install.FAILED_TASK: {
        'handler': 'owner_native_project_work', 'status': 'blocked',
        'owner_claim': copy.deepcopy(observed['owner_claim']),
        'result': {'verified': True, 'receipt': event, 'receipt_sha256': pin}}}}
    helper = SimpleNamespace(exact_s03=Mock(side_effect=lambda root, receipt: {
        'verified': True, 's03_item_id': install.FAILED_S03_ID,
        'receipt_sha256': install.digest(install.encoded(receipt))}))
    return state, pin, helper


class ScopeTests(unittest.TestCase):
    def test_append_changes_only_catalog_and_preserves_all_native_source_and_history_pins(self):
        old, plans, rows, spec, _ = fixture()
        baseline = copy.deepcopy(old)
        actual = install.compose(old, {}, {}, plans, rows, spec)
        expected = copy.deepcopy(old)
        expected['catalog']['tasks'].extend(copy.deepcopy(rows))
        expected['catalog_sha256'] = install.digest(install.encoded(expected['catalog']))
        self.assertEqual(actual, expected)
        self.assertEqual(old, baseline)
        self.assertEqual(actual['module_pins'], old['module_pins'])
        self.assertEqual(actual['project_executor'], old['project_executor'])
        self.assertEqual(actual['global_worker_cap'], 3)
        self.assertEqual(rows[0]['id'], install.REVIEWED_TASK)

    def test_any_runtime_or_source_test_addition_is_rejected(self):
        for runtime, additions in (({'scripts/owner_project_planner.py': b'new'}, {}),
                                   ({}, {'test_nox_c02_optional_starvation.py': b'new'})):
            with self.subTest(runtime=runtime, additions=additions):
                old, plans, rows, spec, _ = fixture()
                with self.assertRaisesRegex(install.Hold, 'RUNTIME_SCOPE'):
                    install.compose(old, runtime, additions, plans, rows, spec)

    def test_model_provenance_test_weakening_and_other_source_are_rejected_even_if_rehashed(self):
        for kind in ('model_origin', 'contract', 'source', 'tests'):
            with self.subTest(kind=kind):
                old, plans, rows, spec, _ = fixture()
                plan = copy.deepcopy(next(iter(plans.values())))
                if kind == 'model_origin':
                    plan['review_origin'] = 'MODEL_CANDIDATE'
                elif kind == 'contract':
                    plan['contract_sha256'] = install.FAILED_CONTRACT_SHA256
                elif kind == 'source':
                    plan['files'][0]['path'] = 'another.py'
                else:
                    plan['verification']['min_tests'] = 1
                pin = install.digest(install.encoded(plan))
                spec['reviewed_plan_sha256'] = pin
                rows[0]['params']['plan_sha256'] = pin
                with self.assertRaisesRegex(install.Hold, 'REVIEWED_(PLAN_SCOPE|EDIT_AND_TEST_SCOPE)'):
                    install.compose(old, {}, {}, {pin: plan}, rows, spec)

    def test_replay_dependency_and_model_contract_admission_are_rejected(self):
        for kind in ('replay', 'dependency', 'model_contract'):
            with self.subTest(kind=kind):
                old, plans, rows, spec, _ = fixture()
                if kind == 'replay':
                    old['catalog']['tasks'].extend(copy.deepcopy(rows))
                    old['catalog_sha256'] = install.digest(install.encoded(old['catalog']))
                elif kind == 'dependency':
                    rows[0]['deps'] = [install.FAILED_TASK]
                else:
                    rows[0]['params']['contract_sha256'] = install.FAILED_CONTRACT_SHA256
                with self.assertRaisesRegex(install.Hold, 'CATALOG_ROW_SCOPE'):
                    install.compose(old, {}, {}, plans, rows, spec)

    def test_three_exact_assets_are_required_and_tampering_or_older_plan_is_rejected(self):
        _, _, _, spec, assets = fixture()
        bundle = {name: base64.b64encode(raw).decode() for name, raw in assets.items()}
        decoded, helper = install.decode(bundle, spec)
        self.assertEqual(decoded, assets)
        self.assertTrue(callable(helper.wait_previous_descendants_stopped))
        changed = copy.deepcopy(bundle)
        changed['reviewed_payload.source'] = base64.b64encode(b'foreign source').decode()
        with self.assertRaisesRegex(install.Hold, 'ASSET_HASH'):
            install.decode(changed, spec)
        changed = copy.deepcopy(spec)
        changed['package_paths']['reviewed_plan.json'] = install.PACKAGE + '/plans/' + '0' * 64 + '.json'
        with self.assertRaisesRegex(install.Hold, 'ASSET_SCOPE'):
            install.decode(bundle, changed)
        changed = copy.deepcopy(bundle)
        changed['old_unreferenced_plan.json'] = base64.b64encode(b'{}').decode()
        with self.assertRaisesRegex(install.Hold, 'ASSET_SET'):
            install.decode(changed, spec)


class FailedModelTests(unittest.TestCase):
    def test_pinned_native_failure_and_synthetic_complete_receipt_are_distinguished(self):
        observed = json.loads(FAILED_OBSERVATION.read_bytes())['row']
        self.assertEqual(install.FAILED_RECEIPT_SHA256, observed['result']['receipt_sha256'])
        self.assertEqual(install.FAILED_CLAIM, observed['owner_claim'])
        self.assertEqual(install.FAILED_S03_ID, observed['s03']['s03_item_id'])
        state, pin, helper = predecessor_fixture()
        before = copy.deepcopy(state)
        with patch.object(install, 'FAILED_RECEIPT_SHA256', pin):
            proof = install.check_failed_model(state, Path('/local-fixture'), helper)
        self.assertEqual(state, before)
        self.assertEqual(proof['model_read_turns'], 10)
        self.assertEqual(proof['recovery_review_origin'], 'OWNER_REVIEWED')
        self.assertFalse(proof['model_source_changed'])
        helper.exact_s03.assert_called_once()

    def test_changed_claim_or_receipt_cannot_authorize_recovery(self):
        for kind in ('claim', 'status', 'receipt', 'source_changed'):
            with self.subTest(kind=kind):
                state, pin, helper = predecessor_fixture()
                task = state['tasks'][install.FAILED_TASK]
                if kind == 'claim':
                    task['owner_claim']['nonce'] = 'f' * 24
                elif kind == 'status':
                    task['status'] = 'done'
                elif kind == 'receipt':
                    task['result']['receipt_sha256'] = 'f' * 64
                else:
                    task['result']['receipt']['project_source_changed'] = True
                with patch.object(install, 'FAILED_RECEIPT_SHA256', pin):
                    with self.assertRaisesRegex(install.Hold, 'EXACT_FAILED_MODEL_RECEIPT'):
                        install.check_failed_model(state, Path('/local-fixture'), helper)
                helper.exact_s03.assert_not_called()

    def test_patch_test_or_other_failure_is_rejected_even_after_receipt_rehash(self):
        for kind in ('patch', 'test', 'short_trace', 'plan', 'reason'):
            with self.subTest(kind=kind):
                state, _, helper = predecessor_fixture()
                task = state['tasks'][install.FAILED_TASK]
                receipt = task['result']['receipt']
                event = receipt['worker_result']
                if kind in ('patch', 'test'):
                    event['planner_receipt']['trace'][0]['action'] = kind
                elif kind == 'short_trace':
                    event['planner_receipt']['trace'].pop()
                elif kind == 'plan':
                    event['project_evidence']['plan_sha256'] = 'f' * 64
                else:
                    event['project_evidence']['reason'] = 'MODEL_SLOT_BUSY'
                pin = install.digest(install.encoded(receipt))
                task['result']['receipt_sha256'] = pin
                with patch.object(install, 'FAILED_RECEIPT_SHA256', pin):
                    with self.assertRaisesRegex(install.Hold, 'FAILED_MODEL_NO_SOURCE_PROGRESS'):
                        install.check_failed_model(state, Path('/local-fixture'), helper)
                helper.exact_s03.assert_not_called()

    def test_changed_s03_identity_fails_closed(self):
        state, pin, helper = predecessor_fixture()
        helper.exact_s03.side_effect = None
        helper.exact_s03.return_value = {'verified': True, 's03_item_id': 'foreign', 'receipt_sha256': pin}
        with patch.object(install, 'FAILED_RECEIPT_SHA256', pin):
            with self.assertRaisesRegex(install.Hold, 'FAILED_MODEL_S03_CHANGED'):
                install.check_failed_model(state, Path('/local-fixture'), helper)


class TransactionTests(unittest.TestCase):
    def test_partial_package_apply_restores_config_removes_owned_assets_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, spec, assets = fixture()
            plan_path, payload_path = spec['package_paths'].values()
            frozen.atomic(root / install.CONFIG, b'old config')
            frozen.atomic(root / install.SOURCE / install.C02_SOURCE, b'existing C02')
            changes = {install.CONFIG: b'new config', plan_path: assets['reviewed_plan.json'],
                       payload_path: assets['reviewed_payload.source']}
            before = {install.CONFIG: b'old config', plan_path: None, payload_path: None}
            def fail_payload(path, raw, mode=0o600):
                if path == root / payload_path:
                    raise OSError('injected partial apply')
                frozen.atomic(path, raw, mode)
            helper = SimpleNamespace(read_regular=frozen.read_regular, atomic=fail_payload,
                                     rollback_transaction=frozen.rollback_transaction)
            applied = []
            with self.assertRaises(OSError):
                install.apply_tracked(root, changes, before, helper, applied)
            self.assertEqual(applied, list(changes))
            install.rollback_owned(root, changes, before, helper, applied)
            self.assertEqual((root / install.CONFIG).read_bytes(), b'old config')
            self.assertFalse((root / plan_path).exists())
            self.assertFalse((root / payload_path).exists())
            self.assertEqual((root / install.SOURCE / install.C02_SOURCE).read_bytes(), b'existing C02')

    def test_rollback_preserves_foreign_package_bytes_and_cas_preserves_foreign_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = install.PACKAGE + '/plans/' + 'a' * 64 + '.json'
            frozen.atomic(root / install.CONFIG, b'old config')
            before = {install.CONFIG: b'old config', asset: None}
            changes = {install.CONFIG: b'new config', asset: b'owned plan'}
            applied = []
            install.apply_tracked(root, changes, before, frozen, applied)
            frozen.atomic(root / asset, b'foreign plan')
            with self.assertRaisesRegex(install.Hold, 'NEW_ASSET_CHANGED_NO_CLEANUP'):
                install.rollback_owned(root, changes, before, frozen, applied)
            self.assertEqual((root / asset).read_bytes(), b'foreign plan')
            self.assertEqual((root / install.CONFIG).read_bytes(), b'old config')
            frozen.atomic(root / install.CONFIG, b'foreign config')
            attempted = []
            with self.assertRaisesRegex(install.Hold, 'CONCURRENT_WRITE'):
                install.apply_tracked(root, {install.CONFIG: b'new config'}, before, frozen, attempted)
            self.assertEqual(attempted, [])
            self.assertEqual((root / install.CONFIG).read_bytes(), b'foreign config')


class RestartSafetyTests(unittest.TestCase):
    def test_old_child_still_alive_blocks_update_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, _, _, spec, assets = fixture()
            state, synthetic_receipt_pin, s03 = predecessor_fixture()
            old['project_executor']['roots']['NOX_PROJECT_SOURCE']['path'] = str(root / install.SOURCE)
            old['module_pins']['owner_project_executor.py'] = 'e' * 64
            before = {'scripts/' + name: ('old ' + name).encode() for name in old['module_pins']}
            before['scripts/owner_subagent_dispatcher.py'] = (HERE / 'complete_executor_budget_20261118/runtime/owner_subagent_dispatcher.py').read_bytes()
            before['scripts/owner_project_model_client.py'] = (HERE / 'complete_executor_retries_20261118/runtime/owner_project_model_client.py').read_bytes()
            before['scripts/owner_autonomy_pool.py'] = b'OLD_POOL = True\n'
            for name in old['module_pins']:
                old['module_pins'][name] = install.digest(before['scripts/' + name])
            before[install.CONFIG] = install.encoded(old)
            marker = b'unchanged bootstrap fixture'
            for path, raw in {**before, install.MARKER: marker, 'state/owner_maintenance.lock': b'fixture'}.items():
                frozen.atomic(root / path, raw)
            # This fixture represents the native state before recovery. The
            # canonical repository source now contains the verified fix, so
            # use the exact preserved bootstrap preimage for the CAS scenario.
            preimage = (HERE / 'complete_executor_20261118/assets/ce_baseline_8657ad367e6dd25b48ca.source').read_bytes()
            self.assertEqual(install.digest(preimage), install.SOURCE_PREIMAGE_SHA256)
            frozen.atomic(root / install.SOURCE / install.C02_SOURCE, preimage)
            for name in install.TRUSTED_TESTS:
                frozen.atomic(root / install.SOURCE / name, (BATCH / 'trusted_tests' / name).read_bytes())
            snapshot = {'files_sha256': 'e' * 64, 'bootstrap_sha256': install.digest(marker), 'files': {}, 'git_pins': {}}
            spec.update(expected_native={path: install.digest(raw) for path, raw in before.items()},
                expected_bootstrap_sha256=install.digest(marker), expected_source_files_sha256=snapshot['files_sha256'])
            children = [{'pid': 123, 'start_ticks': 456, 'ppid': 122}]
            helper = SimpleNamespace(
                Hold=frozen.Hold, preimages=Mock(side_effect=lambda *args: dict(before)),
                read_regular=frozen.read_regular, atomic=frozen.atomic, relpath=frozen.relpath,
                protected_snapshot=Mock(return_value={'protected': 'unchanged'}), stop_clear=Mock(return_value=True),
                queue_idle=Mock(return_value=(state, [])),
                self_fd_children=Mock(return_value={'processes': [], 'children': children, 'unexpected_children': []}),
                exact_s03=s03.exact_s03, source_snapshot=Mock(return_value=snapshot),
                load_budget_module=Mock(return_value=(object(), object())), budget_preflight=Mock(return_value={'verified': True}),
                preserve_terminal_history=Mock(return_value={'verified': True}), stop_checked=Mock(),
                supervisor=Mock(return_value={'state': 'STOPPED'}),
                wait_previous_descendants_stopped=Mock(side_effect=frozen.Hold('OLD_CHILD_STILL_ALIVE')),
                start_checked=Mock(), start_update_checked=Mock())
            executor = SimpleNamespace(__file__=str(root / 'scripts/owner_project_executor.py'),
                                       validate_config=Mock(), validate_plan=Mock())
            with patch.object(install, 'ROOT', root), patch.object(install, 'decode', return_value=(assets, helper)), \
                    patch.object(install, 'FAILED_RECEIPT_SHA256', synthetic_receipt_pin), \
                    patch.dict(os.environ, NOX_OWNER_REQUEST_ID='123456', NOX_OWNER_SOURCE_SHA='a' * 40), \
                    patch.dict(sys.modules, owner_project_executor=executor), patch.object(sys, 'path', list(sys.path)), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(frozen.Hold, 'OLD_CHILD_STILL_ALIVE'):
                    install.run({}, spec, root)
            helper.stop_checked.assert_called_once()
            self.assertEqual(helper.wait_previous_descendants_stopped.call_count, 2)
            helper.start_checked.assert_not_called()
            helper.start_update_checked.assert_not_called()
            self.assertEqual((root / install.CONFIG).read_bytes(), before[install.CONFIG])
            self.assertEqual((root / install.MARKER).read_bytes(), marker)
            self.assertTrue(all(not (root / path).exists() for path in spec['package_paths'].values()))


if __name__ == '__main__':
    unittest.main()
