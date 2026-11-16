"""Focused failures for the checkpoint25 execution-revision issuer."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


def load(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


I = load('owner_qwen_revision_install')
G = load('owner_qwen_training_guard')


def checkpoint(good=25, evaluated=25, loss=1.24):
    return {'successful_updates': good, 'evaluated_at_update': evaluated, 'holdout_loss': loss,
            'observed_file_bytes': 519902179, 'attempted_updates': good, 'skipped_updates': 0,
            'manifest_sha256': I.ANCHOR['manifest_sha256'], 'student_state_sha256': I.ANCHOR['student_state_sha256']}


def previous():
    p = G.policy_step(None, checkpoint(25, 10, 1.2653611116111279), 16 * 1024 ** 3,
                      43278336, 1794816284.2044637, G.DEFAULT_POLICY, 1.2653611116111279)
    # The native guard missed the actual eval10 checkpoint before the old bug;
    # its preserved observed_distinct counter is independently pinned at zero.
    p['observed_distinct_evaluations'] = 0
    return p


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.ctx = {'lineage': {'targets': {'parameters': 43278336}},
                    'certificate': {'final_holdout_loss': 1.303310558}}
        self.config = {'policy': dict(G.DEFAULT_POLICY)}

    def test_real_new_evaluation_clears_only_stale_latch_and_adds_one_observation(self):
        old = previous(); snapshot = copy.deepcopy(old)
        result = I.resumed_policy(G, old, checkpoint(), self.ctx, self.config, 16 * 1024 ** 3, 1794816384.0)
        self.assertEqual(old, snapshot)
        self.assertFalse(result['inhibit']); self.assertEqual(result['last_evaluation_update'], 25)
        self.assertEqual(result['observed_distinct_evaluations'], 1)
        self.assertEqual(result['best_holdout_loss'], 1.24)
        self.assertEqual(result['disk_floor_bytes'], old['disk_floor_bytes'])
        self.assertEqual(result['disk_early_threshold_bytes'], old['disk_early_threshold_bytes'])

    def test_copied_stale_loss_counter_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'REAL_SAME_COUNTER'):
            I.resumed_policy(G, previous(), checkpoint(evaluated=10), self.ctx, self.config, 16 * 1024 ** 3, 1794816384.0)

    def test_disk_hazard_cannot_be_cleared_by_evaluation(self):
        with self.assertRaisesRegex(RuntimeError, 'NOT_PERMISSIVE'):
            I.resumed_policy(G, previous(), checkpoint(), self.ctx, self.config, 10 * 1024 ** 3, 1794816384.0)

    def test_quality_history_is_not_reset(self):
        p = previous(); p['regression_streak'] = 1
        with self.assertRaisesRegex(RuntimeError, 'NOT_PERMISSIVE'):
            I.resumed_policy(G, p, checkpoint(loss=2.0), self.ctx, self.config, 16 * 1024 ** 3, 1794816384.0)

    def test_foreign_latch_is_rejected(self):
        p = previous(); p['reason'] = 'DISK_EARLY_MARGIN'
        with self.assertRaisesRegex(RuntimeError, 'REAL_SAME_COUNTER'):
            I.resumed_policy(G, p, checkpoint(), self.ctx, self.config, 16 * 1024 ** 3, 1794816384.0)

    def test_exact_native_stale_record_required(self):
        cp = checkpoint(evaluated=10, loss=1.2653611116111279)
        p = previous()
        row = {'state': 'INHIBITED', 'policy_state': p, 'checkpoint': cp}
        self.assertEqual(I.migration_policy(G, row, cp), p)
        row['policy_state']['latched_at'] += 1
        with self.assertRaisesRegex(RuntimeError, 'EXACT_STALE'):
            I.migration_policy(G, row, cp)


class FilesystemTests(unittest.TestCase):
    def test_create_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'receipt.json'; I.create(p, b'first')
            with self.assertRaises(FileExistsError):
                I.create(p, b'second')
            self.assertEqual(p.read_bytes(), b'first')

    def test_replace_rejects_foreign_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'record'; I.create(p, b'foreign')
            with self.assertRaisesRegex(RuntimeError, 'REPLACE_PREIMAGE'):
                I.replace(p, b'original', b'new')
            self.assertEqual(p.read_bytes(), b'foreign')

    def test_symlink_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'original'; p.write_bytes(b'x')
            alias = Path(folder) / 'alias'; alias.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                I.read(alias)

    def test_archive_creates_verified_recovery_before_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); state = root / 'state'; area = root / 'private'
            state.mkdir(); area.mkdir(); raw = b'owned stale flag\n'; name = 'TRAIN_PAUSE_REQUEST.flag'
            I.create(state / name, raw)
            with mock.patch.object(I, 'STATE', state), mock.patch.dict(I.FLAGS, {name: I.digest(raw)}):
                I.archive_flag(name, raw, area)
            self.assertFalse((state / name).exists())
            self.assertEqual((area / ('released-' + name)).read_bytes(), raw)

    def test_archive_collision_preserves_live_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); state = root / 'state'; area = root / 'private'
            state.mkdir(); area.mkdir(); raw = b'owned'; name = 'TRAIN_HOLD.flag'
            I.create(state / name, raw); I.create(area / ('released-' + name), b'foreign')
            with mock.patch.object(I, 'STATE', state), mock.patch.dict(I.FLAGS, {name: I.digest(raw)}):
                with self.assertRaises(FileExistsError):
                    I.archive_flag(name, raw, area)
            self.assertEqual((state / name).read_bytes(), raw)

    def test_strict_json_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'data'; p.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_JSON'):
                I.document(p)

    def test_rollback_preflight_rejects_foreign_source_without_touching_it(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'source'; p.write_bytes(b'bad')
            with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_FOREIGN_FILE'):
                I.rollback_preflight([(p, b'old', b'new', 0o644)], [], Path(folder), {})
            self.assertEqual(p.read_bytes(), b'bad')

    def test_rollback_preflight_accepts_unperformed_or_exact_owned_write(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'source'; p.write_bytes(b'new')
            absent = Path(folder) / 'not-created'
            self.assertTrue(I.rollback_preflight([(p, b'old', b'new', 0o644),
                (absent, None, b'planned', 0o600)], [], Path(folder), {}))


class BindingTests(unittest.TestCase):
    def test_dispatcher_single_exact_replacement(self):
        old = I.OLD_SOURCES[I.GUARD]
        raw = ("owner_qwen_training_guard.bind_dispatcher(globals(), '" + old + "')\n").encode()
        new = 'c' * 64
        with mock.patch.dict(I.OLD_SOURCES, {I.DISPATCHER: I.digest(raw)}):
            changed = I.patch_dispatcher(raw, new)
        self.assertIn(new.encode(), changed); self.assertNotIn(old.encode(), changed)

    def test_dispatcher_extra_matching_binding_rejected(self):
        old = I.OLD_SOURCES[I.GUARD]
        raw = ("owner_qwen_training_guard.bind_dispatcher(globals(), '" + old + "')\n").encode() * 2
        with mock.patch.dict(I.OLD_SOURCES, {I.DISPATCHER: I.digest(raw)}):
            with self.assertRaisesRegex(RuntimeError, 'BINDING_ANCHOR'):
                I.patch_dispatcher(raw, 'c' * 64)

    def test_protected_origin_not_a_runtime_target(self):
        self.assertFalse(set(I.PROTECTED) & set(I.CANDIDATES.values()))
        self.assertIn('qwen_student_training_entry.py', I.PROTECTED)
        self.assertEqual(I.CANDIDATES[I.STUDENT], I.STUDENT)


if __name__ == '__main__':
    unittest.main()
