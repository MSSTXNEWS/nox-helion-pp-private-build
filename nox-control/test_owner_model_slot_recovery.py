"""Local evidence and restart gates for two zero-turn model-slot retries.

No native server, model or S03 writes. The recovery-path regression uses real
temporary filesystem writes while substituting the supervisor and observations.
"""
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

import owner_model_slot_recovery as install
from test_owner_continuous_executor_install import fixture as base_fixture, frozen


HERE = Path(__file__).resolve().parent
BATCH = HERE / 'model_slot_recovery_20261118/batch.json'
OBSERVATIONS = HERE / 'model_slot_recovery_20261118/observed_predecessors.json'


def fixture():
    old, _, _, _, _ = base_fixture()
    old['module_pins']['owner_project_model_client.py'] = '4' * 64
    runtime = {'scripts/owner_project_model_client.py': b'FAIR_MODEL_SLOT = True\n'}
    batch = json.loads(BATCH.read_bytes())
    contracts = {}
    rows = copy.deepcopy(batch['catalog_append'])
    for row in rows:
        pin = row['params']['contract_sha256']
        contracts[pin] = json.loads((BATCH.parent / 'package/contracts' / (pin + '.json')).read_bytes())
        row['source_sha256'] = old['module_pins']['owner_subagent_dispatcher.py']
    return old, runtime, {}, contracts, rows


def predecessor_fixture():
    spec = json.loads(BATCH.read_bytes())
    observed = {row['id']: row for row in json.loads(OBSERVATIONS.read_bytes())['predecessors']}
    state = {'tasks': {}}
    for need in spec['recovery_requirements']:
        tid = need['predecessor_task_id']
        row = observed[tid]
        event = copy.deepcopy(row['receipt'])
        event['claim'] = copy.deepcopy(row['owner_claim'])
        event['worker_result'] = {
            'state': 'HOLD_PROJECT_PLANNER_MODEL_SLOT_BUSY',
            'project_evidence': copy.deepcopy(row['project_evidence']),
            'planner_receipt': copy.deepcopy(row['planner_receipt']),
        }
        value = {'verified': True, 'receipt': event,
                 'receipt_sha256': install.digest(install.encoded(event))}
        # Inspection omits some native receipt fields. Bind these synthetic,
        # complete local fixtures to their own canonical hashes, not live pins.
        need['predecessor_receipt_sha256'] = value['receipt_sha256']
        state['tasks'][tid] = {'handler': 'owner_native_project_work', 'status': 'blocked',
            'owner_claim': copy.deepcopy(row['owner_claim']), 'result': value}
    s03_ids = {need['predecessor_task_id']: need['predecessor_s03_item_id']
               for need in spec['recovery_requirements']}
    helper = SimpleNamespace(exact_s03=Mock(side_effect=lambda root, event: {
        'verified': True, 'receipt_sha256': install.digest(install.encoded(event)),
        's03_item_id': s03_ids[event['task_id']]}))
    return state, spec, helper


def set_path(doc, path, value):
    for key in path[:-1]:
        doc = doc[key]
    doc[path[-1]] = value


class CompositionTests(unittest.TestCase):
    def test_only_two_client_pins_and_append_two_rows_change(self):
        old, runtime, additions, contracts, rows = fixture()
        baseline = copy.deepcopy(old)
        actual = install.compose(old, runtime, additions, contracts, rows)
        expected = copy.deepcopy(old)
        pin = install.digest(runtime['scripts/owner_project_model_client.py'])
        expected['module_pins']['owner_project_model_client.py'] = pin
        expected['project_executor']['model']['source_pins']['owner_project_model_client.py'] = pin
        expected['catalog']['tasks'].extend(copy.deepcopy(rows))
        expected['catalog_sha256'] = install.digest(install.encoded(expected['catalog']))
        self.assertEqual(actual, expected)
        self.assertEqual(old, baseline)
        self.assertEqual(actual['catalog']['tasks'][:-2], baseline['catalog']['tasks'])
        self.assertEqual(actual['global_worker_cap'], 3)

    def test_source_additions_or_another_runtime_module_are_rejected(self):
        for extra_runtime, additions in (
                ({'scripts/owner_project_planner.py': b'changed'}, {}),
                ({}, {'test_nox_extra.py': b'new test'})):
            with self.subTest(extra_runtime=extra_runtime, additions=additions):
                old, runtime, _, contracts, rows = fixture()
                baseline = copy.deepcopy(old)
                runtime.update(extra_runtime)
                with self.assertRaisesRegex(install.Hold, 'RUNTIME_SCOPE'):
                    install.compose(old, runtime, additions, contracts, rows)
                self.assertEqual(old, baseline)

    def test_unchanged_client_and_mismatched_existing_client_bindings_are_rejected(self):
        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch):
                old, runtime, additions, contracts, rows = fixture()
                if mismatch:
                    old['project_executor']['model']['source_pins']['owner_project_model_client.py'] = 'f' * 64
                    reason = 'OLD_CLIENT_BINDING'
                else:
                    pin = install.digest(runtime['scripts/owner_project_model_client.py'])
                    old['module_pins']['owner_project_model_client.py'] = pin
                    old['project_executor']['model']['source_pins']['owner_project_model_client.py'] = pin
                    reason = 'CLIENT_UNCHANGED'
                with self.assertRaisesRegex(install.Hold, reason):
                    install.compose(old, runtime, additions, contracts, rows)

    def test_replay_dependency_and_callback_changes_are_rejected(self):
        for kind in ('replay', 'dependency', 'callback'):
            with self.subTest(kind=kind):
                old, runtime, additions, contracts, rows = fixture()
                if kind == 'replay':
                    old['catalog']['tasks'].append(copy.deepcopy(rows[0]))
                    old['catalog_sha256'] = install.digest(install.encoded(old['catalog']))
                elif kind == 'dependency':
                    rows[0]['deps'] = ['old.task']
                else:
                    rows[0]['source_sha256'] = 'f' * 64
                baseline = copy.deepcopy(old)
                with self.assertRaisesRegex(install.Hold, 'CATALOG_ROW_SCOPE'):
                    install.compose(old, runtime, additions, contracts, rows)
                self.assertEqual(old, baseline)


