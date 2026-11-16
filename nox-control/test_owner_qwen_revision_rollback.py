"""Finite rollback: diagnosis, no-clobber writes and failure recovery in /tmp."""
import base64
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


PATH = Path(__file__).with_name('owner_qwen_revision_rollback.py')
SPEC = importlib.util.spec_from_file_location('rollback_candidate', PATH)
R = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(R)


def approval():
    return {'schema': R.REVIEW_SCHEMA, 'execution_revision': dict(R.REFERENCE),
            'diagnostic_sha256': R.DIAGNOSTIC_SHA, 'diagnostic_source_sha256': R.DIAGNOSTIC_SOURCE_SHA,
            'finalize_receipt_sha256': R.FINALIZE_SHA, 'expected_finalize_reason': R.FINALIZE_REASON,
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
        self.raw = PATH.with_name('owner_qwen_revision_failed_diagnostic.json').read_bytes()
        self.assertEqual(R.digest(self.raw), R.DIAGNOSTIC_SHA)
        self.patch = mock.patch.dict(R.BUNDLE, {R.DIAGNOSTIC_ASSET: base64.b64encode(self.raw).decode()})
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_lossless_actual_review_accepts_exact_download_failure(self):
        _, diagnostic, raw = R.review_gate(approval())
        self.assertEqual(raw, self.raw)
        self.assertEqual(diagnostic['log_diagnostics'][0]['mtime_ns'], 1794819351690963054)
        self.assertFalse(diagnostic['activation']['active'])

    def test_missing_review_does_not_load_helpers_write_or_touch_timer(self):
        with mock.patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '6912220000', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), \
             mock.patch.object(R, 'loaded', side_effect=AssertionError('helper executed')), \
             mock.patch.object(R, 'create', side_effect=AssertionError('write')), \
             mock.patch.object(R.signal, 'setitimer') as timer, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(), 2)
            timer.assert_not_called()

    def test_alternate_primary_code_or_finalizer_is_not_authorized(self):
        for key, value in (('primary_diagnosis_code', 'HOLD_UNRELATED_ERROR'),
                           ('finalize_receipt_sha256', 'a' * 64), ('primary_diagnosis_reviewed', False)):
            data = approval(); data[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(R.RollbackHold, 'PRIMARY_DIAGNOSIS_REVIEW_REQUIRED'):
                R.review_gate(data)

    def test_old_log_mtime_and_nonterminal_download_event_are_rejected(self):
        for change in ('old_time', 'last_event'):
            diagnostic = json.loads(self.raw)
            if change == 'old_time':
                diagnostic['log_diagnostics'][0]['mtime_ns'] = 1
            else:
                diagnostic['log_diagnostics'][0]['safe_events'].append({'state': 'UNRELATED'})
            raw = R.encode(diagnostic); pin = R.digest(raw); data = approval(); data['diagnostic_sha256'] = pin
            with self.subTest(change=change), mock.patch.object(R, 'DIAGNOSTIC_SHA', pin), \
                 mock.patch.dict(R.BUNDLE, {R.DIAGNOSTIC_ASSET: base64.b64encode(raw).decode()}), \
                 self.assertRaisesRegex(R.RollbackHold, 'CURRENT_DOWNLOAD_FAILURE'):
                R.review_gate(data)

    def test_actual_helper_closure_is_pinned_and_definition_only_loads(self):
        for name, pin in R.PINS.items():
            raw = PATH.with_name(name).read_bytes()
            self.assertEqual(R.digest(raw), pin, name)
            loaded = R.loaded(name, raw)
            self.assertEqual(loaded.__file__, str(R.SCRIPTS / name))
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
