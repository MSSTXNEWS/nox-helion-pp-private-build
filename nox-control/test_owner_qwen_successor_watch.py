"""Finite watcher flow with real private receipts and fake parent/issuer only."""
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import types
import unittest
from unittest.mock import Mock, patch

import owner_qwen_successor_watch as w

HERE = Path(__file__).resolve().parent
SHARED_PATH = HERE / 'owner_qwen_execution_successor.py'
shared = types.ModuleType('_watch_private_readers'); shared.__file__ = str(SHARED_PATH)
exec(compile(SHARED_PATH.read_bytes(), str(SHARED_PATH), 'exec'), shared.__dict__)


class Clock:
    def __init__(self):
        self.value = 0.0; self.sleeps = []; self.callback = None
    def monotonic(self): return self.value
    def sleep(self, seconds):
        if not 0 <= seconds <= .5: raise AssertionError('Unbounded fixture wait')
        self.value += seconds; self.sleeps.append(seconds)
        if self.callback: self.callback(len(self.sleeps))


class Fixture(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(); self.stack = ExitStack()
        self.root = Path(self.tmp.name); self.scripts = self.root / 'scripts'; self.scripts.mkdir()
        self.area = self.root / 'revision'; self.area.mkdir(mode=0o700)
        self.ref = {'request': '90001', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        self.who = {'pid': 2001, 'start_ticks': 5555, 'boot_id': 'a' * 36}
        self.trainer = {'process_identity': {'pid': 3001, 'start_ticks': 6666, 'boot_id': 'a' * 36},
                        'service': {'state': 'RUNNING', 'pid': 3000}}
        self.clock = Clock(); self.epoch = 1794830000.0; self.events = []; self.stop = False
        self.active = False; self.active_calls = 0
        self.cfg = self.root / 'config.json'; self.admission = self.root / 'admission.json'; self.wrapper = self.root / 'wrapper.sh'
        for path, raw in ((self.cfg, b'config'), (self.admission, b'admission'), (self.wrapper, b'wrapper')):
            self.private(path, raw)
        self.issuer_raw = b'# fixture issuer; never executed\n'
        self.watcher_raw = (HERE / 'owner_qwen_successor_watch.py').read_bytes()
        for name, raw in ((w.SHARED, SHARED_PATH.read_bytes()), (w.SELF, self.watcher_raw), (w.ISSUER, self.issuer_raw)):
            self.private(self.scripts / name, raw)
        self.ctx = {'config_sha256': w.digest(b'config'), 'execution': {'reference': self.ref, 'directory': self.area,
            'admission_sha256': w.digest(b'admission'), 'wrapper_sha256': w.digest(b'wrapper'), 'descriptor': {
                'created_at': self.epoch - 20, 'bootstrap': {'expires_at': self.epoch + 30},
                'activation_issuer_sha256': w.digest(self.issuer_raw), 'activation_watcher_sha256': w.digest(self.watcher_raw)}}}
        self.api = types.SimpleNamespace(read=shared.read, document=shared.document, Hold=shared.Hold,
            validate_reference=shared.validate_reference, process_identity_valid=shared.process_identity_valid,
            finite=shared.finite, sha=shared.sha, CONFIG=self.cfg, ADMISSION=self.admission, WRAPPER=self.wrapper,
            stop_active=lambda: self.stop, current_context=self.current_context, activation_status=self.activation_status)
        self.finalizer = Mock(side_effect=self.finalize)
        self.issuer = types.SimpleNamespace(finalize_same_process=self.finalizer)
        self.issuer_loads = []
        self.real_monitor = w.monitor
        self.stack.enter_context(patch.object(shared, 'OWNER_UID', os.geteuid()))
        self.stack.enter_context(patch.object(w, 'ROOT', self.root))
        self.stack.enter_context(patch.object(w, 'SCRIPTS', self.scripts))
        self.stack.enter_context(patch.object(w, '__file__', str(self.scripts / w.SELF)))
        self.stack.enter_context(patch.object(w, 'STOP_REQUESTED', False))
        self.stack.enter_context(patch.object(w, 'process_identity', return_value=self.who))
        # Native source/private directories require root. The synthetic fixture
        # keeps real nofollow/hash/mode IO but binds ownership to the test UID.
        self.stack.enter_context(patch.object(w, 'source', side_effect=self.fixture_source))
        self.stack.enter_context(patch.object(w, 'private_directory', side_effect=self.fixture_directory))
        self.stack.enter_context(patch.object(w, 'load', side_effect=self.load))
        self.stack.enter_context(patch.object(w.time, 'time', side_effect=lambda: self.epoch + self.clock.value))
        self.stack.enter_context(patch.object(w.time, 'monotonic', side_effect=self.clock.monotonic))
        self.stack.enter_context(patch.object(w.time, 'sleep', side_effect=self.clock.sleep))
        self.stack.enter_context(patch.object(w, 'monitor', side_effect=lambda *a, **k: self.real_monitor(
            *a, monotonic=self.clock.monotonic, sleep=self.clock.sleep, **k)))

    def tearDown(self):
        self.stack.close(); self.tmp.cleanup()

    @staticmethod
    def private(path, raw):
        path.write_bytes(raw); path.chmod(0o600)

    def fixture_source(self, path, expected=None):
        path = w.plain(path); info = path.stat(follow_symlinks=False)
        w.require(info.st_uid == os.geteuid() and info.st_nlink == 1 and not info.st_mode & 0o022, 'FIXTURE_SOURCE_SCOPE')
        return shared.read(path, 131072, expected=expected)

    def fixture_directory(self, path):
        info = w.plain(path).stat(follow_symlinks=False)
        w.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                  and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')

    def current_context(self, ref):
        shared.require(ref == self.ref, 'FIXTURE_REFERENCE')
        return self.ctx

    def activation_status(self, ctx):
        self.active_calls += 1
        return {'active': self.active, 'bootstrap_pending': not self.active,
                'permit_sha256': 'c' * 64 if self.active else None}

    def load(self, name, raw):
        if name == w.SHARED:
            self.assertEqual(w.digest(raw), w.SHARED_SHA); return self.api
        self.assertEqual(name, w.ISSUER); self.assertEqual(raw, self.issuer_raw)
        self.issuer_loads.append(name); return self.issuer

    def finalize(self, ref, start_sha, *, wait_seconds, stop_check):
        self.events.append('finalize')
        self.assertEqual(ref, self.ref); self.assertTrue(shared.sha(start_sha))
        self.assertGreater(wait_seconds, 0); self.assertLessEqual(wait_seconds, 3600)
        self.assertFalse(stop_check())
        self.active = True
        return {'state': 'SUCCESSOR_EXECUTION_EVALUATION_ACTIVE', 'active': True,
                'optimizer_permission_issued': True, 'ordinary_guard_verified': True}

    def start(self, ready_sha=None, mutate=None):
        if ready_sha is None:
            raw = (self.area / 'watcher_ready.json').read_bytes(); ready_sha = w.digest(raw)
        value = {'schema': w.START_SCHEMA, 'execution_revision': copy.deepcopy(self.ref),
            'start_command_issued': True, 'start_command_returncode': 0, 'watcher_ready_sha256': ready_sha,
            'trainer': copy.deepcopy(self.trainer), 'started_at': self.epoch + self.clock.value}
        if mutate: mutate(value)
        raw = w.encode(value); self.private(self.area / 'start_receipt.json', raw)
        return value, w.digest(raw)

    def parent(self, state, start_sha=None, mutate=None):
        value = {'schema': 'NOX_QWEN_EXECUTION_SUCCESSOR_INSTALL_V1', 'execution_revision': copy.deepcopy(self.ref),
            'state': state, 'finished_at': None, 'optimizer_permission_issued': False}
        if state == 'BOOTSTRAP_LOADING_PENDING':
            value.update(start_receipt_sha256=start_sha, finished_at=self.epoch + self.clock.value)
        if mutate: mutate(value)
        self.private(self.area / 'operation_result.json', w.encode(value))
        return value

    def result(self):
        return shared.document(self.area / 'watcher_result.json', 16384, private=True)[0]

    def flags_snapshot(self):
        return {p.name: p.read_bytes() for p in self.root.glob('*flag*')}


class MonitorTests(Fixture):
    def test_armed_before_start_progress_waits_then_one_same_process_finalize(self):
        self.parent('REVISION_INSTALLED_BOOTSTRAP_REQUIRED')
        def advance(n):
            if n == 1:
                ready, raw = shared.document(self.area / 'watcher_ready.json', private=True)
                self.assertFalse((self.area / 'start_receipt.json').exists())
                self.assertEqual(ready['execution_revision'], self.ref); self.assertFalse(ready['start_capability'])
                self.events.append('ready-before-start')
                _, self.start_sha = self.start(w.digest(raw)); self.parent('SINGLE_TRAINER_START_INTENT')
            elif n == 2: self.parent('SAME_COUNTER_EVALUATION_PENDING')
            elif n == 3: self.parent('REAL_EVALUATION_SAME_COUNTER_CHECKPOINT_VERIFIED')
            elif n == 4: self.parent('BOOTSTRAP_LOADING_PENDING', self.start_sha)
            elif n > 4: self.fail('Watcher polled again after its one finalizer call')
        self.clock.callback = advance
        value = w.run(self.ref)
        self.assertEqual(self.events, ['ready-before-start', 'finalize'])
        self.finalizer.assert_called_once(); self.assertTrue(value['finalizer_called_once'])
        self.assertTrue(self.result()['active']); self.assertEqual(self.flags_snapshot(), {})
        self.assertEqual({p.name for p in self.area.iterdir()}, {'watcher_claim.json', 'watcher_ready.json',
            'start_receipt.json', 'operation_result.json', 'watcher_result.json'})

    def test_already_active_is_read_only_no_issuer_import_or_pause(self):
        self.active = True
        value = w.run(self.ref)
        self.assertEqual(value['state'], 'ACTIVATION_OBSERVED_READ_ONLY')
        self.assertTrue(value['read_only']); self.assertFalse(value['optimizer_permission_issued'])
        self.finalizer.assert_not_called(); self.assertEqual(self.issuer_loads, [])
        self.assertEqual(self.flags_snapshot(), {})

    def test_late_activation_between_parent_and_finalizer_prevents_delegation(self):
        _, start_sha = self.start('d' * 64); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        calls = [False, True, True]
        def activated(ctx):
            active = calls.pop(0)
            return {'active': active, 'bootstrap_pending': not active, 'permit_sha256': 'c' * 64 if active else None}
        with patch.object(self.api, 'activation_status', side_effect=activated):
            value = w.monitor(self.api, self.ctx, 'd' * 64)
        self.assertEqual(value['state'], 'ACTIVATION_OBSERVED_READ_ONLY')
        self.finalizer.assert_not_called(); self.assertEqual(self.issuer_loads, [])

    def test_finalizer_pending_or_failure_is_never_automatically_retried(self):
        _, start_sha = self.start('d' * 64); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        self.finalizer.side_effect = None
        self.finalizer.return_value = {'state': 'BOOTSTRAP_LOADING_PENDING', 'active': False, 'optimizer_permission_issued': False}
        value = w.monitor(self.api, self.ctx, 'd' * 64)
        self.assertFalse(value['active']); self.finalizer.assert_called_once()
        self.assertEqual(self.clock.sleeps, [])

    def test_start_identity_ready_reference_rc_or_service_mismatch_cannot_activate(self):
        mutations = (
            lambda v: v['execution_revision'].update(request='90002'),
            lambda v: v.update(watcher_ready_sha256='e' * 64),
            lambda v: v.update(start_command_returncode=True),
            lambda v: v['trainer']['process_identity'].update(pid=True),
            lambda v: v['trainer']['process_identity'].update(start_ticks=0),
            lambda v: v['trainer']['service'].update(state='FATAL'),
            lambda v: v.update(started_at=self.epoch - 21),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutations.index(mutate)):
                _, start_sha = self.start('d' * 64, mutate); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
                with self.assertRaises(w.Hold): w.monitor(self.api, self.ctx, 'd' * 64)
                self.finalizer.assert_not_called(); self.assertEqual(self.issuer_loads, [])

    def test_parent_seal_requires_same_start_sha_reference_and_false_permission(self):
        _, start_sha = self.start('d' * 64)
        for mutate in (lambda v: v.update(start_receipt_sha256='e' * 64),
                       lambda v: v['execution_revision'].update(request='90002'),
                       lambda v: v.update(optimizer_permission_issued=True)):
            self.parent('BOOTSTRAP_LOADING_PENDING', start_sha, mutate)
            with self.assertRaises(w.Hold): w.monitor(self.api, self.ctx, 'd' * 64)
        self.finalizer.assert_not_called()

    def test_unsealed_pending_waits_for_final_finished_at_before_one_finalize(self):
        _, start_sha = self.start('d' * 64)
        self.parent('BOOTSTRAP_LOADING_PENDING', start_sha, lambda v: v.update(finished_at=None))
        self.assertFalse(w.pending_parent(self.api, self.ctx, start_sha))
        def seal(n):
            self.finalizer.assert_not_called()
            self.assertEqual(n, 1)
            self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        self.clock.callback = seal
        value = w.monitor(self.api, self.ctx, 'd' * 64)
        self.finalizer.assert_called_once(); self.assertTrue(value['active'])
        self.assertEqual(self.clock.sleeps, [.5])

    def test_source_or_current_admission_drift_prevents_issuer_load(self):
        _, start_sha = self.start('d' * 64); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        self.private(self.scripts / w.ISSUER, b'foreign issuer')
        with self.assertRaises(shared.Hold): w.monitor(self.api, self.ctx, 'd' * 64)
        self.finalizer.assert_not_called(); self.assertEqual(self.issuer_loads, [])
        self.private(self.scripts / w.ISSUER, self.issuer_raw)
        self.private(self.admission, b'foreign admission')
        with self.assertRaises(shared.Hold): w.monitor(self.api, self.ctx, 'd' * 64)
        self.finalizer.assert_not_called()

    def test_stop_and_ttl_never_call_issuer_or_write_flags(self):
        self.stop = True
        with self.assertRaisesRegex(w.Hold, 'OWNER_STOP'): w.monitor(self.api, self.ctx, 'd' * 64)
        self.stop = False
        self.ctx['execution']['descriptor']['bootstrap']['expires_at'] = self.epoch
        with self.assertRaisesRegex(w.Hold, 'TTL'): w.monitor(self.api, self.ctx, 'd' * 64)
        self.ctx['execution']['descriptor']['bootstrap']['expires_at'] = self.epoch + 1
        with self.assertRaisesRegex(w.Hold, 'EXPIRED'): w.monitor(self.api, self.ctx, 'd' * 64)
        self.finalizer.assert_not_called(); self.assertEqual(self.flags_snapshot(), {})

    def test_sigterm_during_delegated_wait_is_exposed_to_issuer_stop_gate(self):
        def advance(n):
            if n == 1:
                _, start_sha = self.start(); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        self.clock.callback = advance
        def cancelled(ref, start_sha, *, wait_seconds, stop_check):
            self.assertFalse(stop_check()); w.stop_signal()
            self.assertTrue(stop_check())
            raise RuntimeError('HOLD_QWEN_SUCCESSOR_INSTALL_OWNER_STOP')
        self.finalizer.side_effect = cancelled
        value = w.run(self.ref)
        self.finalizer.assert_called_once()
        self.assertIsNone(value['active']); self.assertIsNone(value['optimizer_permission_issued'])
        self.assertEqual(value['activation_observation'], 'NOT_RECHECKED_AFTER_EXCEPTION')
        self.assertFalse(value['flags_changed_by_watcher']); self.assertEqual(self.flags_snapshot(), {})


class ImmutableAndDeadlineTests(Fixture):
    def test_duplicate_claim_never_overwrites_or_arms_second_watcher(self):
        claim = {'schema': w.CLAIM_SCHEMA, 'execution_revision': self.ref, 'first': True}
        original = w.encode(claim); self.private(self.area / 'watcher_claim.json', original)
        with self.assertRaises(FileExistsError): w.run(self.ref)
        self.assertEqual((self.area / 'watcher_claim.json').read_bytes(), original)
        self.assertFalse((self.area / 'watcher_ready.json').exists())
        self.assertFalse((self.area / 'watcher_result.json').exists())
        self.finalizer.assert_not_called()

    def test_deadline_is_recorded_safely_after_arm_without_flag_or_service_action(self):
        self.private(self.root / 'foreign.flag', b'preserved')
        before = self.flags_snapshot()
        with patch.object(self.api, 'activation_status', side_effect=w.Deadline):
            value = w.run(self.ref)
        self.assertEqual(value['state'], 'HOLD_QWEN_SUCCESSOR_WATCH_DEADLINE')
        self.assertIsNone(value['active']); self.assertIsNone(value['optimizer_permission_issued'])
        self.assertEqual(value['activation_observation'], 'NOT_RECHECKED_AFTER_EXCEPTION')
        self.assertEqual(value['service_actions'], 0); self.assertFalse(value['flags_changed_by_watcher'])
        self.assertEqual(self.result(), value); self.assertEqual(self.flags_snapshot(), before)
        self.finalizer.assert_not_called()
        for name in ('watcher_claim.json', 'watcher_ready.json', 'watcher_result.json'):
            self.assertEqual(stat.S_IMODE((self.area / name).stat().st_mode), 0o600)

    def test_deadline_after_delegated_permit_publish_does_not_claim_inactive(self):
        def start_parent(n):
            if n == 1:
                _, start_sha = self.start(); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        self.clock.callback = start_parent
        committed = w.encode({'schema': 'FIXTURE_PRIVATE_ACTIVATION', 'execution_revision': self.ref})
        def publish_then_interrupt(ref, start_sha, *, wait_seconds, stop_check):
            self.assertFalse(stop_check())
            self.private(self.area / 'activation.json', committed)
            self.active = True
            raise w.Deadline()
        self.finalizer.side_effect = publish_then_interrupt
        value = w.run(self.ref)
        self.finalizer.assert_called_once()
        self.assertTrue(self.active)
        self.assertEqual((self.area / 'activation.json').read_bytes(), committed)
        self.assertEqual(value['state'], 'HOLD_QWEN_SUCCESSOR_WATCH_DEADLINE')
        self.assertIsNone(value['active']); self.assertIsNone(value['optimizer_permission_issued'])
        self.assertEqual(value['activation_observation'], 'NOT_RECHECKED_AFTER_EXCEPTION')
        self.assertFalse(value['flags_changed_by_watcher']); self.assertEqual(self.flags_snapshot(), {})
        self.assertEqual(self.result(), value)

    def test_partial_start_json_can_complete_within_two_seconds(self):
        self.private(self.area / 'start_receipt.json', b'{')
        def finish(n):
            if n == 2: self.start('d' * 64)
        self.clock.callback = finish
        value, raw_sha = w.start_receipt(self.api, self.ctx, 'd' * 64)
        self.assertEqual(value['execution_revision'], self.ref); self.assertTrue(shared.sha(raw_sha))
        self.assertLessEqual(self.clock.value, 2); self.assertEqual(len(self.clock.sleeps), 2)

    def test_partial_start_json_expires_without_semantic_relaxation(self):
        self.private(self.area / 'start_receipt.json', b'{')
        with self.assertRaisesRegex(w.Hold, 'START_PARTIAL_JSON'):
            w.start_receipt(self.api, self.ctx, 'd' * 64)
        self.assertGreaterEqual(self.clock.value, 2); self.assertLess(self.clock.value, 2.051)
        self.finalizer.assert_not_called(); self.assertEqual(self.flags_snapshot(), {})

    def test_only_file_changed_retry_not_private_mode_or_invalid_semantics(self):
        self.start('d' * 64)
        original_document = self.api.document; count = [0]
        def changed_then_stable(*args, **kwargs):
            count[0] += 1
            if count[0] == 1: raise shared.Hold('HOLD_QWEN_REVISION_FILE_CHANGED')
            return original_document(*args, **kwargs)
        with patch.object(self.api, 'document', side_effect=changed_then_stable):
            w.start_receipt(self.api, self.ctx, 'd' * 64)
        self.assertEqual(count[0], 2)
        self.clock.sleeps.clear(); (self.area / 'start_receipt.json').chmod(0o644)
        with self.assertRaises(shared.Hold): w.start_receipt(self.api, self.ctx, 'd' * 64)
        self.assertEqual(self.clock.sleeps, [])

    def test_parent_atomic_replace_race_retries_only_file_changed_within_two_seconds(self):
        _, start_sha = self.start('d' * 64); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        real = self.api.document; calls = [0]
        def replaced(*args, **kwargs):
            calls[0] += 1
            if calls[0] <= 2: raise shared.Hold('HOLD_QWEN_REVISION_FILE_CHANGED')
            return real(*args, **kwargs)
        with patch.object(self.api, 'document', side_effect=replaced):
            self.assertTrue(w.pending_parent(self.api, self.ctx, start_sha))
        self.assertEqual(calls[0], 3); self.assertLessEqual(self.clock.value, 2)
        self.clock.sleeps.clear()
        with patch.object(self.api, 'document', side_effect=shared.Hold('HOLD_QWEN_REVISION_PRIVATE_FILE')):
            with self.assertRaises(shared.Hold): w.pending_parent(self.api, self.ctx, start_sha)
        self.assertEqual(self.clock.sleeps, [])

    def test_parent_unstable_race_expires_and_stop_never_authorizes(self):
        _, start_sha = self.start('d' * 64); self.parent('BOOTSTRAP_LOADING_PENDING', start_sha)
        with patch.object(self.api, 'document', side_effect=shared.Hold('HOLD_QWEN_REVISION_FILE_CHANGED')):
            with self.assertRaisesRegex(w.Hold, 'PARENT_FILE_UNSTABLE'):
                w.pending_parent(self.api, self.ctx, start_sha)
        self.assertGreaterEqual(self.clock.value, 2); self.assertLess(self.clock.value, 2.051)
        self.stop = True; before = len(self.clock.sleeps)
        with patch.object(self.api, 'document', side_effect=shared.Hold('HOLD_QWEN_REVISION_FILE_CHANGED')):
            with self.assertRaisesRegex(w.Hold, 'PARENT_FILE_UNSTABLE'):
                w.pending_parent(self.api, self.ctx, start_sha)
        self.assertEqual(len(self.clock.sleeps), before); self.finalizer.assert_not_called()

    def test_unknown_exception_text_and_finalizer_extra_content_are_not_exported(self):
        self.assertEqual(w.sanitized_error(RuntimeError('secret://must-not-export')), 'HOLD_QWEN_SUCCESSOR_WATCH_FAILURE')
        projected = w.safe_finalizer_result({'state': 'ACTIVE', 'active': True, 'private_text': 'must-not-export'})
        self.assertEqual(projected, {'state': 'ACTIVE', 'active': True})
        with self.assertRaises(w.Hold): w.safe_finalizer_result({'state': 'ACTIVE', 'active': 1})
        self.assertEqual(w.safe_finalizer_result({'state': 'HOLD', 'active': None, 'optimizer_permission_issued': None}),
                         {'state': 'HOLD', 'active': None, 'optimizer_permission_issued': None})
        with self.assertRaises(w.Hold): w.safe_finalizer_result({'state': 'HOLD', 'read_only': None})


if __name__ == '__main__':
    unittest.main()