class PredecessorTests(unittest.TestCase):
    def test_exact_two_predecessors_require_exact_s03_and_preserve_history(self):
        state, spec, helper = predecessor_fixture()
        before = copy.deepcopy((state, spec))
        result = install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)
        self.assertEqual(set(result), set(state['tasks']))
        self.assertEqual(helper.exact_s03.call_count, 2)
        self.assertTrue(all(row['verified'] for row in result.values()))
        self.assertEqual((state, spec), before)

    def test_claim_receipt_and_terminal_status_drift_is_rejected(self):
        cases = (
            (('owner_claim', 'nonce'), 'foreign-claim'),
            (('status',), 'running'),
            (('result', 'verified'), False),
            (('result', 'receipt_sha256'), '0' * 64),
            (('result', 'receipt', 'claim', 'nonce'), 'foreign-receipt-claim'),
            (('result', 'receipt', 'job_id'), 'another-job'),
            (('result', 'receipt', 'phase'), 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED'),
            (('result', 'receipt', 'project_source_changed'), True),
        )
        for path, value in cases:
            with self.subTest(path=path):
                state, spec, helper = predecessor_fixture()
                task = state['tasks'][spec['recovery_requirements'][0]['predecessor_task_id']]
                set_path(task, path, value)
                with self.assertRaisesRegex(install.Hold, 'EXACT_BLOCKED_PREDECESSOR'):
                    install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)
                helper.exact_s03.assert_not_called()

    def test_planner_turn_trace_and_candidate_drift_is_rejected_even_after_queue_rehash(self):
        cases = (
            (('completed_model_turns',), 1),
            (('completed_model_turns',), False),
            (('trace',), [{'action': 'patch'}]),
            (('changed_candidate_paths',), ['forge_split_guard.py']),
            (('state',), 'HOLD_PROJECT_PLANNER_MODEL_TIMEOUT'),
            (('contract_sha256',), 'f' * 64),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                state, spec, helper = predecessor_fixture()
                need = spec['recovery_requirements'][0]
                task = state['tasks'][need['predecessor_task_id']]
                event = task['result']['receipt']
                set_path(event['worker_result']['planner_receipt'], path, value)
                task['result']['receipt_sha256'] = install.digest(install.encoded(event))
                with self.assertRaisesRegex(install.Hold, 'EXACT_BLOCKED_PREDECESSOR'):
                    install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)
                helper.exact_s03.assert_not_called()

    def test_pinned_non_slot_failure_cannot_authorize_recovery(self):
        state, spec, helper = predecessor_fixture()
        need = spec['recovery_requirements'][0]
        task = state['tasks'][need['predecessor_task_id']]
        event = task['result']['receipt']
        event['worker_result']['project_evidence']['reason'] = 'FAILED_TESTS'
        pin = install.digest(install.encoded(event))
        task['result']['receipt_sha256'] = need['predecessor_receipt_sha256'] = pin
        with self.assertRaisesRegex(install.Hold, 'PREDECESSOR_NOT_ZERO_TURN_SLOT_FAILURE'):
            install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)
        helper.exact_s03.assert_not_called()

    def test_changed_s03_identity_or_failed_readback_cannot_authorize_recovery(self):
        for proof in ({'verified': True, 's03_item_id': 'foreign-item'},
                      {'verified': False, 's03_item_id': 'unused'}):
            with self.subTest(proof=proof):
                state, spec, helper = predecessor_fixture()
                helper.exact_s03.side_effect = None
                helper.exact_s03.return_value = proof
                with self.assertRaisesRegex(install.Hold, 'PREDECESSOR_S03_CHANGED'):
                    install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)

    def test_retry_manifest_must_cover_exactly_the_new_catalog_ids(self):
        state, spec, helper = predecessor_fixture()
        spec['recovery_requirements'][1]['retry_task_id'] = spec['recovery_requirements'][0]['retry_task_id']
        with self.assertRaisesRegex(install.Hold, 'RETRY_BINDING'):
            install.check_recovery_predecessors(state, spec, Path('/local-fixture'), helper)
        helper.exact_s03.assert_not_called()


