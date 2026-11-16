"""Finite rollback: diagnosis, no-clobber writes and failure recovery in /tmp."""
import base64
import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock


PATH = Path(__file__).with_name('owner_qwen_transport_rollback.py')
SPEC = importlib.util.spec_from_file_location('rollback_candidate', PATH)
R = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(R)


def approval():
    return {'schema': R.REVIEW_SCHEMA, 'execution_revision': dict(R.REFERENCE),
            'diagnostic_sha256': R.DIAGNOSTIC_SHA, 'diagnostic_source_sha256': R.DIAGNOSTIC_SOURCE_SHA,
            'operation_receipt_sha256': R.OPERATION_SHA, 'finalizer': dict(R.FINALIZER), 'expected_operation_state': R.OPERATION_STATE,
            'expected_finalizer_state': R.OPERATION_STATE, 'finalizer_action_completed': True,
            'primary_diagnosis_reviewed': True, 'primary_diagnosis_code': R.PRIMARY_DIAGNOSIS}


def own_file(path, raw, mode=0o600):
    path.write_bytes(raw); path.chmod(mode)
    return path


def target(path, before=b'failed', after=b'origin-held', mode=0o644):
    own_file(path, before)
    return {'label': path.name, 'path': path, 'before': before, 'after': after,
            'before_mode': 0o600, 'declared_mode': mode,
            'before_identity': R.identity(path.stat(), moved=True), 'intent': False, 'applied': False,
            'archive': path.parent / ('retired-' + path.name)}


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.raw = PATH.with_name('owner_qwen_transport_failed_diagnostic.json').read_bytes()
        self.assertEqual(R.digest(self.raw), R.DIAGNOSTIC_SHA)
        self.patch = mock.patch.dict(R.BUNDLE, {R.DIAGNOSTIC_ASSET: base64.b64encode(self.raw).decode()})
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_lossless_actual_review_accepts_exact_download_failure(self):
        _, diagnostic, raw = R.review_gate(approval())
        self.assertEqual(raw, self.raw)
        self.assertEqual(diagnostic['log_diagnostics'][0]['mtime_ns'], 1794826047769141396)
        self.assertFalse(diagnostic['activation']['active'])

    def test_missing_review_does_not_load_helpers_write_or_touch_timer(self):
        with mock.patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '6912220000', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
             mock.patch.object(R, 'loaded', side_effect=AssertionError('helper executed')), \
             mock.patch.object(R, 'create', side_effect=AssertionError('write')), \
             mock.patch.object(R.signal, 'setitimer') as timer, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(), 2)
            timer.assert_not_called()

    def test_alternate_primary_code_or_operation_is_not_authorized(self):
        for key, value in (('primary_diagnosis_code', 'HOLD_UNRELATED_ERROR'),
                           ('operation_receipt_sha256', 'a' * 64), ('primary_diagnosis_reviewed', False)):
            data = approval(); data[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(R.RollbackHold, 'PRIMARY_DIAGNOSIS_REVIEW_REQUIRED'):
                R.review_gate(data)

    def test_old_log_mtime_and_nonterminal_download_event_are_rejected(self):
        for change in ('old_time', 'last_event'):
            diagnostic = json.loads(self.raw)
            if change == 'old_time':
                diagnostic['log_diagnostics'][0]['mtime_ns'] = 1
            else:
                diagnostic['log_diagnostics'][0]['last_nonempty_line_terminal_code'] = 'HOLD_UNRELATED'
            raw = R.encode(diagnostic); pin = R.digest(raw); data = approval(); data['diagnostic_sha256'] = pin
            with self.subTest(change=change), mock.patch.object(R, 'DIAGNOSTIC_SHA', pin), \
                 mock.patch.dict(R.BUNDLE, {R.DIAGNOSTIC_ASSET: base64.b64encode(raw).decode()}), \
                 self.assertRaisesRegex(R.RollbackHold, 'CURRENT_DOWNLOAD_FAILURE'):
                R.review_gate(data)

    def test_actual_helper_closure_is_pinned_and_definition_only_loads(self):
        for name, pin in R.PINS.items():
            raw = PATH.with_name(name).read_bytes()
            self.assertEqual(R.digest(raw), pin, name)
            native = R.CORE_NATIVE if name == R.CORE_ASSET else name
            loaded = R.loaded(native, raw)
            self.assertEqual(loaded.__file__, str(R.SCRIPTS / native))
            self.assertTrue(callable(loaded.main))


class FilesystemTests(unittest.TestCase):
    def test_successful_replace_and_compensation_preserve_bytes_and_declared_modes(self):
        with tempfile.TemporaryDirectory() as d:
            row = target(Path(d) / 'source')
            R.apply_row(row, lambda: None)
            self.assertEqual(row['path'].read_bytes(), b'origin-held')
            self.assertEqual(stat.S_IMODE(row['path'].stat().st_mode), 0o644)
            self.assertEqual(row['after_identity'], R.identity(row['path'].stat(), moved=True))
            R.compensate_rows([row])
            self.assertEqual(row['path'].read_bytes(), b'failed')
            self.assertEqual(stat.S_IMODE(row['path'].stat().st_mode), 0o600)
            R.precheck_rows([row])

    def test_same_bytes_foreign_inode_or_mode_is_rejected_before_write(self):
        for change in ('inode', 'mode'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                row = target(Path(d) / 'source')
                if change == 'inode':
                    foreign = own_file(Path(d) / 'foreign', row['before'])
                    os.replace(foreign, row['path'])
                else:
                    row['path'].chmod(0o644)
                with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_TARGET_IDENTITY'):
                    R.precheck_rows([row], original_only=True)
                with self.assertRaisesRegex(R.RollbackHold, 'REPLACE_IDENTITY'):
                    R.apply_row(row, lambda: None)
                self.assertEqual(row['path'].read_bytes(), row['before'])

    def test_postreplace_fsync_failure_has_owned_inode_and_can_compensate(self):
        with tempfile.TemporaryDirectory() as d:
            row = target(Path(d) / 'source'); saved = []
            with mock.patch.object(R, 'sync_dir', side_effect=OSError('synthetic fsync')):
                with self.assertRaises(OSError):
                    R.apply_row(row, lambda: saved.append(copy.deepcopy(row)))
            self.assertEqual(row['path'].read_bytes(), row['after'])
            self.assertFalse(row['applied'])
            self.assertEqual(saved[-1]['after_identity'], R.identity(row['path'].stat(), moved=True))
            R.compensate_rows([row])
            self.assertEqual(row['path'].read_bytes(), row['before'])

    def test_retire_collision_never_overwrites_either_file(self):
        with tempfile.TemporaryDirectory() as d:
            row = target(Path(d) / 'new-source', after=None, mode=None)
            own_file(row['archive'], b'foreign')
            with self.assertRaises(FileExistsError):
                R.apply_row(row, lambda: None)
            self.assertEqual(row['path'].read_bytes(), row['before'])
            self.assertEqual(row['archive'].read_bytes(), b'foreign')

    def test_retire_fsync_failure_and_foreign_reappearance_remain_safe(self):
        with tempfile.TemporaryDirectory() as d:
            row = target(Path(d) / 'new-source', after=None, mode=None)
            with mock.patch.object(R, 'sync_dir', side_effect=OSError('synthetic fsync')):
                with self.assertRaises(OSError):
                    R.apply_row(row, lambda: None)
            self.assertTrue(row['applied']); self.assertFalse(row['path'].exists())
            R.compensate_rows([row]); self.assertEqual(row['path'].read_bytes(), row['before'])
            R.apply_row(row, lambda: None)
            own_file(row['path'], b'other!')
            with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_TARGET_CHANGED'):
                R.compensate_rows([row])
            self.assertEqual(row['path'].read_bytes(), b'other!')
            self.assertEqual(row['archive'].read_bytes(), row['before'])

    def test_all_targets_preflight_blocks_compensation_before_partial_restoration(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [target(Path(d) / name) for name in ('first', 'second')]
            for row in rows:
                R.apply_row(row, lambda: None)
            rows[0]['path'].chmod(0o640)
            with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_POSTIMAGE_IDENTITY'):
                R.compensate_rows(rows)
            self.assertEqual(rows[1]['path'].read_bytes(), rows[1]['after'])


class ControllerTests(unittest.TestCase):
    def test_both_controller_states_classified_before_any_compensation_stop(self):
        core = types.SimpleNamespace(DISPATCHER_SERVICE='dispatcher', PROXY_SERVICE='proxy', DISPATCHER='dispatcher.py',
             service_identity=mock.Mock(return_value={'pid': 10}), stop_dispatcher=mock.Mock())
        deploy = types.SimpleNamespace(proxy_identity=mock.Mock(return_value={'pid': 20}), stop_proxy=mock.Mock())
        helper = types.SimpleNamespace(service_state=lambda name: {'state': 'RUNNING' if name == 'dispatcher' else 'STOPPING'})
        result = {'dispatcher_stop_attempted': True, 'proxy_stop_attempted': True}
        with self.assertRaisesRegex(R.RollbackHold, 'UNSETTLED_CONTROLLER'):
            R.stop_settled_for_compensation(core, deploy, helper, {'dispatcher': {'pid': 10}, 'proxy': {'pid': 20}}, result)
        core.stop_dispatcher.assert_not_called(); deploy.stop_proxy.assert_not_called()

    def test_stop_intent_is_saved_before_timeout(self):
        core = types.SimpleNamespace(stop_dispatcher=mock.Mock(side_effect=TimeoutError()))
        deploy = types.SimpleNamespace(stop_proxy=mock.Mock()); result = {}; journal = []
        with self.assertRaises(TimeoutError):
            R.stop_owned_services(core, deploy, object(), {'dispatcher': {'pid': 10}}, result,
                                  lambda: journal.append(dict(result)))
        self.assertTrue(journal[0]['dispatcher_stop_attempted']); deploy.stop_proxy.assert_not_called()

    def test_existing_media_yield_requires_real_false(self):
        runtime = types.SimpleNamespace(queue_ids=lambda: {'queue_running': [], 'queue_pending': []})
        core = types.SimpleNamespace(queue_idle=lambda: None, document=lambda *a: ({'tasks': {}}, b''))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(R, 'STATE', Path(d)):
            (Path(d) / 'media').mkdir()
            path = Path(d) / 'media/training_yield.json'
            for active in (None, 0, 1, 'false', True, False):
                own_file(path, R.encode({'active': active}))
                if active is False:
                    R.media_idle(runtime, core)
                else:
                    with self.subTest(active=active), self.assertRaisesRegex(R.RollbackHold, 'ACTIVE_MEDIA_YIELD'):
                        R.media_idle(runtime, core)




class ThirdAttemptTests(unittest.TestCase):
    def test_entry_pins_exact_third_source_and_rejects_alternate_before_exec(self):
        entry = R.loaded('owner_qwen_transport_rollback_entry.py',
                         PATH.with_name('owner_qwen_transport_rollback_entry.py').read_bytes())
        self.assertEqual(entry.NAME, PATH.name)
        self.assertEqual(entry.SOURCE_SHA, R.digest(PATH.read_bytes()))
        self.assertEqual(entry.REVIEW, approval())
        with mock.patch.dict(entry.BUNDLE, {entry.NAME: base64.b64encode(b'print("must not execute")').decode()}), \
             mock.patch.object(entry.types, 'ModuleType', side_effect=AssertionError('executed unpinned module')), \
             self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
            entry.main()

    def test_frozen_sources_and_minimal_changed_function_set(self):
        old_path = PATH.with_name('owner_qwen_retry_rollback.py')
        self.assertEqual(R.digest(old_path.read_bytes()),
                         '61f70c64f1b459fac35133bdbb41eaf287cc7a26a121560c2178aff697ba6dee')
        self.assertEqual(R.digest(PATH.with_name('owner_qwen_revision_rollback.py').read_bytes()),
                         '0ed7a7a7622b7f2ace806fa189995bd39bc61bd96883ef3fed891095e4e7b535')
        def functions(path):
            return {node.name: ast.dump(node, include_attributes=False)
                    for node in ast.parse(path.read_bytes()).body if isinstance(node, ast.FunctionDef)}
        old, new = functions(old_path), functions(PATH)
        self.assertEqual(set(old) - set(new), {'absent_finalizer_and_activation'})
        self.assertEqual(set(new) - set(old), {'sealed_finalizer_and_no_activation'})
        self.assertEqual({name for name in set(old) & set(new) if old[name] != new[name]},
            {'review_gate', 'current_flags', 'native_diagnosis', 'plan_restore', 'plan_projection',
             'precheck_rows', 'apply_row', 'compensate_rows', 'main'})
        self.assertEqual(R.CURRENT_SOURCES[R.CORE_NATIVE], R.PINS[R.CORE_ASSET])
        self.assertEqual(R.CURRENT_SOURCES['qwen_student_training_entry_revision.py'],
                         '8291638636bb03f701802c634cf8b30d077a5176c33d3658fb5cb1c92d50f235')

    def test_synthetic_native_pending_receipts_and_expired_context_are_explicit(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(R, 'FAILED_AREA', Path(d)):
            core = types.SimpleNamespace(SCHEMA='NOX_QWEN_EXECUTION_REVISION_INSTALL_V1')
            operation = {'schema': core.SCHEMA, 'execution_revision': R.REFERENCE,
                'request': R.REFERENCE['request'], 'source_sha': R.REFERENCE['source_sha'],
                'descriptor_sha256': R.DESCRIPTOR_SHA, 'state': R.OPERATION_STATE,
                'start_command_issued': True, 'start_command_returncode': 0,
                'optimizer_permission_issued': False,
                'started_at': 1794824819.8026285, 'finished_at': 1794825456.6506858}
            finalizer = {'schema': core.SCHEMA, 'execution_revision': R.REFERENCE,
                'request': R.FINALIZER['request'], 'source_sha': R.FINALIZER['source_sha'],
                'state': R.OPERATION_STATE, 'continuation_of_existing_start': True,
                'start_command_issued': False, 'optimizer_permission_issued': False,
                'trainer': {'service': {'state': 'BACKOFF', 'pid': None}, 'process_identity': None},
                'started_at': 1794825598.8059433, 'finished_at': 1794826050.0344577}
            op_raw, fin_raw = R.encode(operation), R.encode(finalizer)
            own_file(Path(d) / 'operation_result.json', op_raw)
            fin_path = own_file(Path(d) / R.FINALIZE_NAME, fin_raw)
            final_ref = dict(R.FINALIZER, receipt_sha256=R.digest(fin_raw))
            ctx = {'execution': {'descriptor': {'bootstrap': {'expires_at': R.BOOTSTRAP_DEADLINE}}}}
            diagnostic = {'operation_result': operation, 'finalize_receipt': finalizer}
            with mock.patch.object(R, 'OPERATION_SHA', R.digest(op_raw)), \
                 mock.patch.object(R, 'FINALIZER', final_ref), \
                 mock.patch.object(R.time, 'time', return_value=R.BOOTSTRAP_DEADLINE + 100):
                result = R.native_diagnosis(core, ctx, approval(), diagnostic)
                self.assertEqual(result, {'operation_result.json': op_raw, R.FINALIZE_NAME: fin_raw})
                other = own_file(Path(d) / 'finalize-6919999999.json', b'{}')
                with self.assertRaisesRegex(R.RollbackHold, 'UNREVIEWED_FINALIZER_PRESENT'):
                    R.native_diagnosis(core, ctx, approval(), diagnostic)
                other.unlink()
                fin_path.unlink()
                with self.assertRaisesRegex(R.RollbackHold, 'FINALIZER_MISSING'):
                    R.native_diagnosis(core, ctx, approval(), diagnostic)
                own_file(fin_path, fin_raw)
                activation = Path(d) / 'activation.json'; activation.symlink_to(Path(d) / 'missing')
                with self.assertRaisesRegex(R.RollbackHold, 'ACTIVATION_EXISTS'):
                    R.native_diagnosis(core, ctx, approval(), diagnostic)
                activation.unlink()
                with mock.patch.object(R.time, 'time', return_value=R.BOOTSTRAP_DEADLINE):
                    with self.assertRaisesRegex(R.RollbackHold, 'BOOTSTRAP_NOT_EXPIRED'):
                        R.native_diagnosis(core, ctx, approval(), diagnostic)
                own_file(fin_path, fin_raw + b' ')
                with self.assertRaisesRegex(R.RollbackHold, 'FILE_SHA'):
                    R.native_diagnosis(core, ctx, approval(), diagnostic)

    def test_diagnostic_alternate_current_proofs_are_rejected(self):
        original = json.loads(PATH.with_name(R.DIAGNOSTIC_ASSET).read_bytes())
        for change in ('finalizer', 'deadline', 'active', 'pending', 'missing_hold', 'present_pause',
                       'budget_unproven', 'old_log', 'other_cause', 'not_completed'):
            diagnostic = copy.deepcopy(original)
            if change == 'finalizer':
                diagnostic['finalize_receipt']['sha256'] = 'a' * 64
            elif change == 'deadline':
                diagnostic['activation']['deadline'] += 1
            elif change in ('active', 'pending'):
                diagnostic['activation']['active' if change == 'active' else 'bootstrap_pending'] = True
            elif change == 'missing_hold':
                diagnostic['flags']['TRAIN_HOLD.flag'] = {'present': False}
            elif change == 'present_pause':
                diagnostic['flags']['TRAIN_PAUSE_REQUEST.flag'] = {'present': True, 'sha256': 'a' * 64}
            elif change == 'budget_unproven':
                diagnostic['primary_failure']['transport_budget_exhaustion_observed'] = False
            elif change == 'old_log':
                diagnostic['log_diagnostics'][0]['mtime_ns'] -= 3600 * 1_000_000_000
            elif change == 'other_cause':
                diagnostic['primary_failure']['code'] = 'HOLD_MEMFD_PUBLIC_DOWNLOAD_INTERRUPTED'
            raw = R.encode(diagnostic); pin = R.digest(raw)
            with self.subTest(change=change), mock.patch.object(R, 'DIAGNOSTIC_SHA', pin), \
                 mock.patch.dict(R.BUNDLE, {R.DIAGNOSTIC_ASSET: base64.b64encode(raw).decode()}):
                reviewed = approval()
                if change == 'not_completed':
                    reviewed['finalizer_action_completed'] = False
                with self.assertRaises(R.RollbackHold):
                    R.review_gate(reviewed)

    def test_current_flags_require_exact_owned_hold_and_pause_absence(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(R, 'STATE', Path(d)):
            core = types.SimpleNamespace(global_stop=mock.Mock())
            hold = own_file(Path(d) / 'TRAIN_HOLD.flag',
                ('OWNER_QWEN_WINDOW_FAILED request=' + R.REFERENCE['request'] + ' goal=1000\n').encode())
            expected = {'TRAIN_HOLD.flag': hold.read_bytes(), 'TRAIN_PAUSE_REQUEST.flag': None}
            self.assertEqual(R.current_flags(core), expected)
            pause = Path(d) / 'TRAIN_PAUSE_REQUEST.flag'; pause.symlink_to(Path(d) / 'missing')
            with self.assertRaisesRegex(R.RollbackHold, 'CURRENT_PAUSE_NOT_ABSENT'):
                R.current_flags(core)
            pause.unlink(); own_file(hold, b'foreign\n')
            with self.assertRaisesRegex(R.RollbackHold, 'FILE_SHA'):
                R.current_flags(core)


class AbsentPauseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = mock.patch.object(R, 'STATE', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        (self.root / 'private').mkdir(mode=0o700)
        self.hold = own_file(self.root / 'TRAIN_HOLD.flag', b'current-owned-HOLD\n')
        self.row = {'label': 'TRAIN_PAUSE_REQUEST.flag', 'path': self.root / 'TRAIN_PAUSE_REQUEST.flag',
            'before': None, 'after': b'archived-origin-EVALUATION_STALE-pause\n',
            'before_mode': None, 'before_identity': None, 'declared_mode': 0o600,
            'intent': False, 'applied': False, 'prepared': self.root / 'private/prepared-pause',
            'archive': self.root / 'private/restored-pause'}

    def test_absent_pause_is_created_without_overwrite_and_compensated_only_to_archive(self):
        hold_identity = R.identity(self.hold.stat())
        R.precheck_rows([self.row], original_only=True)
        projected = R.plan_projection([self.row])[0]
        self.assertIsNone(projected['before_sha256']); self.assertTrue(projected['restore_absent_owned_pause'])
        R.apply_row(self.row, lambda: None)
        self.assertEqual(self.row['path'].read_bytes(), self.row['after'])
        self.assertEqual(stat.S_IMODE(self.row['path'].stat().st_mode), 0o600)
        inode = self.row['path'].stat().st_ino
        R.precheck_rows([self.row]); R.compensate_rows([self.row])
        self.assertFalse(self.row['path'].exists())
        self.assertEqual(self.row['archive'].read_bytes(), self.row['after'])
        self.assertEqual(self.row['archive'].stat().st_ino, inode)
        self.assertEqual(R.identity(self.hold.stat()), hold_identity)
        R.precheck_rows([self.row], original_only=True)

    def test_kernel_move_then_exception_keeps_prepared_identity_and_can_compensate(self):
        original = R.rename_noreplace; saved = []
        def moved_then_fault(source, destination):
            original(source, destination)
            raise OSError('synthetic post-kernel interruption')
        with mock.patch.object(R, 'rename_noreplace', side_effect=moved_then_fault):
            with self.assertRaises(OSError):
                R.apply_row(self.row, lambda: saved.append(copy.deepcopy(self.row)))
        self.assertFalse(self.row['applied'])
        self.assertEqual(saved[-1]['after_identity'], R.identity(self.row['path'].stat(), moved=True))
        R.compensate_rows([self.row])
        self.assertFalse(self.row['path'].exists()); self.assertTrue(self.row['archive'].exists())

    def test_foreign_appearance_before_move_never_overwritten(self):
        original = R.rename_noreplace
        def race(source, destination):
            own_file(destination, b'foreign-pause\n')
            return original(source, destination)
        with mock.patch.object(R, 'rename_noreplace', side_effect=race):
            with self.assertRaises(FileExistsError):
                R.apply_row(self.row, lambda: None)
        self.assertEqual(self.row['path'].read_bytes(), b'foreign-pause\n')
        with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_TARGET_CHANGED'):
            R.compensate_rows([self.row])
        self.assertEqual(self.row['prepared'].read_bytes(), self.row['after'])

    def test_same_bytes_foreign_inode_or_mode_blocks_compensation(self):
        R.apply_row(self.row, lambda: None)
        own_file(self.root / 'foreign', self.row['after'])
        os.replace(self.root / 'foreign', self.row['path'])
        with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_POSTIMAGE_IDENTITY'):
            R.compensate_rows([self.row])
        self.assertFalse(self.row['archive'].exists())
        self.row['after_identity'] = R.identity(self.row['path'].stat(), moved=True)
        self.row['path'].chmod(0o640)
        with self.assertRaisesRegex(R.RollbackHold, 'FOREIGN_POSTIMAGE_IDENTITY'):
            R.compensate_rows([self.row])

    def test_compensation_archive_collision_preserves_both_files(self):
        R.apply_row(self.row, lambda: None)
        own_file(self.row['archive'], b'foreign-evidence')
        with self.assertRaises(FileExistsError):
            R.compensate_rows([self.row])
        self.assertEqual(self.row['path'].read_bytes(), self.row['after'])
        self.assertEqual(self.row['archive'].read_bytes(), b'foreign-evidence')

    def test_absence_restore_scope_is_not_a_general_create_api(self):
        self.row['label'] = 'other.flag'; self.row['path'] = self.root / 'other.flag'
        with self.assertRaisesRegex(R.RollbackHold, 'ABSENT_PAUSE_RESTORE_SCOPE'):
            R.apply_row(self.row, lambda: None)
        self.assertFalse(self.row['path'].exists())


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.rows = []
        self.core = types.SimpleNamespace(global_stop=lambda: None, ORIGIN_LINEAGE='a' * 64)
        self.patch = mock.patch.object(R, 'OUTPUT', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        self.six = self.checkpoint(6, 1); self.anchor = self.checkpoint(25, 2)
        self.core.ANCHOR = self.anchor
        self.ctx = {'certificate': {'checkpoint': str(self.root / self.six['directory']),
                     'checkpoint_manifest_sha256': self.six['manifest_sha256']}}
        self.save_ledger()

    def checkpoint(self, n, generation, *, revision=False):
        name = f'checkpoint-u{n:08d}-a{n:08d}-g{generation:020d}'
        folder = self.root / name; folder.mkdir(mode=0o700)
        state = {'successful_total': n, 'attempted_total': n, 'holdout_evaluated_successful_total': min(n, 10)}
        if revision:
            state['execution_binding'] = {'execution_revision': R.REFERENCE}
        raw_state = R.encode(state); own_file(folder / 'student_state.json', raw_state)
        manifest = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': name, 'successful_total': n,
                    'attempted_total': n, 'lineage_sha256': self.core.ORIGIN_LINEAGE,
                    'files_sha256': {'student_state.json': R.digest(raw_state)}}
        if revision:
            manifest['execution_binding'] = state['execution_binding']
        raw = R.encode(manifest); own_file(folder / 'checkpoint_manifest.json', raw)
        row = {'directory': name, 'manifest_sha256': R.digest(raw), 'successful_total': n,
               'attempted_total': n, 'retained': True}; self.rows.append(row)
        return dict(row)

    def save_ledger(self):
        own_file(self.root / 'owner_checkpoints.json', R.encode({'schema': 'NOX_QWEN_OWNED_CHECKPOINTS_V1',
                    'lineage_sha256': self.core.ORIGIN_LINEAGE, 'checkpoints': self.rows}))

    def test_old_six_and_exact25_metadata_inventory_is_stable_and_nonmutating(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        first = R.checkpoint_inventory(self.core, self.ctx); second = R.checkpoint_inventory(self.core, self.ctx)
        self.assertEqual(first, second)
        self.assertEqual(first['summary']['retained_checkpoints'], 2)
        self.assertTrue(first['summary']['metadata_only'])
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_incomplete_or_orphan_checkpoint_cannot_be_hidden_by_latest25(self):
        with self.subTest(partial=True):
            partial = self.root / '.checkpoint-incomplete'; partial.mkdir()
            with self.assertRaisesRegex(R.RollbackHold, 'INCOMPLETE_CHECKPOINT_PRESENT'):
                R.checkpoint_inventory(self.core, self.ctx)
            partial.rmdir()
        self.checkpoint(25, 3, revision=True)  # deliberately not recorded in the ledger
        with self.assertRaisesRegex(R.RollbackHold, 'ORPHAN_OR_MISSING_CHECKPOINT'):
            R.checkpoint_inventory(self.core, self.ctx)

    def test_new_revision_same_counter_and_later_updates_are_rejected(self):
        self.checkpoint(25, 3, revision=True); self.save_ledger()
        with self.assertRaisesRegex(R.RollbackHold, 'NEW_SAME_COUNTER_CHECKPOINT'):
            R.checkpoint_inventory(self.core, self.ctx)
        self.rows[-1]['successful_total'] = 26; self.rows[-1]['attempted_total'] = 26; self.save_ledger()
        with self.assertRaisesRegex(R.RollbackHold, 'NEW_CHECKPOINT_LEDGER_EVIDENCE'):
            R.checkpoint_inventory(self.core, self.ctx)


if __name__ == '__main__':
    unittest.main()