class RestartSafetyTests(unittest.TestCase):
    def test_old_child_still_alive_prevents_restore_start_after_stop_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, runtime, _, contracts, rows = fixture()
            state, spec, s03 = predecessor_fixture()
            old['project_executor']['roots']['NOX_PROJECT_SOURCE']['path'] = str(root / install.SOURCE)
            before = {'scripts/' + name: ('old ' + name).encode() for name in old['module_pins']}
            before['scripts/owner_autonomy_pool.py'] = b'OLD_POOL = True\n'
            for name in old['module_pins']:
                old['module_pins'][name] = install.digest(before['scripts/' + name])
            old['project_executor']['model']['source_pins']['owner_project_model_client.py'] = old['module_pins']['owner_project_model_client.py']
            for row in rows:
                row['source_sha256'] = old['module_pins']['owner_subagent_dispatcher.py']
            before[install.CONFIG] = install.encoded(old)
            marker = b'{"fixture":"unchanged marker"}'
            for path, raw in {**before, install.MARKER: marker, 'state/owner_maintenance.lock': b'fixture'}.items():
                frozen.atomic(root / path, raw)
            assets = {'client.py': next(iter(runtime.values()))}
            paths = {}
            for pin, contract in contracts.items():
                name = 'contract_' + pin + '.json'
                assets[name] = install.encoded(contract)
                paths[name] = 'state/dispatcher/project_executor/package/contracts/' + pin + '.json'
            snapshot = {'files_sha256': 'e' * 64, 'files': {}, 'git_pins': {},
                        'bootstrap_sha256': install.digest(marker)}
            spec.update(expected_native={path: install.digest(raw) for path, raw in before.items()},
                runtime_paths={'client.py': 'scripts/owner_project_model_client.py'},
                source_test_paths={}, package_paths=paths, catalog_append=rows,
                expected_bootstrap_sha256=install.digest(marker),
                expected_source_files_sha256=snapshot['files_sha256'], expected_extra_tools={})
            children = [{'pid': 123, 'start_ticks': 456, 'ppid': 122}]
            helper = SimpleNamespace(
                Hold=frozen.Hold, preimages=Mock(side_effect=lambda *args: dict(before)),
                read_regular=frozen.read_regular, atomic=frozen.atomic, relpath=frozen.relpath,
                protected_snapshot=Mock(return_value={'protected': 'unchanged'}),
                stop_clear=Mock(return_value=True), queue_idle=Mock(return_value=(state, [])),
                self_fd_children=Mock(return_value={'processes': [], 'children': children,
                                                    'unexpected_children': []}),
                exact_s03=s03.exact_s03, source_snapshot=Mock(return_value=snapshot),
                load_budget_module=Mock(return_value=(object(), object())),
                budget_preflight=Mock(return_value={'verified': True}),
                preserve_terminal_history=Mock(return_value={'verified': True}),
                stop_checked=Mock(), supervisor=Mock(return_value={'state': 'STOPPED'}),
                wait_previous_descendants_stopped=Mock(side_effect=frozen.Hold('OLD_CHILD_STILL_ALIVE')),
                start_checked=Mock(), start_update_checked=Mock(),
            )
            planner = SimpleNamespace(__file__=str(root / 'scripts/owner_project_planner.py'),
                                      validate_contract=Mock())
            # Contract validation occurs before stopping; source bytes are not
            # part of this process-lifecycle regression.
            for contract in contracts.values():
                for context in contract['context']:
                    frozen.atomic(root / install.SOURCE / context['path'], b'fixture context')
            with patch.object(install, 'ROOT', root), patch.object(install, 'decode', return_value=(assets, helper)), \
                    patch.dict(os.environ, NOX_OWNER_REQUEST_ID='123456', NOX_OWNER_SOURCE_SHA='a' * 40), \
                    patch.dict(sys.modules, owner_project_planner=planner), \
                    patch.object(sys, 'path', list(sys.path)), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(frozen.Hold, 'OLD_CHILD_STILL_ALIVE'):
                    install.run({}, spec, root)
            helper.stop_checked.assert_called_once()
            self.assertEqual(helper.wait_previous_descendants_stopped.call_count, 2)
            helper.start_checked.assert_not_called()
            helper.start_update_checked.assert_not_called()
            self.assertEqual((root / install.CONFIG).read_bytes(), before[install.CONFIG])
            self.assertEqual((root / 'scripts/owner_project_model_client.py').read_bytes(),
                             before['scripts/owner_project_model_client.py'])


if __name__ == '__main__':
    unittest.main()
